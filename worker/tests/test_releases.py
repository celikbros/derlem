from __future__ import annotations

import json
from pathlib import Path

import pytest

from derlem_worker.releases import (
    ReleaseGateError,
    build_export_manifest,
    build_mixture_report,
    build_release_export,
    build_release_manifest,
    exact_decontamination,
)


def test_exact_decontamination_blocks_matching_document(tmp_path: Path) -> None:
    reference = tmp_path / "eval.jsonl"
    release = tmp_path / "pretrain.jsonl"
    reference.write_text('{"text":"ortak belge"}\n{"text":"yalnız eval"}\n', encoding="utf-8")
    release.write_text('{"text":"özgün belge"}\n{"text":"ortak belge"}\n', encoding="utf-8")

    result = exact_decontamination(
        [("e" * 64, reference)],
        [("p" * 64, release)],
        max_document_bytes=1024,
    )

    assert result.status == "blocked"
    assert result.match_count == 1
    assert result.release_document_count == 2
    assert result.sample_matches[0].source_ordinal == 2


def test_exact_decontamination_reports_not_evaluated_without_references(tmp_path: Path) -> None:
    """Referans kumesi bosken 'passed' yazilmamali.

    Frozen manifest degismez; hak edilmemis bir "dekontaminasyon gecti" muhru
    geri alinamaz. Bos referans durust bir etiket almali.
    """
    release = tmp_path / "pretrain.txt"
    release.write_text("egitim belgesi\n", encoding="utf-8")

    result = exact_decontamination([], [("p" * 64, release)], max_document_bytes=1024)

    assert result.status == "not_evaluated"
    assert result.reference_source_count == 0
    assert result.match_count == 0
    # Release tarafi yine sayilmis olmali; dokum kaybolmasin.
    assert result.release_document_count == 1


def test_exact_decontamination_passes_without_overlap(tmp_path: Path) -> None:
    reference = tmp_path / "holdout.txt"
    release = tmp_path / "pretrain.txt"
    reference.write_text("saklı değerlendirme\n", encoding="utf-8")
    release.write_text("eğitim belgesi\n", encoding="utf-8")

    result = exact_decontamination(
        [("e" * 64, reference)],
        [("p" * 64, release)],
        max_document_bytes=1024,
    )

    assert result.status == "passed"
    assert result.match_count == 0


def test_decontamination_blocks_oversized_document(tmp_path: Path) -> None:
    release = tmp_path / "pretrain.txt"
    release.write_text("x" * 100, encoding="utf-8")

    with pytest.raises(ReleaseGateError) as captured:
        exact_decontamination([], [("p" * 64, release)], max_document_bytes=20)

    assert captured.value.gate_results["decontamination"]["reason"] == "document_too_large"


def test_release_manifest_is_deterministic_and_sorted() -> None:
    release = {"id": "release-id", "name": "Derlem", "version": "v1", "content_purpose": "instruction"}
    sources = [
        {"source_id": "b", "source_sha256": "2" * 64},
        {"source_id": "a", "source_sha256": "1" * 64},
    ]
    gates = {"source_gate": {"status": "passed"}}

    first = build_release_manifest(release, sources, gates, "2026-06-24T20:00:00Z")
    second = build_release_manifest(release, list(reversed(sources)), gates, "2026-06-24T20:00:00Z")

    assert first == second
    decoded = json.loads(first)
    assert [source["source_id"] for source in decoded["sources"]] == ["a", "b"]


def test_mixture_report_is_deterministic_weighted_and_sorted() -> None:
    sources = [
        {
            "source_id": "b",
            "language": "en",
            "domain": "code",
            "source_type": "canonical_jsonl",
            "license": "internal",
            "rights_status": "cleared",
            "byte_size": 300,
            "line_count": 30,
        },
        {
            "source_id": "a",
            "language": "tr",
            "domain": "general",
            "source_type": "web_corpus",
            "license": "cc-by-4.0",
            "rights_status": "cleared",
            "byte_size": 700,
            "line_count": 70,
        },
    ]

    first = build_mixture_report(sources)
    second = build_mixture_report(list(reversed(sources)))

    assert first == second
    assert first["schema_version"] == "derlem.mixture-report.v2"
    assert first["totals"] == {
        "source_count": 2,
        "byte_size": 1000,
        "line_count": 100,
        "missing_byte_size_count": 0,
        "missing_line_count": 0,
    }
    languages = first["dimensions"]["language"]
    assert [entry["value"] for entry in languages] == ["en", "tr"]
    assert languages[0]["source_share_bps"] == 5000
    assert languages[0]["byte_share_bps"] == 3000
    assert languages[1]["line_share_bps"] == 7000
    assert first["quality"]["coverage_status"] == "unavailable"
    assert first["quality"]["sample_document_count"] == 0


