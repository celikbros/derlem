from pathlib import Path

from derlem_worker.fingerprints import (
    FINGERPRINT_VERSION,
    document_fingerprint,
    iter_document_fingerprints,
)


def test_document_fingerprint_normalizes_case_and_whitespace() -> None:
    first = document_fingerprint("  Bu   BELGE    ayni metindir ve yeterince uzundur. ")
    second = document_fingerprint("bu belge ayni metindir ve yeterince uzundur.")

    assert first is not None
    assert first == second


def test_short_documents_are_not_indexed() -> None:
    assert document_fingerprint("kisa") is None


def test_iter_document_fingerprints_extracts_jsonl_text(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text(
        '{"id":"1","text":"Bu belge normalize fingerprint icin yeterince uzundur."}\n'
        '{"id":"2","text":"kisa"}\n',
        encoding="utf-8",
    )

    report, fingerprints = iter_document_fingerprints(source, max_document_bytes=1024)

    assert report.fingerprint_version == FINGERPRINT_VERSION
    assert report.total_documents == 2
    assert report.indexed_documents == 1
    assert report.skipped_too_short == 1
    assert len(fingerprints) == 1
    assert fingerprints[0].source_ordinal == 1
