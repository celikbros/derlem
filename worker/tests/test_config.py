import pytest

from derlem_worker.config import load_config
from derlem_worker.extraction import (
    DEFAULT_MAX_DOCX_ENTRIES,
    DEFAULT_MAX_DOCX_UNCOMPRESSED_BYTES,
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_MAX_PDF_PAGES,
    DEFAULT_MAX_SOURCE_BYTES,
)


EXTRACTION_ENV_KEYS = (
    "EXTRACTION_MAX_SOURCE_BYTES",
    "EXTRACTION_MAX_DOCX_ENTRIES",
    "EXTRACTION_MAX_DOCX_UNCOMPRESSED_BYTES",
    "EXTRACTION_MAX_PDF_PAGES",
    "EXTRACTION_MAX_OUTPUT_CHARS",
)


def _prepare_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    for key in EXTRACTION_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_extraction_limits_have_bounded_defaults(monkeypatch, tmp_path) -> None:
    _prepare_environment(monkeypatch, tmp_path)

    config = load_config()

    assert config.extraction_max_source_bytes == DEFAULT_MAX_SOURCE_BYTES
    assert config.extraction_max_docx_entries == DEFAULT_MAX_DOCX_ENTRIES
    assert (
        config.extraction_max_docx_uncompressed_bytes
        == DEFAULT_MAX_DOCX_UNCOMPRESSED_BYTES
    )
    assert config.extraction_max_pdf_pages == DEFAULT_MAX_PDF_PAGES
    assert config.extraction_max_output_chars == DEFAULT_MAX_OUTPUT_CHARS


def test_extraction_limits_can_be_overridden(monkeypatch, tmp_path) -> None:
    _prepare_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("EXTRACTION_MAX_SOURCE_BYTES", "4096")
    monkeypatch.setenv("EXTRACTION_MAX_DOCX_ENTRIES", "12")
    monkeypatch.setenv("EXTRACTION_MAX_DOCX_UNCOMPRESSED_BYTES", "8192")
    monkeypatch.setenv("EXTRACTION_MAX_PDF_PAGES", "3")
    monkeypatch.setenv("EXTRACTION_MAX_OUTPUT_CHARS", "16384")

    config = load_config()

    assert config.extraction_max_source_bytes == 4096
    assert config.extraction_max_docx_entries == 12
    assert config.extraction_max_docx_uncompressed_bytes == 8192
    assert config.extraction_max_pdf_pages == 3
    assert config.extraction_max_output_chars == 16384


def test_extraction_limits_reject_non_positive_values(monkeypatch, tmp_path) -> None:
    _prepare_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("EXTRACTION_MAX_PDF_PAGES", "0")

    with pytest.raises(
        RuntimeError, match="EXTRACTION_MAX_PDF_PAGES must be a positive integer"
    ):
        load_config()


@pytest.mark.parametrize("value", ["nanm", "infs", "-infs"])
def test_worker_durations_reject_non_finite_values(
    monkeypatch, tmp_path, value: str
) -> None:
    _prepare_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("WORKER_HEARTBEAT_INTERVAL", value)

    with pytest.raises(RuntimeError, match="Unsupported WORKER_HEARTBEAT_INTERVAL"):
        load_config()
