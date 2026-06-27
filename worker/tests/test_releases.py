from __future__ import annotations

import json
from pathlib import Path

import pytest

from derlem_worker.releases import (
    ReleaseGateError,
    build_export_manifest,
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
    assert manifest["export"]["sha256"] == first.sha256
    assert manifest["export"]["record_count"] == 2
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
