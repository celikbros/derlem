"""Hakem orneklemesi: standart kaynak kapisi (TASK-047).

Bir kaynagin belgelerinden tekduze (risk agirliksiz) belirlenimci bir orneklem
cekilir, kaynagi ele vermeyen bir KOR dosya ve ayri bir CEVAP ANAHTARI yazilir,
hakem (model ya da disaridan verilen hukum dosyasi) cagrilir ve dort sayi
hesaplanir: PII isabet orani, kural atma orani, hakem cop orani (Wilson %95),
insan ret orani (incelenmisse). Hukumler ``derlem.decision.v1`` satiridir
(``decision_type = jury``).

Orneklem (``jury-uniform-sha256-v1``):

- Parca kaynagi (``derlem.import-manifest.v1``): her belgenin anahtari
  ``sha256(yontem, tohum, doc_id)``; en kucuk ``n`` anahtar secilir. Secim
  yalniz (tohum, doc_id) kumesine baglidir -- parca sinirlari, sira numaralari
  ya da yeniden alim secimi degistirmez. Ayni metin iki kez geciyorsa (birebir
  kopya) en kucuk sira numarali gecis alinir, kopya sayisi raporlanir.
- Satir kaynagi (txt/jsonl): anahtar ``sha256(yontem, tohum, satir_no)``; bos
  ve sinir asan satirlar nufusa girmez (sayilir).

Kor dosya alanlari YALNIZ ``no``, ``metin``, ``kesildi``, ``char_count``'tur:
url, dump, kimlik, sira no, sinyal yoktur; metindeki her bosluk dizisi tek
bosluga indirilir (FineWeb2-HQ satir sonu tasir, v5 tasimaz -- bicim kaynagi ele
vermesin). Kilavuz ``rubrics/juri-siki-v1.md`` dosyasidir; SHA256'sinin ilk 8
hanesi hakem kimligine girer: ``sonnet+juri-siki-v1@<sha8>``.

Model cagrisi distilasyonun saglayici kaydindan gecer (anahtar YALNIZ worker
ortamindan, ``PROVIDERS['anthropic'].api_key_env``). Kosu basi ve gunluk ust
sinir zorunludur; gunluk sayac dayanikli bir defterdir (cagridan ONCE yazilir).
Anahtar yoksa durum ``judge_unavailable``: kor dosya ve anahtar yine yazilir,
hukumler ``score --verdicts`` ile disaridan verilir.

Komut satiri: ``python -m derlem_worker.jury --help`` (veritabanina yazmaz;
yalniz ``score --apply-db`` yazar).
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

import pyarrow.parquet as pq

from derlem_worker.document_record import (
    DECISION_SCHEMA,
    DECISION_SCHEMA_VERSION,
    DOCUMENT_SCHEMA_VERSION,
    ParquetRowWriter,
    document_id,
    make_decision,
    parquet_schema_version,
    validate_decision,
)
from derlem_worker.import_manifest import (
    ImportManifestError,
    load_import_manifest,
    manifest_shard_paths,
    verify_shard,
)
from derlem_worker.jury_scoring import (
    DECISION_VERDICT,
    Verdict,
    VerdictFileError,
    agreement_report,
    choose_anchor_rows,
    junk_numbers,
    load_verdict_file,
    parse_anchor_sheet,
    parse_model_answer,
    rate_with_interval,
    render_anchor_sheet,
)

SAMPLING_METHOD = "jury-uniform-sha256-v1"
RUN_SCHEMA = "derlem.jury-run.v1"
KEY_SCHEMA = "derlem.jury-key.v1"
QUALITY_NUMBERS_SCHEMA = "derlem.quality-numbers.v1"
DEFAULT_SAMPLE_SIZE = 200
BLIND_MAX_CHARS = 6000
BLIND_FIELDS = ("char_count", "kesildi", "metin", "no")
DEFAULT_RULE_POLICY = "tr-web-v3"
DEFAULT_MAX_DOCUMENT_BYTES = 256 * 1024

RUBRIC_ID = "juri-siki-v1"
RUBRIC_PATH = Path(__file__).resolve().parent / "rubrics" / f"{RUBRIC_ID}.md"

BLIND_FILE = "juri-kor.jsonl"
KEY_FILE = "juri-anahtar.json"
RUN_FILE = "kosu.json"
PASS1_FILE = "hukumler-p1.jsonl"
PASS2_FILE = "hukumler-p2.jsonl"
DECISIONS_FILE = "kararlar.parquet"
NUMBERS_FILE = "kalite-sayilari.json"
ANCHOR_FILE = "kurucu-capa.md"

_WHITESPACE_RE = re.compile(r"\s+")

# Fiyat tablosu (TASK-034: sert sinir cagri/jeton cinsindendir; para bir TAHMINDIR
# ve tablonun surumu kaydedilir). USD / 1M jeton; onbellek yazimi 5 dk TTL.
PRICE_TABLE_VERSION = "anthropic-2026-10-06"
PRICE_TABLE: dict[str, dict[str, float]] = {
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.20},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.20},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20},
}
DEFAULT_JUDGE_MODEL = "claude-sonnet-5-5"
DEFAULT_JUDGE_MAX_TOKENS = 2048
DEFAULT_JUDGE_EFFORT = "low"

# Kurucunun onaylayacagi butce (TASK-047 "Owner actions"); ortamdan degisir.
BUDGET_ENV = {
    "max_calls_per_run": ("DERLEM_JURY_MAX_CALLS_PER_RUN", 450),
    "max_tokens_per_run": ("DERLEM_JURY_MAX_TOKENS_PER_RUN", 3_000_000),
    "max_calls_per_day": ("DERLEM_JURY_MAX_CALLS_PER_DAY", 1_000),
    "max_tokens_per_day": ("DERLEM_JURY_MAX_TOKENS_PER_DAY", 6_000_000),
}
LEDGER_DIR_ENV = "DERLEM_JURY_LEDGER_DIR"
JUDGE_MODEL_ENV = "DERLEM_JURY_MODEL"

ProgressCallback = Callable[[dict[str, int]], None]


class JuryError(RuntimeError):
    pass


class JuryBudgetExhausted(JuryError):
    """Kosu basi ya da gunluk ust sinir: is durur, yeniden denenmez."""


# --------------------------------------------------------------------------
# Kilavuz ve hakem kimligi
# --------------------------------------------------------------------------


def rubric_bytes(path: Path | None = None) -> bytes:
    # Yol cagri aninda cozulur (varsayilan arguman degil): kilavuz SHA'si her
    # kullanimda dosyadan yeniden hesaplanir.
    return (path or RUBRIC_PATH).read_bytes()


def rubric_text(path: Path | None = None) -> str:
    return rubric_bytes(path).decode("utf-8")


def rubric_sha256(path: Path | None = None) -> str:
    return hashlib.sha256(rubric_bytes(path)).hexdigest()


def judge_family(model: str) -> str:
    lowered = model.lower()
    for family in ("sonnet", "opus", "haiku", "fable"):
        if family in lowered:
            return family
    return re.sub(r"[^a-z0-9-]+", "-", lowered).strip("-") or "judge"


def judge_id(label: str, rubric_sha: str, rubric_id: str = RUBRIC_ID) -> str:
    """``sonnet+juri-siki-v1@<sha8>``: kilavuz degisirse kimlik degisir."""
    return f"{label}+{rubric_id}@{rubric_sha[:8]}"


# --------------------------------------------------------------------------
# Orneklem
# --------------------------------------------------------------------------


def sample_key(seed: int, token: str) -> str:
    return hashlib.sha256(f"{SAMPLING_METHOD}\x1f{seed}\x1f{token}".encode("utf-8")).hexdigest()


def normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


@dataclass(frozen=True)
class SampledDocument:
    sample_key: str
    doc_id: str
    source_ordinal: int
    text: str
    external_id: str | None = None
    url: str | None = None
    dump: str | None = None


@dataclass
class SampleDraw:
    method: str
    seed: int
    requested: int
    source_kind: str
    population_documents: int
    skipped_empty: int = 0
    skipped_oversized: int = 0
    duplicate_occurrences: int = 0
    documents: list[SampledDocument] = field(default_factory=list)

    @property
    def doc_ids(self) -> list[str]:
        return [document.doc_id for document in self.documents]


def draw_sample(
    object_path: Path,
    *,
    n: int,
    seed: int,
    store_root: Path | None = None,
    max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    progress_callback: ProgressCallback | None = None,
) -> SampleDraw:
    """Kaynak nesnesinden tekduze belirlenimci orneklem (anahtar sirasinda)."""
    if n <= 0:
        raise ValueError("sample size must be positive")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    manifest = load_import_manifest(object_path) if store_root is not None else None
    if manifest is not None:
        assert store_root is not None
        return _draw_from_manifest(manifest, store_root, n=n, seed=seed, progress_callback=progress_callback)
    return _draw_from_lines(
        object_path, n=n, seed=seed, max_document_bytes=max_document_bytes, progress_callback=progress_callback
    )


def _draw_from_manifest(
    manifest: Mapping[str, Any],
    store_root: Path,
    *,
    n: int,
    seed: int,
    progress_callback: ProgressCallback | None,
) -> SampleDraw:
    shards = manifest_shard_paths(manifest, store_root)
    counters = {"population": 0}

    def keys() -> Iterator[tuple[str, str, int, int, int]]:
        for shard_index, (shard, path) in enumerate(shards):
            verify_shard(path, shard["sha256"], shard["byte_size"])
            if parquet_schema_version(path) != DOCUMENT_SCHEMA_VERSION:
                raise ImportManifestError(f"shard {shard['sha256']} is not a {DOCUMENT_SCHEMA_VERSION} shard")
            parquet = pq.ParquetFile(str(path))
            rows = 0
            try:
                for group in range(parquet.metadata.num_row_groups):
                    table = parquet.read_row_group(group, columns=["doc_id", "source_ordinal"])
                    for doc_id, ordinal in zip(
                        table.column("doc_id").to_pylist(), table.column("source_ordinal").to_pylist()
                    ):
                        rows += 1
                        yield (sample_key(seed, f"doc:{doc_id}"), doc_id, int(ordinal), shard_index, group)
            finally:
                parquet.close()
            if rows != shard["row_count"]:
                raise ImportManifestError(f"shard {shard['sha256']} has {rows} rows, manifest says {shard['row_count']}")
            counters["population"] += rows
            if progress_callback is not None:
                progress_callback({
                    "shards_read": shard_index + 1,
                    "shards_total": len(shards),
                    "documents_seen": counters["population"],
                })

    # Kopya metinler ayni anahtari tasir; fazladan aday kopyalari elemek icin.
    candidates = heapq.nsmallest(2 * n + 16, keys())
    population = counters["population"]
    picked: list[tuple[str, str, int, int, int]] = []
    seen: set[str] = set()
    duplicates = 0
    for candidate in candidates:
        if candidate[1] in seen:
            duplicates += 1
            continue
        if len(picked) < n:
            seen.add(candidate[1])
            picked.append(candidate)
    by_group: dict[tuple[int, int], dict[int, str]] = {}
    for key, _doc_id, ordinal, shard_index, group in picked:
        by_group.setdefault((shard_index, group), {})[ordinal] = key
    texts: dict[int, SampledDocument] = {}
    for (shard_index, group), wanted in sorted(by_group.items()):
        _shard, path = shards[shard_index]
        parquet = pq.ParquetFile(str(path))
        try:
            table = parquet.read_row_group(group, columns=["doc_id", "source_ordinal", "text", "provenance"])
        finally:
            parquet.close()
        for row in table.to_pylist():
            ordinal = int(row["source_ordinal"])
            if ordinal not in wanted:
                continue
            text = row["text"]
            if document_id(text) != row["doc_id"]:
                raise ImportManifestError(f"document {ordinal}: doc_id does not match its text")
            provenance = row.get("provenance") or {}
            texts[ordinal] = SampledDocument(
                sample_key=wanted[ordinal],
                doc_id=row["doc_id"],
                source_ordinal=ordinal,
                text=text,
                external_id=provenance.get("external_id"),
                url=provenance.get("url"),
                dump=provenance.get("dump"),
            )
    documents = [texts[ordinal] for _key, _doc, ordinal, _s, _g in picked]
    return SampleDraw(
        method=SAMPLING_METHOD,
        seed=seed,
        requested=n,
        source_kind="import_manifest",
        population_documents=population,
        duplicate_occurrences=duplicates,
        documents=documents,
    )


def _draw_from_lines(
    path: Path,
    *,
    n: int,
    seed: int,
    max_document_bytes: int,
    progress_callback: ProgressCallback | None,
) -> SampleDraw:
    from derlem_worker.sampling import _document_from_line

    counters = {"population": 0, "empty": 0, "oversized": 0}
    total_bytes = path.stat().st_size
    progress_every = 256 * 1024 * 1024

    def keys() -> Iterator[tuple[str, int, int, int]]:
        offset = 0
        next_progress = progress_every
        with path.open("rb") as handle:
            for ordinal, raw in enumerate(handle, 1):
                start = offset
                offset += len(raw)
                body = raw.rstrip(b"\r\n")
                if len(body) > max_document_bytes:
                    counters["oversized"] += 1
                elif not body.strip():
                    counters["empty"] += 1
                else:
                    counters["population"] += 1
                    yield (sample_key(seed, f"line:{ordinal}"), ordinal, start, len(raw))
                if progress_callback is not None and offset >= next_progress:
                    progress_callback({"input_bytes_processed": offset, "input_bytes_total": total_bytes, "lines_read": ordinal})
                    while next_progress <= offset:
                        next_progress += progress_every

    picked = heapq.nsmallest(n, keys())
    documents: list[SampledDocument] = []
    with path.open("rb") as handle:
        for key, ordinal, start, length in picked:
            handle.seek(start)
            body = handle.read(length).rstrip(b"\r\n").decode("utf-8")
            text, external_id = _document_from_line(body)
            documents.append(SampledDocument(
                sample_key=key, doc_id=document_id(text), source_ordinal=ordinal, text=text, external_id=external_id,
            ))
    return SampleDraw(
        method=SAMPLING_METHOD,
        seed=seed,
        requested=n,
        source_kind="lines",
        population_documents=counters["population"],
        skipped_empty=counters["empty"],
        skipped_oversized=counters["oversized"],
        documents=documents,
    )


# --------------------------------------------------------------------------
# Kor dosya ve cevap anahtari
# --------------------------------------------------------------------------


def blind_row(no: int, text: str) -> dict[str, Any]:
    normalized = normalize_whitespace(text)
    row = {
        "no": no,
        # Kesim bir boslukta biterse sondaki bosluk da gider (bicim izi kalmasin).
        "metin": normalized[:BLIND_MAX_CHARS].rstrip(),
        "kesildi": len(normalized) > BLIND_MAX_CHARS,
        "char_count": len(normalized),
    }
    assert_blind_row_clean(row)
    return row


def assert_blind_row_clean(row: Mapping[str, Any]) -> None:
    """Sizinti korumasi: yalniz izinli alanlar, bicim izi yok."""
    if tuple(sorted(row)) != BLIND_FIELDS:
        raise JuryError(f"blind row has non-blind fields: {sorted(set(row) - set(BLIND_FIELDS))}")
    text = row["metin"]
    if not isinstance(text, str) or _WHITESPACE_RE.search(text.replace(" ", "")) or "  " in text:
        raise JuryError("blind text must be whitespace-normalised (no line breaks, tabs or double spaces)")
    if text != text.strip():
        raise JuryError("blind text must not start or end with whitespace")


def _json_line(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _write_text(path: Path, text: str) -> str:
    data = text.encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def make_run_id(source_label: str, seed: int, n: int, rubric_sha: str, created_at: datetime) -> str:
    stamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"jury-{source_label[:8]}-s{seed}-n{n}-{rubric_sha[:8]}-{stamp}"


def prepare_run(
    draw: SampleDraw,
    out_dir: Path,
    *,
    source_id: str | None,
    object_sha256: str,
    language: str | None = "tr",
    rule_policy: str = DEFAULT_RULE_POLICY,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Kor dosya + cevap anahtari + kosu kaydi; kural ve PII orneklem uzerinde."""
    from derlem_worker.pii import PIIScanner, count_pii_in_text
    from derlem_worker.quality_filters import (
        QUALITY_FILTER_STATUS_NOT_EVALUATED,
        quality_filter_status,
        quality_rejection_reasons,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    created = created_at or _utc_now()
    sha = rubric_sha256()
    run_id = make_run_id(source_id or object_sha256, draw.seed, draw.requested, sha, created)
    rule_status = quality_filter_status(rule_policy, language)
    blind_lines: list[str] = []
    key_rows: list[dict[str, Any]] = []
    for no, document in enumerate(draw.documents, 1):
        row = blind_row(no, document.text)
        blind_lines.append(_json_line(row))
        reasons: tuple[str, ...] = ()
        if rule_status is not None and rule_status != QUALITY_FILTER_STATUS_NOT_EVALUATED:
            reasons = quality_rejection_reasons(document.text, rule_policy)
        pii_counts = count_pii_in_text(document.text)
        key_rows.append({
            "no": no,
            "doc_id": document.doc_id,
            "source_ordinal": document.source_ordinal,
            "sample_key": document.sample_key,
            "external_id": document.external_id,
            "url": document.url,
            "dump": document.dump,
            "char_count_original": len(document.text),
            "char_count": row["char_count"],
            "kesildi": row["kesildi"],
            "rule_reasons": list(reasons),
            "rule_drop": bool(reasons),
            "pii": pii_counts,
            "pii_hit": any(pii_counts.values()),
        })
    blind_sha = _write_text(out_dir / BLIND_FILE, "\n".join(blind_lines) + "\n")
    key = {
        "schema": KEY_SCHEMA,
        "run_id": run_id,
        "source_id": source_id,
        "object_sha256": object_sha256,
        "rows": key_rows,
    }
    key_sha = _write_text(out_dir / KEY_FILE, json.dumps(key, ensure_ascii=False, indent=1) + "\n")
    run = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "created_at": created.isoformat(),
        "source_id": source_id,
        "object_sha256": object_sha256,
        "language": language,
        "sample": {
            "method": draw.method,
            "seed": draw.seed,
            "requested": draw.requested,
            "n": len(draw.documents),
            "source_kind": draw.source_kind,
            "population_documents": draw.population_documents,
            "skipped_empty": draw.skipped_empty,
            "skipped_oversized": draw.skipped_oversized,
            "duplicate_occurrences": draw.duplicate_occurrences,
        },
        "blind": {"file": BLIND_FILE, "sha256": blind_sha, "fields": list(BLIND_FIELDS), "max_chars": BLIND_MAX_CHARS},
        "key": {"file": KEY_FILE, "sha256": key_sha},
        "rubric": {"id": RUBRIC_ID, "sha256": sha, "file": f"worker/src/derlem_worker/rubrics/{RUBRIC_ID}.md"},
        "rule": {"policy": rule_policy, "status": rule_status},
        "pii": {"scanner_version": PIIScanner.version},
    }
    _write_text(out_dir / RUN_FILE, json.dumps(run, ensure_ascii=False, indent=1) + "\n")
    return run


