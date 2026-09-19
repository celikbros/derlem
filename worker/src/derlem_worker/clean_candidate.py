from __future__ import annotations

import argparse
from array import array
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
from typing import Any, BinaryIO

import psycopg
from psycopg.rows import dict_row

from derlem_worker.config import load_config
from derlem_worker.fingerprints import FINGERPRINT_VERSION, document_fingerprint
from derlem_worker.pii import PII_KEYS, count_pii_in_text
from derlem_worker.quality_filters import (
    QUALITY_FILTER_STATUS_NOT_EVALUATED,
    QUALITY_POLICY_NONE,
    SUPPORTED_QUALITY_POLICIES,
    quality_filter_status,
    quality_rejection_reasons,
)
from derlem_worker.sampling import _bounded_lines, _document_from_line
from derlem_worker.similarity import (
    DEFAULT_MAX_CANDIDATES,
    RELEASE_NEAR_DUP_BAND_BITS,
    RELEASE_NEAR_DUP_BAND_COUNT,
    RELEASE_NEAR_DUP_THRESHOLD,
    SIMHASH_VERSION,
    document_simhash,
)


CLEAN_CANDIDATE_VERSION = "clean-candidate-v1"
CLEAN_CANDIDATE_V2_VERSION = "clean-candidate-v2"
# v3 (2026-09-18): ayni gecise held-out bolmesi ve yakin kopya atma eklendi;
# atma raporu her atilan satir icin SHA256, gerekce, karakter sayisi ve onizleme
# tasir (raf mektubu 2026-09-17, kurucu onayi 2026-09-18).
CLEAN_CANDIDATE_V3_VERSION = "clean-candidate-v3"

# Held-out kurali (afacan/docs/HELD_OUT_KURALI.md, v1): belge = satirin sondaki
# LF haric ham baytlari; sha256'nin ilk 8 hex hanesi 2500'e tam bolunuyorsa
# held-out. Konumdan ve yeniden uretimden bagimsizdir; bugunku adayda 2.275 belge
# secer (raf ve Derlem bagimsiz olctu, 2026-09-18).
HELD_OUT_RULE_NONE = "none"
HELD_OUT_RULE_AFACAN_V1 = "afacan-held-out-v1"
HELD_OUT_MODULUS = 2500
SUPPORTED_HELD_OUT_RULES = frozenset({HELD_OUT_RULE_NONE, HELD_OUT_RULE_AFACAN_V1})

REJECTIONS_RECORD_V1 = "clean-candidate-rejections-v1"
REJECTIONS_RECORD_V2 = "clean-candidate-rejections-v2"
REJECTION_PREVIEW_CHARS = 200
# Atilacak-satir listesi: proje ortaminda (Python 3.14) kurulamayan araclarla
# (ornegin fastText dil tanima, 3.13 ortaminda) disarida hesaplanan karar, satir
# baytlarinin SHA256'si uzerinden uretime verilir; listenin SHA'si manifeste yazilir.
DROP_LIST_DEFAULT_REASON = "drop_list"


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
    # v3 alanlari; eski surumlerde None / 0.
    rejections_record_version: str | None = None
    held_out_rule: str | None = None
    held_out_path: str | None = None
    held_out_lines: int = 0
    held_out_byte_size: int = 0
    held_out_sha256: str | None = None
    near_dedup_method: str | None = None
    near_dedup_hamming_threshold: int | None = None
    removed_near_duplicate_lines: int = 0
    simhash_indexed_lines: int = 0
    near_dedup_candidate_overflow_lines: int = 0
    drop_list_path: str | None = None
    drop_list_sha256: str | None = None
    drop_list_method: str | None = None
    drop_list_entries: int = 0
    removed_drop_list_lines: int = 0
    # TASK-026 (2026-09-19): politikanin kaynak diline uygulanip uygulanmadigi
    # ("applied" / "applied_language_unknown" / "not_evaluated"); politika yoksa None.
    # quality_filter_version her durumda istenen politikayi tasir.
    quality_filter_status: str | None = None


