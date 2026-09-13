from __future__ import annotations

import json
from pathlib import Path

from derlem_worker.canonical import parse_canonical_sample
from derlem_worker.sampling import _document_from_line, score_document_risk

# Go demet yayininin (internal/repository/contributions.go) Python ayristiricisiyla
# ortak sozlesmesi. CI'da backend ve worker ayri islerdir; iki dili bu dosya
# baglar. Dosyayi Go testi uretir ve bayt bayt karsilastirir
# (TestContributionBundleGoldenFixture); bu test ayni dosyayi worker'in gercek
# ayristiricisi ve belge metni cikaricisiyla okur.
FIXTURE = Path(__file__).parents[2] / "data_samples" / "example_contribution_bundles.jsonl"


def _lines() -> list[str]:
    return FIXTURE.read_text(encoding="utf-8").splitlines()


def test_go_bundle_fixture_follows_the_runtime_contract() -> None:
    parsed = [parse_canonical_sample(line, json.loads(line)["content_purpose"]) for line in _lines()]

    assert [sample.record_type for sample in parsed] == ["conversation", "conversation", "preference"]
    assert [sample.sample_id for sample in parsed] == [
        "00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-000000000002",
        "00000000-0000-4000-8000-000000000003",
    ]
    edit_pair = parsed[2].value["preference"]
    assert edit_pair["chosen"][0]["content"] != edit_pair["rejected"][0]["content"]


def test_go_bundle_fixture_reads_as_review_text_without_risk_flags() -> None:
    for line in _lines():
        text, external_id = _document_from_line(line)
        _, reasons = score_document_risk(text, line)

        assert not text.startswith("{")
        assert external_id is not None
        assert "invalid_canonical_sample" not in reasons
        assert "missing_text_field" not in reasons


def test_go_bundle_fixture_carries_origin_and_edit_note_in_metadata() -> None:
    records = [json.loads(line) for line in _lines()]

    assert records[1]["metadata"] == {"data_origin": "hybrid", "model_id": "model-x"}
    assert "domain" not in records[1]
    assert records[2]["metadata"]["edit_note"] == "Fiziksel olarak yanlış olan cevap düzeltildi."
    assert all("created_by" not in record for record in records)
