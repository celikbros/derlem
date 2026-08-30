from __future__ import annotations

import pytest

from derlem_worker.quality_filters import (
    QUALITY_POLICY_NONE,
    QUALITY_POLICY_TR_WEB_V1,
    SUPPORTED_QUALITY_POLICIES,
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
