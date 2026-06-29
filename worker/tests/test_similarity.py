from __future__ import annotations

from pathlib import Path

from derlem_worker.similarity import (
    approximate_decontamination,
    document_simhash,
    hamming_distance,
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


def test_hamming_distance_counts_changed_bits() -> None:
    assert hamming_distance(0b1010, 0b0011) == 2
