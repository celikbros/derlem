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
from derlem_worker.quality_filters import QUALITY_POLICY_TR_WEB_V1


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
