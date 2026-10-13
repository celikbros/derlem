from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pytest

from derlem_worker.clean_candidate import (
    CLEAN_CANDIDATE_V2_VERSION,
    derive_clean_candidate,
    ensure_writable_target,
    resolve_output_path,
    write_json_atomic,
)
from derlem_worker.quality_filters import (
    QUALITY_POLICY_TR_WEB_V1,
    QUALITY_POLICY_TR_WEB_V2,
    QUALITY_POLICY_TR_WEB_V3,
    SUPPORTED_QUALITY_POLICIES,
)


def test_derive_clean_candidate_removes_pii_duplicates_and_oversized(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    first = "Bu belge temiz ve normalize duplicate kontrolu icin yeterince uzundur."
    duplicate = "  bu   belge temiz ve normalize duplicate kontrolu icin yeterince uzundur.  "
    oversized = "oversized " + ("x" * 220)
    source.write_text(
        f"{first}\n"
        "mail test@example.com iceren satir cikmali\n"
        f"{duplicate}\n"
        "kisa\n"
        f"{oversized}\n",
        encoding="utf-8",
    )
    output = tmp_path / "clean.txt"

    report = derive_clean_candidate(
        source,
        output,
        source=None,
        max_document_bytes=200,
    )

    assert output.read_text(encoding="utf-8").splitlines() == [first, "kisa"]
    assert report.total_lines == 5
    assert report.written_lines == 2
    assert report.removed_pii_lines == 1
    assert report.removed_duplicate_lines == 1
    assert report.removed_oversized_lines == 1
    assert report.removed_quality_lines == 0
    assert report.quality_filter_version is None
    assert report.quality_reason_document_counts == {}
    assert report.quality_rejections_path is None
    assert report.quality_rejections_sha256 is None
    assert report.quality_rejections_byte_size == 0
    assert report.pii_findings["email"] == 1
    assert "test@example.com" not in str(report)


def test_ensure_writable_target_refuses_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        ensure_writable_target(target, force=False)

    ensure_writable_target(target, force=True)


def test_v2_quality_policy_writes_auditable_rejections(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    clean = "Bu doğal Türkçe belge, doğrulanabilir bir olayı dengeli biçimde açıklıyor."
    hashtag_spam = " ".join(f"#etiket{index % 80}" for index in range(800))
    source.write_text(f"{clean}\n{hashtag_spam}\n", encoding="utf-8")
    output = tmp_path / "clean-v2.txt"
    rejections = tmp_path / "clean-v2.rejections.jsonl"

    report = derive_clean_candidate(
        source,
        output,
        source=None,
        max_document_bytes=256 * 1024,
        quality_policy=QUALITY_POLICY_TR_WEB_V1,
        quality_rejections_path=rejections,
    )

    assert output.read_text(encoding="utf-8").splitlines() == [clean]
    assert report.algorithm_version == CLEAN_CANDIDATE_V2_VERSION
    assert report.quality_filter_version == QUALITY_POLICY_TR_WEB_V1
    assert report.total_lines == 2
    assert report.written_lines == 1
    assert report.removed_quality_lines == 1
    assert report.quality_reason_document_counts
    assert report.quality_rejections_path == str(rejections.resolve())
    rejection_records = [
        json.loads(line)
        for line in rejections.read_text(encoding="utf-8").splitlines()
    ]
    assert rejection_records == [
        {
            "reasons": list(report.quality_reason_document_counts),
            "source_ordinal": 2,
        }
    ]
    rejection_bytes = rejections.read_bytes()
    assert report.quality_rejections_sha256 == hashlib.sha256(rejection_bytes).hexdigest()
    assert report.quality_rejections_byte_size == len(rejection_bytes)


def test_v1_and_v2_default_output_paths_are_distinct(tmp_path: Path) -> None:
    source = {"name": "Gardas seed", "id": "f63352dd-fdd1-4e4b-a8d2-b167b3c856cf"}

    v1 = resolve_output_path(tmp_path, None, source, None)
    v2 = resolve_output_path(
        tmp_path,
        None,
        source,
        None,
        quality_policy=QUALITY_POLICY_TR_WEB_V1,
    )

    assert v1.name == "Gardas_seed_f63352dd_clean_candidate.txt"
    assert v2.name == "Gardas_seed_f63352dd_clean_candidate_v2.txt"


def test_write_json_atomic_replaces_complete_document(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    target.write_text('{"old":true}', encoding="utf-8")

    write_json_atomic(target, {"algorithm": "v2", "count": 3})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "algorithm": "v2",
        "count": 3,
    }
    assert list(tmp_path.glob("report.json.*.tmp")) == []


def test_derive_clean_candidate_refuses_to_overwrite_input(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("Bu temiz satir yeterince uzundur.\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="same as input"):
        derive_clean_candidate(source, source, source=None, max_document_bytes=1024)


# --- v3: held-out bolmesi + yakin kopya atma + zengin atma raporu (2026-09-18) ---

from derlem_worker.clean_candidate import (  # noqa: E402
    CLEAN_CANDIDATE_V3_VERSION,
    HELD_OUT_RULE_AFACAN_V1,
    REJECTIONS_RECORD_V2,
    default_held_out_path,
    is_held_out,
)
from derlem_worker.quality_filters import QUALITY_POLICY_TR_WEB_V2  # noqa: E402
from derlem_worker.similarity import document_simhash, hamming_distance  # noqa: E402


def _held_out_line(prefix: str) -> str:
    # Kurali saglayan bir satir uret (beklenen deneme sayisi ~2500).
    for index in range(200_000):
        candidate = f"{prefix} held-out deneme satırı numara {index} yeterince uzun bir cümledir."
        if is_held_out(candidate.encode("utf-8"), HELD_OUT_RULE_AFACAN_V1):
            return candidate
    raise AssertionError("no held-out line found")


def _near_duplicate_pair() -> tuple[str, str]:
    base_words = [f"sözcük{index}" for index in range(80)]
    base = " ".join(base_words) + "."
    base_signature = document_simhash(base)
    assert base_signature is not None
    for position in range(len(base_words)):
        variant_words = list(base_words)
        variant_words[position] = "değişik"
        variant = " ".join(variant_words) + "."
        signature = document_simhash(variant)
        if signature is not None and hamming_distance(base_signature, signature) <= 3:
            return base, variant
    raise AssertionError("no near-duplicate variant within Hamming 3")


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_v3_splits_held_out_lines_by_content_hash_not_position(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    held = _held_out_line("A")
    plain = "Bu satır eğitim adayında kalır; kural onu seçmez çünkü özeti 2500'e bölünmez."
    assert not is_held_out(plain.encode("utf-8"), HELD_OUT_RULE_AFACAN_V1)
    source.write_text(f"{plain}\n{held}\n", encoding="utf-8")
    output = tmp_path / "clean.txt"

    report = derive_clean_candidate(
        source, output, source=None, max_document_bytes=4096,
        quality_policy=QUALITY_POLICY_TR_WEB_V2, quality_rejections_path=tmp_path / "rej.jsonl",
        held_out_rule=HELD_OUT_RULE_AFACAN_V1,
    )

    held_out_path = default_held_out_path(output)
    assert output.read_text(encoding="utf-8").splitlines() == [plain]
    assert held_out_path.read_text(encoding="utf-8").splitlines() == [held]
    assert report.algorithm_version == CLEAN_CANDIDATE_V3_VERSION
    assert report.held_out_rule == HELD_OUT_RULE_AFACAN_V1
    assert report.held_out_path == str(held_out_path.resolve())
    assert (report.written_lines, report.held_out_lines) == (1, 1)
    assert report.held_out_sha256 == hashlib.sha256(held_out_path.read_bytes()).hexdigest()
    assert report.held_out_byte_size == len(held_out_path.read_bytes())
    assert report.rejections_record_version == REJECTIONS_RECORD_V2
    # Held-out satiri girdide once gelse de ayni tarafa duser: konum degil icerik.
    source.write_text(f"{held}\n{plain}\n", encoding="utf-8")
    report_swapped = derive_clean_candidate(
        source, tmp_path / "clean-2.txt", source=None, max_document_bytes=4096,
        held_out_rule=HELD_OUT_RULE_AFACAN_V1,
    )
    assert report_swapped.held_out_sha256 == report.held_out_sha256


def test_v3_dedup_is_shared_across_streams_so_held_out_never_leaks(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    held = _held_out_line("B")
    leak = "  " + held.replace(" ", "   ") + "  "  # normalize kopya: ayni parmak izi, farkli baytlar
    source.write_text(f"{held}\n{leak}\n", encoding="utf-8")
    output = tmp_path / "clean.txt"
    rejections = tmp_path / "rej.jsonl"

    report = derive_clean_candidate(
        source, output, source=None, max_document_bytes=4096,
        quality_rejections_path=rejections, held_out_rule=HELD_OUT_RULE_AFACAN_V1,
    )

    assert output.read_text(encoding="utf-8") == ""
    assert default_held_out_path(output).read_text(encoding="utf-8").splitlines() == [held]
    assert report.removed_duplicate_lines == 1
    [record] = _records(rejections)
    assert record["reasons"] == ["normalized_duplicate"]
    assert record["duplicate_of"] == 1
    assert record["source_ordinal"] == 2


def test_v3_near_dedup_drops_close_variant_and_reports_partner(tmp_path: Path) -> None:
    base, variant = _near_duplicate_pair()
    unrelated = "Tamamen başka bir konuda, kısa ama imza çıkarılabilecek uzunlukta bir cümle daha burada duruyor."
    source = tmp_path / "source.txt"
    source.write_text(f"{base}\n{unrelated}\n{variant}\n", encoding="utf-8")
    output = tmp_path / "clean.txt"
    rejections = tmp_path / "rej.jsonl"

    report = derive_clean_candidate(
        source, output, source=None, max_document_bytes=8192,
        quality_rejections_path=rejections, near_dedup=True,
    )

    assert output.read_text(encoding="utf-8").splitlines() == [base, unrelated]
    assert report.algorithm_version == CLEAN_CANDIDATE_V3_VERSION
    assert report.removed_near_duplicate_lines == 1
    assert report.simhash_indexed_lines == 2
    assert report.near_dedup_hamming_threshold == 3
    assert report.near_dedup_method == "normalized-word-3gram-simhash64-v1"
    [record] = _records(rejections)
    assert record["reasons"] == ["near_duplicate"]
    assert record["duplicate_of"] == 1
    assert record["sha256"] == hashlib.sha256(variant.encode("utf-8")).hexdigest()
    assert record["char_count"] == len(variant)
    assert record["preview"] == variant[:200]
    # Kontrol: yakin kopya atma kapaliyken ayni girdi uc satiri da yazar.
    control = derive_clean_candidate(source, tmp_path / "control.txt", source=None, max_document_bytes=8192)
    assert control.written_lines == 3


def test_v3_quality_rejection_record_carries_sha_and_preview_without_pii(tmp_path: Path) -> None:
    corrupted = "R�yada dua g�rmek hay�rl� �eylerin habercisidir, diye yazar eski tabirnameler."
    pii_and_corrupt = "Ara beni 0532 123 45 67 numaradan, � bozuk satır."
    source = tmp_path / "source.txt"
    source.write_text(f"{corrupted}\n{pii_and_corrupt}\n", encoding="utf-8")
    rejections = tmp_path / "rej.jsonl"

    report = derive_clean_candidate(
        source, tmp_path / "clean.txt", source=None, max_document_bytes=4096,
        quality_policy=QUALITY_POLICY_TR_WEB_V2, quality_rejections_path=rejections,
        held_out_rule=HELD_OUT_RULE_AFACAN_V1,
    )

    assert report.removed_pii_lines == 1 and report.removed_quality_lines == 1
    [record] = _records(rejections)  # PII'li satir rapora hic girmez
    assert record["reasons"] == ["encoding_corruption"]
    assert record["sha256"] == hashlib.sha256(corrupted.encode("utf-8")).hexdigest()
    assert record["preview"] == corrupted[:200] and record["char_count"] == len(corrupted)
    assert "0532" not in rejections.read_text(encoding="utf-8")


def test_v3_drop_list_removes_listed_lines_with_details_and_records_list_hash(tmp_path: Path) -> None:
    from derlem_worker.clean_candidate import load_drop_list

    foreign = "The quick brown fox jumps over the lazy dog and keeps running across the wide open field."
    turkish = "Hızlı kahverengi tilki tembel köpeğin üzerinden atlar ve geniş açık tarlada koşmaya devam eder."
    source = tmp_path / "source.txt"
    source.write_text(f"{turkish}\n{foreign}\n", encoding="utf-8")
    drop_list = tmp_path / "dil.jsonl"
    drop_list.write_text(
        json.dumps({"sha256": hashlib.sha256(foreign.encode("utf-8")).hexdigest(), "lang": "en", "p": 0.97}) + "\n"
        + json.dumps({"sha256": "0" * 64, "lang": "de", "p": 0.9}) + "\n",  # eslesmeyen kayit
        encoding="utf-8",
    )
    rejections = tmp_path / "rej.jsonl"

    report = derive_clean_candidate(
        source, tmp_path / "clean.txt", source=None, max_document_bytes=4096,
        quality_rejections_path=rejections,
        drop_list_path=drop_list, drop_list_method="fasttext-lid176-ftz-min200-p0.5", drop_list_reason="language_not_turkish",
    )

    assert (tmp_path / "clean.txt").read_text(encoding="utf-8").splitlines() == [turkish]
    assert report.algorithm_version == CLEAN_CANDIDATE_V3_VERSION
    assert report.removed_drop_list_lines == 1
    assert report.drop_list_entries == 2
    assert report.drop_list_method == "fasttext-lid176-ftz-min200-p0.5"
    assert report.drop_list_sha256 == hashlib.sha256(drop_list.read_bytes()).hexdigest()
    [record] = _records(rejections)
    assert record["reasons"] == ["language_not_turkish"]
    assert record["details"] == {"lang": "en", "p": 0.97}
    assert record["sha256"] == hashlib.sha256(foreign.encode("utf-8")).hexdigest()
    # Kontrol: liste verilmezse yabanci satir kalir.
    control = derive_clean_candidate(source, tmp_path / "control.txt", source=None, max_document_bytes=4096)
    assert control.written_lines == 2
    # Bozuk liste reddedilir.
    bad = tmp_path / "bozuk.jsonl"
    bad.write_text('{"lang": "en"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        load_drop_list(bad)


# --- TASK-026 (2026-09-19): dil durustlugu — tr-web politikasi Turkce disi kaynakta calismaz ---

from dataclasses import asdict  # noqa: E402

from derlem_worker.quality_filters import (  # noqa: E402
    QUALITY_FILTER_STATUS_APPLIED,
    QUALITY_FILTER_STATUS_APPLIED_LANGUAGE_UNKNOWN,
    QUALITY_FILTER_STATUS_NOT_EVALUATED,
)

_LANGUAGE_SOURCE_ID = "f63352dd-fdd1-4e4b-a8d2-b167b3c856cf"


def _source_row(language: str) -> dict:
    # load_source'un dondurdugu satirin derive_clean_candidate'in kullandigi alanlari.
    return {"id": _LANGUAGE_SOURCE_ID, "name": "Dil deneme", "object_sha256": "ab" * 32, "language": language}


def _write_spam_source(tmp_path: Path) -> tuple[Path, str, str]:
    clean = "Bu doğal Türkçe belge, doğrulanabilir bir olayı dengeli biçimde açıklıyor."
    hashtag_spam = " ".join(f"#etiket{index % 80}" for index in range(800))
    source = tmp_path / "source.txt"
    source.write_text(f"{clean}\n{hashtag_spam}\n", encoding="utf-8")
    return source, clean, hashtag_spam


def test_tr_web_policy_is_not_evaluated_for_non_turkish_source(tmp_path: Path) -> None:
    source, clean, hashtag_spam = _write_spam_source(tmp_path)
    output = tmp_path / "clean-en.txt"
    rejections = tmp_path / "clean-en.rejections.jsonl"

    report = derive_clean_candidate(
        source, output, source=_source_row("en"), max_document_bytes=256 * 1024,
        quality_policy=QUALITY_POLICY_TR_WEB_V2, quality_rejections_path=rejections,
    )

    # Kural hic calismaz: spam satiri da yazilir, kalite atmasi 0, gerekce sayimi bos.
    assert output.read_text(encoding="utf-8").splitlines() == [clean, hashtag_spam]
    assert report.quality_filter_status == QUALITY_FILTER_STATUS_NOT_EVALUATED
    assert report.quality_filter_version == QUALITY_POLICY_TR_WEB_V2  # istenen politika yine kayitli
    assert report.removed_quality_lines == 0
    assert report.quality_reason_document_counts == {}
    assert report.written_lines == 2
    assert rejections.read_text(encoding="utf-8") == ""
    assert report.source_id == _LANGUAGE_SOURCE_ID
    # Manifest geriye uyumlu: yeni alan asdict ile cikar, eski alanlar yerinde.
    manifest = asdict(report)
    assert manifest["quality_filter_status"] == "not_evaluated"
    assert manifest["quality_filter_version"] == "tr-web-v2"
    assert manifest["algorithm_version"] == CLEAN_CANDIDATE_V2_VERSION


def test_tr_web_policy_still_applies_to_turkish_source(tmp_path: Path) -> None:
    source, clean, _ = _write_spam_source(tmp_path)

    for language in ("tr", "tr-TR"):
        output = tmp_path / f"clean-{language}.txt"
        report = derive_clean_candidate(
            source, output, source=_source_row(language), max_document_bytes=256 * 1024,
            quality_policy=QUALITY_POLICY_TR_WEB_V2,
        )

        assert output.read_text(encoding="utf-8").splitlines() == [clean]
        assert report.quality_filter_status == QUALITY_FILTER_STATUS_APPLIED
        assert report.quality_filter_version == QUALITY_POLICY_TR_WEB_V2
        assert report.removed_quality_lines == 1
        # Kurallar degismedi: ayni satir v1'in iki gerekcesini birden tasir.
        assert report.quality_reason_document_counts == {"extreme_repetition": 1, "hashtag_stuffing": 1}


def test_input_path_run_without_source_language_applies_policy_and_says_so(tmp_path: Path) -> None:
    source, clean, _ = _write_spam_source(tmp_path)
    output = tmp_path / "clean-local.txt"

    report = derive_clean_candidate(
        source, output, source=None, max_document_bytes=256 * 1024, quality_policy=QUALITY_POLICY_TR_WEB_V2,
    )

    # --input-path: kaynak kaydi yok, dil bilinmiyor; politika bugunku gibi uygulanir.
    assert output.read_text(encoding="utf-8").splitlines() == [clean]
    assert report.quality_filter_status == QUALITY_FILTER_STATUS_APPLIED_LANGUAGE_UNKNOWN
    assert report.removed_quality_lines == 1


def test_no_policy_has_no_quality_filter_status(tmp_path: Path) -> None:
    source, _, _ = _write_spam_source(tmp_path)

    report = derive_clean_candidate(
        source, tmp_path / "clean.txt", source=_source_row("en"), max_document_bytes=256 * 1024,
    )

    assert report.quality_filter_status is None
    assert report.quality_filter_version is None
    assert report.removed_quality_lines == 0


# TASK-039/TASK-040 (2026-09-20): manifest hangi yorumlayici ve hangi zlib
# surumuyle uretildigini yazar; `tr-web-v3` bir politika secenegidir.


def test_manifest_records_interpreter_and_zlib_runtime_version(tmp_path: Path) -> None:
    import platform
    import zlib

    source = tmp_path / "source.txt"
    source.write_text(
        "Bu belge kalite süzgeci olmadan da yazılır ve manifest sürümleri taşır.\n",
        encoding="utf-8",
    )

    report = derive_clean_candidate(
        source, tmp_path / "clean.txt", source=None, max_document_bytes=4096
    )

    assert report.interpreter_version == platform.python_version()
    assert report.zlib_runtime_version == zlib.ZLIB_RUNTIME_VERSION
    # Manifeste gercekten yaziliyor (asdict yolundan gecer).
    manifest = tmp_path / "manifest.json"
    write_json_atomic(manifest, asdict(report))
    written = json.loads(manifest.read_text(encoding="utf-8"))
    assert written["interpreter_version"] == platform.python_version()
    assert written["zlib_runtime_version"] == zlib.ZLIB_RUNTIME_VERSION


def test_tr_web_v3_policy_is_selectable_and_keeps_what_v2_dropped(tmp_path: Path) -> None:
    # v2'nin olculen kusuru: tek bir U+FFFD saglam bir haberi attiriyordu.
    # Ayni belge tr-web-v3 altinda tutulur, sablon spam'i atilmaya devam eder.
    truncated_byte = (
        "Belediye meclisi, kent merkezindeki ulaşım planını görüştü ve raporu "
        "oybirliğiyle kabul etti; karar bir sonraki toplantıda uygulanacak.�"
    )
    template_spam = "Aynı cümle tekrar tekrar yazılmıştır burada. " * 200
    source = tmp_path / "source.txt"
    source.write_text(f"{truncated_byte}\n{template_spam}\n", encoding="utf-8")

    v2_report = derive_clean_candidate(
        source,
        tmp_path / "clean-v2.txt",
        source=None,
        max_document_bytes=256 * 1024,
        quality_policy=QUALITY_POLICY_TR_WEB_V2,
        quality_rejections_path=tmp_path / "v2.rejections.jsonl",
    )
    v3_report = derive_clean_candidate(
        source,
        tmp_path / "clean-v3.txt",
        source=None,
        max_document_bytes=256 * 1024,
        quality_policy=QUALITY_POLICY_TR_WEB_V3,
        quality_rejections_path=tmp_path / "v3.rejections.jsonl",
    )

    assert v2_report.removed_quality_lines == 2
    assert v3_report.removed_quality_lines == 1
    assert v3_report.quality_filter_version == QUALITY_POLICY_TR_WEB_V3
    assert v3_report.quality_reason_document_counts == {"extreme_repetition": 1}
    assert (tmp_path / "clean-v3.txt").read_text(encoding="utf-8").splitlines() == [
        truncated_byte
    ]


def test_tr_web_v3_is_offered_by_the_command_line(tmp_path: Path) -> None:
    assert QUALITY_POLICY_TR_WEB_V3 in SUPPORTED_QUALITY_POLICIES


# --------------------------------------------------------------------------
# TASK-044: secim listesi modu (metin yerine doc_id listesi + karar anlik goruntusu)
# --------------------------------------------------------------------------

from datetime import UTC, datetime  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402

from derlem_worker.clean_candidate import derive_selection_list, selection_artifact_paths  # noqa: E402
from derlem_worker.document_record import read_decisions, read_selection  # noqa: E402
from derlem_worker.quality_filters import QUALITY_POLICY_TR_WEB_V3 as _TR_WEB_V3  # noqa: E402
from derlem_worker.selection import SelectionError, materialize, selection_from_text_copy  # noqa: E402


def _selection_fixture(tmp_path: Path) -> tuple[Path, Path]:
    base, variant = _near_duplicate_pair()
    held = _held_out_line("S")
    scope = "Kapsam dışı kaynaktan gelen ve listede adı geçen uzunca bir Türkçe satır burada durur."
    foreign = "The quick brown fox jumps over the lazy dog and keeps running across the wide open field."
    lines = [
        "Temiz bir Türkçe belge; eğitim adayında kalır ve seçim listesine girer.",
        "mail test@example.com iceren satir cikmali",
        "",
        "oversized " + ("x" * 9000),
        "R�yada dua g�rmek hay�rl� �eylerin habercisidir, diye yazar eski tabirnameler.",
        base,
        "  temiz bir   türkçe belge; eğitim adayında kalır ve seçim listesine girer.  ",
        held,
        variant,
        scope,
        foreign,
        "Son temiz satır: satır sonu CRLF olsa da metin aynı kalır ve kopya ile birebir eşleşir.",
    ]
    source = tmp_path / "parent.txt"
    source.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    drop_list = tmp_path / "atilacak.jsonl"
    drop_list.write_text(
        json.dumps({"sha256": hashlib.sha256(scope.encode("utf-8")).hexdigest(), "reason": "source_not_in_scope_s2"}) + "\n"
        + json.dumps({"sha256": hashlib.sha256(foreign.encode("utf-8")).hexdigest(), "reason": "language_not_turkish", "lang": "en"}) + "\n",
        encoding="utf-8",
    )
    return source, drop_list


def _v5_like_options(drop_list: Path) -> dict:
    return dict(
        source=None,
        max_document_bytes=8192,
        quality_policy=_TR_WEB_V3,
        held_out_rule=HELD_OUT_RULE_AFACAN_V1,
        near_dedup=True,
        drop_list_path=drop_list,
        drop_list_method="s2-scope+fasttext-test",
        drop_list_reason="scope_or_language",
    )


def test_selection_list_materializes_to_the_text_copy_byte_for_byte(tmp_path: Path) -> None:
    source, drop_list = _selection_fixture(tmp_path)
    copy_dir = tmp_path / "copy"
    copy_dir.mkdir()
    text_copy = copy_dir / "aday.txt"
    report = derive_clean_candidate(
        source, text_copy, quality_rejections_path=copy_dir / "rej.jsonl", **_v5_like_options(drop_list),
    )

    list_dir = tmp_path / "list"
    list_dir.mkdir()
    would_be = list_dir / "aday.txt"
    decided_at = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    manifest = derive_selection_list(source, would_be, run_id="run-test", decided_at=decided_at, **_v5_like_options(drop_list))

    assert not would_be.exists() and not default_held_out_path(would_be).exists()
    assert manifest["expected_materialization"]["train"]["sha256"] == report.output_sha256
    assert manifest["expected_materialization"]["held_out"]["sha256"] == report.held_out_sha256
    assert manifest["parent"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()

    out = tmp_path / "out" / "aday.txt"
    held_out = tmp_path / "out" / "aday_heldout.txt"
    result = materialize(Path(manifest["manifest_path"]), output_path=out, held_out_output_path=held_out, verify_parent=True)

    assert out.read_bytes() == text_copy.read_bytes()
    assert held_out.read_bytes() == default_held_out_path(text_copy).read_bytes()
    assert result["outputs"]["train"]["sha256"] == report.output_sha256
    assert report.written_lines == 3 and report.held_out_lines == 1

    # Karar anlik goruntusu: secilmeyen her belge bir satir; turleri rapor sayilariyla ayni.
    artifacts = selection_artifact_paths(would_be.resolve())
    decisions = list(read_decisions(artifacts["decisions"]))
    by_type = {}
    for decision in decisions:
        by_type[decision["decision_type"]] = by_type.get(decision["decision_type"], 0) + 1
    assert by_type == {
        "empty_text": report.skipped_blank_lines,
        "pii": report.removed_pii_lines,
        "quality_rule": report.removed_quality_lines,
        "duplicate": report.removed_duplicate_lines,
        "near_duplicate": report.removed_near_duplicate_lines,
        "rights_scope": 1,
        "language": 1,
        "held_out": report.held_out_lines,
    }
    assert {decision["run_id"] for decision in decisions} == {"run-test"}
    assert {decision["decided_at"] for decision in decisions} == {decided_at}
    assert manifest["oversized_ordinals"] == [4]
    selection = list(read_selection(artifacts["selection"]))
    covered = {row["source_ordinal"] for row in selection} | {row["source_ordinal"] for row in decisions}
    assert covered | set(manifest["oversized_ordinals"]) == set(range(1, report.total_lines + 1))
    for row in selection:
        line = source.read_bytes().split(b"\r\n")[row["source_ordinal"] - 1]
        assert row["doc_id"] == hashlib.sha256(line).hexdigest()
    pii = next(decision for decision in decisions if decision["decision_type"] == "pii")
    assert pii["reason"] == "email" and "test@example.com" not in json.dumps(manifest)


def test_selection_list_is_deterministic_apart_from_run_identity(tmp_path: Path) -> None:
    source, drop_list = _selection_fixture(tmp_path)
    shas = []
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        manifest = derive_selection_list(source, tmp_path / name / "aday.txt", **_v5_like_options(drop_list))
        shas.append(manifest["selection"]["sha256"])
    assert shas[0] == shas[1]


def test_materialize_refuses_a_parent_line_that_does_not_match_its_doc_id(tmp_path: Path) -> None:
    source, drop_list = _selection_fixture(tmp_path)
    manifest = derive_selection_list(source, tmp_path / "aday.txt", **_v5_like_options(drop_list))
    tampered = tmp_path / "tampered.txt"
    payload = source.read_bytes()
    tampered.write_bytes(payload.replace(b"Temiz bir", b"Kirli bir", 1))
    assert tampered.stat().st_size == source.stat().st_size
    out = tmp_path / "out.txt"

    with pytest.raises(SelectionError, match="does not match its doc_id"):
        materialize(Path(manifest["manifest_path"]), parent_path=tampered, output_path=out)
    assert not out.exists() and list(tmp_path.glob("out.txt.*")) == []


def test_materialize_refuses_output_whose_sha_differs_from_the_manifest(tmp_path: Path) -> None:
    source, drop_list = _selection_fixture(tmp_path)
    manifest = derive_selection_list(source, tmp_path / "aday.txt", **_v5_like_options(drop_list))
    manifest_path = Path(manifest["manifest_path"])
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored["expected_materialization"]["train"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(stored), encoding="utf-8")
    out = tmp_path / "out.txt"

    with pytest.raises(SelectionError, match="does not match the manifest"):
        materialize(manifest_path, output_path=out)
    assert not out.exists() and list(tmp_path.glob("out.txt.*")) == []


def test_materialize_refuses_a_swapped_selection_list(tmp_path: Path) -> None:
    source, drop_list = _selection_fixture(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = derive_selection_list(source, tmp_path / "a" / "aday.txt", **_v5_like_options(drop_list))
    other_source = tmp_path / "other.txt"
    other_source.write_text("Başka bir ana kaynak satırı, yeterince uzun bir belge.\n", encoding="utf-8")
    second = derive_selection_list(other_source, tmp_path / "b" / "aday.txt", source=None, max_document_bytes=8192)
    shutil.copyfile(second["selection"]["path"], first["selection"]["path"])

    with pytest.raises(SelectionError, match="selection list sha256"):
        materialize(Path(first["manifest_path"]))


def test_existing_text_copy_is_expressed_as_a_selection_list_over_its_parent(tmp_path: Path) -> None:
    source, drop_list = _selection_fixture(tmp_path)
    text_copy = tmp_path / "aday.txt"
    report = derive_clean_candidate(source, text_copy, **_v5_like_options(drop_list))

    manifest = selection_from_text_copy(
        source, text_copy, held_out_path=default_held_out_path(text_copy), output_dir=tmp_path / "secim",
        name="aday", max_document_bytes=8192,
    )
    assert manifest["expected_materialization"]["train"]["sha256"] == report.output_sha256
    out = tmp_path / "out.txt"
    materialize(Path(manifest["manifest_path"]), output_path=out)
    assert out.read_bytes() == text_copy.read_bytes()

    not_subsequence = tmp_path / "ters.txt"
    not_subsequence.write_bytes(b"".join(reversed(text_copy.read_bytes().splitlines(keepends=True))))
    with pytest.raises(SelectionError, match="subsequence"):
        selection_from_text_copy(source, not_subsequence, held_out_path=None, output_dir=tmp_path / "ters",
                                 name="ters", max_document_bytes=8192)


SLICE_ENV = "DERLEM_SLICE_100K"


def test_selection_list_equals_text_copy_on_the_100k_slice(tmp_path: Path) -> None:
    """Gercek veri: 100k dilim (var/olcum-2026-09-17/dilim-100k_v3.txt), v5 ayarlariyla.

    Depoda olmayan veri ister; yol DERLEM_SLICE_100K ile acikca verilmezse atlanir
    (atlama sebebi cikti satirinda gorunur). Olcum betigi bunu ayrica kosar.
    """
    slice_path = os.environ.get(SLICE_ENV, "").strip()
    if not slice_path:
        pytest.skip(f"{SLICE_ENV} not set: 100k slice equality is measured by the TASK-044 script")
    drop_list = Path(os.environ.get("DERLEM_V5_DROP_LIST", "var/olcum-2026-09-21/v5/v5-atilacak-liste.jsonl"))
    options = dict(
        source=None, max_document_bytes=262144, quality_policy=_TR_WEB_V3, held_out_rule=HELD_OUT_RULE_AFACAN_V1,
        near_dedup=True, drop_list_path=drop_list,
        drop_list_method="s2-scope-2026-09-21+fasttext-lid176-ftz-min200-p0.5-window2000",
        drop_list_reason="scope_or_language",
    )
    text_copy = tmp_path / "copy" / "dilim.txt"
    text_copy.parent.mkdir()
    report = derive_clean_candidate(Path(slice_path), text_copy, **options)
    (tmp_path / "list").mkdir()
    manifest = derive_selection_list(Path(slice_path), tmp_path / "list" / "dilim.txt", **options)
    out = tmp_path / "out.txt"
    materialize(Path(manifest["manifest_path"]), output_path=out)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == report.output_sha256
    assert out.read_bytes() == text_copy.read_bytes()
