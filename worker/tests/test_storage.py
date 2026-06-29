from pathlib import Path
from uuid import uuid4

import pytest

from derlem_worker.storage import ContentAddressedStore


def test_ingest_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("birinci\nikinci\n", encoding="utf-8")
    store = ContentAddressedStore(tmp_path / "store")

    first = store.ingest_file(source)
    second = store.ingest_file(source)

    assert first == second
    assert first.byte_size == len(source.read_bytes())
    assert first.line_count == 2
    assert first.detected_encoding == "UTF-8"
    assert (store.root / first.storage_key).read_bytes() == source.read_bytes()


def test_ingest_counts_final_line_without_newline(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("birinci\nikinci", encoding="utf-8")

    stored = ContentAddressedStore(tmp_path / "store").ingest_file(source)

    assert stored.line_count == 2


def test_ingest_reports_bounded_progress(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("birinci\nikinci\nucuncu", encoding="utf-8")
    updates: list[dict[str, int]] = []

    stored = ContentAddressedStore(tmp_path / "store").ingest_file(
        source,
        progress_callback=updates.append,
        progress_interval_bytes=5,
    )

    assert len(updates) >= 2
    assert updates[-1] == {
        "input_bytes_processed": stored.byte_size,
        "input_bytes_total": stored.byte_size,
        "lines_read": stored.line_count,
    }


def test_ingest_bytes_is_utf8_validated_and_idempotent(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "store")
    content = "örnek belge".encode()

    first = store.ingest_bytes(content)
    second = store.ingest_bytes(content)

    assert first == second
    assert first.byte_size == len(content)
    assert first.line_count == 1
    assert (store.root / first.storage_key).read_bytes() == content


def test_ingest_bytes_rejects_invalid_utf8(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "store")

    with pytest.raises(UnicodeDecodeError):
        store.ingest_bytes(b"\xff")


def test_resumable_ingest_preserves_and_reuses_verified_checkpoint(tmp_path: Path) -> None:
    source = tmp_path / "large.txt"
    source.write_bytes((b"Turkce veri satiri\n" * 150_000) + b"son satir")
    store = ContentAddressedStore(tmp_path / "store")
    checkpoint_id = uuid4()

    def interrupt_after_first_chunk(progress: dict[str, int]) -> None:
        if "resumed_from_bytes" in progress:
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="simulated interruption"):
        store.ingest_file_resumable(
            source,
            checkpoint_id=checkpoint_id,
            progress_callback=interrupt_after_first_chunk,
            progress_interval_bytes=256 * 1024,
        )

    checkpoint = store.checkpoint_path(checkpoint_id)
    interrupted_size = checkpoint.stat().st_size
    assert 0 < interrupted_size < source.stat().st_size

    outcome = store.ingest_file_resumable(
        source,
        checkpoint_id=checkpoint_id,
        progress_interval_bytes=256 * 1024,
    )

    assert outcome.resumed_from_bytes == interrupted_size
    assert outcome.checkpoint_revalidated_bytes == interrupted_size
    assert outcome.checkpoint_reset is False
    assert checkpoint.exists()
    assert (store.root / outcome.stored.storage_key).read_bytes() == source.read_bytes()

    store.discard_checkpoint(checkpoint_id)
    assert not checkpoint.exists()


def test_resumable_ingest_restarts_when_source_prefix_changed(tmp_path: Path) -> None:
    source = tmp_path / "changing.txt"
    source.write_bytes(b"a" * (2 * 1024 * 1024 + 17))
    store = ContentAddressedStore(tmp_path / "store")
    checkpoint_id = uuid4()

    def interrupt_after_first_chunk(progress: dict[str, int]) -> None:
        if "resumed_from_bytes" in progress:
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError):
        store.ingest_file_resumable(
            source,
            checkpoint_id=checkpoint_id,
            progress_callback=interrupt_after_first_chunk,
            progress_interval_bytes=256 * 1024,
        )

    changed = bytearray(source.read_bytes())
    changed[0] = ord("b")
    source.write_bytes(changed)

    outcome = store.ingest_file_resumable(source, checkpoint_id=checkpoint_id)

    assert outcome.resumed_from_bytes == 0
    assert outcome.checkpoint_revalidated_bytes == 0
    assert outcome.checkpoint_reset is True
    assert (store.root / outcome.stored.storage_key).read_bytes() == bytes(changed)


def test_resumable_ingest_restarts_oversized_checkpoint(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("kisa kaynak\n", encoding="utf-8")
    store = ContentAddressedStore(tmp_path / "store")
    checkpoint_id = uuid4()
    store.checkpoint_path(checkpoint_id).write_bytes(source.read_bytes() + b"fazla")

    outcome = store.ingest_file_resumable(source, checkpoint_id=checkpoint_id)

    assert outcome.checkpoint_reset is True
    assert outcome.resumed_from_bytes == 0
    assert (store.root / outcome.stored.storage_key).read_bytes() == source.read_bytes()


def test_published_checkpoint_detaches_before_source_growth_resume(tmp_path: Path) -> None:
    source = tmp_path / "growing.txt"
    original = b"a" * (1024 * 1024 + 13)
    source.write_bytes(original)
    store = ContentAddressedStore(tmp_path / "store")
    checkpoint_id = uuid4()

    first = store.ingest_file_resumable(source, checkpoint_id=checkpoint_id)
    first_target = store.root / first.stored.storage_key
    source.write_bytes(original + b"\nyeni satir")

    second = store.ingest_file_resumable(source, checkpoint_id=checkpoint_id)

    assert second.resumed_from_bytes == len(original)
    assert first_target.read_bytes() == original
    assert (store.root / second.stored.storage_key).read_bytes() == source.read_bytes()


def test_published_checkpoint_resets_without_mutating_old_object(tmp_path: Path) -> None:
    source = tmp_path / "replaced.txt"
    original = b"a" * (1024 * 1024 + 13)
    replacement = b"b" * len(original)
    source.write_bytes(original)
    store = ContentAddressedStore(tmp_path / "store")
    checkpoint_id = uuid4()

    first = store.ingest_file_resumable(source, checkpoint_id=checkpoint_id)
    first_target = store.root / first.stored.storage_key
    source.write_bytes(replacement)

    second = store.ingest_file_resumable(source, checkpoint_id=checkpoint_id)

    assert second.checkpoint_reset is True
    assert second.resumed_from_bytes == 0
    assert first_target.read_bytes() == original
    assert (store.root / second.stored.storage_key).read_bytes() == replacement


def test_checkpoint_id_must_be_uuid(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "store")

    with pytest.raises(ValueError):
        store.checkpoint_path("../outside")
