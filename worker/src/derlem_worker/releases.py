from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Iterable, Iterator

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
