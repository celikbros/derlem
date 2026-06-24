from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from derlem_worker.jobs import Job, Worker


def make_worker(tmp_path: Path) -> Worker:
    config = SimpleNamespace(
        database_url="postgresql://unused",
        storage_root=tmp_path / "store",
        staging_root=(tmp_path / "staging").resolve(),
        poll_interval_seconds=1,
    )
    config.staging_root.mkdir(parents=True)
    return Worker(config, worker_id="test")


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
