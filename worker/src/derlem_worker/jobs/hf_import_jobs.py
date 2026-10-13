"""``import_hf_dataset`` isi (TASK-032): kaynak kaydi API'de olusur, alim burada.

Akis: yuk (payload) -> uyarlayici yolu IMPORT_ROOT ya da ADAPTERS_ROOT altinda
dogrulanir -> ``hf_import.import_hf_dataset`` (parcalar ve manifest depoya) ->
tek transaction'da: depo nesneleri (parcalar + manifest) kaydedilir, kaynagin
nesnesi = manifest, ``lineage_ref`` = manifest ozeti, ``license`` = kartin lisans
kimligi, durum ``raw_ingested``; PII ve birebir tekrar kapilari kuyruga girer
(sonrakiler bakim taramasiyla, bugunku zincirle ayni).

Calisma dizini ``IMPORT_ROOT/hf-import/<source_id>``: ayni kaynagin yeniden
denemesi defterden devam eder.
"""

from __future__ import annotations

import json
from pathlib import Path
import time

import psycopg

from derlem_worker.hf_import import ImportResult, import_hf_dataset
from derlem_worker.import_manifest import IMPORT_MANIFEST_MEDIA_TYPE, SHARD_MEDIA_TYPE, storage_key_for
from derlem_worker.jobs.ingest_jobs import _resolve_regular_file_under_root
from derlem_worker.jobs.queue import Job, JobLeaseLost

HF_SOURCE_TYPE = "hf_dataset"
PENDING_LICENSE = "hf-card:pending"


def resolve_adapter_path(value: str, roots: list[Path]) -> Path:
    """Uyarlayici yolu: mutlak, roots'tan birinin altinda, sembolik bag yok, .yaml/.yml."""
    if not value.lower().endswith((".yaml", ".yml")):
        raise ValueError("adapter_path must be a .yaml file")
    errors = []
    for root in roots:
        try:
            return _resolve_regular_file_under_root(value, root, "adapter_path")
        except ValueError as error:
            errors.append(str(error))
    raise ValueError("adapter_path must stay under IMPORT_ROOT or ADAPTERS_ROOT: " + "; ".join(errors))


