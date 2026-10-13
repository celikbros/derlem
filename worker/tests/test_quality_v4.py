"""tr-web-v4 (TASK-046): v3 + `machine_translation` + `commercial_page`.

Uc grup test:
  1. v3 DONDURULMUS: ayni girdi -> v4'un v3'e ait gerekceleri v3'unkiyle birebir.
  2. Her esik icin bir SINIR belgesi (kontrol kosusu: esik ya da koruma kaldirilinca
     en az bir test kirmiziya doner -- var/olcum-2026-10-13/task-046/kontrol_kosulari.py).
  3. clean_candidate: politika secimi, URL okuma, karar kaydi (gerekce basina satir,
     yargic `tr-web-v4@<sha>`).
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re

import pytest

from derlem_worker import commercial_page as cp
from derlem_worker import machine_translation as mt
from derlem_worker import quality_v4
from derlem_worker.clean_candidate import (
    derive_clean_candidate,
    derive_selection_list,
    selection_artifact_paths,
)
from derlem_worker.document_record import read_decisions
from derlem_worker.quality_filters import (
    QUALITY_FILTER_STATUS_APPLIED,
    QUALITY_FILTER_STATUS_NOT_EVALUATED,
    QUALITY_POLICY_TR_WEB_V3,
    QUALITY_POLICY_TR_WEB_V4,
    SUPPORTED_QUALITY_POLICIES,
    V4_REASON_ORDER,
    _REASON_ORDER,
    quality_filter_status,
    quality_rejection_reasons,
)

# ---------------------------------------------------------------------------
# Belge kurucular
# ---------------------------------------------------------------------------

_NEUTRAL = (
    "kalem masa duvar pencere kapı bahçe ağaç yaprak çiçek toprak deniz kum taş "
    "yol köprü şehir köy dağ nehir göl orman bulut yağmur rüzgâr güneş ay yıldız "
    "kitap defter okul sınıf öğretmen öğrenci araba otobüs tren uçak gemi liman"
).split()
_CALQUE = sorted(mt.CALQUE_WORDS)
_NATIVE = sorted(mt.NATIVE_WORDS)


def _words(total: int, *, calque: int = 0, native: int = 0) -> list[str]:
    assert calque + native <= total
    out = [_CALQUE[i % len(_CALQUE)] for i in range(calque)]
    out += [_NATIVE[i % len(_NATIVE)] for i in range(native)]
    out += [_NEUTRAL[i % len(_NEUTRAL)] for i in range(total - calque - native)]
    return out


def _prose(total: int, *, calque: int = 0, native: int = 0, per_sentence: int = 10) -> str:
    """`total` sozcukluk, cumlelere bolunmus duz metin; profil tam olarak ayarli."""
    words = _words(total, calque=calque, native=native)
    sentences = [" ".join(words[i : i + per_sentence]) for i in range(0, len(words), per_sentence)]
    return " ".join(s[:1].upper() + s[1:] + "." for s in sentences)


def _profile(text: str) -> int:
    return mt.machine_translation_stats(text).profile_permille


# Olculen esikler (var/olcum-2026-10-13/task-046/RAPOR.md). Sinir testleri modulun
# sabitlerini DEGIL bu degerleri kullanir: esik kayarsa hem sabitleme testi hem
# sinir testi kirmizi olur (kontrol kosusu). Iki hedef cifti (TASK-049): A = yanlis
# atma tavani %5 (RAPOR §2.3), B = %7,5 (RAPOR §2.4, olc-mt.json frontier["7.5"]).
# Sinir testleri modulun SECTIGI cifte (mt.MT_TARGET) gore sinar: kurucu B'yi
# secip sabiti degistirince testler yesil kalir, ama bir ciftin degeri kayarsa
# sabitleme testi kirmizidir.
_MEASURED_MT_SETS = {
    "A": mt.MachineTranslationThresholds(
        min_words=75,
        url_profile_permille=-4,
        strong_profile_permille=20,
        cyrillic_min=3,
        cyrillic_max_share_per_100=5,
        bu_comma_profile_permille=10,
    ),
    "B": mt.MachineTranslationThresholds(
        min_words=75,
        url_profile_permille=-4,
        strong_profile_permille=14,
        cyrillic_min=3,
        cyrillic_max_share_per_100=5,
        bu_comma_profile_permille=4,
    ),
}
_MEASURED_MT = _MEASURED_MT_SETS[mt.MT_TARGET]
_MEASURED_COM_STRONG = (("price", 2), ("cta", 2), ("spec", 2), ("sponsor", 1))
_MEASURED_TITLE_REPEAT_MIN = 5
_MEASURED_MIN_FAMILIES = 2


def test_thresholds_are_the_measured_ones() -> None:
    assert mt.THRESHOLD_SETS == _MEASURED_MT_SETS
    assert mt.MT_TARGET in {"A", "B"}
    assert mt.THRESHOLDS is mt.THRESHOLD_SETS[mt.MT_TARGET]
    assert mt.THRESHOLDS == _MEASURED_MT
    assert cp.THRESHOLDS == cp.CommercialThresholds(
        title_repeat_min=_MEASURED_TITLE_REPEAT_MIN,
        min_families=_MEASURED_MIN_FAMILIES,
        strong=_MEASURED_COM_STRONG,
    )


# ---------------------------------------------------------------------------
# 0. Kurucularin kendisi (yoksa sinir testleri yanlis seyi sinar)
# ---------------------------------------------------------------------------


def test_builders_produce_the_exact_profile_they_promise() -> None:
    stats = mt.machine_translation_stats(_prose(1000, calque=20, native=0))
    assert (stats.word_count, stats.calque_hits, stats.native_hits) == (1000, 20, 0)
    stats = mt.machine_translation_stats(_prose(1000, calque=0, native=5))
    assert (stats.word_count, stats.calque_hits, stats.native_hits) == (1000, 0, 5)
    assert not set(_NEUTRAL) & (mt.CALQUE_WORDS | mt.NATIVE_WORDS)


# ---------------------------------------------------------------------------
# 1. v3 dondurulmus
# ---------------------------------------------------------------------------

_V3_CORPUS = (
    "",
    "Kısa ama düzgün bir haber cümlesi.",
    "R�yada dua g�rmek hay�rl� �eylerin habercisidir.",
    "{{Bilgi kutusu}} [[Ankara]] başkenttir. " * 3,
    "Aynı cümle tekrar tekrar yazılmıştır burada. " * 200,
    " ".join(f"#etiket{i}" for i in range(80)),
    _prose(1200, calque=40),
    _prose(400, native=10) + " Hemen sipariş ver, ücretsiz kargo! 199 TL. 249 TL.",
    "Ana Sayfa > Ürünler > Kalem " + _prose(200),
)


@pytest.mark.parametrize("text", _V3_CORPUS)
@pytest.mark.parametrize("url", (None, "https://tr.example.ru/tr/sayfa", "https://www.hurriyet.com.tr/x"))
def test_v4_keeps_every_v3_verdict_byte_for_byte(text: str, url: str | None) -> None:
    v3 = quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V3)
    v4 = quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V4, url=url)
    assert v4[: len(v3)] == v3
    assert tuple(reason for reason in v4 if reason in _REASON_ORDER) == v3
    assert set(v4[len(v3) :]) <= set(quality_v4.NEW_REASONS)


def test_v3_ignores_url_and_v4_reason_order_is_v3_order_then_new_rules() -> None:
    text = _prose(400, calque=20)
    assert quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V3, url="https://tr.topwar.ru/x") == ()
    assert V4_REASON_ORDER == _REASON_ORDER + ("machine_translation", "commercial_page")
    spam = "Aynı cümle tekrar tekrar yazılmıştır burada. " * 200
    both = quality_rejection_reasons(spam + " " + _prose(600, calque=60), QUALITY_POLICY_TR_WEB_V4)
    assert both[0] in _REASON_ORDER and both[-1] == "machine_translation"


def test_v4_is_a_turkish_policy_like_v3() -> None:
    assert QUALITY_POLICY_TR_WEB_V4 == "tr-web-v4" and QUALITY_POLICY_TR_WEB_V4 in SUPPORTED_QUALITY_POLICIES
    assert quality_filter_status(QUALITY_POLICY_TR_WEB_V4, "tr") == QUALITY_FILTER_STATUS_APPLIED
    assert quality_filter_status(QUALITY_POLICY_TR_WEB_V4, "en") == QUALITY_FILTER_STATUS_NOT_EVALUATED


def test_rule_switches_turn_each_new_reason_off(monkeypatch: pytest.MonkeyPatch) -> None:
    mt_text = _prose(400, calque=20)
    com_text = _prose(200) + " Fiyat: 199,90 TL, indirimli 149,90 TL."
    assert quality_v4.new_reasons(mt_text) == ("machine_translation",)
    assert quality_v4.new_reasons(com_text) == ("commercial_page",)
    monkeypatch.setattr(quality_v4, "MACHINE_TRANSLATION_ENABLED", False)
    monkeypatch.setattr(quality_v4, "COMMERCIAL_PAGE_ENABLED", False)
    assert quality_v4.new_reasons(mt_text) == ()
    assert quality_v4.new_reasons(com_text) == ()


def test_judge_id_names_the_policy_and_the_rule_code() -> None:
    judge = quality_v4.judge_id()
    assert re.fullmatch(r"tr-web-v4@[0-9a-f]{12}", judge)
    assert judge == f"tr-web-v4@{quality_v4.rule_source_sha256()[:12]}"
    package = Path(quality_v4.__file__).resolve().parent
    for name in quality_v4.RULE_SOURCE_FILES:
        assert (package / name).is_file()


# ---------------------------------------------------------------------------
# 2a. machine_translation: URL imzasi
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    (
        ("https://tr.topwar.ru/12345-haber.html", ("host_tr", "foreign_cctld")),
        ("https://www.example.com/tr/urunler/kalem", ("path_tr",)),
        ("https://support.example.com/tr-tr/help/1", ("path_tr",)),
        ("https://example.com/page?lang=tr", ("path_tr",)),
        ("https://www.jimmylarsson.nu/sayfa.php", ("foreign_cctld",)),
        ("https://www.hurriyet.com.tr/gundem/x", ()),
        ("https://www.example.com/trabzon/tr-haber", ()),
        ("https://tr.wikipedia.org/wiki/Ankara", ()),
        ("https://tr.m.wikipedia.org/wiki/Ankara", ()),
        ("https://kanal.example.tv/dizi", ()),
        ("https://yenax.tr.gg/Bilim.htm", ()),
        (None, ()),
        ("", ()),
        ("http://[bozuk", ()),
    ),
)
def test_url_signature(url: str | None, expected: tuple[str, ...]) -> None:
    assert mt.url_signature(url) == expected


# ---------------------------------------------------------------------------
# 2b. machine_translation: karar ve sinirlar
# ---------------------------------------------------------------------------

_URL = "https://tr.example.ru/makale"


def _mt(text: str, url: str | None = None) -> bool:
    return mt.is_machine_translation(mt.machine_translation_stats(text, url))


def test_url_alone_is_not_enough_native_turkish_under_a_tr_host_is_kept() -> None:
    # URL imzali ama dogal Turkce baglama ogeleriyle yazilmis: profil -5 binde.
    text = _prose(1000, native=5)
    assert _profile(text) == -5
    assert not _mt(text, _URL)


def test_url_with_weak_profile_boundary() -> None:
    th = _MEASURED_MT
    at = _prose(1000, native=-th.url_profile_permille)
    below = _prose(1000, native=-th.url_profile_permille + 1)
    assert _mt(at, _URL)
    assert not _mt(below, _URL)
    assert not _mt(at, None)  # URL yoksa zayif profil yetmez


def test_strong_profile_without_url_boundary() -> None:
    th = _MEASURED_MT
    assert _mt(_prose(1000, calque=th.strong_profile_permille))
    assert not _mt(_prose(1000, calque=th.strong_profile_permille - 1))


def test_bu_comma_path_without_url_boundary() -> None:
    th = _MEASURED_MT
    assert th.bu_comma_profile_permille is not None
    calque = th.bu_comma_profile_permille
    with_bu = "Bu, kalem masa duvar. " + _prose(996, calque=calque)
    assert mt.machine_translation_stats(with_bu).word_count == 1000
    assert mt.machine_translation_stats(with_bu).bu_comma == 1
    assert _mt(with_bu)
    assert not _mt("Bu, kalem masa duvar. " + _prose(996, calque=calque - 1))
    assert not _mt("Bu kalem masa duvar. " + _prose(996, calque=calque))  # virgulsuz: calka degil


def test_min_words_guard_keeps_short_documents_out_of_the_profile() -> None:
    th = _MEASURED_MT
    short = _prose(th.min_words - 1, calque=th.min_words - 1)
    enough = _prose(th.min_words, calque=th.min_words // 2)
    assert not _mt(short)
    # "Bu," yolu da kisa belgede profili kullanmaz ("Bu" bir sozcuk sayilir: -2)
    assert not _mt("Bu, " + _prose(th.min_words - 2, calque=th.min_words - 2))
    assert _mt(enough)


def test_bu_comma_confirms_a_url_signature_even_with_a_native_profile() -> None:
    text = "Bu, kalem masa duvar. " + _prose(996, native=30)
    assert _mt(text, _URL)
    assert not _mt(text, None)


def test_cyrillic_residue_confirms_a_url_signature() -> None:
    th = _MEASURED_MT
    base = _prose(400, native=20)  # profil cok dusuk: tek teyit Kiril
    assert not _mt(base, _URL)
    assert _mt(base + " " + "д" * th.cyrillic_min, _URL)
    assert not _mt(base + " " + "д" * (th.cyrillic_min - 1), _URL)


def test_cyrillic_share_cap_separates_residue_from_a_russian_document() -> None:
    th = _MEASURED_MT
    base = _prose(400, native=20)
    letters = sum(1 for ch in base if ch.isalpha())
    # pay tavanina kadar (dahil degil) kalinti; tavanin ustu kalinti degil
    under = (letters * th.cyrillic_max_share_per_100) // (100 - th.cyrillic_max_share_per_100) - 1
    over = under + 20
    assert _mt(base + " " + "д" * under, _URL)
    assert not _mt(base + " " + "д" * over, _URL)


def test_mt_target_pairs_differ_only_where_measured_and_enter_the_judge() -> None:
    # 17 binde kopya profili: A'nin guclu esiginin (20) altinda, B'ninkinin (14) ustunde.
    between = mt.machine_translation_stats(_prose(1000, calque=17))
    assert not mt.is_machine_translation(between, mt.THRESHOLD_SETS["A"])
    assert mt.is_machine_translation(between, mt.THRESHOLD_SETS["B"])
    # "Bu," yolu: A 10 binde ister, B 4.
    bu = mt.machine_translation_stats("Bu, kalem masa duvar. " + _prose(996, calque=6))
    assert not mt.is_machine_translation(bu, mt.THRESHOLD_SETS["A"])
    assert mt.is_machine_translation(bu, mt.THRESHOLD_SETS["B"])
    # Secim sabiti kural kaynagindadir: yargic kimligi onu kapsar.
    assert "machine_translation.py" in quality_v4.RULE_SOURCE_FILES
    source = (Path(mt.__file__).read_bytes()).decode("utf-8")
    assert source.count(f'MT_TARGET = "{mt.MT_TARGET}"') == 1


def test_machine_translation_rule_is_not_topical() -> None:
    # Ayni sozcukler, ayni konu: yalniz profil farkli.
    native = _prose(600, native=12)
    calque = _prose(600, calque=12)
    assert not _mt(native)
    assert _mt(calque)


# ---------------------------------------------------------------------------
# 2c. commercial_page
# ---------------------------------------------------------------------------


def _com(text: str) -> bool:
    return cp.is_commercial_page(cp.commercial_stats(text))


_ENCYCLOPEDIA = (
    "Ankara, Türkiye'nin başkenti ve en kalabalık ikinci şehridir. 1923 yılında başkent ilan edilen "
    "şehrin nüfusu 2020 sayımına göre 5.663.322 kişidir. Şehir, İç Anadolu Bölgesi'nde yer alır ve "
    "tarih boyunca Galatlar, Romalılar ve Selçuklular tarafından yönetilmiştir. " * 3
)


def test_encyclopedia_article_with_numbers_and_dates_is_kept() -> None:
    assert not _com(_ENCYCLOPEDIA)


def test_one_weak_family_is_not_enough() -> None:
    assert cp.commercial_families(cp.commercial_stats(_ENCYCLOPEDIA + " Bilet 49,90 TL.")) == ("price",)
    assert not _com(_ENCYCLOPEDIA + " Bilet 49,90 TL.")
    assert not _com(_ENCYCLOPEDIA + " Firmamız bu alanda çalışır.")


def test_two_families_make_a_commercial_page() -> None:
    text = _ENCYCLOPEDIA + " Bilet 49,90 TL. Hemen sipariş verin, ücretsiz kargo."
    assert set(cp.commercial_families(cp.commercial_stats(text))) == {"price", "cta"}
    assert _com(text)


@pytest.mark.parametrize(("family", "snippet"), (("price", " Bilet {},90 TL."), ("cta", " Sepete ekle.")))
def test_strong_single_family_boundary(family: str, snippet: str) -> None:
    minimum = dict(_MEASURED_COM_STRONG)[family]
    add = lambda k: "".join(snippet.format(100 + i) for i in range(k))  # noqa: E731
    assert _com(_ENCYCLOPEDIA + add(minimum))
    assert not _com(_ENCYCLOPEDIA + add(minimum - 1))


def test_spec_card_needs_two_fields_alone() -> None:
    minimum = dict(_MEASURED_COM_STRONG)["spec"]
    assert minimum == 2
    assert _com(_ENCYCLOPEDIA + " Ürün kodu: A056. Marka: Biobizz.")
    assert not _com(_ENCYCLOPEDIA + " Ürün kodu: A056.")


def test_sponsor_marker_alone_drops_the_sponsored_review() -> None:
    assert _com(_ENCYCLOPEDIA + " Bu içerik sponsorlu içerik olarak hazırlanmıştır.")


def test_news_about_a_sponsorship_is_not_a_sponsor_label() -> None:
    news = _ENCYCLOPEDIA + " Yarışmanın sponsorluğunu enstitü üstlendi; turnuva bankanın sponsorluğunda yapıldı."
    assert cp.commercial_stats(news).sponsor == 0
    assert not _com(news)


def test_listing_template_boundary_needs_a_second_family() -> None:
    minimum = _MEASURED_TITLE_REPEAT_MIN
    head = "Ümraniye Kazımkarabekir Elektrikçi"
    body = lambda k: " ".join([head] + [f"{head} hizmeti bölgede verilir." for _ in range(k - 1)])  # noqa: E731
    at = body(minimum) + " Bizi arayın."
    below = body(minimum - 1) + " Bizi arayın."
    assert cp.commercial_stats(at).title_repeat == minimum
    assert _com(at)
    assert not _com(below)
    assert not _com(body(minimum + 3))  # tek aile: yalniz sablon


def test_listing_template_counts_non_overlapping_repeats() -> None:
    # "kalem kalem kalem" yedi kez: ust uste binmeyen uc sozcukluk dizi 2 kez.
    assert cp.commercial_stats(" ".join(["Kalem"] * 7)).title_repeat == 2


def test_breadcrumb_and_corporate_voice_are_families() -> None:
    text = "Ana Sayfa > Ürünler > Kalem. Firmamız 1990'dan beri müşterilerimize hizmet verir."
    assert set(cp.commercial_families(cp.commercial_stats(text))) == {"corp_we", "breadcrumb"}
    assert _com(text)


def test_round_prose_amounts_are_not_shop_prices() -> None:
    # Tam alim orneginin goz okumasi: haber ve sikayet metinleri boyle tutarlar tasiyor.
    prose = "Hırsızlar 100 lira aldı. İçecek için 95 TL ödedik, sonra 200 lira daha verdik."
    assert cp.commercial_stats(prose).price == 0
    assert cp.commercial_stats("Satış: 140,18 TL. Etiket 99 ₺. Kira $47.14 gün. Fiyat: 120").price == 4


def test_law_text_mentioning_installments_is_not_a_cta() -> None:
    text = _ENCYCLOPEDIA + " Borç üç taksitle ödenir. 4949 Sayılı Kanun 4949 Sayılı Kanun 4949 Sayılı Kanun"
    assert cp.commercial_stats(text).cta == 0
    assert not _com(text)


# ---------------------------------------------------------------------------
# 3. clean_candidate
# ---------------------------------------------------------------------------

_MT_DOC = _prose(400, calque=20)
_COM_DOC = _ENCYCLOPEDIA + " Bilet 49,90 TL. Hemen sipariş verin, ücretsiz kargo."
_CLEAN_DOC = _ENCYCLOPEDIA
_URL_ONLY_DOC = _prose(400)  # notr profil: URL imzasi + profil >= esik -> ceviri


def _jsonl_source(tmp_path: Path) -> Path:
    lines = [
        {"id": "1", "text": _CLEAN_DOC, "url": "https://tr.wikipedia.org/wiki/Ankara"},
        {"id": "2", "text": _MT_DOC},
        {"id": "3", "text": _COM_DOC},
        {"id": "4", "text": _URL_ONLY_DOC, "provenance": {"url": "https://tr.topwar.ru/1.html"}},
        {"id": "5", "text": _URL_ONLY_DOC + " Ek."},
    ]
    source = tmp_path / "source.jsonl"
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in lines) + "\n"
    source.write_bytes(payload.encode("utf-8"))
    return source


def test_clean_candidate_v4_reads_url_from_the_record_and_counts_new_reasons(tmp_path: Path) -> None:
    source = _jsonl_source(tmp_path)
    report = derive_clean_candidate(
        source, tmp_path / "out.txt", source=None, max_document_bytes=1 << 20,
        quality_policy=QUALITY_POLICY_TR_WEB_V4, quality_rejections_path=tmp_path / "rej.jsonl",
    )
    assert report.quality_filter_version == "tr-web-v4"
    assert report.quality_judge == quality_v4.judge_id()
    assert report.quality_reason_document_counts == {"commercial_page": 1, "machine_translation": 2}
    assert report.written_lines == 2  # wiki maddesi + URL'siz notr belge


def test_clean_candidate_v3_report_has_no_judge_and_ignores_urls(tmp_path: Path) -> None:
    source = _jsonl_source(tmp_path)
    report = derive_clean_candidate(
        source, tmp_path / "out.txt", source=None, max_document_bytes=1 << 20,
        quality_policy=QUALITY_POLICY_TR_WEB_V3,
    )
    assert report.quality_judge is None
    assert report.removed_quality_lines == 0


def test_selection_list_writes_one_decision_row_per_v4_reason(tmp_path: Path) -> None:
    source = _jsonl_source(tmp_path)
    decided_at = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    derive_selection_list(
        source, tmp_path / "aday.txt", source=None, max_document_bytes=1 << 20,
        quality_policy=QUALITY_POLICY_TR_WEB_V4, run_id="run-v4", decided_at=decided_at,
    )
    decisions = list(read_decisions(selection_artifact_paths((tmp_path / "aday.txt").resolve())["decisions"]))
    quality = sorted((d["source_ordinal"], d["reason"]) for d in decisions if d["decision_type"] == "quality_rule")
    assert quality == [(2, "machine_translation"), (3, "commercial_page"), (4, "machine_translation")]
    judges = {d["judge"] for d in decisions if d["decision_type"] == "quality_rule"}
    assert judges == {quality_v4.judge_id()}
    assert all(d["verdict"] == "reject" for d in decisions if d["decision_type"] == "quality_rule")
    lines = source.read_bytes().split(b"\n")
    mt_row = next(d for d in decisions if d["source_ordinal"] == 2)
    assert mt_row["doc_id"] == hashlib.sha256(lines[1]).hexdigest()


def test_selection_list_splits_a_multi_reason_v4_drop_into_rows(tmp_path: Path) -> None:
    spam = "Aynı cümle tekrar tekrar yazılmıştır burada. " * 200
    text = spam + " " + _prose(600, calque=60) + " Bilet 49,90 TL. Hemen sipariş verin."
    source = tmp_path / "source.jsonl"
    source.write_bytes((json.dumps({"text": text}, ensure_ascii=False) + "\n").encode("utf-8"))
    derive_selection_list(
        source, tmp_path / "aday.txt", source=None, max_document_bytes=1 << 20,
        quality_policy=QUALITY_POLICY_TR_WEB_V4, run_id="run-v4",
    )
    decisions = list(read_decisions(selection_artifact_paths((tmp_path / "aday.txt").resolve())["decisions"]))
    reasons = [d["reason"] for d in decisions if d["decision_type"] == "quality_rule"]
    v3 = quality_rejection_reasons(text, QUALITY_POLICY_TR_WEB_V3)
    assert v3 and reasons == [*v3, "machine_translation", "commercial_page"]
