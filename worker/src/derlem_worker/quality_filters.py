from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
import zlib

from derlem_worker import quality_body, quality_v3
from derlem_worker.pii import normalize_language_tag
from derlem_worker.quality_body import body


QUALITY_POLICY_NONE = "none"
QUALITY_POLICY_TR_WEB_V1 = "tr-web-v1"
# tr-web-v2 = tr-web-v1 + iki kesin kural (2026-09-18, 100k dilim olcumu sonrasi):
# geri getirilemez kodlama bozulmasi (U+FFFD) ve Vikipedi isaretleme kalintisi.
# Ikisi de belge uzunlugundan bagimsiz uygulanir; v1 kurallari 500+ sozcuk ister.
QUALITY_POLICY_TR_WEB_V2 = "tr-web-v2"
# tr-web-v3 = TASK-040 (2026-09-20). v2'nin olculen kusuru: kendi atma
# raporunda yanlis atma orani %41,8 (raf) / %23,1 (kurucu), esik %10. Uc duzeltme
# ailesi birlestirildi:
#   (a) "varlik degil oran" + GOVDE: kural belgenin govdesine bakar, tek bir
#       U+FFFD ya da uzun bir menu tek basina atma sebebi degildir;
#   (b) kume ailesi: uslup kumeleri artik ikinci, YAPISAL bir sinyal ister
#       (sozluk esikleri degismedi) -- kural konu filtresi olmaktan cikti;
#   (c) tekrar ailesi: `zlib` yerine saf Python LZ77 kestirimi (TASK-039:
#       hukum yorumlayiciya bagimliydi). Cekirdek esikler degismedi.
# DEGISMEYENLER: v1/v2 kod yollari, `adult_service_spam_cluster` (rafin
# olcumunde 50/50 dogru), `mixed_script_artifact` ve cok gerekceli atmalar.
#
# SIKI AYAR (2026-09-21, kurucu karari "A) Siki korpus -- supheliyi at"):
# yukaridaki gevsetme FAZLA COMERTTI. Kurucu yeni-tutulanlardan 50'sine bakti,
# 48'ine "cop" dedi (ikisini -- Kloroform ve XAML -- "kalsin" diye duzeltti);
# bagimsiz model jurileri ayni 50'de %38-44 "cop" dedi. Her ailede muafiyet
# daraltildi ve muafiyetin sarti acik bir OLCU oldu (esikler ve gerekceler
# quality_v3.py'de; olcum var/olcum-2026-09-21/task-040-siki/RAPOR.md):
#   * gezinme ve hashtag muafiyetleri KAPATILDI,
#   * U+FFFD: yalniz "tek bozuk karakter, tam metnin kuyrugunda, kelime disi",
#   * wiki: duzyazi miktari + orani + islev sozcugu orani + ticari veto,
#   * kume: yapisal sinyal (R1 degismedi) YA DA sozluk yogunlugu marji 2,10x,
#   * "v2 govdede de basiyor mu" kapisi kalkti (govde kirpmasi muafiyet degil).
# Olculen sonuc: kurucunun "iyi" dedigi 7 belgenin 7'si korundu, B sayfasinin
# 50 satirindan 43'u yeniden atildi.
QUALITY_POLICY_TR_WEB_V3 = "tr-web-v3"
SUPPORTED_QUALITY_POLICIES = frozenset(
    {
        QUALITY_POLICY_NONE,
        QUALITY_POLICY_TR_WEB_V1,
        QUALITY_POLICY_TR_WEB_V2,
        QUALITY_POLICY_TR_WEB_V3,
    }
)

# Dil durustlugu (TASK-026, 2026-09-19): tr-web kurallari Turkce sozluk kurallaridir.
# Baska dil ilan etmis bir kaynaga uygulanmazlar; "temiz" yerine "not_evaluated"
# yazilir. Politika burada yoksa dil kisiti yoktur (none). Anahtar: normalize dil
# etiketi (birincil alt etiket, kucuk harf; 'tr-TR' -> 'tr').
QUALITY_POLICY_SUPPORTED_LANGUAGES: dict[str, frozenset[str]] = {
    QUALITY_POLICY_TR_WEB_V1: frozenset({"tr"}),
    QUALITY_POLICY_TR_WEB_V2: frozenset({"tr"}),
    QUALITY_POLICY_TR_WEB_V3: frozenset({"tr"}),
}

