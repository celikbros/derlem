"""Atma raporu yanlis-atma denetimi (TASK-020).

`clean-candidate-rejections-v2` raporundan (temiz_aday_v3.md) sabit tohumla
katmanli bir denetim cetveli cikarir (`sheet`) ve doldurulmus cetvelden
gerekce basina ve toplamda bayt agirlikli yanlis-atma oranini %95 araligiyla
hesaplar (`score`).

Katman kurali: her kaydin katmani `reasons` listesindeki ILK (birincil)
gerekcedir. Bir satir birden cok gerekce tasiyabilir; listenin sirasi
`quality_filters._REASON_ORDER` ile sabittir, dolayisiyla katman atamasi
belirlenimcidir. Cetvelde `reasons` sutunu tum gerekceleri tasir.

Secim kurali: katman icindeki kayitlar
`sha256(f"{seed}:{sha256}:{source_ordinal}")` anahtarina gore siralanir ve ilk
min(sheet_size, katman buyuklugu) kayit alinir. Python'un rastgele sayi
ureticisine bagli degildir; ayni tohum ve ayni rapor ayni cetveli verir.

Rapor hicbir zaman degistirilmez; yalnizca okunur.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO

from derlem_worker.quality_filters import _REASON_ORDER


AUDIT_SHEET_VERSION = "clean-candidate-audit-sheet-v1"
DEFAULT_SEED = 20260919
DEFAULT_SHEET_SIZE = 50
DEFAULT_OUTPUT_DOC = Path("docs/atma_raporu_denetimi_v3.md")
# Rafin esigi: atilan baytin %10'undan fazlasi iyi metinse kural gevsetme konusulur.
FALSE_DROP_THRESHOLD = 0.10
Z_95 = 1.959963984540054

VERDICT_GOOD = "good"
VERDICT_CORRECT_DROP = "correct_drop"
VERDICT_UNSURE = "unsure"
ALLOWED_VERDICTS = (VERDICT_GOOD, VERDICT_CORRECT_DROP, VERDICT_UNSURE)

# Katman sirasi: 12 kalite gerekcesi (quality_filters ile ayni sira), sonra
# v3'un uc atma gerekcesi. Bilinmeyen bir gerekce cetvelde en sona, alfabetik gelir.
STRATUM_ORDER: tuple[str, ...] = tuple(_REASON_ORDER) + (
    "near_duplicate",
    "normalized_duplicate",
    "language_not_turkish",
)

SHEET_COLUMNS = (
    "sha256",
    "reasons",
    "char_count",
    "source_ordinal",
    "preview",
    "duplicate_of",
    "duplicate_of_preview",
    "verdict",
)
REASONS_SEPARATOR = "|"
_HEADER_PREFIX = "# "


@dataclass(frozen=True)
class RejectionRecord:
    sha256: str
    reasons: tuple[str, ...]
    char_count: int
    source_ordinal: int
    preview: str
    duplicate_of: int | None

    @property
    def stratum(self) -> str:
        return self.reasons[0]

    @property
    def row_key(self) -> tuple[str, int]:
        return (self.sha256, self.source_ordinal)


@dataclass(frozen=True)
class StratumTotals:
    """Tam rapordaki katman buyuklugu: kayit sayisi ve char_count toplami."""

    records: int
    chars: int


@dataclass(frozen=True)
class SheetHeader:
    version: str
    seed: int
    sheet_size: int
    report_path: str
    report_sha256: str
    report_records: int
    generated_at: str
    stratum_rule: str


@dataclass(frozen=True)
class SheetRow:
    sha256: str
    reasons: tuple[str, ...]
    char_count: int
    source_ordinal: int
    preview: str
    duplicate_of: int | None
    duplicate_of_preview: str
    verdict: str

    @property
    def stratum(self) -> str:
        return self.reasons[0]

    @property
    def row_key(self) -> tuple[str, int]:
        return (self.sha256, self.source_ordinal)


@dataclass(frozen=True)
class Sheet:
    header: SheetHeader
    stratum_totals: dict[str, StratumTotals]
    rows: tuple[SheetRow, ...]


@dataclass(frozen=True)
class StratumScore:
    reason: str
    report_records: int
    report_chars: int
    weight: float
    sampled: int
    good: int
    correct_drop: int
    unsure: int
    unfilled: int

    @property
    def judged(self) -> int:
        return self.good + self.correct_drop

    @property
    def rate(self) -> float | None:
        return None if self.judged == 0 else self.good / self.judged

    @property
    def interval(self) -> tuple[float, float] | None:
        return None if self.judged == 0 else wilson_interval(self.good, self.judged)

    @property
    def contribution(self) -> float | None:
        """Toplam orana katki: w_s * p_s (raporun tum baytlarina gore pay)."""
        rate = self.rate
        return None if rate is None else self.weight * rate


@dataclass(frozen=True)
class CharWeightedStratum:
    reason: str
    good_chars: int
    judged_chars: int

    @property
    def rate(self) -> float | None:
        return None if self.judged_chars == 0 else self.good_chars / self.judged_chars


@dataclass(frozen=True)
class Agreement:
    compared_rows: int
    agreeing_rows: int
    kappa: float | None

    @property
    def share(self) -> float | None:
        return None if self.compared_rows == 0 else self.agreeing_rows / self.compared_rows


@dataclass(frozen=True)
class ScoreResult:
    header: SheetHeader
    sheet_path: str
    sheet_sha256: str
    strata: tuple[StratumScore, ...]
    char_weighted: tuple[CharWeightedStratum, ...]
    overall_rate: float | None
    overall_interval: tuple[float, float] | None
    effective_n: float | None
    covered_weight: float
    overall_char_weighted_rate: float | None
    top_contributors: tuple[StratumScore, ...]
    agreement: Agreement | None
    second_sheet_path: str | None
    scored_at: str


# --- Rapor okuma --------------------------------------------------------------


def iter_rejection_records(path: Path) -> Iterator[RejectionRecord]:
    """JSONL raporu satir satir okur; eksik ya da bozuk alanlar hata verir."""
    with path.open("rb") as handle:
        for number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}: line {number}: invalid JSON ({error})") from None
            reasons = record.get("reasons")
            if not isinstance(reasons, list) or not reasons or not all(isinstance(item, str) for item in reasons):
                raise ValueError(f"{path}: line {number}: reasons missing or empty")
            sha256 = str(record.get("sha256", ""))
            if len(sha256) != 64:
                raise ValueError(f"{path}: line {number}: sha256 missing (record version must be v2)")
            duplicate_of = record.get("duplicate_of")
            yield RejectionRecord(
                sha256=sha256,
                reasons=tuple(reasons),
                char_count=int(record.get("char_count", 0)),
                source_ordinal=int(record["source_ordinal"]),
                preview=str(record.get("preview", "")),
                duplicate_of=(None if duplicate_of is None else int(duplicate_of)),
            )


def sha256_of_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stratum_sort_key(reason: str) -> tuple[int, str]:
    try:
        return (STRATUM_ORDER.index(reason), reason)
    except ValueError:
        return (len(STRATUM_ORDER), reason)


# --- Cetvel cikarma -----------------------------------------------------------


def selection_key(seed: int, record: RejectionRecord) -> str:
    return hashlib.sha256(f"{seed}:{record.sha256}:{record.source_ordinal}".encode("ascii")).hexdigest()


def draw_sheet(
    records: Iterable[RejectionRecord],
    *,
    seed: int,
    sheet_size: int,
    report_path: str,
    report_sha256: str,
    generated_at: str | None = None,
) -> Sheet:
    """Katman basina min(sheet_size, katman) kayit secer; satirlar katman
    sirasinda, katman icinde source_ordinal'a gore siralidir."""
    if sheet_size <= 0:
        raise ValueError("sheet_size must be positive")
    by_stratum: dict[str, list[RejectionRecord]] = {}
    preview_by_ordinal: dict[int, str] = {}
    total = 0
    for record in records:
        total += 1
        by_stratum.setdefault(record.stratum, []).append(record)
        preview_by_ordinal.setdefault(record.source_ordinal, record.preview)

    totals: dict[str, StratumTotals] = {}
    rows: list[SheetRow] = []
    for stratum in sorted(by_stratum, key=stratum_sort_key):
        members = by_stratum[stratum]
        totals[stratum] = StratumTotals(records=len(members), chars=sum(item.char_count for item in members))
        chosen = sorted(members, key=lambda item: (selection_key(seed, item), item.source_ordinal))[:sheet_size]
        for record in sorted(chosen, key=lambda item: (item.source_ordinal, item.sha256)):
            # Kopya atmalarinda partner (kalan satir) rapora girmez; yalnizca
            # partner de bir sekilde raporda varsa onizlemesi bulunur.
            partner_preview = ""
            if record.duplicate_of is not None:
                partner_preview = preview_by_ordinal.get(record.duplicate_of, "")
            rows.append(SheetRow(
                sha256=record.sha256,
                reasons=record.reasons,
                char_count=record.char_count,
                source_ordinal=record.source_ordinal,
                preview=record.preview,
                duplicate_of=record.duplicate_of,
                duplicate_of_preview=partner_preview,
                verdict="",
            ))
    header = SheetHeader(
        version=AUDIT_SHEET_VERSION,
        seed=seed,
        sheet_size=sheet_size,
        report_path=report_path,
        report_sha256=report_sha256,
        report_records=total,
        generated_at=(generated_at or datetime.now(UTC).isoformat(timespec="seconds")),
        stratum_rule="first reason in `reasons` (primary reason)",
    )
    return Sheet(header=header, stratum_totals=totals, rows=tuple(rows))


