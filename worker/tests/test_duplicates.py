import pytest

from derlem_worker.jobs import classify_exact_duplicate


def test_canonical_source_is_unique() -> None:
    assert classify_exact_duplicate("source-a", "source-a") == ("unique", None)


def test_later_source_points_to_canonical_duplicate() -> None:
    assert classify_exact_duplicate("source-b", "source-a") == ("duplicate", "source-a")


def test_duplicate_classification_requires_identifiers() -> None:
    with pytest.raises(ValueError):
        classify_exact_duplicate("", "source-a")
