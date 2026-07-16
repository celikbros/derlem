from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import psycopg
from psycopg.rows import dict_row
from derlem_worker.releases import (
    ReleaseGateError,
    build_export_manifest,
    build_mixture_report,
    build_release_export,
    build_release_manifest,
    exact_decontamination,
)
from derlem_worker.similarity import approximate_decontamination, release_near_duplicates
from derlem_worker.jobs.queue import Job


class ReleaseJobsMixin:
    def _freeze_release(self, job: Job) -> str:
        release_id = str(job.payload.get("release_id", "")).strip()
        requested_by = str(job.payload.get("requested_by", "")).strip()
        if not release_id or not requested_by:
            raise ReleaseGateError(
                "freeze_release requires release_id and requested_by",
                {"freeze": {"status": "blocked", "reason": "invalid_job_payload"}},
            )

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            release = connection.execute(
                """
                SELECT id::text, name, version, content_purpose, status
                FROM releases
                WHERE id = %s
                """,
                (release_id,),
            ).fetchone()
            source_rows = connection.execute(
                """
                SELECT release_source.source_id::text, release_source.source_sha256,
                    release_source.source_version, release_source.source_name,
                    release_source.source_type, release_source.license,
                    release_source.rights_status, release_source.language,
                    release_source.domain, release_source.lineage_ref,
                    release_source.byte_size, release_source.line_count,
                    object.media_type, object.storage_key,
                    source.object_sha256 AS current_sha256,
                    source.version AS current_version,
                    source.approval_status, source.rights_status AS current_rights_status,
                    source.license_evidence_ref, source.pii_status,
                    source.duplicate_status, source.normalized_dedup_status,
                    source.document_sampling_status,
                    source.sampled_document_count, source.reviewed_document_count,
                    source.approved_document_count, source.flagged_document_count
                FROM release_sources AS release_source
                JOIN sources AS source ON source.id = release_source.source_id
                JOIN storage_objects AS object ON object.sha256 = release_source.source_sha256
                WHERE release_source.release_id = %s
                ORDER BY release_source.source_id
                """,
                (release_id,),
            ).fetchall()
            quality_rows = self._release_quality_rows(connection, release_id)
            reference_rows = []
            if release is not None and release["content_purpose"] == "pretrain":
                reference_rows = connection.execute(
                    """
                    SELECT source.object_sha256, object.storage_key
                    FROM sources AS source
                    JOIN storage_objects AS object ON object.sha256 = source.object_sha256
                    WHERE source.content_purpose IN ('eval', 'holdout')
                      AND source.object_sha256 IS NOT NULL
                      AND source.duplicate_status <> 'duplicate'
                    ORDER BY source.id
                    """
                ).fetchall()

        if release is None:
            raise ReleaseGateError(
                "Release was not found",
                {"freeze": {"status": "blocked", "reason": "release_not_found"}},
            )
        if release["status"] != "draft":
            raise ReleaseGateError(
                "Only draft releases can be frozen",
                {"freeze": {"status": "blocked", "reason": "release_not_draft"}},
            )
        if not source_rows:
            raise ReleaseGateError(
                "Release has no sources",
                {"source_gate": {"status": "blocked", "reason": "empty_release"}},
            )

        for source in source_rows:
            if not self._release_source_is_current(source):
                raise ReleaseGateError(
                    "Release source changed or is no longer eligible",
                    {
                        "source_gate": {
                            "status": "blocked",
                            "reason": "source_changed_or_ineligible",
                            "source_id": source["source_id"],
                        }
                    },
                )

        release_paths = [
            (str(source["source_sha256"]), self._stored_object_path(str(source["storage_key"])))
            for source in source_rows
        ]
        manifest_sources = [self._manifest_source(source) for source in source_rows]
        mixture_report = build_mixture_report(
            manifest_sources,
            [dict(review) for review in quality_rows],
        )
        with psycopg.connect(self.config.database_url) as progress_connection:
            near_duplicates = release_near_duplicates(
                release_paths,
                max_document_bytes=self.config.max_document_bytes,
                progress_callback=lambda progress: self._write_job_progress(
                    progress_connection,
                    job,
                    "release_near_dedup",
                    progress,
                ),
            )
        near_duplicate_report = near_duplicates.to_dict()
        if release["content_purpose"] == "pretrain":
            reference_paths = [
                (str(reference["object_sha256"]), self._stored_object_path(str(reference["storage_key"])))
                for reference in reference_rows
            ]
            decontamination = exact_decontamination(
                reference_paths,
                release_paths,
                max_document_bytes=self.config.max_document_bytes,
            )
            if decontamination.status != "passed":
                raise ReleaseGateError(
                    "Eval or holdout content was found in the pretrain release",
                    {"decontamination": decontamination.to_dict()},
                )
            decontamination_result = decontamination.to_dict()
            if reference_paths:
                with psycopg.connect(self.config.database_url) as progress_connection:
                    approximate = approximate_decontamination(
                        reference_paths,
                        release_paths,
                        max_document_bytes=self.config.max_document_bytes,
                        progress_callback=lambda progress: self._write_job_progress(
                            progress_connection,
                            job,
                            "approximate_decontamination",
                            progress,
                        ),
                    )
                approximate_decontamination_result = approximate.to_dict()
            else:
                approximate_decontamination_result = {
                    "status": "not_applicable",
                    "reason": "no_eval_or_holdout_sources",
                }
        else:
            decontamination_result = {
                "status": "not_applicable",
                "reason": "content_purpose_is_not_pretrain",
            }
            approximate_decontamination_result = {
                "status": "not_applicable",
                "reason": "content_purpose_is_not_pretrain",
            }

        gate_results: dict[str, object] = {
            "source_gate": {"status": "passed", "source_count": len(source_rows)},
            "rights_gate": {"status": "passed"},
            "pii_gate": {"status": "passed"},
            "exact_duplicate_gate": {"status": "passed"},
            "normalized_dedup_gate": {"status": "passed"},
            "document_review_gate": {"status": "passed"},
            "near_duplicate_report": near_duplicate_report,
            "decontamination": decontamination_result,
            "approximate_decontamination": approximate_decontamination_result,
            "mixture_report": mixture_report,
        }
        frozen_at = datetime.now(timezone.utc)
        frozen_at_text = frozen_at.isoformat().replace("+00:00", "Z")
        manifest_bytes = build_release_manifest(
            dict(release),
            manifest_sources,
            gate_results,
            frozen_at_text,
        )
        stored_manifest = self.store.ingest_bytes(manifest_bytes)

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._assert_job_ownership(connection, job)
                locked_release = connection.execute(
                    "SELECT status FROM releases WHERE id = %s FOR UPDATE",
                    (release_id,),
                ).fetchone()
                if locked_release is None or locked_release["status"] != "draft":
                    raise ReleaseGateError(
                        "Release changed before freeze commit",
                        {"freeze": {"status": "blocked", "reason": "release_changed"}},
                    )
                connection.execute(
                    """
                    SELECT source.id
                    FROM release_sources AS release_source
                    JOIN sources AS source ON source.id = release_source.source_id
                    WHERE release_source.release_id = %s
                    ORDER BY source.id
                    FOR SHARE OF source
                    """,
                    (release_id,),
                ).fetchall()
                validity = connection.execute(
                    """
                    SELECT count(*) AS source_count, count(*) FILTER (WHERE
                        source.object_sha256 IS DISTINCT FROM release_source.source_sha256 OR
                        source.version <> release_source.source_version OR
                        source.approval_status <> 'approved_source' OR
                        source.rights_status <> 'cleared' OR
                        source.license_evidence_ref IS NULL OR
                        source.pii_status <> 'clear' OR
                        source.duplicate_status <> 'unique' OR
                        source.normalized_dedup_status <> 'unique' OR
                        source.document_sampling_status <> 'sampled' OR
                        source.sampled_document_count <= 0 OR
                        source.reviewed_document_count <> source.sampled_document_count OR
                        source.approved_document_count <> source.sampled_document_count OR
                        source.flagged_document_count > 0
                    ) AS invalid_count
                    FROM release_sources AS release_source
                    JOIN sources AS source ON source.id = release_source.source_id
                    WHERE release_source.release_id = %s
                    """,
                    (release_id,),
                ).fetchone()
                if (
                    validity is None
                    or int(validity["source_count"]) != len(source_rows)
                    or int(validity["invalid_count"]) > 0
                ):
                    raise ReleaseGateError(
                        "Release sources changed before freeze commit",
                        {"source_gate": {"status": "blocked", "reason": "source_changed"}},
                    )

                locked_quality_report = build_mixture_report(
                    manifest_sources,
                    [
                        dict(review)
                        for review in self._release_quality_rows(connection, release_id)
                    ],
                )["quality"]
                if locked_quality_report != mixture_report["quality"]:
                    raise ReleaseGateError(
                        "Release quality reviews changed before freeze commit",
                        {
                            "quality_mixture": {
                                "status": "blocked",
                                "reason": "quality_snapshot_changed",
                            }
                        },
                    )

                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, 'application/vnd.derlem.release-manifest+json')
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (stored_manifest.sha256, stored_manifest.storage_key, stored_manifest.byte_size),
                )
                updated = connection.execute(
                    """
                    UPDATE releases
                    SET status = 'frozen', manifest_object_sha256 = %s,
                        manifest_sha256 = %s, gate_results = %s::jsonb,
                        frozen_by = %s, frozen_at = %s
                    WHERE id = %s AND status = 'draft'
                    """,
                    (
                        stored_manifest.sha256,
                        stored_manifest.sha256,
                        json.dumps(gate_results, ensure_ascii=False),
                        requested_by,
                        frozen_at,
                        release_id,
                    ),
                )
                if updated.rowcount != 1:
                    raise ReleaseGateError(
                        "Release changed before freeze",
                        {"freeze": {"status": "blocked", "reason": "release_changed"}},
                    )
                connection.execute(
                    """
                    INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                    VALUES (
                        'system', 'release.frozen', 'release', %s,
                        jsonb_build_object(
                            'job_id', %s::text,
                            'manifest_sha256', %s::text,
                            'source_count', %s::integer,
                            'gate_results', %s::jsonb
                        )
                    )
                    """,
                    (
                        release_id,
                        str(job.id),
                        stored_manifest.sha256,
                        len(source_rows),
                        json.dumps(gate_results, ensure_ascii=False),
                    ),
                )
                connection.execute(
                    """
                    UPDATE background_jobs
                    SET status = 'succeeded',
                        result = jsonb_build_object(
                            'release_id', %s::text,
                            'manifest_sha256', %s::text,
                            'source_count', %s::integer,
                            'gate_results', %s::jsonb
                        ),
                        completed_at = now(), updated_at = now()
                    WHERE id = %s AND status = 'running'
                    """,
                    (
                        release_id,
                        stored_manifest.sha256,
                        len(source_rows),
                        json.dumps(gate_results, ensure_ascii=False),
                        job.id,
                    ),
                )
        return stored_manifest.sha256

    def _export_release(self, job: Job) -> str:
        release_id = str(job.payload.get("release_id", "")).strip()
        export_id = str(job.payload.get("export_id", "")).strip()
        export_format = str(job.payload.get("format", "")).strip().lower()
        if not release_id or not export_id or export_format not in {"jsonl", "txt"}:
            raise ReleaseGateError(
                "export_release requires release_id, export_id and a supported format",
                {"export": {"status": "blocked", "reason": "invalid_job_payload"}},
            )

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            release = connection.execute(
                """
                SELECT id::text, name, version, content_purpose, status,
                    manifest_sha256, frozen_at
                FROM releases
                WHERE id = %s
                """,
                (release_id,),
            ).fetchone()
            export = connection.execute(
                """
                SELECT id::text, status, format
                FROM release_exports
                WHERE id = %s AND release_id = %s
                """,
                (export_id, release_id),
            ).fetchone()
            source_rows = connection.execute(
                """
                SELECT release_source.source_id::text, release_source.source_sha256,
                    release_source.source_name, release_source.license,
                    release_source.language, release_source.domain,
                    object.storage_key
                FROM release_sources AS release_source
                JOIN storage_objects AS object ON object.sha256 = release_source.source_sha256
                WHERE release_source.release_id = %s
                ORDER BY release_source.source_id
                """,
                (release_id,),
            ).fetchall()
            if (
                release is None
                or release["status"] != "frozen"
                or export is None
                or export["format"] != export_format
                or export["status"] not in {"queued", "building"}
            ):
                raise ReleaseGateError(
                    "Release export is no longer eligible",
                    {"export": {"status": "blocked", "reason": "export_not_eligible"}},
                )
            self._assert_job_ownership(connection, job)
            connection.execute(
                """
                UPDATE release_exports
                SET status = 'building', last_error = NULL
                WHERE id = %s AND status IN ('queued', 'building')
                """,
                (export_id,),
            )
            connection.commit()

        export_sources: list[dict[str, object]] = []
        for source in source_rows:
            item = dict(source)
            item["path"] = self._stored_object_path(str(source["storage_key"]))
            export_sources.append(item)

        temp_descriptor, temp_name = tempfile.mkstemp(
            prefix=f"release-export-{export_format}-",
            dir=self.store.temp_root,
        )
        os.close(temp_descriptor)
        temp_path = Path(temp_name)
        try:
            with psycopg.connect(self.config.database_url) as progress_connection:
                def update_progress(progress: dict[str, int]) -> None:
                    progress_connection.execute(
                        """
                        UPDATE background_jobs
                        SET result = jsonb_build_object(
                            'phase', 'building',
                            'release_id', %s::text,
                            'export_id', %s::text,
                            'format', %s::text,
                            'progress', %s::jsonb
                        ), updated_at = now()
                        WHERE id = %s AND status = 'running'
                          AND locked_by IS NOT DISTINCT FROM %s
                          AND attempts = %s
                        """,
                        (
                            release_id,
                            export_id,
                            export_format,
                            json.dumps(progress, ensure_ascii=False),
                            job.id,
                            job.lease_owner,
                            job.attempts,
                        ),
                    )
                    progress_connection.commit()

                result = build_release_export(
                    dict(release),
                    export_sources,
                    export_format,
                    temp_path,
                    max_document_bytes=self.config.max_document_bytes,
                    progress_callback=update_progress,
                )
            stored_export = self.store.ingest_file(temp_path)
            if stored_export.sha256 != result.sha256 or stored_export.byte_size != result.byte_size:
                raise RuntimeError("Export checksum changed while publishing")
            manifest_bytes = build_export_manifest(dict(release), export_sources, result)
            stored_manifest = self.store.ingest_bytes(manifest_bytes)
        finally:
            temp_path.unlink(missing_ok=True)

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._assert_job_ownership(connection, job)
                locked_export = connection.execute(
                    """
                    SELECT status
                    FROM release_exports
                    WHERE id = %s AND release_id = %s
                    FOR UPDATE
                    """,
                    (export_id, release_id),
                ).fetchone()
                if locked_export is None or locked_export["status"] != "building":
                    raise ReleaseGateError(
                        "Release export changed before publish",
                        {"export": {"status": "blocked", "reason": "export_changed"}},
                    )
                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (
                        stored_export.sha256,
                        stored_export.storage_key,
                        stored_export.byte_size,
                        result.media_type,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                    VALUES (%s, %s, %s, 'application/vnd.derlem.export-manifest+json')
                    ON CONFLICT (sha256) DO NOTHING
                    """,
                    (
                        stored_manifest.sha256,
                        stored_manifest.storage_key,
                        stored_manifest.byte_size,
                    ),
                )
                updated = connection.execute(
                    """
                    UPDATE release_exports
                    SET status = 'ready', object_sha256 = %s,
                        manifest_object_sha256 = %s, record_count = %s,
                        byte_size = %s, estimated_token_count = %s,
                        token_estimate_lower_bound = %s,
                        token_estimate_upper_bound = %s,
                        token_estimate_method = %s,
                        record_type_counts = %s::jsonb,
                        completed_at = now(), last_error = NULL
                    WHERE id = %s AND status = 'building'
                    """,
                    (
                        stored_export.sha256,
                        stored_manifest.sha256,
                        result.record_count,
                        result.byte_size,
                        result.token_estimate.estimated_token_count,
                        result.token_estimate.lower_bound,
                        result.token_estimate.upper_bound,
                        result.token_estimate.method,
                        json.dumps(result.record_type_counts, ensure_ascii=False),
                        export_id,
                    ),
                )
                if updated.rowcount != 1:
                    raise ReleaseGateError(
                        "Release export changed before commit",
                        {"export": {"status": "blocked", "reason": "export_changed"}},
                    )
                connection.execute(
                    """
                    INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                    VALUES (
                        'system', 'release.export_ready', 'release', %s,
                        jsonb_build_object(
                            'job_id', %s::text,
                            'export_id', %s::text,
                            'format', %s::text,
                            'object_sha256', %s::text,
                            'manifest_object_sha256', %s::text,
                            'record_count', %s::bigint,
                            'byte_size', %s::bigint,
                            'estimated_token_count', %s::bigint,
                            'token_estimate_lower_bound', %s::bigint,
                            'token_estimate_upper_bound', %s::bigint,
                            'token_estimate_method', %s::text,
                            'record_type_counts', %s::jsonb
                        )
                    )
                    """,
                    (
                        release_id,
                        str(job.id),
                        export_id,
                        export_format,
                        stored_export.sha256,
                        stored_manifest.sha256,
                        result.record_count,
                        result.byte_size,
                        result.token_estimate.estimated_token_count,
                        result.token_estimate.lower_bound,
                        result.token_estimate.upper_bound,
                        result.token_estimate.method,
                        json.dumps(result.record_type_counts, ensure_ascii=False),
                    ),
                )
                connection.execute(
                    """
                    UPDATE background_jobs
                    SET status = 'succeeded',
                        result = jsonb_build_object(
                            'phase', 'ready',
                            'release_id', %s::text,
                            'export_id', %s::text,
                            'format', %s::text,
                            'object_sha256', %s::text,
                            'manifest_object_sha256', %s::text,
                            'record_count', %s::bigint,
                            'byte_size', %s::bigint,
                            'estimated_token_count', %s::bigint,
                            'token_estimate_lower_bound', %s::bigint,
                            'token_estimate_upper_bound', %s::bigint,
                            'token_estimate_method', %s::text,
                            'record_type_counts', %s::jsonb
                        ),
                        completed_at = now(), updated_at = now()
                    WHERE id = %s AND status = 'running'
                    """,
                    (
                        release_id,
                        export_id,
                        export_format,
                        stored_export.sha256,
                        stored_manifest.sha256,
                        result.record_count,
                        result.byte_size,
                        result.token_estimate.estimated_token_count,
                        result.token_estimate.lower_bound,
                        result.token_estimate.upper_bound,
                        result.token_estimate.method,
                        json.dumps(result.record_type_counts, ensure_ascii=False),
                        job.id,
                    ),
                )
        return stored_export.sha256

    @staticmethod
    def _release_quality_rows(
        connection: psycopg.Connection,
        release_id: str,
    ) -> list[dict[str, object]]:
        return connection.execute(
            """
            SELECT release_source.source_id::text AS source_id,
                document.id::text AS document_id,
                document.current_version AS document_version,
                document.sample_generation,
                document.current_object_sha256 AS object_sha256,
                current_review.review_id,
                current_review.decision,
                current_review.rubric_version,
                current_review.quality_score,
                current_review.language_quality_score,
                current_review.coherence_score,
                current_review.information_density_score,
                current_review.cleanliness_score
            FROM release_sources AS release_source
            JOIN documents AS document
              ON document.source_id = release_source.source_id
             AND document.is_active
            LEFT JOIN LATERAL (
                SELECT review.id::text AS review_id,
                    review.decision,
                    review.rubric_version,
                    review.quality_score,
                    review.language_quality_score,
                    review.coherence_score,
                    review.information_density_score,
                    review.cleanliness_score
                FROM document_reviews AS review
                WHERE review.document_id = document.id
                  AND review.document_version = document.current_version
                  AND review.object_sha256 = document.current_object_sha256
                ORDER BY review.created_at DESC, review.id DESC
                LIMIT 1
            ) AS current_review ON true
            WHERE release_source.release_id = %s
            ORDER BY release_source.source_id, document.id
            """,
            (release_id,),
        ).fetchall()

    @staticmethod
    def _release_source_is_current(source: dict[str, object]) -> bool:
        return bool(
            str(source["current_sha256"]) == str(source["source_sha256"])
            and int(source["current_version"]) == int(source["source_version"])
            and source["approval_status"] == "approved_source"
            and source["current_rights_status"] == "cleared"
            and source["license_evidence_ref"]
            and source["pii_status"] == "clear"
            and source["duplicate_status"] == "unique"
            and source["normalized_dedup_status"] == "unique"
            and source["document_sampling_status"] == "sampled"
            and int(source["sampled_document_count"]) > 0
            and int(source["reviewed_document_count"]) == int(source["sampled_document_count"])
            and int(source["approved_document_count"]) == int(source["sampled_document_count"])
            and int(source["flagged_document_count"]) == 0
        )

    @staticmethod
    def _manifest_source(source: dict[str, object]) -> dict[str, object]:
        return {
            "source_id": str(source["source_id"]),
            "source_sha256": str(source["source_sha256"]),
            "source_version": int(source["source_version"]),
            "name": str(source["source_name"]),
            "source_type": str(source["source_type"]),
            "license": str(source["license"]),
            "rights_status": str(source["rights_status"]),
            "language": str(source["language"]),
            "domain": str(source["domain"]),
            "lineage_ref": str(source["lineage_ref"]),
            "byte_size": int(source["byte_size"]) if source["byte_size"] is not None else None,
            "line_count": int(source["line_count"]) if source["line_count"] is not None else None,
            "media_type": str(source["media_type"]) if source["media_type"] is not None else None,
        }
