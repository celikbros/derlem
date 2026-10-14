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
import platform
import re
import tempfile
from typing import Any, BinaryIO
import zlib

import psycopg
from psycopg.rows import dict_row

from derlem_worker import machine_translation
from derlem_worker.clean_candidate_signals import (
    SignalPrecompute,
    document_fingerprint_key,
    document_pii_counts,
    document_quality_reasons,
    document_simhash_signature,
)
from derlem_worker.clean_candidate_signals import line_url as _line_url  # noqa: F401 - eski ad (import_manifest belgesi)
from derlem_worker.config import load_config
from derlem_worker.document_record import file_sha256
from derlem_worker.fingerprints import FINGERPRINT_VERSION
from derlem_worker.import_manifest import (
    CANDIDATE_LINE_FORMAT,
    load_import_manifest,
    manifest_candidate_lines,
    manifest_shards_covering,
)
from derlem_worker.pii import PII_KEYS
from derlem_worker.quality_filters import (
    QUALITY_FILTER_STATUS_NOT_EVALUATED,
    QUALITY_POLICY_NONE,
    QUALITY_POLICY_TR_WEB_V4,
    SUPPORTED_QUALITY_POLICIES,
    quality_filter_status,
)
from derlem_worker.quality_v4 import judge_id as tr_web_v4_judge_id
from derlem_worker.sampling import _bounded_lines, _document_from_line
from derlem_worker.selection import (
    HashOnlyOutput,
    SelectionRecorder,
    load_subtraction_drops,
    new_run_id,
    run_started_at,
    write_selection_manifest,
)
from derlem_worker.similarity import (
    DEFAULT_MAX_CANDIDATES,
    RELEASE_NEAR_DUP_BAND_BITS,
    RELEASE_NEAR_DUP_BAND_COUNT,
    RELEASE_NEAR_DUP_THRESHOLD,
    SIMHASH_VERSION,
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
PII_JUDGE = "derlem_worker.pii.count_pii_in_text"
# Secim listesi kosusunda gerekcesi bilinmeyen atilacak-satir kaydinin karar turu.
DROP_LIST_FALLBACK_DECISION_TYPES = frozenset({"language", "rights_scope", "quality_rule", "pii"})


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
    # TASK-039 (2026-09-20): tr-web-v1/v2'nin sikistirma olcutu zlib UYGULAMASINA
    # bagimliydi (3.14/zlib-ng ile 3.13/zlib 1.3.1 arasinda 7 satir taraf
    # degistirdi). tr-web-v3 bu bagimliligi kaldirdi; yine de her manifest hangi
    # yorumlayici ve hangi zlib surumuyle uretildigini yazar, cunku v1/v2 ile
    # uretilmis eski adaylarin yeniden uretilebilirligi buna baglidir.
    interpreter_version: str = ""
    zlib_runtime_version: str = ""
    # TASK-046 (2026-10-13): tr-web-v4'te karar kaydinin yargic kimligi
    # ("tr-web-v4@<kural kodunun sha'si>"); diger politikalarda None.
    quality_judge: str | None = None
    # TASK-049 (2026-10-13): tr-web-v4'te uygulanan makine cevirisi hedef cifti
    # ("A" / "B", machine_translation.MT_TARGET); yargic kimligi bunu zaten kapsar,
    # bu alan okunur ad icindir. Diger politikalarda None.
    machine_translation_target: str | None = None
    # TASK-049: girdi bir alim manifestiyse (derlem.import-manifest.v1) belgeler
    # parcalardan aday satiri olarak okunur (import_manifest.CANDIDATE_LINE_FORMAT);
    # input_kind "import_manifest", import_manifest okunan parcalarin ozeti.
    # Satir dosyasinda ikisi de None.
    input_kind: str | None = None
    import_manifest: dict[str, Any] | None = None
    # TASK-049 ek isi (paralel on hesap): belge-yerel sinyaller tablolardan geldiyse
    # ozet (isci sayisi, tablo sayilari, yeniden kullanilan/hesaplanan/reddedilen,
    # tablolarin toplu SHA'si, politika kimligi); tek surecli eski yolda None.
    # Kararlari ve ciktilari degistirmez.
    signal_precompute: dict[str, Any] | None = None
    # TASK-050 (2026-10-14): tekrar ve yakin kopya kararlarindan SONRA uygulanan
    # cikarma listesi (derlem.decision.v1; source_ordinal = aday satir numarasi).
    # Dusen belge tekrar kayitlarinda kalir, yalniz secime girmez: sonuc
    # ``selection subtract`` ile bayt bayt aynidir. Yoksa None / 0.
    post_dedup_drop_path: str | None = None
    post_dedup_drop_sha256: str | None = None
    post_dedup_drop_entries: int = 0
    removed_post_dedup_drop_lines: int = 0


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
    parser.add_argument(
        "--selection-list",
        action="store_true",
        help="Write a selection list (doc_ids) + decision snapshot (Parquet) + manifest instead of a text copy "
        "(TASK-044); text is produced later by 'python -m derlem_worker.selection materialize'",
    )
    parser.add_argument("--run-id", help="Run id written to every decision row (selection-list mode; default: uuid4)")
    parser.add_argument(
        "--decided-at",
        help="Timezone-aware ISO timestamp written to every decision row (selection-list mode; default: run start). "
        "With --run-id it makes the decisions file reproducible byte for byte",
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        help="Object store root for an --input-path that is a derlem.import-manifest.v1 object "
        "(documents are read from its shards); --source-id uses the configured store",
    )
    parser.add_argument(
        "--drop-list-decision-type",
        choices=sorted(DROP_LIST_FALLBACK_DECISION_TYPES),
        default="language",
        help="Decision type for drop-list entries whose reason is not a known one (selection-list mode)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Import-manifest input only: compute the per-document signals (PII, quality rules, fingerprint, "
        "SimHash, doc_id) in N processes; the order-dependent decisions stay in one pass. 1 = the serial path",
    )
    parser.add_argument(
        "--signals-dir",
        type=Path,
        help="Import-manifest input only: keep the per-row-group signal tables here and reuse those whose "
        "shard SHA and policy identity still match (cheap restart); default with --workers > 1: a temporary "
        "directory removed at the end",
    )
    parser.add_argument(
        "--post-dedup-drop",
        type=Path,
        help="derlem.decision.v1 parquet of reject rows applied AFTER the duplicate/near-duplicate decisions "
        "(source_ordinal = candidate line number; the dropped documents stay in the dedup state). Same result "
        "as 'python -m derlem_worker.selection subtract' (TASK-050)",
    )
    args = parser.parse_args()

    if bool(args.source_id) == bool(args.input_path):
        parser.error("Exactly one of --source-id or --input-path is required")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
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
    decided_at: datetime | None = None
    if args.decided_at:
        decided_at = datetime.fromisoformat(args.decided_at)
        if decided_at.tzinfo is None:
            parser.error("--decided-at must carry a timezone (e.g. 2026-10-13T00:00:00+00:00)")
        if not args.selection_list:
            parser.error("--decided-at goes with --selection-list")
    source: dict[str, Any] | None = None
    store_root: Path | None = None
    if args.source_id:
        if args.store_root:
            parser.error("--store-root goes with --input-path; --source-id uses the configured store")
        source = load_source(config.database_url, config.storage_root, args.source_id)
        input_path = Path(str(source["object_path"]))
        store_root = config.storage_root
    else:
        input_path = args.input_path.resolve(strict=True)
        store_root = args.store_root.resolve(strict=True) if args.store_root else None
    # Parcali kaynak (TASK-049): aday satiri JSON'dur, dosya adi .jsonl.
    import_manifest_input = load_import_manifest(input_path) is not None
    if import_manifest_input and store_root is None:
        parser.error("--input-path is an import manifest; pass --store-root (its documents live in shards)")
    if (args.workers > 1 or args.signals_dir is not None) and not import_manifest_input:
        parser.error("--workers > 1 and --signals-dir need an import-manifest input (signals are per shard row group)")
    signals_dir = args.signals_dir.resolve() if args.signals_dir is not None else None
    suffix = ".jsonl" if import_manifest_input else ".txt"
    output_path = resolve_output_path(
        args.output_dir, args.output_path, source, args.limit_lines,
        input_path=(None if source else input_path), quality_policy=args.quality_policy, v3=v3, suffix=suffix,
    )

    if args.selection_list:
        if args.limit_lines is not None and not import_manifest_input:
            parser.error("--selection-list takes --limit-lines only for an import-manifest slice (measurement)")
        artifacts = selection_artifact_paths(output_path)
        rejections_path = args.quality_rejections_path.resolve() if args.quality_rejections_path else None
        if rejections_path is not None and args.quality_policy == QUALITY_POLICY_NONE and not v3:
            parser.error("--quality-rejections-path requires a non-default --quality-policy")
        for target in (*artifacts.values(), rejections_path):
            if target is not None:
                ensure_writable_target(target, args.force)
        manifest = derive_selection_list(
            input_path,
            output_path,
            source=source,
            max_document_bytes=max_document_bytes,
            quality_policy=args.quality_policy,
            quality_rejections_path=rejections_path,
            held_out_rule=args.held_out_rule,
            near_dedup=args.near_dedup,
            drop_list_path=args.drop_list,
            drop_list_method=args.drop_list_method,
            drop_list_reason=args.drop_list_reason,
            drop_list_decision_type=args.drop_list_decision_type,
            run_id=args.run_id,
            decided_at=decided_at,
            store_root=store_root,
            limit_lines=args.limit_lines,
            workers=args.workers,
            signals_dir=signals_dir,
            post_dedup_drop_path=args.post_dedup_drop,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

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
        store_root=store_root,
        workers=args.workers,
        signals_dir=signals_dir,
        post_dedup_drop_path=args.post_dedup_drop,
    )
    write_json_atomic(manifest_path, asdict(report))
    print(json.dumps({"output": str(output_path), "manifest": str(manifest_path), "report": asdict(report)}, ensure_ascii=False, indent=2))


def selection_artifact_paths(output_path: Path) -> dict[str, Path]:
    """Secim listesi kosusunun dosyalari, metin-kopya yolunun yaninda (ayni govde adi)."""
    stem = output_path.stem
    return {
        "selection": output_path.with_name(f"{stem}.selection.parquet"),
        "decisions": output_path.with_name(f"{stem}.decisions.parquet"),
        "manifest": output_path.with_name(f"{stem}.selection.manifest.json"),
    }


def derive_selection_list(
    input_path: Path,
    output_path: Path,
    *,
    source: dict[str, Any] | None,
    max_document_bytes: int,
    quality_policy: str = QUALITY_POLICY_NONE,
    quality_rejections_path: Path | None = None,
    held_out_rule: str = HELD_OUT_RULE_NONE,
    near_dedup: bool = False,
    drop_list_path: Path | None = None,
    drop_list_method: str | None = None,
    drop_list_reason: str = DROP_LIST_DEFAULT_REASON,
    drop_list_decision_type: str = "language",
    run_id: str | None = None,
    decided_at: datetime | None = None,
    store_root: Path | None = None,
    limit_lines: int | None = None,
    workers: int = 1,
    signals_dir: Path | None = None,
    post_dedup_drop_path: Path | None = None,
) -> dict[str, Any]:
    """Metin-kopya kosusunun aynisi, metin yazmadan: secim listesi + karar anlik goruntusu + manifest.

    ``output_path`` metin-kopyanin olacagi yoldur; dosyalar onun yanina yazilir,
    kendisi yazilmaz. Manifest metin-kopyanin SHA'sini (``expected_materialization``)
    tasir; materialize bu SHA'yi uretmeden ciktiyi yayimlamaz.

    ``input_path`` bir alim manifestiyse (TASK-049) ``store_root`` gerekir; belgeler
    parcalardan aday satiri olarak okunur ve manifestin ``parent`` bolumu parcalari
    listeler (materialize ayni parcalardan uretir). ``limit_lines`` yalniz olcum
    dilimi icindir ve manifestte ``document_limit`` olarak durur.
    """
    if drop_list_decision_type not in DROP_LIST_FALLBACK_DECISION_TYPES:
        raise ValueError(f"unsupported drop-list decision type: {drop_list_decision_type}")
    input_path = input_path.resolve(strict=True)
    output_path = output_path.resolve()
    artifacts = selection_artifact_paths(output_path)
    run_id = run_id or new_run_id()
    decided_at = decided_at or run_started_at()
    parent_sha256, parent_byte_size = file_sha256(input_path)
    if source is not None and str(source.get("object_sha256") or parent_sha256) != parent_sha256:
        raise RuntimeError("Source object sha256 does not match the input bytes")
    recorder = SelectionRecorder(
        selection_path=artifacts["selection"],
        decisions_path=artifacts["decisions"],
        run_id=run_id,
        decided_at=decided_at,
        drop_list_decision_type=drop_list_decision_type,
    )
    try:
        report = derive_clean_candidate(
            input_path,
            output_path,
            source=source,
            max_document_bytes=max_document_bytes,
            quality_policy=quality_policy,
            quality_rejections_path=quality_rejections_path,
            held_out_rule=held_out_rule,
            near_dedup=near_dedup,
            drop_list_path=drop_list_path,
            drop_list_method=drop_list_method,
            drop_list_reason=drop_list_reason,
            selection=recorder,
            store_root=store_root,
            limit_lines=limit_lines,
            workers=workers,
            signals_dir=signals_dir,
            post_dedup_drop_path=post_dedup_drop_path,
        )
        selection_info, decisions_info = recorder.close()
    except BaseException:
        recorder.abort()
        raise
    expected = {
        "train": {
            "sha256": report.output_sha256,
            "byte_size": report.output_byte_size,
            "lines": report.written_lines,
        }
    }
    if report.held_out_sha256 is not None:
        expected["held_out"] = {
            "sha256": report.held_out_sha256,
            "byte_size": report.held_out_byte_size,
            "lines": report.held_out_lines,
        }
    report_dict = asdict(report)
    report_dict["output_path"] = None
    report_dict["held_out_path"] = None
    report_dict["selection_list"] = True
    report_dict["document_limit"] = limit_lines
    parent_extra: dict[str, Any] | None = None
    if report.import_manifest is not None:
        summary = report.import_manifest
        parent_extra = {
            "kind": "import_manifest",
            "schema": summary["schema"],
            "line_format": summary["line_format"],
            "store_root": summary["store_root"],
            "document_limit": limit_lines,
            "documents_read": summary["documents_read"],
            "last_source_ordinal": summary["last_source_ordinal"],
            "shards": summary["shards"],
        }
    manifest = write_selection_manifest(
        artifacts["manifest"],
        report=report_dict,
        parent_path=input_path,
        parent_sha256=parent_sha256,
        parent_byte_size=parent_byte_size,
        selection=selection_info,
        decisions=decisions_info,
        recorder_counts=dict(recorder.selected),
        decision_counts=dict(recorder.decision_counts),
        oversized_ordinals=list(recorder.oversized_ordinals),
        expected=expected,
        run_id=run_id,
        decided_at=decided_at.isoformat(),
        method=f"{report.algorithm_version}+selection-list",
        parent_extra=parent_extra,
        policies=policy_ids(report),
    )
    manifest["manifest_path"] = str(artifacts["manifest"])
    return manifest


def policy_ids(report: CleanCandidateReport) -> dict[str, Any]:
    """Kosunun karar politikalarinin kimlikleri (karar kaydindaki ``judge`` degerleri)."""
    return {
        "pii": PII_JUDGE,
        "quality_rule": report.quality_judge or report.quality_filter_version,
        "quality_filter_status": report.quality_filter_status,
        "machine_translation_target": report.machine_translation_target,
        "duplicate": report.fingerprint_version,
        "near_duplicate": (
            f"{report.near_dedup_method}-hamming{report.near_dedup_hamming_threshold}"
            if report.near_dedup_method else None
        ),
        "held_out": report.held_out_rule,
        "drop_list": report.drop_list_method,
        "max_document_bytes": report.max_document_bytes,
    }


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
    selection: SelectionRecorder | None = None,
    store_root: Path | None = None,
    workers: int = 1,
    signals_dir: Path | None = None,
    post_dedup_drop_path: Path | None = None,
) -> CleanCandidateReport:
    """Metin-kopya turevi; ``selection`` verilirse metin yazilmaz (TASK-044).

    Secim listesi kosusunda karar mantigi ayni koddur; yalniz egitim/held-out
    ciktilari diske yazilmaz, SHA'lari hesaplanir ve her karar ``selection``a gider.

    Girdi bir alim manifestiyse (derlem.import-manifest.v1, TASK-049) belgeler
    ``store_root`` altindaki parcalardan, parca sirasinda, aday satiri olarak gelir
    (``import_manifest.manifest_candidate_lines``); asagidaki dongu -- PII, kalite,
    tekrar, yakin kopya, held-out, sinir asimi -- satir dosyasiyla AYNI koddur.

    Paralel on hesap (yalniz alim manifesti; ``workers`` > 1 ya da ``signals_dir``):
    belge-yerel sinyaller (PII, kalite gerekceleri, parmak izi, SimHash, doc_id)
    ``clean_candidate_signals`` ile parca satir grubu basina tablolarda hesaplanir;
    bu dongu ayni sirada ilerler, sinyali yeniden hesaplamak yerine tablodan alir
    (sira no / asama / doc_id dogrulanarak). Birebir kopya, yakin kopya, held-out,
    atilacak-satir listesi ve sayaclar burada, sirali kalir: cikti bayt bayt aynidir.
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")
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
    # Alim manifesti satir dosyasi degildir: satirlari belge sayilirsa manifest JSON'u
    # aday olurdu. Parcalar store_root altinda; yoksa kosu durur.
    import_manifest = load_import_manifest(input_path)
    if import_manifest is not None and store_root is None:
        raise ValueError("input is a derlem.import-manifest.v1 object; pass store_root to read its shards")
    use_signals = workers > 1 or signals_dir is not None
    if use_signals and import_manifest is None:
        raise ValueError("parallel pre-compute (workers > 1 / signals_dir) needs a derlem.import-manifest.v1 input")
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
    # tr-web-v4 (TASK-046): her gerekce karar kaydinda KENDI satiridir ve yargic
    # kimligi kural kodunun sha'sini tasir; v1-v3 bugunku tek satirlik bicimde kalir.
    v4_policy = effective_quality_policy == QUALITY_POLICY_TR_WEB_V4
    quality_judge = tr_web_v4_judge_id() if quality_policy == QUALITY_POLICY_TR_WEB_V4 else None
    mt_target = machine_translation.MT_TARGET if quality_policy == QUALITY_POLICY_TR_WEB_V4 else None

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
    # TASK-050: tekrar kararlarindan sonra uygulanan cikarma listesi (doc_id -> (aday satir no, karar)).
    post_drop: dict[str, tuple[int, dict[str, Any]]] = {}
    post_drop_sha256: str | None = None
    post_drop_used = 0
    train_bound_lines = 0
    if post_dedup_drop_path is not None:
        post_dedup_drop_path = post_dedup_drop_path.resolve(strict=True)
        loaded, post_drop_sha256, _ = load_subtraction_drops(post_dedup_drop_path)
        post_drop = {row["doc_id"]: (line_ordinal, row) for line_ordinal, row in loaded.items()}
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

    if selection is None:
        output = _AtomicOutput(output_path)
    else:
        output = HashOnlyOutput()
    rejections = _AtomicOutput(quality_rejections_path) if quality_rejections_path is not None else None
    if selection is None:
        held_out = _AtomicOutput(held_out_path) if held_out_path is not None else None
    else:
        held_out = HashOnlyOutput() if held_out_path is not None else None
    near_judge = (
        f"{SIMHASH_VERSION}-hamming{near_index.hamming_threshold}" if near_index is not None else ""
    )
    outputs = [item for item in (output, rejections, held_out) if item is not None]
    shard_progress: dict[str, int] = {}
    if import_manifest is not None:
        assert store_root is not None
        document_lines = manifest_candidate_lines(
            import_manifest, store_root, max_document_bytes, limit_documents=limit_lines, progress=shard_progress,
        )
    else:
        document_lines = _bounded_lines(input_path, max_document_bytes)
    signals: SignalPrecompute | None = None
    signal_summary: dict[str, Any] | None = None
    if use_signals:
        assert import_manifest is not None and store_root is not None
        signals = SignalPrecompute(
            import_manifest, store_root, workers=workers, signals_dir=signals_dir, temp_parent=output_path.parent,
            quality_policy=effective_quality_policy, near_dedup=near_index is not None,
            max_line_bytes=max_document_bytes, limit_documents=limit_lines,
        )
    try:
        with ExitStack() as stack:
            for item in outputs:
                item.open(stack)
            if signals is not None:
                stack.enter_context(signals)
            for ordinal, raw_line, oversized in document_lines:
                if limit_lines is not None and ordinal > limit_lines:
                    break
                total_lines += 1
                # Paralel on hesap: belge-yerel sinyal tablodan (sira no, asama, doc_id
                # dogrulanir); yoksa (eski yol) asagida ayni fonksiyonlarla hesaplanir.
                signal = signals.take(ordinal, raw_line, oversized) if signals is not None else None
                if oversized:
                    removed_oversized_lines += 1
                    if selection is not None:
                        selection.oversized(ordinal)
                    continue
                assert raw_line is not None

                stripped = raw_line.strip()
                if not stripped:
                    skipped_blank_lines += 1
                    if selection is not None:
                        selection.decide(
                            ordinal, hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
                            "empty_text", "reject", "clean-candidate", "blank_line",
                        )
                    continue

                if signal is None:
                    text, _ = _document_from_line(stripped)
                    counts = document_pii_counts(raw_line, stripped, text)
                else:
                    # Metin yalniz atma raporunun onizlemesi icin gerekir; sinyaller tablodadir.
                    text = _document_from_line(stripped)[0] if rejections is not None else ""
                    assert signal.pii_counts is not None
                    counts = signal.pii_counts
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
                    if selection is not None:
                        selection.decide(
                            ordinal, hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
                            "pii", "reject", PII_JUDGE,
                            ",".join(key for key in PII_KEYS if int(counts.get(key, 0)) > 0),
                        )
                    continue

                line_bytes = raw_line.encode("utf-8")
                line_digest = hashlib.sha256(line_bytes)
                if drop_list:
                    dropped = drop_list.get(line_digest.digest())
                    if dropped is not None:
                        removed_drop_list_lines += 1
                        if selection is not None:
                            selection.decide(
                                ordinal, line_digest.hexdigest(), selection.drop_list_type(dropped), "reject",
                                str(drop_list_method), str(dropped.get("reason") or drop_list_reason),
                            )
                        if rejections is not None:
                            rejections.write(_rejection_record(
                                ordinal=ordinal, reasons=(drop_list_reason,), full=True,
                                line_bytes=line_bytes, text=text, details=dropped,
                            ))
                        continue
                if signal is None:
                    quality_reasons = document_quality_reasons(text, stripped, effective_quality_policy, v4_policy)
                else:
                    assert signal.quality_reasons is not None
                    quality_reasons = signal.quality_reasons
                if quality_reasons:
                    removed_quality_lines += 1
                    if selection is not None and v4_policy:
                        for reason in quality_reasons:
                            selection.decide(
                                ordinal, line_digest.hexdigest(), "quality_rule", "reject",
                                str(quality_judge), reason,
                            )
                    elif selection is not None:
                        selection.decide(
                            ordinal, line_digest.hexdigest(), "quality_rule", "reject",
                            effective_quality_policy, ",".join(quality_reasons),
                        )
                    quality_reason_document_counts.update(quality_reasons)
                    if rejections is not None:
                        rejections.write(_rejection_record(
                            ordinal=ordinal, reasons=quality_reasons, full=v3, line_bytes=line_bytes, text=text,
                        ))
                    continue

                key = document_fingerprint_key(text) if signal is None else signal.fingerprint
                if key is None:
                    kept_short_or_unfingerprinted_lines += 1
                else:
                    earlier = seen_fingerprints.get(key)
                    if earlier is not None:
                        removed_duplicate_lines += 1
                        if selection is not None:
                            selection.decide(
                                ordinal, line_digest.hexdigest(), "duplicate", "reject",
                                FINGERPRINT_VERSION, f"normalized_duplicate_of={earlier}",
                            )
                        if rejections is not None and v3:
                            rejections.write(_rejection_record(
                                ordinal=ordinal, reasons=("normalized_duplicate",), full=True,
                                line_bytes=line_bytes, text=text, duplicate_of=earlier,
                            ))
                        continue
                    seen_fingerprints[key] = ordinal
                    indexed_fingerprints += 1

                if near_index is not None:
                    signature = document_simhash_signature(text) if signal is None else signal.simhash
                    if signature is not None:
                        partner = near_index.find_partner(signature)
                        if partner is not None:
                            removed_near_duplicate_lines += 1
                            if selection is not None:
                                selection.decide(
                                    ordinal, line_digest.hexdigest(), "near_duplicate", "reject",
                                    near_judge, f"near_duplicate_of={partner}",
                                )
                            if rejections is not None:
                                rejections.write(_rejection_record(
                                    ordinal=ordinal, reasons=("near_duplicate",), full=True,
                                    line_bytes=line_bytes, text=text, duplicate_of=partner,
                                ))
                            continue
                        near_index.add(signature, ordinal)

                encoded = line_bytes + b"\n"
                if post_drop:
                    to_held_out = held_out is not None and _is_held_out_hex(line_digest.hexdigest())
                    if not to_held_out:
                        train_bound_lines += 1
                    entry = post_drop.get(line_digest.hexdigest())
                    if entry is not None:
                        line_ordinal, row = entry
                        if to_held_out:
                            raise ValueError(
                                f"post-dedup drop doc_id {row['doc_id']} falls into the held-out partition "
                                f"(ordinal {ordinal}); only train documents can be dropped"
                            )
                        if line_ordinal != train_bound_lines:
                            raise ValueError(
                                f"post-dedup drop doc_id {row['doc_id']} names candidate line {line_ordinal}, "
                                f"the document is candidate line {train_bound_lines}"
                            )
                        post_drop_used += 1
                        if selection is not None:
                            selection.record({**row, "source_ordinal": ordinal})
                        if rejections is not None:
                            rejections.write(_rejection_record(
                                ordinal=ordinal, reasons=(str(row["reason"] or row["decision_type"]),), full=True,
                                line_bytes=line_bytes, text=text,
                                details={"judge": row["judge"], "run_id": row["run_id"], "candidate_line": line_ordinal},
                            ))
                        continue
                if held_out is not None and _is_held_out_hex(line_digest.hexdigest()):
                    held_out.write(encoded)
                    held_out_lines += 1
                    if selection is not None:
                        selection.decide(
                            ordinal, line_digest.hexdigest(), "held_out", "held_out", held_out_rule, None,
                        )
                        selection.select(ordinal, line_digest.hexdigest(), "held_out")
                else:
                    output.write(encoded)
                    written_lines += 1
                    if selection is not None:
                        selection.select(ordinal, line_digest.hexdigest(), "train")

            if post_drop and post_drop_used != len(post_drop):
                raise ValueError(
                    f"post-dedup drop list: {len(post_drop) - post_drop_used} of {len(post_drop)} entries match no "
                    "train document (doc_id/candidate line not found)"
                )
            if signals is not None:
                signal_summary = signals.finish(complete=limit_lines is None)
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
        interpreter_version=platform.python_version(),
        zlib_runtime_version=zlib.ZLIB_RUNTIME_VERSION,
        quality_judge=quality_judge,
        machine_translation_target=mt_target,
        input_kind=("import_manifest" if import_manifest is not None else None),
        import_manifest=(
            None if import_manifest is None else _import_manifest_summary(
                import_manifest, store_root, shard_progress, limit_lines,
            )
        ),
        signal_precompute=signal_summary,
        post_dedup_drop_path=(str(post_dedup_drop_path) if post_dedup_drop_path is not None else None),
        post_dedup_drop_sha256=post_drop_sha256,
        post_dedup_drop_entries=len(post_drop),
        removed_post_dedup_drop_lines=post_drop_used,
    )


def _import_manifest_summary(
    manifest: dict[str, Any],
    store_root: Path | None,
    progress: dict[str, int],
    limit_lines: int | None,
) -> dict[str, Any]:
    last = progress.get("last_source_ordinal")
    return {
        "schema": manifest["schema"],
        "dataset": manifest.get("dataset"),
        "revision": manifest.get("revision"),
        "config": manifest.get("config"),
        "line_format": CANDIDATE_LINE_FORMAT,
        "store_root": str(store_root) if store_root is not None else None,
        "documents_total": (manifest.get("totals") or {}).get("documents"),
        "shards_total": len(manifest["shards"]),
        "document_limit": limit_lines,
        "documents_read": progress.get("documents", 0),
        "last_source_ordinal": last,
        "shards": manifest_shards_covering(manifest, last if limit_lines is not None else None),
    }


def resolve_output_path(
    output_dir: Path,
    output_path: Path | None,
    source: dict[str, Any] | None,
    limit_lines: int | None,
    *,
    input_path: Path | None = None,
    quality_policy: str = QUALITY_POLICY_NONE,
    v3: bool = False,
    suffix: str = ".txt",
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
    return output_dir / f"{stem}{suffix}"


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
