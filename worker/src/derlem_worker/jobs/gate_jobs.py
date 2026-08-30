from __future__ import annotations

import json
import psycopg
from psycopg.rows import dict_row
from derlem_worker.fingerprints import FINGERPRINT_VERSION, document_fingerprint
from derlem_worker.pii import PIIReport, PIIScanner
from derlem_worker.sampling import (
    SampledDocument,
    SamplingReport,
    _bounded_lines,
    _document_from_line,
    sample_line_documents,
)
from derlem_worker.jobs.queue import Job


def classify_exact_duplicate(source_id: str, canonical_source_id: str) -> tuple[str, str | None]:
    if not source_id or not canonical_source_id:
        raise ValueError("Source identifiers are required")
    if source_id == canonical_source_id:
        return "unique", None
    return "duplicate", canonical_source_id


class GateJobsMixin:
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
        with psycopg.connect(self.config.database_url) as progress_connection:
            report = self.pii_scanner.scan_file(
                object_path,
                progress_callback=lambda progress: self._write_job_progress(
                    progress_connection,
                    job,
                    "scanning_pii",
                    progress,
                ),
            )
        return object_sha256, report

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
                SELECT source.object_sha256, source.duplicate_status, object.storage_key
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
            total_input_bytes = object_path.stat().st_size
            lines_read = 0
            with psycopg.connect(self.config.database_url) as progress_connection:
                def report_fingerprint_progress(bytes_processed: int, lines_read: int) -> None:
                    self._write_job_progress(
                        progress_connection,
                        job,
                        "fingerprinting",
                        {
                            "input_bytes_processed": bytes_processed,
                            "input_bytes_total": total_input_bytes,
                            "lines_read": lines_read,
                            "documents_scanned": total_documents,
                            "indexed_documents": indexed_documents,
                            "skipped_oversized": skipped_oversized,
                            "skipped_too_short": skipped_too_short,
                        },
                    )

                for ordinal, raw_line, oversized in _bounded_lines(
                    object_path,
                    self.config.max_document_bytes,
                    progress_callback=report_fingerprint_progress,
                ):
                    lines_read = ordinal
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
                self._write_job_progress(
                    progress_connection,
                    job,
                    "matching_duplicates",
                    {
                        "input_bytes_processed": total_input_bytes,
                        "input_bytes_total": total_input_bytes,
                        "lines_read": lines_read,
                        "documents_scanned": total_documents,
                        "indexed_documents": indexed_documents,
                        "skipped_oversized": skipped_oversized,
                        "skipped_too_short": skipped_too_short,
                    },
                )

            # All work above is still transactional. Lock and verify the exact
            # claimed attempt before any source/job state can be published.
            self._assert_job_ownership(connection, job)
            duplicate_counts = connection.execute(
                """
                WITH RECURSIVE source_ancestors(source_id) AS (
                    SELECT source.derived_from_source_id
                    FROM sources AS source
                    WHERE source.id = %s
                      AND source.derived_from_source_id IS NOT NULL
                    UNION
                    SELECT parent.derived_from_source_id
                    FROM sources AS parent
                    JOIN source_ancestors AS ancestor
                      ON parent.id = ancestor.source_id
                    WHERE parent.derived_from_source_id IS NOT NULL
                ),
                current_fingerprints AS (
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
                     AND NOT EXISTS (
                         SELECT 1
                         FROM source_ancestors AS ancestor
                         WHERE ancestor.source_id = other.source_id
                     )
                ),
                lineage_summary AS (
                    SELECT COALESCE(
                        array_agg(source_id::text ORDER BY source_id::text),
                        ARRAY[]::text[]
                    ) AS excluded_source_ids
                    FROM source_ancestors
                )
                SELECT
                    internal_duplicates.duplicate_count,
                    external_duplicates.duplicate_count,
                    external_duplicates.duplicate_source_count,
                    lineage_summary.excluded_source_ids
                FROM internal_duplicates, external_duplicates, lineage_summary
                """,
                (
                    source_id,
                    source_id,
                    object_sha256,
                    FINGERPRINT_VERSION,
                    FINGERPRINT_VERSION,
                    source_id,
                ),
            ).fetchone()
            internal_duplicate_count = int(duplicate_counts[0] or 0)
            external_duplicate_count = int(duplicate_counts[1] or 0)
            duplicate_source_count = int(duplicate_counts[2] or 0)
            excluded_source_ids = tuple(
                str(ancestor_id) for ancestor_id in (duplicate_counts[3] or ())
            )
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
                    "lineage_excluded_source_ids": excluded_source_ids,
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
