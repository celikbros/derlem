from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
import psycopg
from derlem_worker.extraction import convert_file, media_type_for, needs_extraction
from derlem_worker.storage import ContentAddressedStore, IngestOutcome, StoredObject
from derlem_worker.jobs.queue import Job


class IngestJobsMixin:
    def _maybe_extract(
        self, job: Job, ingest_path: Path
    ) -> tuple[Path, dict | None, Path | None]:
        """PDF/DOCX yüklemeleri kanonik satır-belge TXT'ye çevirir.

        Ham ikili, lineage kanıtı olarak içerik adresli depoya alınır;
        dönüşen metin normal ingest zincirine girer. Metin dosyaları
        olduğu gibi geçer.
        """
        candidate = str(job.payload.get("original_filename") or "") or ingest_path.name
        if not needs_extraction(candidate):
            return ingest_path, None, None
        suffix = Path(candidate).suffix.lower()
        raw = self.store.ingest_raw_file(ingest_path)
        descriptor, converted_name = tempfile.mkstemp(
            dir=str(self.config.staging_root), suffix=".extracted.txt"
        )
        os.close(descriptor)
        converted_path = Path(converted_name)
        report = convert_file(ingest_path, converted_path, suffix=suffix)
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
            resolved = Path(staged_path).resolve(strict=True)
            resolved.relative_to(self.config.staging_root)
            return resolved
        local_path = str(job.payload.get("local_path", "")).strip()
        if not local_path:
            raise ValueError("ingest_local_file requires local_path")
        return Path(local_path).resolve(strict=True)

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
                            "resumed_from_bytes": outcome.resumed_from_bytes,
                            "checkpoint_revalidated_bytes": outcome.checkpoint_revalidated_bytes,
                            "checkpoint_reset": outcome.checkpoint_reset,
                            "extraction": extraction,
                        }
                    ),
                    job.id,
                ),
            )
