"""Hakem hukumlerinin puanlanmasi (TASK-047): Wilson araligi, uyum, Cohen kappa,
hukum dosyasi okuma ve kurucu capasi sayfasi.

``var/olcum-2026-09-21/task-040-yeni-tutulanlar-siki/puanla.py`` ve
``var/olcum-2026-09-21/juri/kor_girdi_hazirla.py`` desenlerinin modul hali:

- hukum sozlugu ``kalsin`` / ``cop`` / ``emin degilim``; kart karari geregi
  ``emin degilim`` COP tarafinda sayilir (2026-10-04 elle olcumu: HQ %43 = 39 cop
  + 4 emin degilim, v5 %53 = 49 + 4);
- Wilson %95 (z = 1.959963985);
- kappa ikili (cop+emin degilim / kalsin) ve uc sinifli ayri raporlanir.

Bu modul veritabanina ve ag'a dokunmaz; saf islevlerdir.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

WILSON_Z = 1.959963985

VERDICT_KEEP = "kalsin"
VERDICT_JUNK = "cop"
VERDICT_UNSURE = "emin degilim"
JURY_VERDICTS = (VERDICT_KEEP, VERDICT_JUNK, VERDICT_UNSURE)
# Sikı korpus: emin degilim cop tarafinda.
JUNK_SIDE = frozenset({VERDICT_JUNK, VERDICT_UNSURE})

# derlem.decision.v1 hukum sozlugune esleme (document_record.VERDICTS).
DECISION_VERDICT = {VERDICT_KEEP: "pass", VERDICT_JUNK: "reject", VERDICT_UNSURE: "flag"}

GENRES = (
    "haber", "ansiklopedi", "kose-deneme", "blog", "forum", "teknik-rehber", "akademik",
    "resmi-idari", "din", "edebiyat", "sozluk", "urun-ticari", "diger",
)
JUNK_REASONS = (
    "seo-ticari", "makine-cevirisi", "menu-spot", "bozuk-karakter", "yetiskin-bahis",
    "liste-katalog", "anlamsiz", "enjekte", "forum-yigini", "diger",
)

_VERDICT_ALIASES = {
    "kalsin": VERDICT_KEEP,
    "kal": VERDICT_KEEP,
    "keep": VERDICT_KEEP,
    "ok_to_keep": VERDICT_KEEP,
    "cop": VERDICT_JUNK,
    "com": VERDICT_JUNK,
    "garbage": VERDICT_JUNK,
    "junk": VERDICT_JUNK,
    "emin degilim": VERDICT_UNSURE,
    "emin_degilim": VERDICT_UNSURE,
    "unsure": VERDICT_UNSURE,
}


class VerdictFileError(ValueError):
    pass


def fold(value: str) -> str:
    """Turkce harfleri ASCII'ye katlar, kucuk harf, kenar bosluksuz."""
    text = value.strip().lower()
    for source, target in (("ı", "i"), ("ğ", "g"), ("ş", "s"), ("ç", "c"), ("ö", "o"), ("ü", "u"), ("â", "a"), ("î", "i"), ("û", "u")):
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKD", text)
    return "".join(character for character in text if not unicodedata.combining(character))


def normalize_verdict(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    folded = re.sub(r"\s+", " ", fold(value))
    return _VERDICT_ALIASES.get(folded)


def wilson(successes: int, total: int, z: float = WILSON_Z) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 1.0)
    if successes < 0 or successes > total:
        raise ValueError("successes must be within [0, total]")
    phat = successes / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def rate_with_interval(successes: int, total: int) -> dict[str, Any]:
    low, high = wilson(successes, total)
    return {
        "count": successes,
        "n": total,
        "rate": (successes / total) if total else None,
        "low": low if total else None,
        "high": high if total else None,
        "interval": "wilson95",
    }


def cohen_kappa(left: Sequence[str], right: Sequence[str]) -> float | None:
    """Iki etiket dizisi icin Cohen kappa; beklenen uyum 1 ise None (tanimsiz)."""
    if len(left) != len(right):
        raise ValueError("label sequences must have the same length")
    total = len(left)
    if total == 0:
        return None
    observed = sum(1 for a, b in zip(left, right) if a == b) / total
    labels = set(left) | set(right)
    expected = sum((left.count(label) / total) * (right.count(label) / total) for label in labels)
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def binary_label(verdict: str) -> str:
    return "junk" if verdict in JUNK_SIDE else "keep"


def agreement_report(left: Mapping[int, str], right: Mapping[int, str]) -> dict[str, Any]:
    """Ayni satirlarda iki hukum kumesinin uyumu (test-tekrar ya da hakem-kurucu)."""
    shared = sorted(set(left) & set(right))
    a = [left[number] for number in shared]
    b = [right[number] for number in shared]
    binary_a = [binary_label(value) for value in a]
    binary_b = [binary_label(value) for value in b]
    n = len(shared)
    return {
        "n": n,
        "agreement_3class": (sum(1 for x, y in zip(a, b) if x == y) / n) if n else None,
        "kappa_3class": cohen_kappa(a, b),
        "agreement_binary": (sum(1 for x, y in zip(binary_a, binary_b) if x == y) / n) if n else None,
        "kappa_binary": cohen_kappa(binary_a, binary_b),
        "disagreements": [number for number, x, y in zip(shared, a, b) if x != y],
    }


