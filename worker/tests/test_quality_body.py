"""`body()` sozlesmesi (TASK-040, tr-web-v3 olcum kapsami).

Sozlesmenin metni `derlem_worker.quality_body.body`'nin belgesindedir; burasi
onun sinanmasidir. Sozlesme ihlali sessizce gecmemelidir: kurallar govdeye
bakiyor, saklanan metin ise tam metin -- ikisi arasindaki iliski yazili olmali.
"""

from __future__ import annotations

import pytest

from derlem_worker import quality_filters
from derlem_worker.quality_body import (
    BODY_BLOCK_WORDS,
    BODY_MIN_KEEP_DEN,
    BODY_MIN_KEEP_NUM,
    WORD_RE,
    Block,
    blocks,
    body,
    body_span,
    menu_block_indices,
    prose_after_strip,
    strip_markup,
)

# Ana korpusun bicimi: bir belge = bir fiziksel satir, satir ici bosluk tek
# bosluk. Test belgeleri de oyle yazilmistir.

MENU = (
    "ana sayfa haberler giriş yap üye ol kayıt ol yorum yaz yorumlar paylaş "
    "önceki sonraki kategori kategoriler menü iletişim hakkımızda arama "
    "facebook twitter instagram takipçi beğeni abone ol gizlilik künye "
    "site haritası tümünü gör devamını oku etiketler sepet rezervasyon"
)

_CONTENT = (
    "ulaşım politikası kent araştırma veri öğrenci belediye üniversite proje "
    "rapor bölge tarım sanayi enerji iklim orman su toprak sağlık eğitim kültür "
    "tarih coğrafya deniz liman demiryolu köprü tünel yol trafik otobüs metro "
    "tramvay bisiklet yaya sokak mahalle ilçe şehir köy nüfus gelir bütçe vergi "
    "yatırım istihdam işsizlik üretim tüketim ihracat ithalat piyasa fiyat "
    "maliyet verimlilik teknoloji yazılım donanım ağ sistem yöntem model ölçüm "
    "deney gözlem kuram uygulama sonuç bulgu öneri karar süreç aşama"
).split()
_FUNCTION = (
    "ve bu için gibi kadar ancak çünkü daha çok ile olarak bir her hem ise "
    "sonra önce göre üzere karşı bile yine zaten ayrıca bazı tüm"
).split()
_PREDICATE = (
    "değerlendirilmiştir gösterilmiştir ölçülmüştür incelenmiştir açıklanmıştır "
    "uygulanmıştır geliştirilmiştir tartışılmıştır belirlenmiştir sunulmuştur"
).split()


def prose(sentences: int, seed: int = 20260920) -> str:
    """Belirlenimci sozde-rastgele Turkce duzyazi.

    Kendi dogrusal eslesik uretecini tasir: `random` modulunun surumler arasi
    davranisina bagimli degildir, ayni girdi her yerde ayni metni verir.
    Amac 5-gram tekrari OLMAYAN, islev sozcugu bol bir metin: boylece tekrar
    kurallari karismadan govde ve oran kurallari sinanabilir.
    """
    state = seed

    def pick(pool: list[str]) -> str:
        nonlocal state
        state = (state * 1103515245 + 12345) % (2**31)
        return pool[state % len(pool)]

    out = []
    for _ in range(sentences):
        words = [
            pick(_FUNCTION) if index % 3 == 1 else pick(_CONTENT) for index in range(14)
        ]
        words.append(pick(_PREDICATE))
        out.append(" ".join(words).capitalize() + ".")
    return " ".join(out)


ARTICLE = prose(150)

