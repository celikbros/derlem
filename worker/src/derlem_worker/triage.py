from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from derlem_worker.config import load_config
from derlem_worker.pii import PII_KEYS, count_pii_in_text


@dataclass(frozen=True)
class PIILineTriage:
    total_lines: int
    pii_line_count: int
    finding_counts: dict[str, int]
    line_counts: dict[str, int]
    first_ordinals_by_type: dict[str, list[int]]
    first_any_pii_ordinals: list[int]


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a local source gate triage report")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("var/reports"))
    parser.add_argument("--scan-pii-lines", action="store_true")
    parser.add_argument("--max-ordinals", type=int, default=50)
    args = parser.parse_args()

    if args.max_ordinals <= 0:
        parser.error("--max-ordinals must be positive")

    config = load_config()
    report = build_report(
        database_url=config.database_url,
        storage_root=config.storage_root,
        source_id=args.source_id,
        scan_pii_lines=args.scan_pii_lines,
        max_ordinals=args.max_ordinals,
    )
    paths = write_report(report, args.output_dir)
    print(json.dumps({key: str(path) for key, path in paths.items()}, ensure_ascii=False, indent=2))


def build_report(
    *,
    database_url: str,
    storage_root: Path,
    source_id: str,
    scan_pii_lines: bool,
    max_ordinals: int,
) -> dict[str, Any]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        source = connection.execute(
            """
            SELECT
                source.id::text,
                source.name,
                source.source_type,
                source.content_purpose,
                source.license,
                source.rights_status,
                source.license_evidence_ref,
                source.language,
                source.domain,
                source.lineage_ref,
                source.object_sha256,
                source.byte_size,
                source.line_count,
                source.document_count,
                source.detected_encoding,
                source.pii_status,
                source.duplicate_status,
                source.normalized_dedup_status,
                source.normalized_duplicate_count,
                source.normalized_duplicate_source_count,
                source.document_sampling_status,
                source.approval_status,
                source.risk_level,
                source.updated_at,
                object.storage_key,
                object.immutable
            FROM sources AS source
            LEFT JOIN storage_objects AS object ON object.sha256 = source.object_sha256
            WHERE source.id = %s
            """,
            (source_id,),
        ).fetchone()
        if source is None:
            raise RuntimeError(f"Source was not found: {source_id}")

        jobs = connection.execute(
            """
            SELECT DISTINCT ON (job_type)
                job_type,
                status,
                attempts,
                locked_by,
                locked_at,
                completed_at,
                last_error,
                result
            FROM background_jobs
            WHERE payload->>'source_id' = %s
            ORDER BY job_type, created_at DESC
            """,
            (source_id,),
        ).fetchall()

        pii_scan = connection.execute(
            """
            SELECT scanner_version, status, findings, scanned_at
            FROM pii_scans
            WHERE source_id = %s
            ORDER BY scanned_at DESC
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()
        normalized_dedup_audit = connection.execute(
            """
            SELECT action, details, created_at
            FROM audit_events
            WHERE entity_type = 'source'
              AND entity_id = %s
              AND action IN ('source.normalized_dedup_recomputed', 'source.normalized_dedup_checked')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()

    source_dict = dict(source)
    object_path = None
    storage_key = source_dict.get("storage_key")
    if storage_key:
        object_path = (storage_root / str(storage_key)).resolve()
        object_path.relative_to(storage_root.resolve())

    pii_line_triage = None
    if scan_pii_lines:
        if object_path is None:
            raise RuntimeError("Source does not have a stored object")
        pii_line_triage = asdict(collect_pii_line_triage(object_path, max_ordinals=max_ordinals))

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": _json_safe(source_dict),
        "storage": {
            "object_path": str(object_path) if object_path else None,
            "storage_key": storage_key,
            "immutable": source_dict.get("immutable"),
        },
        "latest_jobs": {str(row["job_type"]): _json_safe(dict(row)) for row in jobs},
        "pii_scan": _json_safe(dict(pii_scan)) if pii_scan else None,
        "normalized_dedup_audit": _json_safe(dict(normalized_dedup_audit)) if normalized_dedup_audit else None,
        "pii_line_triage": pii_line_triage,
        "release_blockers": release_blockers(source_dict),
    }


def collect_pii_line_triage(path: Path, *, max_ordinals: int) -> PIILineTriage:
    finding_counts = {key: 0 for key in PII_KEYS}
    line_counts = {key: 0 for key in PII_KEYS}
    first_ordinals_by_type = {key: [] for key in PII_KEYS}
    first_any_pii_ordinals: list[int] = []
    total_lines = 0
    pii_line_count = 0

    with path.open("r", encoding="utf-8", errors="strict") as source:
        for ordinal, line in enumerate(source, start=1):
            total_lines += 1
            counts = count_pii_in_text(line)
            has_pii = False
            for key in PII_KEYS:
                count = int(counts.get(key, 0))
                if count <= 0:
                    continue
                has_pii = True
                finding_counts[key] += count
                line_counts[key] += 1
                if len(first_ordinals_by_type[key]) < max_ordinals:
                    first_ordinals_by_type[key].append(ordinal)
            if has_pii:
                pii_line_count += 1
                if len(first_any_pii_ordinals) < max_ordinals:
                    first_any_pii_ordinals.append(ordinal)

    return PIILineTriage(
        total_lines=total_lines,
        pii_line_count=pii_line_count,
        finding_counts=finding_counts,
        line_counts=line_counts,
        first_ordinals_by_type=first_ordinals_by_type,
        first_any_pii_ordinals=first_any_pii_ordinals,
    )