def _header_lines(sheet: Sheet) -> list[str]:
    header = sheet.header
    lines = [
        f"{_HEADER_PREFIX}version: {header.version}",
        f"{_HEADER_PREFIX}seed: {header.seed}",
        f"{_HEADER_PREFIX}sheet_size: {header.sheet_size}",
        f"{_HEADER_PREFIX}report_path: {header.report_path}",
        f"{_HEADER_PREFIX}report_sha256: {header.report_sha256}",
        f"{_HEADER_PREFIX}report_records: {header.report_records}",
        f"{_HEADER_PREFIX}generated_at: {header.generated_at}",
        f"{_HEADER_PREFIX}stratum_rule: {header.stratum_rule}",
        f"{_HEADER_PREFIX}allowed_verdicts: {' / '.join(ALLOWED_VERDICTS)}",
    ]
    for stratum in sorted(sheet.stratum_totals, key=stratum_sort_key):
        totals = sheet.stratum_totals[stratum]
        lines.append(f"{_HEADER_PREFIX}stratum: {stratum} records={totals.records} chars={totals.chars}")
    return lines


def _row_values(row: SheetRow) -> list[str]:
    return [
        row.sha256,
        REASONS_SEPARATOR.join(row.reasons),
        str(row.char_count),
        str(row.source_ordinal),
        row.preview,
        ("" if row.duplicate_of is None else str(row.duplicate_of)),
        row.duplicate_of_preview,
        row.verdict,
    ]


