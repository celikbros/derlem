"""tr-web-v3 olcutleri: oran, yapisal sinyal, belirlenimci tekrar (TASK-040).

Bu modul yalniz OLCER ve esikleri tasir; hangi gerekcenin uretilecegine
`quality_filters._tr_web_v3_rejection_reasons` karar verir. tr-web-v1 ve
tr-web-v2 bu modulu kullanmaz.

Uc aile, uc ayri olcum raporundan gelir:

  var/olcum-2026-09-20/task-040-oran-ailesi/RAPOR.md   (oran + govde)
  var/olcum-2026-09-20/task-040-kumeler/RAPOR.md       (yapisal ikinci sinyal)
  var/olcum-2026-09-20/task-040-tekrar/RAPOR.md        (lz77 + cerceve muafiyeti)

Belirlenimcilik (TASK-039 kabul olcutu): butun esikler TAMSAYI karsilastirmasi
ile uygulanir ve sikistirma olcusu `zlib` yerine saf Python LZ77 kestirimidir.
Ayni belge kumesi kok .venv (3.14, zlib-ng) ile worker/.venv (3.13, zlib)
altinda ayni hukmu verir.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from derlem_worker.quality_body import (
    ProseStats,
    encoding_stats,
    prose_after_strip,
)


# ===========================================================================
# 1. "Varlik degil oran" ailesi
# ===========================================================================

FFFD_MIN_COUNT = 2
"""Tek bir U+FFFD hicbir kosulda atma sebebi degildir: kirpilmis son bayt.
v2 tek bir U+FFFD icin atiyordu ve bu tabakada yanlis atma %54 olculdu."""

FFFD_DENSITY_PER_10K = 10
"""Govdede 10.000 karakterde bu kadar U+FFFD varsa bozulma yaygindir.
10 secildi: 20 ile ayni kurtarmayi (25/27) bir eksik sizintiyla veriyor;
5'e inmek sizintiyi 12'ye indirir ama 5 iyi belgeyi feda eder."""

FFFD_TAIL_CHARS = 64
"""TAM metnin son bu kadar karakteri "kuyruk"tur. Yalniz orada duran bozulma
belgeyi atmaz: kesilmis UTF-8 baytinin yeri orasidir."""

MOJIBAKE_BRANCH_ENABLED = False
"""tr-web-v3'te KAPALI (birlestirme kosusu, 2026-09-20).

