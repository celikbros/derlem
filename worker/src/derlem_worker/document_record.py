"""Ortak belge kaydi (derlem.document.v1), karar kaydi (derlem.decision.v1),
secim listesi (derlem.selection.v1) ve Parquet parca yazici/okuyucu (TASK-044).

Ilkeler (docs/veri_mimarisi_2026_10.md 2.2-2.4, docs/belge_kaydi_v1.md):

- Bir belge bir Parquet satiridir; ``text`` hicbir zaman yeniden yazilmaz
  (paragraf sonlari dahil). ``doc_id`` = metnin UTF-8 baytlarinin SHA256'si.
- Kararlar metinden ayridir; her hukum bir satir.
- Parca belirlenimcidir: ayni kayitlar ayni sirayla -> ayni bayt -> ayni SHA.
  Parquet footer'inda zaman damgasi yoktur; tek oynak alan yazicinin surumunu
  tasiyan ``created_by``'dir ("parquet-cpp-arrow version X"). Bu yuzden pyarrow
  surumu pyproject'te tam surumle sabitlenir ve yazici baska surumle yazmayi
  reddeder (SHARD_WRITER_PYARROW_VERSION).
- Parcalar nesne deposuna siradan nesne olarak girer (storage.py, ikili yol).

Bu modul talimat verisi semasini (canonical.py) degistirmez; onun yanindadir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Iterator, Mapping, Sequence

import pyarrow as pa
import pyarrow.parquet as pq


DOCUMENT_SCHEMA_VERSION = "derlem.document.v1"
DECISION_SCHEMA_VERSION = "derlem.decision.v1"
SELECTION_SCHEMA_VERSION = "derlem.selection.v1"
SCHEMA_METADATA_KEY = b"derlem.schema"

# Yazici ayarlari parca kimliginin parcasidir: biri degisirse ayni girdinin SHA'si
# degisir. Degistirmek bilincli bir surum karari ister (docs/belge_kaydi_v1.md).
SHARD_WRITER_PYARROW_VERSION = "25.0.1"
SHARD_CREATED_BY = f"parquet-cpp-arrow version {SHARD_WRITER_PYARROW_VERSION}"
SHARD_COMPRESSION = "zstd"
SHARD_COMPRESSION_LEVEL = 9
SHARD_FORMAT_VERSION = "2.6"
DEFAULT_ROWS_PER_SHARD = 100_000
DEFAULT_ROW_GROUP_SIZE = 10_000

PROVENANCE_FIELDS = ("dataset", "revision", "file", "row", "external_id", "url", "crawl_date", "dump")
LANGUAGE_FIELDS = ("declared", "detected", "score")
RIGHTS_FIELDS = ("license_id", "evidence_ref", "scope")

DECISION_TYPES = frozenset({
    "pii",
    "duplicate",
    "near_duplicate",
    "quality_rule",
    "language",
    "rights_scope",
    "held_out",
    "jury",
    "human_review",
    # Bugunku metin-kopya hattinin iki mekanik karari: satir siniri asimi ve
    # bos satir. Ikisi de "sessizce atilmaz" kuralinin karar kaydindaki karsiligi.
    "oversized",
    "empty_text",
})
# pass: kapidan gecti; reject: egitim secimine girmez; held_out: degerlendirme
# bolmesine ayrildi; flag: hukum degil isaret (ornegin juri "supheli").
VERDICTS = frozenset({"pass", "reject", "held_out", "flag"})
SELECTION_PARTITIONS = ("train", "held_out")

DOCUMENT_SCHEMA = pa.schema(
    [
        pa.field("doc_id", pa.string(), nullable=False),
        pa.field("text", pa.large_string(), nullable=False),
        pa.field("source_id", pa.string()),
        pa.field("source_ordinal", pa.int64(), nullable=False),
        pa.field(
            "provenance",
            pa.struct([
                pa.field("dataset", pa.string()),
                pa.field("revision", pa.string()),
                pa.field("file", pa.string()),
                pa.field("row", pa.int64()),
                pa.field("external_id", pa.string()),
                pa.field("url", pa.string()),
                pa.field("crawl_date", pa.string()),
                pa.field("dump", pa.string()),
            ]),
            nullable=False,
        ),
        pa.field(
            "language",
            pa.struct([
                pa.field("declared", pa.string()),
                pa.field("detected", pa.string()),
                pa.field("score", pa.float64()),
            ]),
            nullable=False,
        ),
        pa.field("signals", pa.map_(pa.string(), pa.float64()), nullable=False),
        pa.field(
            "rights",
            pa.struct([
                pa.field("license_id", pa.string()),
                pa.field("evidence_ref", pa.string()),
                pa.field("scope", pa.string()),
            ]),
            nullable=False,
        ),
        pa.field("extra", pa.string()),
    ],
    metadata={SCHEMA_METADATA_KEY: DOCUMENT_SCHEMA_VERSION.encode("ascii")},
)

DECISION_SCHEMA = pa.schema(
    [
        pa.field("doc_id", pa.string(), nullable=False),
        # Ayni metin bir kaynakta birden cok kez gecebilir (birebir kopya); bu
        # durumda hukum belgeye degil o gecise aittir. Belge duzeyi hukumde null.
        pa.field("source_ordinal", pa.int64()),
        pa.field("decision_type", pa.string(), nullable=False),
        pa.field("verdict", pa.string(), nullable=False),
        pa.field("reason", pa.string()),
        pa.field("judge", pa.string(), nullable=False),
        pa.field("run_id", pa.string(), nullable=False),
        pa.field("decided_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ],
    metadata={SCHEMA_METADATA_KEY: DECISION_SCHEMA_VERSION.encode("ascii")},
)

SELECTION_SCHEMA = pa.schema(
    [
        pa.field("source_ordinal", pa.int64(), nullable=False),
        pa.field("doc_id", pa.string(), nullable=False),
        pa.field("partition", pa.string(), nullable=False),
    ],
    metadata={SCHEMA_METADATA_KEY: SELECTION_SCHEMA_VERSION.encode("ascii")},
)

# Dusuk kardinaliteli sutunlar sozluk kodlanir; metin ve kimlikler kodlanmaz
# (sozluk tasar, geri dusme sayfasi bosa yazilir).
_DOCUMENT_DICTIONARY_COLUMNS = [
    "source_id",
    "provenance.dataset",
    "provenance.revision",
    "provenance.file",
    "provenance.dump",
    "language.declared",
    "language.detected",
    "signals.key_value.key",
    "rights.license_id",
    "rights.evidence_ref",
    "rights.scope",
]
_DOCUMENT_STATISTICS_COLUMNS = [
    "source_ordinal",
    "provenance.row",
    "provenance.crawl_date",
    "provenance.dump",
    "language.declared",
    "language.detected",
    "language.score",
    "signals.key_value.key",
    "signals.key_value.value",
]


class DocumentRecordError(ValueError):
    pass


def document_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_document(
    *,
    text: str,
    source_ordinal: int,
    source_id: str | None = None,
    provenance: Mapping[str, Any] | None = None,
    language: Mapping[str, Any] | None = None,
    signals: Mapping[str, float] | None = None,
    rights: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | str | None = None,
) -> dict[str, Any]:
    """Eksik alt alanlari None ile doldurulmus, dogrulanmis bir belge kaydi."""
    if isinstance(extra, Mapping):
        extra_value = encode_extra(extra)
    else:
        extra_value = extra
    record = {
        "doc_id": document_id(text) if isinstance(text, str) else None,
        "text": text,
        "source_id": source_id,
        "source_ordinal": source_ordinal,
        "provenance": {key: (provenance or {}).get(key) for key in PROVENANCE_FIELDS},
        "language": {key: (language or {}).get(key) for key in LANGUAGE_FIELDS},
        "signals": dict(signals or {}),
        "rights": {key: (rights or {}).get(key) for key in RIGHTS_FIELDS},
        "extra": extra_value,
    }
    validate_document(record)
    return record


def encode_extra(values: Mapping[str, Any]) -> str | None:
    """Eslenmeyen sutunlar: sirali anahtarli, kompakt JSON; bossa None."""
    if not values:
        return None
    return json.dumps(dict(values), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported extra value type: {type(value).__name__}")


def _check_struct(record: Mapping[str, Any], name: str, fields: Sequence[str]) -> None:
    value = record.get(name)
    if not isinstance(value, Mapping):
        raise DocumentRecordError(f"{name} must be an object")
    unknown = set(value) - set(fields)
    if unknown:
        raise DocumentRecordError(f"{name} has unknown fields: {sorted(unknown)}")


def validate_document(record: Mapping[str, Any]) -> None:
    unknown = set(record) - set(DOCUMENT_SCHEMA.names)
    if unknown:
        raise DocumentRecordError(f"unknown document fields: {sorted(unknown)}")
    text = record.get("text")
    if not isinstance(text, str):
        raise DocumentRecordError("text must be a string")
    if not text.strip():
        raise DocumentRecordError("text is empty; empty records are counted by the adapter, not stored")
    if record.get("doc_id") != document_id(text):
        raise DocumentRecordError("doc_id must be the sha256 of the text's UTF-8 bytes")
    ordinal = record.get("source_ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
        raise DocumentRecordError("source_ordinal must be a positive integer")
    source_id = record.get("source_id")
    if source_id is not None and not isinstance(source_id, str):
        raise DocumentRecordError("source_id must be a string or null")
    _check_struct(record, "provenance", PROVENANCE_FIELDS)
    _check_struct(record, "language", LANGUAGE_FIELDS)
    _check_struct(record, "rights", RIGHTS_FIELDS)
    row = record["provenance"].get("row")
    if row is not None and (not isinstance(row, int) or isinstance(row, bool) or row < 0):
        raise DocumentRecordError("provenance.row must be a non-negative integer or null")
    score = record["language"].get("score")
    if score is not None and (not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score)):
        raise DocumentRecordError("language.score must be a finite number or null")
    signals = record.get("signals")
    if not isinstance(signals, Mapping):
        raise DocumentRecordError("signals must be an object")
    for key, value in signals.items():
        if not isinstance(key, str) or not key:
            raise DocumentRecordError("signal names must be non-empty strings")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise DocumentRecordError(f"signal {key!r} must be a finite number")
    extra = record.get("extra")
    if extra is not None:
        if not isinstance(extra, str):
            raise DocumentRecordError("extra must be a JSON string or null")
        try:
            parsed = json.loads(extra)
        except json.JSONDecodeError as error:
            raise DocumentRecordError("extra must be valid JSON") from error
        if not isinstance(parsed, dict):
            raise DocumentRecordError("extra must encode a JSON object")


def make_decision(
    *,
    doc_id: str,
    decision_type: str,
    verdict: str,
    judge: str,
    run_id: str,
    decided_at: datetime,
    reason: str | None = None,
    source_ordinal: int | None = None,
) -> dict[str, Any]:
    record = {
        "doc_id": doc_id,
        "source_ordinal": source_ordinal,
        "decision_type": decision_type,
        "verdict": verdict,
        "reason": reason,
        "judge": judge,
        "run_id": run_id,
        "decided_at": decided_at,
    }
    validate_decision(record)
    return record


def validate_decision(record: Mapping[str, Any]) -> None:
    doc_id = record.get("doc_id")
    if not isinstance(doc_id, str) or len(doc_id) != 64 or any(ch not in "0123456789abcdef" for ch in doc_id):
        raise DocumentRecordError("doc_id must be 64 lowercase hex characters")
    if record.get("decision_type") not in DECISION_TYPES:
        raise DocumentRecordError(f"unknown decision_type: {record.get('decision_type')!r}")
    if record.get("verdict") not in VERDICTS:
        raise DocumentRecordError(f"unknown verdict: {record.get('verdict')!r}")
    for key in ("judge", "run_id"):
        if not isinstance(record.get(key), str) or not record[key]:
            raise DocumentRecordError(f"{key} must be a non-empty string")
    decided_at = record.get("decided_at")
    if not isinstance(decided_at, datetime) or decided_at.tzinfo is None:
        raise DocumentRecordError("decided_at must be a timezone-aware datetime")


# --------------------------------------------------------------------------
# Parquet yazimi
# --------------------------------------------------------------------------


def _require_pinned_writer() -> None:
    if pa.__version__ != SHARD_WRITER_PYARROW_VERSION:
        raise RuntimeError(
            f"Shard writer requires pyarrow {SHARD_WRITER_PYARROW_VERSION} (installed: {pa.__version__}); "
            "the writer version is part of the shard bytes. Change the pin and SHARD_WRITER_PYARROW_VERSION together."
        )


def _writer_options(schema: pa.Schema) -> dict[str, Any]:
    options: dict[str, Any] = {
        "version": SHARD_FORMAT_VERSION,
        "compression": SHARD_COMPRESSION,
        "compression_level": SHARD_COMPRESSION_LEVEL,
        "write_page_checksum": True,
        "store_schema": True,
    }
    if schema.equals(DOCUMENT_SCHEMA, check_metadata=True):
        options["use_dictionary"] = _DOCUMENT_DICTIONARY_COLUMNS
        options["write_statistics"] = _DOCUMENT_STATISTICS_COLUMNS
    elif schema.equals(DECISION_SCHEMA, check_metadata=True):
        options["use_dictionary"] = ["decision_type", "verdict", "reason", "judge", "run_id"]
        options["write_statistics"] = ["source_ordinal", "decision_type", "verdict", "decided_at"]
    elif schema.equals(SELECTION_SCHEMA, check_metadata=True):
        options["use_dictionary"] = ["partition"]
        options["write_statistics"] = ["source_ordinal", "partition"]
    else:
        raise ValueError("unknown Derlem parquet schema")
    return options


def _signals_items(signals: Mapping[str, float]) -> list[tuple[str, float]]:
    # Harita sirasi parca baytlarina girer: anahtara gore sirali.
    return [(key, float(signals[key])) for key in sorted(signals)]


def _table_from_rows(schema: pa.Schema, rows: list[Mapping[str, Any]]) -> pa.Table:
    arrays = []
    for field in schema:
        values = [row.get(field.name) for row in rows]
        if field.name == "signals":
            values = [_signals_items(value or {}) for value in values]
        arrays.append(pa.array(values, type=field.type))
    return pa.Table.from_arrays(arrays, schema=schema)


@dataclass(frozen=True)
class ParquetFileInfo:
    path: str
    sha256: str
    byte_size: int
    row_count: int
    row_groups: int
    first_source_ordinal: int | None
    last_source_ordinal: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "row_count": self.row_count,
            "row_groups": self.row_groups,
            "first_source_ordinal": self.first_source_ordinal,
            "last_source_ordinal": self.last_source_ordinal,
        }


def file_sha256(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(4 * 1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


class ParquetRowWriter:
    """Tek Parquet dosyasi; satirlar sabit boyutlu satir gruplari halinde yazilir.

    Hedefin yanindaki gecici dosyaya yazar, close() basarida yerine koyar ve
    SHA256'yi doner; hata/abort'ta gecici dosya silinir.
    """

    def __init__(
        self,
        path: Path,
        schema: pa.Schema,
        *,
        row_group_size: int = DEFAULT_ROW_GROUP_SIZE,
        validator=None,
    ) -> None:
        _require_pinned_writer()
        if row_group_size <= 0:
            raise ValueError("row_group_size must be positive")
        self.path = path.resolve()
        self.schema = schema
        self.row_group_size = row_group_size
        self.validator = validator
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f"{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        os.close(descriptor)
        self.temp_path = Path(temp_name)
        self._writer: pq.ParquetWriter | None = pq.ParquetWriter(
            str(self.temp_path), schema, **_writer_options(schema)
        )
        self._buffer: list[Mapping[str, Any]] = []
        self.row_count = 0
        self.row_groups = 0
        self.first_ordinal: int | None = None
        self.last_ordinal: int | None = None
        self._has_ordinal = "source_ordinal" in schema.names

    def add(self, row: Mapping[str, Any]) -> None:
        if self._writer is None:
            raise RuntimeError("writer is closed")
        if self.validator is not None:
            self.validator(row)
        if self._has_ordinal:
            ordinal = row.get("source_ordinal")
            if ordinal is not None:
                if self.first_ordinal is None:
                    self.first_ordinal = ordinal
                self.last_ordinal = ordinal
        self._buffer.append(row)
        self.row_count += 1
        if len(self._buffer) >= self.row_group_size:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        assert self._writer is not None
        table = _table_from_rows(self.schema, self._buffer)
        self._writer.write_table(table, row_group_size=len(self._buffer))
        self.row_groups += 1
        self._buffer = []

    def close(self) -> ParquetFileInfo:
        if self._writer is None:
            raise RuntimeError("writer is closed")
        try:
            self._flush()
            self._writer.close()
            self._writer = None
            with self.temp_path.open("rb+") as handle:
                os.fsync(handle.fileno())
            self.temp_path.replace(self.path)
        except BaseException:
            self.abort()
            raise
        digest, size = file_sha256(self.path)
        return ParquetFileInfo(
            path=str(self.path),
            sha256=digest,
            byte_size=size,
            row_count=self.row_count,
            row_groups=self.row_groups,
            first_source_ordinal=self.first_ordinal,
            last_source_ordinal=self.last_ordinal,
        )

    def abort(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:  # noqa: BLE001 - abort yolu, asil hata yukarida
                pass
            self._writer = None
        self.temp_path.unlink(missing_ok=True)


class DocumentShardWriter:
    """Belge kayitlarini ~rows_per_shard belgelik parcalara yazar.

    ``cut()`` o anki parcayi kapatir (ornegin TASK-032'de kaynak dosya siniri:
    bir kaynak dosya = bir parca). Parca adlari sirali: ``<prefix>-00000.parquet``.
    """

    def __init__(
        self,
        out_dir: Path,
        *,
        rows_per_shard: int = DEFAULT_ROWS_PER_SHARD,
        row_group_size: int = DEFAULT_ROW_GROUP_SIZE,
        prefix: str = "part",
    ) -> None:
        if rows_per_shard <= 0:
            raise ValueError("rows_per_shard must be positive")
        self.out_dir = out_dir
        self.rows_per_shard = rows_per_shard
        self.row_group_size = min(row_group_size, rows_per_shard)
        self.prefix = prefix
        self._current: ParquetRowWriter | None = None
        self._last_ordinal = 0
        self.shards: list[ParquetFileInfo] = []

    def __enter__(self) -> "DocumentShardWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()
        elif self._current is not None:
            self.cut()

    def add(self, record: Mapping[str, Any]) -> None:
        validate_document(record)
        ordinal = int(record["source_ordinal"])
        if ordinal <= self._last_ordinal:
            raise DocumentRecordError("source_ordinal must increase strictly within a shard sequence")
        self._last_ordinal = ordinal
        if self._current is None:
            path = self.out_dir / f"{self.prefix}-{len(self.shards):05d}.parquet"
            self._current = ParquetRowWriter(path, DOCUMENT_SCHEMA, row_group_size=self.row_group_size)
        self._current.add(record)
        if self._current.row_count >= self.rows_per_shard:
            self.cut()

    def cut(self) -> None:
        if self._current is None:
            return
        writer, self._current = self._current, None
        self.shards.append(writer.close())

    def close(self) -> list[ParquetFileInfo]:
        self.cut()
        return list(self.shards)

    def abort(self) -> None:
        if self._current is not None:
            self._current.abort()
            self._current = None


def write_document_shards(
    records: Iterable[Mapping[str, Any]],
    out_dir: Path,
    *,
    rows_per_shard: int = DEFAULT_ROWS_PER_SHARD,
    row_group_size: int = DEFAULT_ROW_GROUP_SIZE,
    prefix: str = "part",
) -> list[ParquetFileInfo]:
    with DocumentShardWriter(
        out_dir, rows_per_shard=rows_per_shard, row_group_size=row_group_size, prefix=prefix
    ) as writer:
        for record in records:
            writer.add(record)
    return writer.close()


def publish_parquet(store, info: ParquetFileInfo):
    """Parcayi nesne deposuna siradan (ikili) nesne olarak koyar; SHA dogrulanir."""
    stored = store.ingest_raw_file(Path(info.path))
    if stored.sha256 != info.sha256 or stored.byte_size != info.byte_size:
        raise RuntimeError("Published shard does not match the written shard")
    return stored


# --------------------------------------------------------------------------
# Okuma
# --------------------------------------------------------------------------


def parquet_schema_version(path: Path) -> str | None:
    metadata = pq.read_schema(str(path)).metadata or {}
    value = metadata.get(SCHEMA_METADATA_KEY)
    return value.decode("ascii") if value is not None else None


def _row_to_python(row: dict[str, Any]) -> dict[str, Any]:
    signals = row.get("signals")
    if isinstance(signals, list):
        row["signals"] = dict(signals)
    return row


def iter_parquet_rows(
    path: Path,
    *,
    columns: Sequence[str] | None = None,
    batch_size: int = DEFAULT_ROW_GROUP_SIZE,
    expected_schema: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Satirlari sozluk olarak akitir; ``columns`` verilirse yalniz o sutunlar okunur."""
    parquet = pq.ParquetFile(str(path))
    if expected_schema is not None:
        metadata = parquet.schema_arrow.metadata or {}
        actual = metadata.get(SCHEMA_METADATA_KEY, b"").decode("ascii")
        if actual != expected_schema:
            raise DocumentRecordError(f"expected {expected_schema} parquet, found {actual or 'unknown'}")
    if columns is not None:
        missing = [column for column in columns if column not in parquet.schema_arrow.names]
        if missing:
            raise DocumentRecordError(f"unknown columns requested: {missing}")
    try:
        for batch in parquet.iter_batches(batch_size=batch_size, columns=list(columns) if columns else None):
            for row in batch.to_pylist():
                yield _row_to_python(row)
    finally:
        parquet.close()


def read_documents(
    path: Path,
    *,
    columns: Sequence[str] | None = None,
    batch_size: int = DEFAULT_ROW_GROUP_SIZE,
) -> Iterator[dict[str, Any]]:
    return iter_parquet_rows(path, columns=columns, batch_size=batch_size, expected_schema=DOCUMENT_SCHEMA_VERSION)


def read_decisions(path: Path, *, columns: Sequence[str] | None = None) -> Iterator[dict[str, Any]]:
    return iter_parquet_rows(path, columns=columns, expected_schema=DECISION_SCHEMA_VERSION)


def read_selection(path: Path, *, columns: Sequence[str] | None = None) -> Iterator[dict[str, Any]]:
    return iter_parquet_rows(path, columns=columns, expected_schema=SELECTION_SCHEMA_VERSION)


def parquet_created_by(path: Path) -> str:
    parquet = pq.ParquetFile(str(path))
    try:
        return str(parquet.metadata.created_by)
    finally:
        parquet.close()
