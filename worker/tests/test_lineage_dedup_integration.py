from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
import pytest

from derlem_worker.jobs import Job, Worker


@pytest.fixture()
def lineage_database_url():
    base_url = os.environ.get("DERLEM_TEST_DATABASE_URL", "").strip()
    if not base_url:
        pytest.skip("DERLEM_TEST_DATABASE_URL is not set")

    schema = f"derlem_lineage_worker_test_{uuid4().hex}"
    with psycopg.connect(base_url, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')

    settings = conninfo_to_dict(base_url)
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
                    duplicate_status text NOT NULL DEFAULT 'unique',
                    derived_from_source_id uuid REFERENCES sources(id) ON DELETE RESTRICT,
                    normalized_dedup_status text NOT NULL DEFAULT 'not_checked',
                    normalized_duplicate_count bigint NOT NULL DEFAULT 0,
                    normalized_duplicate_source_count bigint NOT NULL DEFAULT 0,
                    document_count bigint,
                    risk_level text NOT NULL DEFAULT 'low',
                    approval_status text NOT NULL DEFAULT 'raw_ingested',
                    pii_status text NOT NULL DEFAULT 'clear',
                    document_sampling_status text NOT NULL DEFAULT 'not_sampled',
                    created_by uuid
                );

                CREATE TABLE document_fingerprints (
                    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    source_sha256 text NOT NULL REFERENCES storage_objects(sha256),
                    source_ordinal bigint NOT NULL,
                    normalized_sha256 text NOT NULL,
                    normalized_char_count bigint NOT NULL,
                    fingerprint_version text NOT NULL,
                    PRIMARY KEY (source_id, source_sha256, source_ordinal, fingerprint_version)
                );

                CREATE TABLE background_jobs (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    job_type text NOT NULL,
                    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
                    status text NOT NULL DEFAULT 'queued',
                    attempts integer NOT NULL DEFAULT 0,
                    max_attempts integer NOT NULL DEFAULT 3,
                    locked_by text,
                    result jsonb,
                    completed_at timestamptz,
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    created_by uuid
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
        with psycopg.connect(base_url, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_normalized_dedup_excludes_all_ancestors_but_not_unrelated_sources(
    lineage_database_url: str, tmp_path: Path
) -> None:
    config = SimpleNamespace(
        database_url=lineage_database_url,
        storage_root=tmp_path / "storage",
        max_document_bytes=1024,
    )
    worker = Worker(config, worker_id="lineage-test-worker")
    creator_id = uuid4()
    shared = "Bu ortak belge normalize fingerprint kontrolu icin yeterince uzun bir metindir."

    def create_source(unique_text: str, parent_id: UUID | None = None) -> tuple[UUID, str]:
        content = f"{shared}\n{unique_text}\n".encode("utf-8")
        stored = worker.store.ingest_bytes(content)
        source_id = uuid4()
        with psycopg.connect(lineage_database_url) as connection:
            connection.execute(
                """
                INSERT INTO storage_objects(sha256, storage_key, byte_size)
                VALUES (%s, %s, %s)
                ON CONFLICT (sha256) DO NOTHING
                """,
                (stored.sha256, stored.storage_key, stored.byte_size),
            )
            connection.execute(
                """
                INSERT INTO sources(
                    id, object_sha256, derived_from_source_id, created_by
                )
                VALUES (%s, %s, %s, %s)
                """,
                (source_id, stored.sha256, parent_id, creator_id),
            )
        return source_id, stored.sha256

    def fingerprint(source_id: UUID, object_sha256: str):
        job_id = uuid4()
        with psycopg.connect(lineage_database_url) as connection:
            connection.execute(
                """
                INSERT INTO background_jobs(
                    id, job_type, payload, status, attempts, max_attempts,
                    locked_by, created_by
                )
                VALUES (
                    %s, 'index_document_fingerprints',
                    jsonb_build_object('source_id', %s::text, 'object_sha256', %s::text),
                    'running', 1, 3, %s, %s
                )
                """,
                (job_id, str(source_id), object_sha256, worker.worker_id, creator_id),
            )
        job = Job(
            job_id,
            "index_document_fingerprints",
            {"source_id": str(source_id), "object_sha256": object_sha256},
            1,
            3,
            worker.worker_id,
        )
        with psycopg.connect(lineage_database_url) as connection:
            result = worker._index_document_fingerprints(connection, job)
        with psycopg.connect(lineage_database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT result FROM background_jobs WHERE id = %s", (job_id,)
            ).fetchone()
        return result, row["result"]

    raw_id, raw_sha = create_source(
        "Ham kaynakta kalan ve diger turevlerde bulunmayan yeterince uzun satir."
    )
    (raw_result, raw_audit) = fingerprint(raw_id, raw_sha)
    assert raw_result == ("unique", 0, 0)
    assert raw_audit["lineage_excluded_source_ids"] == []

    v1_id, v1_sha = create_source(
        "Birinci temiz aday icin ozgun ve yeterince uzun ikinci satir.", raw_id
    )
    (v1_result, v1_audit) = fingerprint(v1_id, v1_sha)
    assert v1_result == ("unique", 0, 0)
    assert set(v1_audit["lineage_excluded_source_ids"]) == {str(raw_id)}

    v2_id, v2_sha = create_source(
        "Ikinci temiz aday icin ozgun ve yeterince uzun ikinci satir.", v1_id
    )
    (v2_result, v2_audit) = fingerprint(v2_id, v2_sha)
    assert v2_result == ("unique", 0, 0)
    assert set(v2_audit["lineage_excluded_source_ids"]) == {
        str(raw_id),
        str(v1_id),
    }

    unrelated_id, unrelated_sha = create_source(
        "Iliskisiz kaynak icin ozgun ve yeterince uzun ikinci satir."
    )
    (unrelated_result, unrelated_audit) = fingerprint(unrelated_id, unrelated_sha)
    assert unrelated_result == ("duplicates_found", 1, 3)
    assert unrelated_audit["lineage_excluded_source_ids"] == []