QUALITY_FILTER_STATUS_APPLIED = "applied"
# Dil bilinmiyor (--input-path ile yerel deney): politika bugunku gibi uygulanir,
# manifest bunu acikca kaydeder.
QUALITY_FILTER_STATUS_APPLIED_LANGUAGE_UNKNOWN = "applied_language_unknown"
QUALITY_FILTER_STATUS_NOT_EVALUATED = "not_evaluated"


def quality_filter_status(policy: str, language: str | None) -> str | None:
    """Politikanin ilan edilen kaynak diline uygulanip uygulanmayacagi.

    'none' icin None (surumde suzgec yok). Politikanin dil kisiti yoksa ya da dil
    kisitin icindeyse 'applied'; dil bilinmiyorsa 'applied_language_unknown';
    dil kisitin disindaysa 'not_evaluated' (hicbir satir kalite icin atilmaz)."""
    if policy not in SUPPORTED_QUALITY_POLICIES:
        raise ValueError(f"Unsupported quality policy: {policy!r}")
    if policy == QUALITY_POLICY_NONE:
        return None
    supported = QUALITY_POLICY_SUPPORTED_LANGUAGES.get(policy)
    if supported is None:
        return QUALITY_FILTER_STATUS_APPLIED
    if language is None or not language.strip():
        return QUALITY_FILTER_STATUS_APPLIED_LANGUAGE_UNKNOWN
    if normalize_language_tag(language) in supported:
        return QUALITY_FILTER_STATUS_APPLIED
    return QUALITY_FILTER_STATUS_NOT_EVALUATED


_WIKI_MARKUP_RE = re.compile(r'align="|\{\{|\}\}|\[\[|\]\]')

_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
_HASHTAG_RE = re.compile(r"(?<!\w)#[^\W_]+", re.UNICODE)
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
_SEGMENT_RE = re.compile(r"[\n\r]+|(?<=[.!?…])\s+")

_NAVIGATION_PATTERNS = (
    r"\bana\s+sayfa",
    r"\bhaber",
    r"\bgiriş",
    r"\bkayıt",
    r"\byorum",
    r"\bpaylaş",
    r"\bönceki",
    r"\bsonraki",
    r"\bkategor",
    r"\bmenü",
    r"\biletişim",
    r"\bhakkımızda",
    r"\barama",
    r"\bfacebook",
    r"\btwitter",
    r"\binstagram",
    r"\btakipçi",
    r"\bbeğeni",
)
_PROMOTION_PATTERNS = (
    r"\bhemen",
    r"\bücretsiz",
    r"\btıkla",
    r"\bkampanya",
    r"\bsatın\s+al",
    r"\biletişime\s+geç",
    r"\ben\s+iyi",
    r"\bkaliteli",
    r"\bhizmet",
    r"\bsite",
    r"\bonline",
    r"\bfiyat",
    r"\bsipariş",
)
_DATING_PATTERNS = (
    r"\barkadaş",
    r"\bsohbet",
    r"\bchat",
    r"\btanış",
    r"\bevlen",
    r"\bpartner",
    r"\bflört",
)
_OPTICS_PATTERNS = (
    r"\bdürbün",
    r"\bkamera",
    r"\bgece\s+görüş",
    r"\bgüvenlik\s+kam",
    r"\bcasus",
    r"\bzoom",
    r"\boptik",
)
_ADULT_SERVICE_PATTERNS = (
    r"\bescort",
    r"\beskort",
    r"\brandevu",
    r"\bmasaj",
    r"\bilan",
    r"\bbayan",
)
_SEXUAL_PHARMA_PATTERNS = (
    r"\bviagra",
    r"\bcialis",
    r"\blevitra",
    r"\bkamagra",
    r"\bsertleş",
    r"\biktidarsız",
    r"\bcinsel",
    r"\beczane",
    r"\bilaç",
)

