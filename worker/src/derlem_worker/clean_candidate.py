from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

import psycopg
from psycopg.rows import dict_row

from derlem_worker.config import load_config
from derlem_worker.fingerprints import FINGERPRINT_VERSION, document_fingerprint
from derlem_worker.pii import PII_KEYS, count_pii_in_text
from derlem_worker.quality_filters import (
    QUALITY_POLICY_NONE,
    SUPPORTED_QUALITY_POLICIES,
    quality_rejection_reasons,
)
from derlem_worker.sampling import _bounded_lines, _document_from_line


CLEAN_CANDIDATE_VERSION = "clean-candidate-v1"
CLEAN_CANDIDATE_V2_VERSION = "clean-candidate-v2"


@dataclass(frozen=True)
class CleanCandidateReport:
    algorithm_version: str
    quality_filter_version: str | None
    fingerprint_version: str
    generated_at: str
    source_id: str | None
    source_name: str | None
    source_sha256: str | None
    input_path: str
    output_path: str
    quality_rejections_path: str | None
    max_document_bytes: int
    total_lines: int
    written_lines: int
    removed_pii_lines: int
    removed_duplicate_lines: int
    removed_oversized_lines: int
    removed_quality_lines: int
    skipped_blank_lines: int
    indexed_fingerprints: int
    kept_short_or_unfingerprinted_lines: int
    pii_findings: dict[str, int]
    pii_line_counts: dict[str, int]
    quality_reason_document_counts: dict[str, int]
    quality_rejections_sha256: str | None
    quality_rejections_byte_size: int
    output_sha256: str
    output_byte_size: int


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local clean-candidate file from a Derlem source")
    parser.add_argument("--source-id", help="Derlem source id to read from object storage")
    parser.add_argument("--input-path", type=Path, help="Direct input file path for local experiments")
    parser.add_argument("--output-dir", type=Path, default=Path("var/derived"))
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--quality-rejections-path",
        type=Path,
        help="Optional JSONL audit path containing only rejected ordinals and reason codes",
    )
    parser.add_argument("--max-document-bytes", type=int)
    parser.add_argument("--limit-lines", type=int, help="Development-only limit; do not use for final candidates")
    parser.add_argument(
        "--quality-policy",
        choices=sorted(SUPPORTED_QUALITY_POLICIES),
        default=QUALITY_POLICY_NONE,
        help="Optional versioned hard-rejection policy; defaults to the v1 behavior",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing output/manifest paths")
    args = parser.parse_args()

    if bool(args.source_id) == bool(args.input_path):
        parser.error("Exactly one of --source-id or --input-path is required")
    if args.limit_lines is not None and args.limit_lines <= 0:
        parser.error("--limit-lines must be positive")

    config = load_config()
    max_document_bytes = args.max_document_bytes or config.max_document_bytes
    if max_document_bytes <= 0:
        parser.error("--max-document-bytes must be positive")

    source: dict[str, Any] | None = None
    if args.source_id:
        source = load_source(config.database_url, config.storage_root, args.source_id)
        input_path = Path(str(source["object_path"]))
        output_path = resolve_output_path(
            args.output_dir,
            args.output_path,
            source,
            args.limit_lines,
            quality_policy=args.quality_policy,
        )
    else:
        input_path = args.input_path.resolve(strict=True)
        output_path = resolve_output_path(
            args.output_dir,
            args.output_path,
            None,
            args.limit_lines,
            input_path=input_path,
            quality_policy=args.quality_policy,
        )

    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    quality_rejections_path: Path | None = None
    if args.quality_policy != QUALITY_POLICY_NONE:
        quality_rejections_path = (
            args.quality_rejections_path.resolve()
            if args.quality_rejections_path
            else output_path.with_suffix(output_path.suffix + ".rejections.jsonl")
        )
    elif args.quality_rejections_path:
        parser.error("--quality-rejections-path requires a non-default --quality-policy")
    if quality_rejections_path == manifest_path:
        parser.error("--quality-rejections-path must be distinct from the manifest path")
    ensure_writable_target(output_path, args.force)
    ensure_writable_target(manifest_path, args.force)
    if quality_rejections_path is not None:
        ensure_writable_target(quality_rejections_path, args.force)

    report = derive_clean_candidate(
        input_path,
        output_path,
        source=source,
        max_document_bytes=max_document_bytes,
        limit_lines=args.limit_lines,
        quality_policy=args.quality_policy,
        quality_rejections_path=quality_rejections_path,
    )
    write_json_atomic(manifest_path, asdict(report))
    print(json.dumps({"output": str(output_path), "manifest": str(manifest_path), "report": asdict(report)}, ensure_ascii=False, indent=2))


def load_source(database_url: str, storage_root: Path, source_id: str) -> dict[str, Any]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT
                source.id::text,
                source.name,
                source.object_sha256,
                source.content_purpose,
                source.approval_status,
                source.pii_status,
                source.duplicate_status,
                source.normalized_dedup_status,
                object.storage_key
            FROM sources AS source
            JOIN storage_objects AS object ON object.sha256 = source.object_sha256
            WHERE source.id = %s
            """,
            (source_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"Source was not found or has no stored object: {source_id}")
    source = dict(row)
    object_path = (storage_root / str(source["storage_key"])).resolve(strict=True)
    object_path.relative_to(storage_root.resolve())
    source["object_path"] = str(object_path)
    return source


def derive_clean_candidate(
    input_path: Path,
    output_path: Path,
    *,
    source: dict[str, Any] | None,
    max_document_bytes: int,
    limit_lines: int | None = None,
    quality_policy: str = QUALITY_POLICY_NONE,
    quality_rejections_path: Path | None = None,
) -> CleanCandidateReport:
    if quality_policy not in SUPPORTED_QUALITY_POLICIES:
        raise ValueError(f"Unsupported quality policy: {quality_policy}")
    input_path = input_path.resolve(strict=True)
    output_path = output_path.resolve()
    if input_path == output_path:
        raise RuntimeError("Output path must not be the same as input path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if quality_rejections_path is not None:
        if quality_policy == QUALITY_POLICY_NONE:
            raise ValueError("A quality rejections path requires a non-default quality policy")
        quality_rejections_path = quality_rejections_path.resolve()
        if quality_rejections_path in {input_path, output_path}:
            raise RuntimeError("Quality rejections path must be distinct from input and output")
        quality_rejections_path.parent.mkdir(parents=True, exist_ok=True)

    seen_fingerprints: set[str] = set()
    pii_findings = {key: 0 for key in PII_KEYS}
    pii_line_counts = {key: 0 for key in PII_KEYS}
    total_lines = 0
    written_lines = 0
    removed_pii_lines = 0
    removed_duplicate_lines = 0
    removed_oversized_lines = 0
    removed_quality_lines = 0
    skipped_blank_lines = 0
    indexed_fingerprints = 0
    kept_short_or_unfingerprinted_lines = 0
    hasher = hashlib.sha256()
    output_byte_size = 0
    quality_rejections_hasher = hashlib.sha256()
    quality_rejections_byte_size = 0
    quality_reason_document_counts: Counter[str] = Counter()

    file_descriptor, temp_name = tempfile.mkstemp(prefix=f"{output_path.name}.", suffix=".tmp", dir=output_path.parent)
    temp_path = Path(temp_name)
    quality_rejections_descriptor = -1
    quality_rejections_temp_path: Path | None = None
    if quality_rejections_path is not None:
        quality_rejections_descriptor, quality_rejections_temp_name = tempfile.mkstemp(
            prefix=f"{quality_rejections_path.name}.",
            suffix=".tmp",
            dir=quality_rejections_path.parent,
        )
        quality_rejections_temp_path = Path(quality_rejections_temp_name)
    try:
        with ExitStack() as stack:
            destination = stack.enter_context(os.fdopen(file_descriptor, "wb"))
            file_descriptor = -1
            quality_rejections_destination = None
            if quality_rejections_descriptor >= 0:
                quality_rejections_destination = stack.enter_context(
                    os.fdopen(quality_rejections_descriptor, "wb")
                )
                quality_rejections_descriptor = -1
            for ordinal, raw_line, oversized in _bounded_lines(input_path, max_document_bytes):
                if limit_lines is not None and ordinal > limit_lines:
                    break
                total_lines += 1
                if oversized:
                    removed_oversized_lines += 1
                    continue
                assert raw_line is not None

                stripped = raw_line.strip()
                if not stripped:
                    skipped_blank_lines += 1
                    continue

                counts = count_pii_in_text(raw_line)
                has_pii = False
                for key in PII_KEYS:
                    count = int(counts.get(key, 0))
                    if count <= 0:
                        continue
                    has_pii = True
                    pii_findings[key] += count
                    pii_line_counts[key] += 1
                if has_pii:
                    removed_pii_lines += 1
                    continue

                text, _ = _document_from_line(stripped)
                quality_reasons = quality_rejection_reasons(text, quality_policy)
                if quality_reasons:
                    removed_quality_lines += 1
                    quality_reason_document_counts.update(quality_reasons)
                    if quality_rejections_destination is not None:
                        rejection_record = (
                            json.dumps(
                                {
                                    "source_ordinal": ordinal,
                                    "reasons": list(quality_reasons),
                                },
                                ensure_ascii=True,
                                separators=(",", ":"),
                                sort_keys=True,
                            ).encode("utf-8")
                            + b"\n"
                        )
                        quality_rejections_destination.write(rejection_record)
                        quality_rejections_hasher.update(rejection_record)
                        quality_rejections_byte_size += len(rejection_record)
                    continue

                fingerprint = document_fingerprint(text) if text else None
                if fingerprint is None:
                    kept_short_or_unfingerprinted_lines += 1
                else:
                    normalized_sha256, _ = fingerprint
                    if normalized_sha256 in seen_fingerprints:
                        removed_duplicate_lines += 1
                        continue
                    seen_fingerprints.add(normalized_sha256)
                    indexed_fingerprints += 1

                encoded = raw_line.encode("utf-8") + b"\n"
                destination.write(encoded)
                hasher.update(encoded)
                output_byte_size += len(encoded)
                written_lines += 1

            destination.flush()
            os.fsync(destination.fileno())
            if quality_rejections_destination is not None:
                quality_rejections_destination.flush()
                os.fsync(quality_rejections_destination.fileno())
        temp_path.replace(output_path)
        if (
            quality_rejections_temp_path is not None
            and quality_rejections_path is not None
        ):
            quality_rejections_temp_path.replace(quality_rejections_path)
    finally:
        temp_path.unlink(missing_ok=True)
        if quality_rejections_temp_path is not None:
            quality_rejections_temp_path.unlink(missing_ok=True)
        if file_descriptor >= 0:
            try:
                os.close(file_descriptor)
            except OSError:
                pass
        if quality_rejections_descriptor >= 0:
            try:
                os.close(quality_rejections_descriptor)
            except OSError:
                pass

    source_id = str(source["id"]) if source else None
    return CleanCandidateReport(
        algorithm_version=(
            CLEAN_CANDIDATE_VERSION
            if quality_policy == QUALITY_POLICY_NONE
            else CLEAN_CANDIDATE_V2_VERSION
        ),
        quality_filter_version=(
            None if quality_policy == QUALITY_POLICY_NONE else quality_policy
        ),
        fingerprint_version=FINGERPRINT_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
        source_id=source_id,
        source_name=str(source["name"]) if source else None,
        source_sha256=str(source["object_sha256"]) if source else None,
        input_path=str(input_path),
        output_path=str(output_path),
        quality_rejections_path=(
            str(quality_rejections_path)
            if quality_rejections_path is not None
            else None
        ),
        max_document_bytes=max_document_bytes,
        total_lines=total_lines,
        written_lines=written_lines,
        removed_pii_lines=removed_pii_lines,
        removed_duplicate_lines=removed_duplicate_lines,
        removed_oversized_lines=removed_oversized_lines,
        removed_quality_lines=removed_quality_lines,
        skipped_blank_lines=skipped_blank_lines,
        indexed_fingerprints=indexed_fingerprints,
        kept_short_or_unfingerprinted_lines=kept_short_or_unfingerprinted_lines,
        pii_findings=pii_findings,
        pii_line_counts=pii_line_counts,
        quality_reason_document_counts=dict(sorted(quality_reason_document_counts.items())),
        quality_rejections_sha256=(
            quality_rejections_hasher.hexdigest()
            if quality_rejections_path is not None
            else None
        ),
        quality_rejections_byte_size=quality_rejections_byte_size,
        output_sha256=hasher.hexdigest(),
        output_byte_size=output_byte_size,
    )


def resolve_output_path(
    output_dir: Path,
    output_path: Path | None,
    source: dict[str, Any] | None,
    limit_lines: int | None,
    *,
    input_path: Path | None = None,
    quality_policy: str = QUALITY_POLICY_NONE,
) -> Path:
    if output_path:
        return output_path.resolve()
    output_dir = output_dir.resolve()
    if source:
        stem = f"{slugify(str(source['name']))}_{str(source['id'])[:8]}_clean_candidate"
    else:
        assert input_path is not None
        stem = f"{slugify(input_path.stem)}_clean_candidate"
    if quality_policy != QUALITY_POLICY_NONE:
        stem = f"{stem}_v2"
    if limit_lines is not None:
        stem = f"{stem}_first_{limit_lines}"
    return output_dir / f"{stem}.txt"


def write_json_atomic(path: Path, value: Any) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f"{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as destination:
            file_descriptor = -1
            json.dump(value, destination, ensure_ascii=False, indent=2)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
        if file_descriptor >= 0:
            try:
                os.close(file_descriptor)
            except OSError:
                pass


def ensure_writable_target(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise RuntimeError(f"Refusing to overwrite existing file without --force: {path}")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    return slug or "source"


if __name__ == "__main__":
    main()
