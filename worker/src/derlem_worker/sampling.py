from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random


@dataclass(frozen=True)
class SampledDocument:
    source_ordinal: int
    text: str
    external_id: str | None


@dataclass(frozen=True)
class SamplingReport:
    total_documents: int
    eligible_documents: int
    skipped_oversized: int
    samples: tuple[SampledDocument, ...]


def sample_line_documents(
    path: Path,
    *,
    sample_size: int,
    max_document_bytes: int,
    seed: str,
) -> SamplingReport:
    if sample_size <= 0 or max_document_bytes <= 0:
        raise ValueError("Sampling limits must be positive")

    generator = random.Random(int(seed[:16], 16))
    reservoir: list[SampledDocument] = []
    total_documents = 0
    eligible_documents = 0
    skipped_oversized = 0

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
        text, external_id = _document_from_line(stripped)
        if not text:
            continue
        eligible_documents += 1
        candidate = SampledDocument(ordinal, text, external_id)
        if len(reservoir) < sample_size:
            reservoir.append(candidate)
            continue
        replacement = generator.randrange(eligible_documents)
        if replacement < sample_size:
            reservoir[replacement] = candidate

    reservoir.sort(key=lambda item: item.source_ordinal)
    return SamplingReport(
        total_documents=total_documents,
        eligible_documents=eligible_documents,
        skipped_oversized=skipped_oversized,
        samples=tuple(reservoir),
    )


def _bounded_lines(path: Path, max_bytes: int):
    with path.open("rb") as source:
        ordinal = 0
        while True:
            chunk = source.readline(max_bytes + 1)
            if not chunk:
                return
            ordinal += 1
            oversized = len(chunk) > max_bytes
            if oversized and not chunk.endswith(b"\n"):
                while chunk and not chunk.endswith(b"\n"):
                    chunk = source.readline(max_bytes + 1)
            if oversized:
                yield ordinal, None, True
                continue
            yield ordinal, chunk.decode("utf-8").rstrip("\r\n"), False


def _document_from_line(line: str) -> tuple[str, str | None]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return line, None
    if not isinstance(value, dict):
        return line, None

    external_id_value = value.get("id")
    external_id = str(external_id_value) if isinstance(external_id_value, (str, int)) else None
    for key in ("text", "content", "body"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip(), external_id
    return line, external_id
