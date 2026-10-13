"""`machine_translation` kurali (tr-web-v4, TASK-046): makine cevirisi / ceviri ciftligi.

Bu modul yalniz OLCER ve esikleri tasir; gerekceyi `quality_v4` uretir. Kural
YAPISALDIR, konusal degil: hangi konuda yazildigina bakmaz, metnin NASIL
yazildigina ve NEREDEN geldigine bakar. Butun esikler TAMSAYI karsilastirmasidir
(belirlenimcilik, TASK-039 ilkesi).

Olcum: var/olcum-2026-10-13/task-046/RAPOR.md (etiketli 1.200 + 200 + 200 satir;
gozle isaretler + hakem hukumleri). Hedefler (recall >= %80, `kalsin`
satirlarinda yanlis atma <= %5) kurucu tarafindan HENUZ ONAYLANMADI; esikler
gecici hedefe gore secildi.

Sinyaller (her biri tek basina ve birlesik olculdu):

  URL imzasi      ana makine `tr.` ile basliyor / yolda `tr` dil kesimi /
                  Turkiye disi ulke alan adi (2 harfli ccTLD, `tr` ve genel
                  kullanimli olanlar disinda). Ortak belge kaydinin `url`'si
                  sayesinde var; v5'te YOK (adres saklanmadi).
  islev profili   cevirinin kopya kaliplari ("sahiptir", "olacaktır",
                  "aşağıdaki", "dahil" ...) ile dogal Turkce baglama ogeleri
                  ("ise", "diye", "kendisine", "ederek" ...) arasindaki fark,
                  binde. Sozlukler ETIKETLI SATIRLARDAN turetildi (ana ornek,
                  log-oran; yalniz dilbilgisel ogeler tutuldu) -- konu sozcugu yok.
  "Bu," calkasi   cumle basinda "Bu," (Ingilizce "This," kalibi).
  Kiril kalintisi Latin Turkce metinde az sayida Kiril harf (Rusca kaynaktan
                  ceviri; TASK-040'in karisik yazi sinyalinin kucuk dozu).

Olculup REDDEDILEN sinyaller (kodda yok, gerekce raporda): harfi harfine
cevrilmis ozel ad sozlugu (ana ornekten turetilen 7 sozcukluk sozluk kontrol orneginde
MT belgelerinin 1/26sinda, MT-olmayanlarin 5/174unde -- ezber), cumle uzunlugu duzenliligi (AUC 0,50-0,59), Ingilizce sayi bicimi,
"Bay/Sayın + ad" kalibi (cok seyrek).
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import urlsplit


# ---------------------------------------------------------------------------
# URL imzasi
# ---------------------------------------------------------------------------

GENERIC_USE_CCTLDS = frozenset({"co", "io", "tv", "me", "cc", "ws", "fm", "ly", "gg", "tc", "az", "cy"})
"""Ulkeyle iliskisi zayif ya da Turkce yayinda yaygin 2 harfli uzantilar.
Olculen: `.tv` 4, `.gg` 4 (`tr.gg` Turkce ucretsiz barindirma), `.tc` 2, `.az` 1
belgenin HICBIRI ceviri degil; `.co` 4/8 ceviri -- tek basina belirleyici degil,
genel listede. Bu liste etiketli satirlardaki uzanti tablosundan geliyor."""

URL_EXEMPT_HOST_RE = re.compile(
    r"(?:^|\.)(?:wikipedia|wikimedia|wikivoyage|wiktionary|wikibooks|wikiquote|wikisource|"
    r"wikinews|wikiversity|wikidata)\.org$"
)
"""Wikimedia projeleri topluluk yazimidir; `tr.wikipedia.org` dil alt alani
ceviri imzasi degildir (etiketli satirlarda 6 belge, 0 ceviri)."""

_PATH_TR_RE = re.compile(r"(?:^|/)tr(?:[-_][a-z]{2})?(?:/|$)|[?&](?:lang|hl|language|locale)=tr\b")


def url_signature(url: str | None) -> tuple[str, ...]:
    """Yanan URL imzalari: `host_tr`, `path_tr`, `foreign_cctld` (bos olabilir)."""
    if not url:
        return ()
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return ()
    if not host or URL_EXEMPT_HOST_RE.search(host):
        return ()
    found: list[str] = []
    if host.startswith("tr."):
        found.append("host_tr")
    path = parts.path.lower()
    query = parts.query.lower()
    if _PATH_TR_RE.search(path) or (query and _PATH_TR_RE.search("?" + query)):
        found.append("path_tr")
    tld = host.rsplit(".", 1)[-1]
    if len(tld) == 2 and tld.isascii() and tld.isalpha() and tld != "tr" and tld not in GENERIC_USE_CCTLDS:
        found.append("foreign_cctld")
    return tuple(found)


# ---------------------------------------------------------------------------
# Islev profili
# ---------------------------------------------------------------------------
#
# Turetme (var/olcum-2026-10-13/task-046/kesif2.py, kesif3.py): ana ornegin
# 1.000 belgesinde, metinde en sik ~600 kucuk harfli sozcukten (buyuk harfle
# yazilma payi >= %30 olanlar -- ozel ad / baslik sozcugu -- otomatik disarida)
# MT-pozitif ile MT-olmayan belge frekansi log-orani. Iki ucun en guclu 60'ar
# ogesinden YALNIZ dilbilgisel olanlar (zamir, yardimci fiil cekimi, edat,
# baglac, zarf) tutuldu; ad ve konu sozcukleri ("bahis", "satış", "istanbul",
# "türkiye" ...) bilerek atildi -- kural konu filtresi olmasin diye.

CALQUE_WORDS = frozenset(
    """
    olduğundan sahiptir bunları olun olacaktır aşağıdaki dahil sağlar belirli onları
    kullanmak gerekiyor hala anda çoğu çeşitli tamamen yoktur gerçekten açıkça
    yalnızca gerekir onların edilmiş edilmesi takdirde anlamına içerir izin
    """.split()
)
"""Ceviriye kayan ogeler ("have" -> sahiptir, "will be" -> olacaktır, "the
following" -> aşağıdaki, "including" -> dahil, "provides" -> sağlar ...)."""

NATIVE_WORDS = frozenset(
    """
    kendisine içerisinde ise demek şöyle yanında adlı olma yaptığı ait hep aldığı
    ederek biçimde üzerine yana yapılan diye yönelik yandan
    """.split()
)
"""Cevirinin KULLANMADIGI dogal Turkce baglama ogeleri (ana ornekte MT
belgelerinin %0-5'inde, digerlerinde %4-25'inde)."""

assert not CALQUE_WORDS & NATIVE_WORDS

_FOLDED_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_BU_COMMA_RE = re.compile(r"(?:^|[.!?…]\s+|\n\s*)Bu,\s")


def turkish_casefold(text: str) -> str:
    """v1/v2/v3 ile ayni katlama."""
    normalized = unicodedata.normalize("NFKC", text)
    return normalized.replace("I", "ı").replace("İ", "i").casefold()


@dataclass(frozen=True, slots=True)
class MachineTranslationStats:
    url_signals: tuple[str, ...]
    word_count: int
    calque_hits: int
    native_hits: int
    bu_comma: int
    cyrillic: int
    letters: int

    @property
    def profile_permille(self) -> int:
        """(kopya - dogal) / sozcuk, binde, asagi yuvarlanmis (yalniz rapor icin;
        karar tamsayi capraz carpimla verilir)."""
        if self.word_count <= 0:
            return 0
        return (self.calque_hits - self.native_hits) * 1_000 // self.word_count


def machine_translation_stats(text: str, url: str | None = None) -> MachineTranslationStats:
    folded = turkish_casefold(text)
    words = _FOLDED_WORD_RE.findall(folded)
    calque = 0
    native = 0
    for word in words:
        if word in CALQUE_WORDS:
            calque += 1
        elif word in NATIVE_WORDS:
            native += 1
    cyrillic = 0
    letters = 0
    for character in text:
        if character.isalpha():
            letters += 1
            if "Ѐ" <= character <= "ӿ":
                cyrillic += 1
    return MachineTranslationStats(
        url_signals=url_signature(url),
        word_count=len(words),
        calque_hits=calque,
        native_hits=native,
        bu_comma=len(_BU_COMMA_RE.findall(text)),
        cyrillic=cyrillic,
        letters=letters,
    )


# ---------------------------------------------------------------------------
# Karar
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MachineTranslationThresholds:
    min_words: int
    """Profil olcusu bu kadar sozcukten kisa belgede KULLANILMAZ (oran oynak)."""
    url_profile_permille: int
    """URL imzasi VARKEN profilin ulasmasi gereken binde deger (zayif teyit)."""
    strong_profile_permille: int
    """URL imzasi YOKKEN tek basina yeten profil (guclu)."""
    cyrillic_min: int
    cyrillic_max_share_per_100: int
    """Kiril kalintisi: en az `cyrillic_min` Kiril harf, harflerin %X'inden az
    (fazlasi kalinti degil, Rusca/karisik belge -- baska kuralin isi)."""
    bu_comma_profile_permille: int | None = None
    """URL'SIZ ikinci yol: "Bu," calkasi VE profil >= bu deger. None = kapali."""


THRESHOLD_SETS: dict[str, MachineTranslationThresholds] = {
    # A: `kalsin` yanlis atma tavani %5 (RAPOR.md §2.3 secimi; ana recall %79,6,
    # hakem-MT %64, kontrol %73,1, `kal` %4,9, `v5kal` %1,0).
    "A": MachineTranslationThresholds(
        min_words=75,
        url_profile_permille=-4,
        strong_profile_permille=20,
        cyrillic_min=3,
        cyrillic_max_share_per_100=5,
        bu_comma_profile_permille=10,
    ),
    # B: tavan %7,5 (RAPOR.md §2.4 cephesi, olc-mt.json `frontier["7.5"]`; ana
    # recall %83,9, hakem-MT %64, kontrol %80,8, `kal` %6,6, `v5kal` %2,9).
    "B": MachineTranslationThresholds(
        min_words=75,
        url_profile_permille=-4,
        strong_profile_permille=14,
        cyrillic_min=3,
        cyrillic_max_share_per_100=5,
        bu_comma_profile_permille=4,
    ),
}
"""Kurucunun sececegi iki hedef cifti (TASK-046 / TASK-049). Olculen degerler; elle
oynanmaz -- yeni bir cift yeni olcum ister."""

MT_TARGET = "B"
"""POLITIKA SABITI: hangi hedef cifti uygulanir ("A" ya da "B"). Tek degisiklik
noktasi budur. Bu dosya `quality_v4.RULE_SOURCE_FILES` icinde oldugundan secim
yargic kimligine (`tr-web-v4@<sha>`) girer: A ile B ayni kimligi tasiyamaz."""

THRESHOLDS = THRESHOLD_SETS[MT_TARGET]
"""Uygulanan esikler. Secim tablosu RAPOR.md §2.3 / §2.4 (kurucu A/B secimi bekliyor)."""


def _profile_at_least(stats: MachineTranslationStats, permille: int) -> bool:
    return stats.word_count > 0 and (
        (stats.calque_hits - stats.native_hits) * 1_000 >= stats.word_count * permille
    )


def machine_translation_signals(
    stats: MachineTranslationStats,
    thresholds: MachineTranslationThresholds = THRESHOLDS,
) -> tuple[str, ...]:
    """Yanan ALT sinyaller (rapor ve karar icin). Karar `is_machine_translation`."""
    found: list[str] = list(stats.url_signals)
    long_enough = stats.word_count >= thresholds.min_words
    if long_enough and _profile_at_least(stats, thresholds.url_profile_permille):
        found.append("profile_weak")
    if long_enough and _profile_at_least(stats, thresholds.strong_profile_permille):
        found.append("profile_strong")
    if stats.bu_comma >= 1:
        found.append("bu_comma")
        if (
            thresholds.bu_comma_profile_permille is not None
            and long_enough
            and _profile_at_least(stats, thresholds.bu_comma_profile_permille)
        ):
            found.append("bu_comma_profile")
    if (
        stats.cyrillic >= thresholds.cyrillic_min
        and stats.cyrillic * 100 < stats.letters * thresholds.cyrillic_max_share_per_100
    ):
        found.append("cyrillic_residue")
    return tuple(found)


def is_machine_translation(
    stats: MachineTranslationStats,
    thresholds: MachineTranslationThresholds = THRESHOLDS,
) -> bool:
    """Karar: (URL imzasi VE icerik teyidi) YA DA guclu profil.

    Icerik teyidi: zayif profil, "Bu," calkasi ya da Kiril kalintisi. URL tek
    basina YETMEZ: etiketli satirlarda URL imzali 195 belgenin 106'si ceviri
    degildi (tr.motorsport.com, dw.com/tr, support.microsoft.com/tr-tr ...).
    """
    signals = machine_translation_signals(stats, thresholds)
    has_url = any(signal in signals for signal in ("host_tr", "path_tr", "foreign_cctld"))
    content = any(signal in signals for signal in ("profile_weak", "bu_comma", "cyrillic_residue"))
    if has_url and content:
        return True
    return "profile_strong" in signals or "bu_comma_profile" in signals


__all__ = [
    "CALQUE_WORDS",
    "NATIVE_WORDS",
    "MT_TARGET",
    "THRESHOLDS",
    "THRESHOLD_SETS",
    "MachineTranslationStats",
    "MachineTranslationThresholds",
    "is_machine_translation",
    "machine_translation_signals",
    "machine_translation_stats",
    "url_signature",
]