def test_mixture_report_tracks_missing_metrics_and_unknown_values() -> None:
    report = build_mixture_report(
        [
            {
                "source_id": "a",
                "language": "",
                "domain": None,
                "source_type": "other",
                "license": "unknown",
                "rights_status": "unknown",
                "byte_size": None,
                "line_count": None,
            }
        ]
    )

    assert report["totals"]["missing_byte_size_count"] == 1
    assert report["totals"]["missing_line_count"] == 1
    assert report["dimensions"]["language"][0]["value"] == "unknown"
    assert report["dimensions"]["domain"][0]["value"] == "unknown"
    assert report["dimensions"]["language"][0]["byte_share_bps"] == 0


def test_mixture_quality_bands_are_document_based_and_deterministic() -> None:
    sources = [{"source_id": "source-a", "byte_size": 100, "line_count": 6}]
    reviews = [
        _quality_review("doc-1", "review-1", "multidimensional-v1", 1, 1, 1, 1, 1),
        _quality_review("doc-2", "review-2", "multidimensional-v1", 2, 3, 4, 5, 2),
        _quality_review("doc-3", "review-3", "multidimensional-v1", 3, 4, 5, 1, 3),
        _quality_review("doc-4", "review-4", "multidimensional-v1", 5, 5, 4, 2, 5),
        _quality_review("doc-5", "review-5", "overall-v1", 4, None, None, None, None),
        _quality_review("doc-6", None, None, None, None, None, None, None),
    ]

    first = build_mixture_report(sources, reviews)
    second = build_mixture_report(sources, list(reversed(reviews)))

    assert first == second
    quality = first["quality"]
    assert quality["schema_version"] == "derlem.quality-mixture.v2"
    assert quality["basis"] == "active-current-sample-document-review-v1"
    assert quality["coverage_status"] == "partial"
    assert quality["sample_document_count"] == 6
    assert quality["scored_document_count"] == 4
    assert quality["coverage_bps"] == 6667
    assert quality["legacy_document_count"] == 1
    assert quality["missing_review_document_count"] == 1
    assert quality["review_snapshot_method"] == "ordered-sample-review-json-sha256-v2"
    assert len(quality["review_snapshot_sha256"]) == 64

    overall = quality["dimensions"]["overall"]
    assert overall["score_sum"] == 11
    assert overall["average_score_milli"] == 2750
    assert [(band["band"], band["document_count"], band["document_share_bps"]) for band in overall["bands"]] == [
        ("low", 2, 5000),
        ("medium", 1, 2500),
        ("high", 1, 2500),
    ]
    assert quality["dimensions"]["language"]["average_score_milli"] == 3250

    changed_generation = [dict(review) for review in reviews]
    changed_generation[0]["sample_generation"] = 2
    changed = build_mixture_report(sources, changed_generation)
    assert changed["quality"]["review_snapshot_sha256"] != quality["review_snapshot_sha256"]


def test_mixture_quality_rejects_duplicate_documents_and_invalid_scores() -> None:
    source = [{"source_id": "source-a", "byte_size": 1, "line_count": 1}]
    review = _quality_review("doc-1", "review-1", "multidimensional-v1", 4, 4, 4, 4, 4)

    with pytest.raises(ValueError, match="duplicate document_id"):
        build_mixture_report(source, [review, review])

    invalid = _quality_review("doc-2", "review-2", "multidimensional-v1", 6, 4, 4, 4, 4)
    with pytest.raises(ValueError, match="quality_score must be between 1 and 5"):
        build_mixture_report(source, [invalid])

    rejected = _quality_review("doc-3", "review-3", "multidimensional-v1", 4, 4, 4, 4, 4)
    rejected["decision"] = "rejected"
    with pytest.raises(ValueError, match="must be approved"):
        build_mixture_report(source, [rejected])


