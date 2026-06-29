from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Callable, Iterable, Iterator

from derlem_worker.canonical import CanonicalSampleError, parse_canonical_sample
from derlem_worker.fingerprints import normalize_document_text
from derlem_worker.sampling import _bounded_lines, _document_from_line


SIMHASH_VERSION = "normalized-word-3gram-simhash64-v1"
SHINGLE_SIZE = 3
MIN_TOKENS = 5
SIGNATURE_BITS = 64
BAND_COUNT = 8
BAND_BITS = 8
DEFAULT_HAMMING_THRESHOLD = 10
DEFAULT_MAX_CANDIDATES = 5_000
RELEASE_NEAR_DUP_SCHEMA_VERSION = "derlem.release-near-dedup-report.v1"
RELEASE_NEAR_DUP_THRESHOLD = 3
RELEASE_NEAR_DUP_BAND_COUNT = 4
RELEASE_NEAR_DUP_BAND_BITS = 16


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


@dataclass(frozen=True)
class ReleaseNearDuplicatePair:
    source_sha256: str
    source_ordinal: int
    matched_source_sha256: str
    matched_source_ordinal: int
    relation: str
    hamming_distance: int
    similarity_estimate_bps: int


@dataclass(frozen=True)
class ReleaseNearDuplicateResult:
    schema_version: str
    status: str
    method: str
    hamming_threshold: int
    max_candidates_per_document: int
    source_count: int
    document_count: int
    indexed_document_count: int
    skipped_too_short_count: int
    skipped_oversized_count: int
    potential_pair_count: int
    within_source_pair_count: int
    cross_source_pair_count: int
    candidate_overflow_document_count: int
    sample_pairs: tuple[ReleaseNearDuplicatePair, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["sample_pairs"] = [asdict(pair) for pair in self.sample_pairs]
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

    bit_planes: list[int] = []
    shingle_count = len(tokens) - SHINGLE_SIZE + 1
    for index in range(len(tokens) - SHINGLE_SIZE + 1):
        shingle = "\x1f".join(tokens[index : index + SHINGLE_SIZE]).encode("utf-8")
        digest = int.from_bytes(
            hashlib.blake2b(shingle, digest_size=8, person=b"DerlemSH").digest(),
            "big",
        )
        _add_to_bit_planes(bit_planes, digest)

    signature = 0
    for bit in range(SIGNATURE_BITS):
        count = sum(
            (1 << plane_index)
            for plane_index, plane in enumerate(bit_planes)
            if plane & (1 << bit)
        )
        if count * 2 > shingle_count:
            signature |= 1 << bit
    return signature


def _add_to_bit_planes(bit_planes: list[int], value: int) -> None:
    carry = value
    plane_index = 0
    while carry:
        if plane_index == len(bit_planes):
            bit_planes.append(carry)
            return
        next_carry = bit_planes[plane_index] & carry
        bit_planes[plane_index] ^= carry
        carry = next_carry
        plane_index += 1


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
        method=_method_identifier(hamming_threshold, BAND_COUNT, BAND_BITS),
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


def release_near_duplicates(
    sources: Iterable[tuple[str, Path]],
    *,
    max_document_bytes: int,
    hamming_threshold: int = RELEASE_NEAR_DUP_THRESHOLD,
    max_candidates_per_document: int = DEFAULT_MAX_CANDIDATES,
    progress_callback: Callable[[dict[str, int]], None] | None = None,
    progress_interval: int = 50_000,
) -> ReleaseNearDuplicateResult:
    candidates = tuple(sorted(sources, key=lambda source: (source[0], str(source[1]))))
    if max_document_bytes <= 0:
        raise ValueError("max_document_bytes must be positive")
    if not 0 <= hamming_threshold <= SIGNATURE_BITS:
        raise ValueError("hamming_threshold must be between 0 and 64")
    if max_candidates_per_document <= 0:
        raise ValueError("max_candidates_per_document must be positive")
    if progress_interval <= 0:
        raise ValueError("progress_interval must be positive")

    stats = _ScanStats()
    potential_pair_count = 0
    within_source_pair_count = 0
    cross_source_pair_count = 0
    overflow_count = 0
    samples: list[ReleaseNearDuplicatePair] = []

    with tempfile.TemporaryDirectory(prefix="derlem-release-near-dedup-") as temp_directory:
        connection = sqlite3.connect(Path(temp_directory) / "simhash.sqlite3")
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute(
                """
                CREATE TABLE release_signatures (
                    id INTEGER PRIMARY KEY,
                    signature BLOB NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    source_ordinal INTEGER NOT NULL,
                    UNIQUE (source_sha256, source_ordinal)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE release_bands (
                    band INTEGER NOT NULL,
                    bucket INTEGER NOT NULL,
                    release_id INTEGER NOT NULL REFERENCES release_signatures(id),
                    PRIMARY KEY (band, bucket, release_id)
                ) WITHOUT ROWID
                """
            )
            connection.execute(
                "CREATE INDEX release_bands_lookup_idx ON release_bands(band, bucket)"
            )
            candidate_query = _release_candidate_query(max_candidates_per_document + 1)

            for source_sha256, path in candidates:
                for ordinal, signature in _iter_simhashes(
                    path,
                    max_document_bytes=max_document_bytes,
                    stats=stats,
                ):
                    parameters: list[int] = []
                    for band in range(RELEASE_NEAR_DUP_BAND_COUNT):
                        parameters.extend(
                            (
                                band,
                                _band_bucket(
                                    signature,
                                    band,
                                    band_bits=RELEASE_NEAR_DUP_BAND_BITS,
                                ),
                            )
                        )
                    rows = connection.execute(candidate_query, parameters).fetchall()
                    if len(rows) > max_candidates_per_document:
                        overflow_count += 1
                        rows = rows[:max_candidates_per_document]

                    for matched_signature_bytes, matched_source_sha256, matched_ordinal in rows:
                        distance = hamming_distance(
                            signature,
                            int.from_bytes(matched_signature_bytes, "big"),
                        )
                        if distance > hamming_threshold:
                            continue
                        matched_source = str(matched_source_sha256)
                        relation = (
                            "within_source" if source_sha256 == matched_source else "cross_source"
                        )
                        potential_pair_count += 1
                        if relation == "within_source":
                            within_source_pair_count += 1
                        else:
                            cross_source_pair_count += 1
                        if len(samples) < 20:
                            samples.append(
                                ReleaseNearDuplicatePair(
                                    source_sha256=source_sha256,
                                    source_ordinal=ordinal,
                                    matched_source_sha256=matched_source,
                                    matched_source_ordinal=int(matched_ordinal),
                                    relation=relation,
                                    hamming_distance=distance,
                                    similarity_estimate_bps=_similarity_bps(distance),
                                )
                            )

                    inserted = connection.execute(
                        """
                        INSERT INTO release_signatures(signature, source_sha256, source_ordinal)
                        VALUES (?, ?, ?)
                        """,
                        (_signature_bytes(signature), source_sha256, ordinal),
                    )
                    release_id = int(inserted.lastrowid)
                    connection.executemany(
                        "INSERT INTO release_bands(band, bucket, release_id) VALUES (?, ?, ?)",
                        [
                            (
                                band,
                                _band_bucket(
                                    signature,
                                    band,
                                    band_bits=RELEASE_NEAR_DUP_BAND_BITS,
                                ),
                                release_id,
                            )
                            for band in range(RELEASE_NEAR_DUP_BAND_COUNT)
                        ],
                    )
                    if progress_callback is not None and stats.indexed_count % progress_interval == 0:
                        progress_callback(
                            _near_duplicate_progress(
                                stats,
                                potential_pair_count,
                                within_source_pair_count,
                                cross_source_pair_count,
                                overflow_count,
                            )
                        )
            connection.commit()
        finally:
            connection.close()

    if progress_callback is not None:
        progress_callback(
            _near_duplicate_progress(
                stats,
                potential_pair_count,
                within_source_pair_count,
                cross_source_pair_count,
                overflow_count,
            )
        )

    return ReleaseNearDuplicateResult(
        schema_version=RELEASE_NEAR_DUP_SCHEMA_VERSION,
        status="inconclusive" if overflow_count else "reported",
        method=_method_identifier(
            hamming_threshold,
            RELEASE_NEAR_DUP_BAND_COUNT,
            RELEASE_NEAR_DUP_BAND_BITS,
        ),
        hamming_threshold=hamming_threshold,
        max_candidates_per_document=max_candidates_per_document,
        source_count=len(candidates),
        document_count=stats.document_count,
        indexed_document_count=stats.indexed_count,
        skipped_too_short_count=stats.skipped_too_short,
        skipped_oversized_count=stats.skipped_oversized,
        potential_pair_count=potential_pair_count,
        within_source_pair_count=within_source_pair_count,
        cross_source_pair_count=cross_source_pair_count,
        candidate_overflow_document_count=overflow_count,
        sample_pairs=tuple(samples),
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
        text = _similarity_text_from_line(stripped)
        signature = document_simhash(text)
        if signature is None:
            stats.skipped_too_short += 1
            continue
        stats.indexed_count += 1
        yield ordinal, signature


def _similarity_text_from_line(line: str) -> str:
    text, _ = _document_from_line(line)
    if text != line:
        return text
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return text
    if not isinstance(value, dict) or value.get("schema_version") != "derlem.canonical-sample.v1":
        return text
    purpose = value.get("content_purpose")
    if not isinstance(purpose, str):
        return text
    try:
        sample = parse_canonical_sample(line, purpose)
    except CanonicalSampleError:
        return text
    if sample is None:
        return text
    return "\n".join(sample.semantic_texts)


def _signature_bytes(signature: int) -> bytes:
    return signature.to_bytes(8, "big")


def _band_bucket(signature: int, band: int, *, band_bits: int = BAND_BITS) -> int:
    return (signature >> (band * band_bits)) & ((1 << band_bits) - 1)


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


def _release_candidate_query(limit: int) -> str:
    predicates = " OR ".join(
        "(band.band = ? AND band.bucket = ?)" for _ in range(RELEASE_NEAR_DUP_BAND_COUNT)
    )
    return f"""
        SELECT DISTINCT candidate.signature, candidate.source_sha256, candidate.source_ordinal
        FROM release_bands AS band
        JOIN release_signatures AS candidate ON candidate.id = band.release_id
        WHERE {predicates}
        ORDER BY candidate.signature, candidate.source_sha256, candidate.source_ordinal
        LIMIT {int(limit)}
    """


def _similarity_bps(distance: int) -> int:
    return ((SIGNATURE_BITS - distance) * 10_000 + SIGNATURE_BITS // 2) // SIGNATURE_BITS


def _method_identifier(hamming_threshold: int, band_count: int, band_bits: int) -> str:
    return (
        f"{SIMHASH_VERSION}-hamming{hamming_threshold}"
        f"-bands{band_count}x{band_bits}-v1"
    )


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


def _near_duplicate_progress(
    stats: _ScanStats,
    potential_pair_count: int,
    within_source_pair_count: int,
    cross_source_pair_count: int,
    overflow_count: int,
) -> dict[str, int]:
    return {
        "release_documents_scanned": stats.document_count,
        "release_documents_indexed": stats.indexed_count,
        "potential_duplicate_pairs": potential_pair_count,
        "within_source_pairs": within_source_pair_count,
        "cross_source_pairs": cross_source_pair_count,
        "candidate_overflow_documents": overflow_count,
    }