_NAVIGATION_ANCHORS = (
    "ana",
    "haber",
    "giriş",
    "kayıt",
    "yorum",
    "paylaş",
    "önceki",
    "sonraki",
    "kategor",
    "menü",
    "iletişim",
    "hakkımızda",
    "arama",
    "facebook",
    "twitter",
    "instagram",
    "takipçi",
    "beğeni",
)
_PROMOTION_ANCHORS = (
    "hemen",
    "ücretsiz",
    "tıkla",
    "kampanya",
    "satın",
    "iletişime",
    "iyi",
    "kaliteli",
    "hizmet",
    "site",
    "online",
    "fiyat",
    "sipariş",
)
_DATING_ANCHORS = ("arkadaş", "sohbet", "chat", "tanış", "evlen", "partner", "flört")
_OPTICS_ANCHORS = ("dürbün", "kamera", "gece", "güvenlik", "casus", "zoom", "optik")
_ADULT_SERVICE_ANCHORS = ("escort", "eskort", "randevu", "masaj", "ilan", "bayan")
_SEXUAL_PHARMA_ANCHORS = (
    "viagra",
    "cialis",
    "levitra",
    "kamagra",
    "sertleş",
    "iktidarsız",
    "cinsel",
    "eczane",
    "ilaç",
)

_NAVIGATION_RE = None
_PROMOTION_RE = None
_DATING_RE = None
_OPTICS_RE = None
_ADULT_SERVICE_RE = None
_SEXUAL_PHARMA_RE = None

_REASON_ORDER = (
    "encoding_corruption",
    "wiki_markup_residue",
    "extreme_repetition",
    "hashtag_stuffing",
    "mixed_script_artifact",
    "repeated_segments",
    "navigation_boilerplate",
    "commercial_keyword_stuffing",
    "dating_spam_cluster",
    "optics_spam_cluster",
    "adult_service_spam_cluster",
    "sexual_pharma_spam_cluster",
)


@dataclass(frozen=True, slots=True)
class _LexiconStats:
    hits: int
    distinct: int


_EMPTY_LEXICON_STATS = _LexiconStats(hits=0, distinct=0)


def quality_rejection_reasons(text: str, policy: str) -> tuple[str, ...]:
    if policy == QUALITY_POLICY_NONE:
        return ()
    if policy == QUALITY_POLICY_TR_WEB_V1:
        return _tr_web_v1_rejection_reasons(text)
    if policy == QUALITY_POLICY_TR_WEB_V2:
        return _tr_web_v2_rejection_reasons(text)
    if policy == QUALITY_POLICY_TR_WEB_V3:
        return _tr_web_v3_rejection_reasons(text)
    raise ValueError(f"Unsupported quality policy: {policy!r}")


# ---------------------------------------------------------------------------
# tr-web-v3 (TASK-040). v1/v2 asagida oldugu gibi durur; v3 AYRI BIR DALDIR.
# ---------------------------------------------------------------------------
#
# Tasarim: v3 kendi tetiklerini sifirdan yazmaz. v2'nin gerekceleri iki kez
# sorulur -- bir kez TAM METINDE, bir kez GOVDEDE -- ve her aile kendi ikinci
# olcusunu ekler. Bunun uc sonucu var, ucu de olculdu:
#   1. Tekduzelik: oran ailesi yalniz v2'den daha gevsek olabilir (v2'nin
#      tuttugu 1.997 satirda 0 yeni atma).
#   2. Capraz ates yok: kural yalniz kendi tabakasinda konusur.
#   3. "Kuyruk sayfayi goturmuyor": tetik artik govdeye de soruluyor
#      (67 bin karakterlik roportaji sondaki yorum blogu atiyordu).
# Tek istisna tekrar ailesidir: `lz77 <= 260`, `zlib <= 180`in alt kumesi
# DEGILDIR. Bu bilerek boyledir (TASK-039): dogru hukum artik yorumlayicidan
# bagimsiz veriliyor.

_V3_UNTOUCHED_REASONS = (
    # Rafin olcumunde 50/50 dogru: kume fikri saglam, dort esik degil.
    "adult_service_spam_cluster",
    "mixed_script_artifact",
)
_V3_RATIO_FAMILY = (
    "encoding_corruption",
    "wiki_markup_residue",
    "navigation_boilerplate",
)
_V3_CLUSTER_FAMILY = (
    "hashtag_stuffing",
    "commercial_keyword_stuffing",
    "dating_spam_cluster",
    "optics_spam_cluster",
    "sexual_pharma_spam_cluster",
)
_V3_REPETITION_FAMILY = ("extreme_repetition", "repeated_segments")


