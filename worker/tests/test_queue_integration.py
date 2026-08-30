from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from threading import Event, Thread
import time
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
import pytest

from derlem_worker.jobs import Job, Worker
from derlem_worker.jobs.queue import JobLeaseLost
from derlem_worker.storage import ContentAddressedStore


@pytest.fixture(scope="module")
def isolated_database_url():
    base_url = os.environ.get("DERLEM_TEST_DATABASE_URL", "").strip()
    if not base_url:
        pytest.skip("DERLEM_TEST_DATABASE_URL is not set")

    schema = f"derlem_worker_test_{uuid4().hex}"
    with psycopg.connect(base_url, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')

    settings = conninfo_to_dict(base_url)
    settings["options"] = f"-c search_path={schema}"
    test_url = make_conninfo(**settings)
    try:
        with psycopg.connect(test_url, autocommit=True) as connection:
            connection.execute(
                """
                CREATE TABLE background_jobs (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    job_type text NOT NULL,
                    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
                    status text NOT NULL DEFAULT 'queued',
                    priority integer NOT NULL DEFAULT 100,
                    available_at timestamptz NOT NULL DEFAULT now(),
                    attempts integer NOT NULL DEFAULT 0,
                    max_attempts integer NOT NULL DEFAULT 3,
                    locked_at timestamptz,
                    locked_by text,
                    result jsonb,
                    last_error text,
                    completed_at timestamptz,
                    created_by uuid,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE storage_objects (
                    sha256 text PRIMARY KEY,
                    storage_key text NOT NULL,
                    byte_size bigint NOT NULL,
                    media_type text NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE audit_events (
                    actor_type text NOT NULL,
                    action text NOT NULL,
                    entity_type text NOT NULL,
                    entity_id uuid NOT NULL,
                    details jsonb NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE production_runs (
                    id uuid PRIMARY KEY,
                    run_kind text NOT NULL,
                    origin_kind text NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE production_run_completions (
                    production_run_id uuid PRIMARY KEY,
                    job_id uuid NOT NULL UNIQUE,
                    output_manifest_sha256 text NOT NULL,
                    output_sha256 text NOT NULL,
                    output_byte_size bigint NOT NULL,
                    output_record_count bigint NOT NULL,
                    completed_at timestamptz NOT NULL
                )
                """
            )
        yield test_url
    finally:
        with psycopg.connect(base_url, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture(autouse=True)
def clean_worker_tables(isolated_database_url):
    with psycopg.connect(isolated_database_url, autocommit=True) as connection:
        connection.execute(
            "TRUNCATE production_run_completions, production_runs, "
            "background_jobs, storage_objects, audit_events"
        )


def make_database_worker(database_url: str, tmp_path: Path, worker_id: str) -> Worker:
    config = SimpleNamespace(
        database_url=database_url,
        storage_root=tmp_path / f"store-{worker_id}",
        staging_root=(tmp_path / "staging").resolve(),
        import_root=(tmp_path / "import").resolve(),
        lease_timeout_seconds=60.0,
        heartbeat_interval_seconds=10.0,
        poll_interval_seconds=0.01,
    )
    config.staging_root.mkdir(parents=True, exist_ok=True)
    config.import_root.mkdir(parents=True, exist_ok=True)
    return Worker(config, worker_id=worker_id)


def test_real_database_stale_recovery_transfers_attempt_ownership(
    isolated_database_url: str, tmp_path: Path
) -> None:
    old_worker = make_database_worker(isolated_database_url, tmp_path, "old-worker")
    new_worker = make_database_worker(isolated_database_url, tmp_path, "new-worker")
    with psycopg.connect(isolated_database_url) as connection:
        job_id = connection.execute(
            """
            INSERT INTO background_jobs(
                job_type, status, attempts, max_attempts, locked_at, locked_by
            )
            VALUES ('generic_test_job', 'running', 1, 3, now() - interval '10 minutes', 'old-worker')
            RETURNING id
            """
        ).fetchone()[0]
        connection.commit()

    with psycopg.connect(isolated_database_url, row_factory=dict_row) as connection:
        assert new_worker._recover_stale_jobs(connection) == 1
    with psycopg.connect(isolated_database_url) as connection:
        status, attempts, locked_by = connection.execute(
            "SELECT status, attempts, locked_by FROM background_jobs WHERE id = %s",
            (job_id,),
        ).fetchone()
        assert (status, attempts, locked_by) == ("queued", 1, None)
        connection.execute(
            "UPDATE background_jobs SET available_at = now() WHERE id = %s",
            (job_id,),
        )
        connection.commit()

    with psycopg.connect(isolated_database_url, row_factory=dict_row) as connection:
        claimed = new_worker._claim(connection)
    assert claimed is not None
    assert claimed.id == job_id
    assert claimed.attempts == 2
    assert claimed.lease_owner == "new-worker"

    expired_attempt = Job(
        job_id, "generic_test_job", {}, 1, 3, "old-worker"
    )
    with psycopg.connect(isolated_database_url) as connection:
        with pytest.raises(JobLeaseLost):
            old_worker._assert_job_ownership(connection, expired_attempt)


def test_stale_writer_and_reclaimed_attempt_never_share_checkpoint(
    isolated_database_url: str, tmp_path: Path, monkeypatch
) -> None:
    old_worker = make_database_worker(isolated_database_url, tmp_path, "old-writer")
    new_worker = make_database_worker(isolated_database_url, tmp_path, "new-writer")
    shared_store_root = tmp_path / "shared-store"
    old_worker.config.storage_root = shared_store_root
    new_worker.config.storage_root = shared_store_root
    old_worker.store = ContentAddressedStore(shared_store_root)
    new_worker.store = ContentAddressedStore(shared_store_root)
    source = old_worker.config.import_root / "large.txt"
    content = (b"checkpoint-fence\n" * 32_768) + b"done"
    source.write_bytes(content)
    source_id = uuid4()
    with psycopg.connect(isolated_database_url) as connection:
        job_id = connection.execute(
            """
            INSERT INTO background_jobs(
                job_type, payload, status, attempts, max_attempts,
                locked_at, locked_by
            )
            VALUES (
                'ingest_local_file',
                jsonb_build_object(
                    'source_id', %s::text,
                    'local_path', %s::text,
                    'original_filename', 'large.txt'
                ),
                'running', 1, 3, now() - interval '10 minutes', 'old-writer'
            )
            RETURNING id
            """,
            (str(source_id), str(source)),
        ).fetchone()[0]
        connection.commit()

    old_job = Job(
        job_id,
        "ingest_local_file",
        {
            "source_id": str(source_id),
            "local_path": str(source),
            "original_filename": "large.txt",
        },
        1,
        3,
        "old-writer",
    )
    started = Event()
    release = Event()
    original_ingest = old_worker.store.ingest_file_resumable
    progress_calls = 0

    def slow_old_ingest(source_path, *, checkpoint_id, progress_callback):
        def controlled_progress(progress):
            nonlocal progress_calls
            progress_calls += 1
            if progress_calls == 1:
                started.set()
                if not release.wait(10):
                    raise RuntimeError("test timed out waiting for reclaimed attempt")
                # Let the stale writer reach CAS publication. Its final guarded
                # progress update will then observe the transferred lease.
                return
            progress_callback(progress)

        return original_ingest(
            source_path,
            checkpoint_id=checkpoint_id,
            progress_callback=controlled_progress,
            progress_interval_bytes=64 * 1024,
        )

    monkeypatch.setattr(
        old_worker.store, "ingest_file_resumable", slow_old_ingest
    )
    old_thread = Thread(target=old_worker._run_claimed_job, args=(old_job,))
    old_thread.start()
    try:
        assert started.wait(10), "old writer did not reach its checkpoint"
        old_checkpoint_id = old_worker._ingest_checkpoint_id(old_job)
        old_checkpoint = old_worker.store.checkpoint_path(old_checkpoint_id)

        with psycopg.connect(
            isolated_database_url, row_factory=dict_row
        ) as connection:
            assert new_worker._recover_stale_jobs(connection) == 1
        with psycopg.connect(isolated_database_url) as connection:
            connection.execute(
                "UPDATE background_jobs SET available_at = now() WHERE id = %s",
                (job_id,),
            )
            connection.commit()
        with psycopg.connect(
            isolated_database_url, row_factory=dict_row
        ) as connection:
            claimed = new_worker._claim(connection)
        assert claimed is not None and claimed.attempts == 2
        new_checkpoint_id = new_worker._ingest_checkpoint_id(claimed)
        assert new_checkpoint_id != old_checkpoint_id

        new_outcome = new_worker.store.ingest_file_resumable(
            source, checkpoint_id=new_checkpoint_id
        )
        new_worker.store.finalize_checkpoint(new_checkpoint_id, new_outcome.stored)
        release.set()
        old_thread.join(10)
        assert not old_thread.is_alive()

        target = new_worker.store.root / new_outcome.stored.storage_key
        assert target.read_bytes() == content
        assert target.name == hashlib.sha256(content).hexdigest()

        if old_checkpoint.exists():
            old = time.time() - 120
            os.utime(old_checkpoint, (old, old))
            with psycopg.connect(
                isolated_database_url, row_factory=dict_row
            ) as connection:
                new_worker._sweep_orphan_ingest_checkpoints(connection)
        assert not old_checkpoint.exists()
    finally:
        release.set()
        old_thread.join(10)


def test_real_database_heartbeat_prevents_stale_recovery(
    isolated_database_url: str, tmp_path: Path
) -> None:
    owner = make_database_worker(isolated_database_url, tmp_path, "owner")
    observer = make_database_worker(isolated_database_url, tmp_path, "observer")
    with psycopg.connect(isolated_database_url) as connection:
        job_id = connection.execute(
            """
            INSERT INTO background_jobs(
                job_type, status, attempts, max_attempts, locked_at, locked_by
            )
            VALUES ('generic_test_job', 'running', 1, 3, now() - interval '10 minutes', 'owner')
            RETURNING id
            """
        ).fetchone()[0]
        connection.commit()

    job = Job(job_id, "generic_test_job", {}, 1, 3, "owner")
    assert owner._heartbeat_job(job) is True
    with psycopg.connect(isolated_database_url, row_factory=dict_row) as connection:
        assert observer._recover_stale_jobs(connection) == 0
        row = connection.execute(
            "SELECT status, locked_by FROM background_jobs WHERE id = %s",
            (job_id,),
        ).fetchone()
        status, locked_by = row["status"], row["locked_by"]
    assert (status, locked_by) == ("running", "owner")


def test_real_database_orphan_sweep_handles_dict_rows(
    isolated_database_url: str, tmp_path: Path
) -> None:
    worker = make_database_worker(isolated_database_url, tmp_path, "sweeper")
    job_id = uuid4()
    artifact = (
        worker.config.staging_root
        / f"job-{job_id}-attempt-1-orphan.extracted.txt"
    )
    artifact.write_text("orphan", encoding="utf-8")
    old = time.time() - 120
    os.utime(artifact, (old, old))

    with psycopg.connect(isolated_database_url, row_factory=dict_row) as connection:
        assert worker._sweep_orphan_attempt_artifacts(connection) == 1

    assert not artifact.exists()


def test_checkpoint_sweep_preserves_both_sides_of_queued_retry_handoff(
    isolated_database_url: str, tmp_path: Path
) -> None:
    worker = make_database_worker(isolated_database_url, tmp_path, "checkpoint-sweeper")
    with psycopg.connect(isolated_database_url) as connection:
        job_id = connection.execute(
            """
            INSERT INTO background_jobs(job_type, status, attempts, max_attempts)
            VALUES ('ingest_local_file', 'queued', 1, 3)
            RETURNING id
            """
        ).fetchone()[0]
        connection.commit()

    current = worker.store.checkpoint_path(f"{job_id}-attempt-1")
    following = worker.store.checkpoint_path(f"{job_id}-attempt-2")
    unrelated = worker.store.checkpoint_path(f"{job_id}-attempt-3")
    for checkpoint in (current, following, unrelated):
        checkpoint.write_bytes(b"verified prefix")
        old = time.time() - 120
        os.utime(checkpoint, (old, old))

    with psycopg.connect(isolated_database_url, row_factory=dict_row) as connection:
        assert worker._sweep_orphan_ingest_checkpoints(connection) == 1

    assert current.exists()
    assert following.exists()
    assert not unrelated.exists()


def test_distillation_handoff_rolls_back_as_one_database_transaction(
    isolated_database_url: str, tmp_path: Path, monkeypatch
) -> None:
    worker = make_database_worker(isolated_database_url, tmp_path, "distiller")
    source_id = uuid4()
    production_run_id = uuid4()
    creator_id = uuid4()
    monkeypatch.setattr(
        worker, "_validate_distillation_provenance", lambda *_args, **_kwargs: None
    )
    with psycopg.connect(isolated_database_url, autocommit=True) as connection:
        job_id = connection.execute(
            """
            INSERT INTO background_jobs(
                job_type, payload, status, attempts, max_attempts,
                locked_at, locked_by, created_by
            )
            VALUES (
                'distill_source',
                jsonb_build_object(
                    'source_id', %s::text,
                    'production_run_id', %s::text,
                    'provider', 'echo',
                    'prompt_template', 'fizik hakkında yaz',
                    'count', 1
                ),
                'running', 1, 3, now(), 'distiller', %s
            )
            RETURNING id
            """,
            (str(source_id), str(production_run_id), creator_id),
        ).fetchone()[0]
        connection.execute(
            """
            CREATE FUNCTION reject_distill_success() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.job_type = 'distill_source' AND NEW.status = 'succeeded' THEN
                    RAISE EXCEPTION 'simulated crash before parent success commit';
                END IF;
                RETURN NEW;
            END
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER reject_distill_success_trigger
            BEFORE UPDATE ON background_jobs
            FOR EACH ROW EXECUTE FUNCTION reject_distill_success()
            """
        )

    job = Job(
        job_id,
        "distill_source",
        {
            "source_id": str(source_id),
            "production_run_id": str(production_run_id),
            "provider": "echo",
            "prompt_template": "fizik hakkında yaz",
            "count": 1,
        },
        1,
        3,
        "distiller",
    )
    try:
        worker._run_claimed_job(job)
    finally:
        with psycopg.connect(isolated_database_url, autocommit=True) as connection:
            connection.execute(
                "DROP TRIGGER IF EXISTS reject_distill_success_trigger ON background_jobs"
            )
            connection.execute("DROP FUNCTION IF EXISTS reject_distill_success()")

    with psycopg.connect(isolated_database_url) as connection:
        parent_status = connection.execute(
            "SELECT status FROM background_jobs WHERE id = %s", (job_id,)
        ).fetchone()[0]
        child_count = connection.execute(
            "SELECT count(*) FROM background_jobs WHERE job_type = 'ingest_staged_file'"
        ).fetchone()[0]
        audit_count = connection.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        storage_count = connection.execute("SELECT count(*) FROM storage_objects").fetchone()[0]
    assert parent_status == "queued"
    assert (child_count, audit_count, storage_count) == (0, 0, 0)
    assert list(worker.config.staging_root.glob(f"job-{job.id}-attempt-1-*")) == []


def test_distillation_ingest_accepts_only_the_parent_bound_child_job(
    isolated_database_url: str, tmp_path: Path
) -> None:
    worker = make_database_worker(isolated_database_url, tmp_path, "bound-child")
    source_id = uuid4()
    production_run_id = uuid4()
    parent_job_id = uuid4()
    child_job_id = uuid4()
    stale_child_job_id = uuid4()
    creator_id = uuid4()
    manifest_sha256 = "a" * 64
    output_sha256 = "b" * 64
    output_byte_size = 321
    child_payload = {
        "source_id": str(source_id),
        "production_run_id": str(production_run_id),
        "distillation_job_id": str(parent_job_id),
        "distillation_output_sha256": output_sha256,
        "distillation_output_byte_size": output_byte_size,
    }

    with psycopg.connect(isolated_database_url, autocommit=True) as connection:
        connection.execute(
            """
            INSERT INTO production_runs(id, run_kind, origin_kind)
            VALUES (%s, 'model_generation', 'model')
            """,
            (production_run_id,),
        )
        connection.execute(
            """
            INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
            VALUES (%s, 'distill-manifest.json', 2, 'application/json')
            """,
            (manifest_sha256,),
        )
        connection.execute(
            """
            INSERT INTO background_jobs(
                id, job_type, payload, status, attempts, created_by, result,
                completed_at
            ) VALUES (
                %s, 'distill_source', %s::jsonb, 'succeeded', 1, %s,
                '{}'::jsonb, now()
            )
            """,
            (
                parent_job_id,
                json.dumps(
                    {
                        "source_id": str(source_id),
                        "production_run_id": str(production_run_id),
                    }
                ),
                creator_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO background_jobs(
                id, job_type, payload, status, attempts, locked_at, locked_by,
                created_by
            ) VALUES (
                %s, 'ingest_staged_file', %s::jsonb, 'running', 2, now(),
                'bound-child', %s
            )
            """,
            (child_job_id, json.dumps(child_payload), creator_id),
        )
        connection.execute(
            """
            UPDATE background_jobs
            SET result = jsonb_build_object(
                'production_run_id', %s::text,
                'manifest_sha256', %s::text,
                'ingest_job_id', %s::text,
                'output_sha256', %s::text,
                'output_byte_size', %s::bigint,
                'document_count', 1
            )
            WHERE id = %s
            """,
            (
                str(production_run_id),
                manifest_sha256,
                str(child_job_id),
                output_sha256,
                output_byte_size,
                parent_job_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO production_run_completions(
                production_run_id, job_id, output_manifest_sha256,
                output_sha256, output_byte_size, output_record_count,
                completed_at
            )
            SELECT %s, %s, %s, %s, %s, 1, completed_at
            FROM background_jobs WHERE id = %s
            """,
            (
                production_run_id,
                parent_job_id,
                manifest_sha256,
                output_sha256,
                output_byte_size,
                parent_job_id,
            ),
        )

    legitimate = Job(
        child_job_id,
        "ingest_staged_file",
        child_payload,
        2,
        3,
        "bound-child",
    )
    with psycopg.connect(isolated_database_url) as connection:
        worker._validate_ingest_provenance(
            connection,
            legitimate,
            source_id=str(source_id),
            data_origin="model",
            production_run_id=str(production_run_id),
            ingested_sha256=output_sha256,
            ingested_byte_size=output_byte_size,
        )

    with psycopg.connect(isolated_database_url, autocommit=True) as connection:
        connection.execute(
            """
            INSERT INTO background_jobs(
                id, job_type, payload, status, attempts, locked_at, locked_by,
                created_by
            ) VALUES (
                %s, 'ingest_staged_file', %s::jsonb, 'running', 2, now(),
                'bound-child', %s
            )
            """,
            (stale_child_job_id, json.dumps(child_payload), creator_id),
        )

    stale = Job(
        stale_child_job_id,
        "ingest_staged_file",
        child_payload,
        2,
        3,
        "bound-child",
    )
    with psycopg.connect(isolated_database_url) as connection:
        with pytest.raises(RuntimeError, match="invalid or stale"):
            worker._validate_ingest_provenance(
                connection,
                stale,
                source_id=str(source_id),
                data_origin="model",
                production_run_id=str(production_run_id),
                ingested_sha256=output_sha256,
                ingested_byte_size=output_byte_size,
            )

    with psycopg.connect(isolated_database_url, autocommit=True) as connection:
        connection.execute(
            "DELETE FROM production_run_completions WHERE production_run_id = %s",
            (production_run_id,),
        )
    with psycopg.connect(isolated_database_url) as connection:
        with pytest.raises(RuntimeError, match="invalid or stale"):
            worker._validate_ingest_provenance(
                connection,
                legitimate,
                source_id=str(source_id),
                data_origin="model",
                production_run_id=str(production_run_id),
                ingested_sha256=output_sha256,
                ingested_byte_size=output_byte_size,
            )
