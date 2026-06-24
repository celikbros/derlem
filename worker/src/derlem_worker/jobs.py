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
from derlem_worker.storage import ContentAddressedStore, StoredObject

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    id: UUID
    job_type: str
    payload: dict[str, object]
    attempts: int
    max_attempts: int


class Worker:
    def __init__(self, config: Config, worker_id: str | None = None) -> None:
        self.config = config
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.store = ContentAddressedStore(config.storage_root)
        self.pii_scanner = PIIScanner()

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
        connection.commit()