class HFImportJobsMixin:
    def _import_hf_dataset(self, job: Job) -> ImportResult:
        source_id = str(job.payload.get("source_id", "")).strip()
        adapter_value = str(job.payload.get("adapter_path", "")).strip()
        if not source_id or not adapter_value:
            raise ValueError("import_hf_dataset requires source_id and adapter_path")
        adapter_path = resolve_adapter_path(
            adapter_value, [self.config.import_root, getattr(self.config, "adapters_root", Path("adapters").resolve())]
        )
        with psycopg.connect(self.config.database_url) as connection:
            row = connection.execute(
                """
                SELECT object_sha256, source_type, data_origin, production_run_id
                FROM sources WHERE id = %s
                """,
                (source_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Source was not found")
        if row[0] is not None:
            raise RuntimeError("Source is already ingested")
        if row[1] != HF_SOURCE_TYPE or row[2] in {"model", "hybrid"} or row[3] is not None:
            raise RuntimeError("import_hf_dataset requires an hf_dataset source without production provenance")

        work_dir = self.config.import_root / "hf-import" / source_id
        connections = int(job.payload.get("connections") or getattr(self.config, "hf_import_connections", 4))
        with psycopg.connect(self.config.database_url) as progress_connection:
            last = [0.0]

            def progress(values: dict) -> None:
                now = time.monotonic()
                if values.get("event") not in {"file_done", "done"} and now - last[0] < 5.0:
                    return
                last[0] = now
                self._write_job_progress(progress_connection, job, "importing_hf_dataset", values)

            return import_hf_dataset(
                adapter_path,
                work_dir,
                store=self.store,
                connections=max(1, min(8, connections)),
                keep_local_shards=False,
                progress_callback=progress,
            )

    def _complete_hf_import(self, connection: psycopg.Connection, job: Job, result: ImportResult) -> None:
        source_id = str(job.payload["source_id"])
        lineage_note = job.payload.get("lineage_note")
        lineage_ref = result.lineage_ref(str(lineage_note) if lineage_note else None)
        licence_id = result.manifest["licence"]["id"] or "hf-card:unspecified"
        manifest_bytes = result.manifest_path.read_bytes()
        line_count = manifest_bytes.count(b"\n")
        with connection.transaction():
            source = connection.execute(
                "SELECT object_sha256, license FROM sources WHERE id = %s FOR UPDATE",
                (source_id,),
            ).fetchone()
            if source is None:
                raise RuntimeError("Source was not found")
            for shard in result.shards:
                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (shard["sha256"], storage_key_for(shard["sha256"]), shard["byte_size"], SHARD_MEDIA_TYPE),
                )
            connection.execute(
                """
                INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (sha256) DO NOTHING
                """,
                (result.manifest_sha256, result.manifest_storage_key, result.manifest_byte_size, IMPORT_MANIFEST_MEDIA_TYPE),
            )
            # Kaynak API'de kartin lisansi bilinmeden olusur; yalniz yer tutucu degistirilir.
            license_value = licence_id if source[1] == PENDING_LICENSE else source[1]
            updated = connection.execute(
                """
                UPDATE sources
                SET object_sha256 = %s,
                    byte_size = %s,
                    line_count = %s,
                    detected_encoding = 'UTF-8',
                    lineage_ref = %s,
                    license = %s,
                    approval_status = 'raw_ingested'
                WHERE id = %s AND object_sha256 IS NULL AND source_type = %s
                """,
                (
                    result.manifest_sha256,
                    result.manifest_byte_size,
                    line_count,
                    lineage_ref,
                    license_value,
                    source_id,
                    HF_SOURCE_TYPE,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Source is missing or already ingested")
            totals = result.manifest["totals"]
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES ('system', 'source.ingested', 'source', %s, %s::jsonb)
                """,
                (
                    source_id,
                    json.dumps({
                        "job_id": str(job.id),
                        "sha256": result.manifest_sha256,
                        "byte_size": result.manifest_byte_size,
                        "import_kind": HF_SOURCE_TYPE,
                        "dataset": result.manifest["dataset"],
                        "revision": result.manifest["revision"],
                        "shards": totals["shards"],
                        "documents": totals["documents"],
                    }),
                ),
            )
            for job_type in ("scan_pii", "check_exact_duplicate"):
                connection.execute(
                    """
                    INSERT INTO background_jobs(job_type, payload, created_by)
                    SELECT %s, jsonb_build_object('source_id', %s::text, 'object_sha256', %s::text), created_by
                    FROM sources WHERE id = %s
                    ON CONFLICT DO NOTHING
                    """,
                    (job_type, source_id, result.manifest_sha256, source_id),
                )
            completed = connection.execute(
                """
                UPDATE background_jobs
                SET status = 'succeeded', result = %s::jsonb, completed_at = now(), updated_at = now()
                WHERE id = %s AND status = 'running'
                  AND locked_by IS NOT DISTINCT FROM %s
                  AND attempts = %s
                """,
                (
                    json.dumps({
                        "manifest_sha256": result.manifest_sha256,
                        "manifest_byte_size": result.manifest_byte_size,
                        "shards": totals["shards"],
                        "documents": totals["documents"],
                        "records_seen": totals["records_seen"],
                        "empty_text": totals["empty_text"],
                        "bytes_by_column_class": totals["bytes_by_column_class"],
                        "files_skipped_by_resume": result.files_skipped_by_resume,
                        "run": result.run_stats,
                        "datasets_server": result.cross_check,
                    }),
                    job.id,
                    job.lease_owner,
                    job.attempts,
                ),
            )
            if completed.rowcount != 1:
                raise JobLeaseLost(f"Job lease is no longer owned: {job.id}")
