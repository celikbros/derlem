"""`commercial_page` kurali (tr-web-v4, TASK-046): urun / fiyat / satis / sponsorlu sayfa.

Bu modul yalniz OLCER ve esikleri tasir; gerekceyi `quality_v4` uretir.

Kurucunun cizgisi (TASK-041, duzeltilmis hali): "ansiklopedi kalir, sponsorlu
inceleme gider" -- ama TUR bir sinyaldir, hukum degildir; BICIM ONCE. Bu yuzden
kural konu sozlugu degil, satis sayfasinin BICIM izlerini sayar ve AILE sayar:
ayni ailenin on isabeti tek kanittir, iki ayri ailenin birer isabeti iki kanit.

Aileler (her biri tek basina ve birlesik olculdu; RAPOR.md §3):

  price        fiyat ifadesi (rakam + TL/₺/$/€ ...)
  cta          satin alma / arama / siparis cagrisi ("sepete ekle", "hemen ara",
               "ücretsiz kargo", "taksit", "stok durumu" ...)
  spec         urun karti alanlari ("ürün kodu", "marka:", "model:", "isbn",
               "teknik özellikler", "kdv dahil" ...)
  corp_we      kurumun kendini anlatmasi ("firmamız", "müşterilerimiz",
               "hizmetlerimiz", "sunuyoruz" ...) -- ansiklopedi bu dille yazmaz
  sponsor      sponsor / ortaklik / reklam etiketi ("sponsorlu", "affiliate",
               "reklam:", "indirim kodu" ...)
  breadcrumb   magaza gezinti izi ("Ana Sayfa > Ürünler > ...")
  title_repeat listeleme sablonu: basliktaki uc sozcukluk dizi metinde >= N kez
               ("Ümraniye Kazımkarabekir Elektrikçi" x 9; mahalle x hizmet,
               urun x sehir)

Karar: en az `min_families` aile YA DA tek ailede "sayfanin ana isi satis"
diyecek yogunluk (`strong`). Tamsayi karsilastirmalari.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


def turkish_casefold(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return normalized.replace("I", "ı").replace("İ", "i").casefold()


PRICE_RE = re.compile(
    r"\d[\d.]*,\d{2}\s*(?:tl|₺|ytl|usd|\$|euro|eur|€)(?![^\W\d_])"   # 27,99 TL  (kurus hanesi)
    r"|\d[\d,]*\.\d{2}\s*(?:usd|\$|euro|eur|€)(?![^\W\d_])"           # 47.14 $
    r"|\d[\d.,]*\s*(?:₺|\$|€)"                                         # 199 ₺
    r"|(?:₺|\$|€)\s?\d"                                                # $47.14
    r"|fiyat(?:ı|lar|ımız)?\s*[:=]\s*\d"                               # Fiyat: 120
)
"""Satis sayfasinin fiyat BICIMI: kurus haneli tutar, para simgesi ya da "Fiyat:" etiketi.
Duz yazidaki yuvarlak tutar ("100 lira", "95 TL") SAYILMAZ: tam alim orneginin goz
okumasinda ticari kuralin yanlis attigi haber/sikayet metinleri boyle tutarlar tasiyordu."""
CTA_RE = re.compile(
    r"sepete\s+ekle|satın\s+al(?:ın|mak\s+için)?(?![^\W\d_])|sipariş\s+ver|hemen\s+sipariş|online\s+sipariş|"
    r"hemen\s+ara(?:yın)?(?![^\W\d_])|bizi\s+arayın|teklif\s+al|fiyat\s+teklifi|ücretsiz\s+kargo|kargo\s+bedava|"
    r"aynı\s+gün\s+kargo|ücretsiz\s+teslimat|stok\s+durumu|stokta\s+(?:var|yok)|taksit\s+seçenek|"
    r"indirimli\s+fiyat|kampanyalı\s+fiyat|whatsapp\s+(?:hattı|destek|sipariş)|"
    r"hemen\s+indir|ücretsiz\s+indir|şimdi\s+indir|kupon\s+kodu|indirim\s+kodu|promosyon\s+kodu"
)
SPEC_RE = re.compile(
    r"ürün\s+kodu|stok\s+kodu|ürün\s+no(?![^\W\d_])|marka\s*:|model\s*:|ağırlık\s*:|boyut(?:lar)?\s*:|"
    r"renk\s*:|malzeme\s*:|garanti\s+süresi|isbn(?:13|10)?(?![^\W\d_])|barkod|teknik\s+özellikler|"
    r"ürün\s+özellikleri|kdv\s+dahil|vergiler\s+hariç|kargo\s+ücreti"
)
CORP_WE_RE = re.compile(
    r"(?<![^\W\d_])(?:firmamız|şirketimiz|kurumumuz|müşterilerimiz|hizmetlerimiz|ürünlerimiz|markamız|"
    r"mağazamız|ekibimiz|uzman\s+kadromuz|sunuyoruz|sunmaktayız|hizmet\s+vermekteyiz|hizmetinizdeyiz)"
)
SPONSOR_RE = re.compile(
    r"sponsorlu(?![^\W\d_])(?:\s+(?:içerik|bağlantı|yazı))?|reklam\s*:|reklamdır|işbirliği\s+ile\s+hazırlan|"
    r"affiliate|ortaklık\s+bağlantısı|advertorial|tanıtım\s+yazısıdır|bu\s+yazı\s+(?:bir\s+)?(?:reklam|tanıtım)"
)
"""Sayfanin KENDI reklam etiketi. "sponsorlu" tam sozcuktur: "yarismanin sponsorlugunu X
ustlendi" bir haberdir, etiket degil (tam alim tek gecisinden sonra duzeltildi; RAPOR §5)."""
BREADCRUMB_RE = re.compile(r"(?:ana\s*sayfa|anasayfa|home|ev)\s*(?:>|»|›)\s*[^\W\d_]")
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)

