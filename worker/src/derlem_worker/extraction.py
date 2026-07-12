"""Belge ekstraksiyonu: PDF/DOCX -> satır başına belge TXT.

Yüklenen ikili belgeler kanonik metin formatına burada çevrilir. Kural:
paragraflar normalize edilir (iç boşluk/yeni satır tek boşluğa iner) ve
paragraf sınırlarında bölünerek en fazla ``chunk_chars`` karakterlik
belgeler hâlinde, satır başına bir belge olacak şekilde LF ile yazılır.
Görüntü tabanlı (metinsiz) PDF'ler v1'de desteklenmez; OCR ayrı iştir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterator

EXTRACTION_VERSION = "text-extraction-v1"
SUPPORTED_SUFFIXES = {".pdf", ".docx"}
DEFAULT_CHUNK_CHARS = 4000
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_WHITESPACE_RE = re.compile(r"\s+")


class ExtractionError(ValueError):
    """Belgeden kullanılabilir metin çıkarılamadı."""


@dataclass(frozen=True)
class ExtractionReport:
    method: str
    suffix: str
    paragraph_count: int
    document_count: int
    total_chars: int


def needs_extraction(filename: str | None) -> bool:
    if not filename:
        return False
    return Path(filename).suffix.lower() in SUPPORTED_SUFFIXES


def media_type_for(filename: str) -> str:
    return MEDIA_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def _pdf_paragraphs(path: Path) -> Iterator[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ExtractionError("Şifreli PDF desteklenmiyor; şifresini kaldırıp yeniden yükleyin.")
    for page in reader.pages:
        text = page.extract_text() or ""
        for block in re.split(r"\n\s*\n", text):
            yield block


def _docx_paragraphs(path: Path) -> Iterator[str]:
    from docx import Document

    document = Document(str(path))
    for paragraph in document.paragraphs:
        yield paragraph.text
    for table in document.tables:
        for row in table.rows:
            yield " | ".join(cell.text for cell in row.cells)


def extract_paragraphs(path: Path, suffix: str) -> Iterator[str]:
    suffix = suffix.lower()
    if suffix == ".pdf":
        source = _pdf_paragraphs(path)
    elif suffix == ".docx":
        source = _docx_paragraphs(path)
    else:
        raise ExtractionError(f"Desteklenmeyen belge türü: {suffix}")
    for raw in source:
        normalized = _WHITESPACE_RE.sub(" ", raw).strip()
        if normalized:
            yield normalized


def convert_file(
    source_path: Path,
    target_path: Path,
    *,
    suffix: str,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
) -> ExtractionReport:
    """Belgeyi satır-başına-belge TXT'ye çevirir ve raporunu döndürür."""
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be positive")
    paragraph_count = 0
    document_count = 0
    total_chars = 0
    chunk: list[str] = []
    chunk_size = 0

    with target_path.open("wb") as target:

        def flush() -> None:
            nonlocal chunk, chunk_size, document_count, total_chars
            if not chunk:
                return
            line = " ".join(chunk)
            target.write(line.encode("utf-8") + b"\n")
            document_count += 1
            total_chars += len(line)
            chunk = []
            chunk_size = 0

        for paragraph in extract_paragraphs(source_path, suffix):
            paragraph_count += 1
            addition = len(paragraph) if not chunk else len(paragraph) + 1
            if chunk and chunk_size + addition > chunk_chars:
                flush()
                addition = len(paragraph)
            chunk.append(paragraph)
            chunk_size += addition
        flush()

    if document_count == 0:
        target_path.unlink(missing_ok=True)
        raise ExtractionError(
            "Belgeden metin çıkarılamadı; dosya görüntü tabanlı (taranmış) olabilir. "
            "OCR bu sürümde desteklenmiyor."
        )
    return ExtractionReport(
        method=EXTRACTION_VERSION,
        suffix=suffix.lower(),
        paragraph_count=paragraph_count,
        document_count=document_count,
        total_chars=total_chars,
    )
