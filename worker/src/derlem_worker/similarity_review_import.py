from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Callable

import psycopg
from psycopg.rows import dict_row

from derlem_worker.config import Config, load_config
from derlem_worker.fingerprints import normalize_document_text
from derlem_worker.sampling import _bounded_lines
from derlem_worker.similarity import _similarity_text_from_line, document_simhash, hamming_distance
from derlem_worker.similarity_calibration import CALIBRATION_SCHEMA_VERSION
from derlem_worker.storage import ContentAddressedStore, StoredObject


IMPORT_METHOD = "calibration-closest-pair-materialization-v1"


@dataclass(frozen=True)
class RegisteredSource:
    source_id: str
    sha256: str
    storage_key: str
    path: Path


@dataclass(frozen=True)
class MaterializedDocument:
    source_id: str
    source_sha256: str
    source_ordinal: int
    text: str
    signature: int
    token_count: int
    stored: StoredObject


def load_and_validate_report(report_path: Path) -> tuple[bytes, dict[str, object]]:
    raw_report = report_path.resolve(strict=True).read_bytes()
    try:
        report = json.loads(raw_report)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Calibration report must be valid UTF-8 JSON") from error
    if not isinstance(report, dict):
        raise ValueError("Calibration report root must be an object")
    if report.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        raise ValueError("Unsupported calibration report schema")
    if not isinstance(report.get("sources"), list) or not report["sources"]:
        raise ValueError("Calibration report must contain sources")
    corpus_pairs = report.get("corpus_pairs")
    if not isinstance(corpus_pairs, dict) or not isinstance(corpus_pairs.get("closest_pairs"), list):
        raise ValueError("Calibration report must contain closest_pairs")
    if not corpus_pairs["closest_pairs"]:
        raise ValueError("Calibration report has no closest pairs to review")
    return raw_report, report


def materialize_report_pairs(
    report: dict[str, object],
    registered_sources: dict[str, RegisteredSource],
    store: ContentAddressedStore,
    *,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
    progress_interval: int = 100_000,
) -> tuple[list[dict[str, object]], list[StoredObject]]:
    if progress_interval <= 0:
        raise ValueError("progress_interval must be positive")
    source_rows = _source_rows(report)
    pair_rows = _pair_rows(report, source_rows)
    max_document_bytes = int(report["sampling"]["max_document_bytes"])  # type: ignore[index]
    if max_document_bytes <= 0:
        raise ValueError("Calibration max_document_bytes must be positive")

    wanted: dict[str, set[int]] = {sha256: set() for sha256 in source_rows}
    for pair in pair_rows:
        wanted[str(pair["left_source_sha256"])].add(int(pair["left_source_ordinal"]))
        wanted[str(pair["right_source_sha256"])].add(int(pair["right_source_ordinal"]))

    documents: dict[tuple[str, int], MaterializedDocument] = {}
    stored_objects: dict[str, StoredObject] = {}
    scanned_total = 0
    next_progress_at = progress_interval
    for sha256, ordinals in sorted(wanted.items()):
        source = registered_sources.get(sha256)
        if source is None:
            raise ValueError(f"Registered source is missing for SHA256 {sha256}")
        maximum_ordinal = max(ordinals)
        for ordinal, raw_line, oversized in _bounded_lines(source.path, max_document_bytes):
            scanned_total += 1
            if ordinal in ordinals:
                if oversized or raw_line is None:
                    raise ValueError(f"Review document is oversized at {sha256}:{ordinal}")
                text = _similarity_text_from_line(raw_line.strip())
                signature = document_simhash(text)
                if signature is None:
                    raise ValueError(f"Review document is not SimHash eligible at {sha256}:{ordinal}")
                content = text.encode("utf-8")
                stored = store.ingest_bytes(content)
                stored_objects[stored.sha256] = stored
                documents[(sha256, ordinal)] = MaterializedDocument(
                    source_id=source.source_id,
                    source_sha256=sha256,
                    source_ordinal=ordinal,
                    text=text,
                    signature=signature,
                    token_count=len(normalize_document_text(text).split()),
                    stored=stored,
                )
            if progress_callback is not None and scanned_total >= next_progress_at:
                progress_callback(
                    {
                        "documents_scanned": scanned_total,
                        "documents_materialized": len(documents),
                        "documents_required": sum(len(values) for values in wanted.values()),
                    }
                )
                while next_progress_at <= scanned_total:
                    next_progress_at += progress_interval
            if ordinal >= maximum_ordinal:
                break

    missing = sorted(
        (sha256, ordinal)
        for sha256, ordinals in wanted.items()
        for ordinal in ordinals
        if (sha256, ordinal) not in documents
    )
    if missing:
        raise ValueError(f"Review documents were not found: {missing[:5]}")

    materialized_pairs: list[dict[str, object]] = []
    for rank, pair in enumerate(pair_rows, start=1):
        left = documents[(str(pair["left_source_sha256"]), int(pair["left_source_ordinal"]))]
        right = documents[(str(pair["right_source_sha256"]), int(pair["right_source_ordinal"]))]
        actual_distance = hamming_distance(left.signature, right.signature)
        expected_distance = int(pair["hamming_distance"])
        if actual_distance != expected_distance:
            raise ValueError(
                f"Pair distance mismatch at rank {rank}: expected {expected_distance}, got {actual_distance}"
            )
        materialized_pairs.append(
            {
                "pair_rank": rank,
                "hamming_distance": actual_distance,
                "left": left,
                "right": right,
            }
        )
    if progress_callback is not None:
        progress_callback(
            {
                "documents_scanned": scanned_total,
                "documents_materialized": len(documents),
                "documents_required": sum(len(values) for values in wanted.values()),
            }
        )
    return materialized_pairs, list(stored_objects.values())


