"""Kaynak uyarlayicilari (TASK-044): "onlarin sutunu -> bizim alanimiz", kod degil veri.

Bir uyarlayici ``adapters/<ad>.yaml`` dosyasidir. Sozlesme (docs/belge_kaydi_v1.md):

    dataset, revision, config, split   kaynak kimligi (revision sabit surum)
    format                              parquet | jsonl | tsv
    target                              derlem.document.v1 (varsayilan) | derlem.canonical-sample.v1
    columns_read                        okunacak sutunlar = map'te eslenenler + extra
    columns_skipped                     bilerek okunmayanlar (ornegin embeddings)
    map                                 hedef alan -> sutun
    extra                               eslenmeyip extra JSON'a giden sutunlar
    constants                           kaynak duzeyi sabitler (ornegin language.declared)
    document_boundary                   record (bir kayit = bir belge, asla bolunmez)

Dogrulama kurallari:
- Eslenen (columns_read'deki) bir sutun kaynakta yoksa alim BASLAMAZ (AdapterError).
- ``text`` bos/yalniz bosluk kayit belge olmaz; sayilir ve sira numarasiyla raporlanir.
- Uyarlayicida adi gecmeyen sutun atilmaz: ``extra``'ya gider ve raporda listelenir.
  Bir sutunu okumamak icin columns_skipped'e acikca yazmak gerekir.

TASK-032 (alim isi) bu modulu soyle kullanir: ``load_adapter`` -> parquet altbilgisinden
sutun adlari -> ``adapter.plan_columns(names)`` (eksikse ret; okunacak sutun listesi) ->
satir grubu satirlari -> ``adapt_rows`` -> ``DocumentShardWriter`` (bir dosya = bir parca, ``cut``).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Iterator, Mapping

import yaml

from derlem_worker.canonical import (
    CANONICAL_SCHEMA_VERSION,
    CONTENT_PURPOSES,
    TOP_LEVEL_FIELDS,
    CanonicalSampleError,
    parse_canonical_sample,
)
from derlem_worker.document_record import (
    DOCUMENT_SCHEMA_VERSION,
    DocumentRecordError,
    LANGUAGE_FIELDS,
    PROVENANCE_FIELDS,
    RIGHTS_FIELDS,
    document_id,
    encode_extra,
    validate_document,
)
from derlem_worker.sampling import _bounded_lines


ADAPTER_FORMATS = frozenset({"parquet", "jsonl", "tsv"})
ADAPTER_TARGETS = frozenset({DOCUMENT_SCHEMA_VERSION, CANONICAL_SCHEMA_VERSION})
DOCUMENT_BOUNDARIES = frozenset({"record"})
ADAPTER_KEYS = frozenset({
    "dataset",
    "revision",
    "config",
    "split",
    "format",
    "target",
    "content_purpose",
    "columns_read",
    "columns_skipped",
    "map",
    "extra",
    "constants",
    "document_boundary",
    "notes",
})
# Alimin kendisinin doldurdugu alanlar: uyarlayici eslemez.
AUTOMATIC_TARGETS = frozenset({"provenance.dataset", "provenance.revision", "provenance.file", "provenance.row"})
STRING_TARGETS = frozenset(
    {f"provenance.{name}" for name in PROVENANCE_FIELDS if name != "row"}
    | {"language.declared", "language.detected"}
    | {f"rights.{name}" for name in RIGHTS_FIELDS}
)
NUMBER_TARGETS = frozenset({"language.score"})
REPORT_SAMPLE_LIMIT = 100


class AdapterError(ValueError):
    pass


@dataclass(frozen=True)
class SignalMapping:
    name: str
    column: str


@dataclass(frozen=True)
class ColumnPlan:
    read: tuple[str, ...]
    skipped: tuple[str, ...]
    unlisted: tuple[str, ...]


@dataclass(frozen=True)
class Adapter:
    name: str
    sha256: str
    dataset: str
    revision: str
    config: str | None
    split: str | None
    format: str
    target: str
    content_purpose: str | None
    columns_read: tuple[str, ...]
    columns_skipped: tuple[str, ...]
    field_map: tuple[tuple[str, str], ...]
    signals: tuple[SignalMapping, ...]
    extra: tuple[str, ...]
    constants: tuple[tuple[str, Any], ...]
    document_boundary: str

    @property
    def text_column(self) -> str:
        return dict(self.field_map)["text"]

    def mapped_columns(self) -> set[str]:
        return {column for _, column in self.field_map} | {signal.column for signal in self.signals}

    def plan_columns(self, available: Iterable[str]) -> ColumnPlan:
        """Kaynagin sutun adlarina karsi dogrulama; eksik sutun -> AdapterError."""
        names = list(available)
        present = set(names)
        missing = [column for column in self.columns_read if column not in present]
        if missing:
            raise AdapterError(
                f"adapter {self.name}: mapped column(s) missing from source: {missing}; import refused"
            )
        known = set(self.columns_read) | set(self.columns_skipped)
        unlisted = tuple(column for column in names if column not in known)
        read = tuple(column for column in names if column not in set(self.columns_skipped))
        skipped = tuple(column for column in names if column in set(self.columns_skipped))
        return ColumnPlan(read=read, skipped=skipped, unlisted=unlisted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "dataset": self.dataset,
            "revision": self.revision,
            "config": self.config,
            "split": self.split,
            "format": self.format,
            "target": self.target,
            "document_boundary": self.document_boundary,
        }


@dataclass
class AdapterReport:
    adapter: str
    adapter_sha256: str
    target: str
    files: list[str] = field(default_factory=list)
    records_seen: int = 0
    documents: int = 0
    blank_lines: int = 0
    empty_text: int = 0
    empty_text_ordinals: list[int] = field(default_factory=list)
    oversized: int = 0
    oversized_ordinals: list[int] = field(default_factory=list)
    invalid_records: int = 0
    invalid_samples: list[dict[str, Any]] = field(default_factory=list)
    skipped_columns: list[str] = field(default_factory=list)
    unlisted_columns: list[str] = field(default_factory=list)
    missing_signal_values: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.invalid_records == 0

    def note_empty(self, ordinal: int) -> None:
        self.empty_text += 1
        if len(self.empty_text_ordinals) < REPORT_SAMPLE_LIMIT:
            self.empty_text_ordinals.append(ordinal)

    def note_oversized(self, ordinal: int) -> None:
        self.oversized += 1
        if len(self.oversized_ordinals) < REPORT_SAMPLE_LIMIT:
            self.oversized_ordinals.append(ordinal)

    def note_invalid(self, ordinal: int, error: str) -> None:
        self.invalid_records += 1
        if len(self.invalid_samples) < REPORT_SAMPLE_LIMIT:
            self.invalid_samples.append({"source_ordinal": ordinal, "error": error})

    def note_columns(self, plan: ColumnPlan) -> None:
        for column in plan.skipped:
            if column not in self.skipped_columns:
                self.skipped_columns.append(column)
        for column in plan.unlisted:
            if column not in self.unlisted_columns:
                self.unlisted_columns.append(column)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "adapter_sha256": self.adapter_sha256,
            "target": self.target,
            "files": list(self.files),
            "records_seen": self.records_seen,
            "documents": self.documents,
            "blank_lines": self.blank_lines,
            "empty_text": self.empty_text,
            "empty_text_ordinals": list(self.empty_text_ordinals),
            "oversized": self.oversized,
            "oversized_ordinals": list(self.oversized_ordinals),
            "invalid_records": self.invalid_records,
            "invalid_samples": list(self.invalid_samples),
            "skipped_columns": sorted(self.skipped_columns),
            "unlisted_columns": sorted(self.unlisted_columns),
            "missing_signal_values": dict(sorted(self.missing_signal_values.items())),
            "ok": self.ok,
        }


@dataclass(frozen=True)
class CanonicalRecord:
    """Talimat kaydi: satir oldugu gibi (bayt bayt) tasinir; dogrulanmistir."""

    source_ordinal: int
    sample_id: str
    record_type: str
    line: str


# --------------------------------------------------------------------------
# Yukleme ve statik dogrulama
# --------------------------------------------------------------------------


def load_adapter(path: Path) -> Adapter:
    payload = path.read_bytes()
    try:
        value = yaml.safe_load(payload.decode("utf-8"))
    except yaml.YAMLError as error:
        raise AdapterError(f"adapter {path.name}: invalid yaml: {error}") from error
    return parse_adapter(value, name=path.stem, sha256=hashlib.sha256(payload).hexdigest())


def _string_list(value: Any, key: str, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise AdapterError(f"adapter {name}: {key} must be a list of column names")
    if len(set(value)) != len(value):
        raise AdapterError(f"adapter {name}: {key} has duplicate entries")
    return tuple(value)


def _optional_string(value: Mapping[str, Any], key: str, name: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item:
        raise AdapterError(f"adapter {name}: {key} must be a string (quote it in yaml)")
    return item


def parse_adapter(value: Any, *, name: str, sha256: str) -> Adapter:
    if not isinstance(value, dict):
        raise AdapterError(f"adapter {name}: top level must be a mapping")
    unknown = set(value) - ADAPTER_KEYS
    if unknown:
        raise AdapterError(f"adapter {name}: unknown keys {sorted(unknown)}")
    for key in ("dataset", "revision", "format", "document_boundary"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise AdapterError(f"adapter {name}: {key} is required and must be a string")
    adapter_format = value["format"]
    if adapter_format not in ADAPTER_FORMATS:
        raise AdapterError(f"adapter {name}: format must be one of {sorted(ADAPTER_FORMATS)}")
    if value["document_boundary"] not in DOCUMENT_BOUNDARIES:
        raise AdapterError(f"adapter {name}: document_boundary must be 'record' (one record = one document)")
    target = value.get("target", DOCUMENT_SCHEMA_VERSION)
    if target not in ADAPTER_TARGETS:
        raise AdapterError(f"adapter {name}: target must be one of {sorted(ADAPTER_TARGETS)}")
    columns_read = _string_list(value.get("columns_read"), "columns_read", name)
    columns_skipped = _string_list(value.get("columns_skipped"), "columns_skipped", name)
    extra = _string_list(value.get("extra"), "extra", name)
    overlap = set(columns_read) & set(columns_skipped)
    if overlap:
        raise AdapterError(f"adapter {name}: columns both read and skipped: {sorted(overlap)}")
    common = dict(
        name=name,
        sha256=sha256,
        dataset=value["dataset"],
        revision=value["revision"],
        config=_optional_string(value, "config", name),
        split=_optional_string(value, "split", name),
        format=adapter_format,
        target=target,
        columns_read=columns_read,
        columns_skipped=columns_skipped,
        document_boundary=value["document_boundary"],
    )

    if target == CANONICAL_SCHEMA_VERSION:
        if adapter_format != "jsonl":
            raise AdapterError(f"adapter {name}: canonical samples are read from jsonl only")
        if value.get("map") or extra or value.get("constants"):
            raise AdapterError(
                f"adapter {name}: canonical target takes the record as is; map/extra/constants are not allowed"
            )
        purpose = value.get("content_purpose")
        if purpose not in CONTENT_PURPOSES:
            raise AdapterError(f"adapter {name}: content_purpose must be one of {sorted(CONTENT_PURPOSES)}")
        unknown_fields = set(columns_read) - TOP_LEVEL_FIELDS
        if unknown_fields:
            raise AdapterError(f"adapter {name}: not canonical fields: {sorted(unknown_fields)}")
        return Adapter(
            content_purpose=purpose,
            field_map=(),
            signals=(),
            extra=(),
            constants=(),
            **common,
        )

    if value.get("content_purpose") is not None:
        raise AdapterError(f"adapter {name}: content_purpose belongs to the source registration, not a document adapter")
    raw_map = value.get("map")
    if not isinstance(raw_map, dict) or not raw_map:
        raise AdapterError(f"adapter {name}: map is required")
    field_map: list[tuple[str, str]] = []
    signals: list[SignalMapping] = []
    for target_path, source in raw_map.items():
        if not isinstance(target_path, str):
            raise AdapterError(f"adapter {name}: map keys must be strings")
        if target_path in AUTOMATIC_TARGETS:
            raise AdapterError(f"adapter {name}: {target_path} is filled by the importer, not mapped")
        if target_path.startswith("signals."):
            signal_name = target_path[len("signals."):]
            if isinstance(source, dict):
                if set(source) - {"value", "scorer"} or not isinstance(source.get("value"), str):
                    raise AdapterError(f"adapter {name}: {target_path} must be a column or {{value, scorer}}")
                column = source["value"]
                scorer = source.get("scorer")
                if scorer is not None:
                    if not isinstance(scorer, str) or not scorer:
                        raise AdapterError(f"adapter {name}: {target_path}.scorer must be a string")
                    signal_name = scorer
            elif isinstance(source, str):
                column = source
            else:
                raise AdapterError(f"adapter {name}: {target_path} must name a column")
            if not signal_name:
                raise AdapterError(f"adapter {name}: empty signal name")
            if any(signal.name == signal_name for signal in signals):
                raise AdapterError(f"adapter {name}: signal {signal_name!r} mapped twice")
            signals.append(SignalMapping(name=signal_name, column=column))
            continue
        if target_path != "text" and target_path not in STRING_TARGETS and target_path not in NUMBER_TARGETS:
            raise AdapterError(f"adapter {name}: unknown map target {target_path!r}")
        if not isinstance(source, str) or not source:
            raise AdapterError(f"adapter {name}: {target_path} must name a column")
        field_map.append((target_path, source))
    if "text" not in dict(field_map):
        raise AdapterError(f"adapter {name}: text must be mapped")

    raw_constants = value.get("constants") or {}
    if not isinstance(raw_constants, dict):
        raise AdapterError(f"adapter {name}: constants must be a mapping")
    constants: list[tuple[str, Any]] = []
    mapped_targets = {target_path for target_path, _ in field_map}
    for target_path, constant in raw_constants.items():
        if target_path not in STRING_TARGETS and target_path not in NUMBER_TARGETS:
            raise AdapterError(f"adapter {name}: constant target {target_path!r} not allowed")
        if target_path in mapped_targets:
            raise AdapterError(f"adapter {name}: {target_path} is both mapped and constant")
        if target_path in STRING_TARGETS and not isinstance(constant, str):
            raise AdapterError(f"adapter {name}: constant {target_path} must be a string")
        constants.append((target_path, constant))

    used = {column for _, column in field_map} | {signal.column for signal in signals}
    not_read = sorted((used | set(extra)) - set(columns_read))
    if not_read:
        raise AdapterError(f"adapter {name}: mapped/extra columns missing from columns_read: {not_read}")
    both = sorted(used & set(extra))
    if both:
        raise AdapterError(f"adapter {name}: columns both mapped and extra: {both}")
    unused = sorted(set(columns_read) - used - set(extra))
    if unused:
        raise AdapterError(f"adapter {name}: columns read but neither mapped nor extra: {unused}")
    return Adapter(
        content_purpose=None,
        field_map=tuple(field_map),
        signals=tuple(signals),
        extra=extra,
        constants=tuple(constants),
        **common,
    )


# --------------------------------------------------------------------------
# Satir -> belge
# --------------------------------------------------------------------------


def _as_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _as_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a number")
    if isinstance(value, str):
        value = float(value)
    if not isinstance(value, (int, float)):
        raise ValueError(f"not a number: {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _row_to_document(
    adapter: Adapter,
    row: Mapping[str, Any],
    *,
    ordinal: int,
    file_label: str | None,
    row_index: int | None,
    source_id: str | None,
    unlisted: Iterable[str],
    report: AdapterReport,
) -> dict[str, Any] | None:
    text = row.get(adapter.text_column)
    if text is not None and not isinstance(text, str):
        raise ValueError(f"text column {adapter.text_column!r} is {type(text).__name__}, not a string")
    if text is None or not text.strip():
        report.note_empty(ordinal)
        return None
    provenance: dict[str, Any] = {
        "dataset": adapter.dataset,
        "revision": adapter.revision,
        "file": file_label,
        "row": row_index,
    }
    language: dict[str, Any] = {}
    rights: dict[str, Any] = {}
    groups = {"provenance": provenance, "language": language, "rights": rights}
    for target_path, constant in adapter.constants:
        group, key = target_path.split(".", 1)
        groups[group][key] = constant
    for target_path, column in adapter.field_map:
        if target_path == "text":
            continue
        group, key = target_path.split(".", 1)
        raw = row.get(column)
        groups[group][key] = _as_number(raw) if target_path in NUMBER_TARGETS else _as_string(raw)
    signals: dict[str, float] = {}
    for signal in adapter.signals:
        number = _as_number(row.get(signal.column))
        if number is None:
            report.missing_signal_values[signal.name] = report.missing_signal_values.get(signal.name, 0) + 1
            continue
        signals[signal.name] = number
    extra_values = {column: row.get(column) for column in adapter.extra}
    for column in unlisted:
        extra_values[column] = row.get(column)
    record = {
        "doc_id": document_id(text),
        "text": text,
        "source_id": source_id,
        "source_ordinal": ordinal,
        "provenance": {key: provenance.get(key) for key in PROVENANCE_FIELDS},
        "language": {key: language.get(key) for key in LANGUAGE_FIELDS},
        "signals": signals,
        "rights": {key: rights.get(key) for key in RIGHTS_FIELDS},
        "extra": encode_extra(extra_values),
    }
    validate_document(record)
    return record


def adapt_rows(
    adapter: Adapter,
    rows: Iterable[tuple[int, Mapping[str, Any]]],
    *,
    plan: ColumnPlan | None,
    report: AdapterReport,
    file_label: str | None,
    first_ordinal: int,
    source_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """(dosya ici satir no, satir) ciftlerini kayda cevirir.

    Her satir bir sira numarasi tuketir (bos ve gecersiz olanlar dahil): sira
    numarasindaki bosluk raporda gorunen kayittir. Gecersiz satir (tip hatasi,
    gecersiz canonical kayit) belge olmaz, ``invalid_records``'a yazilir.

    ``plan`` None ise sutun kumesi kayit basinadir (JSONL): her kayit ayri
    dogrulanir; eksik sutunlu kayit alimi durdurur, adi gecmeyen anahtarlar o
    kaydin extra'sina gider.
    """
    if adapter.target != DOCUMENT_SCHEMA_VERSION:
        raise AdapterError("adapt_rows is for document adapters; canonical adapters use adapt_file")
    known = set(adapter.columns_read) | set(adapter.columns_skipped)
    if plan is not None:
        report.note_columns(plan)
    ordinal = first_ordinal - 1
    for row_index, row in rows:
        ordinal += 1
        report.records_seen += 1
        if plan is None:
            missing = [column for column in adapter.columns_read if column not in row]
            if missing:
                raise AdapterError(
                    f"adapter {adapter.name}: {file_label} row {row_index} lacks mapped column(s) {missing}; "
                    "import refused"
                )
            unlisted = tuple(key for key in row if key not in known)
            skipped = tuple(key for key in row if key in adapter.columns_skipped)
            if unlisted or skipped:
                report.note_columns(ColumnPlan(read=(), skipped=skipped, unlisted=unlisted))
        else:
            unlisted = plan.unlisted
        try:
            record = _row_to_document(
                adapter,
                row,
                ordinal=ordinal,
                file_label=file_label,
                row_index=row_index,
                source_id=source_id,
                unlisted=unlisted,
                report=report,
            )
        except (ValueError, TypeError, DocumentRecordError) as error:
            report.note_invalid(ordinal, str(error))
            continue
        if record is None:
            continue
        report.documents += 1
        yield record


# --------------------------------------------------------------------------
# Dosya okuyuculari
# --------------------------------------------------------------------------


def _jsonl_rows(path: Path, adapter: Adapter, report: AdapterReport) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open("rb") as source:
        for row_index, raw in enumerate(source):
            line = raw.decode("utf-8").rstrip("\r\n")
            if not line.strip():
                report.blank_lines += 1
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise AdapterError(f"{path.name} line {row_index + 1}: invalid JSON ({error.msg})") from error
            if not isinstance(value, dict):
                raise AdapterError(f"{path.name} line {row_index + 1}: record is not a JSON object")
            yield row_index, value


def _tsv_rows(path: Path) -> tuple[list[str], Iterator[tuple[int, dict[str, Any]]]]:
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    handle = path.open("r", encoding="utf-8", newline="")
    reader = csv.reader(handle, dialect="excel-tab")
    try:
        header = next(reader)
    except StopIteration:
        handle.close()
        return [], iter(())

    def rows() -> Iterator[tuple[int, dict[str, Any]]]:
        try:
            for row_index, values in enumerate(reader):
                if len(values) != len(header):
                    raise AdapterError(
                        f"{path.name} row {row_index + 1}: {len(values)} cells, header has {len(header)}"
                    )
                # TSV'de bos hucre ile eksik deger ayirt edilemez: bos hucre None.
                yield row_index, {key: (cell if cell != "" else None) for key, cell in zip(header, values)}
        finally:
            handle.close()

    return header, rows()


def _parquet_plan_and_rows(
    path: Path, adapter: Adapter
) -> tuple[ColumnPlan, Iterator[tuple[int, dict[str, Any]]]]:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(str(path))
    try:
        plan = adapter.plan_columns(parquet.schema_arrow.names)
    except AdapterError:
        parquet.close()
        raise

    def rows() -> Iterator[tuple[int, dict[str, Any]]]:
        row_index = 0
        try:
            for group in range(parquet.num_row_groups):
                table = parquet.read_row_group(group, columns=list(plan.read))
                for row in table.to_pylist():
                    yield row_index, row
                    row_index += 1
        finally:
            parquet.close()

    return plan, rows()


def adapt_file(
    adapter: Adapter,
    path: Path,
    *,
    report: AdapterReport,
    first_ordinal: int = 1,
    file_label: str | None = None,
    source_id: str | None = None,
) -> Iterator[dict[str, Any] | CanonicalRecord]:
    """Yerel bir kaynak dosyasini uyarlayiciyla okur. Sutun dogrulamasi okumadan once."""
    label = file_label if file_label is not None else path.name
    report.files.append(label)
    if adapter.target == CANONICAL_SCHEMA_VERSION:
        return _adapt_canonical(adapter, path, report=report, first_ordinal=first_ordinal)
    if adapter.format == "parquet":
        plan, rows = _parquet_plan_and_rows(path, adapter)
    elif adapter.format == "tsv":
        header, rows = _tsv_rows(path)
        plan = adapter.plan_columns(header)
    else:
        rows, plan = _jsonl_rows(path, adapter, report), None
    return adapt_rows(
        adapter, rows, plan=plan, report=report, file_label=label, first_ordinal=first_ordinal, source_id=source_id
    )


def _adapt_canonical(
    adapter: Adapter, path: Path, *, report: AdapterReport, first_ordinal: int
) -> Iterator[CanonicalRecord]:
    assert adapter.content_purpose is not None
    ordinal = first_ordinal - 1
    with path.open("rb") as source:
        for raw in source:
            line = raw.decode("utf-8").rstrip("\r\n")
            if not line.strip():
                report.blank_lines += 1
                continue
            ordinal += 1
            report.records_seen += 1
            try:
                sample = parse_canonical_sample(line, adapter.content_purpose)
            except CanonicalSampleError as error:
                report.note_invalid(ordinal, f"invalid_canonical_sample: {error}")
                continue
            if sample is None:
                report.note_invalid(ordinal, "not_canonical_sample")
                continue
            parsed = json.loads(line)
            missing = [column for column in adapter.columns_read if column not in parsed]
            if missing:
                report.note_invalid(ordinal, f"missing fields {missing}")
                continue
            report.documents += 1
            yield CanonicalRecord(
                source_ordinal=ordinal,
                sample_id=sample.sample_id,
                record_type=sample.record_type,
                line=line,
            )


def adapt_files(
    adapter: Adapter,
    paths: Iterable[Path],
    *,
    report: AdapterReport,
    source_id: str | None = None,
) -> Iterator[dict[str, Any] | CanonicalRecord]:
    """Dosyalar verilen sirayla; sira numarasi dosyalar boyunca surer."""
    next_ordinal = 1
    for path in paths:
        before = report.records_seen
        yield from adapt_file(adapter, path, report=report, first_ordinal=next_ordinal, source_id=source_id)
        next_ordinal += report.records_seen - before


def new_report(adapter: Adapter) -> AdapterReport:
    return AdapterReport(adapter=adapter.name, adapter_sha256=adapter.sha256, target=adapter.target)


# --------------------------------------------------------------------------
# Geriye donuk: satir = belge kaynaklari (Faz-2 ana korpus ve turevleri)
# --------------------------------------------------------------------------


def line_source_documents(
    path: Path,
    *,
    report: AdapterReport,
    max_document_bytes: int,
    source_id: str | None,
    dataset: str,
    revision: str,
    file_label: str | None = None,
    language_declared: str | None = None,
    rights: Mapping[str, str | None] | None = None,
) -> Iterator[dict[str, Any]]:
    """Satir = belge nesnesinden belge kaydi (provenance = kaynak + satir no; adres yok).

    Metin satirin kendisidir (sondaki CR/LF haric, baska hicbir sey kirpilmaz):
    doc_id = clean_candidate'in satir SHA256'si, held-out ve atilacak-satir
    listeleriyle ayni kimlik. Sira numarasi = satir numarasi (1'den).
    """
    report.files.append(file_label or path.name)
    for ordinal, raw_line, oversized in _bounded_lines(path, max_document_bytes):
        report.records_seen += 1
        if oversized:
            report.note_oversized(ordinal)
            continue
        assert raw_line is not None
        if not raw_line.strip():
            report.note_empty(ordinal)
            continue
        record = {
            "doc_id": document_id(raw_line),
            "text": raw_line,
            "source_id": source_id,
            "source_ordinal": ordinal,
            "provenance": {
                "dataset": dataset,
                "revision": revision,
                "file": file_label,
                "row": ordinal - 1,
                "external_id": None,
                "url": None,
                "crawl_date": None,
                "dump": None,
            },
            "language": {"declared": language_declared, "detected": None, "score": None},
            "signals": {},
            "rights": {key: (rights or {}).get(key) for key in RIGHTS_FIELDS},
            "extra": None,
        }
        report.documents += 1
        yield record
