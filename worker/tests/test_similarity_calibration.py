from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from derlem_worker.similarity_calibration import (
    CalibrationSource,
    _file_sha256,
    calibrate_similarity,
    write_calibration_report,
)


def test_calibration_is_deterministic_bounded_and_contains_no_raw_text(tmp_path: Path) -> None:
    first_path = tmp_path / "first.txt"
    second_path = tmp_path / "second.txt"
    first_lines = [
        "Derlem kaliteli Türkçe verileri kaynak bilgisiyle güvenli biçimde toplar ve inceler",
        "Matematik problemleri üçgen alanı açı ölçümü ve geometrik kanıt yöntemlerini açıklar",
        "Deniz taşımacılığı liman planlaması rota maliyeti ve yük güvenliğini birlikte değerlendirir",
        "Yazılım testleri hata durumlarını sınır koşullarını ve beklenen çıktıları düzenli doğrular",
        "Tarih araştırmaları arşiv belgelerini dönem bağlamını ve kaynak güvenilirliğini dikkatle karşılaştırır",
        "Müzik kuramı ritim armoni melodi ve biçim ilişkilerini örneklerle ayrıntılı inceler",
    ]
    second_lines = [
        "Derlem kaliteli Türkçe verileri kaynak bilgisiyle güvenli şekilde toplar ve inceler",
        "Sağlık kayıtları kullanılmadan genel beslenme ilkeleri dengeli öğün planlamasını anlatır",
        "Fizik deneyleri ölçüm belirsizliği enerji korunumu ve hareket yasalarını gözlemle sınar",
        "Tarım planlaması toprak yapısını sulama dönemini ürün seçimini ve iklim riskini değerlendirir",
        "Hukuk metinleri kavram tanımlarını karar gerekçelerini ve norm ilişkilerini sistemli açıklar",
        "Dilbilim çalışmaları sözdizimi anlam yapılarını ses değişimlerini ve kullanım örüntülerini inceler",
    ]
    first_path.write_text("\n".join(first_lines) + "\n", encoding="utf-8")
    second_path.write_text("\n".join(second_lines) + "\n", encoding="utf-8")
    sources = [
        CalibrationSource("source-b", "Second", "b" * 64, second_path),
        CalibrationSource("source-a", "First", "a" * 64, first_path),
    ]
    updates: list[dict[str, int]] = []

    first = calibrate_similarity(
        sources,
        content_purpose="instruction",
        max_document_bytes=4096,
        sample_size=20,
        progress_callback=updates.append,
        progress_interval=2,
    )
    second = calibrate_similarity(
        list(reversed(sources)),
        content_purpose="instruction",
        max_document_bytes=4096,
        sample_size=20,
    )

    assert first == second
    assert first["schema_version"] == "derlem.similarity-calibration.v1"
    assert first["sampling"]["sampled_document_count"] == 12
    assert first["sampling"]["sampled_token_lengths"]["min"] >= 8
    assert sum(
        bucket["document_count"]
        for bucket in first["sampling"]["sampled_token_lengths"]["buckets"]
    ) == 12
    assert first["synthetic_perturbations"]["count"] == 48
    assert sum(
        bucket["count"]
        for bucket in first["synthetic_perturbations"]["by_length_bucket"].values()
    ) == 48
    assert first["corpus_pairs"]["pair_count"] == 66
    assert first["decision"]["status"] == "human_labels_required"
    assert first["active_release_policy"]["policy_id"] == "universal-report-only-h3-4x16-v1"
    assert first["active_release_policy"]["purpose_policy_status"] == "pending_labeled_calibration"
    assert first["thresholds"][3]["release_lsh_complete"] is True
    assert first["thresholds"][4]["release_lsh_complete"] is False
    assert "medium_8_15" in first["thresholds"][3]["synthetic_recall_bps_by_length_bucket"]
    recalls = [row["synthetic_recall_bps"] for row in first["thresholds"]]
    corpus_counts = [row["corpus_pair_count"] for row in first["thresholds"]]
    assert recalls == sorted(recalls)
    assert corpus_counts == sorted(corpus_counts)
    assert updates[-1]["documents_scanned"] == 12
    assert updates[-1]["eligible_documents"] == 12

    serialized = json.dumps(first, ensure_ascii=False)
    assert first_lines[0] not in serialized
    assert second_lines[0] not in serialized
    assert first["corpus_pairs"]["closest_pairs"]
    assert "text" not in first["corpus_pairs"]["closest_pairs"][0]


def test_calibration_report_writes_json_and_markdown_without_raw_text(tmp_path: Path) -> None:
    source_path = tmp_path / "source.txt"
    raw_text = "Bu gizli olmayan test belgesi yeterli sayıda sözcükle kalibrasyonu doğrular"
    source_path.write_text(
        f"{raw_text}\n"
        "Başka bir örnek belge farklı kavramlarla doğal metin dağılımını temsil eder\n",
        encoding="utf-8",
    )
    report = calibrate_similarity(
        [CalibrationSource(None, "Local", "c" * 64, source_path)],
        content_purpose="pretrain",
        max_document_bytes=4096,
        sample_size=2,
    )

    paths = write_calibration_report(report, tmp_path / "reports")

    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert raw_text not in paths["json"].read_text(encoding="utf-8")
    assert raw_text not in paths["markdown"].read_text(encoding="utf-8")
    assert "human_labels_required" in paths["markdown"].read_text(encoding="utf-8")
    assert _file_sha256(source_path) == hashlib.sha256(source_path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        write_calibration_report(report, tmp_path / "reports")


@pytest.mark.parametrize(
    ("purpose", "sample_size", "threshold_max"),
    [
        ("unknown", 2, 3),
        ("instruction", 1, 3),
        ("instruction", 2, 17),
    ],
)
def test_calibration_rejects_invalid_contract_values(
    tmp_path: Path,
    purpose: str,
    sample_size: int,
    threshold_max: int,
) -> None:
    path = tmp_path / "source.txt"
    path.write_text("one two three four five six seven eight\n", encoding="utf-8")
    source = CalibrationSource(None, "Local", "d" * 64, path)

    with pytest.raises(ValueError):
        calibrate_similarity(
            [source],
            content_purpose=purpose,
            max_document_bytes=4096,
            sample_size=sample_size,
            threshold_max=threshold_max,
        )
