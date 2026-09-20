from __future__ import annotations

import zlib

import pytest

from derlem_worker.quality_filters import (
    QUALITY_FILTER_STATUS_APPLIED,
    QUALITY_FILTER_STATUS_APPLIED_LANGUAGE_UNKNOWN,
    QUALITY_FILTER_STATUS_NOT_EVALUATED,
    QUALITY_POLICY_NONE,
    QUALITY_POLICY_SUPPORTED_LANGUAGES,
    QUALITY_POLICY_TR_WEB_V1,
    QUALITY_POLICY_TR_WEB_V2,
    QUALITY_POLICY_TR_WEB_V3,
    SUPPORTED_QUALITY_POLICIES,
    quality_filter_status,
    quality_rejection_reasons,
)


def _padded_text(tokens: list[str], target_words: int) -> str:
    assert len(tokens) <= target_words
    padded = [*tokens]
    padded.extend(f"dolgu{index}" for index in range(target_words - len(tokens)))
    return " ".join(padded)


def test_supported_policies_and_none_policy() -> None:
    assert SUPPORTED_QUALITY_POLICIES == frozenset(
        {
            QUALITY_POLICY_NONE,
            QUALITY_POLICY_TR_WEB_V1,
            QUALITY_POLICY_TR_WEB_V2,
            QUALITY_POLICY_TR_WEB_V3,
        }
    )
    assert quality_rejection_reasons("#etiket " * 100, QUALITY_POLICY_NONE) == ()


def test_unknown_policy_is_rejected_without_source_text_in_error() -> None:
    private_text = "özel-belge-içeriği"

    with pytest.raises(ValueError) as captured:
        quality_rejection_reasons(private_text, "future-policy")

    assert "future-policy" in str(captured.value)
    assert private_text not in str(captured.value)


def test_extreme_repetition_word_boundary() -> None:
    assert quality_rejection_reasons(
        "kelime " * 500,
        QUALITY_POLICY_TR_WEB_V1,
    ) == ("extreme_repetition",)
    assert quality_rejection_reasons(
        "kelime " * 499,
        QUALITY_POLICY_TR_WEB_V1,
    ) == ()


def test_hashtag_stuffing_count_boundary() -> None:
    assert quality_rejection_reasons(
        "#etiket " * 50,
        QUALITY_POLICY_TR_WEB_V1,
    ) == ("hashtag_stuffing",)
    assert quality_rejection_reasons(
        "#etiket " * 49,
        QUALITY_POLICY_TR_WEB_V1,
    ) == ()


def test_mixed_script_artifact_requires_all_three_signals() -> None:
    mixed_tokens = " ".join("\u00adaз" for _ in range(20))
    too_few_soft_hyphens = " ".join(
        f"{'\u00ad' if index < 19 else ''}aз"
        for index in range(20)
    )

    assert quality_rejection_reasons(
        mixed_tokens,
        QUALITY_POLICY_TR_WEB_V1,
    ) == ("mixed_script_artifact",)
    assert quality_rejection_reasons(
        too_few_soft_hyphens,
        QUALITY_POLICY_TR_WEB_V1,
    ) == ()


def test_repeated_segments_and_reason_order_are_deterministic() -> None:
    repeated = "bir iki üç dört beş altı. " * 300

    assert quality_rejection_reasons(
        repeated,
        QUALITY_POLICY_TR_WEB_V1,
    ) == (
        "extreme_repetition",
        "repeated_segments",
    )


def test_navigation_boilerplate_uses_rate_boundary_and_second_evidence() -> None:
    navigation = ["ana", "sayfa", "haber", "giriş", "kayıt", "yorum", "paylaş"]
    promotion = ["hemen", "ücretsiz", "tıkla", "kampanya", "kaliteli"]
    text = _padded_text([*navigation, *promotion], 1_500)

    assert quality_rejection_reasons(
        text,
        QUALITY_POLICY_TR_WEB_V1,
    ) == ("navigation_boilerplate",)


def test_commercial_keyword_stuffing_uses_multiple_independent_signals() -> None:
    promotion = ["hemen", "ücretsiz", "tıkla", "kampanya", "kaliteli", "hizmet"]
    text = _padded_text(
        [*promotion, *("hemen" for _ in range(9)), "giriş", "kayıt", "yorum"],
        1_500,
    )

    assert quality_rejection_reasons(
        text,
        QUALITY_POLICY_TR_WEB_V1,
    ) == ("commercial_keyword_stuffing",)