_V3_CLUSTER_LEXICON = {
    "commercial_keyword_stuffing": lambda: _promotion_re(),
    "dating_spam_cluster": lambda: _dating_re(),
    "optics_spam_cluster": lambda: _optics_re(),
    "sexual_pharma_spam_cluster": lambda: _sexual_pharma_re(),
}


def _v3_cluster_density_exceeds(folded: str, word_count: int, reason: str) -> bool:
    """Kumenin KENDI sozlugunun TAM METINDEKI yogunlugu muafiyet tavanini
    asiyor mu (SIKI AYAR, 2026-09-21).

    `hashtag_stuffing` gevsek aileden cikarildi (`HASHTAG_EXEMPTION_ENABLED`):
    kural zaten yapisaldir, sozluk yogunlugu olcusu yoktur -> muafiyet yok.
    """
    if reason == "hashtag_stuffing":
        return not quality_v3.HASHTAG_EXEMPTION_ENABLED
    lexicon = _V3_CLUSTER_LEXICON.get(reason)
    if lexicon is None:
        return True
    hits = _lexicon_stats(lexicon(), folded).hits
    return quality_v3.cluster_density_exceeds(hits, word_count, reason)


def _tr_web_v3_rejection_reasons(text: str) -> tuple[str, ...]:
    v2_full = set(_tr_web_v2_rejection_reasons(text))
    matched = {reason for reason in _V3_UNTOUCHED_REASONS if reason in v2_full}

    # Oran ve kume aileleri ancak v2 o gerekceyi TAM METINDE uretmisse
    # konusabilir. Bunun sonucu olculebilir bir guvencedir: bu iki aile
    # v2'nin TUTTUGU hicbir belgeyi atamaz. (Kume ailesinde tam metin sarti
    # olmasaydi govde kirpmasi yogunlugu yukseltip 706 satirin birinde -- rafin
    # `good` dedigi bir sayfada -- yeni bir gerekce uretiyordu.)
    trigger = v2_full.intersection(_V3_RATIO_FAMILY + _V3_CLUSTER_FAMILY)
    if trigger:
        scope = body(text)
        signals = quality_v3.structural_signals(
            quality_v3.structural_stats(quality_v3.turkish_casefold(scope))
        )

        # --- oran ailesi: v2 tetigi (TAM METIN) + muafiyet olcusu ----------
        # SIKI AYAR (2026-09-21): "v2 govdede de basiyor mu" kapisi KALKTI.
        # Govde kirpmasinin kendisi bir muafiyet degildir; muafiyet acikca
        # olculur. Kurucunun B sayfasinda o kapidan 8 cop belge kaciyordu:
        # 3, 4, 6, 7, 49 (bozulma bastaki basligta, govdede U+FFFD yok) ve
        # 23, 28, 42 (gezinme tetigi govdede basmiyor). Tam metin tetigi
        # duruyor, yani v3 hala v2'nin TUTTUGU hicbir belgeyi atamaz.
        if "encoding_corruption" in trigger and quality_v3.encoding_corruption_ratio(
            text, scope
        ):
            matched.add("encoding_corruption")
        if "wiki_markup_residue" in trigger and quality_v3.wiki_prose_shortfall(
            scope, signals
        ):
            matched.add("wiki_markup_residue")
        if "navigation_boilerplate" in trigger and quality_v3.navigation_prose_shortfall(
            scope
        ):
            matched.add("navigation_boilerplate")

        # --- kume ailesi: yapisal sinyal (R1) + sozluk yogunlugu marji -----
        # Sozluk esikleri DEGISMEDI ve R1 yapilandirmasina dokunulmadi; siki
        # ayarin ekledigi tek sey "esik marji": yogunluk v2 esiginin
        # `CLUSTER_DENSITY_MARGIN` katina ulasiyorsa muafiyet yoktur.
        cluster_hits = [
            reason for reason in _V3_CLUSTER_FAMILY if reason in trigger
        ]
        if cluster_hits:
            relaxed = len(signals) < quality_v3.REQUIRED_STRUCTURAL_SIGNALS
            folded_full = _turkish_casefold(text)
            word_count = len(_WORD_RE.findall(folded_full))
            for reason in cluster_hits:
                if not relaxed or _v3_cluster_density_exceeds(
                    folded_full, word_count, reason
                ):
                    matched.add(reason)

    # Mojibake kolunun v2'de karsiligi yok, bu yuzden tetige baglanamaz; yeni
    # atma uretebilecegi icin KAPALI (gerekce: quality_v3.MOJIBAKE_BRANCH_ENABLED).
    # Ucuz yoklama once: govde tam metnin bir dilimi oldugu icin tam metinde
    # mojibake harfi yoksa govdede de yoktur.
    if (
        quality_v3.MOJIBAKE_BRANCH_ENABLED
        and quality_body.MOJIBAKE_PROBE_RE.search(text)
        and quality_v3.mojibake_corruption(text, body(text))
    ):
        matched.add("encoding_corruption")

    # --- tekrar ailesi: v2 cekirdegi, zlib yerine LZ77 (TASK-039) ----------
    # TAM METIN uzerinde: gerekcesi quality_v3.REPETITION_SCOPE'ta.
    matched.update(
        quality_v3.repetition_reasons(text, quality_v3.turkish_casefold(text))
    )

    return tuple(reason for reason in _REASON_ORDER if reason in matched)


