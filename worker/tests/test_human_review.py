"""TASK-048: pretrain inceleme esigi, atilacak liste, manifest ve ihracat.

Esik 10 kurucunun ONERISIdir; kodda varsayilan yoktur, deger yalniz testte ve
dokumanda gecer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from derlem_worker.document_record import read_decisions
from derlem_worker.human_review import (
    build_human_review_drop_list,
    doc_id_list_sha256,
    load_excluded_doc_ids,
    review_gate_passes,
    summarize_release_human_review,
    threshold_basis_points,
    write_human_review_decisions,
)
from derlem_worker.jobs.release_jobs import ReleaseJobsMixin, _mixture_quality_rows
from derlem_worker.releases import (
    ReleaseGateError,
    build_export_manifest,
    build_release_export,
    build_release_manifest,
    validate_release_contract_evidence,
)

PROPOSED_THRESHOLD = Decimal("10.00")
RELEASE_ID = "11111111-2222-3333-4444-555555555555"
DECIDED_AT = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
REVIEWER_A = "aaaaaaaa-0000-0000-0000-000000000001"
REVIEWER_B = "bbbbbbbb-0000-0000-0000-000000000002"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Kapi formulu (Go ve DB ile ayni tablo)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("purpose", "threshold", "approved", "flagged", "expected"),
    [
        ("pretrain", PROPOSED_THRESHOLD, 180, 20, True),
        ("pretrain", PROPOSED_THRESHOLD, 179, 21, False),
        ("pretrain", PROPOSED_THRESHOLD, 200, 0, True),
        ("pretrain", Decimal("10.50"), 179, 21, True),
        ("pretrain", Decimal("10.49"), 179, 21, False),
        ("pretrain", Decimal("0"), 199, 1, False),
        ("pretrain", None, 180, 20, False),
        ("pretrain", None, 200, 0, True),
        ("instruction", PROPOSED_THRESHOLD, 199, 1, False),
        ("contribution", PROPOSED_THRESHOLD, 199, 1, False),
        ("eval", PROPOSED_THRESHOLD, 199, 1, False),
        ("holdout", PROPOSED_THRESHOLD, 199, 1, False),
        ("instruction", None, 200, 0, True),
    ],
)
def test_review_gate_matches_the_go_and_sql_formula(purpose, threshold, approved, flagged, expected) -> None:
    assert review_gate_passes(purpose, threshold, 200, approved + flagged, approved, flagged) is expected


def test_review_gate_keeps_unreviewed_samples_closed() -> None:
    assert not review_gate_passes("pretrain", PROPOSED_THRESHOLD, 200, 199, 180, 19)
    assert not review_gate_passes("pretrain", PROPOSED_THRESHOLD, 0, 0, 0, 0)


def test_threshold_basis_points_is_exact_and_bounded() -> None:
    assert threshold_basis_points(Decimal("10.00")) == 1000
    assert threshold_basis_points(10.5) == 1050
    assert threshold_basis_points(None) is None
    for invalid in (Decimal("10.005"), Decimal("-0.01"), Decimal("100.01")):
        with pytest.raises(ValueError):
            threshold_basis_points(invalid)


# --------------------------------------------------------------------------
# Atilacak liste
# --------------------------------------------------------------------------

# Ornek: 1-10. sira numaralari. 2 ve 5 reddedildi, 7 hassas (isaret).
# 2. satirin metni 12. satirda tekrar geciyor: ikisi de duser.
SOURCE_LINES = [
    "belge bir",
    "reddedilen iki",
    "belge uc",
    "belge dort",
    "reddedilen bes",
    "belge alti",
    "hassas yedi",
    "belge sekiz",
    "belge dokuz",
    "belge on",
    "belge on bir",
    "reddedilen iki",
    '{"id": "x-13", "text": "jsonl belge on uc"}',
]
DROPPED = {2: "rejected", 5: "rejected", 7: "sensitive_review"}


def _write_source(tmp_path: Path) -> Path:
    path = tmp_path / "source.txt"
    path.write_text("".join(f"{line}\n" for line in SOURCE_LINES), encoding="utf-8")
    return path


def _review_rows(dropped: dict[int, str] = DROPPED) -> list[dict[str, object]]:
    return [
        {
            "source_id": "source-a",
            "document_id": f"doc-{ordinal:02d}",
            "source_ordinal": ordinal,
            "decision": dropped.get(ordinal, "approved"),
            "reviewer_id": REVIEWER_A if ordinal % 2 else REVIEWER_B,
        }
        for ordinal in range(1, 11)
    ]


def _drop_list(tmp_path: Path, *, threshold=Decimal("30.00"), flagged=3, rows=None):
    return build_human_review_drop_list(
        source_id="source-a",
        source_path=_write_source(tmp_path),
        review_rows=rows if rows is not None else _review_rows(),
        content_purpose="pretrain",
        threshold=threshold,
        sampled_document_count=10,
        flagged_document_count=flagged,
        max_document_bytes=1_000_000,
    )


def test_drop_list_excludes_every_occurrence_of_rejected_text(tmp_path: Path) -> None:
    drop_list = _drop_list(tmp_path)

    expected_ids = sorted({_sha("reddedilen iki"), _sha("reddedilen bes"), _sha("hassas yedi")})
    assert list(drop_list.excluded_doc_ids) == expected_ids
    assert (drop_list.rejected, drop_list.flagged, drop_list.approved) == (2, 1, 7)
    assert drop_list.excluded_line_count == 4  # "reddedilen iki" iki kez
    assert drop_list.rate_bps == 3000
    assert drop_list.reviewer_ids == (REVIEWER_A, REVIEWER_B)


def test_drop_list_manifest_block_and_model_card_line(tmp_path: Path) -> None:
    drop_list = _drop_list(tmp_path)
    block = drop_list.manifest_block({"schema_version": "derlem.decision.v1", "sha256": "f" * 64})

    assert block["sampled"] == 10
    assert block["rejected"] == 2
    assert block["flagged"] == 1
    assert block["rate_pct"] == "30.00"
    assert block["threshold_pct"] == "30.00"
    assert block["reviewer_ids"] == [REVIEWER_A, REVIEWER_B]
    assert block["excluded_doc_id_count"] == 3
    assert block["excluded_line_count"] == 4
    assert block["extra_occurrence_count"] == 1
    assert block["excluded_doc_ids_sha256"] == doc_id_list_sha256(drop_list.excluded_doc_ids)
    assert block["excluded_doc_ids_sha256"] == hashlib.sha256(
        "".join(f"{doc_id}\n" for doc_id in drop_list.excluded_doc_ids).encode("ascii")
    ).hexdigest()
    assert "2 rejected + 1 flagged of 10 sampled documents = 30.00% (threshold 30.00%" in block["model_card_line"]


def test_decision_file_is_derlem_decision_v1_human_review(tmp_path: Path) -> None:
    drop_list = _drop_list(tmp_path)
    info = write_human_review_decisions(
        drop_list, tmp_path / "decisions.parquet", run_id=RELEASE_ID, decided_at=DECIDED_AT
    )
    rows = list(read_decisions(Path(info.path)))

    assert info.row_count == 3
    assert {row["decision_type"] for row in rows} == {"human_review"}
    assert {row["run_id"] for row in rows} == {RELEASE_ID}
    by_doc = {row["doc_id"]: row for row in rows}
    assert by_doc[_sha("reddedilen iki")]["verdict"] == "reject"
    assert by_doc[_sha("reddedilen iki")]["judge"] == REVIEWER_B  # sira 2 -> B
    assert by_doc[_sha("reddedilen bes")]["verdict"] == "reject"
    assert by_doc[_sha("hassas yedi")]["verdict"] == "flag"
    assert by_doc[_sha("hassas yedi")]["judge"] == REVIEWER_A
    assert all(row["source_ordinal"] is None for row in rows)

    block = drop_list.manifest_block({"sha256": info.sha256})
    assert load_excluded_doc_ids(Path(info.path), block) == frozenset(drop_list.excluded_doc_ids)
    tampered = dict(block, excluded_doc_ids_sha256="0" * 64)
    with pytest.raises(ValueError):
        load_excluded_doc_ids(Path(info.path), tampered)

    again = write_human_review_decisions(
        drop_list, tmp_path / "again.parquet", run_id=RELEASE_ID, decided_at=DECIDED_AT
    )
    assert again.sha256 == info.sha256  # belirlenimci


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"threshold": Decimal("20.00")}, "review_reject_rate_above_threshold"),
        ({"flagged": 2}, "review_counts_do_not_match_source"),
        ({"threshold": None}, "review_threshold_not_active"),
    ],
)
def test_drop_list_blocks_when_evidence_disagrees(tmp_path: Path, kwargs, reason) -> None:
    with pytest.raises(ReleaseGateError) as captured:
        _drop_list(tmp_path, **kwargs)
    assert captured.value.gate_results["document_review_gate"]["reason"] == reason


def test_drop_list_blocks_unreviewed_or_missing_documents(tmp_path: Path) -> None:
    rows = _review_rows()
    rows[0]["decision"] = None
    with pytest.raises(ReleaseGateError) as captured:
        _drop_list(tmp_path, rows=rows)
    assert captured.value.gate_results["document_review_gate"]["reason"] == "review_row_unreviewed"

    rows = _review_rows()
    rows[4]["source_ordinal"] = 99  # kaynakta yok
    with pytest.raises(ReleaseGateError) as captured:
        _drop_list(tmp_path, rows=rows)
    assert captured.value.gate_results["document_review_gate"]["reason"] == "reviewed_document_not_in_source"


def test_release_threshold_must_be_a_release_constant() -> None:
    block = {
        "threshold_bps": 1000, "sampled": 200, "rejected": 18, "flagged": 2,
        "excluded_doc_id_count": 20, "excluded_line_count": 21, "reviewer_ids": [REVIEWER_A],
        "excluded_doc_ids_sha256": "a" * 64,
    }
    summary = summarize_release_human_review({"s1": block})
    assert summary is not None
    assert summary["rate_pct"] == "10.00"
    assert summary["threshold_pct"] == "10.00"
    assert summarize_release_human_review({}) is None
    with pytest.raises(ReleaseGateError) as captured:
        summarize_release_human_review({"s1": block, "s2": dict(block, threshold_bps=1500)})
    assert captured.value.gate_results["document_review_gate"]["reason"] == "review_threshold_not_release_constant"


# --------------------------------------------------------------------------
# Ihracat: tam olarak k belge duser, SHA beklenen
# --------------------------------------------------------------------------


def _export(tmp_path: Path, name: str, export_format: str, source_path: Path, excluded=None):
    source = {
        "source_id": "source-a",
        "source_sha256": "1" * 64,
        "path": source_path,
        "language": "tr",
        "domain": "web",
        "license": "internal",
    }
    if excluded is not None:
        source["excluded_doc_ids"] = excluded
        source["human_review_decisions_sha256"] = "f" * 64
    output = tmp_path / f"{name}.{export_format}"
    result = build_release_export(
        {"content_purpose": "pretrain"}, [source], export_format, output, max_document_bytes=1_000_000
    )
    return result, output.read_bytes(), source


def test_txt_export_drops_exactly_the_excluded_lines(tmp_path: Path) -> None:
    drop_list = _drop_list(tmp_path)
    source_path = tmp_path / "source.txt"
    excluded = frozenset(drop_list.excluded_doc_ids)

    full, full_bytes, _ = _export(tmp_path, "full", "txt", source_path)
    dropped, dropped_bytes, source = _export(tmp_path, "dropped", "txt", source_path, excluded)

    kept_lines = [
        line for line in full_bytes.decode("utf-8").splitlines(keepends=True)
        if _sha(line.rstrip("\n")) not in excluded
    ]
    assert full.record_count == len(SOURCE_LINES)
    assert dropped.record_count == full.record_count - drop_list.excluded_line_count
    assert dropped.source_excluded_counts == {"source-a": 4}
    assert dropped_bytes == "".join(kept_lines).encode("utf-8")
    assert dropped.sha256 == hashlib.sha256("".join(kept_lines).encode("utf-8")).hexdigest()
    assert full.source_excluded_counts == {}

    manifest = json.loads(build_export_manifest(
        {"id": "r", "name": "n", "version": "v", "content_purpose": "pretrain",
         "frozen_at": "t", "manifest_sha256": "m"}, [source], dropped,
    ))
    assert manifest["sources"][0]["human_review_excluded_record_count"] == 4
    assert manifest["sources"][0]["record_count"] == len(SOURCE_LINES) - 4


def test_jsonl_export_drops_exactly_the_excluded_documents(tmp_path: Path) -> None:
    drop_list = _drop_list(tmp_path)
    source_path = tmp_path / "source.txt"
    excluded = frozenset(drop_list.excluded_doc_ids)

    full, full_bytes, _ = _export(tmp_path, "full", "jsonl", source_path)
    dropped, dropped_bytes, _ = _export(tmp_path, "dropped", "jsonl", source_path, excluded)

    kept = [
        line for line in full_bytes.decode("utf-8").splitlines(keepends=True)
        if json.loads(line)["metadata"]["document_sha256"] not in excluded
    ]
    assert dropped.record_count == full.record_count - 4
    assert dropped_bytes == "".join(kept).encode("utf-8")
    # kalan kayitlarin kimligi (kaynak SHA + sira no + metin SHA) degismez
    assert {json.loads(line)["id"] for line in kept} <= {
        json.loads(line)["id"] for line in full_bytes.decode("utf-8").splitlines()
    }


def test_empty_drop_list_changes_no_export_bytes(tmp_path: Path) -> None:
    source_path = _write_source(tmp_path)
    for export_format in ("txt", "jsonl"):
        full, full_bytes, _ = _export(tmp_path, f"plain-{export_format}", export_format, source_path)
        empty, empty_bytes, _ = _export(tmp_path, f"empty-{export_format}", export_format, source_path, frozenset())
        assert empty_bytes == full_bytes
        assert empty.sha256 == full.sha256
        assert empty.source_excluded_counts == {"source-a": 0}


def test_release_manifest_is_unchanged_without_human_review() -> None:
    args = (
        {"id": "r", "name": "n", "version": "v", "content_purpose": "instruction"},
        [{"source_id": "a"}],
        {"document_review_gate": {"status": "passed"}},
        "2026-10-13T00:00:00Z",
        {"status": "present"},
    )
    assert build_release_manifest(*args) == build_release_manifest(*args, human_review=None)
    with_review = json.loads(build_release_manifest(*args, human_review={"rate_pct": "10.00"}))
    assert with_review["human_review"] == {"rate_pct": "10.00"}
    assert "human_review" not in json.loads(build_release_manifest(*args))


# --------------------------------------------------------------------------
# Dondurma kaniti: esikli kaynak ret satirini kanit sayar, esiksiz saymaz
# --------------------------------------------------------------------------


def _contract_pair(decision: str, *, threshold, purpose="pretrain"):
    release = {
        "contract_snapshot_status": "present",
        "contract_snapshot_sha256": "c" * 64,
        "implementation_bundle_sha256": "d" * 64,
    }
    source = {
        "source_id": "source-a", "contract_source_id": "source-a",
        "data_profile_key": "text-document", "data_origin": "human",
        "production_run_id": None, "production_run_implementation_digest": None,
        "production_run_config_sha256": None, "production_run_input_manifest_sha256": None,
        "production_run_completion_job_id": None, "production_run_output_manifest_sha256": None,
        "production_run_output_sha256": None, "production_run_output_byte_size": None,
        "production_run_output_record_count": None, "production_run_completed_at_utc": None,
        "license_evidence_ref_sha256": "e" * 64, "lineage_ref_sha256": "f" * 64,
        "sample_generation": 1, "sample_source_sha256": "9" * 64,
        "sample_sampling_method": "risk-stratified-sha256-v1", "sample_count": 2,
        "sample_membership_count": 2, "sample_membership_root_sha256": "8" * 64,
        "sample_job_id": None, "profile_config_sha256": "a" * 64,
        "profile_config_schema_artifact_kind": "profile_config_schema",
        "profile_config_schema_sha256": "7" * 64, "profile_implementation_key": "text-document-v1",
        "profile_implementation_digest": "6" * 64, "purpose_contract_sha256": "b" * 64,
        "source_implementation_bundle_sha256": "d" * 64, "review_evidence_status": "campaign_pinned",
        "review_campaign_id": "campaign-a", "rubric_version": "multidimensional-v1",
        "current_content_purpose": purpose, "pretrain_review_reject_threshold": threshold,
    }
    reviews = [
        {
            "source_id": "source-a", "document_id": document_id, "document_version": 1,
            "sample_generation": 1, "object_sha256": "a" * 64, "review_id": f"review-{document_id}",
            "decision": decision_value, "review_campaign_id": "campaign-a",
            "rubric_version": "multidimensional-v1", "quality_score": 4,
            "language_quality_score": 4, "coherence_score": 4,
            "information_density_score": 4, "cleanliness_score": 4,
        }
        for document_id, decision_value in (("doc-1", "approved"), ("doc-2", decision))
    ]
    return release, source, reviews


def test_contract_evidence_counts_rejected_sample_only_under_threshold() -> None:
    release, source, reviews = _contract_pair("rejected", threshold=PROPOSED_THRESHOLD)
    gate = validate_release_contract_evidence(release, [source], reviews)
    assert gate["status"] == "passed"
    assert len(_mixture_quality_rows(reviews)) == 1  # atilan ornek kalite karisimina girmez

    for threshold, purpose in ((None, "pretrain"), (PROPOSED_THRESHOLD, "instruction")):
        release, source, reviews = _contract_pair("rejected", threshold=threshold, purpose=purpose)
        with pytest.raises(ReleaseGateError) as captured:
            validate_release_contract_evidence(release, [source], reviews)
        assert captured.value.gate_results["document_review_gate"]["reason"] == "review_evidence_incomplete"


def test_release_source_current_check_uses_threshold() -> None:
    base = {
        "current_sha256": "a" * 64, "source_sha256": "a" * 64, "current_version": 1,
        "source_version": 1, "current_data_origin": "unknown", "data_origin": "unknown",
        "current_production_run_id": None, "production_run_id": None,
        "current_production_run_completion_job_id": None, "production_run_completion_job_id": None,
        "current_production_run_output_manifest_sha256": None,
        "production_run_output_manifest_sha256": None,
        "current_production_run_output_sha256": None, "production_run_output_sha256": None,
        "current_production_run_output_byte_size": None, "production_run_output_byte_size": None,
        "current_production_run_output_record_count": None, "production_run_output_record_count": None,
        "current_production_run_completed_at_utc": None, "production_run_completed_at_utc": None,
        "current_derived_from_source_id": None, "derived_from_source_id": None,
        "current_license_evidence_ref_sha256": "e" * 64, "license_evidence_ref_sha256": "e" * 64,
        "current_lineage_ref_sha256": "f" * 64, "lineage_ref_sha256": "f" * 64,
        "approval_status": "approved_source", "current_rights_status": "cleared",
        "has_license_evidence": True, "pii_status": "clear", "duplicate_status": "unique",
        "normalized_dedup_status": "unique", "document_sampling_status": "sampled",
        "sampled_document_count": 200, "reviewed_document_count": 200,
        "current_content_purpose": "pretrain",
    }
    passing = dict(base, approved_document_count=180, flagged_document_count=20,
                   pretrain_review_reject_threshold=PROPOSED_THRESHOLD)
    failing = dict(passing, approved_document_count=179, flagged_document_count=21)
    no_threshold = dict(passing, pretrain_review_reject_threshold=None)
    assert ReleaseJobsMixin._release_source_is_current(passing)
    assert not ReleaseJobsMixin._release_source_is_current(failing)
    assert not ReleaseJobsMixin._release_source_is_current(no_threshold)