def test_embedded_lexicon_fragments_do_not_trigger_keyword_stuffing() -> None:
    embedded_promotion = [
        "xhemen",
        "xücretsiz",
        "xtıkla",
        "xkampanya",
        "xkaliteli",
        "xhizmet",
    ]
    text = _padded_text(
        [*embedded_promotion, *("xhemen" for _ in range(9)), "giriş", "kayıt", "yorum"],
        1_500,
    )

    assert quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V1) == ()


def test_word_prefixes_still_match_inflected_spam_terms() -> None:
    topic = ["arkadaşlık", "sohbetler", "tanışma", *("arkadaşlık" for _ in range(5))]
    text = _padded_text([*topic, "hemen", "ücretsiz", "kaliteli"], 1_000)

    assert quality_rejection_reasons(
        text,
        QUALITY_POLICY_TR_WEB_V1,
    ) == ("dating_spam_cluster",)


@pytest.mark.parametrize(
    ("topic_tokens", "evidence_tokens", "expected_reason"),
    (
        (
            ["arkadaş", "sohbet", "chat", *("arkadaş" for _ in range(5))],
            ["hemen", "ücretsiz", "kaliteli"],
            "dating_spam_cluster",
        ),
        (
            ["dürbün", "kamera", "optik", *("dürbün" for _ in range(5))],
            ["hemen", "ücretsiz", "kaliteli"],
            "optics_spam_cluster",
        ),
        (
            ["escort", "randevu", "masaj", *("escort" for _ in range(5))],
            ["giriş", "kayıt", "yorum"],
            "adult_service_spam_cluster",
        ),
        (
            ["viagra", "cialis", "ilaç", *("viagra" for _ in range(5))],
            ["hemen", "ücretsiz", "kaliteli"],
            "sexual_pharma_spam_cluster",
        ),
    ),
)
def test_topic_clusters_require_density_diversity_and_second_evidence(
    topic_tokens: list[str],
    evidence_tokens: list[str],
    expected_reason: str,
) -> None:
    text = _padded_text([*topic_tokens, *evidence_tokens], 1_000)

    assert quality_rejection_reasons(
        text,
        QUALITY_POLICY_TR_WEB_V1,
    ) == (expected_reason,)


def test_legislation_style_list_is_not_rejected() -> None:
    text = " ".join(
        f"Madde {index}. Kurum{index} görev{index} yetki{index} usul{index} "
        f"kayıt{index} hüküm{index} uygular{index}."
        for index in range(250)
    )

    assert quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V1) == ()


def test_normal_news_text_with_urls_is_not_rejected() -> None:
    text = _padded_text(
        [
            "haber",
            "yorum",
            "paylaş",
            "kategori",
            "arama",
            "https://ornek.com/yazi-a",
            "https://ornek.org/yazi-b",
            "https://ornek.net/yazi-c",
        ],
        1_600,
    )

    assert quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V1) == ()


def test_health_education_topic_without_commercial_evidence_is_not_rejected() -> None:
    topic = ["viagra", "cialis", "ilaç", *("ilaç" for _ in range(5))]
    text = _padded_text([*topic, "sağlık", "eğitim", "araştırma"], 1_000)

    assert quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V1) == ()


def test_adult_topic_without_spam_evidence_is_not_rejected() -> None:
    topic = ["escort", "randevu", "masaj", *("masaj" for _ in range(5))]
    text = _padded_text([*topic, "toplumsal", "inceleme", "araştırma"], 1_000)

    assert quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V1) == ()


def test_multilingual_text_without_mixed_tokens_or_soft_hyphens_is_not_rejected() -> None:
    text = " ".join(
        f"Türkçe{index} русский{index} açıklama{index} текст{index}"
        for index in range(300)
    )

    assert quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V1) == ()


# tr-web-v2: v1 + iki kesin kural. 100k dilim olcumunde (2026-09-17) U+FFFD iceren
# satir %0,231, Vikipedi isaretleme kalintisi %0,353 cikti; v1 bunlari gormuyordu
# cunku kurallari 500+ sozcuk istiyor. Yeni kurallar uzunluktan bagimsizdir.