def _tr_web_v2_rejection_reasons(text: str) -> tuple[str, ...]:
    matched: set[str] = set(_tr_web_v1_rejection_reasons(text))
    # U+FFFD: kaynak kodlamasi cozulurken kaybolmus harf. Onarilamaz; belge atilir.
    if "�" in text:
        matched.add("encoding_corruption")
    # MediaWiki tablo/sablon/baglanti isaretlemesi metin degildir.
    if _WIKI_MARKUP_RE.search(text) or text.count("||") >= 2:
        matched.add("wiki_markup_residue")
    return tuple(reason for reason in _REASON_ORDER if reason in matched)


def _tr_web_v1_rejection_reasons(text: str) -> tuple[str, ...]:
    # The filter never returns source text or matched terms. All decisions require
    # structural evidence or multiple independent lexical signals.
    hashtag_gate = text.count("#") >= 50
    soft_hyphen_gate = text.count("\u00ad") >= 20
    folded = _turkish_casefold(text)
    matched: set[str] = set()

    # Five hundred one-character tokens need at least 500 word characters and
    # 499 separators. The two shorter-document rules keep their own explicit
    # gates, so this return is mathematically exact rather than heuristic.
    if len(folded) < 999 and not hashtag_gate and not soft_hyphen_gate:
        return ()

    word_count = len(_WORD_RE.findall(folded))
    hashtag_count = 0
    if hashtag_gate:
        hashtag_count = _count_matches(_HASHTAG_RE, folded)
        if hashtag_count >= 50 and _rate_at_least(hashtag_count, word_count, 50):
            matched.add("hashtag_stuffing")

    if soft_hyphen_gate and _has_mixed_script_artifact(text, folded):
        matched.add("mixed_script_artifact")

    if word_count < 500:
        return tuple(reason for reason in _REASON_ORDER if reason in matched)

    raw_bytes = text.encode("utf-8")
    compressed_enough = (
        bool(raw_bytes)
        and len(zlib.compress(raw_bytes, level=9)) * 100 <= len(raw_bytes) * 18
    )

    duplicate_segment_instances = 0
    segment_count = 0
    if word_count >= 1_500:
        duplicate_segment_instances, segment_count = _duplicate_segment_counts(folded)

    words: list[str] | None = None
    unique_fivegrams: int | None = None
    fivegram_count = max(0, word_count - 4)

    def unique_fivegram_count() -> int:
        nonlocal unique_fivegrams, words
        if unique_fivegrams is None:
            words = _WORD_RE.findall(folded)
            unique_fivegrams = len(
                {
                    (words[index], words[index + 1], words[index + 2], words[index + 3], words[index + 4])
                    for index in range(fivegram_count)
                }
            )
        return unique_fivegrams

    if (
        compressed_enough
        and fivegram_count > 0
        and unique_fivegram_count() * 100 <= fivegram_count * 60
    ):
        matched.add("extreme_repetition")

    if word_count >= 1_500 and _fraction_at_least(
        duplicate_segment_instances,
        segment_count,
        numerator=20,
        denominator=100,
    ):
        if fivegram_count > 0 and unique_fivegram_count() * 100 <= fivegram_count * 70:
            matched.add("repeated_segments")

    if word_count < 1_000:
        return tuple(reason for reason in _REASON_ORDER if reason in matched)

    navigation = _lexicon_stats_if_relevant(
        _navigation_re(),
        folded,
        _NAVIGATION_ANCHORS,
    )
    promotion = _lexicon_stats_if_relevant(
        _promotion_re(),
        folded,
        _PROMOTION_ANCHORS,
    )
    dating = _EMPTY_LEXICON_STATS
    adult_service = _EMPTY_LEXICON_STATS
    if promotion.distinct >= 3 or navigation.distinct >= 3:
        dating = _lexicon_stats_if_relevant(
            _dating_re(),
            folded,
            _DATING_ANCHORS,
        )
        adult_service = _lexicon_stats_if_relevant(
            _adult_service_re(),
            folded,
            _ADULT_SERVICE_ANCHORS,
        )
    optics = _EMPTY_LEXICON_STATS
    sexual_pharma = _EMPTY_LEXICON_STATS
    if promotion.distinct >= 3:
        optics = _lexicon_stats_if_relevant(
            _optics_re(),
            folded,
            _OPTICS_ANCHORS,
        )
        sexual_pharma = _lexicon_stats_if_relevant(
            _sexual_pharma_re(),
            folded,
            _SEXUAL_PHARMA_ANCHORS,
        )

    url_count: int | None = None
    phone_count: int | None = None

    def urls() -> int:
        nonlocal url_count
        if url_count is None:
            url_count = _count_matches(_URL_RE, folded)
        return url_count

    def phones() -> int:
        nonlocal phone_count
        if phone_count is None:
            phone_count = _count_matches(_PHONE_RE, folded)
        return phone_count

    if (
        word_count >= 1_500
        and navigation.distinct >= 5
        and _rate_at_least(navigation.hits, word_count, 4)
    ):
        repeated_navigation = _fraction_at_least(
            duplicate_segment_instances,
            segment_count,
            numerator=5,
            denominator=100,
        )
        if promotion.distinct >= 5 or repeated_navigation:
            matched.add("navigation_boilerplate")
        else:
            if hashtag_count == 0 and "#" in text:
                hashtag_count = _count_matches(_HASHTAG_RE, folded)
            if urls() + hashtag_count >= 10:
                matched.add("navigation_boilerplate")

    if (
        word_count >= 1_500
        and promotion.distinct >= 6
        and _rate_at_least(promotion.hits, word_count, 10)
    ):
        if navigation.distinct >= 3 or phones() + urls() >= 2:
            matched.add("commercial_keyword_stuffing")

    if (
        dating.distinct >= 3
        and _rate_at_least(dating.hits, word_count, 8)
        and (promotion.distinct >= 3 or navigation.distinct >= 3)
    ):
        matched.add("dating_spam_cluster")

    if (
        optics.distinct >= 3
        and _rate_at_least(optics.hits, word_count, 8)
        and promotion.distinct >= 3
    ):
        matched.add("optics_spam_cluster")

    if (
        adult_service.distinct >= 3
        and _rate_at_least(adult_service.hits, word_count, 8)
        and (promotion.distinct >= 3 or navigation.distinct >= 3)
    ):
        matched.add("adult_service_spam_cluster")

    if (
        sexual_pharma.distinct >= 3
        and _rate_at_least(sexual_pharma.hits, word_count, 8)
        and promotion.distinct >= 3
    ):
        matched.add("sexual_pharma_spam_cluster")

    return tuple(reason for reason in _REASON_ORDER if reason in matched)


