from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
import pytest

from derlem_worker.jobs import Job, Worker


@pytest.fixture()
def pii_database_url(test_database_url: str, isolated_schema_name):
    # Adres ve _test korumasi conftest.test_database_url'de; sema adi olusturulma
    # zamanini tasir (supurucu). Tablolar _scan_pii ve _complete_pii_scan'in
    # dokundugu kolonlara indirgenmistir; gercek CHECK kisitlarini Go migration
    # testi (000027) dogrular.
    schema = isolated_schema_name("pii_worker")
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
                    byte_size bigint NOT NULL
                );

                CREATE TABLE sources (
                    id uuid PRIMARY KEY,
                    object_sha256 text NOT NULL REFERENCES storage_objects(sha256),
                    language text NOT NULL,
                    pii_status text NOT NULL DEFAULT 'not_scanned',
                    risk_level text NOT NULL DEFAULT 'unknown',
                    approval_status text NOT NULL DEFAULT 'raw_ingested',
                    duplicate_status text NOT NULL DEFAULT 'unique',
                    normalized_dedup_status text NOT NULL DEFAULT 'unique',
                    document_sampling_status text NOT NULL DEFAULT 'not_sampled'
                );

                CREATE TABLE pii_scans (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    source_id uuid NOT NULL REFERENCES sources(id),
                    job_id uuid,
                    object_sha256 text NOT NULL,
                    scanner_version text NOT NULL,
                    status text NOT NULL,
                    findings jsonb NOT NULL DEFAULT '{}'::jsonb,
                    scanned_at timestamptz NOT NULL DEFAULT now(),
                    UNIQUE (source_id, object_sha256, scanner_version)
                );

                CREATE TABLE background_jobs (
                    id uuid PRIMARY KEY,
                    job_type text NOT NULL,
                    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
                    status text NOT NULL DEFAULT 'queued',
                    attempts integer NOT NULL DEFAULT 0,
                    max_attempts integer NOT NULL DEFAULT 3,
                    locked_by text,
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


@pytest.mark.parametrize(
    ("language", "text", "status", "risk_level", "approval_status"),
    [
        # Desteklenen dil, bulgu yok: temiz muhru hak edilir, kaynak ilerler.
        ("tr", "Bu metin kisisel veri icermiyor.\n", "clear", "low", "auto_checked"),
        ("tr-TR", "Bu metin kisisel veri icermiyor.\n", "clear", "low", "auto_checked"),
        # Desteklenmeyen dil, bulgu yok: v1 burada "clear" yaziyordu. Risk "dusuk"
        # ilan edilmez, kaynak incelemeye ilerletilmez (freeze edilemeyecek bir
        # kaynaga insan emegi harcanmaz).
        ("en", "This text contains no personal data.\n", "not_evaluated", "unknown", "raw_ingested"),
        ("ku", "Ev nivis daneyen kesane nagire.\n", "not_evaluated", "unknown", "raw_ingested"),
        ("multi", "Karma metin, mixed text.\n", "not_evaluated", "unknown", "raw_ingested"),
        # Dilden bagimsiz desen her dilde calisir: bulgu varsa flagged.
        ("en", "Contact: test@example.com\n", "flagged", "high", "quarantined"),
    ],
)
def test_pii_gate_is_honest_about_unsupported_languages(
    pii_database_url: str,
    tmp_path: Path,
    language: str,
    text: str,
    status: str,
    risk_level: str,
    approval_status: str,
) -> None:
    storage_root = (tmp_path / "storage").resolve()
    config = SimpleNamespace(database_url=pii_database_url, storage_root=storage_root)
    worker = Worker(config, worker_id="pii-test-worker")
    stored = worker.store.ingest_bytes(text.encode("utf-8"))
    source_id = uuid4()
    job_id = uuid4()
    payload = {"source_id": str(source_id), "object_sha256": stored.sha256}
    with psycopg.connect(pii_database_url) as connection:
        connection.execute(
            "INSERT INTO storage_objects(sha256, storage_key, byte_size) VALUES (%s, %s, %s)",
            (stored.sha256, stored.storage_key, stored.byte_size),
        )
        connection.execute(
            "INSERT INTO sources(id, object_sha256, language) VALUES (%s, %s, %s)",
            (source_id, stored.sha256, language),
        )
        connection.execute(
            """
            INSERT INTO background_jobs(id, job_type, payload, status, attempts, locked_by)
            VALUES (%s, 'scan_pii', %s::jsonb, 'running', 1, %s)
            """,
            (job_id, json.dumps(payload), worker.worker_id),
        )
    job = Job(
        id=job_id,
        job_type="scan_pii",
        payload=payload,
        attempts=1,
        max_attempts=3,
        lease_owner=worker.worker_id,
    )

    # Dil DB'deki kaynak satirindan okunmali; tarayici tahmin etmez.
    object_sha256, report = worker._scan_pii(job)
    assert report.status == status
    assert report.scanner_version == "basic-tr-v2"

    with psycopg.connect(pii_database_url) as connection:
        worker._complete_pii_scan(connection, job, object_sha256, report)

    with psycopg.connect(pii_database_url, row_factory=dict_row) as connection:
        source = connection.execute(
            "SELECT pii_status, risk_level, approval_status FROM sources WHERE id = %s",
            (source_id,),
        ).fetchone()
        scan = connection.execute(
            "SELECT scanner_version, status FROM pii_scans WHERE source_id = %s",
            (source_id,),
        ).fetchone()
        audit = connection.execute(
            "SELECT details FROM audit_events WHERE entity_id = %s AND action = 'source.pii_scanned'",
            (source_id,),
        ).fetchone()
        job_row = connection.execute(
            "SELECT status, result FROM background_jobs WHERE id = %s",
            (job_id,),
        ).fetchone()

    assert source == {"pii_status": status, "risk_level": risk_level, "approval_status": approval_status}
    assert scan == {"scanner_version": "basic-tr-v2", "status": status}
    assert audit is not None
    assert audit["details"]["status"] == status
    assert audit["details"]["language"] == report.language
    assert job_row["status"] == "succeeded"
    assert job_row["result"]["status"] == status
    assert job_row["result"]["language"] == report.language