def test_v2_rejects_encoding_corruption_regardless_of_length() -> None:
    corrupted = "R�yada dua g�rmek hay�rl� �eylerin habercisidir."

    assert quality_rejection_reasons(corrupted, QUALITY_POLICY_TR_WEB_V2) == ("encoding_corruption",)
    # v1 degismedi: ayni satiri kabul eder (kontrol).
    assert quality_rejection_reasons(corrupted, QUALITY_POLICY_TR_WEB_V1) == ()


def test_v2_rejects_wiki_markup_residue() -> None:
    table_row = '| align="left" | 2002-03 | align="left" | Detroit | 17 || 0 || 19.0 || .438'
    template = "{{Bilgi kutusu|ad=Örnek}} Bu madde bir [[şablon]] taşıyor."
    double_bar = "Takım A || 12 || 3 || Takım B || 9"

    for text in (table_row, template, double_bar):
        assert quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V2) == ("wiki_markup_residue",)
        assert quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V1) == ()


def test_v2_keeps_ordinary_text_and_single_bar() -> None:
    prose = "Ses boşlukta yayılmaz; yayılmak için hava ya da su gibi bir ortam ister. Bu | tek çubuk zararsız."

    assert quality_rejection_reasons(prose, QUALITY_POLICY_TR_WEB_V2) == ()


def test_v2_includes_v1_reasons_and_orders_new_reasons_first() -> None:
    spam = _padded_text(["#etiket"] * 60, 600) + " �"

    reasons = quality_rejection_reasons(spam, QUALITY_POLICY_TR_WEB_V2)

    assert reasons[0] == "encoding_corruption"
    assert "hashtag_stuffing" in reasons
    assert quality_rejection_reasons(spam.replace("�", ""), QUALITY_POLICY_TR_WEB_V1) == ("hashtag_stuffing",)


# TASK-026 (2026-09-19): dil durustlugu. tr-web politikalari Turkce sozluk kurallaridir;
# baska dil ilan etmis kaynakta calistirilmaz, manifest "not_evaluated" yazar.


def test_tr_web_policies_declare_turkish_only() -> None:
    assert QUALITY_POLICY_SUPPORTED_LANGUAGES == {
        QUALITY_POLICY_TR_WEB_V1: frozenset({"tr"}),
        QUALITY_POLICY_TR_WEB_V2: frozenset({"tr"}),
        QUALITY_POLICY_TR_WEB_V3: frozenset({"tr"}),
    }
    assert QUALITY_POLICY_NONE not in QUALITY_POLICY_SUPPORTED_LANGUAGES


@pytest.mark.parametrize(
    "policy",
    (QUALITY_POLICY_TR_WEB_V1, QUALITY_POLICY_TR_WEB_V2, QUALITY_POLICY_TR_WEB_V3),
)
def test_quality_filter_status_follows_declared_language(policy: str) -> None:
    assert quality_filter_status(policy, "tr") == QUALITY_FILTER_STATUS_APPLIED
    # Etiket normalize edilir: bolge alt etiketi, buyuk harf ve bosluk fark yaratmaz.
    assert quality_filter_status(policy, "tr-TR") == QUALITY_FILTER_STATUS_APPLIED
    assert quality_filter_status(policy, " TR ") == QUALITY_FILTER_STATUS_APPLIED
    assert quality_filter_status(policy, "en") == QUALITY_FILTER_STATUS_NOT_EVALUATED
    assert quality_filter_status(policy, "en-US") == QUALITY_FILTER_STATUS_NOT_EVALUATED
    # Dil bilinmiyor (--input-path): politika uygulanir, durum bunu acikca soyler.
    assert quality_filter_status(policy, None) == QUALITY_FILTER_STATUS_APPLIED_LANGUAGE_UNKNOWN
    assert quality_filter_status(policy, "") == QUALITY_FILTER_STATUS_APPLIED_LANGUAGE_UNKNOWN


def test_quality_filter_status_none_policy_and_unknown_policy() -> None:
    assert quality_filter_status(QUALITY_POLICY_NONE, "en") is None
    assert quality_filter_status(QUALITY_POLICY_NONE, None) is None
    with pytest.raises(ValueError, match="future-policy"):
        quality_filter_status("future-policy", "tr")


# ===========================================================================
# tr-web-v3 (TASK-040). Asagidaki testler v1/v2'nin YUKARIDAKI hukumlerini
# degistirmez; v3 ayri bir daldir ve her yeni kural icin bir SINIR belgesi
# tasir: "v2 atardi, v3 tutar" ve "v3 hala atar".
# ===========================================================================