def _turkish_casefold(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return normalized.replace("I", "ı").replace("İ", "i").casefold()


def _has_mixed_script_artifact(text: str, folded: str) -> bool:
    cyrillic_count = 0
    for character in text:
        if "CYRILLIC" in unicodedata.name(character, ""):
            cyrillic_count += 1
            if cyrillic_count >= 20:
                break
    if cyrillic_count < 20:
        return False

    mixed_tokens = 0
    for match in _WORD_RE.finditer(folded):
        word = match.group(0)
        has_latin = False
        has_cyrillic = False
        for character in word:
            name = unicodedata.name(character, "")
            has_latin = has_latin or "LATIN" in name
            has_cyrillic = has_cyrillic or "CYRILLIC" in name
            if has_latin and has_cyrillic:
                mixed_tokens += 1
                break
        if mixed_tokens >= 20:
            return True
    return False


def _duplicate_segment_counts(text: str) -> tuple[int, int]:
    segment_counts: dict[str, int] = {}
    segment_count = 0
    for raw_segment in _SEGMENT_RE.split(text):
        normalized = " ".join(match.group(0) for match in _WORD_RE.finditer(raw_segment))
        if len(normalized) < 20:
            continue
        segment_count += 1
        segment_counts[normalized] = segment_counts.get(normalized, 0) + 1
    duplicate_instances = sum(count for count in segment_counts.values() if count > 1)
    return duplicate_instances, segment_count


def _compile_lexicon(patterns: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(f"(?P<t{index}>{pattern})" for index, pattern in enumerate(patterns))
    return re.compile(alternatives)


def _navigation_re() -> re.Pattern[str]:
    global _NAVIGATION_RE
    if _NAVIGATION_RE is None:
        _NAVIGATION_RE = _compile_lexicon(_NAVIGATION_PATTERNS)
    return _NAVIGATION_RE


def _promotion_re() -> re.Pattern[str]:
    global _PROMOTION_RE
    if _PROMOTION_RE is None:
        _PROMOTION_RE = _compile_lexicon(_PROMOTION_PATTERNS)
    return _PROMOTION_RE


def _dating_re() -> re.Pattern[str]:
    global _DATING_RE
    if _DATING_RE is None:
        _DATING_RE = _compile_lexicon(_DATING_PATTERNS)
    return _DATING_RE


def _optics_re() -> re.Pattern[str]:
    global _OPTICS_RE
    if _OPTICS_RE is None:
        _OPTICS_RE = _compile_lexicon(_OPTICS_PATTERNS)
    return _OPTICS_RE


def _adult_service_re() -> re.Pattern[str]:
    global _ADULT_SERVICE_RE
    if _ADULT_SERVICE_RE is None:
        _ADULT_SERVICE_RE = _compile_lexicon(_ADULT_SERVICE_PATTERNS)
    return _ADULT_SERVICE_RE


def _sexual_pharma_re() -> re.Pattern[str]:
    global _SEXUAL_PHARMA_RE
    if _SEXUAL_PHARMA_RE is None:
        _SEXUAL_PHARMA_RE = _compile_lexicon(_SEXUAL_PHARMA_PATTERNS)
    return _SEXUAL_PHARMA_RE


def _lexicon_stats_if_relevant(
    pattern: re.Pattern[str],
    text: str,
    anchors: tuple[str, ...],
) -> _LexiconStats:
    present = 0
    for anchor in anchors:
        if anchor not in text:
            continue
        present += 1
        if present >= 3:
            return _lexicon_stats(pattern, text)
    return _EMPTY_LEXICON_STATS


def _lexicon_stats(pattern: re.Pattern[str], text: str) -> _LexiconStats:
    hits = 0
    matched_terms: set[str] = set()
    for match in pattern.finditer(text):
        hits += 1
        assert match.lastgroup is not None
        matched_terms.add(match.lastgroup)
    return _LexiconStats(hits=hits, distinct=len(matched_terms))


def _count_matches(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def _rate_at_least(hits: int, total: int, per_thousand: int) -> bool:
    return total > 0 and hits * 1_000 >= total * per_thousand


def _fraction_at_least(
    part: int,
    total: int,
    *,
    numerator: int,
    denominator: int,
) -> bool:
    return total > 0 and part * denominator >= total * numerator


__all__ = [
    "QUALITY_FILTER_STATUS_APPLIED",
    "QUALITY_FILTER_STATUS_APPLIED_LANGUAGE_UNKNOWN",
    "QUALITY_FILTER_STATUS_NOT_EVALUATED",
    "QUALITY_POLICY_NONE",
    "QUALITY_POLICY_SUPPORTED_LANGUAGES",
    "QUALITY_POLICY_TR_WEB_V1",
    "QUALITY_POLICY_TR_WEB_V2",
    "QUALITY_POLICY_TR_WEB_V3",
    "SUPPORTED_QUALITY_POLICIES",
    "quality_filter_status",
    "quality_rejection_reasons",
]