def write_sheet_csv(sheet: Sheet, path: Path) -> None:
    """UTF-8 (BOM'lu; Excel Turkce harfleri dogru acsin). Ust bilgi satirlari
    '# ' ile baslar; puanlayici bunlari atlar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        for line in _header_lines(sheet):
            handle.write(line + "\r\n")
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(SHEET_COLUMNS)
        for row in sheet.rows:
            writer.writerow(_row_values(row))


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def write_sheet_markdown(sheet: Sheet, path: Path) -> None:
    header = sheet.header
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Atma raporu denetim cetveli (v3)",
        "",
        f"- Surum: `{header.version}`",
        f"- Tohum: `{header.seed}` - katman basina en cok {header.sheet_size} kayit",
        f"- Rapor: `{header.report_path}`",
        f"- Rapor SHA256: `{header.report_sha256}` ({header.report_records} kayit)",
        f"- Uretim: {header.generated_at}",
        f"- Katman kurali: {header.stratum_rule}",
        f"- Karar degerleri: {' / '.join(f'`{item}`' for item in ALLOWED_VERDICTS)} (CSV'deki `verdict` sutununa yazilir)",
        "",
        "| Katman | Rapordaki kayit | Rapordaki karakter | Cetveldeki satir |",
        "|---|---:|---:|---:|",
    ]
    counts: dict[str, int] = {}
    for row in sheet.rows:
        counts[row.stratum] = counts.get(row.stratum, 0) + 1
    for stratum in sorted(sheet.stratum_totals, key=stratum_sort_key):
        totals = sheet.stratum_totals[stratum]
        lines.append(f"| `{stratum}` | {totals.records} | {totals.chars} | {counts.get(stratum, 0)} |")
    lines.append(f"| **Toplam** | {header.report_records} | {sum(item.chars for item in sheet.stratum_totals.values())} | {len(sheet.rows)} |")

    current: str | None = None
    for row in sheet.rows:
        if row.stratum != current:
            current = row.stratum
            lines += [
                "",
                f"## `{current}` ({counts[current]} satir)",
                "",
                "| # | sha256 | source_ordinal | char_count | reasons | preview | duplicate_of | verdict |",
                "|---:|---|---:|---:|---|---|---:|---|",
            ]
            index = 0
        index += 1
        duplicate_of = "" if row.duplicate_of is None else str(row.duplicate_of)
        partner = f" (partner: {_markdown_cell(row.duplicate_of_preview)})" if row.duplicate_of_preview else ""
        lines.append(
            f"| {index} | `{row.sha256}` | {row.source_ordinal} | {row.char_count} | "
            f"`{REASONS_SEPARATOR.join(row.reasons)}` | {_markdown_cell(row.preview)}{partner} | {duplicate_of} | |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


# --- Cetvel okuma -------------------------------------------------------------


def _parse_header(lines: list[str], path: Path) -> tuple[SheetHeader, dict[str, StratumTotals]]:
    fields: dict[str, str] = {}
    totals: dict[str, StratumTotals] = {}
    for line in lines:
        body = line[len(_HEADER_PREFIX):].strip()
        key, _, value = body.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "stratum":
            name, *parts = value.split()
            numbers = dict(part.split("=", 1) for part in parts)
            totals[name] = StratumTotals(records=int(numbers["records"]), chars=int(numbers["chars"]))
        else:
            fields[key] = value
    try:
        header = SheetHeader(
            version=fields["version"],
            seed=int(fields["seed"]),
            sheet_size=int(fields["sheet_size"]),
            report_path=fields["report_path"],
            report_sha256=fields["report_sha256"],
            report_records=int(fields["report_records"]),
            generated_at=fields["generated_at"],
            stratum_rule=fields["stratum_rule"],
        )
    except KeyError as error:
        raise ValueError(f"{path}: sheet header is missing {error}") from None
    if not totals:
        raise ValueError(f"{path}: sheet header has no stratum totals")
    return header, totals


def normalize_verdict(value: str) -> str:
    return value.strip().lower()


def read_sheet_csv(path: Path) -> Sheet:
    """Doldurulmus (ya da bos) cetveli okur; bilinmeyen karar degerini reddeder."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return _read_sheet(handle, path)


