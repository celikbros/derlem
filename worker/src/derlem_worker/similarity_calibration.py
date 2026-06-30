from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import heapq
import json
from pathlib import Path
import sys
from typing import Callable, Iterable

import psycopg
from psycopg.rows import dict_row

from derlem_worker.config import load_config
from derlem_worker.fingerprints import normalize_document_text
from derlem_worker.sampling import _bounded_lines
from derlem_worker.similarity import (
    RELEASE_NEAR_DUP_BAND_BITS,
    RELEASE_NEAR_DUP_BAND_COUNT,
    RELEASE_NEAR_DUP_THRESHOLD,
    SIMHASH_VERSION,
    _similarity_text_from_line,
    document_simhash,
    hamming_distance,
)


CALIBRATION_SCHEMA_VERSION = "derlem.similarity-calibration.v1"
CALIBRATION_METHOD = "deterministic-bottom-k-synthetic-perturbation-v1"
SAMPLE_METHOD = "source-ordinal-sha256-bottom-k-v1"
PERTURBATION_METHOD = "token-edit-suite-v1"
CONTENT_PURPOSES = {
    "pretrain",
    "instruction",
    "preference",
    "eval",
    "holdout",
    "post_training",
}
MAX_SAMPLE_SIZE = 2_000


@dataclass(frozen=True)
class CalibrationSource:
    source_id: str | None
    name: str
    sha256: str
    path: Path


@dataclass(frozen=True)
class _SampledDocument:
    priority: int
    source_sha256: str
    source_ordinal: int
    text: str
    signature: int
    token_count: int


@dataclass
class _ScanStats:
    lines_read: int = 0
    documents_scanned: int = 0
    eligible_documents: int = 0
    skipped_blank: int = 0
    skipped_too_short: int = 0
    skipped_oversized: int = 0


