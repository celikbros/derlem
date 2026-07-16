from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path

from derlem_worker.extraction import (
    DEFAULT_MAX_DOCX_ENTRIES,
    DEFAULT_MAX_DOCX_UNCOMPRESSED_BYTES,
    DEFAULT_MAX_PDF_PAGES,
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_MAX_SOURCE_BYTES,
)


@dataclass(frozen=True)
class Config:
    database_url: str
    storage_root: Path
    staging_root: Path
    import_root: Path
    poll_interval_seconds: float
    lease_timeout_seconds: float
    heartbeat_interval_seconds: float
    document_sample_size: int
    max_document_bytes: int
    extraction_max_source_bytes: int
    extraction_max_docx_entries: int
    extraction_max_docx_uncompressed_bytes: int
    extraction_max_pdf_pages: int
    extraction_max_output_chars: int


def load_config() -> Config:
    _load_dotenv(Path(".env"))
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    storage_root = Path(os.environ.get("STORAGE_ROOT", "./var/storage")).resolve()
    staging_root = Path(os.environ.get("STAGING_ROOT", "./var/staging")).resolve()
    import_root = Path(os.environ.get("IMPORT_ROOT", "./var/import")).resolve()
    poll_value = os.environ.get("WORKER_POLL_INTERVAL", "2s").strip()
    lease_timeout_seconds = _duration_env("WORKER_LEASE_TIMEOUT", "5m")
    heartbeat_interval_seconds = _duration_env("WORKER_HEARTBEAT_INTERVAL", "30s")
    if heartbeat_interval_seconds >= lease_timeout_seconds:
        raise RuntimeError("WORKER_HEARTBEAT_INTERVAL must be shorter than WORKER_LEASE_TIMEOUT")
    return Config(
        database_url=database_url,
        storage_root=storage_root,
        staging_root=staging_root,
        import_root=import_root,
        poll_interval_seconds=_parse_duration_seconds(poll_value),
        lease_timeout_seconds=lease_timeout_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        document_sample_size=_positive_int_env("DOCUMENT_SAMPLE_SIZE", 200),
        max_document_bytes=_positive_int_env("MAX_DOCUMENT_BYTES", 256 * 1024),
        extraction_max_source_bytes=_positive_int_env(
            "EXTRACTION_MAX_SOURCE_BYTES", DEFAULT_MAX_SOURCE_BYTES
        ),
        extraction_max_docx_entries=_positive_int_env(
            "EXTRACTION_MAX_DOCX_ENTRIES", DEFAULT_MAX_DOCX_ENTRIES
        ),
        extraction_max_docx_uncompressed_bytes=_positive_int_env(
            "EXTRACTION_MAX_DOCX_UNCOMPRESSED_BYTES",
            DEFAULT_MAX_DOCX_UNCOMPRESSED_BYTES,
        ),
        extraction_max_pdf_pages=_positive_int_env(
            "EXTRACTION_MAX_PDF_PAGES", DEFAULT_MAX_PDF_PAGES
        ),
        extraction_max_output_chars=_positive_int_env(
            "EXTRACTION_MAX_OUTPUT_CHARS", DEFAULT_MAX_OUTPUT_CHARS
        ),
    )


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _parse_duration_seconds(value: str) -> float:
    units = {"ms": 0.001, "s": 1.0, "m": 60.0}
    for suffix, multiplier in units.items():
        if value.endswith(suffix):
            amount = float(value[: -len(suffix)])
            seconds = amount * multiplier
            if not math.isfinite(amount) or not math.isfinite(seconds) or amount <= 0:
                break
            return seconds
    raise RuntimeError(f"Unsupported WORKER_POLL_INTERVAL: {value!r}")


def _duration_env(key: str, fallback: str) -> float:
    value = os.environ.get(key, fallback).strip()
    try:
        return _parse_duration_seconds(value)
    except (RuntimeError, ValueError) as error:
        raise RuntimeError(f"Unsupported {key}: {value!r}") from error


def _positive_int_env(key: str, fallback: int) -> int:
    value = os.environ.get(key, "").strip()
    if not value:
        return fallback
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{key} must be a positive integer") from error
    if parsed <= 0:
        raise RuntimeError(f"{key} must be a positive integer")
    return parsed
