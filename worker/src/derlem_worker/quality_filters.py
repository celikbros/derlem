from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
import zlib


QUALITY_POLICY_NONE = "none"
QUALITY_POLICY_TR_WEB_V1 = "tr-web-v1"
SUPPORTED_QUALITY_POLICIES = frozenset(
    {
        QUALITY_POLICY_NONE,
        QUALITY_POLICY_TR_WEB_V1,
    }
)

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
    if policy != QUALITY_POLICY_TR_WEB_V1:
        raise ValueError(f"Unsupported quality policy: {policy!r}")
    return _tr_web_v1_rejection_reasons(text)


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
    "QUALITY_POLICY_NONE",
    "QUALITY_POLICY_TR_WEB_V1",
    "SUPPORTED_QUALITY_POLICIES",
    "quality_rejection_reasons",
]
