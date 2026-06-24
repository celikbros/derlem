import hashlib
from pathlib import Path

from derlem_worker.sampling import sample_line_documents


def test_sampling_is_deterministic_and_bounded(tmp_path: Path) -> None:
    source = tmp_path / "corpus.txt"
    source.write_text("\n".join(f"belge {index}" for index in range(100)), encoding="utf-8")
    seed = hashlib.sha256(source.read_bytes()).hexdigest()

    first = sample_line_documents(source, sample_size=10, max_document_bytes=128, seed=seed)
    second = sample_line_documents(source, sample_size=10, max_document_bytes=128, seed=seed)

    assert first == second
    assert first.total_documents == 100
    assert first.eligible_documents == 100
    assert len(first.samples) == 10
    assert list(first.samples) == sorted(first.samples, key=lambda item: item.source_ordinal)


def test_sampling_extracts_jsonl_text_and_external_id(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    source.write_text('{"id":"a-1","text":"Merhaba dünya"}\n', encoding="utf-8")

    report = sample_line_documents(source, sample_size=5, max_document_bytes=128, seed="0" * 64)

    assert report.samples[0].text == "Merhaba dünya"
    assert report.samples[0].external_id == "a-1"


def test_sampling_skips_oversized_lines_without_unbounded_read(tmp_path: Path) -> None:
    source = tmp_path / "mixed.txt"
    source.write_text("kısa\n" + ("x" * 1000) + "\nson\n", encoding="utf-8")

    report = sample_line_documents(source, sample_size=10, max_document_bytes=64, seed="1" * 64)

    assert report.total_documents == 3
    assert report.skipped_oversized == 1
    assert [sample.text for sample in report.samples] == ["kısa", "son"]
