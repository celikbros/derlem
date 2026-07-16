from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import time
from uuid import uuid4

import pytest

from derlem_worker.jobs import queue
from derlem_worker.jobs.queue import Job, JobLeaseExpired, JobLeaseLost, QueueMixin
from derlem_worker.storage import ContentAddressedStore


class FakeResult:
    def __init__(self, row=None, *, rowcount: int = 0) -> None:
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql: str, params=()) -> FakeResult:
        self.calls.append((sql, tuple(params)))
        assert self.results, f"Unexpected SQL: {sql}"
        return self.results.pop(0)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeCheckpointStore:
    def __init__(self) -> None:
        self.promotions: list[tuple[str, str]] = []
        self.discards: list[str] = []

    def promote_checkpoint(self, current: str, following: str) -> bool:
        self.promotions.append((current, following))
        return True

    def discard_checkpoint(self, checkpoint_id: str) -> None:
        self.discards.append(checkpoint_id)


class ConflictingCheckpointStore(FakeCheckpointStore):
    def promote_checkpoint(self, current: str, following: str) -> bool:
        self.promotions.append((current, following))
        raise FileExistsError(following)


def make_queue() -> QueueMixin:
    worker = QueueMixin()
    worker.worker_id = "worker-new"
    worker.config = SimpleNamespace(
        database_url="postgresql://unused",
        lease_timeout_seconds=60.0,
        heartbeat_interval_seconds=10.0,
    )
    return worker


def stale_row(*, attempts: int, max_attempts: int) -> dict[str, object]:
    return {
        "id": uuid4(),
        "job_type": "generic_test_job",
        "payload": {"value": 1},
        "attempts": attempts,
        "max_attempts": max_attempts,
        "locked_by": "worker-dead",
    }


@pytest.mark.parametrize(
    ("attempts", "max_attempts", "expected_status"),
    [(1, 3, "queued"), (3, 3, "failed")],
)
def test_stale_recovery_uses_normal_retry_state_transition(
    attempts: int,
    max_attempts: int,
    expected_status: str,
) -> None:
    row = stale_row(attempts=attempts, max_attempts=max_attempts)
    connection = FakeConnection(
        [FakeResult(row), FakeResult(rowcount=1), FakeResult(None)]
    )

    recovered = make_queue()._recover_stale_jobs(connection)

    assert recovered == 1
    update_sql, update_params = connection.calls[1]
    assert "locked_by IS NOT DISTINCT FROM %s" in update_sql
    assert "attempts = %s" in update_sql
    assert update_params[0] == expected_status
    assert update_params[-2:] == ("worker-dead", attempts)
    assert connection.rollbacks == 0
    assert connection.commits == 2


def test_fail_or_retry_rejects_a_worker_that_lost_ownership() -> None:
    job = Job(uuid4(), "generic_test_job", {}, 1, 3, "worker-old")
    connection = FakeConnection([FakeResult(rowcount=0)])

    status = make_queue()._fail_or_retry(connection, job, RuntimeError("boom"))

    assert status is None
    assert connection.commits == 0
    assert connection.rollbacks == 1
    sql, params = connection.calls[0]
    assert "locked_by IS NOT DISTINCT FROM %s" in sql
    assert params[-2:] == ("worker-old", 1)


def test_ownership_check_locks_the_exact_claimed_attempt() -> None:
    job = Job(uuid4(), "generic_test_job", {}, 2, 3, "worker-old")
    connection = FakeConnection([FakeResult(None)])

    with pytest.raises(JobLeaseLost):
        make_queue()._assert_job_ownership(connection, job)

    sql, params = connection.calls[0]
    assert "FOR UPDATE" in sql
    assert "locked_by IS NOT DISTINCT FROM %s" in sql
    assert params == (job.id, "worker-old", 2)


def test_progress_is_guarded_by_owner_and_attempt() -> None:
    job = Job(uuid4(), "generic_test_job", {}, 2, 3, "worker-old")
    connection = FakeConnection([FakeResult(rowcount=0)])

    with pytest.raises(JobLeaseLost):
        make_queue()._write_job_progress(connection, job, "working", {"done": 4})

    sql, params = connection.calls[0]
    assert "locked_by IS NOT DISTINCT FROM %s" in sql
    assert "attempts = %s" in sql
    assert params[-3:] == (job.id, "worker-old", 2)
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_heartbeat_only_renews_the_owned_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    job = Job(uuid4(), "generic_test_job", {}, 2, 3, "worker-old")
    connection = FakeConnection([FakeResult(rowcount=1)])
    monkeypatch.setattr(queue.psycopg, "connect", lambda *_args, **_kwargs: connection)

    assert make_queue()._heartbeat_job(job) is True

    sql, params = connection.calls[0]
    assert "SET locked_at = now()" in sql
    assert "locked_by IS NOT DISTINCT FROM %s" in sql
    assert params == (job.id, "worker-old", 2)


def test_claim_recovers_stale_jobs_before_claiming_new_work() -> None:
    job_id = uuid4()
    claimed = {
        "id": job_id,
        "job_type": "generic_test_job",
        "payload": {},
        "attempts": 1,
        "max_attempts": 3,
        "locked_by": "worker-new",
    }
    connection = FakeConnection([FakeResult(None), FakeResult(claimed)])

    job = make_queue()._claim(connection)

    assert job is not None
    assert job.id == job_id
    assert job.lease_owner == "worker-new"
    assert "status = 'running'" in connection.calls[0][0]
    assert "WITH candidate" in connection.calls[1][0]