FAMILIES = ("price", "cta", "spec", "corp_we", "sponsor", "breadcrumb", "title_repeat")

TITLE_HEAD_WORDS = 30
"""Listeleme sablonu: bas kismin bu kadar sozcugundeki uc sozcukluk diziler aday."""


@dataclass(frozen=True, slots=True)
class CommercialStats:
    word_count: int
    price: int
    cta: int
    spec: int
    corp_we: int
    sponsor: int
    breadcrumb: int
    title_repeat: int
    """Basin ilk `TITLE_HEAD_WORDS` sozcugundeki uc sozcukluk dizilerin metindeki
    en yuksek gecis sayisi (ust uste binmeyen sayim)."""


def _title_repeat(words: list[str]) -> int:
    if len(words) < 6:
        return 0
    head = {tuple(words[i : i + 3]) for i in range(min(TITLE_HEAD_WORDS, len(words) - 2))}
    head = {gram for gram in head if any(len(w) >= 3 and not w.isdigit() for w in gram)}
    if not head:
        return 0
    counts: dict[tuple[str, ...], int] = {}
    last: dict[tuple[str, ...], int] = {}
    for i in range(len(words) - 2):
        gram = (words[i], words[i + 1], words[i + 2])
        if gram in head and last.get(gram, -3) <= i - 3:
            counts[gram] = counts.get(gram, 0) + 1
            last[gram] = i
    return max(counts.values(), default=0)


def commercial_stats(text: str) -> CommercialStats:
    folded = turkish_casefold(text)
    words = _WORD_RE.findall(folded)
    return CommercialStats(
        word_count=len(words),
        price=len(PRICE_RE.findall(folded)),
        cta=len(CTA_RE.findall(folded)),
        spec=len(SPEC_RE.findall(folded)),
        corp_we=len(CORP_WE_RE.findall(folded)),
        sponsor=len(SPONSOR_RE.findall(folded)),
        breadcrumb=len(BREADCRUMB_RE.findall(folded)),
        title_repeat=_title_repeat(words),
    )


@dataclass(frozen=True, slots=True)
class CommercialThresholds:
    title_repeat_min: int
    """`title_repeat` ailesinin yanmasi icin basliktaki dizinin en az gecis sayisi."""
    min_families: int
    """Bu kadar FARKLI aile yanarsa sayfa ticari."""
    strong: tuple[tuple[str, int], ...]
    """Tek aile yeterli olur: (aile, en az isabet). Bos = kapali."""


THRESHOLDS = CommercialThresholds(
    title_repeat_min=5,
    min_families=2,
    strong=(("price", 2), ("cta", 2), ("spec", 2), ("sponsor", 1)),
)
"""Secim tablosu RAPOR.md §3. Gecici hedefe gore (kurucu onayi bekliyor)."""


def commercial_families(
    stats: CommercialStats,
    thresholds: CommercialThresholds = THRESHOLDS,
) -> tuple[str, ...]:
    found: list[str] = []
    for family in FAMILIES:
        value = getattr(stats, family)
        if family == "title_repeat":
            if value >= thresholds.title_repeat_min:
                found.append(family)
        elif value >= 1:
            found.append(family)
    return tuple(found)


def is_commercial_page(
    stats: CommercialStats,
    thresholds: CommercialThresholds = THRESHOLDS,
) -> bool:
    families = commercial_families(stats, thresholds)
    if len(families) >= thresholds.min_families:
        return True
    return any(getattr(stats, family) >= minimum for family, minimum in thresholds.strong)


__all__ = [
    "FAMILIES",
    "THRESHOLDS",
    "CommercialStats",
    "CommercialThresholds",
    "commercial_families",
    "commercial_stats",
    "is_commercial_page",
]
