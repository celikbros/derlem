from pathlib import Path

from derlem_worker.pii import PIIScanner, is_valid_iban, is_valid_luhn, is_valid_tckn


def test_checksum_validators() -> None:
    assert is_valid_tckn("10000000146")
    assert not is_valid_tckn("10000000145")
    assert is_valid_iban("TR330006100519786457841326")
    assert not is_valid_iban("TR340006100519786457841326")
    assert is_valid_luhn("4242 4242 4242 4242")
    assert not is_valid_luhn("4242 4242 4242 4241")


def test_scanner_records_counts_without_values(tmp_path: Path) -> None:
    source = tmp_path / "pii.txt"
    source.write_text(
        "test@example.com\n"
        "10000000146\n"
        "TR330006100519786457841326\n"
        "+90 555 000 00 00\n"
        "4242 4242 4242 4242\n",
        encoding="utf-8",
    )

    report = PIIScanner().scan_file(source)

    assert report.status == "flagged"
    assert report.findings == {
        "tckn": 1,
        "iban": 1,
        "email": 1,
        "phone": 1,
        "payment_card": 1,
    }
    assert "example.com" not in str(report.findings)


def test_scanner_marks_clean_text_clear(tmp_path: Path) -> None:
    source = tmp_path / "clean.txt"
    source.write_text("Bu metin kisisel veri icermiyor.\n", encoding="utf-8")

    report = PIIScanner().scan_file(source)

    assert report.status == "clear"
    assert sum(report.findings.values()) == 0