def test_orphan_attempt_sweep_removes_unreferenced_old_file(tmp_path: Path) -> None:
    worker = make_queue()
    worker.config.staging_root = tmp_path
    job_id = uuid4()
    artifact = tmp_path / f"job-{job_id}-attempt-2-leftover.extracted.txt"
    artifact.write_text("partial", encoding="utf-8")
    old = time.time() - 120
    os.utime(artifact, (old, old))
    connection = FakeConnection([FakeResult((False,))])

    removed = worker._sweep_orphan_attempt_artifacts(connection)

    assert removed == 1
    assert not artifact.exists()
    assert connection.calls[0][1] == (job_id, 2, str(artifact))


def test_orphan_attempt_sweep_preserves_referenced_child_file(tmp_path: Path) -> None:
    worker = make_queue()
    worker.config.staging_root = tmp_path
    job_id = uuid4()
    artifact = tmp_path / f"job-{job_id}-attempt-1-output.distilled.txt"
    artifact.write_text("child input", encoding="utf-8")
    old = time.time() - 120
    os.utime(artifact, (old, old))
    connection = FakeConnection([FakeResult((True,))])

    assert worker._sweep_orphan_attempt_artifacts(connection) == 0
    assert artifact.exists()


def test_successful_retry_transition_cleans_attempt_artifacts(tmp_path: Path) -> None:
    worker = make_queue()
    worker.config.staging_root = tmp_path
    job = Job(uuid4(), "generic_test_job", {}, 1, 3, "worker-old")
    artifact = tmp_path / f"job-{job.id}-attempt-1-part.snapshot.txt"
    artifact.write_text("partial", encoding="utf-8")
    connection = FakeConnection([FakeResult(rowcount=1)])

    assert worker._fail_or_retry(connection, job, RuntimeError("retry")) == "queued"
    assert not artifact.exists()


def test_normal_ingest_retry_promotes_checkpoint_to_next_attempt(tmp_path: Path) -> None:
    worker = make_queue()
    worker.config.staging_root = tmp_path
    worker.store = FakeCheckpointStore()
    job = Job(uuid4(), "ingest_local_file", {}, 2, 3, "worker-old")
    connection = FakeConnection([FakeResult(rowcount=1)])

    assert worker._fail_or_retry(connection, job, RuntimeError("transient")) == "queued"
    assert worker.store.promotions == [
        (f"{job.id}-attempt-2", f"{job.id}-attempt-3")
    ]
    assert worker.store.discards == []


def test_stale_ingest_retry_discards_unsafe_old_attempt_checkpoint(
    tmp_path: Path,
) -> None:
    worker = make_queue()
    worker.config.staging_root = tmp_path
    worker.store = FakeCheckpointStore()
    job = Job(uuid4(), "ingest_local_file", {}, 1, 3, "worker-dead")
    connection = FakeConnection([FakeResult(rowcount=1)])

    assert (
        worker._fail_or_retry(connection, job, JobLeaseExpired("expired"))
        == "queued"
    )
    assert worker.store.promotions == []
    assert worker.store.discards == [f"{job.id}-attempt-1"]


def test_promotion_conflict_never_discards_next_attempt_checkpoint(
    tmp_path: Path,
) -> None:
    worker = make_queue()
    worker.config.staging_root = tmp_path
    worker.store = ConflictingCheckpointStore()
    job = Job(uuid4(), "ingest_local_file", {}, 1, 3, "worker-old")
    connection = FakeConnection([FakeResult(rowcount=1)])

    assert worker._fail_or_retry(connection, job, RuntimeError("retry")) == "queued"
    assert worker.store.promotions == [
        (f"{job.id}-attempt-1", f"{job.id}-attempt-2")
    ]
    assert worker.store.discards == [f"{job.id}-attempt-1"]


def test_checkpoint_sweep_preserves_queued_retry_handoff(tmp_path: Path) -> None:
    worker = make_queue()
    worker.store = SimpleNamespace(
        temp_root=tmp_path,
        discard_checkpoint=lambda _checkpoint_id: pytest.fail(
            "referenced checkpoint must not be discarded"
        ),
    )
    job_id = uuid4()
    checkpoint = tmp_path / f"ingest-{job_id}-attempt-2.part"
    checkpoint.write_bytes(b"verified prefix")
    old = time.time() - 120
    os.utime(checkpoint, (old, old))
    connection = FakeConnection([FakeResult((True,))])

    assert worker._sweep_orphan_ingest_checkpoints(connection) == 0
    assert checkpoint.exists()
    sql, params = connection.calls[0]
    assert "status = 'queued'" in sql
    assert "attempts + 1" in sql
    assert params == (job_id, 2, 2)


def test_checkpoint_sweep_removes_terminal_legacy_checkpoint(tmp_path: Path) -> None:
    worker = make_queue()
    worker.store = ContentAddressedStore(tmp_path / "store")
    job_id = uuid4()
    checkpoint = worker.store.checkpoint_path(job_id)
    checkpoint.write_bytes(b"pre-upgrade prefix")
    old = time.time() - 120
    os.utime(checkpoint, (old, old))
    connection = FakeConnection([FakeResult((False,))])

    assert worker._sweep_orphan_ingest_checkpoints(connection) == 1
    assert not checkpoint.exists()
    sql, params = connection.calls[0]
    assert "status IN ('queued', 'running')" in sql
    assert params == (job_id,)
