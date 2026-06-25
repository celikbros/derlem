from pathlib import Path

import pytest

from derlem_worker.clean_candidate import derive_clean_candidate, ensure_writable_target


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
    assert report.pii_findings["email"] == 1
    assert "test@example.com" not in str(report)


def test_ensure_writable_target_refuses_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        ensure_writable_target(target, force=False)

    ensure_writable_target(target, force=True)


def test_derive_clean_candidate_refuses_to_overwrite_input(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("Bu temiz satir yeterince uzundur.\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="same as input"):
        derive_clean_candidate(source, source, source=None, max_document_bytes=1024)
