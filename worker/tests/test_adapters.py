"""Kaynak uyarlayicilari: yaml sozlesmesi, dogrulama, uc kaynak bicimi (TASK-044)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from derlem_worker.adapters import (
    AdapterError,
    CanonicalRecord,
    adapt_file,
    adapt_files,
    line_source_documents,
    load_adapter,
    new_report,
    parse_adapter,
)
from derlem_worker.document_record import read_documents, validate_document, write_document_shards


REPO = Path(__file__).resolve().parents[2]
ADAPTERS = REPO / "adapters"
FINEWEB_COLUMNS = [
    "text", "id", "date", "dump", "embeddings", "file_path", "language", "language_score",
    "language_script", "minhash_cluster_size", "top_langs", "url", "quality_score",
]


def _fineweb_rows(count: int) -> list[dict]:
    rows = []
    for index in range(count):
        rows.append({
            "text": f"Başlık {index}\n\nBirinci paragraf.\nİkinci satır.\n\nSon paragraf {index}.",
            "id": f"<urn:uuid:{index:08d}>",
            "date": "2017-11-20T19:13:53Z",
            "dump": "CC-MAIN-2017-47",
            "embeddings": [[0.25] * 8],
            "file_path": f"s3://commoncrawl/crawl-data/CC-MAIN-2017-47/{index}.warc.gz",
            "language": "tur",
            "language_score": 0.99,
            "language_script": "Latn",
            "minhash_cluster_size": 4,
            "top_langs": '{"tur_Latn_score": 0.99}',
            "url": f"http://ornek.example/{index}",
            "quality_score": 0.03 + index / 100,
        })
    return rows


def _write_fineweb_parquet(path: Path, rows: list[dict], *, drop: tuple[str, ...] = (), add: dict | None = None) -> None:
    columns = [column for column in FINEWEB_COLUMNS if column not in drop]
    data = {column: [row[column] for row in rows] for column in columns}
    if add:
        data.update(add)
    table = pa.table(data)
    pq.write_table(table, path, row_group_size=3)


def test_repository_adapters_load_and_pass_static_validation() -> None:
    names = sorted(path.name for path in ADAPTERS.glob("*.yaml"))
    assert names == ["derlem-canonical-sample.yaml", "epfml-fineweb2-hq.yaml", "faz2-raw-jsonl.yaml"]
    for path in ADAPTERS.glob("*.yaml"):
        adapter = load_adapter(path)
        assert adapter.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        assert adapter.document_boundary == "record"


def test_fineweb2_row_groups_land_as_documents_with_metadata_and_paragraphs(tmp_path: Path) -> None:
    adapter = load_adapter(ADAPTERS / "epfml-fineweb2-hq.yaml")
    rows = _fineweb_rows(7)
    source = tmp_path / "000_00000.parquet"
    _write_fineweb_parquet(source, rows)
    report = new_report(adapter)

    documents = list(adapt_file(adapter, source, report=report, file_label="tur_Latn/000_00000.parquet"))

    assert report.ok and report.documents == 7 and report.records_seen == 7
    assert report.skipped_columns == ["embeddings"] and report.unlisted_columns == []
    first = documents[0]
    validate_document(first)
    assert first["text"] == rows[0]["text"]
    assert first["text"].count("\n") == rows[0]["text"].count("\n") == 5
    assert first["provenance"] == {
        "dataset": "epfml/FineWeb2-HQ",
        "revision": "c0c06e94fd3a44ae9e802b2b0fc533817601eb5e",
        "file": "tur_Latn/000_00000.parquet",
        "row": 0,
        "external_id": "<urn:uuid:00000000>",
        "url": "http://ornek.example/0",
        "crawl_date": "2017-11-20T19:13:53Z",
        "dump": "CC-MAIN-2017-47",
    }
    assert first["language"] == {"declared": "tur", "detected": None, "score": 0.99}
    assert first["signals"] == {"fineweb2-hq-xlmr-mlp": 0.03, "minhash_cluster_size": 4.0}
    assert json.loads(first["extra"]) == {
        "file_path": rows[0]["file_path"], "language_script": "Latn", "top_langs": '{"tur_Latn_score": 0.99}',
    }
    assert "embeddings" not in first["extra"]
    assert [document["source_ordinal"] for document in documents] == list(range(1, 8))
    assert [document["provenance"]["row"] for document in documents] == list(range(7))
    # Belge kaydi parcaya ve geri: hicbir alan kaybolmaz.
    [shard] = write_document_shards(documents, tmp_path / "shards")
    assert list(read_documents(Path(shard.path))) == documents


def test_missing_mapped_column_refuses_the_import_before_reading(tmp_path: Path) -> None:
    adapter = load_adapter(ADAPTERS / "epfml-fineweb2-hq.yaml")
    source = tmp_path / "eksik.parquet"
    _write_fineweb_parquet(source, _fineweb_rows(2), drop=("url",))
    report = new_report(adapter)

    with pytest.raises(AdapterError, match=r"missing from source: \['url'\]"):
        adapt_file(adapter, source, report=report)
    assert report.records_seen == 0


def test_empty_text_is_counted_and_reported_never_silently_dropped(tmp_path: Path) -> None:
    adapter = load_adapter(ADAPTERS / "epfml-fineweb2-hq.yaml")
    rows = _fineweb_rows(6)
    rows[1]["text"] = ""
    rows[3]["text"] = "   \n "
    rows[4]["text"] = None
    source = tmp_path / "bos.parquet"
    _write_fineweb_parquet(source, rows)
    report = new_report(adapter)

    documents = list(adapt_file(adapter, source, report=report))

    assert [document["source_ordinal"] for document in documents] == [1, 3, 6]
    assert report.empty_text == 3 and report.empty_text_ordinals == [2, 4, 5]
    assert report.records_seen == report.documents + report.empty_text + report.invalid_records == 6
    assert report.to_dict()["empty_text_ordinals"] == [2, 4, 5]


def test_unknown_column_goes_to_extra_and_is_listed(tmp_path: Path) -> None:
    adapter = load_adapter(ADAPTERS / "epfml-fineweb2-hq.yaml")
    rows = _fineweb_rows(2)
    source = tmp_path / "yeni-sutun.parquet"
    _write_fineweb_parquet(source, rows, add={"yeni_sutun": ["a", None]})
    report = new_report(adapter)

    documents = list(adapt_file(adapter, source, report=report))

    assert report.unlisted_columns == ["yeni_sutun"]
    assert json.loads(documents[0]["extra"])["yeni_sutun"] == "a"
    assert json.loads(documents[1]["extra"])["yeni_sutun"] is None


def test_faz2_raw_jsonl_keeps_the_source_label_and_counts_blank_lines(tmp_path: Path) -> None:
    adapter = load_adapter(ADAPTERS / "faz2-raw-jsonl.yaml")
    first = tmp_path / "ttk_corpus.jsonl"
    second = tmp_path / "tdk_corpus.jsonl"
    first.write_text(
        json.dumps({"text": "Bir paragraf.", "source": "ttk_belleten"}, ensure_ascii=False) + "\n"
        + "\n"
        + json.dumps({"text": "", "source": "ttk_belleten"}) + "\n"
        + json.dumps({"text": "Ek alanlı kayıt.", "source": "ttk", "sayfa": 7}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    second.write_text(json.dumps({"text": "kalem: yazı aracı", "source": "tdk"}, ensure_ascii=False) + "\n", encoding="utf-8")
    report = new_report(adapter)

    documents = list(adapt_files(adapter, [first, second], report=report))

    assert [document["text"] for document in documents] == ["Bir paragraf.", "Ek alanlı kayıt.", "kalem: yazı aracı"]
    assert [document["source_ordinal"] for document in documents] == [1, 3, 4]
    assert [document["provenance"]["file"] for document in documents] == ["ttk_corpus.jsonl"] * 2 + ["tdk_corpus.jsonl"]
    assert [document["provenance"]["row"] for document in documents] == [0, 3, 0]
    assert json.loads(documents[0]["extra"]) == {"source": "ttk_belleten"}
    assert json.loads(documents[1]["extra"]) == {"sayfa": 7, "source": "ttk"}
    assert documents[0]["language"]["declared"] == "tr"
    assert report.blank_lines == 1 and report.empty_text_ordinals == [2]
    assert report.unlisted_columns == ["sayfa"]


def test_jsonl_record_without_a_mapped_column_stops_the_import(tmp_path: Path) -> None:
    adapter = load_adapter(ADAPTERS / "faz2-raw-jsonl.yaml")
    source = tmp_path / "eksik.jsonl"
    source.write_text('{"text": "a", "source": "x"}\n{"text": "b"}\n', encoding="utf-8")
    report = new_report(adapter)
    with pytest.raises(AdapterError, match=r"lacks mapped column\(s\) \['source'\]"):
        list(adapt_file(adapter, source, report=report))


def _mevzuat_adapter(**overrides):
    value = {
        "dataset": "muhammetakkurt/mevzuat-gov-dataset",
        "revision": "0123456789abcdef0123456789abcdef01234567",
        "format": "tsv",
        "document_boundary": "record",
        "columns_read": ["metin", "kanun_no", "tur", "resmi_gazete_tarihi", "url"],
        "map": {"text": "metin", "provenance.external_id": "kanun_no", "provenance.url": "url"},
        "constants": {"language.declared": "tr", "rights.license_id": "kamu-mevzuati"},
        "extra": ["tur", "resmi_gazete_tarihi"],
    }
    value.update(overrides)
    return parse_adapter(value, name="mevzuat-test", sha256="0" * 64)


def test_tsv_and_jsonl_mevzuat_records_land_through_the_same_contract(tmp_path: Path) -> None:
    tsv = tmp_path / "mevzuat.tsv"
    tsv.write_text(
        "metin\tkanun_no\ttur\tresmi_gazete_tarihi\turl\n"
        "Madde 1 - Bu Kanunun amacı...\t5237\tKanun\t2004-10-12\thttps://mevzuat.gov.tr/5237\n"
        "\t5238\tKanun\t\t\n",
        encoding="utf-8",
    )
    adapter = _mevzuat_adapter()
    report = new_report(adapter)
    documents = list(adapt_file(adapter, tsv, report=report))
    assert len(documents) == 1 and report.empty_text == 1
    assert documents[0]["provenance"]["external_id"] == "5237"
    assert documents[0]["rights"]["license_id"] == "kamu-mevzuati"
    assert json.loads(documents[0]["extra"]) == {"resmi_gazete_tarihi": "2004-10-12", "tur": "Kanun"}

    jsonl = tmp_path / "mevzuat.jsonl"
    jsonl.write_text(json.dumps({
        "metin": "Madde 1 - Bu Kanunun amacı...", "kanun_no": 5237, "tur": "Kanun",
        "resmi_gazete_tarihi": "2004-10-12", "url": "https://mevzuat.gov.tr/5237",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    jsonl_adapter = _mevzuat_adapter(format="jsonl")
    [from_jsonl] = list(adapt_file(jsonl_adapter, jsonl, report=new_report(jsonl_adapter)))
    assert from_jsonl["doc_id"] == documents[0]["doc_id"]
    assert from_jsonl["provenance"]["external_id"] == "5237"

    bad_header = tmp_path / "eksik.tsv"
    bad_header.write_text("metin\tkanun_no\ttur\turl\nx\t1\tKanun\tu\n", encoding="utf-8")
    with pytest.raises(AdapterError, match="resmi_gazete_tarihi"):
        adapt_file(adapter, bad_header, report=new_report(adapter))


def test_invalid_values_are_counted_as_invalid_records(tmp_path: Path) -> None:
    adapter = load_adapter(ADAPTERS / "epfml-fineweb2-hq.yaml")
    rows = _fineweb_rows(3)
    source = tmp_path / "tip.parquet"
    data = {column: [row[column] for row in rows] for column in FINEWEB_COLUMNS}
    data["quality_score"] = ["0.1", "yuksek", None]
    pq.write_table(pa.table(data), source)
    report = new_report(adapter)

    documents = list(adapt_file(adapter, source, report=report))

    assert [document["source_ordinal"] for document in documents] == [1, 3]
    assert documents[0]["signals"]["fineweb2-hq-xlmr-mlp"] == 0.1
    assert "fineweb2-hq-xlmr-mlp" not in documents[1]["signals"]
    assert report.missing_signal_values == {"fineweb2-hq-xlmr-mlp": 1}
    assert report.invalid_records == 1 and report.invalid_samples[0]["source_ordinal"] == 2
    assert not report.ok


def test_canonical_instruction_samples_pass_through_unchanged(tmp_path: Path) -> None:
    adapter = load_adapter(ADAPTERS / "derlem-canonical-sample.yaml")
    sample_file = REPO / "data_samples" / "example_canonical_conversations.jsonl"
    original = sample_file.read_text(encoding="utf-8").splitlines()
    source = tmp_path / "talimat.jsonl"
    unknown_field = json.loads(original[0])
    unknown_field["model_name"] = "x"
    source.write_text(
        "\n".join([*original, json.dumps(unknown_field, ensure_ascii=False), '{"text": "duz metin"}']) + "\n",
        encoding="utf-8",
    )
    report = new_report(adapter)

    records = list(adapt_file(adapter, source, report=report))

    assert [record.line for record in records] == original
    assert all(isinstance(record, CanonicalRecord) for record in records)
    assert records[0].sample_id == "conversation-001" and records[0].record_type == "conversation"
    assert report.invalid_records == 2
    assert [sample["error"].split(":")[0] for sample in report.invalid_samples] == [
        "invalid_canonical_sample", "not_canonical_sample",
    ]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"map": {"provenance.url": "url"}}, "text must be mapped"),
        ({"columns_read": ["text"]}, "missing from columns_read"),
        ({"columns_skipped": ["text"]}, "both read and skipped"),
        ({"columns_read": ["text", "url", "fazla"], "map": {"text": "text", "provenance.url": "url"}, "extra": []},
         "neither mapped nor extra"),
        ({"map": {"text": "text", "provenance.row": "url"}}, "filled by the importer"),
        ({"map": {"text": "text", "baska.alan": "url"}}, "unknown map target"),
        ({"document_boundary": "paragraph"}, "document_boundary"),
        ({"format": "csv"}, "format"),
        ({"bilinmeyen": 1}, "unknown keys"),
        ({"revision": 12345}, "revision"),
        ({"extra": ["url"]}, "both mapped and extra"),
        ({"constants": {"provenance.url": "x"}}, "both mapped and constant"),
    ],
)
def test_adapter_static_validation(change: dict, message: str) -> None:
    value = {
        "dataset": "d",
        "revision": "r",
        "format": "jsonl",
        "document_boundary": "record",
        "columns_read": ["text", "url"],
        "map": {"text": "text", "provenance.url": "url"},
    }
    value.update(change)
    with pytest.raises(AdapterError, match=message):
        parse_adapter(value, name="test", sha256="0" * 64)


def test_line_source_backfill_keeps_line_bytes_and_ordinals(tmp_path: Path) -> None:
    source = tmp_path / "faz2.txt"
    lines = ["Birinci belge  ", "", "x" * 300, "  üçüncü belge"]
    source.write_bytes(("\n".join(lines) + "\r\n").encode("utf-8"))
    adapter_report = new_report(load_adapter(ADAPTERS / "faz2-raw-jsonl.yaml"))

    documents = list(line_source_documents(
        source, report=adapter_report, max_document_bytes=256, source_id="06ac330e",
        dataset="gardash_faz2_tr_dedup_20260621", revision="9826d58e", file_label="objects/sha256/98/26/9826d58e",
        language_declared="tr",
    ))

    assert [document["text"] for document in documents] == ["Birinci belge  ", "  üçüncü belge"]
    assert [document["source_ordinal"] for document in documents] == [1, 4]
    assert documents[0]["doc_id"] == hashlib.sha256("Birinci belge  ".encode("utf-8")).hexdigest()
    assert documents[1]["provenance"]["row"] == 3 and documents[1]["provenance"]["url"] is None
    assert adapter_report.empty_text_ordinals == [2] and adapter_report.oversized_ordinals == [3]
    assert adapter_report.records_seen == 4
    for document in documents:
        validate_document(document)
