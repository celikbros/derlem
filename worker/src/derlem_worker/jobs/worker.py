from __future__ import annotations

import os
import socket
import time
import traceback
import psycopg
from psycopg.rows import dict_row
from derlem_worker.config import Config
from derlem_worker.pii import PIIReport, PIIScanner
from derlem_worker.releases import (
    ReleaseGateError,
    build_export_manifest,
    build_mixture_report,
    build_release_export,
    build_release_manifest,
    exact_decontamination,
)
from derlem_worker.storage import ContentAddressedStore, IngestOutcome, StoredObject
from derlem_worker.jobs.queue import LOGGER
from derlem_worker.jobs.gate_jobs import GateJobsMixin
from derlem_worker.jobs.ingest_jobs import IngestJobsMixin
from derlem_worker.jobs.queue import QueueMixin
from derlem_worker.jobs.release_jobs import ReleaseJobsMixin
from derlem_worker.jobs.sample_jobs import SampleJobsMixin


class Worker(QueueMixin, IngestJobsMixin, GateJobsMixin, SampleJobsMixin, ReleaseJobsMixin):
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
                ingest_path, extraction, converted_path = self._maybe_extract(job, ingest_path)
                with psycopg.connect(self.config.database_url) as progress_connection:
                    outcome = self.store.ingest_file_resumable(
                        ingest_path,
                        checkpoint_id=job.id,
                        progress_callback=lambda progress: self._write_job_progress(
                            progress_connection,
                            job,
                            (
                                "validating_checkpoint"
                                if "checkpoint_bytes_validated" in progress
                                else "ingesting"
                            ),
                            progress,
                        ),
                    )
                with psycopg.connect(self.config.database_url) as connection:
                    self._complete_ingest(connection, job, outcome, extraction=extraction)
                self._discard_ingest_checkpoint(job, outcome.stored)
                if converted_path is not None:
                    converted_path.unlink(missing_ok=True)
                if job.job_type == "ingest_staged_file":
                    Path(str(job.payload.get("staged_path", ""))).unlink(missing_ok=True)
                LOGGER.info(
                    "job_succeeded job_id=%s sha256=%s resumed_from_bytes=%s",
                    job.id,
                    outcome.stored.sha256,
                    outcome.resumed_from_bytes,
                )
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
            elif job.job_type in {"sample_documents", "resample_documents"}:
                object_sha256, report, stored_samples = self._sample_documents(job)
                with psycopg.connect(self.config.database_url) as connection:
                    self._complete_document_sampling(
                        connection,
                        job,
                        object_sha256,
                        report,
                        stored_samples,
                        resample=job.job_type == "resample_documents",
                    )
                LOGGER.info(
                    "job_succeeded job_id=%s job_type=%s sampled=%s total_documents=%s",
                    job.id,
                    job.job_type,
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
