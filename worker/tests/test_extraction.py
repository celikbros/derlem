from pathlib import Path

import pytest

from derlem_worker.extraction import (
    ExtractionError,
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


def test_unsupported_suffix_raises(tmp_path):
    source = tmp_path / "veri.xyz"
    source.write_text("icerik", encoding="utf-8")
    with pytest.raises(ExtractionError):
        list(extract_paragraphs(source, ".xyz"))
