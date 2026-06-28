import hashlib
from pathlib import Path

from derlem_worker.sampling import sample_line_documents, score_document_risk


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
    assert first.sampling_method == "risk-stratified-sha256-v1"
    assert list(first.samples) == sorted(first.samples, key=lambda item: item.source_ordinal)


def test_sampling_reports_scan_progress(tmp_path: Path) -> None:
    source = tmp_path / "progress.txt"
    source.write_text("\n".join(f"yeterince uzun belge metni {index}" for index in range(20)), encoding="utf-8")
    updates: list[dict[str, int]] = []

    report = sample_line_documents(
        source,
        sample_size=5,
        max_document_bytes=128,
        seed="a" * 64,
        progress_callback=updates.append,
        progress_interval_bytes=32,
    )

    assert report.total_documents == 20
    assert len(updates) > 1
    assert updates[-1]["input_bytes_processed"] == source.stat().st_size
    assert updates[-1]["input_bytes_total"] == source.stat().st_size
    assert updates[-1]["lines_read"] == 20
    assert updates[-1]["documents_scanned"] == 20
    assert updates[-1]["eligible_documents"] == 20


def test_sampling_extracts_jsonl_text_and_external_id(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    source.write_text('{"id":"a-1","text":"Merhaba dünya"}\n', encoding="utf-8")

    report = sample_line_documents(source, sample_size=5, max_document_bytes=128, seed="0" * 64)

    assert report.samples[0].text == "Merhaba dünya"
    assert report.samples[0].external_id == "a-1"
    assert report.samples[0].risk_score > 0


def test_sampling_skips_oversized_lines_without_unbounded_read(tmp_path: Path) -> None:
    source = tmp_path / "mixed.txt"
    source.write_text("kısa\n" + ("x" * 1000) + "\nson\n", encoding="utf-8")

    report = sample_line_documents(source, sample_size=10, max_document_bytes=64, seed="1" * 64)

    assert report.total_documents == 3
    assert report.skipped_oversized == 1
    assert [sample.text for sample in report.samples] == ["kısa", "son"]


def test_risk_stratified_sampling_includes_high_risk_documents(tmp_path: Path) -> None:
    source = tmp_path / "risk.txt"
    ordinary = [
        f"Bu belge örneklem dağılımını koruyan sıradan ve yeterince uzun bir metindir {index}."
        for index in range(100)
    ]
    risky = "TEKRAR" * 2 + "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    source.write_text("\n".join([*ordinary, risky]), encoding="utf-8")

    report = sample_line_documents(
        source,
        sample_size=10,
        max_document_bytes=1024,
        seed="2" * 64,
    )

    assert any(sample.text == risky for sample in report.samples)
    selected = next(sample for sample in report.samples if sample.text == risky)
    assert selected.risk_score >= 2
    assert "high_symbol_ratio" in selected.risk_reasons
    assert report.selected_risk_documents >= 1


def test_document_risk_reasons_are_explainable_and_bounded() -> None:
    score, reasons = score_document_risk("test@example.com\u0001AAAAAAAAAAAA")

    assert score == 8
    assert reasons == (
        "control_characters",
        "repeated_character_run",
        "identifier_pattern",
    )

    score, reasons = score_document_risk('{"unexpected":"value"}', '{"unexpected":"value"}')
    assert score == 3
    assert reasons == ("short_text", "missing_text_field")
