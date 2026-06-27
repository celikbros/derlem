from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Callable, Iterable, Iterator

from derlem_worker.sampling import _bounded_lines, _document_from_line


@dataclass(frozen=True)
class DecontaminationMatch:
    source_sha256: str
    source_ordinal: int
    document_sha256: str


@dataclass(frozen=True)
class DecontaminationResult:
    status: str
    method: str
    reference_source_count: int
    reference_document_count: int
    reference_unique_document_count: int
    release_source_count: int
    release_document_count: int
    match_count: int
    sample_matches: tuple[DecontaminationMatch, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["sample_matches"] = [asdict(match) for match in self.sample_matches]
        return value


@dataclass(frozen=True)
class ExportResult:
    format: str
    media_type: str
    sha256: str
    byte_size: int
    record_count: int
    source_count: int
    source_record_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ReleaseGateError(RuntimeError):
    def __init__(self, message: str, gate_results: dict[str, object]) -> None:
        super().__init__(message)
        self.gate_results = gate_results


def exact_decontamination(
    reference_sources: Iterable[tuple[str, Path]],
    release_sources: Iterable[tuple[str, Path]],
    *,
    max_document_bytes: int,
) -> DecontaminationResult:
    references = tuple(reference_sources)
    candidates = tuple(release_sources)
    if max_document_bytes <= 0:
        raise ValueError("max_document_bytes must be positive")

    with tempfile.TemporaryDirectory(prefix="derlem-decontam-") as temp_directory:
        database_path = Path(temp_directory) / "hashes.sqlite3"
        connection = sqlite3.connect(database_path)
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("CREATE TABLE reference_hashes (digest BLOB PRIMARY KEY) WITHOUT ROWID")

            reference_document_count = 0
            batch: list[tuple[bytes]] = []
            for _, path in references:
                for _, digest in _document_digests(path, max_document_bytes):
                    reference_document_count += 1
                    batch.append((digest,))
                    if len(batch) >= 10_000:
                        connection.executemany(
                            "INSERT OR IGNORE INTO reference_hashes(digest) VALUES (?)",
                            batch,
                        )
                        batch.clear()
            if batch:
                connection.executemany(
                    "INSERT OR IGNORE INTO reference_hashes(digest) VALUES (?)",
                    batch,
                )
            connection.commit()
            reference_unique_count = int(
                connection.execute("SELECT count(*) FROM reference_hashes").fetchone()[0]
            )

            release_document_count = 0
            match_count = 0
            samples: list[DecontaminationMatch] = []
            lookup = connection.cursor()
            for source_sha256, path in candidates:
                for ordinal, digest in _document_digests(path, max_document_bytes):
                    release_document_count += 1
                    if lookup.execute(
                        "SELECT 1 FROM reference_hashes WHERE digest = ?",
                        (digest,),
                    ).fetchone() is None:
                        continue
                    match_count += 1
                    if len(samples) < 20:
                        samples.append(
                            DecontaminationMatch(
                                source_sha256=source_sha256,
                                source_ordinal=ordinal,
                                document_sha256=digest.hex(),
                            )
                        )
        finally:
            connection.close()

    return DecontaminationResult(
        status="passed" if match_count == 0 else "blocked",
        method="document-text-sha256-v1",
        reference_source_count=len(references),
        reference_document_count=reference_document_count,
        reference_unique_document_count=reference_unique_count,
        release_source_count=len(candidates),
        release_document_count=release_document_count,
        match_count=match_count,
        sample_matches=tuple(samples),
    )


def build_release_manifest(
    release: dict[str, object],
    sources: list[dict[str, object]],
    gate_results: dict[str, object],
    frozen_at: str,
) -> bytes:
    sorted_sources = sorted(sources, key=lambda source: str(source["source_id"]))
    manifest = {
        "schema_version": "derlem.release-manifest.v1",
        "release": {
            "id": str(release["id"]),
            "name": str(release["name"]),
            "version": str(release["version"]),
            "content_purpose": str(release["content_purpose"]),
            "frozen_at": frozen_at,
        },
        "gate_results": gate_results,
        "sources": sorted_sources,
    }
    return (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def build_release_export(
    release: dict[str, object],
    sources: list[dict[str, object]],
    export_format: str,
    output_path: Path,
    *,
    max_document_bytes: int,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
    progress_interval: int = 50_000,
) -> ExportResult:
    if export_format not in {"jsonl", "txt"}:
        raise ValueError("export_format must be jsonl or txt")
    if max_document_bytes <= 0 or progress_interval <= 0:
        raise ValueError("export limits must be positive")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    byte_size = 0
    record_count = 0
    input_bytes_processed = 0
    source_record_counts: dict[str, int] = {}
    sorted_sources = sorted(sources, key=lambda source: str(source["source_id"]))

    with output_path.open("wb") as output:
        for source_index, source in enumerate(sorted_sources, start=1):
            source_id = str(source["source_id"])
            source_sha256 = str(source["source_sha256"])
            source_records = 0
            for ordinal, raw_line, oversized in _bounded_lines(
                Path(str(source["path"])),
                max_document_bytes,
            ):
                if oversized:
                    raise ReleaseGateError(
                        f"Document at line {ordinal} exceeds the export limit",
                        {
                            "export": {
                                "status": "blocked",
                                "reason": "document_too_large",
                                "source_id": source_id,
                                "source_ordinal": ordinal,
                                "max_document_bytes": max_document_bytes,
                            }
                        },
                    )
                assert raw_line is not None
                input_bytes_processed += len(raw_line.encode("utf-8")) + 1
                stripped = raw_line.strip()
                if not stripped:
                    continue
                text, external_id = _document_from_line(stripped)
                if not text:
                    continue

                document_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
                stable_id = hashlib.sha256(
                    f"{source_sha256}:{ordinal}:{document_sha256}".encode("ascii")
                ).hexdigest()
                if export_format == "jsonl":
                    record = {
                        "id": stable_id,
                        "text": text,
                        "metadata": {
                            "content_purpose": str(release["content_purpose"]),
                            "document_sha256": document_sha256,
                            "domain": str(source["domain"]),
                            "external_id": external_id,
                            "language": str(source["language"]),
                            "license": str(source["license"]),
                            "source_id": source_id,
                            "source_ordinal": ordinal,
                            "source_sha256": source_sha256,
                        },
                    }
                    encoded = (
                        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    ).encode("utf-8")
                else:
                    single_line_text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
                    encoded = (single_line_text + "\n").encode("utf-8")

                output.write(encoded)
                digest.update(encoded)
                byte_size += len(encoded)
                record_count += 1
                source_records += 1
                if progress_callback is not None and record_count % progress_interval == 0:
                    progress_callback(
                        {
                            "input_bytes_processed": input_bytes_processed,
                            "records_written": record_count,
                            "sources_completed": source_index - 1,
                            "source_count": len(sorted_sources),
                            "output_bytes_written": byte_size,
                        }
                    )
            source_record_counts[source_id] = source_records
            if progress_callback is not None:
                progress_callback(
                    {
                        "input_bytes_processed": input_bytes_processed,
                        "records_written": record_count,
                        "sources_completed": source_index,
                        "source_count": len(sorted_sources),
                        "output_bytes_written": byte_size,
                    }
                )

    return ExportResult(
        format=export_format,
        media_type="application/x-ndjson" if export_format == "jsonl" else "text/plain; charset=utf-8",
        sha256=digest.hexdigest(),
        byte_size=byte_size,
        record_count=record_count,
        source_count=len(sorted_sources),
        source_record_counts=source_record_counts,
    )


def build_export_manifest(
    release: dict[str, object],
    sources: list[dict[str, object]],
    result: ExportResult,
) -> bytes:
    manifest_sources = []
    for source in sorted(sources, key=lambda item: str(item["source_id"])):
        source_id = str(source["source_id"])
        manifest_sources.append(
            {
                "source_id": source_id,
                "source_sha256": str(source["source_sha256"]),
                "record_count": result.source_record_counts.get(source_id, 0),
                "language": str(source["language"]),
                "domain": str(source["domain"]),
                "license": str(source["license"]),
            }
        )
    manifest = {
        "schema_version": "derlem.export-manifest.v1",
        "release": {
            "id": str(release["id"]),
            "name": str(release["name"]),
            "version": str(release["version"]),
            "content_purpose": str(release["content_purpose"]),
            "frozen_at": str(release["frozen_at"]),
            "manifest_sha256": str(release["manifest_sha256"]),
        },
        "export": {
            "format": result.format,
            "media_type": result.media_type,
            "sha256": result.sha256,
            "byte_size": result.byte_size,
            "record_count": result.record_count,
            "document_id_method": "source-sha256-ordinal-document-sha256-v1",
        },
        "sources": manifest_sources,
    }
    return (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _document_digests(path: Path, max_document_bytes: int) -> Iterator[tuple[int, bytes]]:
    for ordinal, raw_line, oversized in _bounded_lines(path, max_document_bytes):
        if oversized:
            raise ReleaseGateError(
                f"Document at line {ordinal} exceeds the decontamination limit",
                {
                    "decontamination": {
                        "status": "blocked",
                        "reason": "document_too_large",
                        "source_ordinal": ordinal,
                        "max_document_bytes": max_document_bytes,
                    }
                },
            )
        assert raw_line is not None
        stripped = raw_line.strip()
        if not stripped:
            continue
        text, _ = _document_from_line(stripped)
        if not text:
            continue
        yield ordinal, hashlib.sha256(text.encode("utf-8")).digest()