def _read_sheet(handle: TextIO, path: Path) -> Sheet:
    header_lines: list[str] = []
    body: list[str] = []
    for line in handle:
        # Ust bilgi bolumu: '# ' satirlari; arada kalan bos satirlar (editorun
        # satir sonu cevirisi) atlanir. Ilk sutun satirindan sonra hepsi govdedir.
        if not body and line.startswith(_HEADER_PREFIX):
            header_lines.append(line.rstrip("\r\n"))
        elif not body and not line.strip():
            continue
        else:
            body.append(line)
    header, totals = _parse_header(header_lines, path)
    reader = csv.reader(body)
    columns = next(reader, None)
    if columns is None or tuple(columns) != SHEET_COLUMNS:
        raise ValueError(f"{path}: unexpected sheet columns {columns!r}; expected {list(SHEET_COLUMNS)!r}")
    rows: list[SheetRow] = []
    invalid: list[str] = []
    seen: set[tuple[str, int]] = set()
    for number, values in enumerate(reader, 1):
        if not values or all(not item.strip() for item in values):
            continue
        if len(values) != len(SHEET_COLUMNS):
            raise ValueError(f"{path}: data row {number} has {len(values)} columns; expected {len(SHEET_COLUMNS)}")
        record = dict(zip(SHEET_COLUMNS, values))
        verdict = normalize_verdict(record["verdict"])
        if verdict and verdict not in ALLOWED_VERDICTS:
            invalid.append(f"row {number} ({record['sha256'][:12]}...): {record['verdict']!r}")
        duplicate_of = record["duplicate_of"].strip()
        row = SheetRow(
            sha256=record["sha256"].strip(),
            reasons=tuple(record["reasons"].split(REASONS_SEPARATOR)),
            char_count=int(record["char_count"]),
            source_ordinal=int(record["source_ordinal"]),
            preview=record["preview"],
            duplicate_of=(int(duplicate_of) if duplicate_of else None),
            duplicate_of_preview=record["duplicate_of_preview"],
            verdict=verdict,
        )
        if row.row_key in seen:
            raise ValueError(f"{path}: duplicate row {row.sha256} / {row.source_ordinal}")
        seen.add(row.row_key)
        rows.append(row)
    if invalid:
        allowed = ", ".join(ALLOWED_VERDICTS)
        raise ValueError(f"{path}: unknown verdicts (allowed: {allowed}, or empty):\n  " + "\n  ".join(invalid))
    return Sheet(header=header, stratum_totals=totals, rows=tuple(rows))


