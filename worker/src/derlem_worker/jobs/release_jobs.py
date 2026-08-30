from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
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
    validate_release_contract_evidence,
)
from derlem_worker.similarity import approximate_decontamination, release_near_duplicates
from derlem_worker.jobs.queue import Job


def _verify_stored_object(
    path: Path,
    expected_sha256: str,
    expected_byte_size: int,
) -> None:
    """Verify immutable CAS bytes without exposing the local storage path."""
    expected_digest = expected_sha256.strip().lower()
    if len(expected_digest) != 64 or any(
        character not in "0123456789abcdef" for character in expected_digest
    ):
        raise ReleaseGateError(
            "Stored object evidence is invalid",
            {
                "storage_integrity": {
                    "status": "blocked",
                    "reason": "invalid_expected_digest",
                }
            },
        )
    if expected_byte_size < 0:
        raise ReleaseGateError(
            "Stored object evidence is invalid",
            {
                "storage_integrity": {
                    "status": "blocked",
                    "reason": "invalid_expected_size",
                    "object_sha256": expected_digest,
                }
            },
        )

    digest = hashlib.sha256()
    actual_byte_size = 0
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ReleaseGateError(
                    "Stored object is not a regular file",
                    {
                        "storage_integrity": {
                            "status": "blocked",
                            "reason": "stored_object_not_regular",
                            "object_sha256": expected_digest,
                        }
                    },
                )
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                actual_byte_size += len(chunk)
            after = os.fstat(handle.fileno())
    except ReleaseGateError:
        raise
    except (OSError, ValueError) as error:
        raise ReleaseGateError(
            "Stored object could not be verified",
            {
                "storage_integrity": {
                    "status": "blocked",
                    "reason": "stored_object_unreadable",
                    "object_sha256": expected_digest,
                }
            },
        ) from error

    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity:
        raise ReleaseGateError(
            "Stored object changed during verification",
            {
                "storage_integrity": {
                    "status": "blocked",
                    "reason": "stored_object_changed_during_verification",
                    "object_sha256": expected_digest,
                }
            },
        )
    if actual_byte_size != expected_byte_size or after.st_size != expected_byte_size:
        raise ReleaseGateError(
            "Stored object size does not match its evidence",
            {
                "storage_integrity": {
                    "status": "blocked",
                    "reason": "stored_object_size_mismatch",
                    "object_sha256": expected_digest,
                    "expected_byte_size": expected_byte_size,
                    "actual_byte_size": actual_byte_size,
                }
            },
        )
    if digest.hexdigest() != expected_digest:
        raise ReleaseGateError(
            "Stored object digest does not match its evidence",
            {
                "storage_integrity": {
                    "status": "blocked",
                    "reason": "stored_object_digest_mismatch",
                    "object_sha256": expected_digest,
                }
            },
        )


