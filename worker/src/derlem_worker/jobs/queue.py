from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from uuid import UUID
import psycopg
from derlem_worker.releases import (
    ReleaseGateError,
    build_export_manifest,
    build_mixture_report,
    build_release_export,
    build_release_manifest,
    exact_decontamination,
)
from derlem_worker.storage import ContentAddressedStore, IngestOutcome, StoredObject


LOGGER = logging.getLogger("derlem_worker.jobs")


@dataclass(frozen=True)
class Job:
    id: UUID
    job_type: str
    payload: dict[str, object]
    attempts: int
    max_attempts: int


class QueueMixin:
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
                result = NULL,
                last_error = NULL,
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

    @staticmethod
    def _write_job_progress(
        connection: psycopg.Connection,
        job: Job,
        phase: str,
        progress: dict[str, int],
    ) -> None:
        connection.execute(
            """
            UPDATE background_jobs
            SET result = jsonb_build_object(
                    'phase', %s::text,
                    'progress', %s::jsonb
                ),
                updated_at = now()
            WHERE id = %s AND status = 'running'
            """,
            (phase, json.dumps(progress, ensure_ascii=False), job.id),
        )
        connection.commit()

    def _stored_object_path(self, storage_key: str) -> Path:
        path = (self.config.storage_root / storage_key).resolve(strict=True)
        path.relative_to(self.config.storage_root)
        return path

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
        if next_status == "failed" and job.job_type == "resample_documents":
            source_id = str(job.payload.get("source_id", ""))
            connection.execute(
                """
                UPDATE sources
                SET document_sampling_status = 'sampled'
                WHERE id = %s AND document_sampling_status = 'resampling'
                """,
                (source_id,),
            )
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES (
                    'system', 'source.document_resample_failed', 'source', %s,
                    jsonb_build_object('job_id', %s::text, 'error', %s::text)
                )
                """,
                (source_id, str(job.id), str(error)[:4000]),
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
        if next_status == "failed" and job.job_type in {"ingest_local_file", "ingest_staged_file"}:
            self._discard_ingest_checkpoint(job)

    def _discard_ingest_checkpoint(self, job: Job, stored: StoredObject | None = None) -> None:
        try:
            if stored is None:
                self.store.discard_checkpoint(job.id)
            else:
                self.store.finalize_checkpoint(job.id, stored)
        except OSError as error:
            LOGGER.warning(
                "ingest_checkpoint_cleanup_failed job_id=%s error=%s",
                job.id,
                error,
            )