def calibrate_similarity(
    sources: Iterable[CalibrationSource],
    *,
    content_purpose: str,
    max_document_bytes: int,
    sample_size: int = 1_000,
    threshold_max: int = 10,
    closest_pair_limit: int = 100,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
    progress_interval: int = 100_000,
) -> dict[str, object]:
    source_list = sorted(sources, key=lambda source: (source.sha256, source.name))
    if not source_list:
        raise ValueError("At least one calibration source is required")
    if content_purpose not in CONTENT_PURPOSES:
        raise ValueError("Unsupported content_purpose")
    if max_document_bytes <= 0:
        raise ValueError("max_document_bytes must be positive")
    if not 2 <= sample_size <= MAX_SAMPLE_SIZE:
        raise ValueError(f"sample_size must be between 2 and {MAX_SAMPLE_SIZE}")
    if not 0 <= threshold_max <= 16:
        raise ValueError("threshold_max must be between 0 and 16")
    if closest_pair_limit <= 0:
        raise ValueError("closest_pair_limit must be positive")
    if progress_interval <= 0:
        raise ValueError("progress_interval must be positive")

    sampled, stats = _sample_documents(
        source_list,
        max_document_bytes=max_document_bytes,
        sample_size=sample_size,
        progress_callback=progress_callback,
        progress_interval=progress_interval,
    )
    perturbation_histograms = {
        name: [0] * 65
        for name in ("drop_middle_token", "replace_middle_token", "swap_middle_tokens", "drop_middle_span")
    }
    length_bucket_histograms = {
        bucket: [0] * 65
        for bucket in ("short_5_7", "medium_8_15", "long_16_31", "very_long_32_plus")
    }
    for document in sampled:
        tokens = normalize_document_text(document.text).split()
        for name, perturbed in _perturbations(tokens):
            signature = document_simhash(" ".join(perturbed))
            if signature is None:
                continue
            distance = hamming_distance(document.signature, signature)
            perturbation_histograms[name][distance] += 1
            length_bucket_histograms[_length_bucket(document.token_count)][distance] += 1

    corpus_histogram, closest_pairs = _corpus_pair_distances(sampled, closest_pair_limit)
    perturbation_total_histogram = [
        sum(histogram[distance] for histogram in perturbation_histograms.values())
        for distance in range(65)
    ]
    perturbation_count = sum(perturbation_total_histogram)
    corpus_pair_count = sum(corpus_histogram)
    thresholds = []
    for threshold in range(threshold_max + 1):
        matched_perturbations = sum(perturbation_total_histogram[: threshold + 1])
        matched_corpus_pairs = sum(corpus_histogram[: threshold + 1])
        thresholds.append(
            {
                "threshold": threshold,
                "synthetic_match_count": matched_perturbations,
                "synthetic_recall_bps": _share_bps(matched_perturbations, perturbation_count),
                "corpus_pair_count": matched_corpus_pairs,
                "corpus_pair_rate_bps": _share_bps(matched_corpus_pairs, corpus_pair_count),
                "release_lsh_complete": threshold < RELEASE_NEAR_DUP_BAND_COUNT,
                "synthetic_recall_bps_by_length_bucket": {
                    bucket: _share_bps(
                        sum(histogram[: threshold + 1]),
                        sum(histogram),
                    )
                    for bucket, histogram in sorted(length_bucket_histograms.items())
                },
            }
        )

    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "method": CALIBRATION_METHOD,
        "content_purpose": content_purpose,
        "sources": [
            {
                "source_id": source.source_id,
                "name": source.name,
                "sha256": source.sha256,
            }
            for source in source_list
        ],
        "sampling": {
            "method": SAMPLE_METHOD,
            "requested_sample_size": sample_size,
            "sampled_document_count": len(sampled),
            "max_document_bytes": max_document_bytes,
            "lines_read": stats.lines_read,
            "documents_scanned": stats.documents_scanned,
            "eligible_documents": stats.eligible_documents,
            "skipped_blank": stats.skipped_blank,
            "skipped_too_short": stats.skipped_too_short,
            "skipped_oversized": stats.skipped_oversized,
            "sampled_token_lengths": _token_length_summary(sampled),
        },
        "simhash": {
            "version": SIMHASH_VERSION,
            "signature_bits": 64,
        },
        "synthetic_perturbations": {
            "method": PERTURBATION_METHOD,
            "count": perturbation_count,
            "distance_histogram": perturbation_total_histogram,
            "distance_quantiles": _distance_quantiles(perturbation_total_histogram),
            "by_type": {
                name: {
                    "count": sum(histogram),
                    "distance_histogram": histogram,
                    "distance_quantiles": _distance_quantiles(histogram),
                }
                for name, histogram in sorted(perturbation_histograms.items())
            },
            "by_length_bucket": {
                bucket: {
                    "count": sum(histogram),
                    "distance_histogram": histogram,
                    "distance_quantiles": _distance_quantiles(histogram),
                }
                for bucket, histogram in sorted(length_bucket_histograms.items())
            },
        },
        "corpus_pairs": {
            "pair_count": corpus_pair_count,
            "distance_histogram": corpus_histogram,
            "distance_quantiles": _distance_quantiles(corpus_histogram),
            "closest_pairs": closest_pairs,
        },
        "thresholds": thresholds,
        "active_release_policy": {
            "policy_id": "universal-report-only-h3-4x16-v1",
            "scope": "all_content_purposes",
            "status": "report_only",
            "purpose_policy_status": "pending_labeled_calibration",
            "hamming_threshold": RELEASE_NEAR_DUP_THRESHOLD,
            "band_count": RELEASE_NEAR_DUP_BAND_COUNT,
            "band_bits": RELEASE_NEAR_DUP_BAND_BITS,
        },
        "decision": {
            "status": "human_labels_required",
            "reason": "Synthetic recall and corpus-pair rates are evidence, not labeled precision",
        },
    }


