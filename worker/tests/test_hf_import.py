"""TASK-032: import_hf_dataset -- ag yok; yerel HTTP sunuculari (hub + ayri CDN) Range destekli.

Sahte hub: /api/datasets/<repo>/tree/<rev>/<onek> (sayfali), /datasets/<repo>/resolve/<rev>/<yol>
(302 -> CDN), /size (datasets-server). CDN: /blob/<yol>, Range -> 206, her araligi kaydeder;
hata enjeksiyonu (429, 500) yapilabilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, unquote, urlsplit

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from derlem_worker import hf_import
from derlem_worker.adapters import AdapterError
from derlem_worker.document_record import read_documents
from derlem_worker.hf_import import HFImportError, HttpClient, import_hf_dataset
from derlem_worker.import_manifest import load_import_manifest, manifest_document_lines
from derlem_worker.pii import PIIScanner
from derlem_worker.sampling import sample_line_documents
from derlem_worker.storage import ContentAddressedStore

REPO = "test-org/fixture-hq"
REV = "0123456789abcdef0123456789abcdef01234567"
CONFIG = "tur_Latn"
EMBED_DIM = 96  # 3 satirlik satir grubunda 2.304 bayt: birlestirme esiginin (4.096) altinda

ADAPTER_YAML = f"""
dataset: {REPO}
revision: "{REV}"
config: {CONFIG}
split: train
format: parquet
target: derlem.document.v1
document_boundary: record
columns_read: [text, id, url, date, dump, language, language_score, quality_score, minhash_cluster_size, file_path]
columns_skipped: [embeddings]
map:
  text: text
  provenance.external_id: id
  provenance.url: url
  provenance.crawl_date: date
  provenance.dump: dump
  language.declared: language
  language.score: language_score
  signals.quality_score: {{value: quality_score, scorer: fineweb2-hq-xlmr-mlp}}
  signals.minhash_cluster_size: minhash_cluster_size