def release_blockers(source: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if source.get("rights_status") != "cleared":
        blockers.append("rights_not_cleared")
    if not source.get("license_evidence_ref"):
        blockers.append("license_evidence_missing")
    if source.get("pii_status") != "clear":
        blockers.append("pii_not_clear")
    if source.get("duplicate_status") != "unique":
        blockers.append("exact_duplicate_not_clear")
    if source.get("normalized_dedup_status") != "unique":
        blockers.append("normalized_dedup_not_clear")
    if source.get("document_sampling_status") != "sampled":
        blockers.append("documents_not_sampled")
    elif (
        int(source.get("sampled_document_count") or 0) <= 0
        or int(source.get("reviewed_document_count") or 0) != int(source.get("sampled_document_count") or 0)
        or int(source.get("approved_document_count") or 0) != int(source.get("sampled_document_count") or 0)
        or int(source.get("flagged_document_count") or 0) > 0
    ):
        blockers.append("document_sample_review_incomplete")
    return blockers


def write_report(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source = report["source"]
    stem = f"{source['name']}_{source['id'][:8]}_triage"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def render_markdown(report: dict[str, Any]) -> str:
    source = report["source"]
    lines = [
        f"# Source Triage: {source['name']}",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Source id: `{source['id']}`",
        f"- SHA256: `{source.get('object_sha256')}`",
        f"- Purpose: `{source.get('content_purpose')}`",
        f"- Approval status: `{source.get('approval_status')}`",
        f"- Risk level: `{source.get('risk_level')}`",
        "",
        "## Gate Summary",
        "",
        "| Gate | Status | Detail |",
        "|---|---|---|",
        f"| Rights | `{source.get('rights_status')}` | license evidence: `{source.get('license_evidence_ref')}` |",
        f"| PII | `{source.get('pii_status')}` | latest scan below |",
        f"| Exact file dedup | `{source.get('duplicate_status')}` | byte-level SHA256 |",
        (
            f"| Normalized document dedup | `{source.get('normalized_dedup_status')}` | "
            f"duplicates: `{source.get('normalized_duplicate_count')}`, "
            f"sources: `{source.get('normalized_duplicate_source_count')}` |"
        ),
        f"| Document sampling | `{source.get('document_sampling_status')}` | document count: `{source.get('document_count')}` |",
        "",
        "## Release Blockers",
        "",
    ]
    blockers = report["release_blockers"]
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- None")

    pii_scan = report.get("pii_scan")
    if pii_scan:
        lines.extend(
            [
                "",
                "## PII Scan",
                "",
                f"- Scanner: `{pii_scan.get('scanner_version')}`",
                f"- Status: `{pii_scan.get('status')}`",
                f"- Findings: `{json.dumps(pii_scan.get('findings', {}), ensure_ascii=False)}`",
            ]
        )

    normalized_job = report.get("latest_jobs", {}).get("index_document_fingerprints")
    normalized_audit = report.get("normalized_dedup_audit")
    if normalized_job and normalized_job.get("result"):
        result = normalized_job["result"]
        audit_details = normalized_audit.get("details") if normalized_audit else {}
        lines.extend(
            [
                "",
                "## Normalized Dedup Result",
                "",
                f"- Status: `{source.get('normalized_dedup_status')}`",
                f"- Duplicate count: `{source.get('normalized_duplicate_count')}`",
                f"- Duplicate source count: `{source.get('normalized_duplicate_source_count')}`",
                f"- Total documents: `{result.get('total_documents')}`",
                f"- Indexed documents: `{result.get('indexed_documents')}`",
                f"- Skipped oversized: `{result.get('skipped_oversized')}`",
                f"- Skipped too short: `{result.get('skipped_too_short')}`",
            ]
        )
        if audit_details:
            lines.append(f"- Latest audit action: `{normalized_audit.get('action')}`")
            excluded_source_ids = audit_details.get("lineage_excluded_source_ids")
            if excluded_source_ids:
                lines.append(
                    f"- Lineage-excluded sources: `{json.dumps(excluded_source_ids, ensure_ascii=False)}`"
                )
            elif audit_details.get("lineage_excluded_source_id"):
                # Eski audit olaylari okunabilir kalir; yeni worker yalnizca
                # cogu ancestor'u ifade eden plural alani yazar.
                lines.append(f"- Lineage-excluded source: `{audit_details.get('lineage_excluded_source_id')}`")

    pii_line_triage = report.get("pii_line_triage")
    if pii_line_triage:
        lines.extend(
            [
                "",
                "## Optional PII Line Triage",
                "",
                f"- Total lines: `{pii_line_triage['total_lines']}`",
                f"- Lines with any PII: `{pii_line_triage['pii_line_count']}`",
                f"- Finding counts: `{json.dumps(pii_line_triage['finding_counts'], ensure_ascii=False)}`",
                f"- Line counts: `{json.dumps(pii_line_triage['line_counts'], ensure_ascii=False)}`",
                f"- First ordinals by type: `{json.dumps(pii_line_triage['first_ordinals_by_type'], ensure_ascii=False)}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Note",
            "",
            "This report intentionally does not include raw document text or PII values.",
            "",
        ]
    )
    return "\n".join(lines)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


if __name__ == "__main__":
    main()