def write_calibration_report(
    report: dict[str, object],
    output_dir: Path,
    *,
    force: bool = False,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_token = "-".join(
        str(source["sha256"])[:8]
        for source in report["sources"]  # type: ignore[index]
    )
    base_name = f"similarity_calibration_{report['content_purpose']}_{source_token}"
    json_path = output_dir / f"{base_name}.json"
    markdown_path = output_dir / f"{base_name}.md"
    for path in (json_path, markdown_path):
        if path.exists() and not force:
            raise FileExistsError(f"Output already exists: {path}")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a bounded SimHash calibration report")
    parser.add_argument("--source-id", help="Derlem source id in PostgreSQL")
    parser.add_argument("--input-path", type=Path, help="Direct local input for experiments")
    parser.add_argument("--source-sha256", help="Required with --input-path")
    parser.add_argument("--content-purpose", choices=sorted(CONTENT_PURPOSES))
    parser.add_argument("--source-name", default="local-input")
    parser.add_argument("--sample-size", type=int, default=1_000)
    parser.add_argument("--threshold-max", type=int, default=10)
    parser.add_argument("--closest-pair-limit", type=int, default=100)
    parser.add_argument("--max-document-bytes", type=int)
    parser.add_argument("--output-dir", type=Path, default=Path("var/reports"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if bool(args.source_id) == bool(args.input_path):
        parser.error("Exactly one of --source-id or --input-path is required")
    if args.source_id:
        config = load_config()
        source, content_purpose = _load_source(
            config.database_url,
            config.storage_root,
            args.source_id,
        )
        max_document_bytes = args.max_document_bytes or config.max_document_bytes
        if args.content_purpose and args.content_purpose != content_purpose:
            parser.error("--content-purpose does not match the registered source")
    else:
        if not args.source_sha256 or not args.content_purpose:
            parser.error("--source-sha256 and --content-purpose are required with --input-path")
        if len(args.source_sha256) != 64:
            parser.error("--source-sha256 must be 64 hexadecimal characters")
        try:
            int(args.source_sha256, 16)
        except ValueError:
            parser.error("--source-sha256 must be 64 hexadecimal characters")
        input_path = args.input_path.resolve(strict=True)
        actual_sha256 = _file_sha256(input_path)
        if actual_sha256 != args.source_sha256.lower():
            parser.error("--source-sha256 does not match --input-path")
        source = CalibrationSource(
            source_id=None,
            name=args.source_name,
            sha256=args.source_sha256.lower(),
            path=input_path,
        )
        content_purpose = args.content_purpose
        max_document_bytes = args.max_document_bytes or 256 * 1024

    report = calibrate_similarity(
        [source],
        content_purpose=content_purpose,
        max_document_bytes=max_document_bytes,
        sample_size=args.sample_size,
        threshold_max=args.threshold_max,
        closest_pair_limit=args.closest_pair_limit,
        progress_callback=lambda progress: print(
            f"scanned={progress['documents_scanned']} eligible={progress['eligible_documents']}",
            file=sys.stderr,
        ),
    )
    paths = write_calibration_report(report, args.output_dir, force=args.force)
    print(json.dumps({key: str(path) for key, path in paths.items()}, ensure_ascii=False, indent=2))


def _sample_documents(
    sources: list[CalibrationSource],
    *,
    max_document_bytes: int,
    sample_size: int,
    progress_callback: Callable[[dict[str, int]], None] | None,
    progress_interval: int,
) -> tuple[list[_SampledDocument], _ScanStats]:
    heap: list[tuple[int, str, int, _SampledDocument]] = []
    stats = _ScanStats()
    next_progress_at = progress_interval
    for source in sources:
        for ordinal, raw_line, oversized in _bounded_lines(source.path, max_document_bytes):
            stats.lines_read += 1
            if oversized:
                stats.documents_scanned += 1
                stats.skipped_oversized += 1
                continue
            assert raw_line is not None
            stripped = raw_line.strip()
            if not stripped:
                stats.skipped_blank += 1
                continue
            stats.documents_scanned += 1
            text = _similarity_text_from_line(stripped)
            signature = document_simhash(text)
            if signature is None:
                stats.skipped_too_short += 1
                continue
            stats.eligible_documents += 1
            priority = int.from_bytes(
                hashlib.sha256(f"{source.sha256}:{ordinal}".encode("ascii")).digest()[:16],
                "big",
            )
            document = _SampledDocument(
                priority,
                source.sha256,
                ordinal,
                text,
                signature,
                len(normalize_document_text(text).split()),
            )
            entry = (-priority, source.sha256, ordinal, document)
            if len(heap) < sample_size:
                heapq.heappush(heap, entry)
            elif priority < -heap[0][0]:
                heapq.heapreplace(heap, entry)

            if progress_callback is not None and stats.documents_scanned >= next_progress_at:
                progress_callback(_scan_progress(stats))
                while next_progress_at <= stats.documents_scanned:
                    next_progress_at += progress_interval

    if progress_callback is not None:
        progress_callback(_scan_progress(stats))
    sampled = sorted((entry[3] for entry in heap), key=lambda document: (
        document.priority,
        document.source_sha256,
        document.source_ordinal,
    ))
    return sampled, stats


def _perturbations(tokens: list[str]) -> list[tuple[str, list[str]]]:
    middle = len(tokens) // 2
    span = max(1, len(tokens) // 10)
    span_start = max(0, min(len(tokens) - span, middle - span // 2))
    swapped = list(tokens)
    swap_left = min(middle, len(tokens) - 2)
    swapped[swap_left], swapped[swap_left + 1] = swapped[swap_left + 1], swapped[swap_left]
    return [
        ("drop_middle_token", tokens[:middle] + tokens[middle + 1 :]),
        ("replace_middle_token", tokens[:middle] + ["derlem_variant_token"] + tokens[middle + 1 :]),
        ("swap_middle_tokens", swapped),
        ("drop_middle_span", tokens[:span_start] + tokens[span_start + span :]),
    ]


def _corpus_pair_distances(
    sampled: list[_SampledDocument],
    closest_pair_limit: int,
) -> tuple[list[int], list[dict[str, object]]]:
    histogram = [0] * 65
    closest_heap: list[tuple[int, str, int, str, int, dict[str, object]]] = []
    for left_index, left in enumerate(sampled):
        for right in sampled[left_index + 1 :]:
            distance = hamming_distance(left.signature, right.signature)
            histogram[distance] += 1
            pair = {
                "left_source_sha256": left.source_sha256,
                "left_source_ordinal": left.source_ordinal,
                "right_source_sha256": right.source_sha256,
                "right_source_ordinal": right.source_ordinal,
                "hamming_distance": distance,
            }
            identity = (
                left.source_sha256,
                left.source_ordinal,
                right.source_sha256,
                right.source_ordinal,
            )
            entry = (-distance, identity[0], identity[1], identity[2], identity[3], pair)
            if len(closest_heap) < closest_pair_limit:
                heapq.heappush(closest_heap, entry)
            elif distance < -closest_heap[0][0]:
                heapq.heapreplace(closest_heap, entry)
    closest = sorted(
        (entry[5] for entry in closest_heap),
        key=lambda pair: (
            int(pair["hamming_distance"]),
            str(pair["left_source_sha256"]),
            int(pair["left_source_ordinal"]),
            str(pair["right_source_sha256"]),
            int(pair["right_source_ordinal"]),
        ),
    )
    return histogram, closest


def _length_bucket(token_count: int) -> str:
    if token_count <= 7:
        return "short_5_7"
    if token_count <= 15:
        return "medium_8_15"
    if token_count <= 31:
        return "long_16_31"
    return "very_long_32_plus"


def _token_length_summary(sampled: list[_SampledDocument]) -> dict[str, object]:
    lengths = sorted(document.token_count for document in sampled)
    buckets = []
    for bucket, minimum, maximum in (
        ("short_5_7", 5, 7),
        ("medium_8_15", 8, 15),
        ("long_16_31", 16, 31),
        ("very_long_32_plus", 32, None),
    ):
        count = sum(_length_bucket(length) == bucket for length in lengths)
        buckets.append(
            {
                "bucket": bucket,
                "token_min": minimum,
                "token_max": maximum,
                "document_count": count,
                "document_share_bps": _share_bps(count, len(lengths)),
            }
        )
    return {
        "min": lengths[0] if lengths else None,
        "p50": _ordered_quantile(lengths, 50),
        "p90": _ordered_quantile(lengths, 90),
        "max": lengths[-1] if lengths else None,
        "buckets": buckets,
    }


def _ordered_quantile(values: list[int], percentile: int) -> int | None:
    if not values:
        return None
    index = max(0, (len(values) * percentile + 99) // 100 - 1)
    return values[min(index, len(values) - 1)]


def _distance_quantiles(histogram: list[int]) -> dict[str, int | None]:
    total = sum(histogram)
    return {
        "p50": _histogram_quantile(histogram, total, 50),
        "p90": _histogram_quantile(histogram, total, 90),
        "p95": _histogram_quantile(histogram, total, 95),
        "p99": _histogram_quantile(histogram, total, 99),
        "max": max((distance for distance, count in enumerate(histogram) if count), default=None),
    }


def _histogram_quantile(
    histogram: list[int],
    total: int,
    percentile: int,
) -> int | None:
    if total <= 0:
        return None
    target = (total * percentile + 99) // 100
    cumulative = 0
    for distance, count in enumerate(histogram):
        cumulative += count
        if cumulative >= target:
            return distance
    return None


def _scan_progress(stats: _ScanStats) -> dict[str, int]:
    return {
        "lines_read": stats.lines_read,
        "documents_scanned": stats.documents_scanned,
        "eligible_documents": stats.eligible_documents,
        "skipped_too_short": stats.skipped_too_short,
        "skipped_oversized": stats.skipped_oversized,
    }


def _share_bps(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return (value * 10_000 + total // 2) // total


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_source(
    database_url: str,
    storage_root: Path,
    source_id: str,
) -> tuple[CalibrationSource, str]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        source = connection.execute(
            """
            SELECT source.id::text, source.name, source.content_purpose,
                source.object_sha256, object.storage_key
            FROM sources AS source
            JOIN storage_objects AS object ON object.sha256 = source.object_sha256
            WHERE source.id = %s
            """,
            (source_id,),
        ).fetchone()
    if source is None:
        raise RuntimeError(f"Source was not found: {source_id}")
    path = (storage_root / str(source["storage_key"])).resolve(strict=True)
    path.relative_to(storage_root)
    return (
        CalibrationSource(
            source_id=str(source["id"]),
            name=str(source["name"]),
            sha256=str(source["object_sha256"]),
            path=path,
        ),
        str(source["content_purpose"]),
    )


def _markdown_report(report: dict[str, object]) -> str:
    sampling = report["sampling"]
    token_lengths = sampling["sampled_token_lengths"]  # type: ignore[index]
    perturbations = report["synthetic_perturbations"]
    corpus_pairs = report["corpus_pairs"]
    decision = report["decision"]
    lines = [
        "# Derlem SimHash Calibration",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Content purpose: `{report['content_purpose']}`",
        f"- Sampled documents: `{sampling['sampled_document_count']}`",  # type: ignore[index]
        f"- Eligible documents: `{sampling['eligible_documents']}`",  # type: ignore[index]
        f"- Synthetic perturbations: `{perturbations['count']}`",  # type: ignore[index]
        f"- Corpus pairs: `{corpus_pairs['pair_count']}`",  # type: ignore[index]
        f"- Decision: `{decision['status']}`",  # type: ignore[index]
        "",
        "## Sampled Token Lengths",
        "",
        f"- Min / p50 / p90 / max: `{token_lengths['min']} / {token_lengths['p50']} / {token_lengths['p90']} / {token_lengths['max']}`",
        "",
        "| Bucket | Documents | Share |",
        "|---|---:|---:|",
    ]
    for bucket in token_lengths["buckets"]:
        lines.append(
            f"| {bucket['bucket']} | {bucket['document_count']} | "
            f"{_format_bps(bucket['document_share_bps'])} |"
        )
    lines.extend([
        "",
        "## Threshold Table",
        "",
        "| Threshold | Synthetic recall | Corpus pairs | Corpus pair rate | LSH complete |",
        "|---:|---:|---:|---:|:---:|",
    ])
    for row in report["thresholds"]:  # type: ignore[assignment]
        lines.append(
            f"| {row['threshold']} | {_format_bps(row['synthetic_recall_bps'])} | "
            f"{row['corpus_pair_count']} | {_format_bps(row['corpus_pair_rate_bps'])} | "
            f"{'yes' if row['release_lsh_complete'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "The report stores source identities, ordinals, distances, and aggregate counts only.",
            "It does not contain raw document text and does not activate a new threshold.",
            "Human labels are required before changing the release policy.",
            "",
        ]
    )
    return "\n".join(lines)


def _format_bps(value: object) -> str:
    return f"{int(value) / 100:.2f}%"


if __name__ == "__main__":
    main()