def is_held_out(line_bytes: bytes, rule: str) -> bool:
    if rule == HELD_OUT_RULE_NONE:
        return False
    if rule != HELD_OUT_RULE_AFACAN_V1:
        raise ValueError(f"Unsupported held-out rule: {rule!r}")
    return _is_held_out_hex(hashlib.sha256(line_bytes).hexdigest())


def _is_held_out_hex(hexdigest: str) -> bool:
    return int(hexdigest[:8], 16) % HELD_OUT_MODULUS == 0


def load_drop_list(path: Path) -> tuple[dict[bytes, dict[str, Any]], str, int]:
    """JSONL: her kayitta 64 hex 'sha256' (satir baytlari, LF haric); diger alanlar
    rapora ayrinti olarak gecer. Donus: (digest -> ayrinti, dosya sha256, kayit sayisi)."""
    entries: dict[bytes, dict[str, Any]] = {}
    payload = path.read_bytes()
    for number, line in enumerate(payload.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        digest = str(record.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"drop list line {number}: sha256 missing or malformed")
        details = {key: value for key, value in record.items() if key not in {"sha256", "source_ordinal"}}
        entries[bytes.fromhex(digest)] = details
    return entries, hashlib.sha256(payload).hexdigest(), len(entries)


class _NearDuplicateIndex:
    """Surum yakin-kopya politikasiyla ayni yontem (SimHash 64, Hamming <= 3,
    4 x 16 bit bant), bellekte: imzalar array('Q'), kovalar array('I')."""

    def __init__(
        self,
        *,
        hamming_threshold: int = RELEASE_NEAR_DUP_THRESHOLD,
        band_count: int = RELEASE_NEAR_DUP_BAND_COUNT,
        band_bits: int = RELEASE_NEAR_DUP_BAND_BITS,
        max_candidates_per_bucket: int = DEFAULT_MAX_CANDIDATES,
    ) -> None:
        self.hamming_threshold = hamming_threshold
        self.band_count = band_count
        self.band_bits = band_bits
        self.band_mask = (1 << band_bits) - 1
        self.max_candidates_per_bucket = max_candidates_per_bucket
        self.signatures = array("Q")
        self.ordinals = array("I")
        self.buckets: dict[int, array] = {}
        self.overflow_lines = 0

    def __len__(self) -> int:
        return len(self.signatures)

    def find_partner(self, signature: int) -> int | None:
        """Hamming esigi icinde daha once gorulmus bir belgenin ordinal'i, yoksa None."""
        overflow = False
        for band in range(self.band_count):
            key = (band << self.band_bits) | ((signature >> (band * self.band_bits)) & self.band_mask)
            members = self.buckets.get(key)
            if not members:
                continue
            if len(members) > self.max_candidates_per_bucket:
                overflow = True
                members = members[-self.max_candidates_per_bucket:]
            for index in members:
                if (self.signatures[index] ^ signature).bit_count() <= self.hamming_threshold:
                    return self.ordinals[index]
        if overflow:
            self.overflow_lines += 1
        return None

    def add(self, signature: int, ordinal: int) -> None:
        index = len(self.signatures)
        self.signatures.append(signature)
        self.ordinals.append(ordinal)
        for band in range(self.band_count):
            key = (band << self.band_bits) | ((signature >> (band * self.band_bits)) & self.band_mask)
            bucket = self.buckets.get(key)
            if bucket is None:
                bucket = self.buckets[key] = array("I")
            bucket.append(index)


class _AtomicOutput:
    """Hedefin yanina gecici dosya; basarida yerine gecer, hatada silinir.
    SHA256 ve boyut yazarken toplanir."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.hasher = hashlib.sha256()
        self.byte_size = 0
        self.descriptor, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
        self.temp_path = Path(temp_name)
        self.handle: BinaryIO | None = None

    def open(self, stack: ExitStack) -> None:
        self.handle = stack.enter_context(os.fdopen(self.descriptor, "wb"))
        self.descriptor = -1

    def write(self, payload: bytes) -> None:
        assert self.handle is not None
        self.handle.write(payload)
        self.hasher.update(payload)
        self.byte_size += len(payload)

    def sync(self) -> None:
        assert self.handle is not None
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def commit(self) -> None:
        self.temp_path.replace(self.path)

    def cleanup(self) -> None:
        self.temp_path.unlink(missing_ok=True)
        if self.descriptor >= 0:
            try:
                os.close(self.descriptor)
            except OSError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local clean-candidate file from a Derlem source")
    parser.add_argument("--source-id", help="Derlem source id to read from object storage")
    parser.add_argument("--input-path", type=Path, help="Direct input file path for local experiments")
    parser.add_argument("--output-dir", type=Path, default=Path("var/derived"))
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--quality-rejections-path",
        type=Path,
        help="Optional JSONL audit path for removed lines (reason codes; v3 adds sha256, char count, preview)",
    )
    parser.add_argument("--max-document-bytes", type=int)
    parser.add_argument("--limit-lines", type=int, help="Development-only limit; do not use for final candidates")
    parser.add_argument(
        "--quality-policy",
        choices=sorted(SUPPORTED_QUALITY_POLICIES),
        default=QUALITY_POLICY_NONE,
        help="Optional versioned hard-rejection policy; defaults to the v1 behavior",
    )
    parser.add_argument(
        "--held-out-rule",
        choices=sorted(SUPPORTED_HELD_OUT_RULES),
        default=HELD_OUT_RULE_NONE,
        help="Split lines matching the rule into a separate held-out file (v3)",
    )
    parser.add_argument("--held-out-path", type=Path, help="Held-out output path (default: <output>_heldout.txt)")
    parser.add_argument(
        "--near-dedup",
        action="store_true",
        help=f"Drop near-duplicates (SimHash, Hamming <= {RELEASE_NEAR_DUP_THRESHOLD}) in the same pass (v3)",
    )
    parser.add_argument("--drop-list", type=Path, help="JSONL of line sha256 digests to drop (v3; e.g. language decisions)")
    parser.add_argument("--drop-list-method", help="Method identifier recorded in the manifest (required with --drop-list)")
    parser.add_argument("--drop-list-reason", default=DROP_LIST_DEFAULT_REASON, help="Reason code written to the rejection report")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output/manifest paths")
    args = parser.parse_args()

    if bool(args.source_id) == bool(args.input_path):
        parser.error("Exactly one of --source-id or --input-path is required")
    if args.limit_lines is not None and args.limit_lines <= 0:
        parser.error("--limit-lines must be positive")
    if args.held_out_path and args.held_out_rule == HELD_OUT_RULE_NONE:
        parser.error("--held-out-path requires --held-out-rule")
    if bool(args.drop_list) != bool(args.drop_list_method):
        parser.error("--drop-list and --drop-list-method go together")

    config = load_config()
    max_document_bytes = args.max_document_bytes or config.max_document_bytes
    if max_document_bytes <= 0:
        parser.error("--max-document-bytes must be positive")

    v3 = args.held_out_rule != HELD_OUT_RULE_NONE or args.near_dedup or args.drop_list is not None
    source: dict[str, Any] | None = None
    if args.source_id:
        source = load_source(config.database_url, config.storage_root, args.source_id)
        input_path = Path(str(source["object_path"]))
        output_path = resolve_output_path(
            args.output_dir, args.output_path, source, args.limit_lines,
            quality_policy=args.quality_policy, v3=v3,
        )
    else:
        input_path = args.input_path.resolve(strict=True)
        output_path = resolve_output_path(
            args.output_dir, args.output_path, None, args.limit_lines,
            input_path=input_path, quality_policy=args.quality_policy, v3=v3,
        )

    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    quality_rejections_path: Path | None = None
    if args.quality_policy != QUALITY_POLICY_NONE or v3:
        quality_rejections_path = (
            args.quality_rejections_path.resolve()
            if args.quality_rejections_path
            else output_path.with_suffix(output_path.suffix + ".rejections.jsonl")
        )
    elif args.quality_rejections_path:
        parser.error("--quality-rejections-path requires a non-default --quality-policy")
    if quality_rejections_path == manifest_path:
        parser.error("--quality-rejections-path must be distinct from the manifest path")
    held_out_path: Path | None = None
    if args.held_out_rule != HELD_OUT_RULE_NONE:
        held_out_path = args.held_out_path.resolve() if args.held_out_path else default_held_out_path(output_path)
    for target in (output_path, manifest_path, quality_rejections_path, held_out_path):
        if target is not None:
            ensure_writable_target(target, args.force)

    report = derive_clean_candidate(
        input_path,
        output_path,
        source=source,
        max_document_bytes=max_document_bytes,
        limit_lines=args.limit_lines,
        quality_policy=args.quality_policy,
        quality_rejections_path=quality_rejections_path,
        held_out_rule=args.held_out_rule,
        held_out_path=held_out_path,
        near_dedup=args.near_dedup,
        drop_list_path=args.drop_list,
        drop_list_method=args.drop_list_method,
        drop_list_reason=args.drop_list_reason,
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
                source.language,
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


def default_held_out_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_heldout{output_path.suffix}")


def _rejection_record(
    *,
    ordinal: int,
    reasons: tuple[str, ...],
    full: bool,
    line_bytes: bytes = b"",
    text: str = "",
    duplicate_of: int | None = None,
    details: dict[str, Any] | None = None,
) -> bytes:
    if not full:
        record: dict[str, Any] = {"source_ordinal": ordinal, "reasons": list(reasons)}
        return json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    # v2 kaydi: rafin istedigi alanlar. Onizleme kisisel veri tasimaz: PII
    # ayiklamasi bu noktadan once calisir ve PII'li satir buraya hic gelmez.
    record = {
        "source_ordinal": ordinal,
        "sha256": hashlib.sha256(line_bytes).hexdigest(),
        "reasons": list(reasons),
        "char_count": len(text),
        "preview": text[:REJECTION_PREVIEW_CHARS],
    }
    if duplicate_of is not None:
        record["duplicate_of"] = duplicate_of
    if details:
        record["details"] = details
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"


def derive_clean_candidate(
    input_path: Path,
    output_path: Path,
    *,
    source: dict[str, Any] | None,
    max_document_bytes: int,
    limit_lines: int | None = None,
    quality_policy: str = QUALITY_POLICY_NONE,
    quality_rejections_path: Path | None = None,
    held_out_rule: str = HELD_OUT_RULE_NONE,
    held_out_path: Path | None = None,
    near_dedup: bool = False,
    drop_list_path: Path | None = None,
    drop_list_method: str | None = None,
    drop_list_reason: str = DROP_LIST_DEFAULT_REASON,
) -> CleanCandidateReport:
    if quality_policy not in SUPPORTED_QUALITY_POLICIES:
        raise ValueError(f"Unsupported quality policy: {quality_policy}")
    if held_out_rule not in SUPPORTED_HELD_OUT_RULES:
        raise ValueError(f"Unsupported held-out rule: {held_out_rule}")
    if bool(drop_list_path) != bool(drop_list_method):
        raise ValueError("drop_list_path and drop_list_method go together")
    v3 = held_out_rule != HELD_OUT_RULE_NONE or near_dedup or drop_list_path is not None
    input_path = input_path.resolve(strict=True)
    output_path = output_path.resolve()
    if input_path == output_path:
        raise RuntimeError("Output path must not be the same as input path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if quality_rejections_path is not None:
        if quality_policy == QUALITY_POLICY_NONE and not v3:
            raise ValueError("A quality rejections path requires a non-default quality policy")
        quality_rejections_path = quality_rejections_path.resolve()
        if quality_rejections_path in {input_path, output_path}:
            raise RuntimeError("Quality rejections path must be distinct from input and output")
        quality_rejections_path.parent.mkdir(parents=True, exist_ok=True)
    if held_out_rule != HELD_OUT_RULE_NONE:
        held_out_path = (held_out_path or default_held_out_path(output_path)).resolve()
        if held_out_path in {input_path, output_path, quality_rejections_path}:
            raise RuntimeError("Held-out path must be distinct from input, output and rejections")
        held_out_path.parent.mkdir(parents=True, exist_ok=True)
    elif held_out_path is not None:
        raise ValueError("A held-out path requires a held-out rule")

    # Dil durustlugu (TASK-026): kaynak politikanin dili disinda bir dil ilan
    # etmisse kurallar hic calistirilmaz (0 kalite atmasi); manifest istenen
    # politikayi ve "not_evaluated" durumunu birlikte yazar. Kaynaksiz (--input-path)
    # kosuda dil bilinmez, politika bugunku gibi uygulanir.
    source_language = str(source["language"]) if source and source.get("language") else None
    quality_status = quality_filter_status(quality_policy, source_language)
    effective_quality_policy = (
        QUALITY_POLICY_NONE if quality_status == QUALITY_FILTER_STATUS_NOT_EVALUATED else quality_policy
    )

    # Tekillestirme kaydi iki akis (egitim adayi ve held-out) icin ortaktir:
    # held-out bir satirin birebir/normalize kopyasi egitime gidemez.
    seen_fingerprints: dict[bytes, int] = {}
    near_index = _NearDuplicateIndex() if near_dedup else None
    drop_list: dict[bytes, dict[str, Any]] = {}
    drop_list_sha256: str | None = None
    drop_list_entries = 0
    removed_drop_list_lines = 0
    if drop_list_path is not None:
        drop_list_path = drop_list_path.resolve(strict=True)
        drop_list, drop_list_sha256, drop_list_entries = load_drop_list(drop_list_path)
    pii_findings = {key: 0 for key in PII_KEYS}
    pii_line_counts = {key: 0 for key in PII_KEYS}
    total_lines = 0
    written_lines = 0
    held_out_lines = 0
    removed_pii_lines = 0
    removed_duplicate_lines = 0
    removed_near_duplicate_lines = 0
    removed_oversized_lines = 0
    removed_quality_lines = 0
    skipped_blank_lines = 0
    indexed_fingerprints = 0
    kept_short_or_unfingerprinted_lines = 0
    quality_reason_document_counts: Counter[str] = Counter()

    output = _AtomicOutput(output_path)
    rejections = _AtomicOutput(quality_rejections_path) if quality_rejections_path is not None else None
    held_out = _AtomicOutput(held_out_path) if held_out_path is not None else None
    outputs = [item for item in (output, rejections, held_out) if item is not None]
    try:
        with ExitStack() as stack:
            for item in outputs:
                item.open(stack)
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

                line_bytes = raw_line.encode("utf-8")
                line_digest = hashlib.sha256(line_bytes)
                text, _ = _document_from_line(stripped)
                if drop_list:
                    dropped = drop_list.get(line_digest.digest())
                    if dropped is not None:
                        removed_drop_list_lines += 1
                        if rejections is not None:
                            rejections.write(_rejection_record(
                                ordinal=ordinal, reasons=(drop_list_reason,), full=True,
                                line_bytes=line_bytes, text=text, details=dropped,
                            ))
                        continue
                quality_reasons = quality_rejection_reasons(text, effective_quality_policy)
                if quality_reasons:
                    removed_quality_lines += 1
                    quality_reason_document_counts.update(quality_reasons)
                    if rejections is not None:
                        rejections.write(_rejection_record(
                            ordinal=ordinal, reasons=quality_reasons, full=v3, line_bytes=line_bytes, text=text,
                        ))
                    continue

                fingerprint = document_fingerprint(text) if text else None
                if fingerprint is None:
                    kept_short_or_unfingerprinted_lines += 1
                else:
                    normalized_sha256, _ = fingerprint
                    key = bytes.fromhex(normalized_sha256)
                    earlier = seen_fingerprints.get(key)
                    if earlier is not None:
                        removed_duplicate_lines += 1
                        if rejections is not None and v3:
                            rejections.write(_rejection_record(
                                ordinal=ordinal, reasons=("normalized_duplicate",), full=True,
                                line_bytes=line_bytes, text=text, duplicate_of=earlier,
                            ))
                        continue
                    seen_fingerprints[key] = ordinal
                    indexed_fingerprints += 1

                if near_index is not None:
                    signature = document_simhash(text) if text else None
                    if signature is not None:
                        partner = near_index.find_partner(signature)
                        if partner is not None:
                            removed_near_duplicate_lines += 1
                            if rejections is not None:
                                rejections.write(_rejection_record(
                                    ordinal=ordinal, reasons=("near_duplicate",), full=True,
                                    line_bytes=line_bytes, text=text, duplicate_of=partner,
                                ))
                            continue
                        near_index.add(signature, ordinal)

                encoded = line_bytes + b"\n"
                if held_out is not None and _is_held_out_hex(line_digest.hexdigest()):
                    held_out.write(encoded)
                    held_out_lines += 1
                else:
                    output.write(encoded)
                    written_lines += 1

            for item in outputs:
                item.sync()
        for item in outputs:
            item.commit()
    finally:
        for item in outputs:
            item.cleanup()

    source_id = str(source["id"]) if source else None
    if v3:
        algorithm_version = CLEAN_CANDIDATE_V3_VERSION
    elif quality_policy != QUALITY_POLICY_NONE:
        algorithm_version = CLEAN_CANDIDATE_V2_VERSION
    else:
        algorithm_version = CLEAN_CANDIDATE_VERSION
    return CleanCandidateReport(
        algorithm_version=algorithm_version,
        quality_filter_version=(None if quality_policy == QUALITY_POLICY_NONE else quality_policy),
        fingerprint_version=FINGERPRINT_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
        source_id=source_id,
        source_name=str(source["name"]) if source else None,
        source_sha256=str(source["object_sha256"]) if source else None,
        input_path=str(input_path),
        output_path=str(output_path),
        quality_rejections_path=(str(quality_rejections_path) if quality_rejections_path is not None else None),
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
        quality_rejections_sha256=(rejections.hasher.hexdigest() if rejections is not None else None),
        quality_rejections_byte_size=(rejections.byte_size if rejections is not None else 0),
        output_sha256=output.hasher.hexdigest(),
        output_byte_size=output.byte_size,
        rejections_record_version=(
            None if rejections is None else (REJECTIONS_RECORD_V2 if v3 else REJECTIONS_RECORD_V1)
        ),
        held_out_rule=(None if held_out_rule == HELD_OUT_RULE_NONE else held_out_rule),
        held_out_path=(str(held_out_path) if held_out is not None else None),
        held_out_lines=held_out_lines,
        held_out_byte_size=(held_out.byte_size if held_out is not None else 0),
        held_out_sha256=(held_out.hasher.hexdigest() if held_out is not None else None),
        near_dedup_method=(SIMHASH_VERSION if near_index is not None else None),
        near_dedup_hamming_threshold=(near_index.hamming_threshold if near_index is not None else None),
        removed_near_duplicate_lines=removed_near_duplicate_lines,
        simhash_indexed_lines=(len(near_index) if near_index is not None else 0),
        near_dedup_candidate_overflow_lines=(near_index.overflow_lines if near_index is not None else 0),
        drop_list_path=(str(drop_list_path) if drop_list_path is not None else None),
        drop_list_sha256=drop_list_sha256,
        drop_list_method=drop_list_method,
        drop_list_entries=drop_list_entries,
        removed_drop_list_lines=removed_drop_list_lines,
        quality_filter_status=quality_status,
    )


def resolve_output_path(
    output_dir: Path,
    output_path: Path | None,
    source: dict[str, Any] | None,
    limit_lines: int | None,
    *,
    input_path: Path | None = None,
    quality_policy: str = QUALITY_POLICY_NONE,
    v3: bool = False,
) -> Path:
    if output_path:
        return output_path.resolve()
    output_dir = output_dir.resolve()
    if source:
        stem = f"{slugify(str(source['name']))}_{str(source['id'])[:8]}_clean_candidate"
    else:
        assert input_path is not None
        stem = f"{slugify(input_path.stem)}_clean_candidate"
    if v3:
        stem = f"{stem}_v3"
    elif quality_policy != QUALITY_POLICY_NONE:
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
