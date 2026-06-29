from __future__ import annotations

import hashlib
import json
from pathlib import Path

from derlem_worker.fingerprints import normalize_document_text
from derlem_worker.similarity import (
    _similarity_text_from_line,
    approximate_decontamination,
    document_simhash,
    hamming_distance,
    release_near_duplicates,
)


def test_simhash_is_deterministic_after_text_normalization() -> None:
    first = document_simhash(
        "Derlem temiz Türkçe veriyi güvenli biçimde toplar ve sürümler halinde yayımlar."
    )
    second = document_simhash(
        "  DERLEM   temiz Türkçe veriyi güvenli biçimde toplar ve sürümler halinde yayımlar.  "
    )

    assert first is not None
    assert first == second


def test_bit_plane_simhash_matches_naive_reference() -> None:
    text = "Derlem release benzerlik raporunu deterministik ve hızlı biçimde üretir"

    assert document_simhash(text) == _naive_simhash(text)


def test_canonical_similarity_uses_semantic_text_not_record_metadata() -> None:
    first = {
        "schema_version": "derlem.canonical-sample.v1",
        "record_type": "conversation",
        "sample_id": "sample-a",
        "content_purpose": "instruction",
        "messages": [{"role": "user", "content": "Derlem semantik ileti metnini karşılaştırma için kullanır"}],
        "metadata": {"batch": "first"},
    }
    second = {
        **first,
        "sample_id": "sample-b",
        "metadata": {"batch": "second"},
    }

    first_text = _similarity_text_from_line(json.dumps(first, ensure_ascii=False))
    second_text = _similarity_text_from_line(json.dumps(second, ensure_ascii=False))

    assert first_text == second_text
    assert first_text == "Derlem semantik ileti metnini karşılaştırma için kullanır"


def test_simhash_rejects_documents_with_too_few_tokens() -> None:
    assert document_simhash("çok kısa bir metin") is None


def test_approximate_decontamination_reports_near_match_without_raw_text(tmp_path: Path) -> None:
    reference = tmp_path / "eval.txt"
    release = tmp_path / "pretrain.txt"
    reference.write_text(
        "Derlem kaliteli Türkçe veriyi kaynak bilgisi ile toplar temizler inceler onaylar ve sürümler halinde yayımlar.\n",
        encoding="utf-8",
    )
    release.write_text(
        "Derlem kaliteli Türkçe veriyi kaynak bilgisi ile toplar temizler dikkatle inceler onaylar ve sürümler halinde yayımlar.\n"
        "Bambaşka konudaki bu belge deniz taşımacılığı liman tarifeleri ve lojistik planlama süreçlerini açıklar.\n",
        encoding="utf-8",
    )

    result = approximate_decontamination(
        [("e" * 64, reference)],
        [("p" * 64, release)],
        max_document_bytes=4096,
    )

    assert result.status == "reported"
    assert result.reference_document_count == 1
    assert result.release_document_count == 2
    assert result.potential_match_count == 1
    assert result.candidate_overflow_document_count == 0
    assert len(result.sample_matches) == 1
    match = result.sample_matches[0]
    assert match.release_source_ordinal == 1
    assert match.reference_source_ordinal == 1
    assert match.hamming_distance <= result.hamming_threshold
    assert 0 < match.similarity_estimate_bps <= 10_000
    assert "text" not in result.to_dict()["sample_matches"][0]


def test_unrelated_documents_do_not_match(tmp_path: Path) -> None:
    reference = tmp_path / "eval.txt"
    release = tmp_path / "pretrain.txt"
    reference.write_text(
        "Matematik sorusu bir üçgenin kenar uzunlukları ve alan hesabı üzerine ayrıntılı bilgi verir.\n",
        encoding="utf-8",
    )
    release.write_text(
        "Mutfakta sebzeler yıkanır doğranır tencereye alınır ve düşük ateşte yavaşça pişirilir.\n",
        encoding="utf-8",
    )

    result = approximate_decontamination(
        [("e" * 64, reference)],
        [("p" * 64, release)],
        max_document_bytes=4096,
    )

    assert result.potential_match_count == 0


def test_candidate_overflow_is_inconclusive(monkeypatch, tmp_path: Path) -> None:
    reference = tmp_path / "eval.txt"
    release = tmp_path / "pretrain.txt"
    reference.write_text("referans bir iki üç dört beş\nreferans altı yedi sekiz dokuz on\n", encoding="utf-8")
    release.write_text("aday bir iki üç dört beş\n", encoding="utf-8")
    signatures = {
        "referans bir iki üç dört beş": 0,
        "referans altı yedi sekiz dokuz on": 1 << 8,
        "aday bir iki üç dört beş": 1,
    }
    monkeypatch.setattr(
        "derlem_worker.similarity.document_simhash",
        lambda text: signatures[text],
    )

    result = approximate_decontamination(
        [("e" * 64, reference)],
        [("p" * 64, release)],
        max_document_bytes=4096,
        max_candidates_per_document=1,
    )

    assert result.status == "inconclusive"
    assert result.candidate_overflow_document_count == 1