CORPUS = {
    "bos": "",
    "tek-bosluk": " ",
    "kisa-cumle": "Kısa bir cümle.",
    "tek-bozuk-karakter": "�",
    "yalniz-menu": MENU,
    "yalniz-makale": ARTICLE,
    "menu-makale-menu": (MENU + " ") * 3 + ARTICLE + " " + (MENU + " ") * 3,
    "uzun-menu-makale-uzun-menu": (MENU + " ") * 12 + ARTICLE + " " + (MENU + " ") * 12,
    "yalniz-uzun-menu": (MENU + " ") * 40,
    "makale-sonra-menu-seli": ARTICLE + " " + (MENU + " ") * 40,
    "sablonlu-makale": "{{Bilgi kutusu|ad=Örnek}} " + ARTICLE + " {{kaynakça}} [[şablon]]",
    "cok-kisa-makale": prose(3),
    "iki-makale": prose(200, seed=7) + " " + ARTICLE,
}
CORPUS_CASES = tuple(CORPUS.values())
CORPUS_IDS = tuple(CORPUS)


# --- S1 Saf ---------------------------------------------------------------


@pytest.mark.parametrize("text", CORPUS_CASES, ids=CORPUS_IDS)
def test_s1_pure_and_repeatable(text: str) -> None:
    first = body(text)
    second = body(text)

    assert first == second
    assert body_span(text) == body_span(text)


# --- S2 Dilim -------------------------------------------------------------


@pytest.mark.parametrize("text", CORPUS_CASES, ids=CORPUS_IDS)
def test_s2_output_is_exactly_the_span_slice(text: str) -> None:
    start, end = body_span(text)

    assert body(text) == text[start:end]
    assert 0 <= start <= end <= len(text)


# --- S3 Bitisik -----------------------------------------------------------


@pytest.mark.parametrize("text", CORPUS_CASES, ids=CORPUS_IDS)
def test_s3_output_is_a_contiguous_piece_of_the_input(text: str) -> None:
    # Hicbir karakter yeniden yazilmaz, ortadan bir sey atilmaz.
    assert body(text) in text


# --- S4 Emin degilse kirpma ----------------------------------------------


@pytest.mark.parametrize("text", CORPUS_CASES, ids=CORPUS_IDS)
def test_s4_never_keeps_less_than_the_declared_share(text: str) -> None:
    assert len(body(text)) * BODY_MIN_KEEP_DEN >= len(text) * BODY_MIN_KEEP_NUM


def test_s4_empty_and_short_documents_are_not_trimmed() -> None:
    assert body("") == ""
    assert body_span("") == (0, 0)
    short = "Ses boşlukta yayılmaz; yayılmak için hava ya da su gibi bir ortam ister."
    assert body(short) == short
    # 120 sozcugun altinda kalan belge hic kirpilmaz, basi menu olsa bile.
    almost = MENU + " " + prose(4)
    assert body(almost) == almost


# --- S5 Etkisizlesen ------------------------------------------------------


@pytest.mark.parametrize("text", CORPUS_CASES, ids=CORPUS_IDS)
def test_s5_idempotent(text: str) -> None:
    once = body(text)

    assert body(once) == once


# --- S6 Disa acik yardimcilar --------------------------------------------


def test_s6_blocks_are_public_pure_and_cover_the_text_in_order() -> None:
    text = (MENU + " ") * 3 + ARTICLE
    chunks = blocks(text)

    assert chunks == blocks(text)
    assert all(isinstance(chunk, Block) for chunk in chunks)
    assert all(
        earlier.end <= later.start for earlier, later in zip(chunks, chunks[1:])
    )
    # Menu bloklari duzyazi degil, makale bloklari duzyazi.
    assert not chunks[0].is_prose
    assert chunks[-1].is_prose


def test_s6_menu_blocks_are_a_subset_of_the_blocks() -> None:
    text = (MENU + " ") * 3 + ARTICLE
    chunks = blocks(text)
    marked = menu_block_indices(text, chunks)

    assert marked
    assert marked <= set(range(len(chunks)))
    assert 0 in marked
    assert len(chunks) - 1 not in marked


# --- Govde gercekten is goruyor mu ---------------------------------------


