import errno
import hashlib
import os
from pathlib import Path
import stat
from threading import Event, Thread
from uuid import uuid4

import pytest

from derlem_worker import storage
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


def test_attempt_scoped_checkpoint_ids_are_isolated(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "store")
    job_id = uuid4()

    first = store.checkpoint_path(f"{job_id}-attempt-1")
    second = store.checkpoint_path(f"{job_id}-attempt-2")

    assert first != second
    assert first.name.endswith("-attempt-1.part")
    assert second.name.endswith("-attempt-2.part")


def test_closed_checkpoint_can_be_promoted_to_next_attempt(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "store")
    job_id = uuid4()
    first_id = f"{job_id}-attempt-1"
    second_id = f"{job_id}-attempt-2"
    first = store.checkpoint_path(first_id)
    first.write_bytes(b"verified prefix")
    original_mode = stat.S_IMODE(first.stat().st_mode)

    assert store.promote_checkpoint(first_id, second_id) is True
    assert not first.exists()
    promoted = store.checkpoint_path(second_id)
    assert promoted.read_bytes() == b"verified prefix"
    assert stat.S_IMODE(promoted.stat().st_mode) == original_mode


def test_checkpoint_promotion_never_replaces_active_next_attempt(
    tmp_path: Path,
) -> None:
    store = ContentAddressedStore(tmp_path / "store")
    job_id = uuid4()
    first_id = f"{job_id}-attempt-1"
    second_id = f"{job_id}-attempt-2"
    first = store.checkpoint_path(first_id)
    second = store.checkpoint_path(second_id)
    first.write_bytes(b"closed old attempt")
    second.write_bytes(b"active next attempt")

    with pytest.raises(FileExistsError):
        store.promote_checkpoint(first_id, second_id)

    assert first.read_bytes() == b"closed old attempt"
    assert second.read_bytes() == b"active next attempt"


def test_checkpoint_id_must_be_uuid_or_attempt_key(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "store")

    with pytest.raises(ValueError):
        store.checkpoint_path("../outside")


def test_cas_fallback_publishes_via_complete_verified_sibling(
    tmp_path: Path, monkeypatch
) -> None:
    store = ContentAddressedStore(tmp_path / "store")
    content = b"complete object bytes"
    digest = hashlib.sha256(content).hexdigest()
    source = tmp_path / "source.part"
    source.write_bytes(content)
    target = store.object_root / digest[:2] / digest[2:4] / digest
    target.parent.mkdir(parents=True)
    real_link = os.link

    def cross_device_once(source_path, target_path, *args, **kwargs):
        if Path(source_path) == source:
            raise OSError(errno.EXDEV, "simulated cross-device link")
        return real_link(source_path, target_path, *args, **kwargs)

    monkeypatch.setattr(storage.os, "link", cross_device_once)

    store._publish_create_only(
        source,
        target,
        expected_sha256=digest,
        expected_size=len(content),
        remove_source=False,
    )

    assert target.read_bytes() == content
    assert not list(target.parent.glob(f".{digest}.publish-*"))


def test_cas_publish_never_creates_target_when_source_disappeared(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "store")
    content = b"expected"
    digest = hashlib.sha256(content).hexdigest()
    missing = tmp_path / "missing.part"
    target = store.object_root / digest[:2] / digest[2:4] / digest
    target.parent.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        store._publish_create_only(
            missing,
            target,
            expected_sha256=digest,
            expected_size=len(content),
        )

    assert not target.exists()


def test_readonly_source_uses_complete_sibling_publication(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "store")
    content = b"readonly complete source"
    digest = hashlib.sha256(content).hexdigest()
    source = tmp_path / "readonly.part"
    source.write_bytes(content)
    source.chmod(stat.S_IREAD)
    target = store.object_root / digest[:2] / digest[2:4] / digest
    target.parent.mkdir(parents=True)

    try:
        store._publish_create_only(
            source,
            target,
            expected_sha256=digest,
            expected_size=len(content),
            remove_source=False,
        )
        assert target.read_bytes() == content
        assert source.read_bytes() == content
    finally:
        source.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_cas_publish_rejects_corrupt_existing_target(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "store")
    content = b"expected"
    digest = hashlib.sha256(content).hexdigest()
    source = tmp_path / "source.part"
    source.write_bytes(content)
    target = store.object_root / digest[:2] / digest[2:4] / digest
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")

    with pytest.raises(RuntimeError, match="size mismatch"):
        store._publish_create_only(
            source,
            target,
            expected_sha256=digest,
            expected_size=len(content),
            remove_source=False,
        )


def test_concurrent_loser_cannot_break_winner_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ContentAddressedStore(tmp_path / "store")
    content = b"same complete object"
    digest = hashlib.sha256(content).hexdigest()
    winner_source = tmp_path / "winner.part"
    loser_source = tmp_path / "loser.part"
    winner_source.write_bytes(content)
    loser_source.write_bytes(content)
    target = store.object_root / digest[:2] / digest[2:4] / digest
    target.parent.mkdir(parents=True)
    winner_linked = Event()
    loser_finished = Event()
    errors: list[BaseException] = []
    original_seal = ContentAddressedStore._seal_and_sync_published_object

    def delayed_seal(
        target_path: Path,
        *,
        published_descriptor: int,
    ) -> None:
        winner_linked.set()
        if not loser_finished.wait(10):
            raise RuntimeError("loser publisher did not finish")
        original_seal(
            target_path,
            published_descriptor=published_descriptor,
        )

    monkeypatch.setattr(
        ContentAddressedStore,
        "_seal_and_sync_published_object",
        staticmethod(delayed_seal),
    )

    def publish_winner() -> None:
        try:
            store._publish_create_only(
                winner_source,
                target,
                expected_sha256=digest,
                expected_size=len(content),
            )
        except BaseException as error:  # surfaced on the main test thread
            errors.append(error)

    winner = Thread(target=publish_winner)
    winner.start()
    try:
        assert winner_linked.wait(10), "winner did not publish its create-only link"
        store._publish_create_only(
            loser_source,
            target,
            expected_sha256=digest,
            expected_size=len(content),
        )
    finally:
        loser_finished.set()
        winner.join(10)

    assert not winner.is_alive()
    assert errors == []
    assert target.read_bytes() == content
    assert not winner_source.exists()
    assert not loser_source.exists()
