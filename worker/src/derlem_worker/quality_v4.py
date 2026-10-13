"""tr-web-v4 (TASK-046): tr-web-v3 + iki yeni kural -- `machine_translation`, `commercial_page`.

v3 hukumleri DONDURULMUSTUR: v4, v3'un gerekcelerini `quality_filters` icindeki
v3 kod yolundan AYNEN alir ve yalniz iki yeni gerekce EKLER. Sonucu olculebilir
bir guvencedir ve testle sabitlenmistir: ayni girdi icin v4'un gerekcelerinden
v3'e ait olanlar v3'un gerekceleriyle birebir aynidir (regresyon testi:
worker/tests/test_quality_v4.py).

Neden iki yeni kural: FineWeb2-HQ'nun karma kor okumasinda (2026-10-04) copun
nedenleri makine cevirisi (12/100) ve SEO/ticari/urun sayfasi (12/100); v3 bu
veride belgelerin %0,6'sini atiyor, hakem ~%40'ina cop diyor. Iki kural da
YAPISALDIR (bicim ve koken), konu sozlugu degil.

Kapsam: iki kural TAM METIN uzerinde calisir (govde degil). Rafin kurali: "metin
kurtarilmak icin kirpilmak zorundaysa coptur" -- magaza gezinti izi, sponsor
etiketi ve fiyat tablosu cogu zaman govdenin disindadir.

`url`: ortak belge kaydinin (derlem.document.v1) `provenance.url`'si. Yoksa
(None) makine cevirisi kurali yalniz icerik sinyalleriyle karar verir -- URL'siz
kaynakta (v5 gibi) kural zayiflar ama YANLIS atma artmaz (olculdu).

Olcum: var/olcum-2026-10-13/task-046/RAPOR.md.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from derlem_worker import commercial_page, machine_translation

POLICY_NAME = "tr-web-v4"

REASON_MACHINE_TRANSLATION = "machine_translation"
REASON_COMMERCIAL_PAGE = "commercial_page"
NEW_REASONS = (REASON_MACHINE_TRANSLATION, REASON_COMMERCIAL_PAGE)
"""v3 gerekcelerinden SONRA, bu sirayla."""

MACHINE_TRANSLATION_ENABLED = True
COMMERCIAL_PAGE_ENABLED = True
"""Kontrol kosulari icin anahtarlar (test bir kurali kapatip kirmiziyi gorur)."""

RULE_SOURCE_FILES = (
    "quality_filters.py",
    "quality_body.py",
    "quality_v3.py",
    "quality_v4.py",
    "machine_translation.py",
    "commercial_page.py",
)
"""Hukmu belirleyen kaynak dosyalar. Karar kaydindaki yargic kimligi
(`tr-web-v4@<sha>`) bunlarin LF'ye cevrilmis baytlarindan hesaplanir: kod
degisirse yargic degisir, ayni kod her isletim sisteminde ayni kimligi verir."""

JUDGE_SHA_HEX_CHARS = 12


def new_reasons(text: str, url: str | None = None) -> tuple[str, ...]:
    """Yalniz v4'un EKLEDIGI gerekceler (v3'unkiler haric), sabit sirada."""
    found: list[str] = []
    if MACHINE_TRANSLATION_ENABLED and machine_translation.is_machine_translation(
        machine_translation.machine_translation_stats(text, url)
    ):
        found.append(REASON_MACHINE_TRANSLATION)
    if COMMERCIAL_PAGE_ENABLED and commercial_page.is_commercial_page(
        commercial_page.commercial_stats(text)
    ):
        found.append(REASON_COMMERCIAL_PAGE)
    return tuple(found)


def rule_source_sha256() -> str:
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in RULE_SOURCE_FILES:
        data = (package / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode("ascii") + b"\0" + str(len(data)).encode("ascii") + b"\0")
        digest.update(data)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def judge_id() -> str:
    """Karar kaydinin `judge` alani: `tr-web-v4@<kural kodunun sha256'si, 12 hane>`."""
    return f"{POLICY_NAME}@{rule_source_sha256()[:JUDGE_SHA_HEX_CHARS]}"


__all__ = [
    "COMMERCIAL_PAGE_ENABLED",
    "MACHINE_TRANSLATION_ENABLED",
    "NEW_REASONS",
    "POLICY_NAME",
    "REASON_COMMERCIAL_PAGE",
    "REASON_MACHINE_TRANSLATION",
    "RULE_SOURCE_FILES",
    "judge_id",
    "new_reasons",
    "rule_source_sha256",
]
