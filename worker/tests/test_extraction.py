from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from derlem_worker.extraction import (
    ExtractionError,
    ExtractionLimits,
    _split_oversized_paragraph,
    convert_file,
    extract_paragraphs,
    media_type_for,
    needs_extraction,
)


def build_minimal_pdf(text_lines: list[str]) -> bytes:
    """Tek sayfalık, gerçek metin içeren asgari geçerli PDF üretir."""
    content_parts = ["BT /F1 12 Tf 50 750 Td"]
    for index, line in enumerate(text_lines):
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        if index > 0:
            content_parts.append("0 -20 Td")
        content_parts.append(f"({escaped}) Tj")
    content_parts.append("ET")
    content = " ".join(content_parts).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_position = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()
    return bytes(output)


def build_docx(path: Path, paragraphs: list[str]) -> None:
    from docx import Document

    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(str(path))


def test_needs_extraction_matches_supported_suffixes():
    assert needs_extraction("kitap.pdf")
    assert needs_extraction("RAPOR.DOCX")
    assert not needs_extraction("corpus.txt")
    assert not needs_extraction("veri.jsonl")
    assert not needs_extraction(None)
    assert not needs_extraction("")


def test_media_type_for_known_suffixes():
    assert media_type_for("a.pdf") == "application/pdf"
    assert media_type_for("a.docx").endswith("wordprocessingml.document")


def test_docx_conversion_produces_line_per_document(tmp_path):
    source = tmp_path / "ornek.docx"
    build_docx(source, ["Birinci paragraf çok önemlidir.", "", "İkinci paragraf şöyledir."])
    target = tmp_path / "cikti.txt"
    report = convert_file(source, target, suffix=".docx")

    raw = target.read_bytes()
    assert b"\r" not in raw
    lines = raw.decode("utf-8").splitlines()
    assert report.document_count == len(lines) == 1  # 4000 karakteri asmadigi icin tek belge
    assert "Birinci paragraf çok önemlidir. İkinci paragraf şöyledir." == lines[0]
    assert report.paragraph_count == 2
    assert report.method == "text-extraction-v1"


def test_docx_chunking_splits_on_paragraph_boundaries(tmp_path):
    source = tmp_path / "uzun.docx"
    paragraphs = [f"Paragraf {i} " + ("kelime " * 80) for i in range(6)]
    build_docx(source, paragraphs)
    target = tmp_path / "cikti.txt"
    report = convert_file(source, target, suffix=".docx", chunk_chars=1200)

    lines = target.read_text(encoding="utf-8").splitlines()
    assert report.document_count == len(lines) > 1
    assert all(len(line) <= 1200 for line in lines)
    assert report.paragraph_count == 6


def test_docx_chunking_splits_one_oversized_paragraph(tmp_path):
    source = tmp_path / "tek-uzun-paragraf.docx"
    paragraph = ("uzun kelime dizisi " * 400).strip()
    build_docx(source, [paragraph])
    target = tmp_path / "cikti.txt"
    report = convert_file(source, target, suffix=".docx", chunk_chars=300)

    lines = target.read_text(encoding="utf-8").splitlines()
    assert report.paragraph_count == 1
    assert report.document_count == len(lines) > 1
    assert all(0 < len(line) <= 300 for line in lines)
    assert " ".join(lines) == paragraph


def test_docx_chunking_hard_splits_one_oversized_token(tmp_path):
    source = tmp_path / "tek-uzun-kelime.docx"
    paragraph = "x" * 1001
    build_docx(source, [paragraph])
    target = tmp_path / "cikti.txt"
    convert_file(source, target, suffix=".docx", chunk_chars=300)

    lines = target.read_text(encoding="utf-8").splitlines()
    assert [len(line) for line in lines] == [300, 300, 300, 101]
    assert "".join(lines) == paragraph


def test_large_single_token_split_is_linear_and_lossless():
    paragraph = "x" * (4 * 1024 * 1024 + 17)

    segments = list(_split_oversized_paragraph(paragraph, 4000))

    assert all(0 < len(segment) <= 4000 for segment in segments)
    assert "".join(segments) == paragraph


def test_extracted_text_aggregate_limit_removes_partial_target(tmp_path):
    source = tmp_path / "fazla-metin.docx"
    build_docx(source, ["123456", "abcdef"])
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="toplam metin sınırı"):
        convert_file(
            source,
            target,
            suffix=".docx",
            limits=ExtractionLimits(max_output_chars=10),
        )

    assert not target.exists()


def test_pdf_conversion_extracts_text(tmp_path):
    source = tmp_path / "ornek.pdf"
    source.write_bytes(build_minimal_pdf(["Merhaba Derlem", "Bu bir deneme sayfasidir"]))
    target = tmp_path / "cikti.txt"
    report = convert_file(source, target, suffix=".pdf")

    text = target.read_text(encoding="utf-8")
    assert "Merhaba Derlem" in text
    assert "deneme sayfasidir" in text
    assert report.document_count >= 1


