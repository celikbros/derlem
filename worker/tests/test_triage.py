from pathlib import Path

from derlem_worker.triage import collect_pii_line_triage, release_blockers


def test_collect_pii_line_triage_records_counts_without_values(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text(
        "temiz satir\n"
        "mail test@example.com\n"
        "tckn 10000000146 ve kart 4242 4242 4242 4242\n",
        encoding="utf-8",
    )

    report = collect_pii_line_triage(source, max_ordinals=10)

    assert report.total_lines == 3
    assert report.pii_line_count == 2
    assert report.finding_counts["email"] == 1
    assert report.finding_counts["tckn"] == 1
    assert report.finding_counts["payment_card"] == 1
    assert report.line_counts["email"] == 1
    assert report.line_counts["tckn"] == 1
    assert report.first_ordinals_by_type["email"] == [2]
    assert report.first_ordinals_by_type["tckn"] == [3]
    assert report.first_any_pii_ordinals == [2, 3]
    assert "example.com" not in str(report)


def test_release_blockers_match_review_gates() -> None:
    source = {
        "rights_status": "unknown",
        "license_evidence_ref": None,
        "pii_status": "flagged",
        "duplicate_status": "unique",
        "normalized_dedup_status": "duplicates_found",
        "document_sampling_status": "not_sampled",
        "sampled_document_count": 0,
        "reviewed_document_count": 0,
        "approved_document_count": 0,
        "flagged_document_count": 0,
    }

    assert release_blockers(source) == [
        "rights_not_cleared",
        "license_evidence_missing",
        "pii_not_clear",
        "normalized_dedup_not_clear",
        "documents_not_sampled",
    ]


def test_release_blockers_require_all_sampled_documents_to_be_approved() -> None:
    source = {
        "rights_status": "cleared",
        "license_evidence_ref": "legal/ok.md",
        "pii_status": "clear",
        "duplicate_status": "unique",
        "normalized_dedup_status": "unique",
        "document_sampling_status": "sampled",
        "sampled_document_count": 200,
        "reviewed_document_count": 199,
        "approved_document_count": 199,
        "flagged_document_count": 0,
    }

    assert release_blockers(source) == ["document_sample_review_incomplete"]


def test_release_blockers_pass_when_quality_gates_and_reviews_are_complete() -> None:
    source = {
        "rights_status": "cleared",
        "license_evidence_ref": "legal/ok.md",
        "pii_status": "clear",
        "duplicate_status": "unique",
        "normalized_dedup_status": "unique",
        "document_sampling_status": "sampled",
        "sampled_document_count": 200,
        "reviewed_document_count": 200,
        "approved_document_count": 200,
        "flagged_document_count": 0,
    }

    assert release_blockers(source) == []
