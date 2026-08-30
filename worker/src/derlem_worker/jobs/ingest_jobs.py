from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import asdict
from pathlib import Path
import psycopg
from derlem_worker.extraction import (
    ExtractionError,
    ExtractionLimits,
    convert_file,
    media_type_for,
    needs_extraction,
)
from derlem_worker.storage import ContentAddressedStore, IngestOutcome, StoredObject
from derlem_worker.jobs.queue import Job, JobLeaseLost


def _resolve_regular_file_under_root(path_value: str, root: Path, field_name: str) -> Path:
    candidate_input = Path(path_value)
    if not candidate_input.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")

    try:
        root_resolved = root.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"Configured root is unavailable: {root}") from error
    if not root_resolved.is_dir():
        raise ValueError(f"Configured root is not a directory: {root_resolved}")

    candidate = Path(os.path.abspath(candidate_input))
    try:
        relative = candidate.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(f"{field_name} must stay under {root_resolved}") from error

    current = root_resolved
    for index, component in enumerate(relative.parts):
        current /= component
        try:
            mode = current.lstat().st_mode
        except OSError as error:
            raise ValueError(f"{field_name} is unavailable: {current}") from error
        if stat.S_ISLNK(mode):
            raise ValueError(f"{field_name} cannot contain symbolic links")
        is_last = index == len(relative.parts) - 1
        if not is_last and not stat.S_ISDIR(mode):
            raise ValueError(f"{field_name} contains a non-directory component")
        if is_last and not stat.S_ISREG(mode):
            raise ValueError(f"{field_name} must reference a regular file")

    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as error:
        raise ValueError(f"{field_name} resolves outside its configured root") from error
    if not resolved.is_file():
        raise ValueError(f"{field_name} must reference a regular file")
    return resolved


def _same_file_version(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _same_file_content(left: os.stat_result, right: os.stat_result) -> bool:
    """Compare identity/content while allowing hard-link creation to change ctime."""
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_size,
        left.st_mtime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_size,
        right.st_mtime_ns,
    )


