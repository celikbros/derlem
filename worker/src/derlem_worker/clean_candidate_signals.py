"""clean_candidate icin paralel on hesap (TASK-049 ek isi, 2026-10-13).

Secim gecisinin pahali kismi BELGE-YEREL'dir: PII taramasi, kalite kurallari
(tr-web-v4: makine cevirisi, ticari sayfa, v3), normalize parmak izi, SimHash
imzasi ve doc_id (aday satirinin SHA256'si). Bunlar bir belgenin yalniz kendi
baytlarina baglidir; sirali duruma (birebir kopya "ilk gorulen kalir", yakin
kopya kovalari, held-out, sayaclar) bagli DEGILDIR. Bu modul:

1. **Paylasilan belge-yerel fonksiyonlar** (``document_pii_counts``,
   ``document_quality_reasons``, ``document_fingerprint_key``,
   ``document_simhash_signature``, ``line_url``): ``clean_candidate``'in tek
   surecli dongusu de bunlari cagirir -- iki yol AYNI kodu kosar.
2. **Sinyal tablosu**: alim manifestindeki her parcanin her Parquet satir grubu
   icin bir tablo (``s<parca>-g<grup>.parquet``, derlem.clean-candidate-signals.v1):
   belge basina sira no, asama, doc_id, PII sayaclari, kalite gerekceleri, parmak
   izi, SimHash. Kimlik (parca SHA'si + satir grubu + politika + yargic + kod
   SHA'si + yorumlayici/zlib) tablonun Parquet metaverisindedir; kimlik tutmazsa
   tablo REDDEDILIR ve yeniden hesaplanir. Tablo belirlenimcidir (sabit pyarrow,
   sabit yazici ayarlari): iki kosu ayni bayt.
3. **SignalPrecompute**: tablolari ``multiprocessing`` (spawn) havuzunda uretir,
   karar dongusune sira no sirasinda verir. Dongu her belgede satiri parcadan
   KENDISI okur (parca SHA dogrulamasi dahil) ve tablo satirini dogrular: sira no,
   asama (sinir asimi / bos) ve doc_id tutmazsa kosu durur. Boylece tablo yalniz
   dogrulanmis baytlara ait sinyali tasiyabilir.

Windows'ta spawn: isci fonksiyonu modul duzeyindedir; bu modul yalniz gereken
modulleri import eder (veritabani, yapilandirma, ``derlem_worker.__main__`` YOK).
"""

from __future__ import annotations

from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import shutil
import tempfile
from typing import Any, Mapping, NamedTuple
import zlib

import pyarrow as pa
import pyarrow.parquet as pq

from derlem_worker.document_record import (
    SCHEMA_METADATA_KEY,
    SHARD_COMPRESSION,
    SHARD_COMPRESSION_LEVEL,
    SHARD_FORMAT_VERSION,
    _require_pinned_writer,
)
from derlem_worker.fingerprints import document_fingerprint
from derlem_worker.import_manifest import (
    CANDIDATE_LINE_FORMAT,
    ImportManifestError,
    candidate_line,
    manifest_shard_paths,
)
from derlem_worker.pii import PII_KEYS, count_pii_in_text
from derlem_worker.quality_filters import QUALITY_POLICY_TR_WEB_V4, quality_rejection_reasons
from derlem_worker.quality_v4 import RULE_SOURCE_FILES
from derlem_worker.quality_v4 import judge_id as tr_web_v4_judge_id
from derlem_worker.sampling import _document_from_line
from derlem_worker.similarity import document_simhash


SIGNALS_SCHEMA_VERSION = "derlem.clean-candidate-signals.v1"
IDENTITY_METADATA_KEY = b"derlem.signals.identity"

# Belgenin tek surecli dongude ulastigi son belge-yerel asama.
STAGE_OVERSIZED = 0  # satir siniri asildi; satir okunmaz, sinyal yok
STAGE_BLANK = 1  # bos satir (parcada olamaz; satir sozlesmesi icin)
STAGE_PII = 2  # PII bulundu; kalite hesaplanmaz
STAGE_QUALITY = 3  # kalite gerekcesi var; parmak izi hesaplanmaz
STAGE_PASS = 4  # kalite gecti; parmak izi (+ SimHash) hesaplandi
STAGES = frozenset({STAGE_OVERSIZED, STAGE_BLANK, STAGE_PII, STAGE_QUALITY, STAGE_PASS})