@dataclass(frozen=True)
class Verdict:
    no: int
    verdict: str
    genre: str
    junk_reason: str
    rationale: str

    @property
    def decision_reason(self) -> str:
        # derlem.decision.v1 ``reason``: "tur/cop_nedeni" (kalsin'da cop_nedeni bos).
        return f"{self.genre}/{self.junk_reason}"

    def to_json(self) -> dict[str, Any]:
        return {"no": self.no, "hukum": self.verdict, "tur": self.genre, "cop_nedeni": self.junk_reason, "gerekce": self.rationale}


def parse_verdict_object(value: Mapping[str, Any], *, no: int | None = None) -> Verdict:
    """Tek hukum nesnesi (model cevabi ya da hukum dosyasi satiri)."""
    number = no if no is not None else value.get("no")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise VerdictFileError(f"verdict row needs a positive integer 'no': {value!r}")
    verdict = normalize_verdict(value.get("hukum"))
    if verdict is None:
        raise VerdictFileError(f"row {number}: unknown verdict {value.get('hukum')!r} (kalsin / cop / emin degilim)")
    genre = fold(str(value.get("tur") or "diger")).replace(" ", "-") or "diger"
    junk_reason = fold(str(value.get("cop_nedeni") or "")).replace(" ", "-")
    if verdict == VERDICT_KEEP:
        junk_reason = ""
    rationale = str(value.get("gerekce") or "").strip()
    return Verdict(no=number, verdict=verdict, genre=genre, junk_reason=junk_reason, rationale=rationale)


def load_verdict_file(path: Path, valid_numbers: Iterable[int]) -> tuple[dict[int, Verdict], list[int]]:
    """JSONL hukum dosyasi -> (no -> Verdict, eksik no listesi).

    Bilinmeyen ``no`` ve ayni ``no``nun iki kez gelmesi hatadir (yanlis dosya
    eslesmesi sessizce puanlanmaz); eksik satir hata degildir, raporlanir.
    """
    valid = set(valid_numbers)
    verdicts: dict[int, Verdict] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise VerdictFileError(f"{path.name}:{line_number}: not JSON") from error
        if not isinstance(value, dict):
            raise VerdictFileError(f"{path.name}:{line_number}: verdict row must be an object")
        verdict = parse_verdict_object(value)
        if verdict.no not in valid:
            raise VerdictFileError(f"{path.name}:{line_number}: no {verdict.no} is not in the blind file")
        if verdict.no in verdicts:
            raise VerdictFileError(f"{path.name}:{line_number}: no {verdict.no} appears twice")
        verdicts[verdict.no] = verdict
    missing = sorted(valid - set(verdicts))
    return verdicts, missing


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.S)


def parse_model_answer(text: str, no: int) -> Verdict:
    """Model cevabindan tek JSON nesnesini cikarir (kod blogu icinde olabilir)."""
    match = _JSON_OBJECT_RE.search(text or "")
    if match is None:
        raise VerdictFileError(f"row {no}: model answer has no JSON object")
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise VerdictFileError(f"row {no}: model answer is not valid JSON") from error
    if not isinstance(value, dict):
        raise VerdictFileError(f"row {no}: model answer must be a JSON object")
    return parse_verdict_object(value, no=no)


def junk_numbers(verdicts: Mapping[int, Verdict], expected: int) -> dict[str, Any]:
    """Hakem cop orani: (cop + emin degilim) / hukum verilen satir, Wilson %95."""
    counts = {label: 0 for label in JURY_VERDICTS}
    reasons: dict[str, int] = {}
    genres: dict[str, int] = {}
    for verdict in verdicts.values():
        counts[verdict.verdict] += 1
        genres[verdict.genre] = genres.get(verdict.genre, 0) + 1
        if verdict.verdict in JUNK_SIDE and verdict.junk_reason:
            reasons[verdict.junk_reason] = reasons.get(verdict.junk_reason, 0) + 1
    judged = sum(counts.values())
    junk = counts[VERDICT_JUNK] + counts[VERDICT_UNSURE]
    result = rate_with_interval(junk, judged)
    result.update({
        "counts": counts,
        "missing": expected - judged,
        "strict_cop_only": rate_with_interval(counts[VERDICT_JUNK], judged),
        "junk_reasons": dict(sorted(reasons.items(), key=lambda item: (-item[1], item[0]))),
        "genres": dict(sorted(genres.items(), key=lambda item: (-item[1], item[0]))),
    })
    return result


# --------------------------------------------------------------------------
# Kurucu capasi: 14-30 satirlik "zor satirlar" sayfasi (rafin bicimi)
# --------------------------------------------------------------------------

