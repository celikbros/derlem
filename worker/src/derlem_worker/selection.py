"""Secim listesiyle turetme (TASK-044, docs/veri_mimarisi_2026_10.md 2.6).

Turev metni kopyalamaz: ana kaynaktaki (parent) secilen belgelerin sira numarasi ve
``doc_id``'si (derlem.selection.v1, Parquet) + o kosunun kararlari (derlem.decision.v1,
Parquet) + manifest. Metin ancak ihracat aninda ``materialize`` ile uretilir ve
manifestteki beklenen SHA ile bayt bayt dogrulanir.

Komutlar:

    python -m derlem_worker.clean_candidate ... --selection-list   (secim listesi kosusu)
    python -m derlem_worker.selection materialize --manifest M [--parent P] [--store-root S] [--output O] [--held-out-output H]
    python -m derlem_worker.selection from-text-copy --parent P --train T [--held-out H] --output-dir D --name N
    python -m derlem_worker.selection subtract --manifest M --drop D --out PREFIX [--parent P] [--store-root S]

``subtract`` (TASK-050) secimin ``train`` bolmesinden bir cikarma listesindeki belgeleri
cikarir (ornegin baska kaynaklarda da bulunan normalize kopyalar); held-out aynen kalir,
kararlara dusen satirlar eklenir, yeni manifestin ``parent``i aynidir. Sonuc
``clean_candidate --post-dedup-drop`` ile yeniden turetmenin bayt bayt aynisidir.

``from-text-copy`` mevcut bir metin-kopya turevini (v1-v5) ana kaynak uzerinde secim
listesi olarak ifade eder: turev, ana kaynagin sirali alt dizisidir.

Ana kaynak bir alim manifestiyse (derlem.import-manifest.v1, TASK-049) manifestin
``parent.kind`` alani ``import_manifest``tir; materialize belgeleri manifestte
listelenen parcalardan (her biri SHA256 ile dogrulanir) aday satiri olarak uretir
(``import_manifest.CANDIDATE_LINE_FORMAT``) ve satir dosyasindaki korumalarin
aynisini uygular.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import tempfile
from typing import Any, BinaryIO, Iterator
import uuid

from derlem_worker.document_record import (
    DECISION_SCHEMA,
    DECISION_SCHEMA_VERSION,
    SELECTION_SCHEMA,
    SELECTION_SCHEMA_VERSION,
    ParquetFileInfo,
    ParquetRowWriter,
    file_sha256,
    read_decisions,
    read_selection,
    validate_decision,
)
from derlem_worker.sampling import _bounded_lines


SELECTION_MANIFEST_VERSION = "derlem.selection-manifest.v1"
MATERIALIZE_METHOD = "parent-lines-by-ordinal-sha256-verified-v1"
MATERIALIZE_METHOD_SHARDS = "import-manifest-candidate-lines-by-ordinal-sha256-verified-v1"
PARENT_KIND_IMPORT_MANIFEST = "import_manifest"
# TASK-050: secimden belge cikarma (yeniden turetmeden); clean_candidate'in
# --post-dedup-drop yoluyla bayt bayt ayni sonuc.
SUBTRACT_METHOD = "selection-subtract-v1"
# Atilacak-satir listesindeki kayit gerekcesi -> karar turu. Listede olmayan
# gerekce kosunun --drop-list-decision-type degerini alir.
DROP_LIST_REASON_DECISION_TYPES = {
    "source_not_in_scope_s2": "rights_scope",
    "trt_terms_forbid": "rights_scope",
    "language_not_turkish": "language",
}


class SelectionError(RuntimeError):
    pass


class HashOnlyOutput:
    """_AtomicOutput ile ayni arayuz; diske yazmaz, yalniz SHA256 ve boyut toplar.

    Secim listesi kosusunda metin-kopyanin ne olacagini (SHA'sini) kopyayi
    yazmadan bilmek icin."""

    def __init__(self) -> None:
        self.hasher = hashlib.sha256()
        self.byte_size = 0
        self.lines = 0

    def open(self, stack: ExitStack) -> None:
        return None

    def write(self, payload: bytes) -> None:
        self.hasher.update(payload)
        self.byte_size += len(payload)
        self.lines += 1

    def sync(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def cleanup(self) -> None:
        return None


@dataclass
class SelectionRecorder:
    """clean_candidate'in karar noktalarindan beslenir; iki Parquet yazar."""

    selection_path: Path
    decisions_path: Path
    run_id: str
    decided_at: datetime
    drop_list_decision_type: str = "language"
    selected: Counter = field(default_factory=Counter)
    decision_counts: Counter = field(default_factory=Counter)
    oversized_ordinals: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._selection = ParquetRowWriter(self.selection_path, SELECTION_SCHEMA, row_group_size=100_000)
        try:
            self._decisions = ParquetRowWriter(
                self.decisions_path, DECISION_SCHEMA, row_group_size=100_000, validator=validate_decision
            )
        except BaseException:
            self._selection.abort()
            raise
        self._last_ordinal = 0

    def _check_order(self, ordinal: int) -> None:
        if ordinal <= self._last_ordinal:
            raise SelectionError("selection ordinals must increase")
        self._last_ordinal = ordinal

    def select(self, ordinal: int, line_digest_hex: str, partition: str) -> None:
        self._check_order(ordinal)
        self._selection.add({"source_ordinal": ordinal, "doc_id": line_digest_hex, "partition": partition})
        self.selected[partition] += 1

    def decide(
        self,
        ordinal: int,
        line_digest_hex: str,
        decision_type: str,
        verdict: str,
        judge: str,
        reason: str | None,
    ) -> None:
        self._decisions.add({
            "doc_id": line_digest_hex,
            "source_ordinal": ordinal,
            "decision_type": decision_type,
            "verdict": verdict,
            "reason": reason,
            "judge": judge,
            "run_id": self.run_id,
            "decided_at": self.decided_at,
        })
        self.decision_counts[f"{decision_type}:{verdict}"] += 1

    def record(self, row: dict[str, Any]) -> None:
        """Hazir bir karar satirini (or. cikarma listesinden, kendi run_id'siyle) aynen yazar."""
        self._decisions.add(row)
        self.decision_counts[f"{row['decision_type']}:{row['verdict']}"] += 1

    def oversized(self, ordinal: int) -> None:
        # Sinir asan satirin metni okunmaz, doc_id'si yoktur: karar kaydina
        # giremez, manifestte sira numarasiyla durur.
        self.oversized_ordinals.append(ordinal)

    def drop_list_type(self, details: dict[str, Any] | None) -> str:
        reason = str((details or {}).get("reason") or "")
        return DROP_LIST_REASON_DECISION_TYPES.get(reason, self.drop_list_decision_type)

    def close(self) -> tuple[ParquetFileInfo, ParquetFileInfo]:
        try:
            selection = self._selection.close()
        except BaseException:
            self._decisions.abort()
            raise
        return selection, self._decisions.close()

    def abort(self) -> None:
        self._selection.abort()
        self._decisions.abort()


def write_selection_manifest(
    path: Path,
    *,
    report: dict[str, Any],
    parent_path: Path,
    parent_sha256: str,
    parent_byte_size: int,
    selection: ParquetFileInfo,
    decisions: ParquetFileInfo | None,
    recorder_counts: dict[str, int],
    decision_counts: dict[str, int],
    oversized_ordinals: list[int],
    expected: dict[str, dict[str, Any]],
    run_id: str | None,
    decided_at: str | None,
    method: str,
    parent_extra: dict[str, Any] | None = None,
    policies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parent: dict[str, Any] = {
        "path": str(parent_path),
        "sha256": parent_sha256,
        "byte_size": parent_byte_size,
    }
    if parent_extra:
        parent.update(parent_extra)
    shard_parent = parent.get("kind") == PARENT_KIND_IMPORT_MANIFEST
    manifest = {
        "schema_version": SELECTION_MANIFEST_VERSION,
        "method": method,
        "parent": parent,
        "max_document_bytes": report.get("max_document_bytes"),
        "selection": {
            "schema_version": SELECTION_SCHEMA_VERSION,
            "path": selection.path,
            "sha256": selection.sha256,
            "byte_size": selection.byte_size,
            "rows": selection.row_count,
            "partitions": dict(sorted(recorder_counts.items())),
        },
        "decisions": None if decisions is None else {
            "schema_version": DECISION_SCHEMA_VERSION,
            "path": decisions.path,
            "sha256": decisions.sha256,
            "byte_size": decisions.byte_size,
            "rows": decisions.row_count,
            "counts": dict(sorted(decision_counts.items())),
            "run_id": run_id,
            "decided_at": decided_at,
            "covers": "every non-selected document with a doc_id; oversized lines are listed below by ordinal",
        },
        "oversized_ordinals": oversized_ordinals,
        "expected_materialization": expected,
        "materialize_method": MATERIALIZE_METHOD_SHARDS if shard_parent else MATERIALIZE_METHOD,
        "report": report,
    }
    if policies is not None:
        manifest["policies"] = policies
    _write_json_atomic(path, manifest)
    return manifest


def _write_json_atomic(path: Path, value: Any) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Materialize
# --------------------------------------------------------------------------


class _VerifiedOutput:
    """Hedefin yanina gecici dosya (ya da yalniz hash); beklenen SHA tutarsa yerine gecer."""

    def __init__(self, path: Path | None) -> None:
        self.path = path.resolve() if path is not None else None
        self.hasher = hashlib.sha256()
        self.byte_size = 0
        self.lines = 0
        self.handle: BinaryIO | None = None
        self.temp_path: Path | None = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(prefix=f"{self.path.name}.", suffix=".tmp", dir=self.path.parent)
            self.temp_path = Path(temp_name)
            self.handle = os.fdopen(descriptor, "wb")

    def write(self, payload: bytes) -> None:
        if self.handle is not None:
            self.handle.write(payload)
        self.hasher.update(payload)
        self.byte_size += len(payload)
        self.lines += 1

    def finish(self, expected: dict[str, Any] | None, label: str) -> dict[str, Any]:
        digest = self.hasher.hexdigest()
        result = {"sha256": digest, "byte_size": self.byte_size, "lines": self.lines}
        if self.handle is not None:
            self.handle.flush()
            os.fsync(self.handle.fileno())
            self.handle.close()
            self.handle = None
        if expected is not None and (expected.get("sha256") != digest or expected.get("byte_size") != self.byte_size):
            self.discard()
            raise SelectionError(
                f"materialized {label} does not match the manifest: sha256 {digest} != {expected.get('sha256')}"
            )
        if self.temp_path is not None and self.path is not None:
            if self.path.exists():
                self.discard()
                raise SelectionError(f"refusing to overwrite existing output: {self.path}")
            self.temp_path.replace(self.path)
            self.temp_path = None
        return result

    def discard(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None
        if self.temp_path is not None:
            self.temp_path.unlink(missing_ok=True)
            self.temp_path = None


def _parent_lines(manifest: dict[str, Any], parent: Path, store_root: Path | None, max_document_bytes: int):
    """Ana kaynagin ``(sira_no, satir | None, sinir_asimi)`` akisi.

    Satir dosyasinda dosyanin satirlari; alim manifestinde manifestin listeledigi
    parcalarin belgeleri aday satiri olarak (secim kosusuyla ayni fonksiyon). Parca
    listesi manifesttekiyle ayni olmali: alim manifesti nesnesi (boyutu ve istenirse
    SHA'si yukarida dogrulandi) parcalari baska sirada ya da baska SHA ile veriyorsa
    uretim durur.
    """
    info = manifest["parent"]
    if info.get("kind") != PARENT_KIND_IMPORT_MANIFEST:
        return _bounded_lines(parent, max_document_bytes)
    from derlem_worker.import_manifest import (
        CANDIDATE_LINE_FORMAT,
        load_import_manifest,
        manifest_candidate_lines,
    )

    if info.get("line_format") != CANDIDATE_LINE_FORMAT:
        raise SelectionError(f"unsupported candidate line format: {info.get('line_format')!r}")
    root = store_root or (Path(info["store_root"]) if info.get("store_root") else None)
    if root is None:
        raise SelectionError("import-manifest parent needs a store root")
    import_manifest = load_import_manifest(parent)
    if import_manifest is None:
        raise SelectionError("parent is not a derlem.import-manifest.v1 object")
    listed = [(shard["sha256"], shard["byte_size"], shard["row_count"]) for shard in info.get("shards") or []]
    actual = [(shard["sha256"], shard["byte_size"], shard["row_count"]) for shard in import_manifest["shards"]]
    if not listed or actual[: len(listed)] != listed:
        raise SelectionError("import manifest shards differ from the selection manifest's shard list")
    limited = dict(import_manifest)
    limited["shards"] = import_manifest["shards"][: len(listed)]
    return manifest_candidate_lines(limited, root.resolve(strict=True), max_document_bytes)


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SELECTION_MANIFEST_VERSION:
        raise SelectionError("not a selection manifest")
    return manifest


def _manifest_file(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (manifest_path.parent / path).resolve()
    return path


def _resolve_parent(manifest: dict[str, Any], parent_path: Path | None, verify_parent: bool) -> Path:
    parent = Path(parent_path or manifest["parent"]["path"]).resolve(strict=True)
    if parent.stat().st_size != manifest["parent"]["byte_size"]:
        raise SelectionError("parent byte size differs from the manifest")
    if verify_parent:
        digest, _ = file_sha256(parent)
        if digest != manifest["parent"]["sha256"]:
            raise SelectionError("parent sha256 differs from the manifest")
    return parent


def _stream_selected(
    manifest: dict[str, Any],
    parent: Path,
    store_root: Path | None,
    selection_path: Path,
    outputs: dict[str, "_VerifiedOutput"],
) -> None:
    """Secilen satirlari ana kaynaktan sirayla bolmelerine yazar (materialize'in cekirdegi)."""
    max_document_bytes = int(manifest["max_document_bytes"])
    selected = read_selection(selection_path)
    current = next(selected, None)
    last = 0
    for ordinal, raw_line, oversized in _parent_lines(manifest, parent, store_root, max_document_bytes):
        if current is None:
            break
        want = int(current["source_ordinal"])
        if want <= last:
            raise SelectionError("selection ordinals must increase")
        if ordinal < want:
            continue
        if oversized or raw_line is None:
            raise SelectionError(f"selected ordinal {want} is oversized in the parent")
        line_bytes = raw_line.encode("utf-8")
        if hashlib.sha256(line_bytes).hexdigest() != current["doc_id"]:
            raise SelectionError(f"parent line {want} does not match its doc_id")
        partition = current["partition"]
        if partition not in outputs:
            raise SelectionError(f"unknown partition {partition!r}")
        outputs[partition].write(line_bytes + b"\n")
        last = want
        current = next(selected, None)
    if current is not None:
        raise SelectionError(f"selected ordinal {current['source_ordinal']} is beyond the end of the parent")


def materialize(
    manifest_path: Path,
    *,
    parent_path: Path | None = None,
    output_path: Path | None = None,
    held_out_output_path: Path | None = None,
    verify_parent: bool = False,
    store_root: Path | None = None,
) -> dict[str, Any]:
    """Secim listesinden metni uretir; ``output_path`` None ise yalniz SHA hesaplar.

    Korumalar: secim dosyasinin SHA'si manifestle ayni; her secilen satirin
    SHA256'si doc_id ile ayni; sira numaralari artan ve ana kaynakta mevcut;
    uretilen metnin SHA'si ve boyutu manifestin beklentisiyle ayni. Biri tutmazsa
    cikti yayimlanmaz. Ana kaynak alim manifestiyse (TASK-049) satirlar parcalardan
    gelir (``store_root`` verilmezse manifestteki depo koku); her parca okunmadan
    once SHA256 ile dogrulanir.
    """
    manifest = _load_manifest(manifest_path)
    parent = _resolve_parent(manifest, parent_path, verify_parent)
    selection_path = _manifest_file(manifest_path, manifest["selection"]["path"])
    selection_digest, _ = file_sha256(selection_path)
    if selection_digest != manifest["selection"]["sha256"]:
        raise SelectionError("selection list sha256 differs from the manifest")
    expected = manifest["expected_materialization"]

    outputs = {
        "train": _VerifiedOutput(output_path),
        "held_out": _VerifiedOutput(held_out_output_path),
    }
    try:
        _stream_selected(manifest, parent, store_root, selection_path, outputs)
        results = {}
        for partition, output in outputs.items():
            results[partition] = output.finish(expected.get(partition), partition)
    except BaseException:
        for output in outputs.values():
            output.discard()
        raise
    return {
        "method": manifest.get("materialize_method", MATERIALIZE_METHOD),
        "manifest": str(manifest_path),
        "parent": str(parent),
        "outputs": results,
        "output_paths": {
            "train": str(output_path) if output_path else None,
            "held_out": str(held_out_output_path) if held_out_output_path else None,
        },
    }


# --------------------------------------------------------------------------
# Subtract (TASK-050): secimden belge cikarma, yeniden turetmeden
# --------------------------------------------------------------------------


def load_subtraction_drops(path: Path) -> tuple[dict[int, dict[str, Any]], str, int]:
    """Cikarma listesi: derlem.decision.v1 Parquet, her satir bir ``reject`` karari.

    ``source_ordinal`` = adayin (secimin ``train`` bolmesinin) 1'den baslayan SATIR
    numarasi -- aday kaynagin ``document_fingerprints.source_ordinal``'i; ``doc_id`` =
    o satirin baytlarinin SHA256'si. Ayni satir numarasi ya da ayni doc_id iki kez
    gecerse liste belirsizdir: reddedilir. Donus: (satir no -> karar satiri, sha256, boyut).
    """
    path = path.resolve(strict=True)
    digest, byte_size = file_sha256(path)
    drops: dict[int, dict[str, Any]] = {}
    seen_doc_ids: set[str] = set()
    for row in read_decisions(path):
        validate_decision(row)
        if row["verdict"] != "reject":
            raise SelectionError(f"drop row for doc_id {row['doc_id']} is not a reject: {row['verdict']!r}")
        line_ordinal = row.get("source_ordinal")
        if not isinstance(line_ordinal, int) or isinstance(line_ordinal, bool) or line_ordinal < 1:
            raise SelectionError(f"drop row for doc_id {row['doc_id']} has no candidate line number")
        if line_ordinal in drops:
            raise SelectionError(f"ambiguous drop list: candidate line {line_ordinal} is listed twice")
        if row["doc_id"] in seen_doc_ids:
            raise SelectionError(f"ambiguous drop list: doc_id {row['doc_id']} is listed twice")
        seen_doc_ids.add(row["doc_id"])
        drops[line_ordinal] = row
    if not drops:
        raise SelectionError("drop list is empty")
    return drops, digest, byte_size


_REFERENCE_RE = re.compile(r"(?:normalized_duplicate_of|near_duplicate_of)=(\d+)")


def subtract(
    manifest_path: Path,
    drop_path: Path,
    out_prefix: Path,
    *,
    parent_path: Path | None = None,
    store_root: Path | None = None,
    verify_parent: bool = False,
) -> dict[str, Any]:
    """Secim listesinden cikarma listesindeki ``train`` belgelerini cikarir.

    Yeni secim = eski secim eksi dusenler (held-out bolmesi aynen); yeni kararlar =
    eski kararlar + dusen satirlar, ebeveyn sira numarasi yerine konmus ve kendi
    sira numaralarinin yerine (sirali) yerlestirilmis; yeni manifestin ``parent``i
    aynidir, ``subtraction`` bolumu girdi secim/karar/cikarma SHA'larini ve sayiyi
    yazar. Beklenen metin (``expected_materialization``) yeni secimden ana kaynak
    uzerinden hash-only uretilir; held-out beklentisi eskisiyle ayni olmali.

    Bu, ``clean_candidate --post-dedup-drop`` ile yeniden turetmenin bayt bayt
    aynisidir: dusen belge tekrar/yakin-kopya kayitlarinda kalir (sonraki kopyalari
    yine onun kopyasi sayilir), yalniz secime girmez.

    Reddedilenler (hicbir sey yazilmaz): satir numarasi -> secim satiri eslemesi
    tutmuyor (doc_id farkli, train bolmesinin disinda), dusen doc_id secimde birden
    cok kez geciyor ya da held-out bolmesinde, ebeveyn sira numarasinda zaten karar
    satiri var, girdi dosyalari manifestle tutmuyor, cikti dosyalari mevcut.
    """
    manifest_path = manifest_path.resolve(strict=True)
    manifest = _load_manifest(manifest_path)
    if manifest.get("decisions") is None:
        raise SelectionError("subtract needs a manifest with a decision snapshot")
    out_prefix = out_prefix.resolve()
    targets = {
        "selection": out_prefix.with_name(out_prefix.name + ".selection.parquet"),
        "decisions": out_prefix.with_name(out_prefix.name + ".decisions.parquet"),
        "manifest": out_prefix.with_name(out_prefix.name + ".selection.manifest.json"),
    }
    selection_path = _manifest_file(manifest_path, manifest["selection"]["path"])
    decisions_path = _manifest_file(manifest_path, manifest["decisions"]["path"])
    inputs = {selection_path, decisions_path, manifest_path, drop_path.resolve()}
    for target in targets.values():
        if target in inputs:
            raise SelectionError(f"output would overwrite an input: {target}")
        if target.exists():
            raise SelectionError(f"refusing to overwrite existing file: {target}")
    for label, path in (("selection", selection_path), ("decisions", decisions_path)):
        digest, _ = file_sha256(path)
        if digest != manifest[label]["sha256"]:
            raise SelectionError(f"{label} sha256 differs from the manifest")
    manifest_digest, _ = file_sha256(manifest_path)
    drops, drop_digest, drop_size = load_subtraction_drops(drop_path)
    drop_doc_ids = {row["doc_id"] for row in drops.values()}
    parent = _resolve_parent(manifest, parent_path, verify_parent)

    written: list[Path] = []
    try:
        # 1. Secim: train satir numarasi -> ebeveyn sira numarasi, doc_id ile dogrulanir.
        problems: list[str] = []
        occurrences: Counter = Counter()
        mapped: dict[int, int] = {}
        partitions: Counter = Counter()
        train_lines = 0
        writer = ParquetRowWriter(targets["selection"], SELECTION_SCHEMA, row_group_size=100_000)
        try:
            for row in read_selection(selection_path):
                partition = row["partition"]
                if row["doc_id"] in drop_doc_ids:
                    occurrences[row["doc_id"]] += 1
                    if partition != "train":
                        problems.append(
                            f"drop doc_id {row['doc_id']} is in the {partition} partition (parent ordinal "
                            f"{row['source_ordinal']}); only train documents can be subtracted"
                        )
                if partition == "train":
                    train_lines += 1
                    drop = drops.get(train_lines)
                    if drop is not None:
                        if drop["doc_id"] == row["doc_id"]:
                            mapped[train_lines] = int(row["source_ordinal"])
                            continue
                        problems.append(
                            f"drop for candidate line {train_lines} names doc_id {drop['doc_id']}, "
                            f"the selection's train line {train_lines} is {row['doc_id']}"
                        )
                writer.add(row)
                partitions[partition] += 1
            for doc_id, count in sorted(occurrences.items()):
                if count > 1:
                    problems.append(f"ambiguous: drop doc_id {doc_id} occurs {count} times in the selection")
            for line_ordinal in sorted(drops):
                if line_ordinal > train_lines:
                    problems.append(
                        f"drop candidate line {line_ordinal} is beyond the train partition ({train_lines} lines)"
                    )
            if problems:
                raise SelectionError("subtraction refused: " + "; ".join(problems[:20]))
            if train_lines != manifest["selection"]["partitions"].get("train"):
                raise SelectionError("train partition size differs from the manifest")
            selection_info = writer.close()
        except BaseException:
            writer.abort()
            raise
        written.append(targets["selection"])

        # 2. Kararlar: eski satirlar + dusenler, ebeveyn sira numarasinin yerine.
        pending = sorted(
            ((parent_ordinal, {**drops[line_ordinal], "source_ordinal": parent_ordinal})
             for line_ordinal, parent_ordinal in mapped.items()),
            key=lambda item: item[0],
        )
        dropped_parent = {parent_ordinal for parent_ordinal, _ in pending}
        references: Counter = Counter()
        decision_counts: Counter = Counter()
        writer = ParquetRowWriter(
            targets["decisions"], DECISION_SCHEMA, row_group_size=100_000, validator=validate_decision
        )
        try:
            index = 0
            last = 0
            for row in read_decisions(decisions_path):
                ordinal = row.get("source_ordinal")
                if ordinal is None:
                    raise SelectionError("a decision row has no source_ordinal; the merge position is undefined")
                if ordinal < last:
                    raise SelectionError("decision rows are not in ordinal order; the merge position is undefined")
                last = ordinal
                while index < len(pending) and pending[index][0] < ordinal:
                    writer.add(pending[index][1])
                    decision_counts[f"{pending[index][1]['decision_type']}:reject"] += 1
                    index += 1
                if ordinal in dropped_parent:
                    raise SelectionError(
                        f"parent ordinal {ordinal} already has a decision row; it is not a plain train selection"
                    )
                for match in _REFERENCE_RE.finditer(row.get("reason") or ""):
                    if int(match.group(1)) in dropped_parent:
                        references[f"{row['decision_type']}:{row['verdict']}"] += 1
                writer.add(row)
                decision_counts[f"{row['decision_type']}:{row['verdict']}"] += 1
            for _, row in pending[index:]:
                writer.add(row)
                decision_counts[f"{row['decision_type']}:reject"] += 1
            decisions_info = writer.close()
        except BaseException:
            writer.abort()
            raise
        written.append(targets["decisions"])

        # 3. Beklenen metin: yeni secimden ana kaynak uzerinden (yalniz hash).
        outputs = {"train": _VerifiedOutput(None), "held_out": _VerifiedOutput(None)}
        _stream_selected(manifest, parent, store_root, targets["selection"], outputs)
        old_expected = manifest["expected_materialization"]
        expected = {key: outputs[key].finish(None, key) for key in old_expected}
        if "held_out" in old_expected and expected["held_out"] != old_expected["held_out"]:
            raise SelectionError("held-out materialization changed; subtraction must leave it untouched")
        if expected["train"]["lines"] != old_expected["train"]["lines"] - len(drops):
            raise SelectionError("train line count is not the old count minus the drops")

        drop_rows = list(drops.values())
        new_manifest = dict(manifest)
        new_manifest["selection"] = {
            **manifest["selection"],
            "path": selection_info.path,
            "sha256": selection_info.sha256,
            "byte_size": selection_info.byte_size,
            "rows": selection_info.row_count,
            "partitions": dict(sorted(partitions.items())),
        }
        new_manifest["decisions"] = {
            **manifest["decisions"],
            "path": decisions_info.path,
            "sha256": decisions_info.sha256,
            "byte_size": decisions_info.byte_size,
            "rows": decisions_info.row_count,
            "counts": dict(sorted(decision_counts.items())),
            "covers": manifest["decisions"].get("covers", "")
            + "; plus the subtraction rows (see subtraction; their own run_id/decided_at)",
        }
        new_manifest["expected_materialization"] = expected
        new_manifest["subtraction"] = {
            "method": SUBTRACT_METHOD,
            "input_manifest": {"path": str(manifest_path), "sha256": manifest_digest},
            "input_selection": {
                "sha256": manifest["selection"]["sha256"], "rows": manifest["selection"]["rows"],
            },
            "input_decisions": {
                "sha256": manifest["decisions"]["sha256"], "rows": manifest["decisions"]["rows"],
            },
            "input_expected_materialization": old_expected,
            "drop": {
                "path": str(drop_path.resolve()),
                "sha256": drop_digest,
                "byte_size": drop_size,
                "rows": len(drops),
                "decision_types": dict(sorted(Counter(row["decision_type"] for row in drop_rows).items())),
                "judges": sorted({row["judge"] for row in drop_rows}),
                "run_ids": sorted({row["run_id"] for row in drop_rows}),
                "source_ordinal": "candidate line number (train partition, 1-based), mapped to the parent ordinal",
            },
            "dropped": len(drops),
            "dropped_parent_ordinals": [parent_ordinal for parent_ordinal, _ in pending],
            "rejections_referencing_dropped": dict(sorted(references.items())),
        }
        new_manifest.pop("manifest_path", None)
        _write_json_atomic(targets["manifest"], new_manifest)
        written.append(targets["manifest"])
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    new_manifest["manifest_path"] = str(targets["manifest"])
    return new_manifest


# --------------------------------------------------------------------------
# Metin-kopya turevi -> secim listesi
# --------------------------------------------------------------------------


def _derived_lines(path: Path | None) -> Iterator[bytes]:
    if path is None:
        return
    with path.open("rb") as handle:
        for line in handle:
            if not line.endswith(b"\n"):
                raise SelectionError(f"{path.name}: last line has no LF; not a clean-candidate output")
            yield line[:-1]


def selection_from_text_copy(
    parent_path: Path,
    train_path: Path,
    *,
    held_out_path: Path | None,
    output_dir: Path,
    name: str,
    max_document_bytes: int,
    source_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Var olan bir metin-kopya turevini ana kaynak uzerinde secim listesi olarak ifade eder.

    Turev ana kaynagin sirali alt dizisidir (clean_candidate satiri oldugu gibi,
    sondaki LF ile yazar). Ana kaynak tek geciste yurunur; turevin siradaki satiri
    ana kaynagin siradaki satiriyla bayt bayt esitse secilir. Ayni metin ana
    kaynakta iki kez geciyorsa ilk gecis secilir: kararlar metne baglidir, bu
    yuzden uretilen metin her durumda aynidir. Turev tukenmezse alt dizi degildir: hata.
    Bu yolda karar anlik goruntusu yoktur (kararlar eski kosunun raporundadir).
    """
    parent = parent_path.resolve(strict=True)
    selection_path = output_dir / f"{name}.selection.parquet"
    manifest_path = output_dir / f"{name}.selection.manifest.json"
    for target in (selection_path, manifest_path):
        if target.exists():
            raise SelectionError(f"refusing to overwrite existing file: {target}")
    writer = ParquetRowWriter(selection_path, SELECTION_SCHEMA, row_group_size=100_000)
    counts: Counter = Counter()
    expected = {"train": _VerifiedOutput(None), "held_out": _VerifiedOutput(None)}
    try:
        train = _derived_lines(train_path)
        held = _derived_lines(held_out_path)
        next_train = next(train, None)
        next_held = next(held, None)
        oversized_ordinals: list[int] = []
        for ordinal, raw_line, oversized in _bounded_lines(parent, max_document_bytes):
            if oversized or raw_line is None:
                oversized_ordinals.append(ordinal)
                continue
            line_bytes = raw_line.encode("utf-8")
            if next_train is not None and line_bytes == next_train:
                partition = "train"
                next_train = next(train, None)
            elif next_held is not None and line_bytes == next_held:
                partition = "held_out"
                next_held = next(held, None)
            else:
                continue
            writer.add({
                "source_ordinal": ordinal,
                "doc_id": hashlib.sha256(line_bytes).hexdigest(),
                "partition": partition,
            })
            expected[partition].write(line_bytes + b"\n")
            counts[partition] += 1
        if next_train is not None or next_held is not None:
            raise SelectionError("derived file is not an ordered subsequence of the parent")
        selection = writer.close()
    except BaseException:
        writer.abort()
        raise
    parent_digest, parent_size = file_sha256(parent)
    expected_result = {key: value.finish(None, key) for key, value in expected.items()}
    if held_out_path is None:
        expected_result.pop("held_out")
    manifest = write_selection_manifest(
        manifest_path,
        report={
            "max_document_bytes": max_document_bytes,
            "derived_from_text_copy": {
                "train_path": str(train_path),
                "held_out_path": str(held_out_path) if held_out_path else None,
            },
            "source_report": source_report,
            "interpreter_version": platform.python_version(),
        },
        parent_path=parent,
        parent_sha256=parent_digest,
        parent_byte_size=parent_size,
        selection=selection,
        decisions=None,
        recorder_counts=dict(counts),
        decision_counts={},
        oversized_ordinals=oversized_ordinals,
        expected=expected_result,
        run_id=None,
        decided_at=None,
        method="selection-from-text-copy-v1",
    )
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def new_run_id() -> str:
    return str(uuid.uuid4())


def run_started_at() -> datetime:
    return datetime.now(UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description="Selection-list derivation: materialize text at export time")
    commands = parser.add_subparsers(dest="command", required=True)

    m = commands.add_parser("materialize", help="Produce text from a selection list and verify its sha256")
    m.add_argument("--manifest", type=Path, required=True)
    m.add_argument("--parent", type=Path, help="Parent object path (default: manifest parent.path)")
    m.add_argument("--output", type=Path, help="Train text output; omitted = hash only, nothing written")
    m.add_argument("--held-out-output", type=Path, help="Held-out text output; omitted = hash only")
    m.add_argument("--verify-parent", action="store_true", help="Also hash the whole parent and compare")
    m.add_argument(
        "--store-root", type=Path,
        help="Object store root for an import-manifest parent (default: the store_root in the manifest)",
    )

    s = commands.add_parser(
        "subtract",
        help="Remove train documents listed in a drop decisions file from a selection (no re-derivation)",
    )
    s.add_argument("--manifest", type=Path, required=True, help="Input selection manifest")
    s.add_argument(
        "--drop", type=Path, required=True,
        help="derlem.decision.v1 parquet of reject rows; source_ordinal = candidate (train) line number",
    )
    s.add_argument("--out", type=Path, required=True, help="Output prefix: <out>.selection.parquet/.decisions.parquet/"
                   ".selection.manifest.json")
    s.add_argument("--parent", type=Path, help="Parent object path (default: manifest parent.path)")
    s.add_argument("--store-root", type=Path, help="Object store root for an import-manifest parent")
    s.add_argument("--verify-parent", action="store_true", help="Also hash the whole parent and compare")

    f = commands.add_parser("from-text-copy", help="Express an existing text-copy derivative as a selection list")
    f.add_argument("--parent", type=Path, required=True)
    f.add_argument("--train", type=Path, required=True)
    f.add_argument("--held-out", type=Path)
    f.add_argument("--output-dir", type=Path, required=True)
    f.add_argument("--name", required=True)
    f.add_argument("--max-document-bytes", type=int, required=True)
    f.add_argument("--source-report", type=Path, help="The derivative's clean-candidate manifest, copied into ours")
    args = parser.parse_args()

    if args.command == "materialize":
        result = materialize(
            args.manifest,
            parent_path=args.parent,
            output_path=args.output,
            held_out_output_path=args.held_out_output,
            verify_parent=args.verify_parent,
            store_root=args.store_root,
        )
    elif args.command == "subtract":
        result = subtract(
            args.manifest,
            args.drop,
            args.out,
            parent_path=args.parent,
            store_root=args.store_root,
            verify_parent=args.verify_parent,
        )
    else:
        source_report = None
        if args.source_report:
            source_report = json.loads(args.source_report.read_text(encoding="utf-8"))
        result = selection_from_text_copy(
            args.parent,
            args.train,
            held_out_path=args.held_out,
            output_dir=args.output_dir,
            name=args.name,
            max_document_bytes=args.max_document_bytes,
            source_report=source_report,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
