from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from derlem_worker.similarity_calibration import CalibrationSource, calibrate_similarity
from derlem_worker.similarity_review_import import (
    RegisteredSource,
    load_and_validate_report,
    materialize_report_pairs,
)
from derlem_worker.storage import ContentAddressedStore


def _report(tmp_path: Path) -> tuple[Path, dict[str, object], CalibrationSource]:
    source_path = tmp_path / "source.txt"
    source_path.write_text(
        "Ankara bugun acik ve gunesli bir havaya uyandi.\n"
        "Ankara bugun acik ve serin bir havaya uyandi.\n"
        "Turkce veri kalitesi dikkatli inceleme ile guclenir.\n",
        encoding="utf-8",
    )
    source_id = str(uuid4())
    source = CalibrationSource(
        source_id=source_id,
        name="test-source",
        sha256="a" * 64,
        path=source_path,
    )
    report = calibrate_similarity(
        [source],
        content_purpose="pretrain",
        max_document_bytes=4096,
        sample_size=3,
        threshold_max=10,
        closest_pair_limit=3,
    )
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path, report, source


def test_load_and_materialize_report_pairs(tmp_path: Path) -> None:
    report_path, report, source = _report(tmp_path)
    raw_report, loaded = load_and_validate_report(report_path)

    assert json.loads(raw_report) == report
    store = ContentAddressedStore(tmp_path / "store")
    pairs, stored = materialize_report_pairs(
        loaded,
        {
            source.sha256: RegisteredSource(
                source_id=source.source_id or "",
                sha256=source.sha256,
                storage_key="source.txt",
                path=source.path,
            )
        },
        store,
        progress_interval=1,
    )

    assert len(pairs) == 3
    assert len(stored) == 3
    assert [pair["pair_rank"] for pair in pairs] == [1, 2, 3]
    assert all(pair["left"].stored.sha256 for pair in pairs)  # type: ignore[union-attr]
    assert all(pair["right"].token_count >= 5 for pair in pairs)  # type: ignore[union-attr]
    assert all((tmp_path / "store" / item.storage_key).exists() for item in stored)


def test_materialization_rejects_report_distance_drift(tmp_path: Path) -> None:
    _, report, source = _report(tmp_path)
    report["corpus_pairs"]["closest_pairs"][0]["hamming_distance"] = 64  # type: ignore[index]

    with pytest.raises(ValueError, match="Pair distance mismatch"):
        materialize_report_pairs(
            report,
            {
                source.sha256: RegisteredSource(
                    source_id=source.source_id or "",
                    sha256=source.sha256,
                    storage_key="source.txt",
                    path=source.path,
                )
            },
            ContentAddressedStore(tmp_path / "store"),
        )


def test_report_validation_rejects_missing_pairs(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "derlem.similarity-calibration.v1",
                "sources": [{"source_id": str(uuid4()), "sha256": "a" * 64}],
                "corpus_pairs": {"closest_pairs": []},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no closest pairs"):
        load_and_validate_report(report_path)