ANCHOR_MIN_ROWS = 14
ANCHOR_MAX_ROWS = 30
ANCHOR_PREVIEW_CHARS = 900
_ANCHOR_BLOCK_RE = re.compile(
    r"^## (\d+)\. `juri no (\d+)`[^\n]*\n\n```text\n.*?\n```\n\nHukum:([^\n]*)\n",
    re.S | re.M,
)


def choose_anchor_rows(
    rows: Sequence[Mapping[str, Any]],
    pass1: Mapping[int, Verdict],
    pass2: Mapping[int, Verdict] | None,
    *,
    size: int = 20,
) -> list[int]:
    """Zor satirlari secer; sira belirlenimcidir (blind ``no`` sirasi).

    Oncelik: (1) iki gecisin ayristigi satirlar, (2) ``emin degilim``,
    (3) kural-hakem ayrismasi (kural atiyor / hakem kalsin ya da tersi),
    (4) kalan yer iki hukum sinifindan en uzun belgelerle dengeli doldurulur.
    Sayfa kasitli olarak zor satirlardan yapildigi icin uyumu NUFUSUN
    uyumundan dusuktur; kappa yalniz yon gostergesidir.
    """
    size = max(ANCHOR_MIN_ROWS, min(ANCHOR_MAX_ROWS, size))
    by_no = {int(row["no"]): row for row in rows}
    chosen: list[int] = []

    def add(numbers: Iterable[int]) -> None:
        for number in sorted(numbers):
            if len(chosen) >= size:
                return
            if number not in chosen and number in by_no:
                chosen.append(number)

    if pass2:
        add(number for number, verdict in pass1.items() if number in pass2 and pass2[number].verdict != verdict.verdict)
    add(number for number, verdict in pass1.items() if verdict.verdict == VERDICT_UNSURE)
    add(
        number for number, verdict in pass1.items()
        if bool(by_no.get(number, {}).get("rule_drop")) != (verdict.verdict in JUNK_SIDE)
    )
    if len(chosen) < size:
        keeps = sorted((n for n, v in pass1.items() if v.verdict == VERDICT_KEEP and n not in chosen),
                       key=lambda n: (-int(by_no[n].get("char_count_original") or 0), n))
        junks = sorted((n for n, v in pass1.items() if v.verdict in JUNK_SIDE and n not in chosen),
                       key=lambda n: (-int(by_no[n].get("char_count_original") or 0), n))
        while len(chosen) < size and (keeps or junks):
            for pool in (junks, keeps):
                if pool and len(chosen) < size:
                    chosen.append(pool.pop(0))
    return sorted(chosen)


def render_anchor_sheet(blind_rows: Mapping[int, Mapping[str, Any]], numbers: Sequence[int], *, title: str) -> str:
    """Kurucu icin markdown sayfasi. Hakem hukmu, kural ve kaynak YAZILMAZ."""
    lines = [
        f"# Kurucunun hizli sayfasi — {len(numbers)} satir ({title})",
        "",
        "Bu sayfanin satirlari **kasitli olarak secilmistir**: hakemin kararsiz oldugu,",
        "iki okumasinin ayristigi ya da kuralla celistigi yerler. Bu yuzden buradan",
        "cikacak uyum nufusun uyumundan DUSUK olur; yalniz kaymanin yonunu gosterir.",
        "",
        "## Soru — tek soru",
        "",
        "> **Bu metin Turkce bir dil modelinin egitim verisinde DURMALI mi, yoksa cop mu?**",
        "",
        "Olcut: \"siki korpus, supheliyi at\". Pratik sorusu: *bu sayfayi birine gosterip",
        "\"bunu modelimize okutacagiz\" deseniz, mahcup olur musunuz?* Olursaniz `cop`.",
        "",
        "## Nasil doldurulur",
        "",
        "Her metnin altindaki `Hukum:` satirina uc sozden birini yazin: `cop`, `kalsin`,",
        "`emin degilim`. Metinler ~900 karakterle kisaltildi; tamami kor dosyada ayni",
        "`juri no` ile durur.",
        "",
        "---",
        "",
    ]
    for index, number in enumerate(numbers, 1):
        row = blind_rows[number]
        text = str(row["metin"])
        preview = text[:ANCHOR_PREVIEW_CHARS]
        if len(text) > ANCHOR_PREVIEW_CHARS or row.get("kesildi"):
            preview += " …(kesildi)"
        lines += [
            f"## {index}. `juri no {number}` · {int(row['char_count'])} karakter",
            "",
            "```text",
            preview.replace("```", "'''"),
            "```",
            "",
            "Hukum: ",
            "",
        ]
    return "\n".join(lines)


def parse_anchor_sheet(text: str) -> dict[int, str]:
    """Doldurulmus sayfa -> (juri no -> kurucu hukmu). Bos hukum atlanir."""
    result: dict[int, str] = {}
    for _index, number, raw in _ANCHOR_BLOCK_RE.findall(text.replace("\r\n", "\n")):
        verdict = normalize_verdict(raw)
        if raw.strip() and verdict is None:
            raise VerdictFileError(f"juri no {number}: unknown owner verdict {raw.strip()!r}")
        if verdict is not None:
            result[int(number)] = verdict
    return result
