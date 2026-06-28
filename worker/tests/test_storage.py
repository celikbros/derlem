from pathlib import Path

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