SIGNALS_SCHEMA = pa.schema(
    [
        pa.field("source_ordinal", pa.int64(), nullable=False),
        pa.field("stage", pa.int8(), nullable=False),
        pa.field("doc_id", pa.binary(32)),
        pa.field("pii", pa.list_(pa.int64())),
        pa.field("quality_reasons", pa.list_(pa.string())),
        pa.field("fingerprint", pa.binary(32)),
        pa.field("simhash", pa.uint64()),
    ],
    metadata={SCHEMA_METADATA_KEY: SIGNALS_SCHEMA_VERSION.encode("ascii")},
)
_SIGNAL_COLUMNS = ("source_ordinal", "text", "provenance")

# Sinyali belirleyen kaynak dosyalar (LF baytlari): biri degisirse tablolar reddedilir.
SIGNAL_SOURCE_FILES = tuple(sorted({
    *RULE_SOURCE_FILES,
    "pii.py",
    "fingerprints.py",
    "similarity.py",
    "sampling.py",
    "canonical.py",
    "import_manifest.py",
    "clean_candidate_signals.py",
}))


class SignalTableError(RuntimeError):
    """Sinyal tablosu belgeyle tutmuyor (sira no, asama ya da doc_id): kosu durur."""


# --------------------------------------------------------------------------
# Belge-yerel fonksiyonlar (tek surecli dongu ve isciler AYNI fonksiyonlari cagirir)
# --------------------------------------------------------------------------


def line_url(line: str) -> str | None:
    """Satir bir JSON kaydiysa adresi: ust duzey `url` ya da `provenance.url`
    (ortak belge kaydi). Duz metin satirinda None. Yalniz tr-web-v4 okur."""
    if not line.startswith("{"):
        return None
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    url = value.get("url")
    if not isinstance(url, str):
        provenance = value.get("provenance")
        url = provenance.get("url") if isinstance(provenance, dict) else None
    return url if isinstance(url, str) and url.strip() else None


def document_pii_counts(raw_line: str, stripped: str, text: str) -> dict[str, int]:
    counts = count_pii_in_text(raw_line)
    if text != stripped:
        # JSON kaydi (TASK-049): satirda belge ici satir sonlari kacisli
        # (\\n) durur; iki satira bolunmus bir numara satirda gorunmez ama
        # metinde (ve TXT ihracatinda) gorunur. Metin de taranir, sayac
        # anahtar basina iki gorunumun buyugudur. Duz metin satirinda
        # metin satirin kendisidir: davranis degismez.
        text_counts = count_pii_in_text(text)
        counts = {
            key: max(int(counts.get(key, 0)), int(text_counts.get(key, 0))) for key in PII_KEYS
        }
    return counts


def document_quality_reasons(text: str, stripped: str, policy: str, v4_policy: bool) -> tuple[str, ...]:
    return quality_rejection_reasons(text, policy, url=(line_url(stripped) if v4_policy else None))


def document_fingerprint_key(text: str) -> bytes | None:
    """Normalize metnin SHA256'si (32 bayt); kisa/bos metinde None."""
    fingerprint = document_fingerprint(text) if text else None
    if fingerprint is None:
        return None
    normalized_sha256, _ = fingerprint
    return bytes.fromhex(normalized_sha256)


def document_simhash_signature(text: str) -> int | None:
    return document_simhash(text) if text else None