def test_body_trims_the_menu_at_the_head_and_the_footer_at_the_tail() -> None:
    text = (MENU + " ") * 3 + ARTICLE + " " + (MENU + " ") * 3
    scope = body(text)

    assert len(scope) < len(text)
    # Bastaki menu de sondaki altbilgi de govdenin disinda.
    assert "facebook" not in scope
    assert ARTICLE[-40:-1] in scope
    # Govde blok siniriyla baslar/biter. Menu tam blok katina denk gelmiyorsa
    # kenarda ya makalenin birkac sozcugu kirpilir ya da menunun birkac sozcugu
    # iceride kalir; fark en cok bir bloktur (`BODY_BLOCK_WORDS`). Bilinen ve
    # kabul edilmis siniktir: kirpmanin cozunurlugu bloktur.
    drift = len(WORD_RE.findall(ARTICLE)) - len(WORD_RE.findall(scope))
    assert abs(drift) <= BODY_BLOCK_WORDS


def test_body_does_not_trim_real_prose_at_the_edges() -> None:
    # En temkinli kirpma: ilk duzyazi blogunda durur. Makalenin acilis
    # cumlelerinin kirpilmasi olcumde reddedilmis bir hataydi (Lagrange
    # mekanigi maddesinin ilk 460 karakteri). Govde son sozcukte bittigi icin
    # sondaki nokta disarida kalir; SOZCUKLERIN tamami govdededir.
    assert WORD_RE.findall(body(ARTICLE)) == WORD_RE.findall(ARTICLE)
    assert body_span(ARTICLE)[0] == 0
    assert len(ARTICLE) - body_span(ARTICLE)[1] <= 1


def test_body_refuses_to_trim_when_almost_nothing_would_remain() -> None:
    # Bas ve son menuden ibaret, ortada bir avuc duzyazi olan sayfa: kirpma
    # metnin dortte birinden azini birakirdi, o yuzden hic kirpilmaz.
    text = (MENU + " ") * 40 + prose(4) + " " + (MENU + " ") * 40

    assert body(text) == text


# --- Olcum yardimcilari ---------------------------------------------------


def test_strip_markup_preserves_length_and_positions() -> None:
    text = '{{Bilgi kutusu|ad=Örnek}} Bu madde bir [[şablon]] taşıyor.'
    cleaned, removed = strip_markup(text)

    assert len(cleaned) == len(text)
    assert removed > 0
    assert "{{" not in cleaned and "[[" not in cleaned
    assert "Bu madde bir" in cleaned


def test_prose_after_strip_reports_what_survives() -> None:
    article = prose(150)
    stub = "{{Bilgi kutusu|ad=Örnek|tür=x|yıl=1999}} [[kategori]] " * 60

    rich = prose_after_strip(article, strip="markup")
    poor = prose_after_strip(stub, strip="markup")

    assert rich.prose_chars * 2 > rich.scope_chars
    assert poor.prose_chars * 2 < poor.scope_chars


def test_prose_after_strip_rejects_an_unknown_strip() -> None:
    with pytest.raises(ValueError, match="unknown strip"):
        prose_after_strip("metin", strip="bilinmeyen")


def test_menu_block_indices_rejects_an_unknown_definition() -> None:
    with pytest.raises(ValueError, match="unknown menu definition"):
        menu_block_indices("metin", blocks("metin"), definition="cumlesiz")


# --- v1/v2 ile ortak tanimlar kaymamali ----------------------------------


def test_word_pattern_matches_the_v1_v2_definition() -> None:
    # quality_body v1/v2 kod yoluna dokunmamak icin sozcuk tanimini KOPYALAR.
    # Kopya kayarsa govde olcumu ile kural olcumu ayri sozcukleri sayar.
    assert WORD_RE.pattern == quality_filters._WORD_RE.pattern
    assert WORD_RE.flags == quality_filters._WORD_RE.flags
