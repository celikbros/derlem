"""Govde cikarimi: kalite kurallarinin OLCUM KAPSAMI (TASK-040, tr-web-v3).

Bu modul saf olcum yardimcilaridir. Hicbir metni yerinde temizlemez; saklanan
metin her zaman TAM METINDIR (docs/data_governance.md). `body()` bir kirpma
degil, bir *kapsam* dondurur: kurallar belgenin govdesine bakar, boru hatti tam
metni yazar.

tr-web-v1 ve tr-web-v2 bu modulu KULLANMAZ; onlarin kod yollari degismedi.

Ortak varsayim (ana korpusun bicimi)
-----------------------------------
Ana korpusta bir belge = bir FIZIKSEL satir: satir sonu yok, sekme yok, art
arda iki bosluk yok. Bu yuzden "paragraf" diye bir sey yoktur ve govde sabit
genislikte SOZCUK BLOKLARI uzerinden hesaplanir. Girdide satir sonu varsa kod
yine calisir (satir sonu bosluktur), bloklama degismez.

Butun esikler tamsayi karsilastirmasina cevrilmistir (kayan nokta yok):
yorumlayicidan bagimsizlik TASK-039'un kabul olcutudur.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


# ---------------------------------------------------------------------------
# Esikler (var/olcum-2026-09-20/task-040-oran-ailesi/RAPOR.md §1)
# ---------------------------------------------------------------------------

BODY_BLOCK_WORDS = 24
"""Bir blok kac sozcuk. 24 ~ iki kisa cumle; menu dizileri bundan uzundur."""

BODY_MIN_WORDS = 120
"""Bundan kisa belgede govde cikarimi yapilmaz (govde = metnin tamami)."""

BODY_PROSE_FUNCTION_WORDS_PER_100 = 12
"""Blok duzyazi sayilsin diye 100 sozcukte en az kac islev sozcugu gerekir."""

BODY_PROSE_VERBS_PER_100 = 8
"""Islev sozcugu yarim esikteyken aranan cekimli yuklem yogunlugu."""

BODY_PROSE_RUN = 1
"""Kirpma nerede durur: art arda bu kadar duzyazi blogu gorulunce. 1 = en
temkinli (ilk duzyazi blogunda durur); gercek duzyazi bastan/sondan asla
kirpilmaz. RUN=2 denendi ve atildi: Lagrange mekanigi maddesinin acilis
cumleleri kirpiliyordu."""

BODY_MAX_HEAD_TRIM_NUM, BODY_MAX_HEAD_TRIM_DEN = 1, 2
"""Bastan en cok metnin yarisi kirpilir; asilirsa hic kirpilmaz."""

BODY_MAX_TAIL_TRIM_NUM, BODY_MAX_TAIL_TRIM_DEN = 1, 2
"""Sondan en cok metnin yarisi kirpilir."""

BODY_MIN_KEEP_NUM, BODY_MIN_KEEP_DEN = 1, 4
"""Govde metnin en az dortte biri olmali; degilse govde = metnin tamami."""

MENU_BLOCK_DEFINITION = "duzyazi-degil"
"""Menu blogu tanimi: bkz. `menu_block_indices`. Iki aday olculdu; digeri
('cumlesiz') nav tabakasinda hic ayirt etmiyordu."""

MENU_NAV_ANCHORS_PER_BLOCK = 3
"""Blokta bu kadar gezinme demeti varsa duzyazi olcutunu gecse de menudur."""


# ---------------------------------------------------------------------------
# Duzenli ifadeler ve sozlukler
# ---------------------------------------------------------------------------
#
# WORD_RE ve SEGMENT_RE, quality_filters.py'deki v1/v2 karsiliklariyla BIREBIR
# ayni olmak zorundadir; kopya, cunku v1/v2 kod yoluna dokunulmuyor. Kaymayi
# test yakalar (worker/tests/test_quality_filters.py, sozlesme testleri).
WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)

# Turkce islev sozcukleri: duzyazida her yerde, menude/listede/tabloda yok.
# Konu sozlugu DEGILDIR (raf mektubu §3a: "konuya degil usluba bak").
BODY_FUNCTION_WORDS = frozenset(
    """
    ve veya ya da ile ama ancak fakat lakin çünkü eğer ki ise de da
    bir bu şu o bunu bunun buna bunlar şunu onun ona onu onlar onlara
    ben sen biz siz kendi kendisi kendini
    için gibi kadar sonra önce göre üzere karşı rağmen dolayı beri doğru
    daha çok az en hem bile yine artık zaten sadece ayrıca henüz hâlâ hala
    var yok değil olan olarak oldu olduğu olduğunu olmak olur olsa oluyor
    ne nasıl neden niçin hangi kim nerede niye
    her bazı birçok tüm bütün hiç herhangi birkaç
    şey şekilde durumda halde yerine arasında içinde üzerinde altında yanında
    ediyor etti etmek eden edilen yapılan yapılır yaptı diye dedi demek
    böyle şöyle işte oysa yoksa iken dahi
    """.split()
)

# Fiil/yuklem cekim ekleri. Idari-hukuki Turkce islev sozcugunu az kullanir ama
# her cumlede cekimli yuklem vardir; menu/tablo parcasinda yoktur. Olculdu:
# islev sozcugu orani TFF disiplin metninde %3,6, TripAdvisor menusunde %7,6 --
# SIRALAMA TERS. Bu yuzden ikinci yol sart.
VERB_SUFFIX_RE = re.compile(
    r"(?:"
    r"(?:m[ıiuü]ş|d[ıiuü]|t[ıiuü])(?:t[ıiuü]r|d[ıiuü]r|lar|ler|m|n|k|nız|niz|nuz|nüz)?"
    r"|[ıiuü]yor(?:du|muş|lar|ler)?"
    r"|(?:a|e)ca[kğ][ıi]?(?:t[ıiuü]r|lar|ler)?"
    r"|(?:a|e)ce[kğ][ıi]?(?:t[ıiuü]r|lar|ler)?"
    r"|m(?:a|e)kt(?:a|e)d[ıiuü]r"
    r"|[ıiuü]l(?:m[ıiuü]ş|d[ıiuü])"
    r"|d[ıiuü]r|t[ıiuü]r"
    r")$"
)

SENTENCE_END_RE = re.compile(r"[.!?…](?:\s|$)")

# Cift kodlama izi (Ã¼ / ÅŸ / Ä± / â€™ ...). U+FFFD'den BAGIMSIZ ikinci sinyal.
MOJIBAKE_RE = re.compile(
    r"[ÃÅÄ][-ſ–—‘’“”"
    r"€ -¿]"
    r"|â€[-¿‘-”¦]"
    r"|Â[ -¿]"
)
# Ucuz on yoklama: mojibake dizilerinin hepsi bu bes harften biriyle baslar.
MOJIBAKE_PROBE_RE = re.compile(r"[ÃÅÄâÂ]")

REPLACEMENT_CHARACTER = "�"

# --- isaretleme / makine verisi kaliplari ---------------------------------
_WIKI_INNER_TEMPLATE_RE = re.compile(r"\{\{(?:(?!\{\{|\}\}).)*\}\}", re.DOTALL)
_WIKI_ORPHAN_RE = re.compile(r"\{\{|\}\}|\[\[|\]\]")
_WIKI_TABLE_RE = re.compile(r"\{\|.*?\|\}", re.DOTALL)
_WIKI_ROW_RE = re.compile(r"\|-+\s*(?:[|!][^|!]*)*")
_WIKI_CELL_RE = re.compile(r"\|\|[^|]*|!![^!]*")
_HTML_ATTR_RE = re.compile(
    r"\b(?:align|valign|width|height|colspan|rowspan|bgcolor|style|class|scope)"
    r"\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s|]+)",
    re.IGNORECASE,
)
# Gomulu JSON/JS yapilandirma blogu: `wiki_markup_residue` tabakasindaki dogru
# atmalarin cogunda `}}` wiki sablonundan degil, TripAdvisor widget'larinin ham
# JSON'undan geliyor. Bu tetigi genisletmez, yalniz DUZYAZI olcumunu duzeltir.
_JSON_PAIR_RE = re.compile(
    r"\"[A-Za-z_][A-Za-z0-9_]*\"\s*:\s*(?:\"[^\"]*\"|null|true|false|\d+|\{|\[|,)"
)
_JSON_PUNCT_RE = re.compile(r"[{}\[\]](?=[\",{}\[\]]|$)")
_JS_CALL_RE = re.compile(r"\([A-Za-z_][\w.]*\.[\w.]*\([^()]*\)[^()]*\)")

# Gezinme demeti (blok duzeyinde). Tek basina guvenilmez (asagiya bakin), ancak
# v2 tetiginin arkasinda kullanilir.
NAVIGATION_BLOCK_ANCHORS = (
    "ana sayfa", "anasayfa", "haberler", "giriş yap", "üye ol", "kayıt ol",
    "yorum yaz", "yorumlar", "paylaş", "önceki", "sonraki", "kategori",
    "kategoriler", "menü", "iletişim", "hakkımızda", "arama",
    "facebook", "twitter", "instagram", "takipçi", "beğeni", "abone ol",
    "gizlilik", "kullanım koşulları", "künye", "site haritası", "tümünü gör",
    "devamını oku", "etiketler", "yorum yap", "sepet", "rezervasyon",
    "albümü görüntüle", "tüm hakları",
)


@dataclass(frozen=True, slots=True)
class Block:
    """Sabit genislikte sozcuk blogu; `start`/`end` metindeki karakter araligi."""

    start: int
    end: int
    words: int
    function_words: int
    verbs: int
    sentence_ends: int
    is_prose: bool


@dataclass(frozen=True, slots=True)
class EncodingStats:
    """U+FFFD ve mojibake sayimi. Oranlar TAMSAYI binde/on-binde olarak
    karsilastirilir; burada ham sayilar tasinir."""

    scope_chars: int
    replacement_count: int
    replacement_outside_tail: int
    mojibake_count: int


@dataclass(frozen=True, slots=True)
class ProseStats:
    """Bir kalinti turu bosaltildiktan sonra ayakta kalan duzyazi."""

    scope_chars: int
    scope_words: int
    residue_chars: int
    prose_chars: int
    prose_blocks: int


def turkish_fold_preserving_length(text: str) -> str:
    """Konum koruyan Turkce kucultme.

    NFKC ya da casefold uzunlugu degistirirse (ligatur, 'İ' ayrismasi...) daha
    temkinli `lower()` yoluna duser. Konumlar korunmak zorundadir: blok
    sinirlari ham metnin indisleridir.
    """
    normalized = unicodedata.normalize("NFKC", text)
    if len(normalized) != len(text):
        return text.replace("I", "ı").replace("İ", "i").lower()
    folded = normalized.replace("I", "ı").replace("İ", "i").casefold()
    if len(folded) != len(text):
        return text.replace("I", "ı").replace("İ", "i").lower()
    return folded


def _word_spans(text: str) -> list[tuple[int, int, str]]:
    folded = turkish_fold_preserving_length(text)
    return [
        (match.start(), match.end(), folded[match.start() : match.end()])
        for match in WORD_RE.finditer(text)
    ]


def blocks(text: str) -> list[Block]:
    """Metni `BODY_BLOCK_WORDS` sozcukluk bloklara boler ve her blogu siniflar.

    Blok duzyazi sayilir:
      * 100 sozcukte en az `BODY_PROSE_FUNCTION_WORDS_PER_100` islev sozcugu, YA DA
      * islev sozcugu yarim esikteyse ama blokta cekimli yuklem yogunlugu
        `BODY_PROSE_VERBS_PER_100`'u buluyor ve en az bir cumle sonu varsa
        (resmi/idari Turkce bu ikinci yoldan gecer).
    """
    spans = _word_spans(text)
    out: list[Block] = []
    for index in range(0, len(spans), BODY_BLOCK_WORDS):
        chunk = spans[index : index + BODY_BLOCK_WORDS]
        if not chunk:
            continue
        start = chunk[0][0]
        end = chunk[-1][1]
        words = len(chunk)
        function_words = sum(1 for _, _, word in chunk if word in BODY_FUNCTION_WORDS)
        verbs = sum(1 for _, _, word in chunk if VERB_SUFFIX_RE.search(word))
        sentence_ends = len(SENTENCE_END_RE.findall(text[start:end]))
        dense = function_words * 100 >= words * BODY_PROSE_FUNCTION_WORDS_PER_100
        half = function_words * 200 >= words * BODY_PROSE_FUNCTION_WORDS_PER_100
        formal = half and verbs * 100 >= words * BODY_PROSE_VERBS_PER_100 and sentence_ends >= 1
        out.append(
            Block(
                start=start,
                end=end,
                words=words,
                function_words=function_words,
                verbs=verbs,
                sentence_ends=sentence_ends,
                is_prose=dense or formal,
            )
        )
    return out


def _first_prose_run(chunks: list[Block], *, reverse: bool) -> int | None:
    order = range(len(chunks) - 1, -1, -1) if reverse else range(len(chunks))
    step = -1 if reverse else 1
    for index in order:
        run = 0
        cursor = index
        while 0 <= cursor < len(chunks) and chunks[cursor].is_prose:
            run += 1
            if run >= BODY_PROSE_RUN:
                return index
            cursor += step
    return None


def body_span(text: str) -> tuple[int, int]:
    """Govdenin metindeki [start, end) karakter araligi; kirpilamazsa
    (0, len(text)). Sozlesme icin `body`e bakin."""
    length = len(text)
    chunks = blocks(text)
    if sum(chunk.words for chunk in chunks) < BODY_MIN_WORDS or len(chunks) < 3:
        return (0, length)

    head = _first_prose_run(chunks, reverse=False)
    tail = _first_prose_run(chunks, reverse=True)
    if head is None or tail is None or tail < head:
        return (0, length)

    start = chunks[head].start
    end = chunks[tail].end
    if start * BODY_MAX_HEAD_TRIM_DEN > length * BODY_MAX_HEAD_TRIM_NUM:
        start = 0
    if (length - end) * BODY_MAX_TAIL_TRIM_DEN > length * BODY_MAX_TAIL_TRIM_NUM:
        end = length
    if (end - start) * BODY_MIN_KEEP_DEN < length * BODY_MIN_KEEP_NUM:
        return (0, length)
    return (start, end)


def body(text: str) -> str:
    """Belgenin govdesi: bastaki gezinme/menu dizisi ve sondaki yorum/altbilgi
    blogu kirpilmis hali. tr-web-v3 kurallari bunun uzerinde calisir; SAKLANAN
    METIN her zaman tam metindir (data_governance.md: yerinde temizleme yok).

    SOZLESME (var/olcum-2026-09-20/task-040-oran-ailesi/RAPOR.md §1; testleri
    worker/tests/test_quality_body.py)
    -----------------------------------------------------------------------
    S1  Saf fonksiyon: yan etkisiz; dosya/ag/saat/rastgelelik yok; ayni girdi
        ayni cikti.
    S2  Dilim: `body(text) == text[start:end]`, `(start, end) = body_span(text)`.
        Hicbir karakter yeniden yazilmaz, normallestirilmez, kucultulmez.
    S3  Bitisik: cikti metnin BITISIK bir parcasidir (`body(text) in text`).
        Yalniz bastan ve sondan kirpar; ortadan hicbir sey atmaz.
    S4  Emin degilse kirpmaz -- `body(text) == text` doner. Ozellikle belge
        `BODY_MIN_WORDS` sozcukten kisaysa, bastaki/sondaki kirpma metnin
        yarisini geciyorsa ya da geriye metnin dortte birinden azi kalacaksa.
        Dolayisiyla her zaman `4 * len(body(text)) >= len(text)` ve
        `body("") == ""`.
    S5  Etkisizlesen: `body(body(t)) == body(t)`. Sozlesmenin zorunlu parcasi
        degildir ama kurallarin ikinci kez cagirmasi guvenlidir.
    S6  Oteki aileler (kume/yineleme) kendi olcumlerini `body(text)` uzerinde
        yapar. Blok bazli siniflama gerekiyorsa `blocks(text)` dogrudan
        kullanilabilir; ikisi de disa acik ve saftir.
    """
    start, end = body_span(text)
    return text[start:end]


# ---------------------------------------------------------------------------
# "Kirpinca ne kaliyor" makinesi
# ---------------------------------------------------------------------------


def _blank(text: str, pattern: re.Pattern[str]) -> tuple[str, int]:
    """Kaliba uyan parcalari BOSLUKLA doldurur; uzunluk ve konumlar korunur."""
    removed = 0
    pieces: list[str] = []
    cursor = 0
    for match in pattern.finditer(text):
        pieces.append(text[cursor : match.start()])
        pieces.append(" " * (match.end() - match.start()))
        removed += match.end() - match.start()
        cursor = match.end()
    pieces.append(text[cursor:])
    return "".join(pieces), removed


def strip_markup(text: str) -> tuple[str, int]:
    """Wiki isaretlemesi + HTML oznitelik kalintisi + gomulu JSON/JS'i bosaltir.

    Donen metin girdiyle AYNI UZUNLUKTADIR (bosaltilan yerler bosluk); ikinci
    deger bosaltilan karakter sayisidir. Bu bir temizleme degil bir OLCUM
    yardimcisidir: ciktisi hicbir yere yazilmaz, saklanan metin degismez.
    """
    removed = 0
    current = text
    for _ in range(6):  # ic ice sablonlar: icten disa
        current, count = _blank(current, _WIKI_INNER_TEMPLATE_RE)
        removed += count
        if not count:
            break
    for pattern in (
        _WIKI_TABLE_RE,
        _WIKI_ROW_RE,
        _WIKI_CELL_RE,
        _HTML_ATTR_RE,
        _JS_CALL_RE,
        _JSON_PAIR_RE,
        _JSON_PUNCT_RE,
        _WIKI_ORPHAN_RE,
    ):
        current, count = _blank(current, pattern)
        removed += count
    return current, removed


def _prose_chars(piece: str) -> int:
    """Bir blok diliminde ayakta kalan duzyazi karakteri (bosaltilanlar haric)."""
    words = WORD_RE.findall(piece)
    if not words:
        return 0
    return sum(len(word) for word in words) + len(words) - 1


def menu_block_indices(
    scope: str,
    chunks: list[Block],
    *,
    definition: str = MENU_BLOCK_DEFINITION,
) -> set[int]:
    """Menu/liste blogu tanimi.

    'duzyazi-degil': blok duzyazi olcutunu gecemiyorsa ya da icinde
    `MENU_NAV_ANCHORS_PER_BLOCK` gezinme demeti varsa menudur.

    UYARI: bu tanim TEK BASINA guvenilmez. v2 tetigi olmadan kullanildiginda
    Kayseri Buyuksehir meclis karar ozetlerini, MYK yeterlilik belgelerini,
    Resmi Gazete yapi denetim kararlarini ve 67 bin karakterlik bir roportaji
    menu saniyordu (148 iyi satirin 27'sine basiyordu). v2 tetiginin arkasinda
    ayni sayi 1'e dustu. Bu tanimi baska bir kural yeniden kullanacaksa once
    kendi olcumunu yapmalidir.
    """
    if definition != MENU_BLOCK_DEFINITION:
        raise ValueError(f"unknown menu definition: {definition!r}")
    folded = turkish_fold_preserving_length(scope)
    marked: set[int] = set()
    for index, chunk in enumerate(chunks):
        window = folded[chunk.start : chunk.end]
        navigation_hits = sum(1 for anchor in NAVIGATION_BLOCK_ANCHORS if anchor in window)
        if not chunk.is_prose or navigation_hits >= MENU_NAV_ANCHORS_PER_BLOCK:
            marked.add(index)
    return marked


def prose_after_strip(scope: str, *, strip: str) -> ProseStats:
    """`scope` (govde) icinden `strip` turu kalintiyi dusunce kalan duzyazi.

    strip='markup'     : isaretleme/makine verisi bosaltilir, ayakta kalan
                         duzyazi bloklari sayilir.
    strip='navigation' : menu bloklari duser, kalan her sey govde metni sayilir.
    """
    if not scope:
        return ProseStats(0, 0, 0, 0, 0)
    if strip == "markup":
        cleaned, residue = strip_markup(scope)
        chunks = blocks(cleaned)
        skipped = {index for index, chunk in enumerate(chunks) if not chunk.is_prose}
    elif strip == "navigation":
        cleaned = scope
        chunks = blocks(cleaned)
        skipped = menu_block_indices(scope, chunks)
        residue = sum(chunks[index].end - chunks[index].start for index in skipped)
    else:
        raise ValueError(f"unknown strip: {strip!r}")

    prose_chars = 0
    prose_blocks = 0
    for index, chunk in enumerate(chunks):
        if index in skipped:
            continue
        prose_chars += _prose_chars(cleaned[chunk.start : chunk.end])
        prose_blocks += 1
    return ProseStats(
        scope_chars=len(scope),
        scope_words=sum(chunk.words for chunk in chunks),
        residue_chars=residue,
        prose_chars=prose_chars,
        prose_blocks=prose_blocks,
    )


def encoding_stats(text: str, scope: str, *, tail_chars: int) -> EncodingStats:
    """U+FFFD sayimi/konumu ve mojibake sayimi.

    Sayim GOVDEDE yapilir; kuyruk muafiyeti TAM metnin sonuna bakar, cunku
    kesilmis son UTF-8 bayti orada durur.
    """
    outside = 0
    if REPLACEMENT_CHARACTER in text:
        outside = text[: max(0, len(text) - tail_chars)].count(REPLACEMENT_CHARACTER)
    # Mojibake taramasi her belgede kosmaz: once tek gecislik ucuz bir yoklama.
    mojibake = 0
    if MOJIBAKE_PROBE_RE.search(scope):
        mojibake = len(MOJIBAKE_RE.findall(scope))
    return EncodingStats(
        scope_chars=len(scope),
        replacement_count=scope.count(REPLACEMENT_CHARACTER),
        replacement_outside_tail=outside,
        mojibake_count=mojibake,
    )


__all__ = [
    "BODY_BLOCK_WORDS",
    "BODY_FUNCTION_WORDS",
    "BODY_MIN_WORDS",
    "BODY_PROSE_FUNCTION_WORDS_PER_100",
    "BODY_PROSE_RUN",
    "Block",
    "EncodingStats",
    "MENU_BLOCK_DEFINITION",
    "ProseStats",
    "REPLACEMENT_CHARACTER",
    "WORD_RE",
    "blocks",
    "body",
    "body_span",
    "encoding_stats",
    "menu_block_indices",
    "prose_after_strip",
    "strip_markup",
    "turkish_fold_preserving_length",
]
