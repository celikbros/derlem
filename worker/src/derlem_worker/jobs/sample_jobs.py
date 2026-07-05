from __future__ import annotations

import json
import psycopg
from psycopg.rows import dict_row
from derlem_worker.sampling import (
    SampledDocument,
    SamplingReport,
    _bounded_lines,
    _document_from_line,
    sample_line_documents,
)
from derlem_worker.storage import ContentAddressedStore, IngestOutcome, StoredObject
from derlem_worker.jobs.queue import Job


class SampleJobsMixin:
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
        with psycopg.connect(self.config.database_url) as progress_connection:
            latest_progress: dict[str, int] = {}

            def update_sampling_progress(progress: dict[str, int]) -> None:
                latest_progress.clear()
                latest_progress.update(progress)
                self._write_job_progress(
                    progress_connection,
                    job,
                    "sampling",
                    progress,
                )

            report = sample_line_documents(
                object_path,
                sample_size=self.config.document_sample_size,
                max_document_bytes=self.config.max_document_bytes,
                seed=object_sha256,
                progress_callback=update_sampling_progress,
            )
            publish_progress = dict(latest_progress)
            publish_progress["samples_selected"] = len(report.samples)
            self._write_job_progress(
                progress_connection,
                job,
                "publishing_samples",
                publish_progress,
            )
            stored_samples = [
                (sample, self.store.ingest_bytes(sample.text.encode("utf-8")))
                for sample in report.samples
            ]
        return object_sha256, report, stored_samples

    def _complete_document_sampling(
        self,
        connection: psycopg.Connection,
        job: Job,
        object_sha256: str,
        report: SamplingReport,
        stored_samples: list[tuple[SampledDocument, StoredObject]],
        *,
        resample: bool = False,
    ) -> None:
        source_id = str(job.payload["source_id"])
        inserted_count = 0
        retired_count = 0
        with connection.transaction():
            source = connection.execute(
                """
                SELECT object_sha256, duplicate_status, normalized_dedup_status, pii_status,
                    document_sampling_status, document_sample_generation,
                    document_sampling_method, reviewed_document_count, approval_status
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

            previous_generation = int(source[5])
            previous_sampling_method = str(source[6])
            if resample:
                if (
                    source[4] != "resampling"
                    or int(source[7]) != 0
                    or source[8] in {"approved_source", "release_candidate", "rejected", "quarantined"}
                ):
                    raise RuntimeError("Source is no longer eligible for document resampling")
                safety = connection.execute(
                    """
                    SELECT
                        count(*) FILTER (WHERE document.is_active),
                        count(*) FILTER (WHERE document.is_active AND (
                            document.current_version <> 1 OR document.status <> 'sampled'
                        )),
                        (SELECT count(*)
                         FROM document_reviews AS review
                         JOIN documents AS reviewed_document
                           ON reviewed_document.id = review.document_id
                         WHERE reviewed_document.source_id = %s),
                        (SELECT count(*) FROM reviews AS review WHERE review.source_id = %s)
                    FROM documents AS document
                    WHERE document.source_id = %s
                    """,
                    (source_id, source_id, source_id),
                ).fetchone()
                if (
                    safety is None
                    or int(safety[0]) == 0
                    or int(safety[1]) > 0
                    or int(safety[2]) > 0
                    or int(safety[3]) > 0
                ):
                    raise RuntimeError("Document samples changed while resampling")
                retired_count = connection.execute(
                    "UPDATE documents SET is_active = false WHERE source_id = %s AND is_active",
                    (source_id,),
                ).rowcount
                sample_generation = previous_generation + 1
            else:
                if source[4] != "not_sampled":
                    raise RuntimeError("Source is no longer eligible for initial document sampling")
                sample_generation = max(1, previous_generation + 1)

            if resample:
                superseded = connection.execute(
                    """
                    UPDATE document_sample_generations
                    SET status = 'superseded'
                    WHERE source_id = %s AND status = 'active'
                    """,
                    (source_id,),
                )
                if superseded.rowcount != 1:
                    raise RuntimeError("Active sample generation snapshot was not found")
            connection.execute(
                """
                INSERT INTO document_sample_generations(
                    source_id, generation, source_sha256, sampling_method,
                    status, sample_count, job_id
                )
                VALUES (%s, %s, %s, %s, 'active', %s, %s)
                """,
                (
                    source_id,
                    sample_generation,
                    object_sha256,
                    report.sampling_method,
                    len(report.samples),
                    job.id,
                ),
            )

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
                        text_preview, byte_size, char_count, sampling_method,
                        risk_score, risk_reasons, is_active, sample_generation
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s)
                    ON CONFLICT (source_id, source_ordinal) DO UPDATE SET
                        external_id = EXCLUDED.external_id,
                        current_object_sha256 = EXCLUDED.current_object_sha256,
                        text_preview = EXCLUDED.text_preview,
                        byte_size = EXCLUDED.byte_size,
                        char_count = EXCLUDED.char_count,
                        status = 'sampled',
                        current_version = 1,
                        sampling_method = EXCLUDED.sampling_method,
                        risk_score = EXCLUDED.risk_score,
                        risk_reasons = EXCLUDED.risk_reasons,
                        is_active = true,
                        sample_generation = EXCLUDED.sample_generation
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
                        report.sampling_method,
                        sample.risk_score,
                        list(sample.risk_reasons),
                        sample_generation,
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
                    VALUES (%s, 1, %s, %s, %s, 'system', %s)
                    ON CONFLICT (document_id, version) DO NOTHING
                    """,
                    (
                        document[0],
                        stored.sha256,
                        stored.byte_size,
                        len(sample.text),
                        report.sampling_method,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO document_sample_memberships(
                        source_id, generation, document_id, source_ordinal,
                        object_sha256, risk_score, risk_reasons
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source_id,
                        sample_generation,
                        document[0],
                        sample.source_ordinal,
                        stored.sha256,
                        sample.risk_score,
                        list(sample.risk_reasons),
                    ),
                )

            updated = connection.execute(
                """
                UPDATE sources
                SET document_count = %s,
                    sampled_document_count = (
                        SELECT count(*) FROM documents WHERE source_id = %s AND is_active
                    ),
                    document_sampling_status = 'sampled',
                    document_sample_generation = %s,
                    document_sampling_method = %s,
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
                (
                    report.total_documents,
                    source_id,
                    sample_generation,
                    report.sampling_method,
                    source[3],
                    source_id,
                    object_sha256,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Source object changed while recording document samples")

            result_json = json.dumps(
                {
                    "sampling_method": report.sampling_method,
                    "previous_sampling_method": previous_sampling_method,
                    "previous_generation": previous_generation,
                    "sample_generation": sample_generation,
                    "resample": resample,
                    "sample_size": len(report.samples),
                    "inserted_count": inserted_count,
                    "retired_count": retired_count,
                    "total_documents": report.total_documents,
                    "eligible_documents": report.eligible_documents,
                    "skipped_oversized": report.skipped_oversized,
                    "risk_candidate_documents": report.risk_candidate_documents,
                    "selected_risk_documents": report.selected_risk_documents,
                    "risk_reason_counts": report.risk_reason_counts,
                }
            )
            connection.execute(
                """
                INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                VALUES (
                    'system',
                    CASE WHEN %s THEN 'source.documents_resampled' ELSE 'source.documents_sampled' END,
                    'source', %s, %s::jsonb
                )
                """,
                (resample, source_id, result_json),
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
