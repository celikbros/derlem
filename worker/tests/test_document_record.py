"""derlem.document.v1 / derlem.decision.v1 / derlem.selection.v1 ve Parquet parcalari (TASK-044)."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from derlem_worker import document_record
from derlem_worker.document_record import (
    DECISION_SCHEMA,
    DOCUMENT_SCHEMA,
    DOCUMENT_SCHEMA_VERSION,
    SELECTION_SCHEMA,
    SHARD_CREATED_BY,
    DocumentRecordError,
    DocumentShardWriter,
    ParquetRowWriter,
    document_id,
    make_decision,
    make_document,
    parquet_created_by,
    publish_parquet,
    read_decisions,
    read_documents,
    read_selection,
    validate_decision,
    write_document_shards,
)
from derlem_worker.storage import ContentAddressedStore


WORKER_SRC = Path(__file__).resolve().parents[1] / "src"


def _documents(count: int, *, start: int = 1) -> list[dict]:
    records = []
    for ordinal in range(start, start + count):
        records.append(
            make_document(
                text=f"Belge {ordinal}: ilk paragraf.\n\nİkinci paragraf — ğüşıöç ve 🙂.",
                source_ordinal=ordinal,
                source_id=None,
                provenance={
                    "dataset": "epfml/FineWeb2-HQ",
                    "revision": "c0c06e94",
                    "file": "tur_Latn/000_00000.parquet",
                    "row": ordinal - start,
                    "external_id": f"<urn:uuid:{ordinal}>",
                    "url": f"https://ornek.example/{ordinal}",
                    "crawl_date": "2017-11-20T19:13:53Z",
                    "dump": "CC-MAIN-2017-47",
                },
                language={"declared": "tur", "score": 0.99},
                signals={"fineweb2-hq-xlmr-mlp": ordinal / 1000, "minhash_cluster_size": 4},
                rights={"license_id": "odc-by-1.0", "evidence_ref": "docs/haklar/hf-fineweb2-hq.md", "scope": "non_commercial"},
                extra={"file_path": "s3://commoncrawl/x.warc.gz", "top_langs": '{"tur_Latn_score": 0.99}'},
            )
        )
    return records


def test_document_round_trip_keeps_every_field_and_paragraph_breaks(tmp_path: Path) -> None:
    records = _documents(5)
    sparse = make_document(text="  kenar boşlukları korunur  \n", source_ordinal=9)
    [info] = write_document_shards([*records, sparse], tmp_path / "out")

    back = list(read_documents(Path(info.path)))

    assert back == [*records, sparse]
    assert back[0]["text"].count("\n") == 2
    assert back[-1]["text"] == "  kenar boşlukları korunur  \n"
    assert back[-1]["provenance"] == {key: None for key in document_record.PROVENANCE_FIELDS}
    assert back[-1]["signals"] == {} and back[-1]["extra"] is None
    assert info.row_count == 6 and (info.first_source_ordinal, info.last_source_ordinal) == (1, 9)
    schema = pq.read_schema(info.path)
    assert schema.names == DOCUMENT_SCHEMA.names
    assert schema.metadata[b"derlem.schema"] == DOCUMENT_SCHEMA_VERSION.encode("ascii")
    # Parquet harita girdisinin ic adini kendisi koyar; tip ve alanlar aynidir.
    for field in DOCUMENT_SCHEMA:
        if field.name != "signals":
            assert schema.field(field.name).equals(field)


def test_doc_id_is_sha256_of_raw_text_bytes() -> None:
    text = "Ham metin\r\n  "
    assert document_id(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    with pytest.raises(DocumentRecordError, match="doc_id"):
        document_record.validate_document({**make_document(text="a", source_ordinal=1), "doc_id": "0" * 64})


def test_empty_text_is_not_a_document() -> None:
    for text in ("", "   \n\t"):
        with pytest.raises(DocumentRecordError, match="empty"):
            make_document(text=text, source_ordinal=1)


def test_document_validation_rejects_shape_errors() -> None:
    good = make_document(text="metin", source_ordinal=1)
    cases = [
        {**good, "source_ordinal": 0},
        {**good, "provenance": {**good["provenance"], "bilinmeyen": 1}},
        {**good, "signals": {"puan": float("nan")}},
        {**good, "signals": {"puan": True}},
        {**good, "extra": "[1, 2]"},
        {**good, "extra": "{bozuk"},
        {**good, "unknown": 1},
    ]
    for record in cases:
        with pytest.raises(DocumentRecordError):
            document_record.validate_document(record)


def test_decision_and_selection_round_trip(tmp_path: Path) -> None:
    decided_at = datetime(2026, 10, 13, 12, 0, 0, 123456, tzinfo=UTC)
    decisions = [
        make_decision(doc_id="a" * 64, decision_type="pii", verdict="reject", judge="pii-v1",
                      run_id="run-1", decided_at=decided_at, reason="email", source_ordinal=3),
        make_decision(doc_id="b" * 64, decision_type="jury", verdict="flag", judge="sonnet+siki-v1",
                      run_id="run-1", decided_at=decided_at),
    ]
    writer = ParquetRowWriter(tmp_path / "d.parquet", DECISION_SCHEMA, validator=validate_decision)
    for row in decisions:
        writer.add(row)
    info = writer.close()
    assert list(read_decisions(Path(info.path))) == decisions

    selection = ParquetRowWriter(tmp_path / "s.parquet", SELECTION_SCHEMA)
    selection.add({"source_ordinal": 1, "doc_id": "c" * 64, "partition": "train"})
    selection_info = selection.close()
    assert list(read_selection(Path(selection_info.path))) == [
        {"source_ordinal": 1, "doc_id": "c" * 64, "partition": "train"}
    ]
    # Bir dosya baska bir sema olarak okunamaz.
    with pytest.raises(DocumentRecordError, match=DOCUMENT_SCHEMA_VERSION):
        list(read_documents(Path(info.path)))


def test_decision_validation_rejects_unknown_type_and_verdict() -> None:
    base = dict(doc_id="a" * 64, decision_type="pii", verdict="reject", judge="j", run_id="r",
                decided_at=datetime(2026, 1, 1, tzinfo=UTC))
    make_decision(**base)
    for change in ({"decision_type": "keyfi"}, {"verdict": "belki"}, {"doc_id": "A" * 64},
                   {"decided_at": datetime(2026, 1, 1)}):
        with pytest.raises(DocumentRecordError):
            make_decision(**{**base, **change})


def test_shard_writer_splits_by_count_and_cuts_on_request(tmp_path: Path) -> None:
    records = _documents(25)
    with DocumentShardWriter(tmp_path / "out", rows_per_shard=10, row_group_size=4) as writer:
        for record in records[:12]:
            writer.add(record)
        writer.cut()  # kaynak dosya siniri
        for record in records[12:]:
            writer.add(record)
    shards = writer.close()

    assert [shard.row_count for shard in shards] == [10, 2, 10, 3]
    assert [Path(shard.path).name for shard in shards] == [f"part-{index:05d}.parquet" for index in range(4)]
    assert [shard.row_groups for shard in shards] == [3, 1, 3, 1]
    assert [row["source_ordinal"] for shard in shards for row in read_documents(Path(shard.path))] == list(range(1, 26))


def test_shard_writer_refuses_non_increasing_ordinals_and_leaves_no_partial_file(tmp_path: Path) -> None:
    first, second = _documents(2)
    out = tmp_path / "out"
    with pytest.raises(DocumentRecordError, match="increase"):
        with DocumentShardWriter(out) as writer:
            writer.add(second)
            writer.add(first)
    assert list(out.iterdir()) == []


def test_reader_projects_columns(tmp_path: Path) -> None:
    [info] = write_document_shards(_documents(3), tmp_path / "out")
    rows = list(read_documents(Path(info.path), columns=["doc_id", "signals"]))
    assert set(rows[0]) == {"doc_id", "signals"}
    assert rows[2]["signals"] == {"fineweb2-hq-xlmr-mlp": 0.003, "minhash_cluster_size": 4.0}
    with pytest.raises(DocumentRecordError, match="unknown columns"):
        list(read_documents(Path(info.path), columns=["yok"]))


_DETERMINISM_SCRIPT = """
import json, sys
from pathlib import Path
from derlem_worker.document_record import write_document_shards
records = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
shards = write_document_shards(records, Path(sys.argv[2]), rows_per_shard=40, row_group_size=16)
print(json.dumps([shard.sha256 for shard in shards]))
"""


def test_shard_bytes_are_identical_across_separate_processes(tmp_path: Path) -> None:
    records = _documents(100)
    fixture = tmp_path / "records.json"
    fixture.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(WORKER_SRC), "PYTHONIOENCODING": "utf-8"}
    runs = []
    for name in ("run-a", "run-b"):
        completed = subprocess.run(
            [sys.executable, "-c", _DETERMINISM_SCRIPT, str(fixture), str(tmp_path / name)],
            check=True, capture_output=True, text=True, env=env,
        )
        runs.append(json.loads(completed.stdout))
    in_process = [shard.sha256 for shard in write_document_shards(records, tmp_path / "run-c", rows_per_shard=40, row_group_size=16)]

    assert len(runs[0]) == 3
    assert runs[0] == runs[1] == in_process
    for name in ("run-a", "run-b", "run-c"):
        for path in sorted((tmp_path / name).iterdir()):
            assert hashlib.sha256(path.read_bytes()).hexdigest() in in_process


def test_shard_footer_carries_no_volatile_fields(tmp_path: Path) -> None:
    [info] = write_document_shards(_documents(2), tmp_path / "out")
    metadata = pq.ParquetFile(info.path).metadata
    assert parquet_created_by(Path(info.path)) == SHARD_CREATED_BY
    assert set(metadata.metadata) == {b"ARROW:schema", b"derlem.schema"}
    assert metadata.metadata[b"derlem.schema"] == DOCUMENT_SCHEMA_VERSION.encode("ascii")
    assert metadata.row_group(0).column(0).compression == "ZSTD"


def test_writer_refuses_an_unpinned_pyarrow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pa, "__version__", "0.0.1")
    with pytest.raises(RuntimeError, match="requires pyarrow"):
        write_document_shards(_documents(1), tmp_path / "out")


def test_shard_is_published_as_an_ordinary_content_addressed_object(tmp_path: Path) -> None:
    [info] = write_document_shards(_documents(4), tmp_path / "out")
    store = ContentAddressedStore(tmp_path / "store")

    stored = publish_parquet(store, info)

    object_path = tmp_path / "store" / stored.storage_key
    assert stored.sha256 == info.sha256 == hashlib.sha256(object_path.read_bytes()).hexdigest()
    assert stored.storage_key == f"objects/sha256/{info.sha256[:2]}/{info.sha256[2:4]}/{info.sha256}"
    assert [row["source_ordinal"] for row in read_documents(object_path)] == [1, 2, 3, 4]
    # Ayni parca ikinci kez yayimlanirsa ayni nesne (icerik adresli, degismez).
    assert publish_parquet(store, info).storage_key == stored.storage_key