def test_jsonl_export_is_deterministic_model_independent_and_sorted(tmp_path: Path) -> None:
    first_source = tmp_path / "first.jsonl"
    second_source = tmp_path / "second.txt"
    first_source.write_text('{"id":"doc-1","text":"Merhaba dünya"}\n', encoding="utf-8")
    second_source.write_text("İkinci belge\n", encoding="utf-8")
    release = {
        "id": "release-id",
        "name": "Derlem",
        "version": "v1",
        "content_purpose": "pretrain",
        "frozen_at": "2026-06-27T00:00:00Z",
        "manifest_sha256": "f" * 64,
    }
    sources = [
        {
            "source_id": "b",
            "source_sha256": "2" * 64,
            "path": second_source,
            "language": "tr",
            "domain": "general",
            "license": "internal",
        },
        {
            "source_id": "a",
            "source_sha256": "1" * 64,
            "path": first_source,
            "language": "tr",
            "domain": "general",
            "license": "internal",
        },
    ]
    first_output = tmp_path / "first-export.jsonl"
    second_output = tmp_path / "second-export.jsonl"

    first = build_release_export(
        release,
        sources,
        "jsonl",
        first_output,
        max_document_bytes=1024,
    )
    second = build_release_export(
        release,
        list(reversed(sources)),
        "jsonl",
        second_output,
        max_document_bytes=1024,
    )

    assert first == second
    assert first_output.read_bytes() == second_output.read_bytes()
    records = [json.loads(line) for line in first_output.read_text(encoding="utf-8").splitlines()]
    assert [record["text"] for record in records] == ["Merhaba dünya", "İkinci belge"]
    assert records[0]["metadata"]["external_id"] == "doc-1"
    assert "model" not in records[0]["metadata"]

    manifest = json.loads(build_export_manifest(release, sources, first))
    assert manifest["schema_version"] == "derlem.export-manifest.v2"
    assert manifest["export"]["sha256"] == first.sha256
    assert manifest["export"]["record_count"] == 2
    assert manifest["export"]["record_type_counts"] == {"text": 2}
    assert manifest["export"]["token_estimate"]["method"] == "unicode-codepoint-range-v1"
    assert manifest["export"]["token_estimate"]["lower_bound"] > 0
    assert (
        manifest["export"]["token_estimate"]["lower_bound"]
        <= manifest["export"]["token_estimate"]["estimated_token_count"]
        <= manifest["export"]["token_estimate"]["upper_bound"]
    )
    assert [source["source_id"] for source in manifest["sources"]] == ["a", "b"]


def test_txt_export_flattens_embedded_newlines(tmp_path: Path) -> None:
    source_path = tmp_path / "source.jsonl"
    source_path.write_text('{"text":"birinci\\nikinci"}\n', encoding="utf-8")
    output_path = tmp_path / "export.txt"
    release = {"content_purpose": "instruction"}
    sources = [
        {
            "source_id": "a",
            "source_sha256": "1" * 64,
            "path": source_path,
            "language": "tr",
            "domain": "general",
            "license": "internal",
        }
    ]

    result = build_release_export(
        release,
        sources,
        "txt",
        output_path,
        max_document_bytes=1024,
    )

    assert output_path.read_text(encoding="utf-8") == "birinci ikinci\n"
    assert result.record_count == 1


