from contextlib import nullcontext
import hashlib
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from uuid import uuid4

import pytest

from derlem_worker.extraction import ExtractionError, ExtractionReport
from derlem_worker.jobs import Job, Worker
from derlem_worker.jobs import ingest_jobs


def make_worker(tmp_path: Path) -> Worker:
    config = SimpleNamespace(
        database_url="postgresql://unused",
        storage_root=tmp_path / "store",
        staging_root=(tmp_path / "staging").resolve(),
        import_root=(tmp_path / "import").resolve(),
        poll_interval_seconds=1,
        extraction_max_source_bytes=100 * 1024 * 1024,
        extraction_max_docx_entries=2048,
        extraction_max_docx_uncompressed_bytes=256 * 1024 * 1024,
        extraction_max_pdf_pages=1000,
        extraction_max_output_chars=32 * 1024 * 1024,
    )
    config.staging_root.mkdir(parents=True)
    config.import_root.mkdir(parents=True)
    return Worker(config, worker_id="test")


class _FetchOneResult:
    def __init__(self, row) -> None:
        self.row = row

    def fetchone(self):
        return self.row


class _ProvenanceConnection:
    def __init__(self, row) -> None:
        self.row = row
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params=()):
        self.calls.append((sql, tuple(params)))
        return _FetchOneResult(self.row)


