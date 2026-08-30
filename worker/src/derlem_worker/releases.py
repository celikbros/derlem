from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import tempfile
from typing import Callable, Iterable, Iterator

from derlem_worker.sampling import _bounded_lines, _document_from_line
from derlem_worker.canonical import CanonicalSampleError, parse_canonical_sample


QUALITY_BASIS = "active-pinned-campaign-or-legacy-review-v1"
QUALITY_RUBRIC = "multidimensional-v1"
QUALITY_DIMENSIONS = (
    ("overall", "quality_score"),
    ("language", "language_quality_score"),
    ("coherence", "coherence_score"),
    ("information_density", "information_density_score"),
    ("cleanliness", "cleanliness_score"),
)
QUALITY_BANDS = (
    ("low", 1, 2),
    ("medium", 3, 3),
    ("high", 4, 5),
)


@dataclass(frozen=True)
class DecontaminationMatch:
    source_sha256: str
    source_ordinal: int
    document_sha256: str


@dataclass(frozen=True)
class DecontaminationResult:
    status: str
    method: str
    reference_source_count: int
    reference_document_count: int
    reference_unique_document_count: int
    release_source_count: int
    release_document_count: int
    match_count: int
    sample_matches: tuple[DecontaminationMatch, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["sample_matches"] = [asdict(match) for match in self.sample_matches]
        return value


@dataclass(frozen=True)
class TokenEstimate:
    method: str
    semantic_utf8_bytes: int
    semantic_codepoints: int
    whitespace_units: int
    lower_bound: int
    estimated_token_count: int
    upper_bound: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ExportResult:
    format: str
    media_type: str
    sha256: str
    byte_size: int
    record_count: int
    source_count: int
    source_record_counts: dict[str, int]
    record_type_counts: dict[str, int]
    token_estimate: TokenEstimate

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ReleaseGateError(RuntimeError):
    def __init__(self, message: str, gate_results: dict[str, object]) -> None:
        super().__init__(message)
        self.gate_results = gate_results


def _is_canonical_utc_microsecond(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") == value


def validate_release_contract_evidence(
    release: dict[str, object],
    sources: Iterable[dict[str, object]],
    quality_reviews: Iterable[dict[str, object]],
) -> dict[str, object]:
    source_list = [dict(source) for source in sources]
    review_list = [dict(review) for review in quality_reviews]
    snapshot_sha256 = str(release.get("contract_snapshot_sha256") or "")
    implementation_sha256 = str(release.get("implementation_bundle_sha256") or "")
    if (
        release.get("contract_snapshot_status") != "present"
        or not _is_sha256(snapshot_sha256)
        or not _is_sha256(implementation_sha256)
    ):
        raise ReleaseGateError(
            "Release contract snapshot is missing",
            {
                "contract_snapshot": {
                    "status": "blocked",
                    "reason": "release_contract_snapshot_missing",
                }
            },
        )

    expected_by_source: dict[str, dict[str, object]] = {}
    for source in source_list:
        source_id = str(source.get("source_id") or "")
        evidence_status = str(source.get("review_evidence_status") or "")
        data_origin = str(source.get("data_origin") or "")
        production_run_id = source.get("production_run_id")
        production_run_id = (
            str(production_run_id) if production_run_id is not None else None
        )
        run_implementation_digest = source.get("production_run_implementation_digest")
        run_config_sha256 = source.get("production_run_config_sha256")
        run_input_manifest_sha256 = source.get("production_run_input_manifest_sha256")
        completion_job_id = source.get("production_run_completion_job_id")
        completion_job_id = (
            str(completion_job_id) if completion_job_id is not None else None
        )
        completion_manifest_sha256 = source.get(
            "production_run_output_manifest_sha256"
        )
        completion_output_sha256 = source.get("production_run_output_sha256")
        completion_output_byte_size = source.get(
            "production_run_output_byte_size"
        )
        completion_output_record_count = source.get(
            "production_run_output_record_count"
        )
        completion_at_utc = source.get("production_run_completed_at_utc")
        completion_values = (
            completion_job_id,
            completion_manifest_sha256,
            completion_output_sha256,
            completion_output_byte_size,
            completion_output_record_count,
            completion_at_utc,
        )
        campaign_id = source.get("review_campaign_id")
        campaign_id = str(campaign_id) if campaign_id is not None else None
        if (
            not source_id
            or str(source.get("contract_source_id") or "") != source_id
            or not _is_sha256(str(source.get("profile_config_sha256") or ""))
            or source.get("profile_config_schema_artifact_kind")
            != "profile_config_schema"
            or not _is_sha256(
                str(source.get("profile_config_schema_sha256") or "")
            )
            or not str(source.get("profile_implementation_key") or "").strip()
            or not _is_sha256(
                str(source.get("profile_implementation_digest") or "")
            )
            or not _is_sha256(str(source.get("purpose_contract_sha256") or ""))
            or not _is_sha256(str(source.get("source_implementation_bundle_sha256") or ""))
            or data_origin not in {"unknown", "human", "model", "hybrid"}
            or (data_origin in {"model", "hybrid"} and not production_run_id)
            or (
                data_origin in {"model", "hybrid"}
                and (
                    any(value is None for value in completion_values)
                    or not completion_job_id
                    or not _is_sha256(str(completion_manifest_sha256 or ""))
                    or not _is_sha256(str(completion_output_sha256 or ""))
                    or str(completion_output_sha256) != str(source.get("source_sha256"))
                    or int(completion_output_byte_size or -1)
                    != int(source.get("byte_size") or -2)
                    or int(completion_output_byte_size or 0) <= 0
                    or int(completion_output_record_count or 0) <= 0
                    or int(completion_output_record_count or -1)
                    != int(source.get("line_count") or -2)
                    or not _is_canonical_utc_microsecond(completion_at_utc)
                )
            )
            or (
                data_origin not in {"model", "hybrid"}
                and any(value is not None for value in completion_values)
            )
            or not _is_sha256(str(source.get("license_evidence_ref_sha256") or ""))
            or not _is_sha256(str(source.get("lineage_ref_sha256") or ""))
            or int(source.get("sample_generation") or 0) <= 0
            or not _is_sha256(str(source.get("sample_source_sha256") or ""))
            or not str(source.get("sample_sampling_method") or "").strip()
            or int(source.get("sample_count") or 0) <= 0
            or int(source.get("sample_membership_count") or 0) <= 0
            or int(source.get("sample_membership_count") or 0)
            != int(source.get("sample_count") or 0)
            or not _is_sha256(
                str(source.get("sample_membership_root_sha256") or "")
            )
            or (
                production_run_id is not None
                and not _is_sha256(str(run_implementation_digest or ""))
            )
            or (
                production_run_id is None
                and any(
                    value is not None
                    for value in (
                        run_implementation_digest,
                        run_config_sha256,
                        run_input_manifest_sha256,
                    )
                )
            )
            or (
                run_config_sha256 is not None
                and not _is_sha256(str(run_config_sha256))
            )
            or (
                run_input_manifest_sha256 is not None
                and not _is_sha256(str(run_input_manifest_sha256))
            )
            or evidence_status not in {"campaign_pinned", "absent_pre_registry"}
            or (evidence_status == "campaign_pinned" and not campaign_id)
            or (evidence_status == "absent_pre_registry" and campaign_id is not None)
            or (
                evidence_status == "absent_pre_registry"
                and str(source.get("data_profile_key") or "") != "legacy-auto"
            )
        ):
            raise ReleaseGateError(
                "Release source contract snapshot is incomplete",
                {
                    "contract_snapshot": {
                        "status": "blocked",
                        "reason": "release_source_contract_snapshot_missing",
                        "source_id": source_id,
                    }
                },
            )
        expected_by_source[source_id] = {
            "review_evidence_status": evidence_status,
            "review_campaign_id": campaign_id,
            "rubric_version": str(source.get("rubric_version") or ""),
            "sample_generation": int(source.get("sample_generation") or 0),
            "sample_count": int(source.get("sample_count") or 0),
            "sample_membership_count": int(
                source.get("sample_membership_count") or 0
            ),
        }

    covered_by_source = {source_id: 0 for source_id in expected_by_source}
    for review in review_list:
        source_id = str(review.get("source_id") or "")
        expected = expected_by_source.get(source_id)
        actual_campaign = review.get("review_campaign_id")
        actual_campaign = str(actual_campaign) if actual_campaign is not None else None
        if expected is None or not review.get("review_id") or review.get("decision") != "approved":
            raise ReleaseGateError(
                "Release review evidence is incomplete",
                {
                    "document_review_gate": {
                        "status": "blocked",
                        "reason": "review_evidence_incomplete",
                        "source_id": source_id,
                    }
                },
            )
        if expected["review_evidence_status"] == "campaign_pinned":
            matches = (
                actual_campaign == expected["review_campaign_id"]
                and str(review.get("rubric_version") or "") == expected["rubric_version"]
                and int(review.get("sample_generation") or 0)
                == expected["sample_generation"]
            )
        else:
            matches = (
                actual_campaign is None
                and int(review.get("sample_generation") or 0)
                == expected["sample_generation"]
            )
        if not matches:
            raise ReleaseGateError(
                "Release review evidence belongs to another campaign",
                {
                    "document_review_gate": {
                        "status": "blocked",
                        "reason": "review_campaign_mismatch",
                        "source_id": source_id,
                        "document_id": str(review.get("document_id") or ""),
                    }
                },
            )
        covered_by_source[source_id] += 1

    if any(
        count != int(expected_by_source[source_id]["sample_count"])
        for source_id, count in covered_by_source.items()
    ):
        raise ReleaseGateError(
            "Release review campaign has no active evidence",
            {
                "document_review_gate": {
                    "status": "blocked",
                    "reason": "review_campaign_evidence_incomplete",
                }
            },
        )

    return {
        "status": "passed",
        "contract_snapshot_sha256": snapshot_sha256,
        "implementation_bundle_sha256": implementation_sha256,
        "source_count": len(source_list),
        "review_document_count": len(review_list),
    }


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass
class _SemanticStatistics:
    utf8_bytes: int = 0
    codepoints: int = 0
    whitespace_units: int = 0

    def add(self, texts: Iterable[str]) -> None:
        for text in texts:
            if not text:
                continue
            self.utf8_bytes += len(text.encode("utf-8"))
            self.codepoints += len(text)
            self.whitespace_units += len(text.split())

    def estimate(self) -> TokenEstimate:
        lower_bound = max(self.whitespace_units, math.ceil(self.codepoints / 6))
        estimated = max(lower_bound, math.ceil(self.codepoints / 4))
        upper_bound = max(estimated, math.ceil(self.codepoints / 2))
        return TokenEstimate(
            method="unicode-codepoint-range-v1",
            semantic_utf8_bytes=self.utf8_bytes,
            semantic_codepoints=self.codepoints,
            whitespace_units=self.whitespace_units,
            lower_bound=lower_bound,
            estimated_token_count=estimated,
            upper_bound=upper_bound,
        )


def exact_decontamination(
    reference_sources: Iterable[tuple[str, Path]],
    release_sources: Iterable[tuple[str, Path]],
    *,
    max_document_bytes: int,
) -> DecontaminationResult:
    references = tuple(reference_sources)
    candidates = tuple(release_sources)
    if max_document_bytes <= 0:
        raise ValueError("max_document_bytes must be positive")

    with tempfile.TemporaryDirectory(prefix="derlem-decontam-") as temp_directory:
        database_path = Path(temp_directory) / "hashes.sqlite3"
        connection = sqlite3.connect(database_path)
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("CREATE TABLE reference_hashes (digest BLOB PRIMARY KEY) WITHOUT ROWID")

            reference_document_count = 0
            batch: list[tuple[bytes]] = []
            for _, path in references:
                for _, digest in _document_digests(path, max_document_bytes):
                    reference_document_count += 1
                    batch.append((digest,))
                    if len(batch) >= 10_000:
                        connection.executemany(
                            "INSERT OR IGNORE INTO reference_hashes(digest) VALUES (?)",
                            batch,
                        )
                        batch.clear()
            if batch:
                connection.executemany(
                    "INSERT OR IGNORE INTO reference_hashes(digest) VALUES (?)",
                    batch,
                )
            connection.commit()
            reference_unique_count = int(
                connection.execute("SELECT count(*) FROM reference_hashes").fetchone()[0]
            )

            release_document_count = 0
            match_count = 0
            samples: list[DecontaminationMatch] = []
            lookup = connection.cursor()
            for source_sha256, path in candidates:
                for ordinal, digest in _document_digests(path, max_document_bytes):
                    release_document_count += 1
                    if lookup.execute(
                        "SELECT 1 FROM reference_hashes WHERE digest = ?",
                        (digest,),
                    ).fetchone() is None:
                        continue
                    match_count += 1
                    if len(samples) < 20:
                        samples.append(
                            DecontaminationMatch(
                                source_sha256=source_sha256,
                                source_ordinal=ordinal,
                                document_sha256=digest.hex(),
                            )
                        )
        finally:
            connection.close()

    if not references:
        # Referans kumesi bos: karsilastirilacak hicbir sey yoktu. Burada
        # "passed" yazmak frozen manifeste hak edilmemis bir "dekontaminasyon
        # gecti" muhru basar ve manifest degismez oldugu icin geri alinamaz.
        # Yanibasindaki approximate kapi ayni durumda zaten durust davraniyor
        # (not_applicable + no_eval_or_holdout_sources); tutarsizlik bizdeydi.
        # reference_source_count = 0 da manifeste yaziliyor, yani etiket ile
        # sayac birbirini dogruluyor.
        status = "not_evaluated"
    else:
        status = "passed" if match_count == 0 else "blocked"

    return DecontaminationResult(
        status=status,
        method="document-text-sha256-v1",
        reference_source_count=len(references),
        reference_document_count=reference_document_count,
        reference_unique_document_count=reference_unique_count,
        release_source_count=len(candidates),
        release_document_count=release_document_count,
        match_count=match_count,
        sample_matches=tuple(samples),
    )


def build_release_manifest(
    release: dict[str, object],
    sources: list[dict[str, object]],
    gate_results: dict[str, object],
    frozen_at: str,
    contract_snapshot: dict[str, object],
) -> bytes:
    sorted_sources = sorted(sources, key=lambda source: str(source["source_id"]))
    manifest = {
        "schema_version": "derlem.release-manifest.v2",
        "release": {
            "id": str(release["id"]),
            "name": str(release["name"]),
            "version": str(release["version"]),
            "content_purpose": str(release["content_purpose"]),
            "frozen_at": frozen_at,
        },
        "contract_snapshot": contract_snapshot,
        "gate_results": gate_results,
        "sources": sorted_sources,
    }
    return (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def build_mixture_report(
    sources: Iterable[dict[str, object]],
    quality_reviews: Iterable[dict[str, object]] = (),
) -> dict[str, object]:
    source_list = sorted(sources, key=lambda source: str(source["source_id"]))
    quality_review_list = sorted(
        (dict(review) for review in quality_reviews),
        key=lambda review: (str(review.get("source_id", "")), str(review.get("document_id", ""))),
    )
    total_bytes = sum(_non_negative_int(source.get("byte_size")) for source in source_list)
    total_lines = sum(_non_negative_int(source.get("line_count")) for source in source_list)
    dimensions: dict[str, list[dict[str, object]]] = {}

    for dimension in ("language", "domain", "source_type", "license", "rights_status"):
        grouped: dict[str, dict[str, int]] = {}
        for source in source_list:
            value = str(source.get(dimension) or "unknown").strip() or "unknown"
            bucket = grouped.setdefault(value, {"source_count": 0, "byte_size": 0, "line_count": 0})
            bucket["source_count"] += 1
            bucket["byte_size"] += _non_negative_int(source.get("byte_size"))
            bucket["line_count"] += _non_negative_int(source.get("line_count"))

        entries = []
        for value in sorted(grouped):
            bucket = grouped[value]
            entries.append(
                {
                    "value": value,
                    "source_count": bucket["source_count"],
                    "source_share_bps": _share_bps(bucket["source_count"], len(source_list)),
                    "byte_size": bucket["byte_size"],
                    "byte_share_bps": _share_bps(bucket["byte_size"], total_bytes),
                    "line_count": bucket["line_count"],
                    "line_share_bps": _share_bps(bucket["line_count"], total_lines),
                }
            )
        dimensions[dimension] = entries

    return {
        "schema_version": "derlem.mixture-report.v2",
        "status": "reported",
        "totals": {
            "source_count": len(source_list),
            "byte_size": total_bytes,
            "line_count": total_lines,
            "missing_byte_size_count": sum(source.get("byte_size") is None for source in source_list),
            "missing_line_count": sum(source.get("line_count") is None for source in source_list),
        },
        "dimensions": dimensions,
        "quality": _build_quality_mixture(quality_review_list),
    }


def _build_quality_mixture(reviews: list[dict[str, object]]) -> dict[str, object]:
    snapshot = hashlib.sha256()
    seen_documents: set[str] = set()
    multidimensional: list[dict[str, object]] = []
    legacy_document_count = 0
    missing_review_document_count = 0

    for review in reviews:
        source_id = str(review.get("source_id") or "").strip()
        document_id = str(review.get("document_id") or "").strip()
        if not source_id or not document_id:
            raise ValueError("Quality snapshot rows require source_id and document_id")
        if document_id in seen_documents:
            raise ValueError("Quality snapshot contains duplicate document_id")
        seen_documents.add(document_id)

        rubric_version = str(review.get("rubric_version") or "").strip()
        normalized: dict[str, object] = {
            "source_id": source_id,
            "document_id": document_id,
            "document_version": _positive_int(review.get("document_version"), "document_version"),
            "sample_generation": _positive_int(
                review.get("sample_generation"),
                "sample_generation",
            ),
            "object_sha256": str(review.get("object_sha256") or ""),
            "review_id": str(review.get("review_id") or "") or None,
            "decision": str(review.get("decision") or "") or None,
            "review_campaign_id": (
                str(review.get("review_campaign_id"))
                if review.get("review_campaign_id") is not None
                else None
            ),
            "rubric_version": rubric_version or None,
        }

        if rubric_version == QUALITY_RUBRIC:
            if normalized["review_id"] is None:
                raise ValueError("Multidimensional quality row requires review_id")
            if normalized["decision"] != "approved":
                raise ValueError("Multidimensional quality row must be approved")
            for _, field in QUALITY_DIMENSIONS:
                normalized[field] = _quality_score(review.get(field), field)
            multidimensional.append(normalized)
        elif rubric_version == "overall-v1":
            if normalized["review_id"] is None:
                raise ValueError("Legacy quality row requires review_id")
            if normalized["decision"] != "approved":
                raise ValueError("Legacy quality row must be approved")
            normalized["quality_score"] = _quality_score(
                review.get("quality_score"),
                "quality_score",
            )
            for _, field in QUALITY_DIMENSIONS[1:]:
                normalized[field] = None
            legacy_document_count += 1
        elif not rubric_version:
            for _, field in QUALITY_DIMENSIONS:
                normalized[field] = None
            missing_review_document_count += 1
        else:
            raise ValueError(f"Unsupported quality rubric: {rubric_version}")

        snapshot.update(
            (
                json.dumps(
                    normalized,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        )

    sample_document_count = len(reviews)
    scored_document_count = len(multidimensional)
    if scored_document_count == sample_document_count and sample_document_count > 0:
        coverage_status = "complete"
    elif scored_document_count > 0:
        coverage_status = "partial"
    else:
        coverage_status = "unavailable"

    dimensions: dict[str, dict[str, object]] = {}
    for dimension, field in QUALITY_DIMENSIONS:
        scores = [int(review[field]) for review in multidimensional]
        score_sum = sum(scores)
        bands = []
        for band, minimum, maximum in QUALITY_BANDS:
            document_count = sum(minimum <= score <= maximum for score in scores)
            bands.append(
                {
                    "band": band,
                    "score_min": minimum,
                    "score_max": maximum,
                    "document_count": document_count,
                    "document_share_bps": _share_bps(document_count, scored_document_count),
                }
            )
        dimensions[dimension] = {
            "score_sum": score_sum,
            "average_score_milli": (
                (score_sum * 1_000 + scored_document_count // 2) // scored_document_count
                if scored_document_count
                else None
            ),
            "bands": bands,
        }

    return {
        "schema_version": "derlem.quality-mixture.v2",
        "basis": QUALITY_BASIS,
        "rubric_version": QUALITY_RUBRIC,
        "coverage_status": coverage_status,
        "review_snapshot_method": "ordered-sample-review-json-sha256-v3",
        "review_snapshot_sha256": snapshot.hexdigest(),
        "sample_document_count": sample_document_count,
        "scored_document_count": scored_document_count,
        "coverage_bps": _share_bps(scored_document_count, sample_document_count),
        "legacy_document_count": legacy_document_count,
        "missing_review_document_count": missing_review_document_count,
        "dimensions": dimensions,
    }


def _positive_int(value: object, field: str) -> int:
    parsed = int(value or 0)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _quality_score(value: object, field: str) -> int:
    if value is None:
        raise ValueError(f"{field} is required")
    parsed = int(value)
    if not 1 <= parsed <= 5:
        raise ValueError(f"{field} must be between 1 and 5")
    return parsed


def _non_negative_int(value: object) -> int:
    if value is None:
        return 0
    parsed = int(value)
    if parsed < 0:
        raise ValueError("Mixture metrics must be non-negative")
    return parsed


def _share_bps(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return (value * 10_000 + total // 2) // total


def build_release_export(
    release: dict[str, object],
    sources: list[dict[str, object]],
    export_format: str,
    output_path: Path,
    *,
    max_document_bytes: int,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
    progress_interval: int = 50_000,
) -> ExportResult:
    if export_format not in {"jsonl", "txt"}:
        raise ValueError("export_format must be jsonl or txt")
    if max_document_bytes <= 0 or progress_interval <= 0:
        raise ValueError("export limits must be positive")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    byte_size = 0
    record_count = 0
    input_bytes_processed = 0
    source_record_counts: dict[str, int] = {}
    record_type_counts: dict[str, int] = {}
    semantic_statistics = _SemanticStatistics()
    sorted_sources = sorted(sources, key=lambda source: str(source["source_id"]))

    with output_path.open("wb") as output:
        for source_index, source in enumerate(sorted_sources, start=1):
            source_id = str(source["source_id"])
            source_sha256 = str(source["source_sha256"])
            source_records = 0
            for ordinal, raw_line, oversized in _bounded_lines(
                Path(str(source["path"])),
                max_document_bytes,
            ):
                if oversized:
                    raise ReleaseGateError(
                        f"Document at line {ordinal} exceeds the export limit",
                        {
                            "export": {
                                "status": "blocked",
                                "reason": "document_too_large",
                                "source_id": source_id,
                                "source_ordinal": ordinal,
                                "max_document_bytes": max_document_bytes,
                            }
                        },
                    )
                assert raw_line is not None
                input_bytes_processed += len(raw_line.encode("utf-8")) + 1
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    canonical = parse_canonical_sample(stripped, str(release["content_purpose"]))
                except CanonicalSampleError as error:
                    raise ReleaseGateError(
                        f"Invalid canonical sample at line {ordinal}: {error}",
                        {
                            "export": {
                                "status": "blocked",
                                "reason": "invalid_canonical_sample",
                                "source_id": source_id,
                                "source_ordinal": ordinal,
                                "validation_error": str(error),
                            }
                        },
                    ) from error

                if canonical is not None:
                    if export_format != "jsonl":
                        raise ReleaseGateError(
                            "Structured canonical records require JSONL export",
                            {
                                "export": {
                                    "status": "blocked",
                                    "reason": "structured_record_requires_jsonl",
                                    "source_id": source_id,
                                    "source_ordinal": ordinal,
                                    "record_type": canonical.record_type,
                                }
                            },
                        )
                    canonical_bytes = json.dumps(
                        canonical.value,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
                    source_document_sha256 = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
                    stable_id = hashlib.sha256(
                        f"{source_sha256}:{ordinal}:{canonical_sha256}".encode("ascii")
                    ).hexdigest()
                    record = {
                        "export_schema_version": "derlem.canonical-export-record.v1",
                        "id": stable_id,
                        "record_type": canonical.record_type,
                        "sample": canonical.value,
                        "lineage": {
                            "canonical_payload_sha256": canonical_sha256,
                            "domain": str(source["domain"]),
                            "language": str(source["language"]),
                            "license": str(source["license"]),
                            "source_document_sha256": source_document_sha256,
                            "source_id": source_id,
                            "source_ordinal": ordinal,
                            "source_sha256": source_sha256,
                        },
                    }
                    encoded = (
                        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    ).encode("utf-8")
                    record_type = canonical.record_type
                    semantic_statistics.add(canonical.semantic_texts)
                else:
                    text, external_id = _document_from_line(stripped)
                    if not text:
                        continue
                    document_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    stable_id = hashlib.sha256(
                        f"{source_sha256}:{ordinal}:{document_sha256}".encode("ascii")
                    ).hexdigest()
                    if export_format == "jsonl":
                        record = {
                            "id": stable_id,
                            "text": text,
                            "metadata": {
                                "content_purpose": str(release["content_purpose"]),
                                "document_sha256": document_sha256,
                                "domain": str(source["domain"]),
                                "external_id": external_id,
                                "language": str(source["language"]),
                                "license": str(source["license"]),
                                "source_id": source_id,
                                "source_ordinal": ordinal,
                                "source_sha256": source_sha256,
                            },
                        }
                        encoded = (
                            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                            + "\n"
                        ).encode("utf-8")
                    else:
                        single_line_text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
                        encoded = (single_line_text + "\n").encode("utf-8")
                    record_type = "text"
                    semantic_statistics.add((text,))

                output.write(encoded)
                digest.update(encoded)
                byte_size += len(encoded)
                record_count += 1
                source_records += 1
                record_type_counts[record_type] = record_type_counts.get(record_type, 0) + 1
                if progress_callback is not None and record_count % progress_interval == 0:
                    token_estimate = semantic_statistics.estimate()
                    progress_callback(
                        {
                            "input_bytes_processed": input_bytes_processed,
                            "records_written": record_count,
                            "sources_completed": source_index - 1,
                            "source_count": len(sorted_sources),
                            "output_bytes_written": byte_size,
                            "estimated_tokens": token_estimate.estimated_token_count,
                        }
                    )
            source_record_counts[source_id] = source_records
            if progress_callback is not None:
                token_estimate = semantic_statistics.estimate()
                progress_callback(
                    {
                        "input_bytes_processed": input_bytes_processed,
                        "records_written": record_count,
                        "sources_completed": source_index,
                        "source_count": len(sorted_sources),
                        "output_bytes_written": byte_size,
                        "estimated_tokens": token_estimate.estimated_token_count,
                    }
                )

    return ExportResult(
        format=export_format,
        media_type="application/x-ndjson" if export_format == "jsonl" else "text/plain; charset=utf-8",
        sha256=digest.hexdigest(),
        byte_size=byte_size,
        record_count=record_count,
        source_count=len(sorted_sources),
        source_record_counts=source_record_counts,
        record_type_counts=record_type_counts,
        token_estimate=semantic_statistics.estimate(),
    )


def build_export_manifest(
    release: dict[str, object],
    sources: list[dict[str, object]],
    result: ExportResult,
) -> bytes:
    manifest_sources = []
    for source in sorted(sources, key=lambda item: str(item["source_id"])):
        source_id = str(source["source_id"])
        manifest_sources.append(
            {
                "source_id": source_id,
                "source_sha256": str(source["source_sha256"]),
                "record_count": result.source_record_counts.get(source_id, 0),
                "language": str(source["language"]),
                "domain": str(source["domain"]),
                "license": str(source["license"]),
            }
        )
    manifest = {
        "schema_version": "derlem.export-manifest.v2",
        "release": {
            "id": str(release["id"]),
            "name": str(release["name"]),
            "version": str(release["version"]),
            "content_purpose": str(release["content_purpose"]),
            "frozen_at": str(release["frozen_at"]),
            "manifest_sha256": str(release["manifest_sha256"]),
        },
        "export": {
            "format": result.format,
            "media_type": result.media_type,
            "sha256": result.sha256,
            "byte_size": result.byte_size,
            "record_count": result.record_count,
            "document_id_method": "source-sha256-ordinal-payload-sha256-v2",
            "record_type_counts": result.record_type_counts,
            "token_estimate": result.token_estimate.to_dict(),
        },
        "sources": manifest_sources,
    }
    return (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _document_digests(path: Path, max_document_bytes: int) -> Iterator[tuple[int, bytes]]:
    for ordinal, raw_line, oversized in _bounded_lines(path, max_document_bytes):
        if oversized:
            raise ReleaseGateError(
                f"Document at line {ordinal} exceeds the decontamination limit",
                {
                    "decontamination": {
                        "status": "blocked",
                        "reason": "document_too_large",
                        "source_ordinal": ordinal,
                        "max_document_bytes": max_document_bytes,
                    }
                },
            )
        assert raw_line is not None
        stripped = raw_line.strip()
        if not stripped:
            continue
        text, _ = _document_from_line(stripped)
        if not text:
            continue
        yield ordinal, hashlib.sha256(text.encode("utf-8")).digest()