from derlem_worker import quality_body, quality_v3  # noqa: E402
from derlem_worker import quality_filters as quality_filters_module  # noqa: E402
from derlem_worker.quality_filters import (  # noqa: E402
    _REASON_ORDER,
    _V3_CLUSTER_FAMILY,
    _V3_RATIO_FAMILY,
    _V3_REPETITION_FAMILY,
    _V3_UNTOUCHED_REASONS,
)
from test_quality_body import MENU, prose  # noqa: E402

ARTICLE = prose(150)
# Gercek bir site menusu gezinme demetlerinin yaninda promosyon sozcukleri de
# tasir; v2'nin `navigation_boilerplate` kurali ikinci kanit olarak tam da
# onlari arar.
SITE_MENU = (
    MENU + " hemen tıkla ücretsiz kampanya kaliteli hizmet online fiyat sipariş"
)


def _v3(text: str) -> tuple[str, ...]:
    return quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V3)


def _v2(text: str) -> tuple[str, ...]:
    return quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V2)


def test_v3_reason_families_partition_the_reason_list() -> None:
    families = (
        _V3_UNTOUCHED_REASONS
        + _V3_RATIO_FAMILY
        + _V3_CLUSTER_FAMILY
        + _V3_REPETITION_FAMILY
    )

    assert sorted(families) == sorted(_REASON_ORDER)
    assert len(set(families)) == len(families)


# --- oran ailesi: varlik degil oran --------------------------------------


def test_v3_keeps_an_article_with_one_trailing_replacement_character() -> None:
    # v2'nin en pahali hatasi: kirpilmis son bayt yuzunden saglam bir makaleyi
    # atmak (bu tabakada yanlis atma %54 olculdu).
    text = ARTICLE + " �"

    assert _v2(text) == ("encoding_corruption",)
    assert _v3(text) == ()


def test_v3_still_drops_widespread_encoding_corruption() -> None:
    text = ARTICLE.replace("a", "�", 400)

    assert _v2(text) == ("encoding_corruption",)
    assert _v3(text) == ("encoding_corruption",)


def test_v3_encoding_needs_at_least_two_replacement_characters() -> None:
    # Kisa belge: tek bir bozuk karakter bile YOGUNLUK esigini gecer
    # (10,7/10k > 10). Belgeyi ayakta tutan sey yalniz adet sartidir --
    # "kirpilmis son bayt bir belgeyi atmaz" kurali budur.
    short = prose(9, seed=555)
    one = _scatter_replacements(short, 1)
    two = _scatter_replacements(short, 2)

    assert _v2(one) == _v2(two) == ("encoding_corruption",)
    assert quality_v3.FFFD_MIN_COUNT == 2
    assert _v3(one) == ()
    assert _v3(two) == ("encoding_corruption",)


def test_v3_encoding_ignores_corruption_that_sits_only_in_the_tail() -> None:
    text = prose(15) + " � � bitis sozcugu buradadir."

    assert _v2(text) == ("encoding_corruption",)
    # Ikisi de TAM metnin son FFFD_TAIL_CHARS karakterinin icinde: kesilmis
    # baytin yeri orasidir, sayfayi atmaz.
    assert quality_v3.FFFD_TAIL_CHARS == 64
    assert _v3(text) == ()


def test_v3_keeps_a_long_article_that_carries_a_few_wiki_templates() -> None:
    text = "{{Bilgi kutusu|ad=Örnek}} " + ARTICLE + " {{kaynakça}} [[şablon]]"

    assert _v2(text) == ("wiki_markup_residue",)
    assert _v3(text) == ()


def test_v3_still_drops_a_stub_that_is_mostly_markup() -> None:
    text = (
        '{{Bilgi kutusu|ad=Örnek|tür=x|yıl=1999}} {| align="left" | 12 || 3 || 4 |- '
        "|| 5 || 6 [[kategori]] "
    ) * 60 + prose(3)

    assert "wiki_markup_residue" in _v2(text)
    assert "wiki_markup_residue" in _v3(text)


def test_v3_keeps_an_article_whose_menu_is_long_but_whose_body_is_prose() -> None:
    # "Kuyruk sayfayi goturmuyor": uc kat menu bas ve sonda, ortada makale.
    text = (SITE_MENU + " ") * 3 + ARTICLE + " " + (SITE_MENU + " ") * 3

    assert "navigation_boilerplate" in _v2(text)
    assert _v3(text) == ()