extra: [file_path]
"""

CARD = f"""---
license: odc-by
configs:
- config_name: {CONFIG}
  data_files:
  - split: train
    path: {CONFIG}/*
- config_name: other
  data_files:
  - split: train
    path: other/*
---
# Fixture card
""".encode("utf-8")


def _texts(file_index: int, rows: int) -> list[str]:
    texts = []
    for row in range(rows):
        if (file_index, row) in {(0, 4), (1, 0)}:
            texts.append("   ")  # bos metin: belge olmaz, sayilir
            continue
        paragraphs = [f"Dosya {file_index} satir {row} paragraf {p} — Türkçe metin ğüşıöç." for p in range(row % 3 + 1)]
        texts.append("\n\n".join(paragraphs) + ("\n" if row % 2 else ""))
    return texts


def _fixture_table(file_index: int, rows: int) -> pa.Table:
    texts = _texts(file_index, rows)
    return pa.table({
        "text": texts,
        "id": [f"<urn:uuid:{file_index:04d}-{row:06d}>" for row in range(rows)],
        "dump": ["CC-MAIN-2024-10"] * rows,
        "url": [f"https://ornek{file_index}.com.tr/{row}" for row in range(rows)],
        "date": ["2024-03-01T00:00:00Z"] * rows,
        # Atlanan sutun ortada: once ve sonra okunan sutunlar var (FineWeb2-HQ duzeni).
        "embeddings": [[float(row + d) for d in range(EMBED_DIM)] for row in range(rows)],
        "file_path": [f"s3://cc/{file_index}/{row}.warc.gz" for row in range(rows)],
        "language": ["tur"] * rows,
        "language_score": [0.99] * rows,
        "minhash_cluster_size": [row % 5 + 1 for row in range(rows)],
        "quality_score": [None if row == 2 else 0.01 * row for row in range(rows)],
    })


@dataclass
class ServerState:
    files: dict[str, bytes] = field(default_factory=dict)
    range_log: list[tuple[str, int, int]] = field(default_factory=list)
    hub_log: list[tuple[str, str | None]] = field(default_factory=list)
    cdn_auth: list[str | None] = field(default_factory=list)
    inject: list[int] = field(default_factory=list)  # CDN Range isteklerine sirayla verilecek hata kodlari
    ignore_range: bool = False
    tree_page_size: int = 2
    lock: threading.Lock = field(default_factory=threading.Lock)


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


class _Handler(BaseHTTPRequestHandler):
    state: ServerState
    role: str
    cdn_base: str

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass

    def _send(self, status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        state = self.state
        if self.role == "cdn":
            return self._cdn(path)
        with state.lock:
            state.hub_log.append((self.path, self.headers.get("Authorization")))
        if path == "/size":
            body = json.dumps({"size": {"splits": [{"split": "train", "num_rows": 14, "num_bytes_parquet_files": 1}]}, "partial": False})
            return self._send(200, body.encode(), {"Content-Type": "application/json"})
        tree = re.fullmatch(rf"/api/datasets/{re.escape(REPO)}/tree/([^/]+)(?:/(.*))?", path)
        if tree:
            if tree.group(1) != REV:
                return self._send(404)
            prefix = tree.group(2) or ""
            entries = []
            for name in sorted(state.files):
                if prefix and not name.startswith(prefix + "/"):
                    continue
                data = state.files[name]
                entry = {"type": "file", "path": name, "size": len(data), "oid": _git_blob_sha1(data)}
                if name.endswith(".parquet"):
                    entry["lfs"] = {"oid": hashlib.sha256(data).hexdigest(), "size": len(data), "pointerSize": 135}
                    entry["xetHash"] = hashlib.sha256(b"xet" + data).hexdigest()
                entries.append(entry)
            entries.insert(0, {"type": "directory", "path": prefix or "x", "oid": "0"})
            cursor = int(parse_qs(parts.query).get("cursor", ["0"])[0])
            page = entries[cursor : cursor + state.tree_page_size]
            headers = {"Content-Type": "application/json"}
            if cursor + state.tree_page_size < len(entries):
                nxt = f"{parts.path}?recursive=true&expand=false&cursor={cursor + state.tree_page_size}"
                headers["Link"] = f'<{nxt}>; rel="next"'
            return self._send(200, json.dumps(page).encode(), headers)
        resolve = re.fullmatch(rf"/datasets/{re.escape(REPO)}/resolve/([^/]+)/(.*)", path)
        if resolve:
            if resolve.group(1) != REV:
                return self._send(404)
            name = resolve.group(2)
            if name == "README.md":
                return self._send(200, CARD, {"X-Repo-Commit": REV})
            data = state.files.get(name)
            if data is None:
                return self._send(404)
            headers = {
                "Location": f"{self.cdn_base}/blob/{name}?Expires=99999999999",
                "X-Repo-Commit": REV,
                "X-Linked-Size": str(len(data)),
            }
            if name.endswith(".parquet"):
                headers["X-Linked-ETag"] = f'"{hashlib.sha256(data).hexdigest()}"'
            return self._send(302, b"", headers)
        return self._send(404)

    def _cdn(self, path: str) -> None:
        state = self.state
        name = path.removeprefix("/blob/")
        data = state.files.get(name)
        with state.lock:
            state.cdn_auth.append(self.headers.get("Authorization"))
        if data is None:
            return self._send(404)
        header = self.headers.get("Range")
        if header is None or state.ignore_range:
            return self._send(200, data, {"Accept-Ranges": "bytes"})
        start, end = (int(x) for x in re.fullmatch(r"bytes=(\d+)-(\d+)", header).groups())
        with state.lock:
            if state.inject:
                code = state.inject.pop(0)
                return self._send(code, b"slow down", {"Retry-After": "0"})
            state.range_log.append((name, start, end - start + 1))
        end = min(end, len(data) - 1)
        body = data[start : end + 1]
        return self._send(206, body, {"Content-Range": f"bytes {start}-{end}/{len(data)}", "Accept-Ranges": "bytes"})


@dataclass
class FakeHub:
    state: ServerState
    hub_url: str
    cdn_url: str
    tables: dict[str, pa.Table]


@pytest.fixture
def fake_hub(tmp_path):
    state = ServerState()
    tables: dict[str, pa.Table] = {}
    for index, rows in enumerate((7, 5, 2)):
        table = _fixture_table(index, rows)
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, row_group_size=3, compression="NONE", use_dictionary=False)
        name = f"{CONFIG}/{index:03d}_00000.parquet"
        state.files[name] = sink.getvalue().to_pybytes()
        tables[name] = table
    # Baska config'in dosyasi ve parquet olmayan dosya: secilmemeli.
    other = pa.BufferOutputStream()
    pq.write_table(_fixture_table(9, 2), other)
    state.files["other/000_00000.parquet"] = other.getvalue().to_pybytes()
    state.files[f"{CONFIG}/notes.txt"] = b"not data"

    servers = []
    cdn_handler = type("CdnHandler", (_Handler,), {"state": state, "role": "cdn", "cdn_base": ""})
    cdn = ThreadingHTTPServer(("127.0.0.1", 0), cdn_handler)
    cdn_url = f"http://127.0.0.1:{cdn.server_address[1]}"
    hub_handler = type("HubHandler", (_Handler,), {"state": state, "role": "hub", "cdn_base": cdn_url})
    hub = ThreadingHTTPServer(("127.0.0.1", 0), hub_handler)
    hub_url = f"http://127.0.0.1:{hub.server_address[1]}"
    for server in (cdn, hub):
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        servers.append(server)
    yield FakeHub(state=state, hub_url=hub_url, cdn_url=cdn_url, tables=tables)
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def adapter_path(tmp_path) -> Path:
    path = tmp_path / "fixture-hq.yaml"
    path.write_text(ADAPTER_YAML, encoding="utf-8")
    return path


def _client(**kwargs) -> HttpClient:
    kwargs.setdefault("sleep", lambda seconds: None)
    return HttpClient(hub_endpoint=kwargs.pop("hub"), timeout=10, **kwargs)


def _run(fake_hub, adapter_path, work_dir, **kwargs):
    http = kwargs.pop("http", None) or _client(hub=fake_hub.hub_url)
    return import_hf_dataset(
        adapter_path,
        work_dir,
        hub_endpoint=fake_hub.hub_url,
        datasets_server=fake_hub.hub_url,
        http=http,
        progress_interval_seconds=0,
        **kwargs,
    )


def _skipped_ranges(data: bytes, column: str = "embeddings") -> list[tuple[int, int]]:
    metadata = pq.ParquetFile(pa.BufferReader(data)).metadata
    ranges = []
    for group in range(metadata.num_row_groups):
        meta = metadata.row_group(group)
        for index in range(meta.num_columns):
            chunk = meta.column(index)
            if chunk.path_in_schema.split(".")[0] == column:
                start = chunk.data_page_offset
                if chunk.has_dictionary_page and chunk.dictionary_page_offset:
                    start = min(start, chunk.dictionary_page_offset)
                ranges.append((start, start + chunk.total_compressed_size))
    return ranges


def test_pinned_import_is_deterministic_and_token_stays_on_hub(fake_hub, adapter_path, tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test_secret")
    first = _run(fake_hub, adapter_path, tmp_path / "run-a")
    second = _run(fake_hub, adapter_path, tmp_path / "run-b", connections=3)

    assert [s["sha256"] for s in first.shards] == [s["sha256"] for s in second.shards]
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    assert first.manifest_sha256 == second.manifest_sha256
    manifest = first.manifest
    assert manifest["revision"] == REV
    assert [f["path"] for f in manifest["source_files"]] == [f"{CONFIG}/{i:03d}_00000.parquet" for i in range(3)]
    assert manifest["licence"] == {"id": "odc-by", "card_path": "README.md", "card_sha256": hashlib.sha256(CARD).hexdigest()}
    assert manifest["totals"]["shards"] == 3 and len(first.shards) == 3
    # Her hub istegi sabit surume gider; token hub'a gider, CDN'e asla.
    for path, auth in fake_hub.state.hub_log:
        if path.startswith(("/api/datasets", "/datasets")):
            assert REV in path
        assert auth == "Bearer hf_test_secret"
    assert fake_hub.state.cdn_auth and all(auth is None for auth in fake_hub.state.cdn_auth)
    assert first.cross_check["num_rows"] == 14
    # Manifest bir alim manifesti olarak taninir; ozet lineage_ref tek satir JSON.
    assert load_import_manifest(first.manifest_path)["schema"] == "derlem.import-manifest.v1"
    summary = json.loads(first.lineage_ref("not"))
    assert summary["manifest_sha256"] == first.manifest_sha256 and summary["documents"] == 12


def test_records_keep_metadata_and_paragraph_breaks(fake_hub, adapter_path, tmp_path):
    result = _run(fake_hub, adapter_path, tmp_path / "run")
    documents = []
    for shard in result.shards:
        documents.extend(read_documents(tmp_path / "run" / "shards" / shard["local_name"]))
    expected = []
    for name, table in fake_hub.tables.items():
        for row, item in enumerate(table.to_pylist()):
            expected.append((name, row, item))
    by_key = {(d["provenance"]["file"], d["provenance"]["row"]): d for d in documents}
    kept = [(name, row, item) for name, row, item in expected if item["text"].strip()]
    assert len(documents) == len(kept) == 12
    for name, row, item in kept:
        document = by_key[(name, row)]
        assert document["text"] == item["text"]
        assert document["text"].count("\n") == item["text"].count("\n")
        assert document["provenance"]["url"] == item["url"]
        assert document["provenance"]["crawl_date"] == item["date"]
        assert document["provenance"]["dump"] == item["dump"]
        assert document["provenance"]["external_id"] == item["id"]
        assert document["provenance"]["revision"] == REV
        assert document["language"]["score"] == item["language_score"]
        assert document["signals"]["minhash_cluster_size"] == item["minhash_cluster_size"]
        if item["quality_score"] is not None:
            assert document["signals"]["fineweb2-hq-xlmr-mlp"] == item["quality_score"]
    ordinals = [d["source_ordinal"] for d in documents]
    assert ordinals == sorted(ordinals) and len(set(ordinals)) == len(ordinals)


def test_empty_text_is_counted_not_stored(fake_hub, adapter_path, tmp_path):
    result = _run(fake_hub, adapter_path, tmp_path / "run")
    report = result.manifest["adapter_report"]
    # dosya 0 satir 4 -> sira 5; dosya 1 satir 0 -> sira 8 (dosya 0'da 7 satir)
    assert report["empty_text"] == 2
    assert report["empty_text_ordinals"] == [5, 8]
    assert report["records_seen"] == 14 and report["documents"] == 12
    assert report["missing_signal_values"] == {"fineweb2-hq-xlmr-mlp": 2}
    assert result.manifest["totals"]["records_seen"] == 14


def test_skipped_column_bytes_are_never_requested(fake_hub, adapter_path, tmp_path):
    result = _run(fake_hub, adapter_path, tmp_path / "run", connections=2)
    ledger_lines = (tmp_path / "run" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    entries = {json.loads(line)["path"]: json.loads(line) for line in ledger_lines[1:]}
    assert len(fake_hub.state.range_log) > 0
    for name, data in fake_hub.state.files.items():
        if not name.startswith(CONFIG) or not name.endswith(".parquet"):
            continue
        forbidden = _skipped_ranges(data)
        assert forbidden
        requests = [(start, length) for path, start, length in fake_hub.state.range_log if path == name]
        for start, length in requests:
            for low, high in forbidden:
                assert not (start < high and low < start + length), (name, start, length, low, high)
        downloaded = sum(length for _, length in requests)
        assert entries[name]["bytes_downloaded"] == downloaded
        embeddings = sum(high - low for low, high in forbidden)
        # Indirilen bayt + atlanan bayt dosyadan buyuk olamaz: embeddings indirilmedi.
        assert downloaded + embeddings <= len(data)
        assert entries[name]["column_bytes"]["embeddings"] == embeddings
    totals = result.manifest["totals"]["bytes_by_column_class"]
    assert totals["skipped"] > 0 and totals["text"] > 0 and totals["metadata"] > 0
    # Okunan sutunlar dosya basina iki istek: (text..date) + (file_path..quality_score); altbilgi 2 istek.
    first = f"{CONFIG}/000_00000.parquet"
    assert entries[first]["footer"]["requests"] == 2
    assert entries[first]["requests"] == 2 + 2 * entries[first]["row_groups_read"]


def test_resume_after_failure_at_shard_n_gives_identical_output(fake_hub, adapter_path, tmp_path):
    clean = _run(fake_hub, adapter_path, tmp_path / "clean")

    def fail_after_two(progress):
        if progress["event"] == "file_done" and progress["files_done"] == 2:
            raise RuntimeError("injected failure after shard 2")

    work = tmp_path / "resumed"
    with pytest.raises(RuntimeError, match="injected"):
        _run(fake_hub, adapter_path, work, progress_callback=fail_after_two)
    ledger = (work / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 3  # baslik + iki parca
    fake_hub.state.range_log.clear()
    resumed = _run(fake_hub, adapter_path, work)
    assert resumed.files_skipped_by_resume == 2
    assert {path for path, _, _ in fake_hub.state.range_log} == {f"{CONFIG}/002_00000.parquet"}
    assert [s["sha256"] for s in resumed.shards] == [s["sha256"] for s in clean.shards]
    assert resumed.manifest_path.read_bytes() == clean.manifest_path.read_bytes()


def test_half_read_file_is_restarted_from_scratch(fake_hub, adapter_path, tmp_path):
    clean = _run(fake_hub, adapter_path, tmp_path / "clean")

    def fail_mid_file(progress):
        if progress["event"] == "row_group" and progress.get("file", "").endswith("001_00000.parquet"):
            raise RuntimeError("injected failure mid-file")

    work = tmp_path / "half"
    with pytest.raises(RuntimeError, match="mid-file"):
        _run(fake_hub, adapter_path, work, progress_callback=fail_mid_file)
    leftovers = [p.name for p in (work / "shards").iterdir()]
    assert leftovers == ["shard-00000.parquet"], leftovers  # yarim parca kalmadi
    resumed = _run(fake_hub, adapter_path, work)
    assert resumed.files_skipped_by_resume == 1
    assert resumed.manifest_path.read_bytes() == clean.manifest_path.read_bytes()


def test_resume_refuses_foreign_ledger(fake_hub, adapter_path, tmp_path):
    work = tmp_path / "run"
    _run(fake_hub, adapter_path, work, only_files=[f"{CONFIG}/000_00000.parquet"])
    with pytest.raises(HFImportError, match="different import"):
        _run(fake_hub, adapter_path, work)


def test_store_publish_resume_and_gates_read_the_manifest(fake_hub, adapter_path, tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    work = tmp_path / "run"
    result = _run(fake_hub, adapter_path, work, store=store, keep_local_shards=False)
    assert result.manifest_storage_key is not None
    assert not list((work / "shards").glob("*.parquet"))
    manifest_object = store.root / result.manifest_storage_key
    assert manifest_object.read_bytes() == result.manifest_path.read_bytes()
    again = _run(fake_hub, adapter_path, work, store=store, keep_local_shards=False)
    assert again.files_skipped_by_resume == 3 and again.manifest_sha256 == result.manifest_sha256

    # Kapilarin satir sozlesmesi: manifest nesnesi parcalarin belgeleri olarak okunur.
    manifest = load_import_manifest(manifest_object)
    lines = list(manifest_document_lines(manifest, store.root, 256 * 1024))
    assert len(lines) == 12
    texts = {json.loads(line)["text"] for _, line, _ in lines}
    expected = {t for table in fake_hub.tables.values() for t in table.column("text").to_pylist() if t.strip()}
    assert texts == expected
    report = sample_line_documents(
        manifest_object, sample_size=5, max_document_bytes=256 * 1024, seed=result.manifest_sha256, store_root=store.root
    )
    assert report.total_documents == 12 and len(report.samples) == 5
    assert all(sample.text.strip() in {t.strip() for t in expected} for sample in report.samples)
    assert all(sample.external_id and sample.external_id.startswith("<urn:uuid:") for sample in report.samples)
    pii_progress: list[dict] = []
    pii = PIIScanner().scan_file(manifest_object, language="tr", store_root=store.root, progress_callback=pii_progress.append)
    assert pii_progress[-1]["lines_read"] == 12 and pii.status == "clear"
    # Manifestin kendisi satir olarak taranmaz (store_root yoksa eski yol: JSON satirlari).
    legacy: list[dict] = []
    PIIScanner().scan_file(manifest_object, language="tr", progress_callback=legacy.append)
    assert legacy[-1]["lines_read"] != 12
    # Bozulmus parca okunmaz.
    shard_path = store.root / f"objects/sha256/{result.shards[0]['sha256'][:2]}/{result.shards[0]['sha256'][2:4]}/{result.shards[0]['sha256']}"
    shard_path.chmod(0o644)
    data = bytearray(shard_path.read_bytes())
    data[100] ^= 0xFF
    shard_path.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="does not match"):
        list(manifest_document_lines(manifest, store.root, 256 * 1024))


def test_missing_mapped_column_fails_the_job(fake_hub, tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text(ADAPTER_YAML.replace("[text, id, url,", "[text, id, url, title,").replace("extra: [file_path]", "extra: [file_path, title]"), encoding="utf-8")
    with pytest.raises(AdapterError, match="missing from source"):
        _run(fake_hub, path, tmp_path / "run")
    assert not list((tmp_path / "run" / "shards").glob("*.parquet"))


def test_rate_limit_and_server_errors_are_retried(fake_hub, adapter_path, tmp_path):
    fake_hub.state.inject = [429, 429, 503]
    sleeps: list[float] = []
    http = _client(hub=fake_hub.hub_url, sleep=sleeps.append)
    result = _run(fake_hub, adapter_path, tmp_path / "run", http=http)
    assert http.retries == 3 and len(sleeps) == 3
    assert result.manifest["totals"]["documents"] == 12


def test_retries_are_bounded(fake_hub, adapter_path, tmp_path):
    fake_hub.state.inject = [500] * 50
    http = _client(hub=fake_hub.hub_url, max_attempts=3)
    with pytest.raises(HFImportError, match="after 3 attempts"):
        _run(fake_hub, adapter_path, tmp_path / "run", http=http)


def test_backoff_is_exponential_and_honours_retry_after():
    client = HttpClient(hub_endpoint="https://huggingface.co", backoff_base=1.0, backoff_cap=60.0)
    assert [client._delay(attempt, None) for attempt in range(8)] == [1, 2, 4, 8, 16, 32, 60, 60]
    assert client._delay(0, "7") == 7.0


def test_server_ignoring_range_is_refused(fake_hub, adapter_path, tmp_path):
    fake_hub.state.ignore_range = True
    with pytest.raises(HFImportError, match="ignored the Range"):
        _run(fake_hub, adapter_path, tmp_path / "run")


def test_unpinned_revision_is_refused(fake_hub, tmp_path):
    path = tmp_path / "branch.yaml"
    path.write_text(ADAPTER_YAML.replace(f'revision: "{REV}"', "revision: main"), encoding="utf-8")
    with pytest.raises(HFImportError, match="40-hex commit"):
        _run(fake_hub, path, tmp_path / "run")


def test_dry_run_subset_first_row_group(fake_hub, adapter_path, tmp_path):
    name = f"{CONFIG}/000_00000.parquet"
    result = _run(fake_hub, adapter_path, tmp_path / "run", only_files=[name], max_row_groups=1)
    assert result.manifest["max_row_groups_per_file"] == 1
    assert result.manifest["totals"]["records_seen"] == 3
    with pytest.raises(HFImportError, match="not in the pinned revision"):
        _run(fake_hub, adapter_path, tmp_path / "other", only_files=["other/000_00000.parquet"])


def test_coalesce_never_bridges_a_skipped_chunk():
    assert hf_import.coalesce([(0, 10), (20, 30)], forbidden=[(10, 20)]) == [(0, 10), (20, 30)]
    assert hf_import.coalesce([(0, 10), (20, 30)], forbidden=[]) == [(0, 30)]
    assert hf_import.coalesce([(0, 10), (10, 30)], forbidden=[]) == [(0, 30)]


JSONL_ADAPTER = f"""
dataset: {REPO}
revision: "{REV}"
config: jsonl
split: train
format: jsonl
document_boundary: record
columns_read: [text, source]
map:
  text: text
constants:
  language.declared: tr
extra: [source]
"""


def test_jsonl_path_downloads_whole_file_and_checks_sha(fake_hub, tmp_path):
    lines = [json.dumps({"text": f"Belge {i}\n\nikinci paragraf", "source": "s"}, ensure_ascii=False) for i in range(4)]
    lines.append(json.dumps({"text": "", "source": "s"}))
    fake_hub.state.files["jsonl/part-0.jsonl"] = ("\n".join(lines) + "\n").encode("utf-8")
    path = tmp_path / "jsonl.yaml"
    path.write_text(JSONL_ADAPTER, encoding="utf-8")
    result = _run(fake_hub, path, tmp_path / "run")
    assert result.manifest["totals"]["documents"] == 4
    assert result.manifest["adapter_report"]["empty_text"] == 1
    documents = list(read_documents(tmp_path / "run" / "shards" / result.shards[0]["local_name"]))
    assert documents[0]["text"] == "Belge 0\n\nikinci paragraf"
    assert not list((tmp_path / "run" / "raw").iterdir())


def test_jsonl_sha_mismatch_is_refused(fake_hub, tmp_path, monkeypatch):
    fake_hub.state.files["jsonl/part-0.jsonl"] = b'{"text": "a", "source": "s"}\n'
    path = tmp_path / "jsonl.yaml"
    path.write_text(JSONL_ADAPTER, encoding="utf-8")
    original = hf_import.HubClient.list_tree

    def tampered(self, prefix):
        return [hf_import.RemoteFile(f.path, f.size, "0" * 40, f.lfs_sha256, f.xet_hash) for f in original(self, prefix)]

    monkeypatch.setattr(hf_import.HubClient, "list_tree", tampered)
    with pytest.raises(HFImportError, match="git blob sha1"):
        _run(fake_hub, path, tmp_path / "run")


def test_adapter_path_must_stay_under_known_roots(tmp_path):
    from derlem_worker.jobs.hf_import_jobs import resolve_adapter_path

    adapters = tmp_path / "adapters"
    imports = tmp_path / "import"
    adapters.mkdir()
    imports.mkdir()
    good = adapters / "a.yaml"
    good.write_text(ADAPTER_YAML, encoding="utf-8")
    outside = tmp_path / "outside.yaml"
    outside.write_text(ADAPTER_YAML, encoding="utf-8")
    assert resolve_adapter_path(str(good), [imports, adapters]) == good.resolve()
    for bad in (str(outside), str(adapters / ".." / "outside.yaml"), "adapters/a.yaml", str(adapters / "a.txt")):
        with pytest.raises(ValueError):
            resolve_adapter_path(bad, [imports, adapters])


def test_release_freeze_refuses_import_manifest_sources(fake_hub, adapter_path, tmp_path):
    from derlem_worker.jobs.release_jobs import _refuse_import_manifest_source
    from derlem_worker.releases import ReleaseGateError

    result = _run(fake_hub, adapter_path, tmp_path / "run")
    with pytest.raises(ReleaseGateError, match="not yet supported"):
        _refuse_import_manifest_source(result.manifest_path, "source-1")
    plain = tmp_path / "plain.txt"
    plain.write_text('{"schema": "x"}\nmetin\n', encoding="utf-8")
    _refuse_import_manifest_source(plain, "source-2")


def test_resume_rejects_tampered_shard(fake_hub, adapter_path, tmp_path):
    work = tmp_path / "run"
    clean = _run(fake_hub, adapter_path, work)
    shard = work / "shards" / clean.shards[1]["local_name"]
    data = bytearray(shard.read_bytes())
    data[50] ^= 0xFF
    shard.write_bytes(bytes(data))
    fake_hub.state.range_log.clear()
    again = _run(fake_hub, adapter_path, work)
    assert again.files_skipped_by_resume == 2
    assert {path for path, _, _ in fake_hub.state.range_log} == {f"{CONFIG}/001_00000.parquet"}
    assert again.manifest_path.read_bytes() == clean.manifest_path.read_bytes()
    assert shard.read_bytes() != bytes(data)
