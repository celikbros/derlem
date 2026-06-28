from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import hashlib
import heapq
import json
from pathlib import Path
import random
import re
from typing import Callable
import unicodedata


SAMPLING_METHOD = "risk-stratified-sha256-v1"
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_REPEATED_CHARACTER_RE = re.compile(r"(.)\1{7,}", re.DOTALL)
_IDENTIFIER_RE = re.compile(
    r"(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\bTR\d{24}\b|(?<!\d)\d{11}(?!\d))",
    re.IGNORECASE,
)
ProgressCallback = Callable[[dict[str, int]], None]
ByteProgressCallback = Callable[[int, int], None]
PROGRESS_INTERVAL_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class SampledDocument:
    source_ordinal: int
    text: str
    external_id: str | None
    risk_score: int = 0
    risk_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SamplingReport:
    sampling_method: str
    total_documents: int
    eligible_documents: int
    skipped_oversized: int
    risk_candidate_documents: int
    selected_risk_documents: int
    risk_reason_counts: dict[str, int]
    samples: tuple[SampledDocument, ...]


def sample_line_documents(
    path: Path,
    *,
    sample_size: int,
    max_document_bytes: int,
    seed: str,
    progress_callback: ProgressCallback | None = None,
    progress_interval_bytes: int = PROGRESS_INTERVAL_BYTES,
) -> SamplingReport:
    if sample_size <= 0 or max_document_bytes <= 0 or progress_interval_bytes <= 0:
        raise ValueError("Sampling limits must be positive")

    generator = random.Random(int(seed[:16], 16))
    reservoir: list[SampledDocument] = []
    risk_quota = max(1, sample_size // 2)
    risk_heap: list[tuple[int, int, int, SampledDocument]] = []
    risk_reason_counts: Counter[str] = Counter()
    total_documents = 0
    eligible_documents = 0
    skipped_oversized = 0
    risk_candidate_documents = 0

    def report_progress(bytes_processed: int, lines_read: int) -> None:
        if progress_callback is None:
            return
        progress_callback(
            {
                "input_bytes_processed": bytes_processed,
                "input_bytes_total": path.stat().st_size,
                "lines_read": lines_read,
                "documents_scanned": total_documents,
                "eligible_documents": eligible_documents,
                "skipped_oversized": skipped_oversized,
                "risk_candidate_documents": risk_candidate_documents,
            }
        )

    for ordinal, raw_line, oversized in _bounded_lines(
        path,
        max_document_bytes,
        progress_callback=report_progress,
        progress_interval_bytes=progress_interval_bytes,
    ):
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
        risk_score, risk_reasons = score_document_risk(text, stripped)
        candidate = SampledDocument(ordinal, text, external_id, risk_score, risk_reasons)
        if risk_score > 0:
            risk_candidate_documents += 1
            risk_reason_counts.update(risk_reasons)
            tie_breaker = int(
                hashlib.sha256(f"{seed}:{ordinal}".encode("ascii")).hexdigest()[:16],
                16,
            )
            ranked = (risk_score, tie_breaker, ordinal, candidate)
            if len(risk_heap) < risk_quota:
                heapq.heappush(risk_heap, ranked)
            elif ranked[:3] > risk_heap[0][:3]:
                heapq.heapreplace(risk_heap, ranked)
        if len(reservoir) < sample_size:
            reservoir.append(candidate)
            continue
        replacement = generator.randrange(eligible_documents)
        if replacement < sample_size:
            reservoir[replacement] = candidate

    selected: list[SampledDocument] = []
    selected_ordinals: set[int] = set()
    for _, _, _, candidate in sorted(risk_heap, reverse=True):
        selected.append(candidate)
        selected_ordinals.add(candidate.source_ordinal)
    for candidate in reservoir:
        if len(selected) >= sample_size:
            break
        if candidate.source_ordinal in selected_ordinals:
            continue
        selected.append(candidate)
        selected_ordinals.add(candidate.source_ordinal)

    selected.sort(key=lambda item: item.source_ordinal)
    return SamplingReport(
        sampling_method=SAMPLING_METHOD,
        total_documents=total_documents,
        eligible_documents=eligible_documents,
        skipped_oversized=skipped_oversized,
        risk_candidate_documents=risk_candidate_documents,
        selected_risk_documents=sum(sample.risk_score > 0 for sample in selected),
        risk_reason_counts=dict(sorted(risk_reason_counts.items())),
        samples=tuple(selected),
    )


def score_document_risk(text: str, raw_line: str | None = None) -> tuple[int, tuple[str, ...]]:
    reasons: list[str] = []
    score = 0
    length = len(text)

    if length < 24:
        reasons.append("short_text")
        score += 1
    if length > 4_000:
        reasons.append("long_text")
        score += 2
    if any(unicodedata.category(character) in {"Cc", "Cf"} and not character.isspace() for character in text):
        reasons.append("control_characters")
        score += 3
    if length >= 40:
        symbol_count = sum(not character.isalnum() and not character.isspace() for character in text)
        if symbol_count / length > 0.35:
            reasons.append("high_symbol_ratio")
            score += 2
    if _REPEATED_CHARACTER_RE.search(text):
        reasons.append("repeated_character_run")
        score += 2

    words = [word.casefold() for word in _WORD_RE.findall(text)]
    if len(words) >= 20 and len(set(words)) / len(words) < 0.25:
        reasons.append("low_lexical_diversity")
        score += 2
    if _IDENTIFIER_RE.search(text):
        reasons.append("identifier_pattern")
        score += 3

    if raw_line is not None and raw_line.lstrip().startswith("{"):
        try:
            structured = json.loads(raw_line)
        except json.JSONDecodeError:
            reasons.append("malformed_json")
            score += 2
        else:
            if isinstance(structured, dict) and not any(
                isinstance(structured.get(key), str) and structured[key].strip()
                for key in ("text", "content", "body")
            ):
                reasons.append("missing_text_field")
                score += 2

    return min(score, 10), tuple(reasons)


def _bounded_lines(
    path: Path,
    max_bytes: int,
    *,
    progress_callback: ByteProgressCallback | None = None,
    progress_interval_bytes: int = PROGRESS_INTERVAL_BYTES,
):
    if progress_interval_bytes <= 0:
        raise ValueError("progress_interval_bytes must be positive")
    with path.open("rb") as source:
        ordinal = 0
        next_progress_at = progress_interval_bytes
        while True:
            chunk = source.readline(max_bytes + 1)
            if not chunk:
                if progress_callback is not None:
                    progress_callback(source.tell(), ordinal)
                return
            ordinal += 1
            oversized = len(chunk) > max_bytes
            if oversized and not chunk.endswith(b"\n"):
                while chunk and not chunk.endswith(b"\n"):
                    chunk = source.readline(max_bytes + 1)
            bytes_processed = source.tell()
            if progress_callback is not None and bytes_processed >= next_progress_at:
                progress_callback(bytes_processed, ordinal)
                while next_progress_at <= bytes_processed:
                    next_progress_at += progress_interval_bytes
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