Mojibake kolu, v3'un v2'yi asabildigi TEK yerdi: v2'de karsiligi olmadigi icin
bir tetige baglanamaz, yani YENI atma uretebilir. Birinci asama olcumu onu
"olculmemis ama bedava" diye birakmisti (2.706 belgenin 0'inda basti).

Birlestirmede gercek regresyon kosusu bedelini buldu: v4 aday dosyasinin ilk
5.000 satirinda kol bir satiri -- Zeynuddin el-Amili uzerine bir ilahiyat
makalesini -- attiriyor, cunku kalibin `Â[ -¿]` kolu Turkce'nin SAPKALI Â
harfini yakaliyor ("el-ÂMILÎ", "TABAKÂT"). 300.000 satirlik tam regresyonda da
tek yeni atma sebebi buydu.

Gercek mojibake (`Ã¼`, `ÅŸ`, `Ä±`, `â€™`) hala taninir ve kol kodda durur, ama
kapali: bu korpusta mojibake yoktur, Â harfi vardir. Acilmasi icin once
mojibake'in gercekten bulundugu bir korpusta olculmesi ve Turkce sapkali
harflerden ayrilmasi gerekir (ayri kart)."""

MOJIBAKE_MIN_COUNT = 5
MOJIBAKE_DENSITY_PER_10K = 10

WIKI_MIN_PROSE_CHARS = 4000
"""Isaretleme/makine verisi bosaltildiktan sonra kalmasi gereken en az duzyazi.
Bu ornekte hic baglamadi ama populasyonda "4000 karakterden fazla duzyazi
birakan belge bu kuralla asla atilamaz" guvencesi verir."""

WIKI_MIN_PROSE_RATIO_NUM, WIKI_MIN_PROSE_RATIO_DEN = 45, 100
"""Kalan duzyazinin govdeye orani (0,45). En dusuk sizintiya ulasan EN KUCUK
oran; 0,50/0,55 ayni sonucu daha saldirgan bir esikle verir."""

NAV_MIN_PROSE_CHARS: int | None = None
"""Mutlak taban YOK: bu tabakanin belgeleri zaten uzun (hepsinde >3000
karakter kaliyor) ve her denenen taban (4k/8k/15k) sizintiyi artirdi."""

NAV_MIN_PROSE_RATIO_NUM, NAV_MIN_PROSE_RATIO_DEN = 65, 100
"""Menu bloklari dusunce kalan metin / govde (0,65). 0,75 bir iyi belgeyi uc
cop'a takas eder; kurucunun yeni-tutulanlar sayfasi bu iki deger arasinda
karar verecek."""


def encoding_corruption_ratio(text: str, scope: str) -> bool:
    """Govdede U+FFFD hem SAYICA hem ORAN olarak esigi asiyor mu ve bunlarin
    en az biri metnin kuyrugunun disinda mi.

    (Mojibake kolu ayri: `mojibake_corruption`.)
    """
    stats = encoding_stats(text, scope, tail_chars=FFFD_TAIL_CHARS)
    return (
        stats.replacement_count >= FFFD_MIN_COUNT
        and stats.replacement_outside_tail >= 1
        and stats.replacement_count * 10_000 >= stats.scope_chars * FFFD_DENSITY_PER_10K
    )


def mojibake_corruption(text: str, scope: str) -> bool:
    """Cift kodlama izi. `MOJIBAKE_BRANCH_ENABLED` False iken her zaman False
    doner (yukaridaki gerekce); olcum icin dogrudan cagrilabilir."""
    stats = encoding_stats(text, scope, tail_chars=FFFD_TAIL_CHARS)
    return (
        stats.mojibake_count >= MOJIBAKE_MIN_COUNT
        and stats.mojibake_count * 10_000 >= stats.scope_chars * MOJIBAKE_DENSITY_PER_10K
    )


def _below_ratio(stats: ProseStats, *, numerator: int, denominator: int) -> bool:
    return stats.prose_chars * denominator < stats.scope_chars * numerator


def wiki_prose_shortfall(scope: str) -> bool:
    """"Isaretleme var mi" degil: "kirpinca kac karakter duzyazi kaliyor".

    Belge ancak HEM mutlak olarak az duzyazi birakiyorsa HEM de kalan duzyazi
    govdenin kucuk bir parcasiysa atilir (VE).
    """
    stats = prose_after_strip(scope, strip="markup")
    return stats.prose_chars < WIKI_MIN_PROSE_CHARS and _below_ratio(
        stats, numerator=WIKI_MIN_PROSE_RATIO_NUM, denominator=WIKI_MIN_PROSE_RATIO_DEN
    )


def navigation_prose_shortfall(scope: str) -> bool:
    """"Menusu uzun mu" degil: "menu dusunce kac karakter metin kaliyor"."""
    stats = prose_after_strip(scope, strip="navigation")
    if NAV_MIN_PROSE_CHARS is not None and stats.prose_chars >= NAV_MIN_PROSE_CHARS:
        return False
    return _below_ratio(
        stats, numerator=NAV_MIN_PROSE_RATIO_NUM, denominator=NAV_MIN_PROSE_RATIO_DEN
    )


# ===========================================================================
# 2. Kume ailesi: ikinci, YAPISAL sinyal
# ===========================================================================
#
# v2 bu kumeleri TEK BIR sinyalle atiyordu: anahtar kelime yogunlugu. Sonuc
# konu filtresiydi -- `optics_spam_cluster` OPPO/Nokia maddelerine ve telefon
# incelemelerine basiyordu (%62 yanlis). v3 hicbir sozluk esigini gevsetmez;
# kural ayrica konudan BAGIMSIZ bir yapisal sinyal ister.
#
# Tasiyici sinyal islev sozcugu oranidir: Turkce duzyazi baglac, edat ve
# zamirle yurur; anahtar kelime yigmasi yurumez.

_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
_SEGMENT_RE = re.compile(r"[\n\r]+|(?<=[.!?…])\s+")
_URL_RE = re.compile(
    r"(?:\b(?:https?://|www\.)\S+|"
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:com|net|org|info|biz|xyz|site|online|tr|co|io)\b\S*)",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?90\s*)?(?:\(?0?5\d{2}\)?[\s.-]*)?"
    r"\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)"
)
_CTA_RE = re.compile(
    r"hemen\s+ara|hemen\s+arayın|hemen\s+tıkla|whatsapp|watsap|bizi\s+arayın|"
    r"ücretsiz\s+kargo|sipariş\s+ver|teklif\s+al|fiyat\s+teklifi|"
    r"iletişime\s+geç|randevu\s+al|hemen\s+üye|kayıt\s+ol\b|tıklayın"
)
_PRICE_RE = re.compile(r"\d[\d.,]*\s*(?:tl|₺|lira|usd|\$|euro|€)\b")
_SENTENCE_END_RE = re.compile(r"[.!?…]")

