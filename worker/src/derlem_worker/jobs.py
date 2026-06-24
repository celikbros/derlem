from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import socket
import time
import traceback
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from derlem_worker.config import Config
from derlem_worker.pii import PIIReport, PIIScanner
from derlem_worker.sampling import SampledDocument, SamplingReport, sample_line_documents
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
        total = duplicate_jobs.rowcount + sample_jobs.rowcount
        if total > 0:
            LOGGER.info(
                "maintenance_jobs_queued exact_duplicate=%s document_samples=%s",
                duplicate_jobs.rowcount,
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
            else:
                raise ValueError(f"Unsupported job type: {job.job_type}")
        except Exception as error:  # Worker boundary: failure must be persisted.
            LOGGER.error("job_failed job_id=%s error=%s", job.id, error)
            LOGGER.debug("%s", traceback.format_exc())
            with psycopg.connect(self.config.database_url) as connection:
                self._fail_or_retry(connection, job, error)
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
                SELECT source.object_sha256, source.duplicate_status, object.storage_key
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
        if row["duplicate_status"] != "unique":
            raise ValueError("Only canonical unique sources can be sampled")

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
                        WHEN document_sampling_status = 'sampled' THEN 'sampled_for_review'
                        ELSE 'auto_checked'
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
                        'sample_documents',
                        jsonb_build_object('source_id', %s::text, 'object_sha256', %s::text),
                        created_by
                    FROM sources
                    WHERE id = %s AND document_sampling_status = 'not_sampled'
                    ON CONFLICT DO NOTHING
                    """,
                    (source_id, object_sha256, source_id),
                )
        return status, duplicate_of

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
                SELECT object_sha256, duplicate_status
                FROM sources
                WHERE id = %s
                FOR UPDATE
                """,
                (source_id,),
            ).fetchone()
            if source is None or str(source[0]) != object_sha256:
                raise RuntimeError("Source object changed while completing document sampling")
            if source[1] != "unique":
                raise RuntimeError("Only canonical unique sources can be sampled")

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
                        WHEN approval_status = 'auto_checked' THEN 'sampled_for_review'
                        ELSE approval_status
                    END
                WHERE id = %s AND object_sha256 = %s
                """,
                (report.total_documents, source_id, source_id, object_sha256),
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

    def _fail_or_retry(self, connection: psycopg.Connection, job: Job, error: Exception) -> None:
        next_status = "failed" if job.attempts >= job.max_attempts else "queued"
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
        connection.commit()