def test_progress_callback_reports_final_counts(tmp_path: Path) -> None:
    reference = tmp_path / "eval.txt"
    release = tmp_path / "pretrain.txt"
    reference.write_text("one two three four five six seven\n", encoding="utf-8")
    release.write_text("one two three four five six seven\n", encoding="utf-8")
    updates: list[dict[str, int]] = []

    approximate_decontamination(
        [("e" * 64, reference)],
        [("p" * 64, release)],
        max_document_bytes=4096,
        progress_callback=updates.append,
        progress_interval=1,
    )

    assert updates
    assert updates[-1]["reference_documents_scanned"] == 1
    assert updates[-1]["reference_documents_indexed"] == 1
    assert updates[-1]["release_documents_scanned"] == 1
    assert updates[-1]["release_documents_indexed"] == 1
    assert updates[-1]["potential_matches"] == 1
    assert updates[-1]["candidate_overflow_documents"] == 0


def test_release_near_duplicates_counts_within_and_cross_source_pairs(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    duplicate = "Derlem kaliteli Türkçe veriyi güvenli biçimde toplar inceler onaylar ve yayımlar."
    first.write_text(f"{duplicate}\n{duplicate}\n", encoding="utf-8")
    second.write_text(
        f"{duplicate}\nBu belge farklı bir konuyu ve deniz taşımacılığı planlarını ayrıntılı anlatır.\n",
        encoding="utf-8",
    )

    result = release_near_duplicates(
        [("b" * 64, second), ("a" * 64, first)],
        max_document_bytes=4096,
    )

    assert result.schema_version == "derlem.release-near-dedup-report.v1"
    assert result.status == "reported"
    assert result.method == "normalized-word-3gram-simhash64-v1-hamming3-bands4x16-v1"
    assert result.source_count == 2
    assert result.document_count == 4
    assert result.indexed_document_count == 4
    assert result.potential_pair_count == 3
    assert result.within_source_pair_count == 1
    assert result.cross_source_pair_count == 2
    assert result.candidate_overflow_document_count == 0
    assert len(result.sample_pairs) == 3
    assert {pair.relation for pair in result.sample_pairs} == {"within_source", "cross_source"}
    assert all(pair.hamming_distance == 0 for pair in result.sample_pairs)
    assert "text" not in result.to_dict()["sample_pairs"][0]


def test_release_near_duplicate_overflow_is_inconclusive(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text(
        "first document has enough words for indexing now\n"
        "second document has enough words for indexing now\n"
        "third document has enough words for indexing now\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("derlem_worker.similarity.document_simhash", lambda _text: 0)

    result = release_near_duplicates(
        [("a" * 64, source)],
        max_document_bytes=4096,
        max_candidates_per_document=1,
    )

    assert result.status == "inconclusive"
    assert result.candidate_overflow_document_count == 1


def test_release_near_duplicate_progress_reports_final_counts(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    line = "one two three four five six seven"
    source.write_text(f"{line}\n{line}\n", encoding="utf-8")
    updates: list[dict[str, int]] = []

    release_near_duplicates(
        [("a" * 64, source)],
        max_document_bytes=4096,
        progress_callback=updates.append,
        progress_interval=1,
    )

    assert updates
    assert updates[-1] == {
        "release_documents_scanned": 2,
        "release_documents_indexed": 2,
        "potential_duplicate_pairs": 1,
        "within_source_pairs": 1,
        "cross_source_pairs": 0,
        "candidate_overflow_documents": 0,
    }


def test_hamming_distance_counts_changed_bits() -> None:
    assert hamming_distance(0b1010, 0b0011) == 2


def _naive_simhash(text: str) -> int | None:
    tokens = normalize_document_text(text).split()
    if len(tokens) < 5:
        return None
    weights = [0] * 64
    for index in range(len(tokens) - 2):
        shingle = "\x1f".join(tokens[index : index + 3]).encode("utf-8")
        digest = int.from_bytes(
            hashlib.blake2b(shingle, digest_size=8, person=b"DerlemSH").digest(),
            "big",
        )
        for bit in range(64):
            weights[bit] += 1 if digest & (1 << bit) else -1
    signature = 0
    for bit, weight in enumerate(weights):
        if weight > 0:
            signature |= 1 << bit
    return signature