# Konudan bagimsiz duzyazi tasiyicilari. Kumelerin sozlukleriyle ORTAK HICBIR
# SOZCUGU YOKTUR; bu sartla "ikinci sinyal bagimsizdir" denebilir.
CLUSTER_FUNCTION_WORDS = frozenset(
    """
    ve veya ya ile bir bu şu o ne ki de da daha çok az en için gibi kadar göre
    sonra önce ama fakat ancak çünkü ayrıca hem her tüm bütün bazı hiç artık
    yine ise değil var yok olan olarak olduğu oldu olup oluyor olur ben sen
    biz siz onlar kendi bile sadece hatta nasıl neden niçin zaten işte birlikte
    arasında içinde üzerine üzere karşı dolayı tarafından böyle öyle şöyle şey
    mi mı mu mü ilk son diğer birçok birkaç nerede zaman yani ederek eden
    ettiği yapılan yapılması olması bunun onun şeyi kez defa üzerinde
    altında yanında rağmen ragmen doğru sırasında başka aynı büyük küçük yeni
    """.split()
)

FUNCTION_WORD_MAX_PER_100 = 14
"""`no_prose`: islev sozcugu orani bunun altindaysa metin duzyazi degildir.
Olculen ayrisma (govde, medyan): optics good 0,176 / cop 0,077; dating
0,226 / 0,119; commercial 0,188 / 0,130."""

SENTENCE_END_MIN_PER_100_WORDS = 2
"""`no_sentences`: 100 sozcukte cumle sonu. DURUST SINIR: bu ornekte tek
basina hicbir karari degistirmedi (yandigi her belgede `no_prose` da yaniyor)."""

PHONE_MIN = 5
CTA_MIN = 3
PRICE_MIN = 12
"""`contact_cta`: iyi sayilan is/ilan sayfalari da birkac telefon ve fiyat
tasir; esik "sayfanin ana isi satis" diyecek kadar yuksektir."""

URL_PER_1000_WORDS_MIN = 5
"""`link_flood`. DURUST SINIR: `no_sentences` gibi, bu ornekte tek basina
hicbir karari degistirmedi."""

DUPLICATE_SEGMENT_RATIO_MIN_PER_100 = 20
"""`repeated_block`: yinelenen iletisim/altbilgi blogu orani."""

REQUIRED_STRUCTURAL_SIGNALS = 1
"""Kac yapisal sinyal sart. 2 olculdu ve ELENDI: atilan karakterin %36,6'sini
saliyor ve cok gerekceli atmalardan ikisini bozuyordu."""

CLUSTER_STRUCTURAL_SIGNALS = (
    "no_prose",
    "no_sentences",
    "contact_cta",
    "link_flood",
    "repeated_block",
)


@dataclass(frozen=True, slots=True)
class StructuralStats:
    """Konudan bagimsiz yapisal olcumler (hepsi govde uzerinde)."""

    word_count: int
    function_words: int
    sentence_ends: int
    phone_count: int
    price_count: int
    cta_count: int
    url_count: int
    duplicate_segments: int
    segment_count: int


def turkish_casefold(text: str) -> str:
    """v1/v2 ile BIREBIR ayni katlama (uzunluk korumaz; konum gerekmez)."""
    normalized = unicodedata.normalize("NFKC", text)
    return normalized.replace("I", "ı").replace("İ", "i").casefold()


