from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
from threading import Event, Thread
import tempfile
import time
from uuid import UUID
import psycopg
from derlem_worker.releases import ReleaseGateError
from derlem_worker.storage import StoredObject


LOGGER = logging.getLogger("derlem_worker.jobs")
ATTEMPT_ARTIFACT_RE = re.compile(
    r"^job-([0-9a-fA-F-]{36})-attempt-([1-9][0-9]*)-"
)
CHECKPOINT_ARTIFACT_RE = re.compile(
    r"^ingest-([0-9a-fA-F-]{36})-attempt-([1-9][0-9]*)\.part$"
)
LEGACY_CHECKPOINT_ARTIFACT_RE = re.compile(
    r"^ingest-([0-9a-fA-F-]{36})\.part$"
)


@dataclass(frozen=True)
class Job:
    id: UUID
    job_type: str
    payload: dict[str, object]
    attempts: int
    max_attempts: int
    lease_owner: str | None = None


class JobLeaseLost(RuntimeError):
    """Raised when a worker no longer owns the claimed attempt."""


class JobLeaseExpired(RuntimeError):
    """Persisted when a running worker stops renewing its lease."""


class QueueMixin:
    def _claim(self, connection: psycopg.Connection) -> Job | None:
        self._sweep_orphan_attempt_artifacts(connection)
        self._sweep_orphan_ingest_checkpoints(connection)
        self._recover_stale_jobs(connection)
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
            RETURNING job.id, job.job_type, job.payload, job.attempts, job.max_attempts,
                job.locked_by
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
            lease_owner=row["locked_by"],
        )

    def _write_job_progress(
        self,
        connection: psycopg.Connection,
        job: Job,
        phase: str,
        progress: dict[str, int],
    ) -> None:
        updated = connection.execute(
            """
            UPDATE background_jobs
            SET result = jsonb_build_object(
                    'phase', %s::text,
                    'progress', %s::jsonb
                ),
                updated_at = now()
            WHERE id = %s AND status = 'running'
              AND locked_by IS NOT DISTINCT FROM %s
              AND attempts = %s
            """,
            (
                phase,
                json.dumps(progress, ensure_ascii=False),
                job.id,
                job.lease_owner,
                job.attempts,
            ),
        )
        if updated.rowcount != 1:
            connection.rollback()
            raise JobLeaseLost(f"Job lease is no longer owned: {job.id}")
        connection.commit()

    def _recover_stale_jobs(
        self,
        connection: psycopg.Connection,
        *,
        limit: int = 100,
    ) -> int:
        recovered = 0
        for _ in range(limit):
            row = connection.execute(
                """
                SELECT id, job_type, payload, attempts, max_attempts, locked_by
                FROM background_jobs
                WHERE status = 'running'
                  AND (locked_at IS NULL OR locked_at < now() - (%s * interval '1 second'))
                ORDER BY locked_at ASC NULLS FIRST, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (self.config.lease_timeout_seconds,),
            ).fetchone()
            if row is None:
                connection.commit()
                break
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            stale_job = Job(
                id=row["id"],
                job_type=row["job_type"],
                payload=payload,
                attempts=row["attempts"],
                max_attempts=row["max_attempts"],
                lease_owner=row["locked_by"],
            )
            next_status = self._fail_or_retry(
                connection,
                stale_job,
                JobLeaseExpired(
                    f"worker lease expired (previous owner: {stale_job.lease_owner or 'unknown'})"
                ),
            )
            if next_status is not None:
                recovered += 1
                LOGGER.warning(
                    "stale_job_recovered job_id=%s previous_owner=%s next_status=%s attempts=%s",
                    stale_job.id,
                    stale_job.lease_owner,
                    next_status,
                    stale_job.attempts,
                )
        return recovered

    def _new_attempt_artifact(self, job: Job, *, suffix: str) -> tuple[int, Path]:
        """Create a private, attempt-scoped staging artifact.

        The stable prefix lets stale-lease recovery remove files left behind by
        a killed worker without touching another attempt or an uploaded source.
        """
        staging_root = self.config.staging_root.resolve()
        staging_root.mkdir(parents=True, exist_ok=True)
        prefix = f"job-{job.id}-attempt-{job.attempts}-"
        descriptor, name = tempfile.mkstemp(
            dir=str(staging_root), prefix=prefix, suffix=suffix
        )
        path = Path(name).resolve()
        path.relative_to(staging_root)
        return descriptor, path

    def _discard_attempt_artifacts(self, job: Job) -> None:
        staging_root = getattr(self.config, "staging_root", None)
        if staging_root is None:
            return
        try:
            root = Path(staging_root).resolve(strict=True)
        except OSError:
            return
        prefix = f"job-{job.id}-attempt-{job.attempts}-"
        for path in root.glob(f"{prefix}*"):
            try:
                resolved_parent = path.parent.resolve(strict=True)
                if resolved_parent != root or path.is_symlink() or not path.is_file():
                    continue
                path.unlink(missing_ok=True)
            except OSError as error:
                # Windows cannot unlink an artifact while the expired worker
                # still has it open. The old owner is nevertheless prevented
                # from publishing by the lease guards; a later sweep can retry.
                LOGGER.warning(
                    "attempt_artifact_cleanup_failed job_id=%s path=%s error=%s",
                    job.id,
                    path,
                    error,
                )

    @staticmethod
    def _remove_attempt_artifact(path: Path, *, job_id: UUID) -> None:
        """Best-effort boundary cleanup that must never terminate the worker."""
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            # In particular, Windows refuses to unlink read-only/open files.
            # The DB-aware stale artifact sweeper retries after the lease ages.
            LOGGER.warning(
                "attempt_artifact_cleanup_failed job_id=%s path=%s error=%s",
                job_id,
                path,
                error,
            )

    def _sweep_orphan_attempt_artifacts(
        self, connection: psycopg.Connection, *, limit: int = 100
    ) -> int:
        """Retry cleanup of old attempt files not owned by a live DB job."""
        staging_root = getattr(self.config, "staging_root", None)
        if staging_root is None:
            return 0
        try:
            root = Path(staging_root).resolve(strict=True)
        except OSError:
            return 0

        cutoff = time.time() - self.config.lease_timeout_seconds
        candidates: list[tuple[float, Path, UUID, int]] = []
        for path in root.glob("job-*-attempt-*-*"):
            match = ATTEMPT_ARTIFACT_RE.match(path.name)
            if match is None:
                continue
            try:
                modified_at = path.lstat().st_mtime
                job_id = UUID(match.group(1))
                attempt = int(match.group(2))
            except (OSError, ValueError):
                continue
            if modified_at <= cutoff:
                candidates.append((modified_at, path, job_id, attempt))

        removed = 0
        for _, path, job_id, attempt in sorted(candidates)[:limit]:
            reference_row = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM background_jobs AS job
                    WHERE (
                        job.id = %s
                        AND job.attempts = %s
                        AND job.status = 'running'
                    ) OR (
                        job.job_type = 'ingest_staged_file'
                        AND job.status IN ('queued', 'running')
                        AND job.payload->>'staged_path' = %s
                    )
                ) AS referenced
                """,
                (job_id, attempt, str(path)),
            ).fetchone()
            referenced = (
                reference_row["referenced"]
                if isinstance(reference_row, dict)
                else reference_row[0]
            )
            if referenced:
                continue
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError as error:
                LOGGER.warning(
                    "orphan_artifact_cleanup_failed path=%s error=%s", path, error
                )
        if removed:
            LOGGER.info("orphan_attempt_artifacts_removed count=%s", removed)
        return removed

    def _sweep_orphan_ingest_checkpoints(
        self, connection: psycopg.Connection, *, limit: int = 100
    ) -> int:
        """Remove old attempt checkpoints only after DB ownership is fenced."""
        store = getattr(self, "store", None)
        if store is None:
            return 0
        temp_root = getattr(store, "temp_root", None)
        if temp_root is None:
            return 0
        try:
            root = Path(temp_root).resolve(strict=True)
        except OSError:
            return 0

        cutoff = time.time() - self.config.lease_timeout_seconds
        candidates: list[tuple[float, Path, UUID, int | None]] = []
        for path in root.glob("ingest-*.part"):
            match = CHECKPOINT_ARTIFACT_RE.match(path.name)
            legacy_match = LEGACY_CHECKPOINT_ARTIFACT_RE.match(path.name)
            if match is None and legacy_match is None:
                continue
            try:
                modified_at = path.lstat().st_mtime
                job_id = UUID((match or legacy_match).group(1))
                attempt = int(match.group(2)) if match is not None else None
            except (OSError, ValueError):
                continue
            if modified_at <= cutoff:
                candidates.append((modified_at, path, job_id, attempt))

        removed = 0
        for _, path, job_id, attempt in sorted(candidates)[:limit]:
            if attempt is None:
                reference_row = connection.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM background_jobs
                        WHERE id = %s AND status IN ('queued', 'running')
                    ) AS referenced
                    """,
                    (job_id,),
                ).fetchone()
                checkpoint_id: UUID | str = job_id
            else:
                reference_row = connection.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM background_jobs
                        WHERE id = %s
                          AND (
                              (status = 'running' AND attempts = %s)
                              OR (
                                  status = 'queued'
                                  AND %s IN (attempts, attempts + 1)
                              )
                          )
                    ) AS referenced
                    """,
                    (job_id, attempt, attempt),
                ).fetchone()
                checkpoint_id = f"{job_id}-attempt-{attempt}"
            referenced = (
                reference_row["referenced"]
                if isinstance(reference_row, dict)
                else reference_row[0]
            )
            if referenced:
                continue
            try:
                store.discard_checkpoint(checkpoint_id)
                removed += 1
            except (OSError, RuntimeError, ValueError) as error:
                LOGGER.warning(
                    "orphan_checkpoint_cleanup_failed path=%s error=%s", path, error
                )
        if removed:
            LOGGER.info("orphan_ingest_checkpoints_removed count=%s", removed)
        return removed

    @staticmethod
    def _ingest_checkpoint_id(job: Job, *, attempt: int | None = None) -> str:
        effective_attempt = job.attempts if attempt is None else attempt
        return f"{job.id}-attempt-{effective_attempt}"

    def _assert_job_ownership(
        self,
        connection: psycopg.Connection,
        job: Job,
    ) -> None:
        owned = connection.execute(
            """
            SELECT 1
            FROM background_jobs
            WHERE id = %s AND status = 'running'
              AND locked_by IS NOT DISTINCT FROM %s
              AND attempts = %s
            FOR UPDATE
            """,
            (job.id, job.lease_owner, job.attempts),
        ).fetchone()
        if owned is None:
            raise JobLeaseLost(f"Job lease is no longer owned: {job.id}")

    def _heartbeat_job(self, job: Job) -> bool:
        with psycopg.connect(self.config.database_url) as connection:
            updated = connection.execute(
                """
                UPDATE background_jobs
                SET locked_at = now(), updated_at = now()
                WHERE id = %s AND status = 'running'
                  AND locked_by IS NOT DISTINCT FROM %s
                  AND attempts = %s
                """,
                (job.id, job.lease_owner, job.attempts),
            )
            connection.commit()
        return updated.rowcount == 1

    @contextmanager
    def _maintain_job_lease(self, job: Job) -> Iterator[Event]:
        stop = Event()
        lost = Event()

        def heartbeat_loop() -> None:
            while not stop.wait(self.config.heartbeat_interval_seconds):
                try:
                    if not self._heartbeat_job(job):
                        lost.set()
                        LOGGER.warning("job_lease_lost job_id=%s", job.id)
                        return
                except psycopg.Error as error:
                    # A transient heartbeat failure must not mutate the job. If it
                    # lasts past the timeout, recovery transfers ownership and the
                    # guarded completion path rejects this worker.
                    LOGGER.warning("job_heartbeat_failed job_id=%s error=%s", job.id, error)

        thread = Thread(
            target=heartbeat_loop,
            name=f"derlem-heartbeat-{job.id}",
            daemon=True,
        )
        thread.start()
        try:
            yield lost
        finally:
            stop.set()
            thread.join(timeout=min(5.0, self.config.heartbeat_interval_seconds))

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
    ) -> str | None:
        next_status = "failed" if permanent or job.attempts >= job.max_attempts else "queued"
        retry_delay = min(300, 5 * (2 ** max(0, job.attempts - 1)))
        updated = connection.execute(
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
              AND locked_by IS NOT DISTINCT FROM %s
              AND attempts = %s
            """,
            (
                next_status,
                next_status,
                retry_delay,
                str(error)[:4000],
                next_status,
                job.id,
                job.lease_owner,
                job.attempts,
            ),
        )
        if updated.rowcount != 1:
            connection.rollback()
            LOGGER.warning("job_state_update_rejected_lost_lease job_id=%s", job.id)
            return None
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
        self._discard_attempt_artifacts(job)
        if job.job_type in {"ingest_local_file", "ingest_staged_file"}:
            if next_status == "queued" and not isinstance(error, JobLeaseExpired):
                self._promote_ingest_checkpoint(job)
            else:
                self._discard_ingest_checkpoint(job)
        return next_status

    def _promote_ingest_checkpoint(self, job: Job) -> None:
        current = self._ingest_checkpoint_id(job)
        following = self._ingest_checkpoint_id(job, attempt=job.attempts + 1)
        try:
            promoted = self.store.promote_checkpoint(current, following)
            if promoted:
                LOGGER.info(
                    "ingest_checkpoint_promoted job_id=%s from_attempt=%s to_attempt=%s",
                    job.id,
                    job.attempts,
                    job.attempts + 1,
                )
        except (OSError, RuntimeError, ValueError) as error:
            LOGGER.warning(
                "ingest_checkpoint_promotion_failed job_id=%s error=%s",
                job.id,
                error,
            )
            # A create-only promotion can fail because the next attempt has
            # already created its own checkpoint. Never delete that active
            # attempt's file; only retire the closed source checkpoint.
            try:
                self.store.discard_checkpoint(current)
            except (OSError, RuntimeError, ValueError) as cleanup_error:
                LOGGER.warning(
                    "ingest_checkpoint_cleanup_failed job_id=%s checkpoint=%s error=%s",
                    job.id,
                    current,
                    cleanup_error,
                )

    def _discard_ingest_checkpoint(self, job: Job, stored: StoredObject | None = None) -> None:
        try:
            if stored is None:
                self.store.discard_checkpoint(self._ingest_checkpoint_id(job))
            else:
                self.store.finalize_checkpoint(
                    self._ingest_checkpoint_id(job), stored
                )
        except (OSError, RuntimeError, ValueError) as error:
            LOGGER.warning(
                "ingest_checkpoint_cleanup_failed job_id=%s error=%s",
                job.id,
                error,
            )
