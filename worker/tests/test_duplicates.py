import pytest

from derlem_worker.jobs import classify_exact_duplicate, lineage_excluded_source_id


def test_canonical_source_is_unique() -> None:
    assert classify_exact_duplicate("source-a", "source-a") == ("unique", None)


def test_later_source_points_to_canonical_duplicate() -> None:
    assert classify_exact_duplicate("source-b", "source-a") == ("duplicate", "source-a")


def test_duplicate_classification_requires_identifiers() -> None:
    with pytest.raises(ValueError):
        classify_exact_duplicate("", "source-a")


def test_lineage_exclusion_reads_valid_parent_id() -> None:
    parent_id = "06ac330e-350f-45f0-b596-3dd4aa1dbc57"

    assert lineage_excluded_source_id({"derived_from_source_id": parent_id}) == parent_id


def test_lineage_exclusion_ignores_missing_or_invalid_parent_id() -> None:
    assert lineage_excluded_source_id({}) is None
    assert lineage_excluded_source_id({"derived_from_source_id": "not-a-uuid"}) is None
    assert lineage_excluded_source_id(None) is None