def _count_matches(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def _normalized_segments(folded: str) -> list[str]:
    """v1/v2 ile AYNI normalizasyon: sozcukler bosluk ile, <20 karakter atlanir."""
    out: list[str] = []
    for raw_segment in _SEGMENT_RE.split(folded):
        normalized = " ".join(match.group(0) for match in _WORD_RE.finditer(raw_segment))
        if len(normalized) < 20:
            continue
        out.append(normalized)
    return out


def structural_stats(folded_scope: str) -> StructuralStats:
    words = _WORD_RE.findall(folded_scope)
    segments = _normalized_segments(folded_scope)
    counts: dict[str, int] = {}
    for segment in segments:
        counts[segment] = counts.get(segment, 0) + 1
    return StructuralStats(
        word_count=len(words),
        function_words=sum(1 for word in words if word in CLUSTER_FUNCTION_WORDS),
        sentence_ends=len(_SENTENCE_END_RE.findall(folded_scope)),
        phone_count=_count_matches(_PHONE_RE, folded_scope),
        price_count=_count_matches(_PRICE_RE, folded_scope),
        cta_count=_count_matches(_CTA_RE, folded_scope),
        url_count=_count_matches(_URL_RE, folded_scope),
        duplicate_segments=sum(count for count in counts.values() if count > 1),
        segment_count=len(segments),
    )


def structural_signals(stats: StructuralStats) -> tuple[str, ...]:
    """Yanan yapisal sinyaller. Hepsi tamsayi karsilastirmasidir."""
    words = stats.word_count
    found: list[str] = []
    if words > 0 and stats.function_words * 100 < words * FUNCTION_WORD_MAX_PER_100:
        found.append("no_prose")
    if words > 0 and stats.sentence_ends * 100 < words * SENTENCE_END_MIN_PER_100_WORDS:
        found.append("no_sentences")
    if (
        stats.phone_count >= PHONE_MIN
        or stats.cta_count >= CTA_MIN
        or stats.price_count >= PRICE_MIN
    ):
        found.append("contact_cta")
    if words > 0 and stats.url_count * 1_000 >= words * URL_PER_1000_WORDS_MIN:
        found.append("link_flood")
    if (
        stats.segment_count > 0
        and stats.duplicate_segments * 100
        >= stats.segment_count * DUPLICATE_SEGMENT_RATIO_MIN_PER_100
    ):
        found.append("repeated_block")
    return tuple(found)


# ===========================================================================
# 3. Tekrar ailesi: belirlenimci sikistirilabilirlik + cerceve muafiyeti
# ===========================================================================

LZ77_WINDOW = 32_768
LZ77_MIN_MATCH = 4
LZ77_MAX_MATCH = 258
LZ77_MAX_CHAIN = 24
LZ77_LITERAL_BITS = 9
LZ77_MATCH_BITS = 25


def lz77_ratio_permille(text: str) -> int:
    """Saf Python LZ77 kestirimi: tahmini sikistirilmis boy / ham boy, binde.

    NEDEN: v2'nin `zlib.compress(level=9)` olcutu YORUMLAYICIYA BAGIMLIDIR.
    Olculdu (TASK-039): 1.206 satirin 869'unda sikistirilmis bayt, 415'inde
    binde cinsinden oran 3.14 (zlib-ng) ile 3.13 (zlib 1.3.1) arasinda
    farkliydi; %18 sinirinin +-%0,2 bandinda 11 satir vardi ve v4 taramasinda
    7 satir gercekten taraf degistirdi.

    Bu kestirim yapisal olarak belirlenimcidir: sabit pencere, sabit zincir
    derinligi, sabit maliyet modeli (degismez 9 bit / eslesme 25 bit), tamsayi
    aritmetigi, kutuphane cagrisi yok. Ayni 1.206 satirda iki yorumlayici
    arasinda fark: 0.

    zlib'in yerini tutmak icin degil, AYNI AYRIMI yapmak icin: asiri tekrarli
    metin cok dusuk oran verir. `<=260` ile `zlib<=180` ortusmesi %98,0.
    """
    raw = text.encode("utf-8")
    size = len(raw)
    if size == 0:
        return 1000
    heads: dict[bytes, list[int]] = {}
    bits = 0
    index = 0
    while index < size:
        best_length = 0
        if index + LZ77_MIN_MATCH <= size:
            chain = heads.get(raw[index : index + LZ77_MIN_MATCH])
            if chain:
                limit = index - LZ77_WINDOW
                for candidate in reversed(chain[-LZ77_MAX_CHAIN:]):
                    if candidate < limit:
                        continue
                    length = LZ77_MIN_MATCH
                    max_length = min(LZ77_MAX_MATCH, size - index)
                    while length < max_length and raw[candidate + length] == raw[index + length]:
                        length += 1
                    if length > best_length:
                        best_length = length
                        if length == max_length:
                            break
        if best_length >= LZ77_MIN_MATCH:
            bits += LZ77_MATCH_BITS
            step = best_length
        else:
            bits += LZ77_LITERAL_BITS
            step = 1
        for offset in range(step):
            position = index + offset
            if position + LZ77_MIN_MATCH <= size:
                heads.setdefault(raw[position : position + LZ77_MIN_MATCH], []).append(position)
        index += step
    return ((bits + 7) // 8 * 1000) // size


def unique_fivegram_permille(words: list[str]) -> int:
    """Benzersiz 5-gram / toplam 5-gram, binde. Saf Python, belirlenimci."""
    total = len(words) - 4
    if total <= 0:
        return 1000
    seen = {
        (words[i], words[i + 1], words[i + 2], words[i + 3], words[i + 4])
        for i in range(total)
    }
    return (len(seen) * 1000) // total


REPETITION_MIN_WORDS = 500
"""v2 ile ayni."""

EXTREME_U5_MAX_PERMILLE = 600
"""v2 ile ayni."""

EXTREME_LZ77_MAX_PERMILLE = 260
"""v2'nin `zlib <= 180 binde` olcutunun belirlenimci karsiligi. 260 secildi:
245/250 ile denetim kumesindeki kurtarilan/sizan AYNI (16/3), ortusme farki
%0,4; ama 260 TASK-039'un yedi sinir satirinin YEDISINI de iki yorumlayicida
da atiyor (250 yalniz ikisini)."""

REPEATED_MIN_WORDS = 1_500
REPEATED_DUP_MIN_PERMILLE = 200
REPEATED_U5_MAX_PERMILLE = 700
"""Ucu de v2 ile ayni. Cekirdegi gevsetmek olculdu ve elendi."""

# --- ASKIDA: "cerceve + ozgun dolgu" muafiyeti ----------------------------
FRAME_EXEMPTION_ENABLED = False
"""tr-web-v3'te KAPALI (kurucu hukmu, 2026-09-20).

Ne yapar: resmi/kurumsal Turkce'nin yapisal imzasini tanir -- ayni iskelete
(rakamlar maskelenmis) sahip segment gruplari var, bu gruplarin uyeleri
BIRBIRINDEN FARKLI ve metin yogun sayi/kimlik tasiyicisi iceriyor (ada,
parsel, tarih, karar numarasi). Boyle bir belge "sablon spam" degildir.

NEDEN KAPALI: olcum iki yonde cikti.
  * Rafin denetlediği 76 aile satirinda 16/23 iyi belgeyi kurtariyor, 3/53 cop
    siziyordu -- guclu bir sonuc.
  * Ama KURUCUNUN hukum verdigi 5 aile satirinin hicbirine `good` demedi ve
    muafiyet bunlardan IKISINI seriyor (kurtajforum basligi, kompresor bakim
    kitabi): kurucunun olceginde bu bir kurtarma degil, 2/5 sizintidir.
  * Etiketsiz 500 satirlik genis ornekte tabakalarin %19'unu (belge) / %14'unu
    (karakter) tutuyor ve tutulanlarin icinde en az iyi metin kadar cop var
    (forum sayfalama, "Son Dakika ... Haberleri" etiket sayfalari, İzlesene
    video listeleri, KAYAK/agoda otel listeleri, bahis girisleri).
  * Iki ince esigi (`FRAME_NOVELTY_MIN_PERMILLE`, `FRAME_DISTINCT_NUMBERS_MIN`)
    76 satirlik bir ornekte ayarlandi; asiri uyum riski acik.

Bu celiski olcumle kapanmaz, HUKUMLE kapanir. Kurucu yeni-tutulanlar sayfasini
hukme baglayinca acilip acilmayacagina karar verilecek; o zamana kadar
tr-web-v3 muafiyetsiz calisir ve boyle bir belge ATILIR.
"""

FRAME_MIN_PERMILLE = 100
"""Segmentlerin >= %10'u bir cercevede."""

FRAME_NOVELTY_MIN_PERMILLE = 225
"""Cerceve orneklerinin >= %22,5'i farkli dolgulu."""

FRAME_NUMBERS_PER_KWORD_MIN = 20
"""Bin sozcukte >= 20 sayi belirteci."""

FRAME_DISTINCT_NUMBERS_MIN = 35
"""Ve >= 35 FARKLI sayi. 30 yerine 35: iki sizintiyi bedelsiz kapatiyordu."""

_NUMBER_RE = re.compile(r"\d+(?:[.,/:\-]\d+)*")
_DIGIT_RUN_RE = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class RepetitionStats:
    """Tekrar olcumleri.

    Pahali alanlar YALNIZ karari degistirebilecekleri durumda hesaplanir;
    aksi halde kurali basmayacak bir taban deger tasirlar. Bu bir kisayol
    degil, ayni kararin ucuz yoludur:
      * `word_count < REPETITION_MIN_WORDS` ise hicbir kol basamaz;
      * `unique_fivegram_permille > REPEATED_U5_MAX_PERMILLE` ise de oyle;
      * `lz77_permille` (saf Python, pahali) ancak 5-gram orani
        `EXTREME_U5_MAX_PERMILLE`'i asmiyorsa hesaplanir, cunku aksi halde
        `extreme_repetition` zaten basamaz -> 1000 (sikismiyor) yazilir;
      * segment sayimi ancak `repeated_segments`in sozcuk kapisi geciliyorsa
        yapilir -> aksi halde 0.
    """

    word_count: int
    segment_count: int
    duplicate_segments: int
    unique_fivegram_permille: int
    lz77_permille: int


def repetition_stats(scope: str, folded_scope: str) -> RepetitionStats:
    words = _WORD_RE.findall(folded_scope)
    word_count = len(words)
    if word_count < REPETITION_MIN_WORDS:
        return RepetitionStats(word_count, 0, 0, 1000, 1000)
    unique5 = unique_fivegram_permille(words)
    if unique5 > REPEATED_U5_MAX_PERMILLE:
        return RepetitionStats(word_count, 0, 0, unique5, 1000)

    lz77 = lz77_ratio_permille(scope) if unique5 <= EXTREME_U5_MAX_PERMILLE else 1000
    segment_count = 0
    duplicates = 0
    if word_count >= REPEATED_MIN_WORDS:
        counts: dict[str, int] = {}
        for segment in _normalized_segments(folded_scope):
            counts[segment] = counts.get(segment, 0) + 1
            segment_count += 1
        duplicates = sum(count for count in counts.values() if count > 1)
    return RepetitionStats(
        word_count=word_count,
        segment_count=segment_count,
        duplicate_segments=duplicates,
        unique_fivegram_permille=unique5,
        lz77_permille=lz77,
    )


@dataclass(frozen=True, slots=True)
class FrameStats:
    frame_instances: int
    frame_distinct_fills: int
    segment_count: int
    word_count: int
    number_tokens: int
    distinct_numbers: int


def frame_stats(scope: str, folded_scope: str) -> FrameStats:
    """"Cerceve + dolgu" olcumleri (yalniz muafiyet aciksa hesaplanir)."""
    segments = _normalized_segments(folded_scope)
    frames: dict[str, list[str]] = {}
    for segment in segments:
        frames.setdefault(_DIGIT_RUN_RE.sub("#", segment), []).append(segment)
    instances = 0
    distinct_fills = 0
    for members in frames.values():
        if len(members) < 2:
            continue
        instances += len(members)
        distinct_fills += len(set(members))
    numbers = _NUMBER_RE.findall(scope)
    return FrameStats(
        frame_instances=instances,
        frame_distinct_fills=distinct_fills,
        segment_count=len(segments),
        word_count=len(_WORD_RE.findall(folded_scope)),
        number_tokens=len(numbers),
        distinct_numbers=len(set(numbers)),
    )


def informative_frames(stats: FrameStats) -> bool:
    """Resmi/kurumsal Turkce imzasi. Sozluk yok, konu yok -- yalniz yapi.

    `FRAME_EXEMPTION_ENABLED` False iken hicbir yerden cagrilmaz; acildiginda
    ne oldugunu gosteren test worker/tests/test_quality_filters.py'dedir.
    """
    return (
        stats.segment_count > 0
        and stats.word_count > 0
        and stats.frame_instances * 1_000 >= stats.segment_count * FRAME_MIN_PERMILLE
        and stats.frame_distinct_fills * 1_000
        >= stats.frame_instances * FRAME_NOVELTY_MIN_PERMILLE
        and stats.number_tokens * 1_000 >= stats.word_count * FRAME_NUMBERS_PER_KWORD_MIN
        and stats.distinct_numbers >= FRAME_DISTINCT_NUMBERS_MIN
    )


REPETITION_SCOPE = "tam metin"
"""Tekrar ailesi TAM METIN uzerinde olcer -- tek aile boyle.

Cunku olculdu (birlestirme kosusu, gercek `body()` ile, 706 denetim satiri):
govde uzerinde olcmek bu ailede 2 iyi belge kurtariyor ama 9 cop belgeyi
seriyor (rafin hukmu), kurucunun hukmunde ise 0 kurtarma karsiliginda 1
sizinti veriyor (TripAdvisor sayfasi `5724960ec1`). Sebebi anlasilir: bas/son
kirpmasi belgenin OZGUN parcasini (haber kirintisi, altbilgi metni) atip geriye
sablon iskeletini birakiyor -- ama ayni kirpma sozcuk sayisini 500/1.500
kapilarinin altina da dusurebiliyor, ve bu ailede kapilarin altina dusmek
"tutulur" demek.

Bu yuzden govde sozlesmesinin S6 maddesi ("oteki aileler olcumlerini govdede
yapar") bu aile icin OLCUMLE reddedildi. Oran ve kume aileleri govdeyi
kullanmaya devam ediyor.
"""


def repetition_reasons(scope: str, folded_scope: str) -> tuple[str, ...]:
    """Tekrar ailesinin v3 gerekceleri.

    Cekirdek esikler v2 ile aynidir; tek degisiklik sikistirma olcusunun
    `zlib` yerine `lz77_ratio_permille` olmasidir (TASK-039). Kapsam icin
    `REPETITION_SCOPE`e bakin.
    """
    stats = repetition_stats(scope, folded_scope)
    if stats.word_count < REPETITION_MIN_WORDS:
        return ()
    if FRAME_EXEMPTION_ENABLED and informative_frames(frame_stats(scope, folded_scope)):
        return ()

    matched: list[str] = []
    if (
        stats.lz77_permille <= EXTREME_LZ77_MAX_PERMILLE
        and stats.unique_fivegram_permille <= EXTREME_U5_MAX_PERMILLE
    ):
        matched.append("extreme_repetition")
    if (
        stats.word_count >= REPEATED_MIN_WORDS
        and stats.segment_count > 0
        and stats.duplicate_segments * 1_000
        >= stats.segment_count * REPEATED_DUP_MIN_PERMILLE
        and stats.unique_fivegram_permille <= REPEATED_U5_MAX_PERMILLE
    ):
        matched.append("repeated_segments")
    return tuple(matched)


__all__ = [
    "CLUSTER_FUNCTION_WORDS",
    "CLUSTER_STRUCTURAL_SIGNALS",
    "EXTREME_LZ77_MAX_PERMILLE",
    "FFFD_DENSITY_PER_10K",
    "FFFD_MIN_COUNT",
    "FFFD_TAIL_CHARS",
    "FRAME_EXEMPTION_ENABLED",
    "FrameStats",
    "NAV_MIN_PROSE_RATIO_NUM",
    "REQUIRED_STRUCTURAL_SIGNALS",
    "RepetitionStats",
    "StructuralStats",
    "WIKI_MIN_PROSE_CHARS",
    "WIKI_MIN_PROSE_RATIO_NUM",
    "encoding_corruption_ratio",
    "frame_stats",
    "informative_frames",
    "lz77_ratio_permille",
    "mojibake_corruption",
    "navigation_prose_shortfall",
    "repetition_reasons",
    "repetition_stats",
    "structural_signals",
    "structural_stats",
    "turkish_casefold",
    "unique_fivegram_permille",
    "wiki_prose_shortfall",
]
