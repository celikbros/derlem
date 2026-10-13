"""TASK-047: ``jury_sample`` isi veritabaniyla -- sayilar kaynak kartina
(``sources.source_metadata.quality_numbers``) girer, anahtar yoksa
``judge_unavailable``, butce asiminda is kalici olarak durur.

Tablolar isin dokundugu kolonlara indirgenmistir (test_pii_gate_integration
deseni); _test veritabani ve izole sema conftest'ten gelir.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
import pytest

from derlem_worker import jury
from derlem_worker.jobs import Job, Worker
from derlem_worker.jobs import jury_jobs
from derlem_worker.jury import JudgeResponse, JudgeSettings


@pytest.fixture()
def jury_database_url(test_database_url: str, isolated_schema_name):
    schema = isolated_schema_name("jury_worker")
    with psycopg.connect(test_database_url, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
    settings = conninfo_to_dict(test_database_url)
    settings["options"] = f"-c search_path={schema}"
    test_url = make_conninfo(**settings)
    try:
        with psycopg.connect(test_url, autocommit=True) as connection:
            connection.execute(
                """
                CREATE TABLE storage_objects (
                    sha256 text PRIMARY KEY,
                    storage_key text NOT NULL UNIQUE,
                    byte_size bigint NOT NULL,
                    media_type text
                );
                CREATE TABLE sources (
                    id uuid PRIMARY KEY,
                    object_sha256 text NOT NULL REFERENCES storage_objects(sha256),
                    language text NOT NULL,
                    content_purpose text NOT NULL DEFAULT 'pretrain',
                    document_count bigint,
                    reviewed_document_count bigint NOT NULL DEFAULT 0,
                    flagged_document_count bigint NOT NULL DEFAULT 0,
                    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
                );
                CREATE TABLE pii_scans (
                    source_id uuid NOT NULL REFERENCES sources(id),
                    object_sha256 text NOT NULL,
                    scanner_version text NOT NULL,
                    status text NOT NULL,
                    findings jsonb NOT NULL DEFAULT '{}'::jsonb,
                    scanned_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE background_jobs (
                    id uuid PRIMARY KEY,
                    job_type text NOT NULL,
                    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
                    status text NOT NULL DEFAULT 'queued',
                    attempts integer NOT NULL DEFAULT 0,
                    max_attempts integer NOT NULL DEFAULT 3,
                    locked_by text,
                    locked_at timestamptz,
                    available_at timestamptz NOT NULL DEFAULT now(),
                    last_error text,
                    result jsonb,
                    completed_at timestamptz,
                    updated_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE audit_events (
                    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    actor_type text NOT NULL,
                    action text NOT NULL,
                    entity_type text NOT NULL,
                    entity_id uuid,
                    details jsonb NOT NULL DEFAULT '{}'::jsonb
                );
                """
            )
        yield test_url
    finally:
        with psycopg.connect(test_database_url, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _setup(url: str, tmp_path: Path, *, seed: int = 20261013, n: int = 6):
    storage_root = (tmp_path / "storage").resolve()
    staging_root = (tmp_path / "staging").resolve()
    config = SimpleNamespace(database_url=url, storage_root=storage_root, staging_root=staging_root,
                             max_document_bytes=256 * 1024)
    worker = Worker(config, worker_id="jury-test-worker")
    lines = [f"Belge {index}: düzgün Türkçe bir paragraf, içinde sayı {index * 13} geçiyor." for index in range(1, 21)]
    lines[3] = "Bize yazın: ali@ornek.com.tr adresinden ulaşabilirsiniz, haber metni devam ediyor."
    stored = worker.store.ingest_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    source_id = uuid4()
    job_id = uuid4()
    payload = {"source_id": str(source_id), "object_sha256": stored.sha256, "seed": seed, "n": n}
    with psycopg.connect(url) as connection:
        connection.execute("INSERT INTO storage_objects(sha256, storage_key, byte_size) VALUES (%s, %s, %s)",
                           (stored.sha256, stored.storage_key, stored.byte_size))
        connection.execute(
            """INSERT INTO sources(id, object_sha256, language, document_count, reviewed_document_count,
                   flagged_document_count, source_metadata)
               VALUES (%s, %s, 'tr', 20, 10, 2, '{"seed_key": "korunur"}'::jsonb)""",
            (source_id, stored.sha256),
        )
        connection.execute(
            "INSERT INTO pii_scans(source_id, object_sha256, scanner_version, status, findings) VALUES (%s, %s, 'basic-tr-v2', 'flagged', %s::jsonb)",
            (source_id, stored.sha256, json.dumps({"email": 1, "phone": 0})),
        )
        connection.execute(
            "INSERT INTO background_jobs(id, job_type, payload, status, attempts, locked_by) VALUES (%s, 'jury_sample', %s::jsonb, 'running', 1, %s)",
            (job_id, json.dumps(payload), worker.worker_id),
        )
    job = Job(id=job_id, job_type="jury_sample", payload=payload, attempts=1, max_attempts=3, lease_owner=worker.worker_id)
    return worker, job, source_id


def _source_and_job(url: str, source_id, job_id):
    with psycopg.connect(url, row_factory=dict_row) as connection:
        source = connection.execute("SELECT source_metadata FROM sources WHERE id = %s", (source_id,)).fetchone()
        job = connection.execute("SELECT status, result, last_error FROM background_jobs WHERE id = %s", (job_id,)).fetchone()
        objects = {row["sha256"]: row["media_type"] for row in connection.execute("SELECT sha256, media_type FROM storage_objects")}
        audit = connection.execute(
            "SELECT details FROM audit_events WHERE action = 'source.quality_numbers_recorded' AND entity_id = %s", (source_id,)
        ).fetchall()
    return source["source_metadata"], job, objects, audit


def test_without_key_job_records_judge_unavailable_numbers_on_the_card(jury_database_url, tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv(jury.LEDGER_DIR_ENV, str(tmp_path / "ledger"))
    worker, job, source_id = _setup(jury_database_url, tmp_path)

    worker._run_claimed_job(job)

    metadata, job_row, objects, audit = _source_and_job(jury_database_url, source_id, job.id)
    assert job_row["status"] == "succeeded", job_row["last_error"]
    assert metadata["seed_key"] == "korunur"  # diger metadata anahtarlari korunur
    numbers = metadata["quality_numbers"]
    assert numbers["schema"] == "derlem.quality-numbers.v1"
    assert numbers["jury"]["status"] == "judge_unavailable" and numbers["judge_id"] is None
    assert numbers["sample"]["n"] == 6 and numbers["sample"]["population_documents"] == 20
    assert numbers["pii"]["n"] == 6 and numbers["rule"]["policy"] == "tr-web-v3"
    assert numbers["pii"]["population"]["hits_per_1k_documents"] == 50.0
    assert numbers["human"]["count"] == 2 and numbers["human"]["n"] == 10
    assert numbers["blind_sha256"] in objects and numbers["key_sha256"] in objects
    assert objects[numbers["blind_sha256"]].startswith("application/x-ndjson")
    assert numbers["artifacts"][jury.BLIND_FILE] == numbers["blind_sha256"]
    assert job_row["result"]["jury_status"] == "judge_unavailable" and "next_step" in job_row["result"]
    assert audit and audit[0]["details"]["jury_status"] == "judge_unavailable"
    blind = (worker.config.storage_root / f"objects/sha256/{numbers['blind_sha256'][:2]}/{numbers['blind_sha256'][2:4]}/{numbers['blind_sha256']}").read_text(encoding="utf-8")
    assert all(tuple(sorted(json.loads(line))) == jury.BLIND_FIELDS for line in blind.splitlines())
    assert not (tmp_path / "ledger").exists()  # anahtar yokken sayaca dokunulmaz


def _fake_judge(monkeypatch, calls: list[str]) -> None:
    settings = JudgeSettings(provider="anthropic", model="claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY")
    monkeypatch.setattr(jury_jobs, "resolve_judge", lambda: (settings, "sk-test"))

    def caller_factory(_settings, _key, _rubric):
        def call(message: str) -> JudgeResponse:
            calls.append(message)
            verdict = "cop" if len(calls) % 3 == 0 else "kalsin"
            return JudgeResponse(text=json.dumps({"hukum": verdict, "tur": "haber", "cop_nedeni": "seo-ticari" if verdict == "cop" else ""}),
                                 stop_reason="end_turn", input_tokens=500, output_tokens=40)
        return call

    monkeypatch.setattr(jury_jobs, "anthropic_judge_caller", caller_factory)


def test_judged_job_writes_decision_rows_to_store_and_card(jury_database_url, tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    _fake_judge(monkeypatch, calls)
    monkeypatch.setenv(jury.LEDGER_DIR_ENV, str(tmp_path / "ledger"))
    worker, job, source_id = _setup(jury_database_url, tmp_path)

    worker._run_claimed_job(job)

    metadata, job_row, objects, _audit = _source_and_job(jury_database_url, source_id, job.id)
    assert job_row["status"] == "succeeded", job_row["last_error"]
    numbers = metadata["quality_numbers"]
    assert len(calls) == 12  # 6 satir x 2 gecis
    assert numbers["jury"]["status"] == "judged" and numbers["jury"]["n"] == 6
    assert numbers["judge_id"] == f"sonnet+juri-siki-v1@{jury.rubric_sha256()[:8]}"
    assert numbers["jury"]["retest"]["n"] == 6
    decisions = numbers["decisions"]
    assert decisions["rows"] == 12 and objects[decisions["sha256"]] == "application/vnd.apache.parquet"
    from derlem_worker.document_record import read_decisions

    stored = worker.config.storage_root / f"objects/sha256/{decisions['sha256'][:2]}/{decisions['sha256'][2:4]}/{decisions['sha256']}"
    rows = list(read_decisions(stored))
    assert {row["decision_type"] for row in rows} == {"jury"} and {row["judge"] for row in rows} == {numbers["judge_id"]}
    assert numbers["cost"]["calls"] == 12 and numbers["cost"]["price_table"] == jury.PRICE_TABLE_VERSION
    assert job_row["result"]["calls"] == 12 and job_row["result"]["decisions_sha256"] == decisions["sha256"]


def test_budget_cap_stops_the_job_permanently_before_any_call(jury_database_url, tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    _fake_judge(monkeypatch, calls)
    monkeypatch.setenv(jury.LEDGER_DIR_ENV, str(tmp_path / "ledger"))
    monkeypatch.setenv("DERLEM_JURY_MAX_CALLS_PER_RUN", "5")
    worker, job, source_id = _setup(jury_database_url, tmp_path)

    worker._run_claimed_job(job)

    metadata, job_row, _objects, _audit = _source_and_job(jury_database_url, source_id, job.id)
    assert calls == []
    assert job_row["status"] == "failed"  # attempts 1 < max 3: kalici, yeniden denenmez
    assert "judge_budget_exceeded" in job_row["last_error"]
    assert "quality_numbers" not in metadata


def test_retry_of_the_same_job_cannot_pay_twice(jury_database_url, tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    _fake_judge(monkeypatch, calls)
    monkeypatch.setenv(jury.LEDGER_DIR_ENV, str(tmp_path / "ledger"))
    monkeypatch.setenv("DERLEM_JURY_MAX_CALLS_PER_RUN", "15")
    worker, job, source_id = _setup(jury_database_url, tmp_path)
    worker._run_claimed_job(job)
    assert len(calls) == 12
    # Ayni is yeniden deneniyor (or. tamamlamadan sonra kaybolan onay): kosu sayaci
    # ise bagli oldugu icin 12 + 12 > 15 -> hicbir ucretli cagri yapilmadan durur.
    with psycopg.connect(jury_database_url) as connection:
        connection.execute("UPDATE background_jobs SET status = 'running', attempts = 2 WHERE id = %s", (job.id,))
    retry = Job(id=job.id, job_type=job.job_type, payload=job.payload, attempts=2, max_attempts=3, lease_owner=worker.worker_id)
    worker._run_claimed_job(retry)
    _metadata, job_row, _objects, _audit = _source_and_job(jury_database_url, source_id, job.id)
    assert len(calls) == 12 and job_row["status"] == "failed" and "judge_budget_exceeded" in job_row["last_error"]
