from __future__ import annotations

import json
from pathlib import Path

from derlem_worker.fingerprints import iter_document_fingerprints
from derlem_worker.sampling import _document_from_line, sample_line_documents, score_document_risk

# Worker kanonik kaydi okuyabilmeli (TASK-002 S1). Okuyamazsa ornekleme ham JSON'u
# belge diye incelemeye koyar, her kayit missing_text_field alir ve sample_id her
# satirda farkli oldugu icin ayni icerikli iki katki tekrar olarak yakalanmaz.


def _conversation(sample_id: str, question: str, answer: str) -> dict:
    return {
        "schema_version": "derlem.canonical-sample.v1",
        "record_type": "conversation",
        "sample_id": sample_id,
        "content_purpose": "instruction",
        "messages": [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
    }


def _edit_pair(sample_id: str) -> dict:
    # response_edit_pair'in kanonik bicimi: soru baglam, duzeltilmis cevap chosen,
    # orijinal cevap rejected (TASK-002).
    return {
        "schema_version": "derlem.canonical-sample.v1",
        "record_type": "preference",
        "sample_id": sample_id,
        "content_purpose": "preference",
        "messages": [{"role": "user", "content": "Işık hızı nedir?"}],
        "preference": {
            "chosen": [{"role": "assistant", "content": "Boşlukta yaklaşık 299.792 km/s'dir."}],
            "rejected": [{"role": "assistant", "content": "Saniyede 300 km'dir."}],
        },
    }


def _line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False)


def test_canonical_record_yields_semantic_text_and_sample_id() -> None:
    text, external_id = _document_from_line(
        _line(_conversation("katki-1", "Soru metni burada?", "Cevap metni burada."))
    )

    assert text == "Soru metni burada?\nCevap metni burada."
    assert external_id == "katki-1"


def test_canonical_edit_pair_text_contains_prompt_and_both_answers() -> None:
    text, external_id = _document_from_line(_line(_edit_pair("duzeltme-1")))

    assert external_id == "duzeltme-1"
    for fragment in ("Işık hızı nedir?", "299.792 km/s", "Saniyede 300 km"):
        assert fragment in text
    assert "schema_version" not in text


def test_invalid_canonical_record_is_returned_raw_not_repaired() -> None:
    record = _conversation("bozuk-1", "Soru?", "Cevap.")
    record["unexpected_field"] = "x"
    line = _line(record)

    assert _document_from_line(line) == (line, None)


def test_plain_json_text_record_is_unchanged() -> None:
    assert _document_from_line('{"id": "d1", "text": "  düz metin  "}') == ("düz metin", "d1")


def test_valid_canonical_record_is_not_flagged_as_missing_text_field() -> None:
    line = _line(
        _conversation("katki-2", "Yeterince uzun bir soru metni?", "Yeterince uzun bir cevap metni.")
    )
    text, _ = _document_from_line(line)

    _, reasons = score_document_risk(text, line)

    assert "missing_text_field" not in reasons
    assert "invalid_canonical_sample" not in reasons


def test_invalid_canonical_record_is_flagged_for_review() -> None:
    # Ihracat gecersiz tek kayitta tum release'i bloke eder; incelemede one cikmali.
    record = _conversation("bozuk-2", "Soru?", "Cevap.")
    record["content_purpose"] = "not-a-purpose"
    line = _line(record)

    score, reasons = score_document_risk(line, line)

    assert "invalid_canonical_sample" in reasons
    assert score >= 5


def test_exact_dedup_catches_identical_canonical_records_with_different_sample_ids(tmp_path: Path) -> None:
    source = tmp_path / "canonical.jsonl"
    question = "Derlem aynı içerikli iki katkıyı tekrar olarak yakalamalı mı?"
    answer = "Evet; kimlikleri farklı olsa da anlamsal metinleri aynıdır."
    source.write_text(
        _line(_conversation("katki-a", question, answer))
        + "\n"
        + _line(_conversation("katki-b", question, answer))
        + "\n",
        encoding="utf-8",
    )

    report, fingerprints = iter_document_fingerprints(source, max_document_bytes=4096)

    assert report.indexed_documents == 2
    assert fingerprints[0].normalized_sha256 == fingerprints[1].normalized_sha256


def test_sampling_reviews_semantic_text_not_raw_json(tmp_path: Path) -> None:
    source = tmp_path / "canonical-sample.jsonl"
    lines = [
        _line(
            _conversation(
                f"katki-{index}",
                f"Soru numarası {index} için yeterince uzun bir metin?",
                f"Cevap numarası {index} için yeterince uzun bir metin.",
            )
        )
        for index in range(5)
    ]
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = sample_line_documents(source, sample_size=5, max_document_bytes=4096, seed="b" * 64)

    assert len(report.samples) == 5
    for sample in report.samples:
        assert not sample.text.startswith("{")
        assert sample.external_id is not None and sample.external_id.startswith("katki-")
    assert "missing_text_field" not in report.risk_reason_counts
