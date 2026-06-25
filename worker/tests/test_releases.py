from __future__ import annotations

import json
from pathlib import Path

import pytest

from derlem_worker.releases import (
    ReleaseGateError,
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