def test_v3_still_drops_a_page_that_is_only_a_menu() -> None:
    text = (SITE_MENU + " ") * 40

    assert "navigation_boilerplate" in _v2(text)
    assert "navigation_boilerplate" in _v3(text)


# --- kume ailesi: ikinci, yapisal sinyal ---------------------------------


OPTICS_TOPIC = "kamera zoom optik dürbün güvenlik kamerası gece görüş"
PROMOTION = "hemen ücretsiz kaliteli kampanya tıkla fiyat"

PHONE_REVIEW = ARTICLE + " " + " ".join(
    f"Bu modelde {OPTICS_TOPIC} özellikleri {index} numaralı testte {PROMOTION} "
    f"karşılaştırması ile birlikte ayrıntılı olarak değerlendirilmiştir."
    for index in range(30)
)
OPTICS_SPAM = (
    OPTICS_TOPIC + " " + PROMOTION + " 0532 111 22 33 599 TL sipariş ver "
) * 130


def test_v3_keeps_topic_words_that_appear_inside_real_prose() -> None:
    # Rafin en sert sikayeti: `optics_spam_cluster` telefon incelemelerine ve
    # OPPO/Nokia maddelerine basiyordu (%62 yanlis). Konu ayni, uslup farkli.
    assert _v2(PHONE_REVIEW) == ("optics_spam_cluster",)
    assert _v3(PHONE_REVIEW) == ()


def test_v3_still_drops_the_same_topic_without_any_prose() -> None:
    assert "optics_spam_cluster" in _v2(OPTICS_SPAM)
    assert "optics_spam_cluster" in _v3(OPTICS_SPAM)


def test_v3_cluster_drop_needs_a_structural_signal() -> None:
    prose_signals = quality_v3.structural_signals(
        quality_v3.structural_stats(quality_v3.turkish_casefold(PHONE_REVIEW))
    )
    spam_signals = quality_v3.structural_signals(
        quality_v3.structural_stats(quality_v3.turkish_casefold(OPTICS_SPAM))
    )

    assert prose_signals == ()
    assert "no_prose" in spam_signals
    assert quality_v3.REQUIRED_STRUCTURAL_SIGNALS == 1


def test_v3_does_not_widen_any_cluster_beyond_v2() -> None:
    # R1'in sarti: hicbir sozluk esigi gevsetilmedi. Kume gerekcesi ancak v2
    # onu zaten uretmisse konusulur, bu yuzden v3 hicbir kumede v2'den daha
    # genis olamaz.
    for text in (PHONE_REVIEW, OPTICS_SPAM, ARTICLE, (SITE_MENU + " ") * 40):
        assert {r for r in _v3(text) if r in _V3_CLUSTER_FAMILY} <= {
            r for r in _v2(text) if r in _V3_CLUSTER_FAMILY
        }


# --- dokunulmayanlar ------------------------------------------------------


ADULT_SPAM = (
    "escort eskort randevu masaj bayan ilan " + PROMOTION + " giriş kayıt yorum "
) * 130


def test_v3_does_not_touch_adult_service_spam() -> None:
    # Rafin olcumunde bu kume 50/50 dogruydu: kume fikri saglam, dort esik degil.
    assert "adult_service_spam_cluster" in _v2(ADULT_SPAM)
    assert "adult_service_spam_cluster" in _v3(ADULT_SPAM)
    assert "adult_service_spam_cluster" in _V3_UNTOUCHED_REASONS


def test_v3_does_not_touch_mixed_script_artifact() -> None:
    mixed = " ".join("­aз" for _ in range(20))

    assert _v2(mixed) == ("mixed_script_artifact",)
    assert _v3(mixed) == ("mixed_script_artifact",)


def test_v3_keeps_dropping_documents_that_several_rules_agree_on() -> None:
    # Rafin olcumu: cok gerekceli atmalarin 52/65'i dogru. Bu belgede birden
    # cok kural basiyor ve v3'te de basmaya devam ediyor.
    assert len(_v2(OPTICS_SPAM)) >= 2
    assert len(_v3(OPTICS_SPAM)) >= 2


# --- tekrar ailesi: belirlenimci sikistirilabilirlik ---------------------