def test_structured_conversation_export_preserves_canonical_fields(tmp_path: Path) -> None:
    source_path = tmp_path / "conversation.jsonl"
    sample = {
        "schema_version": "derlem.canonical-sample.v1",
        "record_type": "conversation",
        "sample_id": "conv-1",
        "content_purpose": "instruction",
        "train_policy": "assistant_only",
        "messages": [
            {"role": "user", "content": "İki ile ikiyi topla."},
            {"role": "assistant", "content": "Dört."},
        ],
        "metadata": {"difficulty": "easy"},
    }
    source_path.write_text(json.dumps(sample, ensure_ascii=False) + "\n", encoding="utf-8")
    output_path = tmp_path / "conversation-export.jsonl"
    release = {
        "id": "release-id",
        "name": "Instruction",
        "version": "v1",
        "content_purpose": "instruction",
        "frozen_at": "2026-06-29T00:00:00Z",
        "manifest_sha256": "f" * 64,
    }
    sources = [
        {
            "source_id": "a",
            "source_sha256": "1" * 64,
            "path": source_path,
            "language": "tr",
            "domain": "math",
            "license": "internal",
        }
    ]

    result = build_release_export(
        release,
        sources,
        "jsonl",
        output_path,
        max_document_bytes=4096,
    )

    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert exported["export_schema_version"] == "derlem.canonical-export-record.v1"
    assert exported["record_type"] == "conversation"
    assert exported["sample"]["schema_version"] == "derlem.canonical-sample.v1"
    assert exported["sample"]["sample_id"] == "conv-1"
    assert exported["sample"]["messages"] == sample["messages"]
    assert exported["sample"]["metadata"] == {"difficulty": "easy"}
    assert exported["lineage"]["source_id"] == "a"
    assert len(exported["lineage"]["canonical_payload_sha256"]) == 64
    assert result.record_type_counts == {"conversation": 1}
    assert result.token_estimate.estimated_token_count > 0


def test_structured_records_are_rejected_from_txt_export(tmp_path: Path) -> None:
    source_path = tmp_path / "conversation.jsonl"
    source_path.write_text(
        json.dumps(
            {
                "schema_version": "derlem.canonical-sample.v1",
                "record_type": "conversation",
                "sample_id": "conv-1",
                "content_purpose": "instruction",
                "messages": [{"role": "user", "content": "Merhaba"}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    sources = [
        {
            "source_id": "a",
            "source_sha256": "1" * 64,
            "path": source_path,
            "language": "tr",
            "domain": "general",
            "license": "internal",
        }
    ]

    with pytest.raises(ReleaseGateError) as captured:
        build_release_export(
            {"content_purpose": "instruction"},
            sources,
            "txt",
            tmp_path / "invalid.txt",
            max_document_bytes=4096,
        )

    assert captured.value.gate_results["export"]["reason"] == "structured_record_requires_jsonl"


def test_canonical_purpose_mismatch_blocks_export(tmp_path: Path) -> None:
    source_path = tmp_path / "mismatch.jsonl"
    source_path.write_text(
        json.dumps(
            {
                "schema_version": "derlem.canonical-sample.v1",
                "record_type": "conversation",
                "sample_id": "eval-1",
                "content_purpose": "eval",
                "messages": [{"role": "user", "content": "Soru"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sources = [
        {
            "source_id": "a",
            "source_sha256": "1" * 64,
            "path": source_path,
            "language": "tr",
            "domain": "general",
            "license": "internal",
        }
    ]

    with pytest.raises(ReleaseGateError) as captured:
        build_release_export(
            {"content_purpose": "instruction"},
            sources,
            "jsonl",
            tmp_path / "invalid.jsonl",
            max_document_bytes=4096,
        )

    assert captured.value.gate_results["export"]["reason"] == "invalid_canonical_sample"
    assert captured.value.gate_results["export"]["validation_error"] == "content_purpose_mismatch"


def _quality_review(
    document_id: str,
    review_id: str | None,
    rubric_version: str | None,
    quality_score: int | None,
    language_quality_score: int | None,
    coherence_score: int | None,
    information_density_score: int | None,
    cleanliness_score: int | None,
) -> dict[str, object]:
    return {
        "source_id": "source-a",
        "document_id": document_id,
        "document_version": 1,
        "sample_generation": 1,
        "object_sha256": "a" * 64,
        "review_id": review_id,
        "decision": "approved" if review_id else None,
        "rubric_version": rubric_version,
        "quality_score": quality_score,
        "language_quality_score": language_quality_score,
        "coherence_score": coherence_score,
        "information_density_score": information_density_score,
        "cleanliness_score": cleanliness_score,
    }
