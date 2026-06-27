from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import socket
import tempfile
import time
import traceback
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from derlem_worker.config import Config
from derlem_worker.fingerprints import FINGERPRINT_VERSION, document_fingerprint
from derlem_worker.pii import PIIReport, PIIScanner
from derlem_worker.releases import (
    ReleaseGateError,
    build_export_manifest,
    build_release_export,
    build_release_manifest,
    exact_decontamination,
)
from derlem_worker.sampling import (
    SampledDocument,
    SamplingReport,
    _bounded_lines,
    _document_from_line,
    sample_line_documents,
)
from derlem_worker.storage import ContentAddressedStore, StoredObject

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    id: UUID
    job_type: str
    payload: dict[str, object]
    attempts: int
    max_attempts: int


def classify_exact_duplicate(source_id: str, canonical_source_id: str) -> tuple[str, str | None]:
    if not source_id or not canonical_source_id:
        raise ValueError("Source identifiers are required")
    if source_id == canonical_source_id:
        return "unique", None
    return "duplicate", canonical_source_id


def lineage_excluded_source_id(source_metadata: object) -> str | None:
    if not isinstance(source_metadata, dict):
        return None
    candidate = str(source_metadata.get("derived_from_source_id") or "").strip()
    if not candidate:
        return None
    try:
        return str(UUID(candidate))
    except ValueError:
        return None