def test_ordinary_ingest_rejects_forged_production_handoff_fields(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    job = Job(
        uuid4(),
        "ingest_staged_file",
        {
            "source_id": str(uuid4()),
            "production_run_id": str(uuid4()),
            "distillation_job_id": str(uuid4()),
        },
        1,
        3,
        "worker",
    )
    connection = _ProvenanceConnection((uuid4(),))

    with pytest.raises(RuntimeError, match="unexpected"):
        worker._validate_ingest_provenance(
            connection,
            job,
            source_id=str(job.payload["source_id"]),
            data_origin="unknown",
            production_run_id=None,
            ingested_sha256="a" * 64,
            ingested_byte_size=1,
        )
    assert connection.calls == []


def test_run_bound_ingest_accepts_only_exact_distillation_child(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    source_id = str(uuid4())
    run_id = str(uuid4())
    parent_id = str(uuid4())
    output_sha256 = "a" * 64
    output_byte_size = 123
    job = Job(
        uuid4(),
        "ingest_staged_file",
        {
            "source_id": source_id,
            "production_run_id": run_id,
            "distillation_job_id": parent_id,
            "distillation_output_sha256": output_sha256,
            "distillation_output_byte_size": output_byte_size,
        },
        2,
        3,
        "worker-a",
    )
    connection = _ProvenanceConnection((parent_id,))

    worker._validate_ingest_provenance(
        connection,
        job,
        source_id=source_id,
        data_origin="model",
        production_run_id=run_id,
        ingested_sha256=output_sha256,
        ingested_byte_size=output_byte_size,
    )

    assert len(connection.calls) == 1
    sql, params = connection.calls[0]
    assert "parent.result->>'ingest_job_id' = child.id::text" in sql
    assert "parent.status = 'succeeded'" in sql
    assert "child.locked_by IS NOT DISTINCT FROM %s" in sql
    assert "parent.result->>'output_sha256'" in sql
    assert params[:3] == (job.id, "worker-a", 2)


@pytest.mark.parametrize(
    ("payload_change", "evidence_row"),
    [
        ({"production_run_id": None}, (uuid4(),)),
        ({"distillation_job_id": None}, (uuid4(),)),
        ({"production_run_id": "wrong-run"}, (uuid4(),)),
        ({"distillation_output_sha256": None}, (uuid4(),)),
        ({"distillation_output_byte_size": None}, (uuid4(),)),
        ({}, None),
    ],
)
def test_run_bound_ingest_rejects_forged_or_stale_child(
    tmp_path: Path, payload_change: dict[str, object], evidence_row
) -> None:
    worker = make_worker(tmp_path)
    source_id = str(uuid4())
    run_id = str(uuid4())
    payload: dict[str, object] = {
        "source_id": source_id,
        "production_run_id": run_id,
        "distillation_job_id": str(uuid4()),
        "distillation_output_sha256": "a" * 64,
        "distillation_output_byte_size": 123,
    }
    for key, value in payload_change.items():
        if value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
    job = Job(uuid4(), "ingest_staged_file", payload, 1, 3, "worker")

    with pytest.raises(RuntimeError, match="provenance"):
        worker._validate_ingest_provenance(
            _ProvenanceConnection(evidence_row),
            job,
            source_id=source_id,
            data_origin="model",
            production_run_id=run_id,
            ingested_sha256="a" * 64,
            ingested_byte_size=123,
        )


def test_run_bound_ingest_rejects_staged_output_mutation(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    source_id = str(uuid4())
    run_id = str(uuid4())
    parent_id = str(uuid4())
    expected_sha256 = "a" * 64
    expected_byte_size = 123
    job = Job(
        uuid4(),
        "ingest_staged_file",
        {
            "source_id": source_id,
            "production_run_id": run_id,
            "distillation_job_id": parent_id,
            "distillation_output_sha256": expected_sha256,
            "distillation_output_byte_size": expected_byte_size,
        },
        1,
        3,
        "worker",
    )

    with pytest.raises(RuntimeError, match="output artifact mismatch"):
        worker._validate_ingest_provenance(
            _ProvenanceConnection((parent_id,)),
            job,
            source_id=source_id,
            data_origin="model",
            production_run_id=run_id,
            ingested_sha256="b" * 64,
            ingested_byte_size=expected_byte_size + 1,
        )


def test_staged_ingest_path_must_stay_under_staging_root(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("data", encoding="utf-8")
    job = Job(
        id=uuid4(),
        job_type="ingest_staged_file",
        payload={"source_id": str(uuid4()), "staged_path": str(outside)},
        attempts=1,
        max_attempts=3,
    )

    with pytest.raises(ValueError):
        worker._ingest_path(job)


def test_staged_ingest_accepts_file_under_staging_root(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    staged = worker.config.staging_root / "upload.part"
    staged.write_text("data", encoding="utf-8")
    job = Job(
        id=uuid4(),
        job_type="ingest_staged_file",
        payload={"source_id": str(uuid4()), "staged_path": str(staged)},
        attempts=1,
        max_attempts=3,
    )

    assert worker._ingest_path(job) == staged.resolve()


def test_local_ingest_accepts_regular_file_under_import_root(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    source = worker.config.import_root / "source.txt"
    source.write_text("data", encoding="utf-8")
    job = Job(
        id=uuid4(),
        job_type="ingest_local_file",
        payload={"source_id": str(uuid4()), "local_path": str(source)},
        attempts=1,
        max_attempts=3,
    )

    assert worker._ingest_path(job) == source.resolve()


@pytest.mark.parametrize("target_kind", ["outside", "directory", "missing", "relative"])
def test_local_ingest_rejects_invalid_target(tmp_path: Path, target_kind: str) -> None:
    worker = make_worker(tmp_path)
    if target_kind == "outside":
        target = tmp_path / "outside.txt"
        target.write_text("data", encoding="utf-8")
    elif target_kind == "directory":
        target = worker.config.import_root
    elif target_kind == "missing":
        target = worker.config.import_root / "missing.txt"
    else:
        target = Path("relative.txt")
    job = Job(
        id=uuid4(),
        job_type="ingest_local_file",
        payload={"source_id": str(uuid4()), "local_path": str(target)},
        attempts=1,
        max_attempts=3,
    )

    with pytest.raises(ValueError):
        worker._ingest_path(job)


def test_local_ingest_rejects_symlink(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("data", encoding="utf-8")
    link = worker.config.import_root / "source-link.txt"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks are unavailable: {error}")
    job = Job(
        id=uuid4(),
        job_type="ingest_local_file",
        payload={"source_id": str(uuid4()), "local_path": str(link)},
        attempts=1,
        max_attempts=3,
    )

    with pytest.raises(ValueError, match="symbolic links"):
        worker._ingest_path(job)


def test_text_ingest_source_is_pinned_by_hardlink_when_supported(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    source = worker.config.import_root / "large.txt"
    source.write_text("stable bytes\n", encoding="utf-8")
    job = Job(uuid4(), "ingest_local_file", {"source_id": str(uuid4())}, 1, 3)

    try:
        pinned = worker._hardlink_ingest_source(job, source, suffix=".txt")
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"hard links are unavailable: {error}")
    try:
        assert os.path.samefile(source, pinned)
        assert pinned.read_bytes() == source.read_bytes()
    finally:
        pinned.unlink(missing_ok=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific hard-link semantics")
def test_windows_text_snapshot_copies_readonly_source(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    source = worker.config.import_root / "readonly.txt"
    source.write_text("stable bytes\n", encoding="utf-8")
    source.chmod(stat.S_IREAD)
    job = Job(uuid4(), "ingest_local_file", {"source_id": str(uuid4())}, 1, 3)

    snapshot = worker._snapshot_ingest_source(job, source)
    try:
        assert not os.path.samefile(source, snapshot)
        assert snapshot.read_bytes() == source.read_bytes()
        snapshot.unlink()
    finally:
        source.chmod(stat.S_IREAD | stat.S_IWRITE)
        snapshot.unlink(missing_ok=True)


def test_pdf_snapshot_preserves_suffix_and_bytes(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    source = worker.config.import_root / "local.PDF"
    content = b"%PDF-1.7\noriginal"
    source.write_bytes(content)
    job = Job(uuid4(), "ingest_local_file", {"source_id": str(uuid4())}, 1, 3)

    snapshot = worker._snapshot_ingest_source(job, source)
    try:
        assert snapshot.suffix == ".pdf"
        assert snapshot.read_bytes() == content
        assert not os.path.samefile(source, snapshot)
    finally:
        snapshot.unlink(missing_ok=True)


def test_snapshot_rejects_source_changed_between_lstat_and_open(
    tmp_path: Path, monkeypatch
) -> None:
    worker = make_worker(tmp_path)
    source = worker.config.import_root / "changing.pdf"
    source.write_bytes(b"%PDF-1.7\nold")
    job = Job(uuid4(), "ingest_local_file", {"source_id": str(uuid4())}, 1, 3)
    target = worker.config.staging_root / "controlled.snapshot.pdf"
    target_descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    original_open = ingest_jobs.os.open

    monkeypatch.setattr(
        worker,
        "_new_attempt_artifact",
        lambda _job, *, suffix: (target_descriptor, target),
    )

    def replace_before_open(path, flags):
        source.write_bytes(b"%PDF-1.7\nchanged-content")
        return original_open(path, flags)

    monkeypatch.setattr(ingest_jobs.os, "open", replace_before_open)

    with pytest.raises(ValueError, match="changed between validation and open"):
        worker._copy_ingest_source(
            job, source, suffix=".pdf", extraction_input=True
        )

    assert not target.exists()


def test_extraction_and_raw_lineage_use_the_same_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    worker = make_worker(tmp_path)
    source = worker.config.import_root / "local.pdf"
    original = b"%PDF-1.7\noriginal-version"
    source.write_bytes(original)
    job = Job(
        uuid4(),
        "ingest_local_file",
        {"source_id": str(uuid4())},
        1,
        3,
    )
    snapshot = worker._snapshot_ingest_source(job, source)
    source.write_bytes(b"%PDF-1.7\nmutated-after-snapshot")
    parsed: dict[str, bytes] = {}

    def fake_convert(source_path, target_path, **_kwargs):
        parsed["bytes"] = source_path.read_bytes()
        target_path.write_text("derived\n", encoding="utf-8")
        return ExtractionReport("test", ".pdf", 1, 1, 7)

    monkeypatch.setattr(ingest_jobs, "convert_file", fake_convert)
    derived = None
    try:
        _, extraction, derived = worker._maybe_extract(
            job, snapshot, source_name=source.name
        )
        assert parsed["bytes"] == original
        assert extraction is not None
        assert extraction["original_filename"] == "local.pdf"
        assert extraction["raw_sha256"] == hashlib.sha256(original).hexdigest()
    finally:
        if derived is not None:
            derived.unlink(missing_ok=True)
        snapshot.unlink(missing_ok=True)


def test_oversized_extraction_is_rejected_before_snapshot_copy(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    worker.config.extraction_max_source_bytes = 8
    source = worker.config.import_root / "oversized.pdf"
    source.write_bytes(b"%PDF-1.7\nfar-too-large")
    job = Job(uuid4(), "ingest_local_file", {"source_id": str(uuid4())}, 1, 3)

    with pytest.raises(ExtractionError, match="kaynak boyutu sınırını"):
        worker._snapshot_ingest_source(job, source)

    assert list(worker.config.staging_root.glob(f"job-{job.id}-attempt-1-*")) == []


def test_failed_extraction_removes_partial_derived_file(tmp_path: Path, monkeypatch) -> None:
    worker = make_worker(tmp_path)
    staged = worker.config.staging_root / "broken.pdf"
    staged.write_bytes(b"not-a-pdf")
    job = Job(
        id=uuid4(),
        job_type="ingest_staged_file",
        payload={
            "source_id": str(uuid4()),
            "staged_path": str(staged),
            "original_filename": "broken.pdf",
        },
        attempts=1,
        max_attempts=3,
    )
    created_paths: list[Path] = []
    original_new_artifact = worker._new_attempt_artifact

    def tracked_artifact(job_arg, *, suffix):
        descriptor, path = original_new_artifact(job_arg, suffix=suffix)
        created_paths.append(path)
        return descriptor, path

    monkeypatch.setattr(worker, "_new_attempt_artifact", tracked_artifact)

    with pytest.raises(ExtractionError):
        worker._maybe_extract(job, staged)

    assert len(created_paths) == 1
    assert not created_paths[0].exists()


def test_worker_applies_configured_extraction_source_limit(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    worker.config.extraction_max_source_bytes = 8
    staged = worker.config.staging_root / "oversized.pdf"
    staged.write_bytes(b"%PDF-1.7\noversized")
    job = Job(
        id=uuid4(),
        job_type="ingest_staged_file",
        payload={
            "source_id": str(uuid4()),
            "staged_path": str(staged),
            "original_filename": "oversized.pdf",
        },
        attempts=1,
        max_attempts=3,
    )

    with pytest.raises(ExtractionError, match="kaynak boyutu sınırını"):
        worker._maybe_extract(job, staged)

    assert list(worker.config.staging_root.glob("*.extracted.txt")) == []


def test_downstream_ingest_failure_removes_derived_file(tmp_path: Path, monkeypatch) -> None:
    worker = make_worker(tmp_path)
    staged = worker.config.staging_root / "source.pdf"
    staged.write_bytes(b"input")
    derived = worker.config.staging_root / "source.extracted.txt"
    derived.write_text("derived\n", encoding="utf-8")
    job = Job(
        id=uuid4(),
        job_type="ingest_staged_file",
        payload={"source_id": str(uuid4()), "staged_path": str(staged)},
        attempts=1,
        max_attempts=3,
        lease_owner="test",
    )

    monkeypatch.setattr(worker, "_ingest_path", lambda _job: staged)
    monkeypatch.setattr(
        worker,
        "_maybe_extract",
        lambda _job, _path, **_kwargs: (derived, {"method": "test"}, derived),
    )

    def fail_ingest(*_args, **_kwargs):
        raise RuntimeError("downstream failure")

    monkeypatch.setattr(worker.store, "ingest_file_resumable", fail_ingest)
    monkeypatch.setattr(
        "derlem_worker.jobs.worker.psycopg.connect",
        lambda *_args, **_kwargs: nullcontext(SimpleNamespace()),
    )
    monkeypatch.setattr(worker, "_fail_or_retry", lambda *_args, **_kwargs: "queued")

    worker._run_claimed_job(job)

    assert not derived.exists()
    assert staged.exists()