def _snapshot_verified_object(
    source_path: Path,
    expected_sha256: str,
    expected_byte_size: int,
    snapshot_root: Path,
) -> Path:
    """Copy and verify the exact bytes consumed by release gates or export."""
    destination = snapshot_root / expected_sha256.strip().lower()
    if destination.exists():
        _verify_stored_object(destination, expected_sha256, expected_byte_size)
        return destination

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".verified-object-",
        dir=snapshot_root,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    published = False
    try:
        with source_path.open("rb") as source, temporary_path.open("wb") as target:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise OSError("stored object is not a regular file")
            shutil.copyfileobj(source, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
            after = os.fstat(source.fileno())
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise OSError("stored object changed while snapshotting")
        _verify_stored_object(temporary_path, expected_sha256, expected_byte_size)
        os.replace(temporary_path, destination)
        published = True
        return destination
    except ReleaseGateError:
        raise
    except (OSError, ValueError) as error:
        raise ReleaseGateError(
            "Stored object could not be snapshotted for verification",
            {
                "storage_integrity": {
                    "status": "blocked",
                    "reason": "stored_object_snapshot_failed",
                    "object_sha256": expected_sha256.strip().lower(),
                }
            },
        ) from error
    finally:
        if not published:
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                pass
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


class ReleaseJobsMixin:
    def _freeze_release(self, job: Job) -> str:
        release_id = str(job.payload.get("release_id", "")).strip()
        requested_by = str(job.payload.get("requested_by", "")).strip()
        if not release_id or not requested_by:
            raise ReleaseGateError(
                "freeze_release requires release_id and requested_by",
                {"freeze": {"status": "blocked", "reason": "invalid_job_payload"}},
            )

        with tempfile.TemporaryDirectory(
            prefix="release-freeze-verified-",
            dir=self.store.temp_root,
        ) as snapshot_directory:
            return self._freeze_release_with_verified_objects(
                job,
                release_id,
                requested_by,
                Path(snapshot_directory),
            )

    def _freeze_release_with_verified_objects(
        self,
        job: Job,
        release_id: str,
        requested_by: str,
        snapshot_root: Path,
    ) -> str:

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            release = connection.execute(
                """
                SELECT id::text, name, version, content_purpose, status,
                    contract_snapshot_status, contract_snapshot_artifact_kind,
                    contract_snapshot_sha256, implementation_bundle_sha256
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
                    release_source.domain,
                    release_source.byte_size, release_source.line_count,
                    object.byte_size AS object_byte_size,
                    object.media_type, object.storage_key,
                    source.object_sha256 AS current_sha256,
                    source.version AS current_version,
                    source.data_origin AS current_data_origin,
                    source.production_run_id::text AS current_production_run_id,
                    source.derived_from_source_id::text AS current_derived_from_source_id,
                    source.approval_status, source.rights_status AS current_rights_status,
                    source.license_evidence_ref IS NOT NULL AS has_license_evidence,
                    contract_spec_artifact_sha256(
                        convert_to(source.license_evidence_ref, 'UTF8')
                    ) AS current_license_evidence_ref_sha256,
                    contract_spec_artifact_sha256(
                        convert_to(source.lineage_ref, 'UTF8')
                    ) AS current_lineage_ref_sha256,
                    source.pii_status,
                    source.duplicate_status, source.normalized_dedup_status,
                    source.document_sampling_status,
                    source.sampled_document_count, source.reviewed_document_count,
                    source.approved_document_count, source.flagged_document_count,
                    snapshot.source_id::text AS contract_source_id,
                    snapshot.data_profile_key, snapshot.data_profile_version,
                    snapshot.data_origin,
                    snapshot.production_run_id::text AS production_run_id,
                    snapshot.derived_from_source_id::text AS derived_from_source_id,
                    snapshot.production_run_implementation_digest,
                    snapshot.production_run_config_sha256,
                    snapshot.production_run_input_manifest_sha256,
                    snapshot.production_run_completion_job_id::text
                        AS production_run_completion_job_id,
                    snapshot.production_run_output_manifest_sha256,
                    snapshot.production_run_output_sha256,
                    snapshot.production_run_output_byte_size,
                    snapshot.production_run_output_record_count,
                    snapshot.production_run_completed_at_utc,
                    current_completion.job_id::text
                        AS current_production_run_completion_job_id,
                    current_completion.output_manifest_sha256
                        AS current_production_run_output_manifest_sha256,
                    current_completion.output_sha256
                        AS current_production_run_output_sha256,
                    current_completion.output_byte_size
                        AS current_production_run_output_byte_size,
                    current_completion.output_record_count
                        AS current_production_run_output_record_count,
                    to_char(
                        current_completion.completed_at AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                    ) AS current_production_run_completed_at_utc,
                    completion_manifest_object.storage_key
                        AS production_run_manifest_storage_key,
                    completion_manifest_object.byte_size
                        AS production_run_manifest_object_byte_size,
                    snapshot.license_evidence_ref_sha256,
                    snapshot.lineage_ref_sha256,
                    snapshot.sample_generation,
                    snapshot.sample_source_sha256,
                    snapshot.sample_sampling_method,
                    snapshot.sample_count,
                    snapshot.sample_membership_count,
                    snapshot.sample_membership_root_sha256,
                    snapshot.sample_job_id::text AS sample_job_id,
                    snapshot.profile_config_sha256,
                    snapshot.profile_config_schema_artifact_kind,
                    snapshot.profile_config_schema_sha256,
                    snapshot.payload_schema_sha256,
                    snapshot.field_extraction_sha256,
                    snapshot.profile_implementation_key,
                    snapshot.profile_implementation_digest,
                    snapshot.rubric_key, snapshot.rubric_version,
                    snapshot.rubric_sha256,
                    snapshot.protocol_key, snapshot.protocol_version,
                    snapshot.protocol_sha256,
                    snapshot.pii_policy_key, snapshot.pii_policy_version,
                    snapshot.pii_policy_sha256,
                    snapshot.dedup_policy_key, snapshot.dedup_policy_version,
                    snapshot.dedup_policy_sha256,
                    snapshot.leakage_policy_key, snapshot.leakage_policy_version,
                    snapshot.leakage_policy_sha256,
                    snapshot.purpose_contract_version,
                    snapshot.purpose_contract_sha256,
                    snapshot.export_contract_key, snapshot.export_contract_version,
                    snapshot.export_contract_sha256,
                    snapshot.review_evidence_status,
                    snapshot.review_campaign_id::text,
                    snapshot.implementation_bundle_sha256
                        AS source_implementation_bundle_sha256
                FROM release_sources AS release_source
                JOIN sources AS source ON source.id = release_source.source_id
                JOIN storage_objects AS object ON object.sha256 = release_source.source_sha256
                LEFT JOIN release_source_contract_snapshots AS snapshot
                  ON snapshot.release_id = release_source.release_id
                 AND snapshot.source_id = release_source.source_id
                LEFT JOIN production_run_completions AS current_completion
                  ON current_completion.production_run_id = source.production_run_id
                LEFT JOIN storage_objects AS completion_manifest_object
                  ON completion_manifest_object.sha256 =
                     snapshot.production_run_output_manifest_sha256
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
                    SELECT source.object_sha256, object.storage_key,
                        object.byte_size AS object_byte_size
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

        contract_gate = validate_release_contract_evidence(
            dict(release),
            [dict(source) for source in source_rows],
            [dict(review) for review in quality_rows],
        )
        release_paths: list[tuple[str, Path]] = []
        for source in source_rows:
            pinned_byte_size = source["byte_size"]
            object_byte_size = source["object_byte_size"]
            if (
                pinned_byte_size is None
                or object_byte_size is None
                or int(pinned_byte_size) != int(object_byte_size)
            ):
                raise ReleaseGateError(
                    "Release source size evidence is incomplete or inconsistent",
                    {
                        "storage_integrity": {
                            "status": "blocked",
                            "reason": "stored_object_size_evidence_mismatch",
                            "source_id": str(source["source_id"]),
                            "object_sha256": str(source["source_sha256"]),
                        }
                    },
                )
            source_path = self._release_object_path(
                str(source["storage_key"]),
                str(source["source_sha256"]),
            )
            release_paths.append(
                (
                    str(source["source_sha256"]),
                    _snapshot_verified_object(
                        source_path,
                        str(source["source_sha256"]),
                        int(pinned_byte_size),
                        snapshot_root,
                    ),
                )
            )
            if source["data_origin"] in {"model", "hybrid"}:
                if (
                    source["production_run_manifest_storage_key"] is None
                    or source["production_run_manifest_object_byte_size"] is None
                ):
                    raise ReleaseGateError(
                        "Production completion manifest is unavailable",
                        {
                            "production_evidence": {
                                "status": "blocked",
                                "reason": "completion_manifest_unavailable",
                                "source_id": str(source["source_id"]),
                            }
                        },
                    )
                completion_manifest_path = self._release_object_path(
                    str(source["production_run_manifest_storage_key"]),
                    str(source["production_run_output_manifest_sha256"]),
                )
                _snapshot_verified_object(
                    completion_manifest_path,
                    str(source["production_run_output_manifest_sha256"]),
                    int(source["production_run_manifest_object_byte_size"]),
                    snapshot_root,
                )

        reference_paths: list[tuple[str, Path]] = []
        for reference in reference_rows:
            reference_sha256 = str(reference["object_sha256"])
            reference_path = self._release_object_path(
                str(reference["storage_key"]),
                reference_sha256,
            )
            reference_paths.append(
                (
                    reference_sha256,
                    _snapshot_verified_object(
                        reference_path,
                        reference_sha256,
                        int(reference["object_byte_size"]),
                        snapshot_root,
                    ),
                )
            )

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
            decontamination = exact_decontamination(
                reference_paths,
                release_paths,
                max_document_bytes=self.config.max_document_bytes,
            )
            # Yalniz GERCEK bir eslesme freeze'i durdurur. "not_evaluated"
            # (referans kumesi bos) durdurmaz -- durumu manifeste durustce
            # yazip devam eder; aksi halde eval/holdout kaynagi alinmadan
            # hicbir pretrain release'i dondurulemezdi.
            if decontamination.status == "blocked":
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
            "storage_integrity": {
                "status": "passed",
                "source_object_count": len(release_paths),
                "reference_object_count": len(reference_paths),
            },
            "rights_gate": {"status": "passed"},
            "pii_gate": {"status": "passed"},
            "exact_duplicate_gate": {"status": "passed"},
            "normalized_dedup_gate": {"status": "passed"},
            "document_review_gate": {"status": "passed"},
            "contract_snapshot": contract_gate,
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
            {
                "status": "present",
                "artifact_kind": str(release["contract_snapshot_artifact_kind"]),
                "sha256": str(release["contract_snapshot_sha256"]),
                "implementation_bundle_sha256": str(
                    release["implementation_bundle_sha256"]
                ),
            },
        )
        stored_manifest = self.store.ingest_bytes(manifest_bytes)

        with psycopg.connect(self.config.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._assert_job_ownership(connection, job)
                locked_release = connection.execute(
                    """
                    SELECT status, contract_snapshot_status,
                        contract_snapshot_artifact_kind,
                        contract_snapshot_sha256, implementation_bundle_sha256
                    FROM releases
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (release_id,),
                ).fetchone()
                if (
                    locked_release is None
                    or locked_release["status"] != "draft"
                    or locked_release["contract_snapshot_status"] != "present"
                    or locked_release["contract_snapshot_sha256"]
                    != release["contract_snapshot_sha256"]
                    or locked_release["implementation_bundle_sha256"]
                    != release["implementation_bundle_sha256"]
                ):
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
                        source.data_origin IS DISTINCT FROM snapshot.data_origin OR
                        source.production_run_id IS DISTINCT FROM snapshot.production_run_id OR
                        (
                            source.data_origin IN ('model', 'hybrid') AND (
                                current_completion.production_run_id IS NULL OR
                                current_completion.job_id IS DISTINCT FROM
                                    snapshot.production_run_completion_job_id OR
                                current_completion.output_manifest_sha256 IS DISTINCT FROM
                                    snapshot.production_run_output_manifest_sha256 OR
                                current_completion.output_sha256 IS DISTINCT FROM
                                    snapshot.production_run_output_sha256 OR
                                current_completion.output_byte_size IS DISTINCT FROM
                                    snapshot.production_run_output_byte_size OR
                                current_completion.output_record_count IS DISTINCT FROM
                                    snapshot.production_run_output_record_count OR
                                current_completion.output_record_count IS DISTINCT FROM
                                    source.line_count OR
                                to_char(
                                    current_completion.completed_at AT TIME ZONE 'UTC',
                                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                                ) IS DISTINCT FROM
                                    snapshot.production_run_completed_at_utc
                            )
                        ) OR
                        (
                            source.data_origin NOT IN ('model', 'hybrid') AND (
                                snapshot.production_run_completion_job_id IS NOT NULL OR
                                snapshot.production_run_output_manifest_sha256 IS NOT NULL OR
                                snapshot.production_run_output_sha256 IS NOT NULL OR
                                snapshot.production_run_output_byte_size IS NOT NULL OR
                                snapshot.production_run_output_record_count IS NOT NULL OR
                                snapshot.production_run_completed_at_utc IS NOT NULL
                            )
                        ) OR
                        source.derived_from_source_id IS DISTINCT FROM
                            snapshot.derived_from_source_id OR
                        contract_spec_artifact_sha256(
                            convert_to(source.license_evidence_ref, 'UTF8')
                        ) IS DISTINCT FROM snapshot.license_evidence_ref_sha256 OR
                        contract_spec_artifact_sha256(
                            convert_to(source.lineage_ref, 'UTF8')
                        ) IS DISTINCT FROM snapshot.lineage_ref_sha256 OR
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
                    JOIN release_source_contract_snapshots AS snapshot
                      ON snapshot.release_id = release_source.release_id
                     AND snapshot.source_id = release_source.source_id
                    LEFT JOIN production_run_completions AS current_completion
                      ON current_completion.production_run_id =
                         source.production_run_id
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

                locked_quality_rows = [
                    dict(review)
                    for review in self._release_quality_rows(connection, release_id)
                ]
                validate_release_contract_evidence(
                    dict(locked_release),
                    [dict(source) for source in source_rows],
                    locked_quality_rows,
                )
                locked_quality_report = build_mixture_report(
                    manifest_sources,
                    locked_quality_rows,
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

        with tempfile.TemporaryDirectory(
            prefix="release-export-verified-",
            dir=self.store.temp_root,
        ) as snapshot_directory:
            return self._export_release_with_verified_objects(
                job,
                release_id,
                export_id,
                export_format,
                Path(snapshot_directory),
            )

    def _export_release_with_verified_objects(
        self,
        job: Job,
        release_id: str,
        export_id: str,
        export_format: str,
        snapshot_root: Path,
    ) -> str:

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
                    release_source.byte_size,
                    object.byte_size AS object_byte_size,
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
            if (
                source["byte_size"] is None
                or source["object_byte_size"] is None
                or int(source["byte_size"]) != int(source["object_byte_size"])
            ):
                raise ReleaseGateError(
                    "Release source size evidence is incomplete or inconsistent",
                    {
                        "storage_integrity": {
                            "status": "blocked",
                            "reason": "stored_object_size_evidence_mismatch",
                            "source_id": str(source["source_id"]),
                            "object_sha256": str(source["source_sha256"]),
                        }
                    },
                )
            source_path = self._release_object_path(
                str(source["storage_key"]),
                str(source["source_sha256"]),
            )
            item["path"] = _snapshot_verified_object(
                source_path,
                str(source["source_sha256"]),
                int(source["byte_size"]),
                snapshot_root,
            )
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
                current_review.review_campaign_id,
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
            JOIN release_source_contract_snapshots AS snapshot
              ON snapshot.release_id = release_source.release_id
             AND snapshot.source_id = release_source.source_id
            LEFT JOIN LATERAL (
                SELECT review.id::text AS review_id,
                    review.decision,
                    review.review_campaign_id::text AS review_campaign_id,
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
                  AND (
                    (
                      snapshot.review_evidence_status = 'campaign_pinned'
                      AND review.review_campaign_id = snapshot.review_campaign_id
                    )
                    OR (
                      snapshot.review_evidence_status = 'absent_pre_registry'
                      AND snapshot.data_profile_key = 'legacy-auto'
                      AND review.review_campaign_id IS NULL
                    )
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM document_review_reversals AS reversal
                      WHERE reversal.review_id = review.id
                  )
                ORDER BY review.created_at DESC, review.id DESC
                LIMIT 1
            ) AS current_review ON true
            WHERE release_source.release_id = %s
              AND document.sample_generation = snapshot.sample_generation
            ORDER BY release_source.source_id, document.id
            """,
            (release_id,),
        ).fetchall()

    def _release_object_path(self, storage_key: str, object_sha256: str) -> Path:
        try:
            return self._stored_object_path(storage_key)
        except (OSError, RuntimeError, ValueError) as error:
            raise ReleaseGateError(
                "Stored object is unavailable",
                {
                    "storage_integrity": {
                        "status": "blocked",
                        "reason": "stored_object_unavailable",
                        "object_sha256": object_sha256.strip().lower(),
                    }
                },
            ) from error

    @staticmethod
    def _release_source_is_current(source: dict[str, object]) -> bool:
        return bool(
            str(source["current_sha256"]) == str(source["source_sha256"])
            and int(source["current_version"]) == int(source["source_version"])
            and source["current_data_origin"] == source["data_origin"]
            and source["current_production_run_id"] == source["production_run_id"]
            and source["current_production_run_completion_job_id"]
            == source["production_run_completion_job_id"]
            and source["current_production_run_output_manifest_sha256"]
            == source["production_run_output_manifest_sha256"]
            and source["current_production_run_output_sha256"]
            == source["production_run_output_sha256"]
            and source["current_production_run_output_byte_size"]
            == source["production_run_output_byte_size"]
            and source["current_production_run_output_record_count"]
            == source["production_run_output_record_count"]
            and source["current_production_run_completed_at_utc"]
            == source["production_run_completed_at_utc"]
            and source["current_derived_from_source_id"] == source["derived_from_source_id"]
            and source["current_license_evidence_ref_sha256"]
            == source["license_evidence_ref_sha256"]
            and source["current_lineage_ref_sha256"] == source["lineage_ref_sha256"]
            and source["approval_status"] == "approved_source"
            and source["current_rights_status"] == "cleared"
            and source["has_license_evidence"]
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
            "lineage_ref_sha256": str(source["lineage_ref_sha256"]),
            "license_evidence_ref_sha256": str(source["license_evidence_ref_sha256"]),
            "provenance": {
                "data_origin": str(source["data_origin"]),
                "production_run_id": (
                    str(source["production_run_id"])
                    if source["production_run_id"] is not None
                    else None
                ),
                "derived_from_source_id": (
                    str(source["derived_from_source_id"])
                    if source["derived_from_source_id"] is not None
                    else None
                ),
                "production_run_evidence": (
                    {
                        "implementation_digest": str(
                            source["production_run_implementation_digest"]
                        ),
                        "config_sha256": (
                            str(source["production_run_config_sha256"])
                            if source["production_run_config_sha256"] is not None
                            else None
                        ),
                        "input_manifest_sha256": (
                            str(source["production_run_input_manifest_sha256"])
                            if source["production_run_input_manifest_sha256"] is not None
                            else None
                        ),
                        "completion": (
                            {
                                "job_id": str(
                                    source["production_run_completion_job_id"]
                                ),
                                "output_manifest_sha256": str(
                                    source["production_run_output_manifest_sha256"]
                                ),
                                "output_sha256": str(
                                    source["production_run_output_sha256"]
                                ),
                                "output_byte_size": int(
                                    source["production_run_output_byte_size"]
                                ),
                                "output_record_count": int(
                                    source["production_run_output_record_count"]
                                ),
                                "completed_at_utc": str(
                                    source["production_run_completed_at_utc"]
                                ),
                            }
                            if source["data_origin"] in {"model", "hybrid"}
                            else None
                        ),
                    }
                    if source["production_run_id"] is not None
                    else None
                ),
            },
            "byte_size": int(source["byte_size"]) if source["byte_size"] is not None else None,
            "line_count": int(source["line_count"]) if source["line_count"] is not None else None,
            "media_type": str(source["media_type"]) if source["media_type"] is not None else None,
            "contract": {
                "data_profile_key": str(source["data_profile_key"]),
                "data_profile_version": str(source["data_profile_version"]),
                "profile_config_sha256": str(source["profile_config_sha256"]),
                "profile_config_schema_artifact_kind": str(
                    source["profile_config_schema_artifact_kind"]
                ),
                "profile_config_schema_sha256": str(
                    source["profile_config_schema_sha256"]
                ),
                "payload_schema_sha256": str(source["payload_schema_sha256"]),
                "field_extraction_sha256": str(source["field_extraction_sha256"]),
                "profile_implementation_key": str(
                    source["profile_implementation_key"]
                ),
                "profile_implementation_digest": str(
                    source["profile_implementation_digest"]
                ),
                "rubric_key": str(source["rubric_key"]),
                "rubric_version": str(source["rubric_version"]),
                "rubric_sha256": str(source["rubric_sha256"]),
                "protocol_key": str(source["protocol_key"]),
                "protocol_version": str(source["protocol_version"]),
                "protocol_sha256": str(source["protocol_sha256"]),
                "pii_policy_key": str(source["pii_policy_key"]),
                "pii_policy_version": str(source["pii_policy_version"]),
                "pii_policy_sha256": str(source["pii_policy_sha256"]),
                "dedup_policy_key": str(source["dedup_policy_key"]),
                "dedup_policy_version": str(source["dedup_policy_version"]),
                "dedup_policy_sha256": str(source["dedup_policy_sha256"]),
                "leakage_policy_key": str(source["leakage_policy_key"]),
                "leakage_policy_version": str(source["leakage_policy_version"]),
                "leakage_policy_sha256": str(source["leakage_policy_sha256"]),
                "purpose_contract_version": str(source["purpose_contract_version"]),
                "purpose_contract_sha256": str(source["purpose_contract_sha256"]),
                "export_contract_key": str(source["export_contract_key"]),
                "export_contract_version": str(source["export_contract_version"]),
                "export_contract_sha256": str(source["export_contract_sha256"]),
                "review_evidence_status": str(source["review_evidence_status"]),
                "review_campaign_id": (
                    str(source["review_campaign_id"])
                    if source["review_campaign_id"] is not None
                    else None
                ),
                "sample": {
                    "generation": int(source["sample_generation"]),
                    "source_sha256": str(source["sample_source_sha256"]),
                    "sampling_method": str(source["sample_sampling_method"]),
                    "count": int(source["sample_count"]),
                    "membership_count": int(source["sample_membership_count"]),
                    "membership_root_sha256": str(
                        source["sample_membership_root_sha256"]
                    ),
                    "job_id": (
                        str(source["sample_job_id"])
                        if source["sample_job_id"] is not None
                        else None
                    ),
                },
                "implementation_bundle_sha256": str(
                    source["source_implementation_bundle_sha256"]
                ),
            },
        }
