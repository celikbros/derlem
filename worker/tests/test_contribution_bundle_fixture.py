from __future__ import annotations

import json
from pathlib import Path

from derlem_worker.canonical import parse_canonical_sample
from derlem_worker.releases import build_release_export
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


def _export(tmp_path: Path, purpose: str, lines: list[str]) -> tuple[list[dict], object]:
    source_path = tmp_path / f"{purpose}-bundle.jsonl"
    source_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output_path = tmp_path / f"{purpose}-export.jsonl"
    release = {
        "id": "release-id",
        "name": "Katki",
        "version": "v1",
        "content_purpose": purpose,
        "frozen_at": "2026-09-13T00:00:00Z",
        "manifest_sha256": "f" * 64,
    }
    sources = [
        {
            "source_id": "bundle",
            "source_sha256": "1" * 64,
            "path": source_path,
            "language": "tr",
            "domain": "fizik",
            "license": "internal",
        }
    ]
    result = build_release_export(release, sources, "jsonl", output_path, max_document_bytes=4096)
    exported = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    return exported, result


# Ihracat kapisi kanonik kaydi ilk ihracatta dogrular; tek gecersiz kayit tum
# release'i bloke eder. Go demetinin urettigi kayitlar bu kapidan gecmeli
# (TASK-002 kabul kriteri: preference / jsonl).
def test_go_bundle_edit_pair_passes_the_preference_export_gate(tmp_path: Path) -> None:
    edit_pair_lines = [line for line in _lines() if json.loads(line)["content_purpose"] == "preference"]
    assert len(edit_pair_lines) == 1

    exported, result = _export(tmp_path, "preference", edit_pair_lines)

    assert result.record_type_counts == {"preference": 1}
    sample = exported[0]["sample"]
    assert sample["task_type"] == "response_edit_pair"
    assert sample["preference"]["chosen"][0]["content"] == "Hayır; ses yayılmak için bir ortam ister."
    assert sample["preference"]["rejected"][0]["content"] == "Evet, ses her yerde yayılır."
    assert sample["metadata"]["edit_note"] == "Fiziksel olarak yanlış olan cevap düzeltildi."


def test_go_bundle_qa_pairs_pass_the_instruction_export_gate(tmp_path: Path) -> None:
    qa_lines = [line for line in _lines() if json.loads(line)["content_purpose"] == "instruction"]
    assert len(qa_lines) == 2

    exported, result = _export(tmp_path, "instruction", qa_lines)

    assert result.record_type_counts == {"conversation": 2}
    assert exported[1]["sample"]["metadata"] == {"data_origin": "hybrid", "model_id": "model-x"}