class IngestJobsMixin:
    def _validate_ingest_provenance(
        self,
        connection: psycopg.Connection,
        job: Job,
        *,
        source_id: str,
        data_origin: str,
        production_run_id: str | None,
        ingested_sha256: str,
        ingested_byte_size: int,
    ) -> None:
        """Fail closed when a source is bound to production provenance.

        Ordinary uploads must never inherit a production run. The sole current
        run-bound ingest path is the exact child job atomically published by a
        successful model-distillation parent. Parent result -> child id makes a
        copied or replayed payload insufficient evidence.
        """
        payload_run_id = str(job.payload.get("production_run_id") or "").strip()
        parent_job_id = str(job.payload.get("distillation_job_id") or "").strip()
        output_sha256 = str(
            job.payload.get("distillation_output_sha256") or ""
        ).strip()
        raw_output_byte_size = job.payload.get("distillation_output_byte_size")
        has_handoff_fields = bool(
            payload_run_id
            or parent_job_id
            or output_sha256
            or raw_output_byte_size is not None
        )
        run_bound_source = production_run_id is not None or data_origin in {
            "model",
            "hybrid",
        }

        if not run_bound_source:
            if has_handoff_fields:
                raise RuntimeError("Ingest production provenance is unexpected")
            return

        try:
            output_byte_size = int(raw_output_byte_size)
        except (TypeError, ValueError):
            output_byte_size = -1

        if (
            data_origin != "model"
            or production_run_id is None
            or job.job_type != "ingest_staged_file"
            or not payload_run_id
            or not parent_job_id
            or payload_run_id != production_run_id
            or len(output_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in output_sha256
            )
            or output_byte_size < 0
        ):
            raise RuntimeError("Ingest production provenance mismatch")

        evidence = connection.execute(
            """
            SELECT parent.id
            FROM background_jobs AS child
            JOIN background_jobs AS parent
              ON parent.id::text = child.payload->>'distillation_job_id'
            JOIN production_runs AS run
              ON run.id::text = child.payload->>'production_run_id'
            JOIN production_run_completions AS completion
              ON completion.production_run_id = run.id
             AND completion.job_id = parent.id
            JOIN storage_objects AS manifest
              ON btrim(manifest.sha256::text) = parent.result->>'manifest_sha256'
            WHERE child.id = %s
              AND child.job_type = 'ingest_staged_file'
              AND child.status = 'running'
              AND child.locked_by IS NOT DISTINCT FROM %s
              AND child.attempts = %s
              AND child.payload->>'source_id' = %s
              AND child.payload->>'production_run_id' = %s
              AND child.payload->>'distillation_job_id' = %s
              AND parent.id::text = %s
              AND parent.job_type = 'distill_source'
              AND parent.status = 'succeeded'
              AND parent.created_by IS NOT DISTINCT FROM child.created_by
              AND parent.payload->>'source_id' = %s
              AND parent.payload->>'production_run_id' = %s
              AND parent.result->>'production_run_id' = %s
              AND parent.result->>'ingest_job_id' = child.id::text
              AND parent.result->>'manifest_sha256' ~ '^[0-9a-f]{64}$'
              AND child.payload->>'distillation_output_sha256' = %s
              AND child.payload->>'distillation_output_byte_size' = %s
              AND parent.result->>'output_sha256' = %s
              AND parent.result->>'output_sha256' =
                    child.payload->>'distillation_output_sha256'
              AND parent.result->>'output_byte_size' = %s
              AND parent.result->>'output_byte_size' =
                    child.payload->>'distillation_output_byte_size'
              AND btrim(completion.output_manifest_sha256::text) =
                    parent.result->>'manifest_sha256'
              AND btrim(completion.output_sha256::text) =
                    parent.result->>'output_sha256'
              AND completion.output_byte_size::text =
                    parent.result->>'output_byte_size'
              AND completion.output_record_count::text =
                    parent.result->>'document_count'
              AND completion.completed_at = parent.completed_at
              AND run.run_kind = 'model_generation'
              AND run.origin_kind = 'model'
            """,
            (
                job.id,
                job.lease_owner,
                job.attempts,
                source_id,
                production_run_id,
                parent_job_id,
                parent_job_id,
                source_id,
                production_run_id,
                production_run_id,
                output_sha256,
                str(output_byte_size),
                output_sha256,
                str(output_byte_size),
            ),
        ).fetchone()
        if evidence is None:
            raise RuntimeError("Ingest production provenance handoff is invalid or stale")
        if (ingested_sha256, ingested_byte_size) != (
            output_sha256,
            output_byte_size,
        ):
            raise RuntimeError("Distillation output artifact mismatch")

    def _snapshot_ingest_source(self, job: Job, source_path: Path) -> Path:
        """Pin or copy one source into private attempt-local staging.

        Text inputs use an atomic hard link when the roots share a filesystem,
        preserving resumable ingest without doubling very large files. Inputs
        that need extraction are copied because parsing and raw lineage hashing
        must consume exactly the same stable bytes. Cross-device text inputs
        fall back to a capacity-checked copy.
        """
        suffix = source_path.suffix.lower()
        if suffix not in {".pdf", ".docx", ".txt", ".json", ".jsonl"}:
            suffix = ".source"
        candidate = (
            str(job.payload.get("original_filename") or "") or source_path.name
        )
        if not needs_extraction(candidate) and os.name != "nt":
            try:
                return self._hardlink_ingest_source(job, source_path, suffix=suffix)
            except (NotImplementedError, OSError):
                # Cross-device links and platforms without link support still
                # get a private copy, subject to disk headroom.
                pass

        return self._copy_ingest_source(
            job,
            source_path,
            suffix=suffix,
            extraction_input=needs_extraction(candidate),
        )

    def _hardlink_ingest_source(
        self, job: Job, source_path: Path, *, suffix: str
    ) -> Path:
        descriptor, pinned_path = self._new_attempt_artifact(
            job, suffix=f".snapshot{suffix}"
        )
        os.close(descriptor)
        pinned_path.unlink()
        try:
            before = source_path.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Ingest source must remain a regular file")
            os.link(source_path, pinned_path, follow_symlinks=False)
            linked = pinned_path.lstat()
            after_path = source_path.lstat()
            if not stat.S_ISREG(linked.st_mode) or not _same_file_content(
                before, linked
            ) or not _same_file_version(linked, after_path):
                raise ValueError("Ingest source changed while it was being pinned")
            return pinned_path
        except Exception:
            pinned_path.unlink(missing_ok=True)
            raise

    def _copy_ingest_source(
        self,
        job: Job,
        source_path: Path,
        *,
        suffix: str,
        extraction_input: bool,
    ) -> Path:
        target_descriptor, snapshot_path = self._new_attempt_artifact(
            job, suffix=f".snapshot{suffix}"
        )
        source_descriptor: int | None = None
        target_open = True
        try:
            before = source_path.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Ingest source must remain a regular file")

            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            source_descriptor = os.open(source_path, flags)
            opened = os.fstat(source_descriptor)
            if not stat.S_ISREG(opened.st_mode) or not _same_file_content(before, opened):
                raise ValueError("Ingest source changed between validation and open")
            if (
                extraction_input
                and opened.st_size > self.config.extraction_max_source_bytes
            ):
                raise ExtractionError(
                    "Belge extraction kaynak boyutu sınırını aşıyor "
                    f"({opened.st_size} > "
                    f"{self.config.extraction_max_source_bytes} byte)."
                )
            free_bytes = shutil.disk_usage(self.config.staging_root).free
            reserve_bytes = min(64 * 1024 * 1024, max(1024 * 1024, free_bytes // 20))
            if opened.st_size + reserve_bytes > free_bytes:
                raise RuntimeError(
                    "Insufficient staging capacity for a secure ingest snapshot"
                )

            with os.fdopen(source_descriptor, "rb") as source:
                source_descriptor = None
                with os.fdopen(target_descriptor, "wb") as target:
                    target_open = False
                    while chunk := source.read(4 * 1024 * 1024):
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
                    after_handle = os.fstat(source.fileno())

            try:
                after_path = source_path.lstat()
            except OSError as error:
                raise ValueError("Ingest source changed while snapshotting") from error
            if not _same_file_version(opened, after_handle) or not _same_file_version(
                before, after_path
            ):
                raise ValueError("Ingest source changed while snapshotting")
            return snapshot_path
        except Exception:
            if source_descriptor is not None:
                os.close(source_descriptor)
                source_descriptor = None
            if target_open:
                os.close(target_descriptor)
                target_open = False
            snapshot_path.unlink(missing_ok=True)
            raise
        finally:
            if source_descriptor is not None:
                os.close(source_descriptor)
            if target_open:
                os.close(target_descriptor)

    def _maybe_extract(
        self,
        job: Job,
        ingest_path: Path,
        *,
        source_name: str | None = None,
    ) -> tuple[Path, dict | None, Path | None]:
        """PDF/DOCX yüklemeleri kanonik satır-belge TXT'ye çevirir.

        Ham ikili, lineage kanıtı olarak içerik adresli depoya alınır;
        dönüşen metin normal ingest zincirine girer. Metin dosyaları
        olduğu gibi geçer.
        """
        candidate = (
            str(job.payload.get("original_filename") or "")
            or source_name
            or ingest_path.name
        )
        if not needs_extraction(candidate):
            return ingest_path, None, None
        suffix = Path(candidate).suffix.lower()
        descriptor, converted_path = self._new_attempt_artifact(
            job, suffix=".extracted.txt"
        )
        os.close(descriptor)
        try:
            # Parse before publishing the raw binary. Rejected/corrupt input
            # must not leave an unreferenced object or partial derived file.
            report = convert_file(
                ingest_path,
                converted_path,
                suffix=suffix,
                limits=ExtractionLimits(
                    max_source_bytes=self.config.extraction_max_source_bytes,
                    max_docx_entries=self.config.extraction_max_docx_entries,
                    max_docx_uncompressed_bytes=(
                        self.config.extraction_max_docx_uncompressed_bytes
                    ),
                    max_pdf_pages=self.config.extraction_max_pdf_pages,
                    max_output_chars=self.config.extraction_max_output_chars,
                ),
            )
        except ExtractionError:
            converted_path.unlink(missing_ok=True)
            raise
        except Exception as error:
            converted_path.unlink(missing_ok=True)
            raise ExtractionError(
                "Belge ayrıştırılamadı; dosya bozuk veya desteklenmeyen yapıdadır."
            ) from error
        try:
            raw = self.store.ingest_raw_file(ingest_path)
        except Exception:
            converted_path.unlink(missing_ok=True)
            raise
        extraction = {
            **asdict(report),
            "original_filename": candidate,
            "raw_sha256": raw.sha256,
            "raw_byte_size": raw.byte_size,
            "raw_storage_key": raw.storage_key,
            "raw_media_type": media_type_for(candidate),
        }
        return converted_path, extraction, converted_path

    def _ingest_path(self, job: Job) -> Path:
        source_id = str(job.payload.get("source_id", "")).strip()
        if not source_id:
            raise ValueError(f"{job.job_type} requires source_id")
        if job.job_type == "ingest_staged_file":
            staged_path = str(job.payload.get("staged_path", "")).strip()
            if not staged_path:
                raise ValueError("ingest_staged_file requires staged_path")
            return _resolve_regular_file_under_root(
                staged_path, self.config.staging_root, "staged_path"
            )
        local_path = str(job.payload.get("local_path", "")).strip()
        if not local_path:
            raise ValueError("ingest_local_file requires local_path")
        return _resolve_regular_file_under_root(
            local_path, self.config.import_root, "local_path"
        )

    def _complete_ingest(
        self,
        connection: psycopg.Connection,
        job: Job,
        outcome: IngestOutcome,
        extraction: dict | None = None,
    ) -> None:
        stored = outcome.stored
        source_id = str(job.payload["source_id"])
        with connection.transaction():
            declared = connection.execute(
                """
                SELECT declared_sha256, declared_byte_size, declared_line_count,
                    data_origin, production_run_id::text
                FROM sources
                WHERE id = %s
                FOR UPDATE
                """,
                (source_id,),
            ).fetchone()
            if declared is None:
                raise RuntimeError("Source was not found")
            (
                declared_sha256,
                declared_byte_size,
                declared_line_count,
                data_origin,
                production_run_id,
            ) = declared
            self._validate_ingest_provenance(
                connection,
                job,
                source_id=source_id,
                data_origin=str(data_origin),
                production_run_id=(
                    str(production_run_id) if production_run_id is not None else None
                ),
                ingested_sha256=stored.sha256,
                ingested_byte_size=stored.byte_size,
            )
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
            if extraction is not None:
                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (
                        extraction["raw_sha256"],
                        extraction["raw_storage_key"],
                        extraction["raw_byte_size"],
                        extraction["raw_media_type"],
                    ),
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
                    jsonb_build_object(
                        'job_id', %s::text,
                        'sha256', %s::text,
                        'byte_size', %s::bigint,
                        'resumed_from_bytes', %s::bigint,
                        'checkpoint_revalidated_bytes', %s::bigint,
                        'checkpoint_reset', %s::boolean,
                        'extraction_method', %s::text,
                        'raw_sha256', %s::text
                    )
                )
                """,
                (
                    source_id,
                    str(job.id),
                    stored.sha256,
                    stored.byte_size,
                    outcome.resumed_from_bytes,
                    outcome.checkpoint_revalidated_bytes,
                    outcome.checkpoint_reset,
                    extraction["method"] if extraction else None,
                    extraction["raw_sha256"] if extraction else None,
                ),
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
            completed_job = connection.execute(
                """
                UPDATE background_jobs
                SET status = 'succeeded', result = %s::jsonb, completed_at = now(), updated_at = now()
                WHERE id = %s AND status = 'running'
                  AND locked_by IS NOT DISTINCT FROM %s
                  AND attempts = %s
                """,
                (
                    json.dumps(
                        {
                            "sha256": stored.sha256,
                            "byte_size": stored.byte_size,
                            "line_count": stored.line_count,
                            "detected_encoding": stored.detected_encoding,
                            "original_filename": job.payload.get("original_filename"),
                            "resumed_from_bytes": outcome.resumed_from_bytes,
                            "checkpoint_revalidated_bytes": outcome.checkpoint_revalidated_bytes,
                            "checkpoint_reset": outcome.checkpoint_reset,
                            "extraction": extraction,
                        }
                    ),
                    job.id,
                    job.lease_owner,
                    job.attempts,
                ),
            )
            if completed_job.rowcount != 1:
                raise JobLeaseLost(f"Job lease is no longer owned: {job.id}")
