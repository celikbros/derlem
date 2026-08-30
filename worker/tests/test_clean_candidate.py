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
