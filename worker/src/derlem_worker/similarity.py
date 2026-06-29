from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import sqlite3
import tempfile
from typing import Callable, Iterable, Iterator

from derlem_worker.fingerprints import normalize_document_text
from derlem_worker.sampling import _bounded_lines, _document_from_line


SIMHASH_VERSION = "normalized-word-3gram-simhash64-v1"
APPROXIMATE_METHOD = f"{SIMHASH_VERSION}-hamming10-bands8x8-v1"
SHINGLE_SIZE = 3
MIN_TOKENS = 5
SIGNATURE_BITS = 64
BAND_COUNT = 8
BAND_BITS = 8
DEFAULT_HAMMING_THRESHOLD = 10
DEFAULT_MAX_CANDIDATES = 5_000


@dataclass(frozen=True)
class ApproximateMatch:
    release_source_sha256: str
    release_source_ordinal: int
    reference_source_sha256: str
    reference_source_ordinal: int
    hamming_distance: int
    similarity_estimate_bps: int


@dataclass(frozen=True)
class ApproximateDecontaminationResult:
    status: str
    method: str
    hamming_threshold: int
    max_candidates_per_document: int
    reference_source_count: int
    reference_document_count: int
    reference_indexed_count: int
    reference_unique_signature_count: int
    release_source_count: int
    release_document_count: int
    release_indexed_count: int
    skipped_too_short_count: int
    skipped_oversized_count: int
    potential_match_count: int
    candidate_overflow_document_count: int
    sample_matches: tuple[ApproximateMatch, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["sample_matches"] = [asdict(match) for match in self.sample_matches]
        return value


@dataclass
class _ScanStats:
    document_count: int = 0
    indexed_count: int = 0
    skipped_too_short: int = 0
    skipped_oversized: int = 0


def document_simhash(text: str) -> int | None:
    normalized = normalize_document_text(text)
    tokens = normalized.split()
    if len(tokens) < MIN_TOKENS:
        return None

    weights = [0] * SIGNATURE_BITS
    for index in range(len(tokens) - SHINGLE_SIZE + 1):
        shingle = "\x1f".join(tokens[index : index + SHINGLE_SIZE]).encode("utf-8")
        digest = int.from_bytes(
            hashlib.blake2b(shingle, digest_size=8, person=b"DerlemSH").digest(),
            "big",
        )
        for bit in range(SIGNATURE_BITS):
            weights[bit] += 1 if digest & (1 << bit) else -1

    signature = 0
    for bit, weight in enumerate(weights):
        if weight > 0:
            signature |= 1 << bit
    return signature


def hamming_distance(first: int, second: int) -> int:
    return (first ^ second).bit_count()


def approximate_decontamination(
    reference_sources: Iterable[tuple[str, Path]],
    release_sources: Iterable[tuple[str, Path]],
    *,
    max_document_bytes: int,
    hamming_threshold: int = DEFAULT_HAMMING_THRESHOLD,
    max_candidates_per_document: int = DEFAULT_MAX_CANDIDATES,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
    progress_interval: int = 50_000,
) -> ApproximateDecontaminationResult:
    references = tuple(reference_sources)
    candidates = tuple(release_sources)
    if max_document_bytes <= 0:
        raise ValueError("max_document_bytes must be positive")
    if not 0 <= hamming_threshold <= SIGNATURE_BITS:
        raise ValueError("hamming_threshold must be between 0 and 64")
    if max_candidates_per_document <= 0:
        raise ValueError("max_candidates_per_document must be positive")
    if progress_interval <= 0:
        raise ValueError("progress_interval must be positive")

    reference_stats = _ScanStats()
    release_stats = _ScanStats()
    potential_match_count = 0
    overflow_count = 0
    samples: list[ApproximateMatch] = []

    with tempfile.TemporaryDirectory(prefix="derlem-approx-decontam-") as temp_directory:
        connection = sqlite3.connect(Path(temp_directory) / "simhash.sqlite3")
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute(
                """
                CREATE TABLE reference_signatures (
                    id INTEGER PRIMARY KEY,
                    signature BLOB NOT NULL UNIQUE,
                    source_sha256 TEXT NOT NULL,
                    source_ordinal INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE reference_bands (
                    band INTEGER NOT NULL,
                    bucket INTEGER NOT NULL,
                    reference_id INTEGER NOT NULL REFERENCES reference_signatures(id),
                    PRIMARY KEY (band, bucket, reference_id)
                ) WITHOUT ROWID
                """
            )
            connection.execute(
                "CREATE INDEX reference_bands_lookup_idx ON reference_bands(band, bucket)"
            )

            for source_sha256, path in references:
                for ordinal, signature in _iter_simhashes(
                    path,
                    max_document_bytes=max_document_bytes,
                    stats=reference_stats,
                ):
                    inserted = connection.execute(
                        """
                        INSERT OR IGNORE INTO reference_signatures(signature, source_sha256, source_ordinal)
                        VALUES (?, ?, ?)
                        """,
                        (_signature_bytes(signature), source_sha256, ordinal),
                    )
                    if inserted.rowcount != 1:
                        continue
                    reference_id = int(inserted.lastrowid)
                    connection.executemany(
                        "INSERT INTO reference_bands(band, bucket, reference_id) VALUES (?, ?, ?)",
                        [
                            (band, _band_bucket(signature, band), reference_id)
                            for band in range(BAND_COUNT)
                        ],
                    )
                    if (
                        progress_callback is not None
                        and reference_stats.indexed_count % progress_interval == 0
                    ):
                        progress_callback(
                            _progress(
                                reference_stats,
                                release_stats,
                                potential_match_count,
                                overflow_count,
                            )
                        )
            connection.commit()
            unique_signature_count = int(
                connection.execute("SELECT count(*) FROM reference_signatures").fetchone()[0]
            )

            candidate_query = _candidate_query(max_candidates_per_document + 1)
            for release_source_sha256, path in candidates:
                for release_ordinal, signature in _iter_simhashes(
                    path,
                    max_document_bytes=max_document_bytes,
                    stats=release_stats,
                ):
                    parameters: list[int] = []
                    for band in range(BAND_COUNT):
                        parameters.extend((band, _band_bucket(signature, band)))
                    rows = connection.execute(candidate_query, parameters).fetchall()
                    if len(rows) > max_candidates_per_document:
                        overflow_count += 1
                        rows = rows[:max_candidates_per_document]

                    best: tuple[int, str, int] | None = None
                    for reference_signature_bytes, reference_source_sha256, reference_ordinal in rows:
                        distance = hamming_distance(
                            signature,
                            int.from_bytes(reference_signature_bytes, "big"),
                        )
                        if distance > hamming_threshold:
                            continue
                        candidate = (distance, str(reference_source_sha256), int(reference_ordinal))
                        if best is None or candidate < best:
                            best = candidate
                    if best is not None:
                        potential_match_count += 1
                    if best is not None and len(samples) < 20:
                        distance, reference_source_sha256, reference_ordinal = best
                        samples.append(
                            ApproximateMatch(
                                release_source_sha256=release_source_sha256,
                                release_source_ordinal=release_ordinal,
                                reference_source_sha256=reference_source_sha256,
                                reference_source_ordinal=reference_ordinal,
                                hamming_distance=distance,
                                similarity_estimate_bps=_similarity_bps(distance),
                            )
                        )
                    if (
                        progress_callback is not None
                        and release_stats.indexed_count % progress_interval == 0
                    ):
                        progress_callback(
                            _progress(
                                reference_stats,
                                release_stats,
                                potential_match_count,
                                overflow_count,
                            )
                        )
        finally:
            connection.close()

    if progress_callback is not None:
        progress_callback(
            _progress(
                reference_stats,
                release_stats,
                potential_match_count,
                overflow_count,
            )
        )

    return ApproximateDecontaminationResult(
        status="inconclusive" if overflow_count else "reported",
        method=APPROXIMATE_METHOD,
        hamming_threshold=hamming_threshold,
        max_candidates_per_document=max_candidates_per_document,
        reference_source_count=len(references),
        reference_document_count=reference_stats.document_count,
        reference_indexed_count=reference_stats.indexed_count,
        reference_unique_signature_count=unique_signature_count,
        release_source_count=len(candidates),
        release_document_count=release_stats.document_count,
        release_indexed_count=release_stats.indexed_count,
        skipped_too_short_count=(
            reference_stats.skipped_too_short + release_stats.skipped_too_short
        ),
        skipped_oversized_count=(
            reference_stats.skipped_oversized + release_stats.skipped_oversized
        ),
        potential_match_count=potential_match_count,
        candidate_overflow_document_count=overflow_count,
        sample_matches=tuple(samples),
    )


def _iter_simhashes(
    path: Path,
    *,
    max_document_bytes: int,
    stats: _ScanStats,
) -> Iterator[tuple[int, int]]:
    for ordinal, raw_line, oversized in _bounded_lines(path, max_document_bytes):
        if oversized:
            stats.document_count += 1
            stats.skipped_oversized += 1
            continue
        assert raw_line is not None
        stripped = raw_line.strip()
        if not stripped:
            continue
        stats.document_count += 1
        text, _ = _document_from_line(stripped)
        signature = document_simhash(text)
        if signature is None:
            stats.skipped_too_short += 1
            continue
        stats.indexed_count += 1
        yield ordinal, signature


def _signature_bytes(signature: int) -> bytes:
    return signature.to_bytes(8, "big")


def _band_bucket(signature: int, band: int) -> int:
    return (signature >> (band * BAND_BITS)) & ((1 << BAND_BITS) - 1)


def _candidate_query(limit: int) -> str:
    predicates = " OR ".join("(band.band = ? AND band.bucket = ?)" for _ in range(BAND_COUNT))
    return f"""
        SELECT DISTINCT reference.signature, reference.source_sha256, reference.source_ordinal
        FROM reference_bands AS band
        JOIN reference_signatures AS reference ON reference.id = band.reference_id
        WHERE {predicates}
        ORDER BY reference.signature, reference.source_sha256, reference.source_ordinal
        LIMIT {int(limit)}
    """


def _similarity_bps(distance: int) -> int:
    return ((SIGNATURE_BITS - distance) * 10_000 + SIGNATURE_BITS // 2) // SIGNATURE_BITS


def _progress(
    reference_stats: _ScanStats,
    release_stats: _ScanStats,
    potential_match_count: int,
    overflow_count: int,
) -> dict[str, int]:
    return {
        "reference_documents_scanned": reference_stats.document_count,
        "reference_documents_indexed": reference_stats.indexed_count,
        "release_documents_scanned": release_stats.document_count,
        "release_documents_indexed": release_stats.indexed_count,
        "potential_matches": potential_match_count,
        "candidate_overflow_documents": overflow_count,
    }