# --- Puanlama -----------------------------------------------------------------


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson skor araligi (binom oran icin %95)."""
    if trials <= 0:
        raise ValueError("trials must be positive")
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    # Uclarda kayan nokta kalintisi (0 basari -> 7e-18) yerine tam 0 / 1.
    low = 0.0 if successes <= 0 else max(0.0, centre - half)
    high = 1.0 if successes >= trials else min(1.0, centre + half)
    return (low, high)


def score_strata(sheet: Sheet) -> tuple[StratumScore, ...]:
    total_chars = sum(item.chars for item in sheet.stratum_totals.values())
    tallies: dict[str, dict[str, int]] = {
        stratum: {"sampled": 0, VERDICT_GOOD: 0, VERDICT_CORRECT_DROP: 0, VERDICT_UNSURE: 0, "unfilled": 0}
        for stratum in sheet.stratum_totals
    }
    for row in sheet.rows:
        if row.stratum not in tallies:
            raise ValueError(f"sheet row {row.sha256} has stratum {row.stratum!r} that is not in the header")
        tally = tallies[row.stratum]
        tally["sampled"] += 1
        tally[row.verdict or "unfilled"] += 1
    scores = []
    for stratum in sorted(sheet.stratum_totals, key=stratum_sort_key):
        totals = sheet.stratum_totals[stratum]
        tally = tallies[stratum]
        scores.append(StratumScore(
            reason=stratum,
            report_records=totals.records,
            report_chars=totals.chars,
            weight=(totals.chars / total_chars if total_chars else 0.0),
            sampled=tally["sampled"],
            good=tally[VERDICT_GOOD],
            correct_drop=tally[VERDICT_CORRECT_DROP],
            unsure=tally[VERDICT_UNSURE],
            unfilled=tally["unfilled"],
        ))
    return tuple(scores)


def char_weighted_strata(sheet: Sheet) -> tuple[CharWeightedStratum, ...]:
    """Katman icinde karakter agirlikli oran: iyi satirlarin karakteri /
    karara baglanmis satirlarin karakteri."""
    good: dict[str, int] = {}
    judged: dict[str, int] = {}
    for row in sheet.rows:
        if row.verdict not in (VERDICT_GOOD, VERDICT_CORRECT_DROP):
            continue
        judged[row.stratum] = judged.get(row.stratum, 0) + row.char_count
        if row.verdict == VERDICT_GOOD:
            good[row.stratum] = good.get(row.stratum, 0) + row.char_count
    return tuple(
        CharWeightedStratum(reason=stratum, good_chars=good.get(stratum, 0), judged_chars=judged.get(stratum, 0))
        for stratum in sorted(sheet.stratum_totals, key=stratum_sort_key)
    )


def overall_false_drop(strata: Iterable[StratumScore]) -> tuple[float | None, tuple[float, float] | None, float | None, float]:
    """Katman agirlikli toplam oran: sum(w_s * p_s) / sum(w_s), w_s = katmanin
    rapordaki karakter payi; yalnizca karara baglanmis satiri olan katmanlar
    girer. Aralik: Wilson, etkin orneklem n_eff = 1 / sum((w_s/W)^2 / n_s)
    (Kish) ile. Donus: (oran, aralik, n_eff, kapsanan agirlik)."""
    covered = [item for item in strata if item.judged > 0]
    weight = sum(item.weight for item in covered)
    if not covered or weight <= 0:
        return None, None, None, 0.0
    rate = sum(item.weight * (item.rate or 0.0) for item in covered) / weight
    effective_n = 1.0 / sum((item.weight / weight) ** 2 / item.judged for item in covered)
    return rate, wilson_interval(rate * effective_n, effective_n), effective_n, weight


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    categories = {item for pair in pairs for item in pair}
    expected = sum(
        (sum(1 for a, _ in pairs if a == category) / n) * (sum(1 for _, b in pairs if b == category) / n)
        for category in categories
    )
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else 0.0
    return (observed - expected) / (1 - expected)


def compute_agreement(first: Sheet, second: Sheet) -> Agreement:
    """Iki cetvelin ortak satirlarinda (ikisinde de karar var) uyum payi ve
    Cohen kappa. Ikinci cetvelin her satiri birincide bulunmali."""
    first_rows = {row.row_key: row for row in first.rows}
    missing = [row for row in second.rows if row.row_key not in first_rows]
    if missing:
        raise ValueError(
            f"second sheet has {len(missing)} row(s) that are not in the first sheet "
            f"(first: {missing[0].sha256} / {missing[0].source_ordinal})"
        )
    pairs = [
        (first_rows[row.row_key].verdict, row.verdict)
        for row in second.rows
        if row.verdict and first_rows[row.row_key].verdict
    ]
    return Agreement(
        compared_rows=len(pairs),
        agreeing_rows=sum(1 for a, b in pairs if a == b),
        kappa=cohen_kappa(pairs),
    )


def score_sheet(
    sheet: Sheet,
    *,
    sheet_path: str,
    sheet_sha256: str,
    second: Sheet | None = None,
    second_path: str | None = None,
    scored_at: str | None = None,
) -> ScoreResult:
    if not any(row.verdict for row in sheet.rows):
        raise ValueError("the sheet has no verdicts; nothing to score")
    strata = score_strata(sheet)
    char_weighted = char_weighted_strata(sheet)
    rate, interval, effective_n, covered = overall_false_drop(strata)
    judged_chars = sum(item.judged_chars for item in char_weighted)
    weighted_chars_rate: float | None = None
    if judged_chars:
        # Katman icinde karakter agirlikli, katmanlar arasinda rapor payi agirlikli.
        by_reason = {item.reason: item for item in char_weighted}
        covered_strata = [item for item in strata if item.judged > 0]
        weight = sum(item.weight for item in covered_strata)
        weighted_chars_rate = sum(
            item.weight * (by_reason[item.reason].rate or 0.0) for item in covered_strata
        ) / weight
    ranked = sorted(
        (item for item in strata if item.contribution is not None and item.contribution > 0),
        key=lambda item: (-(item.contribution or 0.0), stratum_sort_key(item.reason)),
    )
    agreement = compute_agreement(sheet, second) if second is not None else None
    return ScoreResult(
        header=sheet.header,
        sheet_path=sheet_path,
        sheet_sha256=sheet_sha256,
        strata=strata,
        char_weighted=char_weighted,
        overall_rate=rate,
        overall_interval=interval,
        effective_n=effective_n,
        covered_weight=covered,
        overall_char_weighted_rate=weighted_chars_rate,
        top_contributors=tuple(ranked[:3]),
        agreement=agreement,
        second_sheet_path=second_path,
        scored_at=(scored_at or datetime.now(UTC).isoformat(timespec="seconds")),
    )


# --- Belge --------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "-" if value is None else f"%{value * 100:.2f}".replace(".", ",")


def _interval(value: tuple[float, float] | None) -> str:
    return "-" if value is None else f"{_pct(value[0])} - {_pct(value[1])}"


def render_score_markdown(result: ScoreResult) -> str:
    header = result.header
    lines = [
        "# Atma raporu denetimi v3 - yanlis-atma orani (TASK-020)",
        "",
        f"**Puanlama:** {result.scored_at} · **Cetvel:** `{result.sheet_path}` (SHA256 `{result.sheet_sha256}`) ·",
        f"**Rapor:** `{header.report_path}` (SHA256 `{header.report_sha256}`, {header.report_records} kayit) ·",
        f"**Tohum:** `{header.seed}` · katman basina en cok {header.sheet_size} kayit · katman kurali: {header.stratum_rule}.",
        "",
        "Bu belge `derlem_worker.clean_candidate_audit score` tarafindan yazilir; elle duzenlenen",
        "bolumler bir sonraki puanlamada silinir. Karar ve takip notlari gorev kartina yazilir.",
        "",
        "## Yontem",
        "",
        "- Katman = kaydin `reasons` listesindeki ilk gerekce. Katman agirligi `w_s` = katmanin",
        "  rapordaki `char_count` toplaminin tum raporun toplamina orani (raporda bayt yok; karakter",
        "  sayisi baytin yerine gecer).",
        "- Katman orani `p_s` = `good` / (`good` + `correct_drop`); `unsure` ve bos satirlar payda disi.",
        "  Aralik: Wilson skor araligi, %95.",
        "- Toplam oran = sum(`w_s` * `p_s`) / sum(`w_s`), yalnizca karara baglanmis satiri olan katmanlar",
        "  uzerinden. Aralik: Wilson, etkin orneklem `n_eff` = 1 / sum((`w_s`/W)^2 / `n_s`) (Kish).",
        "- Katki = `w_s` * `p_s`: katmanin toplam yanlis-atma payina getirdigi pay; en yuksek uc katman",
        "  asagida siralanir.",
        f"- Rafin esigi: toplam oran > {_pct(FALSE_DROP_THRESHOLD)} ise kural gevsetme konusulur.",
        "",
        "## Gerekce basina",
        "",
        "| Gerekce | Rapor kayit | Rapor karakter | Agirlik | Cetvel | good | correct_drop | unsure | bos | Oran | %95 aralik | Katki | Karakter agirlikli oran |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    by_reason = {item.reason: item for item in result.char_weighted}
    for item in result.strata:
        lines.append(
            f"| `{item.reason}` | {item.report_records} | {item.report_chars} | {_pct(item.weight)} | {item.sampled} | "
            f"{item.good} | {item.correct_drop} | {item.unsure} | {item.unfilled} | {_pct(item.rate)} | "
            f"{_interval(item.interval)} | {_pct(item.contribution)} | {_pct(by_reason[item.reason].rate)} |"
        )
    total_sampled = sum(item.sampled for item in result.strata)
    total_good = sum(item.good for item in result.strata)
    total_correct = sum(item.correct_drop for item in result.strata)
    total_unsure = sum(item.unsure for item in result.strata)
    total_unfilled = sum(item.unfilled for item in result.strata)
    lines += [
        "",
        "## Toplam",
        "",
        "| Olcu | Deger |",
        "|---|---|",
        f"| Cetvel satiri | {total_sampled} (good {total_good} · correct_drop {total_correct} · unsure {total_unsure} · bos {total_unfilled}) |",
        f"| Kapsanan agirlik (karari olan katmanlar) | {_pct(result.covered_weight)} |",
        f"| **Bayt agirlikli yanlis-atma orani** | **{_pct(result.overall_rate)}** |",
        f"| %95 aralik (Wilson, n_eff = {'-' if result.effective_n is None else f'{result.effective_n:.1f}'.replace('.', ',')}) | {_interval(result.overall_interval)} |",
        f"| Karakter agirlikli oran (katman icinde de karakterle) | {_pct(result.overall_char_weighted_rate)} |",
    ]
    if result.overall_rate is not None:
        above = result.overall_rate > FALSE_DROP_THRESHOLD
        low, high = result.overall_interval or (0.0, 0.0)
        if high <= FALSE_DROP_THRESHOLD:
            certainty = "aralik tumuyle esigin altinda"
        elif low > FALSE_DROP_THRESHOLD:
            certainty = "aralik tumuyle esigin ustunde"
        else:
            certainty = "aralik esigi kapsiyor; kesin degil"
        lines += [
            f"| {_pct(FALSE_DROP_THRESHOLD)} esigi ile karsilastirma | {'**ustunde**' if above else 'altinda'} ({certainty}) |",
        ]
    lines += ["", "## En yuksek katkili uc gerekce", ""]
    if result.top_contributors:
        lines += ["| Sira | Gerekce | Oran | Katki |", "|---:|---|---:|---:|"]
        for rank, item in enumerate(result.top_contributors, 1):
            lines.append(f"| {rank} | `{item.reason}` | {_pct(item.rate)} | {_pct(item.contribution)} |")
    else:
        lines.append("Hicbir katmanda `good` karari yok.")
    lines += ["", "## Degerlendirici uyumu", ""]
    if result.agreement is None:
        lines.append("Ikinci cetvel verilmedi; uyum sayisi yok.")
    else:
        agreement = result.agreement
        kappa = "-" if agreement.kappa is None else f"{agreement.kappa:.3f}".replace(".", ",")
        lines += [
            f"Ikinci cetvel: `{result.second_sheet_path}`.",
            "",
            "| Olcu | Deger |",
            "|---|---|",
            f"| Ikisinde de karar olan satir | {agreement.compared_rows} |",
            f"| Ayni karar | {agreement.agreeing_rows} ({_pct(agreement.share)}) |",
            f"| Cohen kappa | {kappa} |",
        ]
    lines += [
        "",
        "## Karar",
        "",
        "Kural degisikligi karari ve varsa takip karti gorev kartina (TASK-020) yazilir; bu belge",
        "yalnizca olcumu tasir.",
    ]
    return "\n".join(lines) + "\n"


# --- CLI ----------------------------------------------------------------------


def _run_sheet(args: argparse.Namespace) -> None:
    report_path: Path = args.report.resolve(strict=True)
    report_sha256 = sha256_of_file(report_path)
    if args.expect_report_sha256 and args.expect_report_sha256.lower() != report_sha256:
        raise SystemExit(f"report SHA256 mismatch: expected {args.expect_report_sha256}, got {report_sha256}")
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.stem or f"{report_path.name.split('.')[0]}_audit_sheet_seed{args.seed}"
    csv_path = output_dir / f"{stem}.csv"
    md_path = output_dir / f"{stem}.md"
    for target in (csv_path, md_path):
        if target.exists() and not args.force:
            raise SystemExit(f"Refusing to overwrite existing file without --force: {target}")
    sheet = draw_sheet(
        iter_rejection_records(report_path),
        seed=args.seed,
        sheet_size=args.sheet_size,
        report_path=str(report_path),
        report_sha256=report_sha256,
    )
    write_sheet_csv(sheet, csv_path)
    write_sheet_markdown(sheet, md_path)
    summary = {
        "csv": str(csv_path),
        "markdown": str(md_path),
        "csv_sha256": sha256_of_file(csv_path),
        "rows": len(sheet.rows),
        "seed": args.seed,
        "sheet_size": args.sheet_size,
        "report_sha256": report_sha256,
        "report_records": sheet.header.report_records,
        "strata": {
            stratum: {"records": totals.records, "chars": totals.chars}
            for stratum, totals in sheet.stratum_totals.items()
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _run_score(args: argparse.Namespace) -> None:
    sheet_path: Path = args.sheet.resolve(strict=True)
    sheet = read_sheet_csv(sheet_path)
    second: Sheet | None = None
    second_path: str | None = None
    if args.second is not None:
        second_path = str(args.second.resolve(strict=True))
        second = read_sheet_csv(Path(second_path))
    result = score_sheet(
        sheet,
        sheet_path=str(sheet_path),
        sheet_sha256=sha256_of_file(sheet_path),
        second=second,
        second_path=second_path,
    )
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_score_markdown(result), encoding="utf-8", newline="\n")
    summary = {
        "out": str(out),
        "overall_rate": result.overall_rate,
        "overall_interval": result.overall_interval,
        "effective_n": result.effective_n,
        "covered_weight": result.covered_weight,
        "top_contributors": [item.reason for item in result.top_contributors],
        "agreement": (
            None if result.agreement is None
            else {"compared": result.agreement.compared_rows, "share": result.agreement.share, "kappa": result.agreement.kappa}
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Rejection-report false-drop audit: stratified sheet and byte-weighted scorer")
    commands = parser.add_subparsers(dest="command", required=True)

    sheet = commands.add_parser("sheet", help="Draw a fixed-seed stratified audit sheet (CSV + Markdown) from a rejections JSONL")
    sheet.add_argument("--report", type=Path, required=True, help="Path to the *.rejections.jsonl report (read only)")
    sheet.add_argument("--output-dir", type=Path, required=True, help="Directory for the sheet files (keep it under var/)")
    sheet.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Selection seed (default {DEFAULT_SEED})")
    sheet.add_argument("--sheet-size", type=int, default=DEFAULT_SHEET_SIZE, help="Rows per stratum (default 50)")
    sheet.add_argument("--stem", help="File stem for the CSV and Markdown outputs")
    sheet.add_argument("--expect-report-sha256", help="Refuse to run if the report SHA256 differs")
    sheet.add_argument("--force", action="store_true", help="Overwrite existing sheet files")
    sheet.set_defaults(handler=_run_sheet)

    score = commands.add_parser("score", help="Score a filled sheet and write the Markdown result document")
    score.add_argument("--sheet", type=Path, required=True, help="Filled sheet CSV (verdict column: good / correct_drop / unsure)")
    score.add_argument("--second", type=Path, help="Second reviewer's sheet with the same rows (adds the agreement number)")
    score.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_DOC, help=f"Markdown output (default {DEFAULT_OUTPUT_DOC})")
    score.set_defaults(handler=_run_score)

    args = parser.parse_args(argv)
    if args.command == "sheet" and args.sheet_size <= 0:
        parser.error("--sheet-size must be positive")
    try:
        args.handler(args)
    except ValueError as error:
        raise SystemExit(f"error: {error}") from None


if __name__ == "__main__":
    main()