def test_pdf_without_text_raises_extraction_error(tmp_path):
    source = tmp_path / "bos.pdf"
    source.write_bytes(build_minimal_pdf([]))
    target = tmp_path / "cikti.txt"
    with pytest.raises(ExtractionError):
        convert_file(source, target, suffix=".pdf")
    assert not target.exists()


def test_rejects_binary_source_over_configured_byte_limit(tmp_path):
    source = tmp_path / "buyuk.pdf"
    payload = build_minimal_pdf(["sinir testi"])
    source.write_bytes(payload)
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="kaynak boyutu sınırını"):
        convert_file(
            source,
            target,
            suffix=".pdf",
            limits=ExtractionLimits(max_source_bytes=len(payload) - 1),
        )

    assert not target.exists()


def test_rejects_pdf_content_spoofed_as_docx(tmp_path):
    source = tmp_path / "sahte.docx"
    source.write_bytes(build_minimal_pdf(["aslinda pdf"]))
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="ZIP imzası"):
        convert_file(source, target, suffix=".docx")

    assert not target.exists()


def test_rejects_docx_content_spoofed_as_pdf(tmp_path):
    source = tmp_path / "sahte.pdf"
    build_docx(source, ["aslinda docx"])
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="PDF imzası"):
        convert_file(source, target, suffix=".pdf")

    assert not target.exists()


def test_rejects_corrupt_pdf_after_magic_validation(tmp_path):
    source = tmp_path / "bozuk.pdf"
    source.write_bytes(b"%PDF-1.7\nbozuk-xref")
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="ayrıştırılamadı"):
        convert_file(source, target, suffix=".pdf")

    assert not target.exists()


def test_rejects_corrupt_docx_container_before_parser(tmp_path):
    source = tmp_path / "bozuk.docx"
    source.write_bytes(b"PK\x03\x04bozuk-merkez-dizini")
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="ZIP kapsayıcısı"):
        convert_file(source, target, suffix=".docx")

    assert not target.exists()


def test_rejects_docx_with_corrupt_member_crc(tmp_path):
    source = tmp_path / "bozuk-girdi.docx"
    marker = b"unique-document-payload"
    with ZipFile(source, "w", compression=ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", b"content-types")
        archive.writestr("word/document.xml", marker)
    payload = bytearray(source.read_bytes())
    marker_offset = payload.index(marker)
    payload[marker_offset] ^= 0x1
    source.write_bytes(payload)
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="ZIP girdisi bozuk"):
        convert_file(source, target, suffix=".docx")

    assert not target.exists()


def test_rejects_zip_that_is_not_a_docx(tmp_path):
    source = tmp_path / "sahte.docx"
    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("payload.txt", "docx degil")
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="geçerli bir DOCX"):
        convert_file(source, target, suffix=".docx")

    assert not target.exists()


def test_rejects_docx_zip_entry_count_over_limit(tmp_path):
    source = tmp_path / "cok-girdili.docx"
    build_docx(source, ["gecerli belge"])
    with ZipFile(source, "r") as archive:
        base_entry_count = len(archive.infolist())
    with ZipFile(source, "a", compression=ZIP_DEFLATED) as archive:
        for index in range(3):
            archive.writestr(f"word/media/extra-{index}.bin", b"")
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="girdi sayısı sınırını"):
        convert_file(
            source,
            target,
            suffix=".docx",
            limits=ExtractionLimits(max_docx_entries=base_entry_count + 2),
        )

    assert not target.exists()


def test_rejects_docx_zip_bomb_like_uncompressed_metadata(tmp_path):
    source = tmp_path / "sikistirma-bombasi.docx"
    build_docx(source, ["gecerli belge"])
    with ZipFile(source, "r") as archive:
        base_uncompressed_bytes = sum(entry.file_size for entry in archive.infolist())
    with ZipFile(source, "a", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/media/highly-compressed.bin", b"0" * (1024 * 1024))
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="açılmış içerik boyutu sınırını"):
        convert_file(
            source,
            target,
            suffix=".docx",
            limits=ExtractionLimits(
                max_docx_uncompressed_bytes=base_uncompressed_bytes + 1024
            ),
        )

    assert source.stat().st_size < base_uncompressed_bytes + 1024 * 1024
    assert not target.exists()


def test_rejects_pdf_page_count_over_limit(tmp_path):
    from pypdf import PdfWriter

    source = tmp_path / "cok-sayfali.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as output:
        writer.write(output)
    target = tmp_path / "cikti.txt"

    with pytest.raises(ExtractionError, match="sayfa sınırını"):
        convert_file(
            source,
            target,
            suffix=".pdf",
            limits=ExtractionLimits(max_pdf_pages=1),
        )

    assert not target.exists()


def test_extraction_limits_must_be_positive():
    with pytest.raises(ValueError, match="max_pdf_pages must be positive"):
        ExtractionLimits(max_pdf_pages=0)


def test_unsupported_suffix_raises(tmp_path):
    source = tmp_path / "veri.xyz"
    source.write_text("icerik", encoding="utf-8")
    with pytest.raises(ExtractionError):
        list(extract_paragraphs(source, ".xyz"))
