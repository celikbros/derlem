from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import unicodedata

from derlem_worker.sampling import _bounded_lines, _document_from_line

FINGERPRINT_VERSION = "normalized-document-sha256-v1"
MIN_NORMALIZED_CHARS = 32
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class DocumentFingerprint:
    source_ordinal: int
    normalized_sha256: str
    normalized_char_count: int


@dataclass(frozen=True)
class FingerprintReport:
    fingerprint_version: str
    total_documents: int
    indexed_documents: int
    skipped_oversized: int
    skipped_too_short: int


def normalize_document_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.casefold()
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def document_fingerprint(text: str) -> tuple[str, int] | None:
    normalized = normalize_document_text(text)
    if len(normalized) < MIN_NORMALIZED_CHARS:
        return None
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest, len(normalized)


def iter_document_fingerprints(
    path: Path,
    *,
    max_document_bytes: int,
) -> tuple[FingerprintReport, tuple[DocumentFingerprint, ...]]:
    total_documents = 0
    indexed_documents = 0
    skipped_oversized = 0
    skipped_too_short = 0
    fingerprints: list[DocumentFingerprint] = []

    for ordinal, raw_line, oversized in _bounded_lines(path, max_document_bytes):
        if oversized:
            total_documents += 1
            skipped_oversized += 1
            continue
        assert raw_line is not None
        stripped = raw_line.strip()
        if not stripped:
            continue
        total_documents += 1
        text, _ = _document_from_line(stripped)
        if not text:
            continue
        fingerprint = document_fingerprint(text)
        if fingerprint is None:
            skipped_too_short += 1
            continue
        normalized_sha256, normalized_char_count = fingerprint
        indexed_documents += 1
        fingerprints.append(
            DocumentFingerprint(
                source_ordinal=ordinal,
                normalized_sha256=normalized_sha256,
                normalized_char_count=normalized_char_count,
            )
        )

    return (
        FingerprintReport(
            fingerprint_version=FINGERPRINT_VERSION,
            total_documents=total_documents,
            indexed_documents=indexed_documents,
            skipped_oversized=skipped_oversized,
            skipped_too_short=skipped_too_short,
        ),
        tuple(fingerprints),
    )
