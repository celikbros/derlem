from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from derlem_worker.jobs import Worker

# Bakim taramasi eskiden yalniz worker acilisinda kosuyordu (main.py); acilistan
# sonra not_checked'e cekilen kaynak (TASK-014 sifirlamasi) hic kuyruga girmiyordu.
# TASK-015: run_forever dongusu araligi dolunca taramayi kosar.


def _worker(tmp_path: Path, interval: float) -> tuple[Worker, list[float]]:
    config = SimpleNamespace(database_url="postgresql://unused", storage_root=tmp_path / "storage",
                             max_document_bytes=1024, maintenance_sweep_seconds=interval)
    worker = Worker(config, worker_id="sweep-test")
    calls: list[float] = []
    worker.enqueue_maintenance_jobs = lambda: calls.append(1.0) or 0  # type: ignore[method-assign]
    return worker, calls


def test_sweep_runs_once_per_interval_not_on_every_poll(tmp_path: Path) -> None:
    worker, calls = _worker(tmp_path, interval=300.0)

    assert worker.maybe_sweep_maintenance(now=1000.0) is True   # ilk cagri: hemen
    assert worker.maybe_sweep_maintenance(now=1100.0) is False  # aralik dolmadi
    assert worker.maybe_sweep_maintenance(now=1299.0) is False
    assert worker.maybe_sweep_maintenance(now=1300.0) is True   # tam aralikta bir kez daha
    assert worker.maybe_sweep_maintenance(now=1301.0) is False
    assert len(calls) == 2


def test_sweep_failure_does_not_stop_the_loop(tmp_path: Path) -> None:
    worker, _ = _worker(tmp_path, interval=10.0)

    def boom() -> int:
        raise RuntimeError("db down")

    worker.enqueue_maintenance_jobs = boom  # type: ignore[method-assign]
    assert worker.maybe_sweep_maintenance(now=0.0) is True
    assert worker.maybe_sweep_maintenance(now=5.0) is False


def test_default_interval_when_config_predates_the_field(tmp_path: Path) -> None:
    config = SimpleNamespace(database_url="postgresql://unused", storage_root=tmp_path / "storage", max_document_bytes=1024)
    worker = Worker(config, worker_id="sweep-test")
    worker.enqueue_maintenance_jobs = lambda: 0  # type: ignore[method-assign]

    assert worker.maybe_sweep_maintenance(now=0.0) is True
    assert worker.maybe_sweep_maintenance(now=299.0) is False
    assert worker.maybe_sweep_maintenance(now=300.0) is True