def import_review_run(
    config: Config,
    report_path: Path,
    *,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, object]:
    raw_report, report = load_and_validate_report(report_path)
    report_sha256 = hashlib.sha256(raw_report).hexdigest()
    with psycopg.connect(config.database_url, row_factory=dict_row) as connection:
        existing = connection.execute(
            """
            SELECT run.id::text, run.pair_count,
                (SELECT count(DISTINCT review.pair_id)
                 FROM similarity_pair_reviews AS review
                 JOIN similarity_review_pairs AS pair ON pair.id = review.pair_id
                 WHERE pair.run_id = run.id) AS reviewed_pair_count
            FROM similarity_calibration_runs AS run
            WHERE run.report_object_sha256 = %s
            """,
            (report_sha256,),
        ).fetchone()
        if existing is not None:
            return {
                "run_id": str(existing["id"]),
                "report_sha256": report_sha256,
                "pair_count": int(existing["pair_count"]),
                "reviewed_pair_count": int(existing["reviewed_pair_count"]),
                "status": "already_imported",
            }
        registered_sources = _registered_sources(connection, report, config.storage_root)

    store = ContentAddressedStore(config.storage_root)
    materialized_pairs, stored_objects = materialize_report_pairs(
        report,
        registered_sources,
        store,
        progress_callback=progress_callback,
    )
    report_object = store.ingest_bytes(raw_report)
    stored_objects.append(report_object)

    with psycopg.connect(config.database_url, row_factory=dict_row) as connection:
        with connection.transaction():
            for stored in stored_objects:
                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (
                        stored.sha256,
                        stored.storage_key,
                        stored.byte_size,
                        "application/json; charset=utf-8" if stored.sha256 == report_sha256 else "text/plain; charset=utf-8",
                    ),
                )
            sampling = report["sampling"]  # type: ignore[index]
            thresholds = report["thresholds"]  # type: ignore[index]
            run = connection.execute(
                """
                INSERT INTO similarity_calibration_runs(
                    report_object_sha256, schema_version, method, content_purpose,
                    source_snapshot, sampled_document_count, eligible_document_count,
                    simhash_version, threshold_max, pair_count
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                RETURNING id::text
                """,
                (
                    report_sha256,
                    report["schema_version"],
                    report["method"],
                    report["content_purpose"],
                    json.dumps(report["sources"], ensure_ascii=False, sort_keys=True),
                    sampling["sampled_document_count"],
                    sampling["eligible_documents"],
                    report["simhash"]["version"],  # type: ignore[index]
                    max(int(row["threshold"]) for row in thresholds),
                    len(materialized_pairs),
                ),
            ).fetchone()
            assert run is not None
            run_id = str(run["id"])
            for pair in materialized_pairs:
                left = pair["left"]
                right = pair["right"]
                assert isinstance(left, MaterializedDocument)
                assert isinstance(right, MaterializedDocument)
                connection.execute(
                    """
                    INSERT INTO similarity_review_pairs(
                        run_id, pair_rank, hamming_distance,
                        left_source_id, left_source_sha256, left_source_ordinal,
                        left_object_sha256, left_text_preview, left_token_count,
                        right_source_id, right_source_sha256, right_source_ordinal,
                        right_object_sha256, right_text_preview, right_token_count
                    )
                    VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        run_id,
                        pair["pair_rank"],
                        pair["hamming_distance"],
                        left.source_id,
                        left.source_sha256,
                        left.source_ordinal,
                        left.stored.sha256,
                        _preview(left.text),
                        left.token_count,
                        right.source_id,
                        right.source_sha256,
                        right.source_ordinal,
                        right.stored.sha256,
                        _preview(right.text),
                        right.token_count,
                    ),
                )
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES (
                    'system', 'similarity.calibration_imported', 'similarity_calibration_run', %s,
                    jsonb_build_object(
                        'report_sha256', %s::text,
                        'pair_count', %s::integer,
                        'import_method', %s::text
                    )
                )
                """,
                (run_id, report_sha256, len(materialized_pairs), IMPORT_METHOD),
            )
    return {
        "run_id": run_id,
        "report_sha256": report_sha256,
        "pair_count": len(materialized_pairs),
        "reviewed_pair_count": 0,
        "status": "imported",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import calibration closest pairs into the review queue")
    parser.add_argument("--report", type=Path, required=True, help="Calibration JSON report")
    args = parser.parse_args()
    config = load_config()
    outcome = import_review_run(
        config,
        args.report,
        progress_callback=lambda progress: print(
            f"scanned={progress['documents_scanned']} "
            f"materialized={progress['documents_materialized']}/{progress['documents_required']}",
            file=sys.stderr,
        ),
    )
    print(json.dumps(outcome, ensure_ascii=False, indent=2, sort_keys=True))


def _source_rows(report: dict[str, object]) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for raw_source in report["sources"]:  # type: ignore[assignment]
        if not isinstance(raw_source, dict):
            raise ValueError("Calibration source must be an object")
        source_id = str(raw_source.get("source_id") or "")
        sha256 = str(raw_source.get("sha256") or "").lower()
        if not source_id or len(sha256) != 64:
            raise ValueError("Calibration sources must have source_id and SHA256")
        try:
            int(sha256, 16)
        except ValueError as error:
            raise ValueError("Calibration source SHA256 is invalid") from error
        if sha256 in rows:
            raise ValueError("Calibration source SHA256 values must be unique")
        rows[sha256] = {"source_id": source_id, "sha256": sha256}
    return rows


def _pair_rows(
    report: dict[str, object],
    sources: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    closest_pairs = report["corpus_pairs"]["closest_pairs"]  # type: ignore[index]
    rows: list[dict[str, object]] = []
    identities: set[tuple[str, int, str, int]] = set()
    for raw_pair in closest_pairs:
        if not isinstance(raw_pair, dict):
            raise ValueError("Calibration pair must be an object")
        left_sha = str(raw_pair.get("left_source_sha256") or "").lower()
        right_sha = str(raw_pair.get("right_source_sha256") or "").lower()
        left_ordinal = int(raw_pair.get("left_source_ordinal") or 0)
        right_ordinal = int(raw_pair.get("right_source_ordinal") or 0)
        distance = int(raw_pair.get("hamming_distance") or 0)
        if left_sha not in sources or right_sha not in sources:
            raise ValueError("Calibration pair references an unknown source")
        if left_ordinal <= 0 or right_ordinal <= 0 or not 0 <= distance <= 64:
            raise ValueError("Calibration pair identity or distance is invalid")
        identity = (left_sha, left_ordinal, right_sha, right_ordinal)
        if identity in identities:
            raise ValueError("Calibration closest_pairs contains a duplicate")
        identities.add(identity)
        rows.append(
            {
                "left_source_sha256": left_sha,
                "left_source_ordinal": left_ordinal,
                "right_source_sha256": right_sha,
                "right_source_ordinal": right_ordinal,
                "hamming_distance": distance,
            }
        )
    return rows


def _registered_sources(
    connection: psycopg.Connection[dict[str, object]],
    report: dict[str, object],
    storage_root: Path,
) -> dict[str, RegisteredSource]:
    registered: dict[str, RegisteredSource] = {}
    for source in _source_rows(report).values():
        row = connection.execute(
            """
            SELECT source.id::text, source.object_sha256, object.storage_key
            FROM sources AS source
            JOIN storage_objects AS object ON object.sha256 = source.object_sha256
            WHERE source.id = %s
            """,
            (source["source_id"],),
        ).fetchone()
        if row is None:
            raise ValueError(f"Registered source was not found: {source['source_id']}")
        sha256 = str(row["object_sha256"])
        if sha256 != source["sha256"]:
            raise ValueError(f"Registered source SHA256 changed: {source['source_id']}")
        path = (storage_root / str(row["storage_key"])).resolve(strict=True)
        path.relative_to(storage_root)
        registered[sha256] = RegisteredSource(
            source_id=str(row["id"]),
            sha256=sha256,
            storage_key=str(row["storage_key"]),
            path=path,
        )
    return registered


def _preview(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= 500 else collapsed[:499] + "…"


if __name__ == "__main__":
    main()