def line_signals(
    raw_line: str, *, quality_policy: str, v4_policy: bool, near_dedup: bool,
) -> tuple[int, bytes, list[int] | None, list[str] | None, bytes | None, int | None]:
    """(asama, doc_id, pii, kalite gerekceleri, parmak izi, simhash) -- tek surecli
    dongunun sirasi ve kisa devreleriyle: PII varsa kalite yok, gerekce varsa parmak izi yok."""
    doc_id = hashlib.sha256(raw_line.encode("utf-8")).digest()
    stripped = raw_line.strip()
    if not stripped:
        return STAGE_BLANK, doc_id, None, None, None, None
    text, _ = _document_from_line(stripped)
    counts = document_pii_counts(raw_line, stripped, text)
    pii = [int(counts.get(key, 0)) for key in PII_KEYS]
    if any(count > 0 for count in pii):
        return STAGE_PII, doc_id, pii, None, None, None
    reasons = document_quality_reasons(text, stripped, quality_policy, v4_policy)
    if reasons:
        return STAGE_QUALITY, doc_id, pii, list(reasons), None, None
    simhash = document_simhash_signature(text) if near_dedup else None
    return STAGE_PASS, doc_id, pii, [], document_fingerprint_key(text), simhash


# --------------------------------------------------------------------------
# Kimlik
# --------------------------------------------------------------------------


def signal_code_sha256() -> str:
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in SIGNAL_SOURCE_FILES:
        data = (package / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode("ascii") + b"\0" + str(len(data)).encode("ascii") + b"\0")
        digest.update(data)
    return digest.hexdigest()


def signal_policy_identity(*, quality_policy: str, near_dedup: bool, max_line_bytes: int) -> dict[str, Any]:
    """Tablonun parcadan bagimsiz kimligi. ``quality_policy`` ETKIN politikadir
    (dil durustlugu uygulandiktan sonra); tr-web-v4'te yargic kimligi MT hedefini tasir."""
    return {
        "schema": SIGNALS_SCHEMA_VERSION,
        "line_format": CANDIDATE_LINE_FORMAT,
        "max_line_bytes": int(max_line_bytes),
        "quality_policy": quality_policy,
        "quality_judge": tr_web_v4_judge_id() if quality_policy == QUALITY_POLICY_TR_WEB_V4 else None,
        "near_dedup": bool(near_dedup),
        "pii_keys": list(PII_KEYS),
        "code_sha256": signal_code_sha256(),
        "interpreter": platform.python_version(),
        "zlib": zlib.ZLIB_RUNTIME_VERSION,
    }


def _identity_bytes(identity: Mapping[str, Any]) -> bytes:
    return json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


# --------------------------------------------------------------------------
# Tablo yazma / okuma
# --------------------------------------------------------------------------