TEMPLATE_SPAM = (
    "Top Tarihi Karar Konusu Mimar Sinan Kavşağı bölgesinde revizyon imar "
    "planı yapılması talebi. " * 80
)
OFFICIAL_MINUTES = "".join(
    f"Top. Tarihi : {1 + index % 28:02d}.{1 + index % 12:02d}.20{10 + index % 9:02d} "
    f"Karar No : {100 + index} Konusu : {index + 1000} ada {index + 7} parsel "
    f"numaralı taşınmazın imar planı değişikliği talebi hususunda hazırlanan "
    f"İmar ve Bayındırlık Komisyonu raporunun görüşülmesi bulunduğundan buna "
    f"dair komisyon raporu okundu ve kabulüne oybirliği ile karar verildi. "
    for index in range(60)
)


def test_v3_still_drops_template_spam() -> None:
    assert _v2(TEMPLATE_SPAM) == ("extreme_repetition",)
    assert _v3(TEMPLATE_SPAM) == ("extreme_repetition",)


def test_v3_repetition_verdict_does_not_depend_on_the_zlib_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-039: v2'nin hukmu `zlib`in uygulamasina bagliydi (3.14/zlib-ng ile
    3.13/zlib arasinda yedi satir taraf degistirdi). v3'un hicbir karari
    `zlib`e bakmaz.

    Sinama: `zlib.compress` iki ucta da taklit edilir. v2'nin hukmu degisir,
    v3'unki degismez.
    """
    corpus = (TEMPLATE_SPAM, OFFICIAL_MINUTES, ARTICLE, OPTICS_SPAM, PHONE_REVIEW)
    expected = [_v3(text) for text in corpus]

    def always_compressible(data: bytes, level: int = 9) -> bytes:
        return b""

    def never_compressible(data: bytes, level: int = 9) -> bytes:
        return data * 2

    # `zlib` modulunun kendisi yamalanir: hangi modul `import zlib` demis olursa
    # olsun ayni nesneyi gorur. Boylece v3'un HICBIR kolu sikistirmaya donerse
    # bu test kizarir.
    for fake in (always_compressible, never_compressible):
        monkeypatch.setattr(zlib, "compress", fake)
        assert [_v3(text) for text in corpus] == expected

    # Kontrol: taklit gercekten v2'yi etkiliyor, yani sinama bos degil.
    # "Hicbir sey sikismiyor" dunyasinda v2 sablon spam'ini ARTIK ATMIYOR;
    # v3 ayni belgeyi atmaya devam ediyor.
    monkeypatch.setattr(zlib, "compress", never_compressible)
    assert _v2(TEMPLATE_SPAM) == ()
    assert _v3(TEMPLATE_SPAM) == ("extreme_repetition",)


def test_v3_lz77_estimate_is_a_fixed_integer_measure() -> None:
    # Sabit pencere, sabit zincir derinligi, sabit maliyet modeli, tamsayi
    # aritmetigi: ayni metin her yorumlayicida ayni sayiyi verir. Bu degerler
    # kok .venv (3.14, zlib-ng) ve worker/.venv (3.13, zlib) altinda aynidir.
    assert quality_v3.lz77_ratio_permille("") == 1000
    assert quality_v3.lz77_ratio_permille("kelime " * 500) == 14
    assert quality_v3.lz77_ratio_permille(TEMPLATE_SPAM) == 25
    assert quality_v3.lz77_ratio_permille(OFFICIAL_MINUTES) == 84
    assert quality_v3.EXTREME_LZ77_MAX_PERMILLE == 260


# --- ASKIDA BIRAKILAN KORUMALAR ------------------------------------------


def test_frame_exemption_is_disabled_so_official_minutes_are_still_dropped() -> None:
    """Kurucu hukmu: muafiyet kodda dursun, tr-web-v3'te KAPALI olsun.

    Bu belge tam da muafiyetin tanimak icin yazildigi belgedir (ayni cerceve
    60 kez, her seferinde farkli tarih / karar no / ada / parsel) -- ve muafiyet
    kapali oldugu icin ATILIR. Muafiyet acilirsa bu test kizarir; kurucunun
    yeni-tutulanlar sayfasi hukme baglanmadan acilmamalidir.
    """
    assert quality_v3.FRAME_EXEMPTION_ENABLED is False
    assert _v2(OFFICIAL_MINUTES) == ("extreme_repetition",)
    assert _v3(OFFICIAL_MINUTES) == ("extreme_repetition",)

    # Muafiyet acik olsaydi bu belge kurtarilirdi: olcut belgeyi TANIYOR.
    assert quality_v3.informative_frames(
        quality_v3.frame_stats(
            OFFICIAL_MINUTES, quality_v3.turkish_casefold(OFFICIAL_MINUTES)
        )
    )
    # Birebir kopyali sablon spam'ini ise tanimiyor (dolgu ozgun degil).
    assert not quality_v3.informative_frames(
        quality_v3.frame_stats(
            TEMPLATE_SPAM, quality_v3.turkish_casefold(TEMPLATE_SPAM)
        )
    )


def test_mojibake_branch_is_disabled_so_turkish_circumflex_survives() -> None:
    """Mojibake kolu v2'de karsiligi olmayan tek koldu, yani YENI atma
    uretebiliyordu. Regresyon kosusunda bedeli olculdu: Turkce'nin sapkali A
    harfi ("el-AMILI", "TABAKAT" -- sapkalilariyla) mojibake sanilip saglam bir
    ilahiyat makalesini attiriyordu.
    """
    assert quality_v3.MOJIBAKE_BRANCH_ENABLED is False
    text = (
        "ZEYNÜDDİN EL-ÂMİLÎ ÖLDÜRÜLMESİYLE İLGİLİ İMÂMİYYE TABAKÂT "
        "KİTAPLARINDAKİ KURGULARIN DEĞERLENDİRİLMESİ. " + ARTICLE
    )

    assert _v2(text) == ()
    assert _v3(text) == ()
    # Kalip hala Â'yi mojibake sayiyor: kol acilirsa bu belge yeniden duser.
    assert quality_body.MOJIBAKE_RE.findall("el-ÂMİLÎ TABAKÂT")


# --- v3 hicbir belgeyi v2'den once atmaz (tekrar ailesi haric) -----------


def test_v3_adds_no_new_reason_outside_the_repetition_family() -> None:
    corpus = (
        ARTICLE,
        PHONE_REVIEW,
        OPTICS_SPAM,
        ADULT_SPAM,
        TEMPLATE_SPAM,
        OFFICIAL_MINUTES,
        (SITE_MENU + " ") * 3 + ARTICLE + " " + (SITE_MENU + " ") * 3,
        (SITE_MENU + " ") * 40,
        ARTICLE + " �",
    )

    for text in corpus:
        assert set(_v3(text)) - set(_v2(text)) <= set(_V3_REPETITION_FAMILY)


# --- her esigin kendi sinir belgesi --------------------------------------


def _scatter_replacements(text: str, count: int) -> str:
    """Bozuk karakterleri metne ESIT ARALIKLARLA serpistirir: yogunluk
    olcusunu yalniz basina sinamak icin (bas taraftaki yigilma govde
    kirpmasini tetikler ve olcuyu gizler)."""
    step = len(text) // (count + 1)
    pieces: list[str] = []
    cursor = 0
    for index in range(count):
        end = step * (index + 1)
        pieces.append(text[cursor:end])
        pieces.append("�")
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def test_v3_encoding_density_boundary() -> None:
    # 15.4 bin karakterlik govdede 15 bozuk karakter = 9,7/10k (tutulur),
    # 16 tanesi = 10,4/10k (atilir). Esik: FFFD_DENSITY_PER_10K.
    assert quality_v3.FFFD_DENSITY_PER_10K == 10
    below = _scatter_replacements(ARTICLE, 15)
    above = _scatter_replacements(ARTICLE, 16)

    assert _v2(below) == _v2(above) == ("encoding_corruption",)
    assert _v3(below) == ()
    assert _v3(above) == ("encoding_corruption",)


WIKI_MARKUP = (
    '{{Bilgi kutusu|ad=Örnek|tür=x|yıl=1999|ülke=Türkiye}} '
    '{| align="left" width="200" | 12 || 3 || 4 |- || 5 || 6 |} [[kategori]] '
)
# Isaretlemesi govdenin yarisindan cogunu kaplayan, ama yine de dokuz bin
# karakter duzyazi birakan bir madde.
MARKUP_HEAVY_ARTICLE = " ".join(
    prose(8, seed=1000 + index) + " " + WIKI_MARKUP * 12 for index in range(10)
)


def test_v3_keeps_an_article_with_enough_prose_even_if_markup_dominates() -> None:
    # Mutlak taban: "4000 karakterden fazla duzyazi birakan belge bu kuralla
    # asla atilamaz". Oran tek basina bakarsa bu madde duserdi (0,41 < 0,45).
    stats = quality_body.prose_after_strip(
        quality_body.body(MARKUP_HEAVY_ARTICLE), strip="markup"
    )

    assert stats.prose_chars >= quality_v3.WIKI_MIN_PROSE_CHARS
    assert stats.prose_chars * 100 < stats.scope_chars * quality_v3.WIKI_MIN_PROSE_RATIO_NUM
    assert "wiki_markup_residue" in _v2(MARKUP_HEAVY_ARTICLE)
    assert "wiki_markup_residue" not in _v3(MARKUP_HEAVY_ARTICLE)


def test_v3_cluster_reason_must_also_appear_on_the_full_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Govde kirpmasi yogunlugu YUKSELTEBILIR: kirpmadan sonra kalan parca tek
    basina bir kume esigini gecebilir. O zaman bile v3 yeni bir kume gerekcesi
    uretmez -- gerekce TAM METINDE de bulunmak zorundadir.

    Olculdu: bu sart olmadan 706 denetim satirinin birinde (rafin `good` dedigi
    32 bin karakterlik bir sayfada) yeni bir `commercial_keyword_stuffing`
    gerekcesi cikiyordu. Burada ayni durum govde fonksiyonu yerine konarak
    dogrudan kuruluyor: tam metin bir menu sayfasi, govde ise bir optik spam
    sayfasi."""
    page = (SITE_MENU + " ") * 40

    assert "navigation_boilerplate" in _v2(page)  # tetik var, govde hesaplanir
    assert "optics_spam_cluster" not in _v2(page)
    assert "optics_spam_cluster" in _v2(OPTICS_SPAM)

    monkeypatch.setattr(quality_filters_module, "body", lambda text: OPTICS_SPAM)

    assert "optics_spam_cluster" not in _v3(page)