def load_run(run_dir: Path) -> tuple[dict[str, Any], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """(kosu, kor satirlar no->satir, anahtar satirlari no->satir); SHA'lar dogrulanir."""
    run = json.loads((run_dir / RUN_FILE).read_text(encoding="utf-8"))
    if run.get("schema") != RUN_SCHEMA:
        raise JuryError(f"{run_dir}: not a {RUN_SCHEMA} directory")
    for part in ("blind", "key"):
        data = (run_dir / run[part]["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != run[part]["sha256"]:
            raise JuryError(f"{run[part]['file']} changed after the run was prepared")
    blind = {}
    for line in (run_dir / BLIND_FILE).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            blind[int(row["no"])] = row
    key = json.loads((run_dir / KEY_FILE).read_text(encoding="utf-8"))
    return run, blind, {int(row["no"]): row for row in key["rows"]}


# --------------------------------------------------------------------------
# Butce: kosu basi ve gunluk ust sinir, dayanikli defter
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetLimits:
    max_calls_per_run: int
    max_tokens_per_run: int
    max_calls_per_day: int
    max_tokens_per_day: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "BudgetLimits":
        source = os.environ if env is None else env
        values: dict[str, int] = {}
        for name, (variable, default) in BUDGET_ENV.items():
            raw = str(source.get(variable, "") or "").strip()
            value = int(raw) if raw else default
            if value < 0:
                raise ValueError(f"{variable} must be non-negative")
            values[name] = value
        return cls(**values)

    def to_dict(self) -> dict[str, int]:
        return {
            "max_calls_per_run": self.max_calls_per_run,
            "max_tokens_per_run": self.max_tokens_per_run,
            "max_calls_per_day": self.max_calls_per_day,
            "max_tokens_per_day": self.max_tokens_per_day,
        }


class BudgetLedger:
    """Gunluk (UTC) dayanikli sayac: ``jury-budget-YYYY-MM-DD.json``.

    Her cagri ONCE ayrilir (cagri + tahmini jeton) ve diske yazilir (fsync +
    atomik yer degistirme); cagridan sonra tahmin gercek jetonla duzeltilir.
    Surec cagri sirasinda olurse ayrilan cagri sayilmis kalir: sayac asla eksik
    saymaz. Es zamanli yazicilar bir kilit dosyasiyla siralanir.
    """

    def __init__(self, ledger_dir: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.ledger_dir = ledger_dir
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _path(self) -> Path:
        return self.ledger_dir / f"jury-budget-{self.clock().astimezone(timezone.utc):%Y-%m-%d}.json"

    def _lock(self) -> Path:
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        lock = self.ledger_dir / "jury-budget.lock"
        deadline = time.monotonic() + 30
        while True:
            try:
                descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, str(os.getpid()).encode("ascii"))
                os.close(descriptor)
                return lock
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > 120:
                        lock.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise JuryError(f"budget ledger lock is held: {lock}")
                time.sleep(0.05)

    def read(self) -> dict[str, Any]:
        path = self._path()
        if not path.exists():
            return {"day": path.stem.removeprefix("jury-budget-"), "calls": 0, "tokens": 0, "runs": {}}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, state: Mapping[str, Any]) -> None:
        path = self._path()
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, ensure_ascii=False, sort_keys=True, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)

    def update(self, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        lock = self._lock()
        try:
            state = self.read()
            change(state)
            self._write(state)
            return state
        finally:
            lock.unlink(missing_ok=True)


class JuryBudget:
    def __init__(self, ledger: BudgetLedger, limits: BudgetLimits, run_id: str) -> None:
        self.ledger = ledger
        self.limits = limits
        self.run_id = run_id

    def _run(self, state: Mapping[str, Any]) -> dict[str, int]:
        return dict(state.get("runs", {}).get(self.run_id, {"calls": 0, "tokens": 0}))

    def preflight(self, planned_calls: int, planned_tokens: int) -> dict[str, Any]:
        """Hic cagri yapmadan once: plan (cagri + kotumser jeton tahmini) sinirlara
        sigmiyorsa is baslamaz."""
        state = self.ledger.read()
        run = self._run(state)
        problems = []
        if run["calls"] + planned_calls > self.limits.max_calls_per_run:
            problems.append(f"run calls {run['calls'] + planned_calls} > {self.limits.max_calls_per_run}")
        if run["tokens"] + planned_tokens > self.limits.max_tokens_per_run:
            problems.append(f"run tokens {run['tokens'] + planned_tokens} > {self.limits.max_tokens_per_run}")
        if int(state["calls"]) + planned_calls > self.limits.max_calls_per_day:
            problems.append(f"day calls {int(state['calls']) + planned_calls} > {self.limits.max_calls_per_day}")
        if int(state["tokens"]) + planned_tokens > self.limits.max_tokens_per_day:
            problems.append(f"day tokens {int(state['tokens']) + planned_tokens} > {self.limits.max_tokens_per_day}")
        if problems:
            raise JuryBudgetExhausted("judge_budget_exceeded before any call: " + "; ".join(problems))
        return {"planned_calls": planned_calls, "planned_tokens": planned_tokens}

    def reserve(self, estimated_tokens: int) -> None:
        def change(state: dict[str, Any]) -> None:
            run = self._run(state)
            if run["calls"] + 1 > self.limits.max_calls_per_run:
                raise JuryBudgetExhausted(f"judge_budget_exhausted: run call cap {self.limits.max_calls_per_run}")
            if run["tokens"] + estimated_tokens > self.limits.max_tokens_per_run:
                raise JuryBudgetExhausted(f"judge_budget_exhausted: run token cap {self.limits.max_tokens_per_run}")
            if int(state["calls"]) + 1 > self.limits.max_calls_per_day:
                raise JuryBudgetExhausted(f"judge_budget_exhausted: daily call cap {self.limits.max_calls_per_day}")
            if int(state["tokens"]) + estimated_tokens > self.limits.max_tokens_per_day:
                raise JuryBudgetExhausted(f"judge_budget_exhausted: daily token cap {self.limits.max_tokens_per_day}")
            run["calls"] += 1
            run["tokens"] += estimated_tokens
            state["calls"] = int(state["calls"]) + 1
            state["tokens"] = int(state["tokens"]) + estimated_tokens
            state.setdefault("runs", {})[self.run_id] = run

        self.ledger.update(change)

    def settle(self, estimated_tokens: int, actual_tokens: int) -> None:
        delta = actual_tokens - estimated_tokens

        def change(state: dict[str, Any]) -> None:
            run = self._run(state)
            run["tokens"] = max(0, run["tokens"] + delta)
            state["tokens"] = max(0, int(state["tokens"]) + delta)
            state.setdefault("runs", {})[self.run_id] = run

        self.ledger.update(change)


def default_ledger_dir(storage_root: Path | None = None) -> Path:
    configured = os.environ.get(LEDGER_DIR_ENV, "").strip()
    if configured:
        return Path(configured).resolve()
    base = (storage_root.parent if storage_root is not None else Path("var").resolve())
    return base / "state" / "jury-budget"


# --------------------------------------------------------------------------
# Hakem cagrisi
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class JudgeResponse:
    text: str
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens


JudgeCaller = Callable[[str], JudgeResponse]


@dataclass(frozen=True)
class JudgeSettings:
    provider: str
    model: str
    api_key_env: str
    max_tokens: int = DEFAULT_JUDGE_MAX_TOKENS
    effort: str = DEFAULT_JUDGE_EFFORT

    @property
    def label(self) -> str:
        return judge_family(self.model)


def resolve_judge(env: Mapping[str, str] | None = None) -> tuple[JudgeSettings, str | None]:
    """Saglayici kaydindan ayarlar ve anahtar (yoksa None -> judge_unavailable).

    Anahtar degiskeninin ADI kayittan gelir; is yukunden ya da veritabanindan
    asla okunmaz (distill_jobs ile ayni kural).
    """
    from derlem_worker.distillation import PROVIDERS

    source = os.environ if env is None else env
    spec = PROVIDERS["anthropic"]
    model = str(source.get(JUDGE_MODEL_ENV, "") or "").strip() or DEFAULT_JUDGE_MODEL
    settings = JudgeSettings(provider=spec.key, model=model, api_key_env=spec.api_key_env)
    api_key = str(source.get(spec.api_key_env, "") or "").strip()
    return settings, (api_key or None)


def anthropic_judge_caller(
    settings: JudgeSettings,
    api_key: str,
    rubric: str,
    *,
    post: Callable[[str, dict[str, str], dict], dict] | None = None,
) -> JudgeCaller:
    """Kilavuz sistem isteminde (onbellekli), belge kullanici mesajinda."""
    from derlem_worker.distillation import PROVIDERS, _http_post_json

    spec = PROVIDERS[settings.provider]
    sender = post or _http_post_json

    def call(user_message: str) -> JudgeResponse:
        body = {
            "model": settings.model,
            "max_tokens": settings.max_tokens,
            "system": [{"type": "text", "text": rubric, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user_message}],
            "output_config": {"effort": settings.effort},
        }
        data = sender(spec.api_base, {"x-api-key": api_key, "anthropic-version": "2023-06-01"}, body)
        usage = data.get("usage") or {}
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        return JudgeResponse(
            text=text,
            stop_reason=data.get("stop_reason"),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens") or 0),
            cache_read_input_tokens=int(usage.get("cache_read_input_tokens") or 0),
        )

    return call


def judge_user_message(row: Mapping[str, Any]) -> str:
    cut = ", kesildi" if row.get("kesildi") else ""
    return (
        f"Belge (juri no {row['no']}) · {row['char_count']} karakter{cut}:\n\n"
        f"<metin>\n{row['metin']}\n</metin>\n\nYalniz JSON nesnesini yaz."
    )


def estimate_call_tokens(rubric: str, row: Mapping[str, Any], max_tokens: int) -> int:
    # Turkce ~3 karakter/jeton; tahmin bilerek kotumser (2 karakter/jeton).
    return math.ceil((len(rubric) + len(judge_user_message(row))) / 2) + max_tokens


@dataclass
class JudgePass:
    label: str
    verdicts: dict[int, Verdict] = field(default_factory=dict)
    errors: dict[int, str] = field(default_factory=dict)
    calls: int = 0
    usage: Counter = field(default_factory=Counter)


def judge_rows(
    blind_rows: Sequence[Mapping[str, Any]],
    caller: JudgeCaller,
    budget: JuryBudget,
    *,
    rubric: str,
    max_tokens: int,
    label: str,
    progress_callback: ProgressCallback | None = None,
    max_consecutive_errors: int = 5,
) -> JudgePass:
    """Her belge icin bir cagri; butce cagridan ONCE ayrilir.

    Ret (``stop_reason = refusal``) ya da ayristirilamayan cevap o satirda
    hukum yok demektir (raporlanir); yedek model kullanilmaz -- yedek hakemi
    sessizce degistirir ve judge id yalan olur.
    """
    result = JudgePass(label=label)
    consecutive = 0
    for index, row in enumerate(blind_rows, 1):
        number = int(row["no"])
        estimate = estimate_call_tokens(rubric, row, max_tokens)
        budget.reserve(estimate)
        result.calls += 1
        try:
            response = caller(judge_user_message(row))
        except Exception as error:  # noqa: BLE001 - satir hatasi kaydedilir, sayac ayrildi
            budget.settle(estimate, estimate)
            result.errors[number] = f"call_failed: {error}"[:500]
            consecutive += 1
            if consecutive >= max_consecutive_errors:
                raise JuryError(f"judge failed {consecutive} times in a row; last: {error}") from error
            continue
        budget.settle(estimate, response.total_tokens)
        for name in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            result.usage[name] += getattr(response, name)
        if response.stop_reason == "refusal":
            result.errors[number] = "refusal"
            consecutive += 1
        else:
            try:
                result.verdicts[number] = parse_model_answer(response.text, number)
                consecutive = 0
            except VerdictFileError as error:
                result.errors[number] = f"unparsable: {error}"[:500]
                consecutive += 1
        if consecutive >= max_consecutive_errors:
            raise JuryError(f"judge failed {consecutive} times in a row")
        if progress_callback is not None:
            progress_callback({"pass": 1 if label == "p1" else 2, "judged": index, "total": len(blind_rows),
                               "verdicts": len(result.verdicts), "errors": len(result.errors), "calls": result.calls})
    return result


def estimated_cost_usd(usage: Mapping[str, int], model: str) -> float | None:
    prices = PRICE_TABLE.get(model)
    if prices is None:
        return None
    return round(
        (usage.get("input_tokens", 0) * prices["input"]
         + usage.get("output_tokens", 0) * prices["output"]
         + usage.get("cache_creation_input_tokens", 0) * prices["cache_write"]
         + usage.get("cache_read_input_tokens", 0) * prices["cache_read"]) / 1_000_000,
        4,
    )


def write_verdicts(path: Path, verdicts: Mapping[int, Verdict]) -> str:
    lines = [_json_line(verdicts[number].to_json()) for number in sorted(verdicts)]
    return _write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def run_judge(
    run_dir: Path,
    caller: JudgeCaller,
    budget: JuryBudget,
    *,
    settings: JudgeSettings,
    retest: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> tuple[JudgePass, JudgePass | None, dict[str, Any]]:
    run, blind, _key = load_run(run_dir)
    rubric = rubric_text()
    if rubric_sha256() != run["rubric"]["sha256"]:
        raise JuryError("rubric changed since the run was prepared; prepare a new run")
    rows = [blind[number] for number in sorted(blind)]
    passes = 2 if retest else 1
    per_pass = sum(estimate_call_tokens(rubric, row, settings.max_tokens) for row in rows)
    planned = budget.preflight(len(rows) * passes, per_pass * passes)
    pass1 = judge_rows(rows, caller, budget, rubric=rubric, max_tokens=settings.max_tokens, label="p1",
                       progress_callback=progress_callback)
    write_verdicts(run_dir / PASS1_FILE, pass1.verdicts)
    pass2 = None
    if retest:
        pass2 = judge_rows(rows, caller, budget, rubric=rubric, max_tokens=settings.max_tokens, label="p2",
                           progress_callback=progress_callback)
        write_verdicts(run_dir / PASS2_FILE, pass2.verdicts)
    usage: Counter = Counter()
    for item in (pass1, pass2):
        if item is not None:
            usage.update(item.usage)
    cost = {
        "model": settings.model,
        "calls": pass1.calls + (pass2.calls if pass2 else 0),
        "planned_calls": planned["planned_calls"],
        "usage": dict(usage),
        "estimated_usd": estimated_cost_usd(usage, settings.model),
        "price_table": PRICE_TABLE_VERSION,
        "limits": budget.limits.to_dict(),
        "errors": {"p1": pass1.errors, "p2": pass2.errors if pass2 else {}},
    }
    return pass1, pass2, cost


# --------------------------------------------------------------------------
# Karar satirlari ve dort sayi
# --------------------------------------------------------------------------


def decision_rows(
    key_rows: Mapping[int, Mapping[str, Any]],
    verdicts: Mapping[int, Verdict],
    *,
    judge: str,
    run_id: str,
    decided_at: datetime,
) -> list[dict[str, Any]]:
    rows = []
    for number in sorted(verdicts):
        verdict = verdicts[number]
        key = key_rows[number]
        rows.append(make_decision(
            doc_id=key["doc_id"],
            source_ordinal=int(key["source_ordinal"]),
            decision_type="jury",
            verdict=DECISION_VERDICT[verdict.verdict],
            reason=verdict.decision_reason,
            judge=judge,
            run_id=run_id,
            decided_at=decided_at,
        ))
    return rows


def write_decisions(path: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    writer = ParquetRowWriter(path, DECISION_SCHEMA, validator=validate_decision)
    try:
        for row in rows:
            writer.add(row)
    except BaseException:
        writer.abort()
        raise
    info = writer.close()
    return {"file": path.name, "schema": DECISION_SCHEMA_VERSION, "sha256": info.sha256,
            "byte_size": info.byte_size, "rows": info.row_count}


def compute_quality_numbers(
    run: Mapping[str, Any],
    key_rows: Mapping[int, Mapping[str, Any]],
    *,
    pass1: Mapping[int, Verdict] | None,
    pass2: Mapping[int, Verdict] | None,
    judge: str | None,
    judge_model: str | None,
    computed_at: datetime,
    decisions: Mapping[str, Any] | None = None,
    human: Mapping[str, int] | None = None,
    population_pii: Mapping[str, Any] | None = None,
    cost: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [key_rows[number] for number in sorted(key_rows)]
    n = len(rows)
    pii_categories: Counter = Counter()
    for row in rows:
        for category, count in (row.get("pii") or {}).items():
            if count:
                pii_categories[category] += 1
    pii = {"scope": "sample", "scanner_version": run["pii"]["scanner_version"],
           **rate_with_interval(sum(1 for row in rows if row.get("pii_hit")), n),
           "documents_by_category": dict(sorted(pii_categories.items()))}
    if population_pii:
        pii["population"] = dict(population_pii)
    reasons: Counter = Counter()
    for row in rows:
        reasons.update(row.get("rule_reasons") or [])
    rule = {"scope": "sample", "policy": run["rule"]["policy"], "status": run["rule"]["status"],
            **rate_with_interval(sum(1 for row in rows if row.get("rule_drop")), n),
            "reasons": dict(sorted(reasons.items(), key=lambda item: (-item[1], item[0])))}
    if pass1 is not None:
        jury: dict[str, Any] = {"status": "judged", **junk_numbers(pass1, n)}
        jury["retest"] = (
            agreement_report({k: v.verdict for k, v in pass1.items()}, {k: v.verdict for k, v in pass2.items()})
            if pass2 is not None else None
        )
        if jury["retest"] is not None:
            jury["retest"].pop("disagreements", None)
        # Kural-hakem capraz tablosu: kuralin gormedigi copu gosterir.
        crossed = Counter()
        for number, verdict in pass1.items():
            crossed[f"rule_{'drop' if key_rows[number].get('rule_drop') else 'keep'}__jury_{'junk' if verdict.verdict != 'kalsin' else 'keep'}"] += 1
        jury["rule_crosstab"] = dict(sorted(crossed.items()))
    else:
        jury = {"status": "judge_unavailable", "rate": None, "low": None, "high": None, "n": 0}
    human_numbers = None
    if human and int(human.get("reviewed", 0)) > 0:
        human_numbers = {"scope": "review_sample", **rate_with_interval(int(human["rejected"]), int(human["reviewed"]))}
    return {
        "schema": QUALITY_NUMBERS_SCHEMA,
        "computed_at": computed_at.isoformat(),
        "run_id": run["run_id"],
        "source_id": run.get("source_id"),
        "object_sha256": run["object_sha256"],
        "sample": dict(run["sample"]),
        "rubric": {"id": run["rubric"]["id"], "sha256": run["rubric"]["sha256"]},
        "judge_id": judge,
        "judge_model": judge_model,
        "pii": pii,
        "rule": rule,
        "jury": jury,
        "human": human_numbers,
        "decisions": dict(decisions) if decisions else None,
        "blind_sha256": run["blind"]["sha256"],
        "key_sha256": run["key"]["sha256"],
        "cost": dict(cost) if cost else None,
    }


def score_run(
    run_dir: Path,
    *,
    pass1: Mapping[int, Verdict] | None,
    pass2: Mapping[int, Verdict] | None,
    judge_label: str | None,
    judge_model: str | None,
    computed_at: datetime | None = None,
    human: Mapping[str, int] | None = None,
    population_pii: Mapping[str, Any] | None = None,
    cost: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Karar parquet'i (hukum varsa) ve ``kalite-sayilari.json``."""
    run, _blind, key_rows = load_run(run_dir)
    sha = run["rubric"]["sha256"]
    if rubric_sha256() != sha:
        raise JuryError("rubric in the repository differs from the run's rubric; judge id would lie")
    computed = computed_at or _utc_now()
    judge = judge_id(judge_label, sha) if (pass1 is not None and judge_label) else None
    decisions = None
    if pass1 is not None:
        assert judge is not None
        rows = decision_rows(key_rows, pass1, judge=judge, run_id=run["run_id"], decided_at=computed)
        if pass2 is not None:
            rows += decision_rows(key_rows, pass2, judge=judge, run_id=f"{run['run_id']}/retest", decided_at=computed)
        decisions = write_decisions(run_dir / DECISIONS_FILE, rows)
    numbers = compute_quality_numbers(
        run, key_rows, pass1=pass1, pass2=pass2, judge=judge, judge_model=judge_model, computed_at=computed,
        decisions=decisions, human=human, population_pii=population_pii, cost=cost,
    )
    _write_text(run_dir / NUMBERS_FILE, json.dumps(numbers, ensure_ascii=False, indent=1) + "\n")
    return numbers


# --------------------------------------------------------------------------
# Karma kor dosya (iki kosu tek oturumda: hakem katiligi esit)
# --------------------------------------------------------------------------

MIX_KEY_FILE = "karma-anahtar.json"


def mix_runs(run_dirs: Sequence[Path], out_dir: Path, *, seed: int) -> dict[str, Any]:
    rows: list[tuple[str, int, Mapping[str, Any]]] = []
    for run_dir in run_dirs:
        run, blind, _key = load_run(run_dir)
        for number in sorted(blind):
            rows.append((str(run_dir.resolve()), number, blind[number]))
    random.Random(seed).shuffle(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Kosu dizinleri karma dizine gore goreli yazilir (klasor tasinabilir kalir).
    rows = [(os.path.relpath(run_dir, out_dir.resolve()).replace(os.sep, "/"), number, row) for run_dir, number, row in rows]
    lines, key = [], []
    for number, (run_dir, run_no, row) in enumerate(rows, 1):
        mixed = {"no": number, "metin": row["metin"], "kesildi": row["kesildi"], "char_count": row["char_count"]}
        assert_blind_row_clean(mixed)
        lines.append(_json_line(mixed))
        key.append({"no": number, "run_dir": run_dir, "run_no": run_no})
    blind_sha = _write_text(out_dir / BLIND_FILE, "\n".join(lines) + "\n")
    _write_text(out_dir / MIX_KEY_FILE, json.dumps({"seed": seed, "blind_sha256": blind_sha, "rows": key}, indent=1) + "\n")
    return {"rows": len(rows), "blind_sha256": blind_sha}


def split_mixed_verdicts(mix_dir: Path, verdict_file: Path, *, output_name: str) -> dict[str, int]:
    key = json.loads((mix_dir / MIX_KEY_FILE).read_text(encoding="utf-8"))
    blind_sha = hashlib.sha256((mix_dir / BLIND_FILE).read_bytes()).hexdigest()
    if blind_sha != key["blind_sha256"]:
        raise JuryError("mixed blind file changed after mixing")
    mapping = {int(row["no"]): (row["run_dir"], int(row["run_no"])) for row in key["rows"]}
    verdicts, _missing = load_verdict_file(verdict_file, mapping)
    per_run: dict[str, dict[int, Verdict]] = {}
    for number, verdict in verdicts.items():
        run_dir, run_no = mapping[number]
        run_dir = str((mix_dir / run_dir).resolve())
        per_run.setdefault(run_dir, {})[run_no] = Verdict(run_no, verdict.verdict, verdict.genre, verdict.junk_reason, verdict.rationale)
    counts = {}
    for run_dir, items in per_run.items():
        write_verdicts(Path(run_dir) / output_name, items)
        counts[run_dir] = len(items)
    return counts


# --------------------------------------------------------------------------
# Veritabani (yalniz is ve ``score --apply-db``)
# --------------------------------------------------------------------------


def load_source_context(connection, source_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT source.object_sha256, source.language, source.content_purpose, source.document_count,
            source.reviewed_document_count, source.flagged_document_count, object.storage_key
        FROM sources AS source
        JOIN storage_objects AS object ON object.sha256 = source.object_sha256
        WHERE source.id = %s
        """,
        (source_id,),
    ).fetchone()
    if row is None:
        raise JuryError("Source or stored object was not found")
    object_sha256, language, purpose, document_count, reviewed, flagged, storage_key = row
    scan = connection.execute(
        """
        SELECT scanner_version, status, findings FROM pii_scans
        WHERE source_id = %s AND object_sha256 = %s
        ORDER BY scanned_at DESC LIMIT 1
        """,
        (source_id, object_sha256),
    ).fetchone()
    population_pii = None
    if scan is not None:
        findings = dict(scan[2] or {})
        hits = sum(int(value or 0) for value in findings.values())
        population_pii = {
            "scope": "population_scan",
            "scanner_version": scan[0],
            "status": scan[1],
            "hits": hits,
            "findings": findings,
            "hits_per_1k_documents": round(1000 * hits / int(document_count), 3) if document_count else None,
        }
    return {
        "object_sha256": str(object_sha256),
        "language": str(language),
        "content_purpose": str(purpose),
        "storage_key": str(storage_key),
        "human": {"reviewed": int(reviewed or 0), "rejected": int(flagged or 0)},
        "population_pii": population_pii,
    }


ARTIFACT_MEDIA_TYPES = {
    BLIND_FILE: "application/x-ndjson; charset=utf-8",
    KEY_FILE: "application/json",
    RUN_FILE: "application/json",
    PASS1_FILE: "application/x-ndjson; charset=utf-8",
    PASS2_FILE: "application/x-ndjson; charset=utf-8",
    DECISIONS_FILE: "application/vnd.apache.parquet",
    NUMBERS_FILE: "application/json",
}


def publish_run_artifacts(store, run_dir: Path) -> dict[str, dict[str, Any]]:
    """Kosu dosyalarini nesne deposuna alir (hukum dosyalari varsa)."""
    published: dict[str, dict[str, Any]] = {}
    for name, media_type in ARTIFACT_MEDIA_TYPES.items():
        path = run_dir / name
        if not path.exists() or name == NUMBERS_FILE:
            continue
        stored = store.ingest_raw_file(path) if name == DECISIONS_FILE else store.ingest_bytes(path.read_bytes())
        published[name] = {"sha256": stored.sha256, "storage_key": stored.storage_key,
                           "byte_size": stored.byte_size, "media_type": media_type}
    return published


def record_quality_numbers(connection, *, source_id: str, numbers: Mapping[str, Any],
                           artifacts: Mapping[str, Mapping[str, Any]], actor_job_id: str | None = None) -> None:
    """``sources.source_metadata.quality_numbers`` + depo nesneleri + denetim olayi (migration yok)."""
    for item in artifacts.values():
        connection.execute(
            """
            INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (sha256) DO NOTHING
            """,
            (item["sha256"], item["storage_key"], item["byte_size"], item["media_type"]),
        )
    payload = dict(numbers)
    payload["artifacts"] = {name: item["sha256"] for name, item in artifacts.items()}
    updated = connection.execute(
        """
        UPDATE sources
        SET source_metadata = jsonb_set(COALESCE(source_metadata, '{}'::jsonb), '{quality_numbers}', %s::jsonb, true)
        WHERE id = %s AND object_sha256 = %s
        """,
        (json.dumps(payload, ensure_ascii=False), source_id, numbers["object_sha256"]),
    )
    if updated.rowcount != 1:
        raise JuryError("Source object changed while recording quality numbers")
    connection.execute(
        """
        INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
        VALUES ('system', 'source.quality_numbers_recorded', 'source', %s, %s::jsonb)
        """,
        (source_id, json.dumps({
            "job_id": actor_job_id,
            "run_id": numbers["run_id"],
            "judge_id": numbers.get("judge_id"),
            "jury_status": numbers["jury"]["status"],
            "decisions_sha256": (numbers.get("decisions") or {}).get("sha256"),
        })),
    )


# --------------------------------------------------------------------------
# Komut satiri
# --------------------------------------------------------------------------


def _read_only_source(source_id: str) -> tuple[dict[str, Any], Path, Path]:
    import psycopg

    from derlem_worker.config import load_config

    config = load_config()
    with psycopg.connect(config.database_url) as connection:
        connection.read_only = True
        context = load_source_context(connection, source_id)
    path = (config.storage_root / context["storage_key"]).resolve(strict=True)
    path.relative_to(config.storage_root)
    return context, path, config.storage_root


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=1))


def _command_sample(args: argparse.Namespace) -> int:
    started = time.monotonic()
    context: dict[str, Any] = {}
    if args.object:
        object_path = Path(args.object).resolve()
        store_root = Path(args.store_root).resolve()
        object_sha256 = args.object_sha256 or object_path.name
        language = args.language
    else:
        context, object_path, store_root = _read_only_source(args.source_id)
        object_sha256 = context["object_sha256"]
        language = args.language or context["language"]

    def progress(values: dict[str, int]) -> None:
        print(f"  ... {values}", file=sys.stderr, flush=True)

    draw = draw_sample(object_path, n=args.n, seed=args.seed, store_root=store_root,
                       max_document_bytes=args.max_document_bytes, progress_callback=progress)
    out_dir = Path(args.out).resolve()
    run = prepare_run(draw, out_dir, source_id=args.source_id, object_sha256=object_sha256,
                      language=language, rule_policy=args.policy)
    numbers = score_run(out_dir, pass1=None, pass2=None, judge_label=None, judge_model=None,
                        human=(context.get("human") if context else None),
                        population_pii=(context.get("population_pii") if context else None))
    _print({"run_id": run["run_id"], "out": str(out_dir), "sample": run["sample"],
            "blind_sha256": run["blind"]["sha256"], "pii": {k: numbers["pii"][k] for k in ("count", "n", "rate", "low", "high")},
            "rule": {k: numbers["rule"][k] for k in ("count", "n", "rate", "low", "high")},
            "jury": numbers["jury"]["status"], "seconds": round(time.monotonic() - started, 1)})
    return 0


def _command_judge(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    run, _blind, _key = load_run(run_dir)
    settings, api_key = resolve_judge()
    if api_key is None:
        print(f"judge_unavailable: {settings.api_key_env} is not set in this environment; "
              f"use `score --verdicts` with verdicts produced elsewhere", file=sys.stderr)
        return 3
    budget = JuryBudget(BudgetLedger(default_ledger_dir()), BudgetLimits.from_env(), run["run_id"])
    caller = anthropic_judge_caller(settings, api_key, rubric_text())
    pass1, pass2, cost = run_judge(run_dir, caller, budget, settings=settings, retest=not args.no_retest,
                                   progress_callback=lambda values: print(f"  ... {values}", file=sys.stderr, flush=True))
    numbers = score_run(run_dir, pass1=pass1.verdicts, pass2=(pass2.verdicts if pass2 else None),
                        judge_label=settings.label, judge_model=settings.model, cost=cost)
    _print({"jury": numbers["jury"], "cost": cost})
    return 0


def _command_score(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    run, blind, _key = load_run(run_dir)
    pass1, missing1 = load_verdict_file(Path(args.verdicts), blind)
    pass2 = None
    missing2: list[int] = []
    if args.retest:
        pass2, missing2 = load_verdict_file(Path(args.retest), blind)
    context: dict[str, Any] = {}
    if args.source_id_context or args.apply_db:
        if not run.get("source_id"):
            raise JuryError("this run has no source_id; database context is unavailable")
        _ctx, _path, _root = _read_only_source(run["source_id"])
        context = _ctx
        if context["object_sha256"] != run["object_sha256"]:
            raise JuryError("source object changed since the run was prepared")
    numbers = score_run(
        run_dir, pass1=pass1, pass2=pass2, judge_label=args.judge_label,
        judge_model=args.judge_model or f"external:{args.judge_label}",
        human=context.get("human"), population_pii=context.get("population_pii"),
    )
    if args.apply_db:
        import psycopg

        from derlem_worker.config import load_config
        from derlem_worker.storage import ContentAddressedStore

        config = load_config()
        artifacts = publish_run_artifacts(ContentAddressedStore(config.storage_root), run_dir)
        with psycopg.connect(config.database_url) as connection:
            with connection.transaction():
                record_quality_numbers(connection, source_id=run["source_id"], numbers=numbers, artifacts=artifacts)
    jury = numbers["jury"]
    _print({
        "run_id": numbers["run_id"], "judge_id": numbers["judge_id"],
        "jury_junk": {k: jury.get(k) for k in ("count", "n", "rate", "low", "high", "counts", "missing")},
        "retest": jury.get("retest"),
        "rule": {k: numbers["rule"][k] for k in ("count", "n", "rate", "low", "high")},
        "pii": {k: numbers["pii"][k] for k in ("count", "n", "rate", "low", "high")},
        "rule_crosstab": jury.get("rule_crosstab"),
        "missing": {"p1": missing1, "p2": missing2},
        "decisions": numbers["decisions"],
        "applied_to_db": bool(args.apply_db),
    })
    return 0


def _command_anchor(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    run, blind, key = load_run(run_dir)
    pass1, _ = load_verdict_file(Path(args.verdicts) if args.verdicts else run_dir / PASS1_FILE, blind)
    retest_path = Path(args.retest) if args.retest else run_dir / PASS2_FILE
    pass2 = load_verdict_file(retest_path, blind)[0] if retest_path.exists() else None
    numbers = choose_anchor_rows(list(key.values()), pass1, pass2, size=args.rows)
    out = Path(args.out).resolve() if args.out else run_dir / ANCHOR_FILE
    _write_text(out, render_anchor_sheet(blind, numbers, title=run["run_id"]))
    _print({"rows": numbers, "out": str(out)})
    return 0


def _command_anchor_score(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    _run, blind, _key = load_run(run_dir)
    pass1, _ = load_verdict_file(Path(args.verdicts) if args.verdicts else run_dir / PASS1_FILE, blind)
    owner = parse_anchor_sheet(Path(args.sheet).read_text(encoding="utf-8"))
    report = agreement_report({k: v.verdict for k, v in pass1.items()}, owner)
    report["note"] = "hard rows chosen on purpose: agreement here is a lower bound, read the direction"
    _print(report)
    return 0


def _command_mix(args: argparse.Namespace) -> int:
    _print(mix_runs([Path(item) for item in args.runs], Path(args.out).resolve(), seed=args.seed))
    return 0


def _command_split(args: argparse.Namespace) -> int:
    _print(split_mixed_verdicts(Path(args.mix_dir).resolve(), Path(args.verdicts), output_name=args.output_name))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m derlem_worker.jury", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="tekduze orneklem + kor dosya + cevap anahtari (DB'ye yazmaz)")
    target = sample.add_mutually_exclusive_group(required=True)
    target.add_argument("--source-id", help="kaynak (DB'den YALNIZ okuma ile nesne yolu)")
    target.add_argument("--object", help="kaynak nesnesinin yolu (DB'siz)")
    sample.add_argument("--store-root", default="var/storage")
    sample.add_argument("--object-sha256")
    sample.add_argument("--language", default=None)
    sample.add_argument("--n", type=int, default=DEFAULT_SAMPLE_SIZE)
    sample.add_argument("--seed", type=int, required=True)
    sample.add_argument("--policy", default=DEFAULT_RULE_POLICY)
    sample.add_argument("--max-document-bytes", type=int, default=DEFAULT_MAX_DOCUMENT_BYTES)
    sample.add_argument("--out", required=True)
    sample.set_defaults(handler=_command_sample)

    judge = sub.add_parser("judge", help="model hakemi (anahtar ortamdan; butce zorunlu)")
    judge.add_argument("--run-dir", required=True)
    judge.add_argument("--no-retest", action="store_true")
    judge.set_defaults(handler=_command_judge)

    score = sub.add_parser("score", help="disaridan hukum dosyasi -> karar parquet + dort sayi")
    score.add_argument("--run-dir", required=True)
    score.add_argument("--verdicts", required=True, help="JSONL: no, hukum, tur, cop_nedeni, gerekce")
    score.add_argument("--retest", help="ayni satirlarin ikinci okumasi (test-tekrar)")
    score.add_argument("--judge-label", default="sonnet")
    score.add_argument("--judge-model", default=None)
    score.add_argument("--source-id-context", action="store_true", help="insan ret ve nufus PII'yi DB'den OKU")
    score.add_argument("--apply-db", action="store_true", help="sayilari kaynak kartina YAZ (veritabanina yazar)")
    score.set_defaults(handler=_command_score)

    anchor = sub.add_parser("anchor", help="kurucu capasi: 14-30 zor satir")
    anchor.add_argument("--run-dir", required=True)
    anchor.add_argument("--verdicts")
    anchor.add_argument("--retest")
    anchor.add_argument("--rows", type=int, default=20)
    anchor.add_argument("--out")
    anchor.set_defaults(handler=_command_anchor)

    anchor_score = sub.add_parser("anchor-score", help="kurucu sayfasi -> hakem-kurucu kappa")
    anchor_score.add_argument("--run-dir", required=True)
    anchor_score.add_argument("--sheet", required=True)
    anchor_score.add_argument("--verdicts")
    anchor_score.set_defaults(handler=_command_anchor_score)

    mix = sub.add_parser("mix", help="iki kosunun kor dosyasini tek karma dosyada birlestir")
    mix.add_argument("--runs", nargs="+", required=True)
    mix.add_argument("--out", required=True)
    mix.add_argument("--seed", type=int, required=True)
    mix.set_defaults(handler=_command_mix)

    split = sub.add_parser("split", help="karma hukum dosyasini kosulara geri dagit")
    split.add_argument("--mix-dir", required=True)
    split.add_argument("--verdicts", required=True)
    split.add_argument("--output-name", default="hukumler-karma.jsonl")
    split.set_defaults(handler=_command_split)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (JuryError, VerdictFileError, ImportManifestError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