def write_signal_table(path: Path, identity: Mapping[str, Any], rows: list[tuple]) -> None:
    """Belirlenimci Parquet (sabit pyarrow + ayarlar); gecici dosya, basarida yerine gecer."""
    _require_pinned_writer()
    columns = list(zip(*rows)) if rows else [()] * len(SIGNALS_SCHEMA)
    schema = SIGNALS_SCHEMA.with_metadata({
        SCHEMA_METADATA_KEY: SIGNALS_SCHEMA_VERSION.encode("ascii"),
        IDENTITY_METADATA_KEY: _identity_bytes(identity),
    })
    table = pa.Table.from_arrays(
        [pa.array(list(values), type=field.type) for values, field in zip(columns, SIGNALS_SCHEMA)],
        schema=schema,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temp_path = Path(temp_name)
    try:
        pq.write_table(
            table,
            str(temp_path),
            row_group_size=max(len(rows), 1),
            version=SHARD_FORMAT_VERSION,
            compression=SHARD_COMPRESSION,
            compression_level=SHARD_COMPRESSION_LEVEL,
            write_page_checksum=True,
            store_schema=True,
            use_dictionary=["quality_reasons.list.element"],
            write_statistics=["source_ordinal", "stage"],
        )
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def signal_table_identity(path: Path) -> dict[str, Any] | None:
    """Tablonun kimligi; dosya yok/okunamaz/baska sema ise None."""
    try:
        metadata = pq.read_schema(str(path)).metadata or {}
    except (OSError, pa.ArrowException):
        return None
    if metadata.get(SCHEMA_METADATA_KEY) != SIGNALS_SCHEMA_VERSION.encode("ascii"):
        return None
    raw = metadata.get(IDENTITY_METADATA_KEY)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


@dataclass
class _Chunk:
    name: str
    path: Path
    identity: dict[str, Any]
    task: dict[str, Any]
    status: str = "pending"  # reused | computed
    rejected: bool = False
    sha256: str | None = None
    byte_size: int = 0


class _LoadedChunk:
    __slots__ = ("ordinals", "stages", "doc_ids", "pii", "reasons", "fingerprints", "simhashes", "rows")

    def __init__(self, table: pa.Table) -> None:
        self.ordinals = table.column("source_ordinal").to_pylist()
        self.stages = table.column("stage").to_pylist()
        self.doc_ids = table.column("doc_id").to_pylist()
        self.pii = table.column("pii").to_pylist()
        self.reasons = table.column("quality_reasons").to_pylist()
        self.fingerprints = table.column("fingerprint").to_pylist()
        self.simhashes = table.column("simhash").to_pylist()
        self.rows = len(self.ordinals)


def _load_table(path: Path, identity: Mapping[str, Any]) -> tuple[_LoadedChunk, str, int]:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    parquet = pq.ParquetFile(pa.BufferReader(data), page_checksum_verification=True)
    metadata = parquet.schema_arrow.metadata or {}
    if metadata.get(IDENTITY_METADATA_KEY) != _identity_bytes(identity):
        raise SignalTableError(f"signal table {path.name}: identity changed while running")
    table = parquet.read()
    if not table.schema.remove_metadata().equals(SIGNALS_SCHEMA.remove_metadata()):
        raise SignalTableError(f"signal table {path.name}: unexpected schema")
    loaded = _LoadedChunk(table)
    if loaded.rows != identity["rows"]:
        raise SignalTableError(f"signal table {path.name}: {loaded.rows} rows, expected {identity['rows']}")
    return loaded, digest, len(data)


# --------------------------------------------------------------------------
# Isci (spawn): modul duzeyinde
# --------------------------------------------------------------------------


def compute_signal_chunk(task: Mapping[str, Any]) -> dict[str, Any]:
    """Bir parcanin bir satir grubu -> sinyal tablosu. Aday satiri ve sinir asimi
    ``import_manifest.manifest_candidate_lines`` ile ayni kuraldir; dongu bunu
    her belgede doc_id ve asamayla dogrular."""
    identity = task["identity"]
    max_line_bytes = int(identity["max_line_bytes"])
    quality_policy = str(identity["quality_policy"])
    v4_policy = quality_policy == QUALITY_POLICY_TR_WEB_V4
    near_dedup = bool(identity["near_dedup"])
    parquet = pq.ParquetFile(task["shard_path"])
    try:
        documents = parquet.read_row_group(int(identity["row_group"]), columns=list(_SIGNAL_COLUMNS)).to_pylist()
    finally:
        parquet.close()
    rows: list[tuple] = []
    for document in documents:
        ordinal = int(document["source_ordinal"])
        line = candidate_line(document)
        if len(line.encode("utf-8")) + 1 > max_line_bytes:
            rows.append((ordinal, STAGE_OVERSIZED, None, None, None, None, None))
            continue
        rows.append((ordinal, *line_signals(
            line, quality_policy=quality_policy, v4_policy=v4_policy, near_dedup=near_dedup,
        )))
    if len(rows) != identity["rows"]:
        raise SignalTableError(f"row group has {len(rows)} rows, shard metadata says {identity['rows']}")
    write_signal_table(Path(task["out_path"]), identity, rows)
    return {"name": task["name"], "rows": len(rows)}


# --------------------------------------------------------------------------
# Dongunun tarafi
# --------------------------------------------------------------------------


class DocumentSignal(NamedTuple):
    stage: int
    pii_counts: dict[str, int] | None
    quality_reasons: tuple[str, ...] | None
    fingerprint: bytes | None
    simhash: int | None


class SignalPrecompute:
    """Sinyal tablolarini planlar, yeniden kullanir ya da (havuzda) hesaplar ve
    karar dongusune sira no sirasinda verir.

    ``workers`` 1 ise tablolar ayni surecte, ihtiyac aninda hesaplanir; >1 ise
    spawn havuzu tum eksik tablolari sirayla isler, dongu siradakini bekler
    (on hesap ile sirali gecis ust uste biner). ``signals_dir`` None ise tablolar
    cikti dizininin yaninda gecici bir dizine yazilir ve sonda silinir.
    """

    def __init__(
        self,
        manifest: Mapping[str, Any],
        store_root: Path,
        *,
        workers: int,
        signals_dir: Path | None,
        temp_parent: Path,
        quality_policy: str,
        near_dedup: bool,
        max_line_bytes: int,
        limit_documents: int | None,
    ) -> None:
        if workers < 1:
            raise ValueError("workers must be at least 1")
        self.manifest = manifest
        self.store_root = store_root
        self.workers = workers
        self.signals_dir = signals_dir.resolve() if signals_dir is not None else None
        self.temp_parent = temp_parent
        self.limit_documents = limit_documents
        self.policy = signal_policy_identity(
            quality_policy=quality_policy, near_dedup=near_dedup, max_line_bytes=max_line_bytes,
        )
        self.chunks: list[_Chunk] = []
        self._dir: Path | None = None
        self._temp_dir: Path | None = None
        self._executor: ProcessPoolExecutor | None = None
        self._futures: dict[str, Future] = {}
        self._next = 0
        self._current: _LoadedChunk | None = None
        self._pos = 0
        self.documents = 0

    # -- yasam dongusu ------------------------------------------------------

    def __enter__(self) -> "SignalPrecompute":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close(cancel=exc_type is not None)

    def start(self) -> None:
        if self.signals_dir is not None:
            self.signals_dir.mkdir(parents=True, exist_ok=True)
            self._dir = self.signals_dir
        else:
            self.temp_parent.mkdir(parents=True, exist_ok=True)
            self._temp_dir = Path(tempfile.mkdtemp(prefix="signals.", dir=self.temp_parent))
            self._dir = self._temp_dir
        self._plan()
        pending = []
        for chunk in self.chunks:
            existing = signal_table_identity(chunk.path) if chunk.path.exists() else None
            if existing is not None and existing == chunk.identity:
                chunk.status = "reused"
            else:
                chunk.rejected = chunk.path.exists()
                pending.append(chunk)
        if self.workers > 1 and pending:
            self._executor = ProcessPoolExecutor(
                max_workers=min(self.workers, len(pending)),
                mp_context=multiprocessing.get_context("spawn"),
            )
            for chunk in pending:
                self._futures[chunk.name] = self._executor.submit(compute_signal_chunk, chunk.task)

    def close(self, *, cancel: bool = False) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=cancel)
            self._executor = None
        if self._temp_dir is not None:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def _plan(self) -> None:
        assert self._dir is not None
        remaining = self.limit_documents
        for index, (shard, path) in enumerate(manifest_shard_paths(self.manifest, self.store_root)):
            if remaining is not None and remaining <= 0:
                break
            try:
                parquet = pq.ParquetFile(str(path))
            except OSError as error:
                raise ImportManifestError(f"shard {shard['sha256']} is missing from the store") from error
            try:
                metadata = parquet.metadata
                group_rows = [metadata.row_group(group).num_rows for group in range(metadata.num_row_groups)]
            finally:
                parquet.close()
            for group, rows in enumerate(group_rows):
                if remaining is not None and remaining <= 0:
                    break
                name = f"s{index:05d}-g{group:04d}.parquet"
                identity = {
                    **self.policy,
                    "shard_index": index,
                    "shard_sha256": shard["sha256"],
                    "shard_byte_size": shard["byte_size"],
                    "row_group": group,
                    "rows": rows,
                }
                out_path = self._dir / name
                self.chunks.append(_Chunk(
                    name=name, path=out_path, identity=identity,
                    task={"name": name, "shard_path": str(path), "out_path": str(out_path), "identity": identity},
                ))
                if remaining is not None:
                    remaining -= rows

    # -- dongu ------------------------------------------------------------

    def _load_next(self) -> None:
        if self._next >= len(self.chunks):
            raise SignalTableError("document beyond the planned signal tables")
        chunk = self.chunks[self._next]
        self._next += 1
        if chunk.status != "reused":
            future = self._futures.pop(chunk.name, None)
            if future is not None:
                future.result()
            else:
                compute_signal_chunk(chunk.task)
            chunk.status = "computed"
        self._current, chunk.sha256, chunk.byte_size = _load_table(chunk.path, chunk.identity)
        self._pos = 0

    def take(self, ordinal: int, raw_line: str | None, oversized: bool) -> DocumentSignal:
        while self._current is None or self._pos >= self._current.rows:
            self._load_next()
        current = self._current
        index = self._pos
        self._pos += 1
        self.documents += 1
        if current.ordinals[index] != ordinal:
            raise SignalTableError(f"signal table ordinal {current.ordinals[index]} != document ordinal {ordinal}")
        stage = current.stages[index]
        if stage not in STAGES:
            raise SignalTableError(f"ordinal {ordinal}: unknown stage {stage}")
        if oversized or stage == STAGE_OVERSIZED:
            if not (oversized and stage == STAGE_OVERSIZED):
                raise SignalTableError(f"ordinal {ordinal}: oversized flag differs from the signal table")
            return DocumentSignal(stage, None, None, None, None)
        assert raw_line is not None
        if hashlib.sha256(raw_line.encode("utf-8")).digest() != current.doc_ids[index]:
            raise SignalTableError(f"ordinal {ordinal}: doc_id differs from the signal table")
        if (stage == STAGE_BLANK) != (not raw_line.strip()):
            raise SignalTableError(f"ordinal {ordinal}: blank flag differs from the signal table")
        if stage == STAGE_BLANK:
            return DocumentSignal(stage, None, None, None, None)
        pii = current.pii[index]
        if pii is None or len(pii) != len(PII_KEYS) or (stage == STAGE_PII) != any(pii):
            raise SignalTableError(f"ordinal {ordinal}: PII counts do not match the stage")
        reasons = current.reasons[index]
        if stage == STAGE_PII:
            if reasons is not None:
                raise SignalTableError(f"ordinal {ordinal}: quality evaluated after PII")
        elif reasons is None or bool(reasons) != (stage == STAGE_QUALITY):
            raise SignalTableError(f"ordinal {ordinal}: quality reasons do not match the stage")
        return DocumentSignal(
            stage,
            dict(zip(PII_KEYS, pii)),
            None if reasons is None else tuple(reasons),
            current.fingerprints[index],
            current.simhashes[index],
        )

    def finish(self, *, complete: bool) -> dict[str, Any]:
        """Kosu ozeti. ``complete`` (dilim degil): planlanan her tablo tamamen tuketilmis olmali."""
        if complete:
            exhausted = self._current is None or self._pos >= self._current.rows
            if self._next != len(self.chunks) or not exhausted:
                raise SignalTableError("signal tables hold documents the shards did not yield")
        used = self.chunks[: self._next]
        listing = "".join(f"{chunk.name}\t{chunk.sha256}\n" for chunk in used)
        return {
            "schema": SIGNALS_SCHEMA_VERSION,
            "workers": self.workers,
            "signals_dir": str(self.signals_dir) if self.signals_dir is not None else None,
            "tables": len(used),
            "tables_reused": sum(1 for chunk in used if chunk.status == "reused"),
            "tables_computed": sum(1 for chunk in used if chunk.status == "computed"),
            "tables_rejected": sum(1 for chunk in used if chunk.rejected),
            "documents": self.documents,
            "tables_sha256": hashlib.sha256(listing.encode("ascii")).hexdigest(),
            "tables_byte_size": sum(chunk.byte_size for chunk in used),
            "policy": dict(self.policy),
        }


__all__ = [
    "DocumentSignal",
    "SIGNALS_SCHEMA_VERSION",
    "SignalPrecompute",
    "SignalTableError",
    "compute_signal_chunk",
    "document_fingerprint_key",
    "document_pii_counts",
    "document_quality_reasons",
    "document_simhash_signature",
    "line_signals",
    "line_url",
    "signal_code_sha256",
    "signal_policy_identity",
    "signal_table_identity",
    "write_signal_table",
]