SHORT_WIKI_ARTICLE = (
    "{{Bilgi kutusu|ad=Örnek}} " + prose(25, seed=77) + " [[kategori]]"
)
# Menusu METNIN ORTASINDA olan sayfa: govde bas/sondan kirptigi icin menuleri
# atamaz, tetik govdede de basar -- karari veren sey yalniz oran olcusudur.
MENU_BETWEEN_SECTIONS = " ".join(
    piece
    for index in range(4)
    for piece in (prose(30, seed=200 + index), (SITE_MENU + " ") * 3)
) + " " + prose(30, seed=999)


def test_v3_keeps_a_short_article_whose_prose_survives_the_markup() -> None:
    # Mutlak taban tek basina bakarsa bu kisa madde duserdi (2.559 < 4.000);
    # ayakta tutan sey ORAN olcusudur: isaretleme kirpilinca geriye govdenin
    # %98'i duzyazi olarak kaliyor.
    stats = quality_body.prose_after_strip(
        quality_body.body(SHORT_WIKI_ARTICLE), strip="markup"
    )

    assert stats.prose_chars < quality_v3.WIKI_MIN_PROSE_CHARS
    assert (
        stats.prose_chars * quality_v3.WIKI_MIN_PROSE_RATIO_DEN
        >= stats.scope_chars * quality_v3.WIKI_MIN_PROSE_RATIO_NUM
    )
    assert _v2(SHORT_WIKI_ARTICLE) == ("wiki_markup_residue",)
    assert _v3(SHORT_WIKI_ARTICLE) == ()


def test_v3_keeps_a_page_whose_menus_sit_between_real_sections() -> None:
    # Govde kirpmasi burada is goremez (menuler ortada); tetik hem tam metinde
    # hem govdede basiyor. Sayfayi kurtaran sey "menu dusunce ne kaliyor"
    # olcusudur: %76 duzyazi kaliyor, esik %65.
    scope = quality_body.body(MENU_BETWEEN_SECTIONS)
    stats = quality_body.prose_after_strip(scope, strip="navigation")

    assert "navigation_boilerplate" in _v2(MENU_BETWEEN_SECTIONS)
    assert "navigation_boilerplate" in _v2(scope)
    assert (
        stats.prose_chars * quality_v3.NAV_MIN_PROSE_RATIO_DEN
        >= stats.scope_chars * quality_v3.NAV_MIN_PROSE_RATIO_NUM
    )
    assert "navigation_boilerplate" not in _v3(MENU_BETWEEN_SECTIONS)