class Worker:
    def __init__(self, config: Config, worker_id: str | None = None) -> None:
        self.config = config
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.store = ContentAddressedStore(config.storage_root)
        self.pii_scanner = PIIScanner()

    def enqueue_maintenance_jobs(self) -> int:
        with psycopg.connect(self.config.database_url) as connection:
            duplicate_jobs = connection.execute(
                """
                INSERT INTO background_jobs(job_type, payload, created_by)
                SELECT
                    'check_exact_duplicate',
                    jsonb_build_object(
                        'source_id', source.id::text,
                        'object_sha256', source.object_sha256::text
                    ),
                    source.created_by
                FROM sources AS source
                WHERE source.object_sha256 IS NOT NULL
                  AND source.duplicate_status = 'not_checked'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM background_jobs AS job
                      WHERE job.job_type = 'check_exact_duplicate'
                        AND job.payload->>'source_id' = source.id::text
                        AND job.status IN ('queued', 'running')
                  )
                ON CONFLICT DO NOTHING
                """
            )
            fingerprint_jobs = connection.execute(
                """
                INSERT INTO background_jobs(job_type, payload, created_by)
                SELECT
                    'index_document_fingerprints',
                    jsonb_build_object(
                        'source_id', source.id::text,
                        'object_sha256', source.object_sha256::text
                    ),
                    source.created_by
                FROM sources AS source
                WHERE source.object_sha256 IS NOT NULL
                  AND source.duplicate_status = 'unique'
                  AND source.normalized_dedup_status = 'not_checked'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM background_jobs AS job
                      WHERE job.job_type = 'index_document_fingerprints'
                        AND job.payload->>'source_id' = source.id::text
                        AND job.status IN ('queued', 'running')
                  )
                ON CONFLICT DO NOTHING
                """
            )
            sample_jobs = connection.execute(
                """
                INSERT INTO background_jobs(job_type, payload, created_by)
                SELECT
                    'sample_documents',
                    jsonb_build_object(
                        'source_id', source.id::text,
                        'object_sha256', source.object_sha256::text
                    ),
                    source.created_by
                FROM sources AS source
                WHERE source.object_sha256 IS NOT NULL
                  AND source.duplicate_status = 'unique'
                  AND source.normalized_dedup_status = 'unique'
                  AND source.document_sampling_status = 'not_sampled'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM background_jobs AS job
                      WHERE job.job_type = 'sample_documents'
                        AND job.payload->>'source_id' = source.id::text
                        AND job.status IN ('queued', 'running')
                  )
                ON CONFLICT DO NOTHING
                """
            )
            connection.commit()
        total = duplicate_jobs.rowcount + fingerprint_jobs.rowcount + sample_jobs.rowcount
        if total > 0:
            LOGGER.info(
                "maintenance_jobs_queued exact_duplicate=%s document_fingerprints=%s document_samples=%s",
                duplicate_jobs.rowcount,
                fingerprint_jobs.rowcount,
                sample_jobs.rowcount,
            )
        return total

    def run_once(self) -> bool:
        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            job = self._claim(connection)
        if job is None:
            return False

        try:
            if job.job_type in {"ingest_local_file", "ingest_staged_file"}:
                ingest_path = self._ingest_path(job)
                stored = self.store.ingest_file(ingest_path)
                with psycopg.connect(self.config.database_url) as connection:
                    self._complete_ingest(connection, job, stored)
                if job.job_type == "ingest_staged_file":
                    ingest_path.unlink(missing_ok=True)
                LOGGER.info("job_succeeded job_id=%s sha256=%s", job.id, stored.sha256)
            elif job.job_type == "scan_pii":
                object_sha256, report = self._scan_pii(job)
                with psycopg.connect(self.config.database_url) as connection:
                    self._complete_pii_scan(connection, job, object_sha256, report)
                LOGGER.info("job_succeeded job_id=%s pii_status=%s", job.id, report.status)
            elif job.job_type == "check_exact_duplicate":
                with psycopg.connect(self.config.database_url) as connection:
                    status, duplicate_of = self._complete_exact_duplicate_check(connection, job)
                LOGGER.info(
                    "job_succeeded job_id=%s duplicate_status=%s duplicate_of=%s",
                    job.id,
                    status,
                    duplicate_of,
                )
            elif job.job_type == "index_document_fingerprints":
                with psycopg.connect(self.config.database_url) as connection:
                    status, duplicate_count, duplicate_source_count = self._index_document_fingerprints(
                        connection,
                        job,
                    )
                LOGGER.info(
                    "job_succeeded job_id=%s normalized_dedup_status=%s duplicate_count=%s duplicate_source_count=%s",
                    job.id,
                    status,
                    duplicate_count,
                    duplicate_source_count,
                )
            elif job.job_type == "sample_documents":
                object_sha256, report, stored_samples = self._sample_documents(job)
                with psycopg.connect(self.config.database_url) as connection:
                    self._complete_document_sampling(
                        connection,
                        job,
                        object_sha256,
                        report,
                        stored_samples,
                    )
                LOGGER.info(
                    "job_succeeded job_id=%s sampled=%s total_documents=%s",
                    job.id,
                    len(report.samples),
                    report.total_documents,
                )
            elif job.job_type == "freeze_release":
                manifest_sha256 = self._freeze_release(job)
                LOGGER.info(
                    "job_succeeded job_id=%s release_id=%s manifest_sha256=%s",
                    job.id,
                    job.payload.get("release_id"),
                    manifest_sha256,
                )
            elif job.job_type == "export_release":
                export_sha256 = self._export_release(job)
                LOGGER.info(
                    "job_succeeded job_id=%s release_id=%s format=%s export_sha256=%s",
                    job.id,
                    job.payload.get("release_id"),
                    job.payload.get("format"),
                    export_sha256,
                )
            else:
                raise ValueError(f"Unsupported job type: {job.job_type}")
        except Exception as error:  # Worker boundary: failure must be persisted.
            LOGGER.error("job_failed job_id=%s error=%s", job.id, error)
            LOGGER.debug("%s", traceback.format_exc())
            with psycopg.connect(self.config.database_url) as connection:
                self._fail_or_retry(
                    connection,
                    job,
                    error,
                    permanent=isinstance(error, ReleaseGateError),
                )
        return True

    def run_forever(self) -> None:
        LOGGER.info("worker_started worker_id=%s", self.worker_id)
        while True:
            if not self.run_once():
                time.sleep(self.config.poll_interval_seconds)

    def _claim(self, connection: psycopg.Connection) -> Job | None:
        row = connection.execute(
            """
            WITH candidate AS (
                SELECT id
                FROM background_jobs
                WHERE status = 'queued' AND available_at <= now()
                ORDER BY priority ASC, available_at ASC, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE background_jobs AS job
            SET status = 'running',
                attempts = attempts + 1,
                locked_at = now(),
                locked_by = %s,
                updated_at = now()
            FROM candidate
            WHERE job.id = candidate.id
            RETURNING job.id, job.job_type, job.payload, job.attempts, job.max_attempts
            """,
            (self.worker_id,),
        ).fetchone()
        connection.commit()
        if row is None:
            return None
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return Job(
            id=row["id"],
            job_type=row["job_type"],
            payload=payload,
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
        )

    def _ingest_path(self, job: Job) -> Path:
        source_id = str(job.payload.get("source_id", "")).strip()
        if not source_id:
            raise ValueError(f"{job.job_type} requires source_id")
        if job.job_type == "ingest_staged_file":
            staged_path = str(job.payload.get("staged_path", "")).strip()
            if not staged_path:
                raise ValueError("ingest_staged_file requires staged_path")
            resolved = Path(staged_path).resolve(strict=True)
            resolved.relative_to(self.config.staging_root)
            return resolved
        local_path = str(job.payload.get("local_path", "")).strip()
        if not local_path:
            raise ValueError("ingest_local_file requires local_path")
        return Path(local_path).resolve(strict=True)

    def _scan_pii(self, job: Job) -> tuple[str, PIIReport]:
        source_id = str(job.payload.get("source_id", "")).strip()
        expected_sha256 = str(job.payload.get("object_sha256", "")).strip()
        if not source_id:
            raise ValueError("scan_pii requires source_id")

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                SELECT source.object_sha256, object.storage_key
                FROM sources AS source
                JOIN storage_objects AS object ON object.sha256 = source.object_sha256
                WHERE source.id = %s
                """,
                (source_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Source or stored object was not found")
        object_sha256 = str(row["object_sha256"])
        if expected_sha256 and expected_sha256 != object_sha256:
            raise ValueError("Source object changed before PII scan")

        object_path = (self.config.storage_root / str(row["storage_key"])).resolve()
        object_path.relative_to(self.config.storage_root)
        return object_sha256, self.pii_scanner.scan_file(object_path)

    def _sample_documents(
        self,
        job: Job,
    ) -> tuple[str, SamplingReport, list[tuple[SampledDocument, StoredObject]]]:
        source_id = str(job.payload.get("source_id", "")).strip()
        expected_sha256 = str(job.payload.get("object_sha256", "")).strip()
        if not source_id:
            raise ValueError("sample_documents requires source_id")

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                SELECT source.object_sha256, source.duplicate_status,
                    source.normalized_dedup_status, object.storage_key
                FROM sources AS source
                JOIN storage_objects AS object ON object.sha256 = source.object_sha256
                WHERE source.id = %s
                """,
                (source_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Source or stored object was not found")
        object_sha256 = str(row["object_sha256"])
        if expected_sha256 and expected_sha256 != object_sha256:
            raise ValueError("Source object changed before document sampling")
        if row["duplicate_status"] != "unique" or row["normalized_dedup_status"] != "unique":
            raise ValueError("Only canonical deduplicated sources can be sampled")

        object_path = (self.config.storage_root / str(row["storage_key"])).resolve()
        object_path.relative_to(self.config.storage_root)
        report = sample_line_documents(
            object_path,
            sample_size=self.config.document_sample_size,
            max_document_bytes=self.config.max_document_bytes,
            seed=object_sha256,
        )
        stored_samples = [
            (sample, self.store.ingest_bytes(sample.text.encode("utf-8")))
            for sample in report.samples
        ]
        return object_sha256, report, stored_samples

    def _complete_ingest(
        self,
        connection: psycopg.Connection,
        job: Job,
        stored: StoredObject,
    ) -> None:
        source_id = str(job.payload["source_id"])
        with connection.transaction():
            declared = connection.execute(
                """
                SELECT declared_sha256, declared_byte_size, declared_line_count
                FROM sources
                WHERE id = %s
                FOR UPDATE
                """,
                (source_id,),
            ).fetchone()
            if declared is None:
                raise RuntimeError("Source was not found")
            declared_sha256, declared_byte_size, declared_line_count = declared
            mismatches = []
            if declared_sha256 is not None and str(declared_sha256) != stored.sha256:
                mismatches.append("sha256")
            if declared_byte_size is not None and int(declared_byte_size) != stored.byte_size:
                mismatches.append("byte_size")
            if declared_line_count is not None and int(declared_line_count) != stored.line_count:
                mismatches.append("line_count")
            if mismatches:
                raise RuntimeError(f"Declared artifact mismatch: {', '.join(mismatches)}")

            connection.execute(
                """
                INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                VALUES (%s, %s, %s, 'text/plain')
                ON CONFLICT (sha256) DO NOTHING
                """,
                (stored.sha256, stored.storage_key, stored.byte_size),
            )
            updated = connection.execute(
                """
                UPDATE sources
                SET object_sha256 = %s,
                    byte_size = %s,
                    line_count = %s,
                    detected_encoding = %s,
                    approval_status = 'raw_ingested'
                WHERE id = %s AND object_sha256 IS NULL
                """,
                (
                    stored.sha256,
                    stored.byte_size,
                    stored.line_count,
                    stored.detected_encoding,
                    source_id,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Source is missing or already ingested")
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES (
                    'system', 'source.ingested', 'source', %s,
                    jsonb_build_object('job_id', %s::text, 'sha256', %s::text, 'byte_size', %s::bigint)
                )
                """,
                (source_id, str(job.id), stored.sha256, stored.byte_size),
            )
            connection.execute(
                """
                INSERT INTO background_jobs(job_type, payload, created_by)
                SELECT
                    'scan_pii',
                    jsonb_build_object('source_id', %s::text, 'object_sha256', %s::text),
                    created_by
                FROM sources
                WHERE id = %s
                ON CONFLICT DO NOTHING
                """,
                (source_id, stored.sha256, source_id),
            )
            connection.execute(
                """
                INSERT INTO background_jobs(job_type, payload, created_by)
                SELECT
                    'check_exact_duplicate',
                    jsonb_build_object('source_id', %s::text, 'object_sha256', %s::text),
                    created_by
                FROM sources
                WHERE id = %s
                ON CONFLICT DO NOTHING
                """,
                (source_id, stored.sha256, source_id),
            )
            connection.execute(
                """
                UPDATE background_jobs
                SET status = 'succeeded', result = %s::jsonb, completed_at = now(), updated_at = now()
                WHERE id = %s AND status = 'running'
                """,
                (
                    json.dumps(
                        {
                            "sha256": stored.sha256,
                            "byte_size": stored.byte_size,
                            "line_count": stored.line_count,
                            "detected_encoding": stored.detected_encoding,
                            "original_filename": job.payload.get("original_filename"),
                        }
                    ),
                    job.id,
                ),
            )

    def _complete_pii_scan(
        self,
        connection: psycopg.Connection,
        job: Job,
        object_sha256: str,
        report: PIIReport,
    ) -> None:
        source_id = str(job.payload["source_id"])
        findings_json = json.dumps(report.findings)
        with connection.transaction():
            connection.execute(
                """
                INSERT INTO pii_scans(
                    source_id, job_id, object_sha256, scanner_version, status, findings
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (source_id, object_sha256, scanner_version)
                DO UPDATE SET
                    job_id = EXCLUDED.job_id,
                    status = EXCLUDED.status,
                    findings = EXCLUDED.findings,
                    scanned_at = now()
                """,
                (source_id, job.id, object_sha256, report.scanner_version, report.status, findings_json),
            )
            updated = connection.execute(
                """
                UPDATE sources
                SET pii_status = %s,
                    risk_level = CASE
                        WHEN %s = 'flagged' THEN 'high'
                        WHEN risk_level = 'unknown' THEN 'low'
                        ELSE risk_level
                    END,
                    approval_status = CASE
                        WHEN %s = 'flagged' THEN 'quarantined'
                        WHEN duplicate_status = 'duplicate' THEN 'quarantined'
                        WHEN normalized_dedup_status = 'duplicates_found' THEN 'quarantined'
                        WHEN duplicate_status = 'unique' AND normalized_dedup_status = 'unique'
                            THEN CASE
                                WHEN document_sampling_status = 'sampled' THEN 'sampled_for_review'
                                ELSE 'auto_checked'
                            END
                        ELSE approval_status
                    END
                WHERE id = %s AND object_sha256 = %s
                """,
                (report.status, report.status, report.status, source_id, object_sha256),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Source object changed while completing PII scan")
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES (
                    'system', 'source.pii_scanned', 'source', %s,
                    jsonb_build_object(
                        'job_id', %s::text,
                        'scanner_version', %s::text,
                        'status', %s::text,
                        'findings', %s::jsonb
                    )
                )
                """,
                (source_id, str(job.id), report.scanner_version, report.status, findings_json),
            )
            connection.execute(
                """
                UPDATE background_jobs
                SET status = 'succeeded',
                    result = jsonb_build_object(
                        'scanner_version', %s::text,
                        'status', %s::text,
                        'findings', %s::jsonb
                    ),
                    completed_at = now(),
                    updated_at = now()
                WHERE id = %s AND status = 'running'
                """,
                (report.scanner_version, report.status, findings_json, job.id),
            )

    def _complete_exact_duplicate_check(
        self,
        connection: psycopg.Connection,
        job: Job,
    ) -> tuple[str, str | None]:
        source_id = str(job.payload.get("source_id", "")).strip()
        expected_sha256 = str(job.payload.get("object_sha256", "")).strip()
        if not source_id:
            raise ValueError("check_exact_duplicate requires source_id")

        with connection.transaction():
            source = connection.execute(
                """
                SELECT object_sha256
                FROM sources
                WHERE id = %s
                FOR UPDATE
                """,
                (source_id,),
            ).fetchone()
            if source is None or source[0] is None:
                raise RuntimeError("Source or stored object was not found")
            object_sha256 = str(source[0])
            if expected_sha256 and expected_sha256 != object_sha256:
                raise RuntimeError("Source object changed before exact duplicate check")

            canonical = connection.execute(
                """
                SELECT id::text
                FROM sources
                WHERE object_sha256 = %s
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (object_sha256,),
            ).fetchone()
            if canonical is None:
                raise RuntimeError("Canonical source was not found")
            canonical_id = str(canonical[0])
            status, duplicate_of = classify_exact_duplicate(source_id, canonical_id)

            updated = connection.execute(
                """
                UPDATE sources
                SET duplicate_status = %s,
                    duplicate_of_source_id = %s,
                    risk_level = CASE
                        WHEN %s = 'duplicate' AND risk_level NOT IN ('high', 'critical') THEN 'medium'
                        ELSE risk_level
                    END,
                    approval_status = CASE
                        WHEN %s = 'duplicate' THEN 'quarantined'
                        WHEN pii_status = 'clear'
                             AND normalized_dedup_status = 'unique'
                             AND approval_status NOT IN ('approved_source', 'release_candidate', 'rejected')
                            THEN CASE
                                WHEN document_sampling_status = 'sampled' THEN 'sampled_for_review'
                                ELSE 'auto_checked'
                            END
                        ELSE approval_status
                    END
                WHERE id = %s AND object_sha256 = %s
                """,
                (status, duplicate_of, status, status, source_id, object_sha256),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Source object changed while completing exact duplicate check")

            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES (
                    'system', 'source.exact_duplicate_checked', 'source', %s,
                    jsonb_strip_nulls(jsonb_build_object(
                        'job_id', %s::text,
                        'scanner_version', 'sha256-file-v1',
                        'status', %s::text,
                        'object_sha256', %s::text,
                        'duplicate_of_source_id', %s::text
                    ))
                )
                """,
                (source_id, str(job.id), status, object_sha256, duplicate_of),
            )
            connection.execute(
                """
                UPDATE background_jobs
                SET status = 'succeeded',
                    result = jsonb_strip_nulls(jsonb_build_object(
                        'scanner_version', 'sha256-file-v1',
                        'status', %s::text,
                        'object_sha256', %s::text,
                        'duplicate_of_source_id', %s::text
                    )),
                    completed_at = now(),
                    updated_at = now()
                WHERE id = %s AND status = 'running'
                """,
                (status, object_sha256, duplicate_of, job.id),
            )
            if status == "unique":
                connection.execute(
                    """
                    INSERT INTO background_jobs(job_type, payload, created_by)
                    SELECT
                        'index_document_fingerprints',
                        jsonb_build_object('source_id', %s::text, 'object_sha256', %s::text),
                        created_by
                    FROM sources
                    WHERE id = %s AND normalized_dedup_status = 'not_checked'
                    ON CONFLICT DO NOTHING
                    """,
                    (source_id, object_sha256, source_id),
                )
        return status, duplicate_of

    def _index_document_fingerprints(
        self,
        connection: psycopg.Connection,
        job: Job,
    ) -> tuple[str, int, int]:
        source_id = str(job.payload.get("source_id", "")).strip()
        expected_sha256 = str(job.payload.get("object_sha256", "")).strip()
        if not source_id:
            raise ValueError("index_document_fingerprints requires source_id")

        with connection.transaction():
            source = connection.execute(
                """
                SELECT source.object_sha256, source.duplicate_status, object.storage_key, source.source_metadata
                FROM sources AS source
                JOIN storage_objects AS object ON object.sha256 = source.object_sha256
                WHERE source.id = %s
                FOR UPDATE OF source
                """,
                (source_id,),
            ).fetchone()
            if source is None or source[0] is None:
                raise RuntimeError("Source or stored object was not found")
            object_sha256 = str(source[0])
            if expected_sha256 and expected_sha256 != object_sha256:
                raise RuntimeError("Source object changed before document fingerprinting")
            if source[1] != "unique":
                raise RuntimeError("Only canonical unique sources can be fingerprinted")
            excluded_source_id = lineage_excluded_source_id(source[3])

            connection.execute(
                """
                DELETE FROM document_fingerprints
                WHERE source_id = %s AND source_sha256 = %s AND fingerprint_version = %s
                """,
                (source_id, object_sha256, FINGERPRINT_VERSION),
            )

            total_documents = 0
            indexed_documents = 0
            skipped_oversized = 0
            skipped_too_short = 0
            batch: list[tuple[str, str, int, str, int, str]] = []
            object_path = self._stored_object_path(str(source[2]))
            for ordinal, raw_line, oversized in _bounded_lines(
                object_path,
                self.config.max_document_bytes,
            ):
                if oversized:
                    total_documents += 1
                    skipped_oversized += 1
                    continue
                assert raw_line is not None
                stripped = raw_line.strip()
                if not stripped:
                    continue
                total_documents += 1
                text, _ = _document_from_line(stripped)
                if not text:
                    continue
                fingerprint = document_fingerprint(text)
                if fingerprint is None:
                    skipped_too_short += 1
                    continue
                normalized_sha256, normalized_char_count = fingerprint
                indexed_documents += 1
                batch.append(
                    (
                        source_id,
                        object_sha256,
                        ordinal,
                        normalized_sha256,
                        normalized_char_count,
                        FINGERPRINT_VERSION,
                    )
                )
                if len(batch) >= 1000:
                    self._insert_document_fingerprint_batch(connection, batch)
                    batch.clear()
            if batch:
                self._insert_document_fingerprint_batch(connection, batch)

            duplicate_counts = connection.execute(
                """
                WITH current_fingerprints AS (
                    SELECT source_ordinal, normalized_sha256
                    FROM document_fingerprints
                    WHERE source_id = %s
                      AND source_sha256 = %s
                      AND fingerprint_version = %s
                ),
                internal_duplicates AS (
                    SELECT COALESCE(sum(count_per_hash - 1), 0)::bigint AS duplicate_count
                    FROM (
                        SELECT count(*) AS count_per_hash
                        FROM current_fingerprints
                        GROUP BY normalized_sha256
                        HAVING count(*) > 1
                    ) AS grouped
                ),
                external_duplicates AS (
                    SELECT
                        count(DISTINCT current_fingerprints.source_ordinal)::bigint AS duplicate_count,
                        count(DISTINCT other.source_id)::bigint AS duplicate_source_count
                    FROM current_fingerprints
                    JOIN document_fingerprints AS other
                      ON other.fingerprint_version = %s
                     AND other.normalized_sha256 = current_fingerprints.normalized_sha256
                     AND other.source_id <> %s
                     AND (%s::uuid IS NULL OR other.source_id <> %s::uuid)
                )
                SELECT
                    internal_duplicates.duplicate_count,
                    external_duplicates.duplicate_count,
                    external_duplicates.duplicate_source_count
                FROM internal_duplicates, external_duplicates
                """,
                (
                    source_id,
                    object_sha256,
                    FINGERPRINT_VERSION,
                    FINGERPRINT_VERSION,
                    source_id,
                    excluded_source_id,
                    excluded_source_id,
                ),
            ).fetchone()
            internal_duplicate_count = int(duplicate_counts[0] or 0)
            external_duplicate_count = int(duplicate_counts[1] or 0)
            duplicate_source_count = int(duplicate_counts[2] or 0)
            duplicate_count = internal_duplicate_count + external_duplicate_count
            status = "unique" if duplicate_count == 0 else "duplicates_found"

            updated = connection.execute(
                """
                UPDATE sources
                SET normalized_dedup_status = %s,
                    normalized_duplicate_count = %s,
                    normalized_duplicate_source_count = %s,
                    document_count = %s,
                    risk_level = CASE
                        WHEN %s = 'duplicates_found' AND risk_level NOT IN ('high', 'critical') THEN 'medium'
                        ELSE risk_level
                    END,
                    approval_status = CASE
                        WHEN %s = 'duplicates_found' THEN 'quarantined'
                        WHEN pii_status = 'clear'
                             AND duplicate_status = 'unique'
                             AND approval_status NOT IN ('approved_source', 'release_candidate', 'rejected')
                            THEN CASE
                                WHEN document_sampling_status = 'sampled' THEN 'sampled_for_review'
                                ELSE 'auto_checked'
                            END
                        ELSE approval_status
                    END
                WHERE id = %s AND object_sha256 = %s
                """,
                (
                    status,
                    duplicate_count,
                    duplicate_source_count,
                    total_documents,
                    status,
                    status,
                    source_id,
                    object_sha256,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Source object changed while recording document fingerprints")

            result_json = json.dumps(
                {
                    "scanner_version": FINGERPRINT_VERSION,
                    "status": status,
                    "total_documents": total_documents,
                    "indexed_documents": indexed_documents,
                    "skipped_oversized": skipped_oversized,
                    "skipped_too_short": skipped_too_short,
                    "duplicate_count": duplicate_count,
                    "internal_duplicate_count": internal_duplicate_count,
                    "external_duplicate_count": external_duplicate_count,
                    "duplicate_source_count": duplicate_source_count,
                    "lineage_excluded_source_id": excluded_source_id,
                }
            )
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES ('system', 'source.normalized_dedup_checked', 'source', %s, %s::jsonb)
                """,
                (source_id, result_json),
            )
            connection.execute(
                """
                UPDATE background_jobs
                SET status = 'succeeded', result = %s::jsonb,
                    completed_at = now(), updated_at = now()
                WHERE id = %s AND status = 'running'
                """,
                (result_json, job.id),
            )
            if status == "unique":
                connection.execute(
                    """
                    INSERT INTO background_jobs(job_type, payload, created_by)
                    SELECT
                        'sample_documents',
                        jsonb_build_object('source_id', %s::text, 'object_sha256', %s::text),
                        created_by
                    FROM sources
                    WHERE id = %s AND document_sampling_status = 'not_sampled'
                    ON CONFLICT DO NOTHING
                    """,
                    (source_id, object_sha256, source_id),
                )
        return status, duplicate_count, duplicate_source_count

    @staticmethod
    def _insert_document_fingerprint_batch(
        connection: psycopg.Connection,
        batch: list[tuple[str, str, int, str, int, str]],
    ) -> None:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO document_fingerprints(
                    source_id, source_sha256, source_ordinal,
                    normalized_sha256, normalized_char_count, fingerprint_version
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                batch,
            )

    def _complete_document_sampling(
        self,
        connection: psycopg.Connection,
        job: Job,
        object_sha256: str,
        report: SamplingReport,
        stored_samples: list[tuple[SampledDocument, StoredObject]],
    ) -> None:
        source_id = str(job.payload["source_id"])
        inserted_count = 0
        with connection.transaction():
            source = connection.execute(
                """
                SELECT object_sha256, duplicate_status, normalized_dedup_status, pii_status
                FROM sources
                WHERE id = %s
                FOR UPDATE
                """,
                (source_id,),
            ).fetchone()
            if source is None or str(source[0]) != object_sha256:
                raise RuntimeError("Source object changed while completing document sampling")
            if source[1] != "unique" or source[2] != "unique":
                raise RuntimeError("Only canonical deduplicated sources can be sampled")

            for sample, stored in stored_samples:
                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, 'text/plain; charset=utf-8')
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (stored.sha256, stored.storage_key, stored.byte_size),
                )
                preview = " ".join(sample.text.split())
                if len(preview) > 240:
                    preview = preview[:240] + "…"
                document = connection.execute(
                    """
                    INSERT INTO documents(
                        source_id, source_ordinal, external_id, current_object_sha256,
                        text_preview, byte_size, char_count
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_id, source_ordinal) DO NOTHING
                    RETURNING id
                    """,
                    (
                        source_id,
                        sample.source_ordinal,
                        sample.external_id,
                        stored.sha256,
                        preview,
                        stored.byte_size,
                        len(sample.text),
                    ),
                ).fetchone()
                if document is None:
                    continue
                inserted_count += 1
                connection.execute(
                    """
                    INSERT INTO document_versions(
                        document_id, version, object_sha256, byte_size, char_count,
                        actor_type, reason
                    )
                    VALUES (%s, 1, %s, %s, %s, 'system', 'reservoir-sha256-v1')
                    """,
                    (document[0], stored.sha256, stored.byte_size, len(sample.text)),
                )

            updated = connection.execute(
                """
                UPDATE sources
                SET document_count = %s,
                    sampled_document_count = (
                        SELECT count(*) FROM documents WHERE source_id = %s
                    ),
                    document_sampling_status = 'sampled',
                    approval_status = CASE
                        WHEN %s = 'clear'
                             AND duplicate_status = 'unique'
                             AND normalized_dedup_status = 'unique'
                             AND approval_status NOT IN ('approved_source', 'release_candidate', 'rejected')
                            THEN 'sampled_for_review'
                        ELSE approval_status
                    END
                WHERE id = %s AND object_sha256 = %s
                """,
                (report.total_documents, source_id, source[3], source_id, object_sha256),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Source object changed while recording document samples")

            result_json = json.dumps(
                {
                    "sampling_method": "reservoir-sha256-v1",
                    "sample_size": len(report.samples),
                    "inserted_count": inserted_count,
                    "total_documents": report.total_documents,
                    "eligible_documents": report.eligible_documents,
                    "skipped_oversized": report.skipped_oversized,
                }
            )
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES ('system', 'source.documents_sampled', 'source', %s, %s::jsonb)
                """,
                (source_id, result_json),
            )
            connection.execute(
                """
                UPDATE background_jobs
                SET status = 'succeeded', result = %s::jsonb,
                    completed_at = now(), updated_at = now()
                WHERE id = %s AND status = 'running'
                """,
                (result_json, job.id),
            )

    def _freeze_release(self, job: Job) -> str:
        release_id = str(job.payload.get("release_id", "")).strip()
        requested_by = str(job.payload.get("requested_by", "")).strip()
        if not release_id or not requested_by:
            raise ReleaseGateError(
                "freeze_release requires release_id and requested_by",
                {"freeze": {"status": "blocked", "reason": "invalid_job_payload"}},
            )

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            release = connection.execute(
                """
                SELECT id::text, name, version, content_purpose, status
                FROM releases
                WHERE id = %s
                """,
                (release_id,),
            ).fetchone()
            source_rows = connection.execute(
                """
                SELECT release_source.source_id::text, release_source.source_sha256,
                    release_source.source_version, release_source.source_name,
                    release_source.source_type, release_source.license,
                    release_source.rights_status, release_source.language,
                    release_source.domain, release_source.lineage_ref,
                    release_source.byte_size, release_source.line_count,
                    object.media_type, object.storage_key,
                    source.object_sha256 AS current_sha256,
                    source.version AS current_version,
                    source.approval_status, source.rights_status AS current_rights_status,
                    source.license_evidence_ref, source.pii_status,
                    source.duplicate_status, source.normalized_dedup_status,
                    source.document_sampling_status,
                    source.sampled_document_count, source.reviewed_document_count,
                    source.approved_document_count, source.flagged_document_count
                FROM release_sources AS release_source
                JOIN sources AS source ON source.id = release_source.source_id
                JOIN storage_objects AS object ON object.sha256 = release_source.source_sha256
                WHERE release_source.release_id = %s
                ORDER BY release_source.source_id
                """,
                (release_id,),
            ).fetchall()
            reference_rows = []
            if release is not None and release["content_purpose"] == "pretrain":
                reference_rows = connection.execute(
                    """
                    SELECT source.object_sha256, object.storage_key
                    FROM sources AS source
                    JOIN storage_objects AS object ON object.sha256 = source.object_sha256
                    WHERE source.content_purpose IN ('eval', 'holdout')
                      AND source.object_sha256 IS NOT NULL
                      AND source.duplicate_status <> 'duplicate'
                    ORDER BY source.id
                    """
                ).fetchall()

        if release is None:
            raise ReleaseGateError(
                "Release was not found",
                {"freeze": {"status": "blocked", "reason": "release_not_found"}},
            )
        if release["status"] != "draft":
            raise ReleaseGateError(
                "Only draft releases can be frozen",
                {"freeze": {"status": "blocked", "reason": "release_not_draft"}},
            )
        if not source_rows:
            raise ReleaseGateError(
                "Release has no sources",
                {"source_gate": {"status": "blocked", "reason": "empty_release"}},
            )

        for source in source_rows:
            if not self._release_source_is_current(source):
                raise ReleaseGateError(
                    "Release source changed or is no longer eligible",
                    {
                        "source_gate": {
                            "status": "blocked",
                            "reason": "source_changed_or_ineligible",
                            "source_id": source["source_id"],
                        }
                    },
                )

        release_paths = [
            (str(source["source_sha256"]), self._stored_object_path(str(source["storage_key"])))
            for source in source_rows
        ]
        if release["content_purpose"] == "pretrain":
            reference_paths = [
                (str(reference["object_sha256"]), self._stored_object_path(str(reference["storage_key"])))
                for reference in reference_rows
            ]
            decontamination = exact_decontamination(
                reference_paths,
                release_paths,
                max_document_bytes=self.config.max_document_bytes,
            )
            if decontamination.status != "passed":
                raise ReleaseGateError(
                    "Eval or holdout content was found in the pretrain release",
                    {"decontamination": decontamination.to_dict()},
                )
            decontamination_result = decontamination.to_dict()
        else:
            decontamination_result = {
                "status": "not_applicable",
                "reason": "content_purpose_is_not_pretrain",
            }

        gate_results: dict[str, object] = {
            "source_gate": {"status": "passed", "source_count": len(source_rows)},
            "rights_gate": {"status": "passed"},
            "pii_gate": {"status": "passed"},
            "exact_duplicate_gate": {"status": "passed"},
            "normalized_dedup_gate": {"status": "passed"},
            "document_review_gate": {"status": "passed"},
            "decontamination": decontamination_result,
        }
        frozen_at = datetime.now(timezone.utc)
        frozen_at_text = frozen_at.isoformat().replace("+00:00", "Z")
        manifest_sources = [self._manifest_source(source) for source in source_rows]
        manifest_bytes = build_release_manifest(
            dict(release),
            manifest_sources,
            gate_results,
            frozen_at_text,
        )
        stored_manifest = self.store.ingest_bytes(manifest_bytes)

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                locked_release = connection.execute(
                    "SELECT status FROM releases WHERE id = %s FOR UPDATE",
                    (release_id,),
                ).fetchone()
                if locked_release is None or locked_release["status"] != "draft":
                    raise ReleaseGateError(
                        "Release changed before freeze commit",
                        {"freeze": {"status": "blocked", "reason": "release_changed"}},
                    )
                connection.execute(
                    """
                    SELECT source.id
                    FROM release_sources AS release_source
                    JOIN sources AS source ON source.id = release_source.source_id
                    WHERE release_source.release_id = %s
                    ORDER BY source.id
                    FOR SHARE OF source
                    """,
                    (release_id,),
                ).fetchall()
                validity = connection.execute(
                    """
                    SELECT count(*) AS source_count, count(*) FILTER (WHERE
                        source.object_sha256 IS DISTINCT FROM release_source.source_sha256 OR
                        source.version <> release_source.source_version OR
                        source.approval_status <> 'approved_source' OR
                        source.rights_status <> 'cleared' OR
                        source.license_evidence_ref IS NULL OR
                        source.pii_status <> 'clear' OR
                        source.duplicate_status <> 'unique' OR
                        source.normalized_dedup_status <> 'unique' OR
                        source.document_sampling_status <> 'sampled' OR
                        source.sampled_document_count <= 0 OR
                        source.reviewed_document_count <> source.sampled_document_count OR
                        source.approved_document_count <> source.sampled_document_count OR
                        source.flagged_document_count > 0
                    ) AS invalid_count
                    FROM release_sources AS release_source
                    JOIN sources AS source ON source.id = release_source.source_id
                    WHERE release_source.release_id = %s
                    """,
                    (release_id,),
                ).fetchone()
                if (
                    validity is None
                    or int(validity["source_count"]) != len(source_rows)
                    or int(validity["invalid_count"]) > 0
                ):
                    raise ReleaseGateError(
                        "Release sources changed before freeze commit",
                        {"source_gate": {"status": "blocked", "reason": "source_changed"}},
                    )

                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, 'application/vnd.derlem.release-manifest+json')
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (stored_manifest.sha256, stored_manifest.storage_key, stored_manifest.byte_size),
                )
                updated = connection.execute(
                    """
                    UPDATE releases
                    SET status = 'frozen', manifest_object_sha256 = %s,
                        manifest_sha256 = %s, gate_results = %s::jsonb,
                        frozen_by = %s, frozen_at = %s
                    WHERE id = %s AND status = 'draft'
                    """,
                    (
                        stored_manifest.sha256,
                        stored_manifest.sha256,
                        json.dumps(gate_results, ensure_ascii=False),
                        requested_by,
                        frozen_at,
                        release_id,
                    ),
                )
                if updated.rowcount != 1:
                    raise ReleaseGateError(
                        "Release changed before freeze",
                        {"freeze": {"status": "blocked", "reason": "release_changed"}},
                    )
                connection.execute(
                    """
                    INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                    VALUES (
                        'system', 'release.frozen', 'release', %s,
                        jsonb_build_object(
                            'job_id', %s::text,
                            'manifest_sha256', %s::text,
                            'source_count', %s::integer,
                            'gate_results', %s::jsonb
                        )
                    )
                    """,
                    (
                        release_id,
                        str(job.id),
                        stored_manifest.sha256,
                        len(source_rows),
                        json.dumps(gate_results, ensure_ascii=False),
                    ),
                )
                connection.execute(
                    """
                    UPDATE background_jobs
                    SET status = 'succeeded',
                        result = jsonb_build_object(
                            'release_id', %s::text,
                            'manifest_sha256', %s::text,
                            'source_count', %s::integer,
                            'gate_results', %s::jsonb
                        ),
                        completed_at = now(), updated_at = now()
                    WHERE id = %s AND status = 'running'
                    """,
                    (
                        release_id,
                        stored_manifest.sha256,
                        len(source_rows),
                        json.dumps(gate_results, ensure_ascii=False),
                        job.id,
                    ),
                )
        return stored_manifest.sha256

    def _export_release(self, job: Job) -> str:
        release_id = str(job.payload.get("release_id", "")).strip()
        export_id = str(job.payload.get("export_id", "")).strip()
        export_format = str(job.payload.get("format", "")).strip().lower()
        if not release_id or not export_id or export_format not in {"jsonl", "txt"}:
            raise ReleaseGateError(
                "export_release requires release_id, export_id and a supported format",
                {"export": {"status": "blocked", "reason": "invalid_job_payload"}},
            )

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            release = connection.execute(
                """
                SELECT id::text, name, version, content_purpose, status,
                    manifest_sha256, frozen_at
                FROM releases
                WHERE id = %s
                """,
                (release_id,),
            ).fetchone()
            export = connection.execute(
                """
                SELECT id::text, status, format
                FROM release_exports
                WHERE id = %s AND release_id = %s
                """,
                (export_id, release_id),
            ).fetchone()
            source_rows = connection.execute(
                """
                SELECT release_source.source_id::text, release_source.source_sha256,
                    release_source.source_name, release_source.license,
                    release_source.language, release_source.domain,
                    object.storage_key
                FROM release_sources AS release_source
                JOIN storage_objects AS object ON object.sha256 = release_source.source_sha256
                WHERE release_source.release_id = %s
                ORDER BY release_source.source_id
                """,
                (release_id,),
            ).fetchall()
            if (
                release is None
                or release["status"] != "frozen"
                or export is None
                or export["format"] != export_format
                or export["status"] not in {"queued", "building"}
            ):
                raise ReleaseGateError(
                    "Release export is no longer eligible",
                    {"export": {"status": "blocked", "reason": "export_not_eligible"}},
                )
            connection.execute(
                """
                UPDATE release_exports
                SET status = 'building', last_error = NULL
                WHERE id = %s AND status IN ('queued', 'building')
                """,
                (export_id,),
            )
            connection.commit()

        export_sources: list[dict[str, object]] = []
        for source in source_rows:
            item = dict(source)
            item["path"] = self._stored_object_path(str(source["storage_key"]))
            export_sources.append(item)

        temp_descriptor, temp_name = tempfile.mkstemp(
            prefix=f"release-export-{export_format}-",
            dir=self.store.temp_root,
        )
        os.close(temp_descriptor)
        temp_path = Path(temp_name)
        try:
            with psycopg.connect(self.config.database_url) as progress_connection:
                def update_progress(progress: dict[str, int]) -> None:
                    progress_connection.execute(
                        """
                        UPDATE background_jobs
                        SET result = jsonb_build_object(
                            'phase', 'building',
                            'release_id', %s::text,
                            'export_id', %s::text,
                            'format', %s::text,
                            'progress', %s::jsonb
                        ), updated_at = now()
                        WHERE id = %s AND status = 'running'
                        """,
                        (
                            release_id,
                            export_id,
                            export_format,
                            json.dumps(progress, ensure_ascii=False),
                            job.id,
                        ),
                    )
                    progress_connection.commit()

                result = build_release_export(
                    dict(release),
                    export_sources,
                    export_format,
                    temp_path,
                    max_document_bytes=self.config.max_document_bytes,
                    progress_callback=update_progress,
                )
            stored_export = self.store.ingest_file(temp_path)
            if stored_export.sha256 != result.sha256 or stored_export.byte_size != result.byte_size:
                raise RuntimeError("Export checksum changed while publishing")
            manifest_bytes = build_export_manifest(dict(release), export_sources, result)
            stored_manifest = self.store.ingest_bytes(manifest_bytes)
        finally:
            temp_path.unlink(missing_ok=True)

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                locked_export = connection.execute(
                    """
                    SELECT status
                    FROM release_exports
                    WHERE id = %s AND release_id = %s
                    FOR UPDATE
                    """,
                    (export_id, release_id),
                ).fetchone()
                if locked_export is None or locked_export["status"] != "building":
                    raise ReleaseGateError(
                        "Release export changed before publish",
                        {"export": {"status": "blocked", "reason": "export_changed"}},
                    )
                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (
                        stored_export.sha256,
                        stored_export.storage_key,
                        stored_export.byte_size,
                        result.media_type,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, 'application/vnd.derlem.export-manifest+json')
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (
                        stored_manifest.sha256,
                        stored_manifest.storage_key,
                        stored_manifest.byte_size,
                    ),
                )
                updated = connection.execute(
                    """
                    UPDATE release_exports
                    SET status = 'ready', object_sha256 = %s,
                        manifest_object_sha256 = %s, record_count = %s,
                        byte_size = %s, completed_at = now(), last_error = NULL
                    WHERE id = %s AND status = 'building'
                    """,
                    (
                        stored_export.sha256,
                        stored_manifest.sha256,
                        result.record_count,
                        result.byte_size,
                        export_id,
                    ),
                )
                if updated.rowcount != 1:
                    raise ReleaseGateError(
                        "Release export changed before commit",
                        {"export": {"status": "blocked", "reason": "export_changed"}},
                    )
                connection.execute(
                    """
                    INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                    VALUES (
                        'system', 'release.export_ready', 'release', %s,
                        jsonb_build_object(
                            'job_id', %s::text,
                            'export_id', %s::text,
                            'format', %s::text,
                            'object_sha256', %s::text,
                            'manifest_object_sha256', %s::text,
                            'record_count', %s::bigint,
                            'byte_size', %s::bigint
                        )
                    )
                    """,
                    (
                        release_id,
                        str(job.id),
                        export_id,
                        export_format,
                        stored_export.sha256,
                        stored_manifest.sha256,
                        result.record_count,
                        result.byte_size,
                    ),
                )
                connection.execute(
                    """
                    UPDATE background_jobs
                    SET status = 'succeeded',
                        result = jsonb_build_object(
                            'phase', 'ready',
                            'release_id', %s::text,
                            'export_id', %s::text,
                            'format', %s::text,
                            'object_sha256', %s::text,
                            'manifest_object_sha256', %s::text,
                            'record_count', %s::bigint,
                            'byte_size', %s::bigint
                        ),
                        completed_at = now(), updated_at = now()
                    WHERE id = %s AND status = 'running'
                    """,
                    (
                        release_id,
                        export_id,
                        export_format,
                        stored_export.sha256,
                        stored_manifest.sha256,
                        result.record_count,
                        result.byte_size,
                        job.id,
                    ),
                )
        return stored_export.sha256

    def _stored_object_path(self, storage_key: str) -> Path:
        path = (self.config.storage_root / storage_key).resolve(strict=True)
        path.relative_to(self.config.storage_root)
        return path

    @staticmethod
    def _release_source_is_current(source: dict[str, object]) -> bool:
        return bool(
            str(source["current_sha256"]) == str(source["source_sha256"])
            and int(source["current_version"]) == int(source["source_version"])
            and source["approval_status"] == "approved_source"
            and source["current_rights_status"] == "cleared"
            and source["license_evidence_ref"]
            and source["pii_status"] == "clear"
            and source["duplicate_status"] == "unique"
            and source["normalized_dedup_status"] == "unique"
            and source["document_sampling_status"] == "sampled"
            and int(source["sampled_document_count"]) > 0
            and int(source["reviewed_document_count"]) == int(source["sampled_document_count"])
            and int(source["approved_document_count"]) == int(source["sampled_document_count"])
            and int(source["flagged_document_count"]) == 0
        )

    @staticmethod
    def _manifest_source(source: dict[str, object]) -> dict[str, object]:
        return {
            "source_id": str(source["source_id"]),
            "source_sha256": str(source["source_sha256"]),
            "source_version": int(source["source_version"]),
            "name": str(source["source_name"]),
            "source_type": str(source["source_type"]),
            "license": str(source["license"]),
            "rights_status": str(source["rights_status"]),
            "language": str(source["language"]),
            "domain": str(source["domain"]),
            "lineage_ref": str(source["lineage_ref"]),
            "byte_size": int(source["byte_size"]) if source["byte_size"] is not None else None,
            "line_count": int(source["line_count"]) if source["line_count"] is not None else None,
            "media_type": str(source["media_type"]) if source["media_type"] is not None else None,
        }

    def _fail_or_retry(
        self,
        connection: psycopg.Connection,
        job: Job,
        error: Exception,
        *,
        permanent: bool = False,
    ) -> None:
        next_status = "failed" if permanent or job.attempts >= job.max_attempts else "queued"
        retry_delay = min(300, 5 * (2 ** max(0, job.attempts - 1)))
        connection.execute(
            """
            UPDATE background_jobs
            SET status = %s,
                available_at = CASE WHEN %s = 'queued' THEN now() + (%s * interval '1 second') ELSE available_at END,
                locked_at = NULL,
                locked_by = NULL,
                last_error = %s,
                completed_at = CASE WHEN %s = 'failed' THEN now() ELSE NULL END,
                updated_at = now()
            WHERE id = %s AND status = 'running'
            """,
            (next_status, next_status, retry_delay, str(error)[:4000], next_status, job.id),
        )
        if next_status == "failed" and job.job_type == "sample_documents":
            connection.execute(
                """
                UPDATE sources
                SET document_sampling_status = 'failed'
                WHERE id = %s AND document_sampling_status = 'not_sampled'
                """,
                (str(job.payload.get("source_id", "")),),
            )
        if next_status == "failed" and job.job_type == "index_document_fingerprints":
            connection.execute(
                """
                UPDATE sources
                SET normalized_dedup_status = 'failed'
                WHERE id = %s AND normalized_dedup_status = 'not_checked'
                """,
                (str(job.payload.get("source_id", "")),),
            )
        if next_status == "failed" and job.job_type == "freeze_release":
            release_id = str(job.payload.get("release_id", ""))
            gate_results = (
                error.gate_results
                if isinstance(error, ReleaseGateError)
                else {"freeze": {"status": "failed", "reason": "worker_error"}}
            )
            connection.execute(
                """
                UPDATE releases
                SET gate_results = %s::jsonb
                WHERE id = %s AND status = 'draft'
                """,
                (json.dumps(gate_results, ensure_ascii=False), release_id),
            )
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES (
                    'system', 'release.freeze_blocked', 'release', %s,
                    jsonb_build_object(
                        'job_id', %s::text,
                        'error', %s::text,
                        'gate_results', %s::jsonb
                    )
                )
                """,
                (
                    release_id,
                    str(job.id),
                    str(error)[:4000],
                    json.dumps(gate_results, ensure_ascii=False),
                ),
            )
        if next_status == "failed" and job.job_type == "export_release":
            export_id = str(job.payload.get("export_id", ""))
            connection.execute(
                """
                UPDATE release_exports
                SET status = 'failed', last_error = %s, completed_at = now()
                WHERE id = %s AND status IN ('queued', 'building')
                """,
                (str(error)[:4000], export_id),
            )
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES (
                    'system', 'release.export_failed', 'release', %s,
                    jsonb_build_object(
                        'job_id', %s::text,
                        'export_id', %s::text,
                        'format', %s::text,
                        'error', %s::text
                    )
                )
                """,
                (
                    str(job.payload.get("release_id", "")),
                    str(job.id),
                    export_id,
                    str(job.payload.get("format", "")),
                    str(error)[:4000],
                ),
            )
        connection.commit()
