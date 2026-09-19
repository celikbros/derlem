"""TASK-018 — pretrain freeze → txt/jsonl export provasinin Python yarisi.

Go yarisi (internal/repository/pretrain_rehearsal_integration_test.go) 100k
dilimi pretrain/holdout kaynak olarak eker, taslagi Releases.Create ile acar
(sozlesme anlik goruntusu DB'de turetilir) ve QueueFreeze ile freeze_release
isini kuyruga alir; sonuc satirlarini fixtures/pretrain_rehearsal/ altina
yazar. Bu dosya ayni satirlari TAZE bir semaya (gercek migration'lar) yukler
ve worker'i surec icinde kosturur: freeze_release, sonra txt ve jsonl
export_release. Iki yari ayri sureclerdir; onlari fixture baglar.

Sapma testi: fixture'daki anlik goruntu satirlari yuklenirken DB
tetikleyicileri (release_source_contract_snapshots_validate ve releases'in
pending -> present gecisi) anlik goruntuyu guncel sozlesme kayit defterine
karsi yeniden turetir. Kayit defteri degisirse yukleme kirmizi olur; bu
dosyadaki iki negatif test bozuk bir fixture'in gercekten reddedildigini
kanitlar.

Dilim metni git'e girmez (203 MB). Varsayilan yeri var/olcum-2026-09-17;
DERLEM_PRETRAIN_SLICE_DIR ile degistirilir. Dilim yoksa test ACIKCA atlanir;
dilim varsa ama SHA-256'si fixture'dakinden farkliysa test kirmizi olur.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from derlem_worker.jobs import Worker

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pretrain_rehearsal" / "slice100k.fixture.json"
MIGRATIONS_DIR = REPO_ROOT / "internal" / "database" / "migrations"
SLICE_DIR_ENV = "DERLEM_PRETRAIN_SLICE_DIR"
DEFAULT_SLICE_DIR = REPO_ROOT / "var" / "olcum-2026-09-17"
MEGABYTE = 1_000_000


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="module")
def rehearsal_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.fail(
            f"{FIXTURE_PATH} is missing; generate it with "
            "DERLEM_UPDATE_GOLDEN=1 go test ./internal/repository/ -run TestPretrainRehearsal",
            pytrace=False,
        )
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "derlem.pretrain-rehearsal-fixture.v1"
    return fixture


@pytest.fixture(scope="module")
def slice_paths(rehearsal_fixture: dict) -> dict[str, Path]:
    slice_dir = Path(os.environ.get(SLICE_DIR_ENV, "").strip() or DEFAULT_SLICE_DIR)
    paths = {
        "candidate": slice_dir / rehearsal_fixture["slice"]["candidate"]["file"],
        "holdout": slice_dir / rehearsal_fixture["slice"]["holdout"]["file"],
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        pytest.skip(
            "100k slice is not available (the slice text is not committed): "
            f"{missing}. Point {SLICE_DIR_ENV} at a directory holding it to run the rehearsal."
        )
    for key, path in paths.items():
        expected = rehearsal_fixture["slice"][key]["sha256"]
        actual = _sha256_of(path)
        assert actual == expected, (
            f"{path} sha256={actual} differs from the fixture ({expected}); the Go half and "
            "the Python half must see the same slice bytes (regenerate the fixture)"
        )
    return paths


@pytest.fixture(scope="session")
def migrated_schema(test_database_url: str, isolated_schema_name):
    """Gercek Go migration dosyalarini (internal/database/migrations) izole bir
    semaya uygular; Go tarafindaki newReleaseContractTestPool ile ayni kurallar:
    pgcrypto once public'te olusturulur ki DROP SCHEMA ... CASCADE eklentiyi
    veritabaninin tamamindan silmesin."""

    @contextmanager
    def make(label: str):
        schema = isolated_schema_name(label)
        with psycopg.connect(test_database_url, autocommit=True) as admin:
            admin.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        settings = conninfo_to_dict(test_database_url)
        settings["options"] = f"-c search_path={schema}"
        url = make_conninfo(**settings)
        try:
            started = time.perf_counter()
            with psycopg.connect(url) as connection:
                for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                    with connection.transaction():
                        connection.execute(path.read_text(encoding="utf-8"))
            print(f"[rehearsal] migrated {schema} in {time.perf_counter() - started:.1f}s")
            yield url
        finally:
            with psycopg.connect(test_database_url, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
                )

    return make


def _insert_row(connection: psycopg.Connection, table: str, row: dict) -> None:
    connection.execute(
        sql.SQL("INSERT INTO {table} SELECT * FROM jsonb_populate_record(NULL::{table}, %s::jsonb)").format(
            table=sql.Identifier(table)
        ),
        (Jsonb(row),),
    )


def load_fixture_rows(connection: psycopg.Connection, fixture: dict) -> None:
    """Go'nun urettigi satirlari yabanci anahtar sirasiyla yukler.

    releases satiri DB kuralina gore 'pending' baslar; anlik goruntuler
    yuklendikten sonra 'present'e gecirilir ve o gecisde tetikleyici paket
    SHA'sini cocuk anlik goruntulerden yeniden turetip fixture'daki degerle
    karsilastirir. Uydurma ya da eskimis bir anlik goruntu burada durur.
    """
    tables = fixture["tables"]
    for table in fixture["table_order"]:
        for row in tables[table]:
            if table == "releases":
                pending = dict(
                    row,
                    contract_snapshot_status="pending",
                    contract_snapshot_artifact_kind=None,
                    contract_snapshot_sha256=None,
                    implementation_bundle_sha256=None,
                )
                _insert_row(connection, table, pending)
                continue
            _insert_row(connection, table, row)
        if table == "release_source_contract_snapshots":
            for row in tables["releases"]:
                connection.execute(
                    """
                    UPDATE releases
                    SET contract_snapshot_status = 'present',
                        contract_snapshot_artifact_kind = %s,
                        contract_snapshot_sha256 = %s,
                        implementation_bundle_sha256 = %s
                    WHERE id = %s AND status = 'draft' AND contract_snapshot_status = 'pending'
                    """,
                    (
                        row["contract_snapshot_artifact_kind"],
                        row["contract_snapshot_sha256"],
                        row["implementation_bundle_sha256"],
                        row["id"],
                    ),
                )


def make_worker(database_url: str, root: Path) -> Worker:
    config = SimpleNamespace(
        database_url=database_url,
        storage_root=(root / "store").resolve(),
        staging_root=(root / "staging").resolve(),
        import_root=(root / "import").resolve(),
        lease_timeout_seconds=1800.0,
        heartbeat_interval_seconds=10.0,
        poll_interval_seconds=0.01,
        max_document_bytes=256 * 1024,
    )
    config.staging_root.mkdir(parents=True, exist_ok=True)
    config.import_root.mkdir(parents=True, exist_ok=True)
    return Worker(config, worker_id="pretrain-rehearsal")


def _job_row(database_url: str, job_id: str) -> dict:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return connection.execute(
            "SELECT status, last_error, result FROM background_jobs WHERE id = %s", (job_id,)
        ).fetchone()


def _stored_path(worker: Worker, database_url: str, sha256: str) -> Path:
    with psycopg.connect(database_url) as connection:
        storage_key = connection.execute(
            "SELECT storage_key FROM storage_objects WHERE sha256 = %s", (sha256,)
        ).fetchone()[0]
    return worker.store.root / storage_key


def test_freeze_and_export_the_100k_slice_in_process(
    migrated_schema, rehearsal_fixture: dict, slice_paths: dict[str, Path], tmp_path: Path
) -> None:
    measurements: dict[str, object] = {}
    with migrated_schema("pretrain_rehearsal") as database_url:
        worker = make_worker(database_url, tmp_path)

        # Dilim nesneleri worker'in kendi CAS deposuna alinir; anahtar ve SHA
        # Go'nun yazdigi storage_objects satirlariyla birebir ayni olmali.
        for key in ("candidate", "holdout"):
            started = time.perf_counter()
            stored = worker.store.ingest_file(slice_paths[key])
            elapsed = time.perf_counter() - started
            expected = rehearsal_fixture["slice"][key]
            assert stored.sha256 == expected["sha256"]
            assert stored.storage_key == expected["storage_key"]
            assert stored.byte_size == expected["byte_size"]
            assert stored.line_count == expected["line_count"]
            measurements[f"ingest_{key}_seconds"] = round(elapsed, 3)

        started = time.perf_counter()
        with psycopg.connect(database_url) as connection:
            load_fixture_rows(connection, rehearsal_fixture)
            connection.commit()
        measurements["fixture_load_seconds"] = round(time.perf_counter() - started, 3)

        release_id = rehearsal_fixture["release_id"]
        freeze_job_id = rehearsal_fixture["freeze_job_id"]
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            release = connection.execute(
                "SELECT status, contract_snapshot_status, contract_snapshot_sha256, implementation_bundle_sha256 "
                "FROM releases WHERE id = %s",
                (release_id,),
            ).fetchone()
            job = connection.execute(
                "SELECT job_type, status FROM background_jobs WHERE id = %s", (freeze_job_id,)
            ).fetchone()
        fixture_release = rehearsal_fixture["tables"]["releases"][0]
        assert release["status"] == "draft"
        assert release["contract_snapshot_status"] == "present"
        # DB gecis tetikleyicisi paketi yeniden turetti ve fixture'dakiyle esitledi.
        assert release["contract_snapshot_sha256"] == fixture_release["contract_snapshot_sha256"]
        assert release["implementation_bundle_sha256"] == fixture_release["implementation_bundle_sha256"]
        assert (job["job_type"], job["status"]) == ("freeze_release", "queued")

        # --- freeze_release ---------------------------------------------------
        started = time.perf_counter()
        assert worker.run_once() is True
        freeze_seconds = time.perf_counter() - started
        measurements["freeze_seconds"] = round(freeze_seconds, 3)
        freeze_job = _job_row(database_url, freeze_job_id)
        assert freeze_job["status"] == "succeeded", freeze_job["last_error"]

        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            frozen = connection.execute(
                "SELECT status, manifest_sha256, manifest_object_sha256, gate_results, frozen_by "
                "FROM releases WHERE id = %s",
                (release_id,),
            ).fetchone()
        assert frozen["status"] == "frozen"
        assert str(frozen["frozen_by"]) == rehearsal_fixture["creator_id"]
        gates = frozen["gate_results"]
        assert gates["contract_snapshot"]["status"] == "passed"
        assert gates["contract_snapshot"]["review_document_count"] == rehearsal_fixture["sample_size"]
        assert gates["contract_snapshot"]["contract_snapshot_sha256"] == fixture_release["contract_snapshot_sha256"]
        assert gates["storage_integrity"] == {
            "status": "passed", "source_object_count": 1, "reference_object_count": 1
        }
        # Kart 'exact_decontamination.compared_document_count' der; kodun yazdigi
        # anahtarlar decontamination.reference_document_count / match_count'tur.
        exact = gates["decontamination"]
        assert exact["status"] == "passed"
        assert exact["method"] == "document-text-sha256-v1"
        assert exact["reference_source_count"] == 1
        assert exact["reference_document_count"] == rehearsal_fixture["slice"]["holdout"]["line_count"] == 43
        assert exact["reference_unique_document_count"] == 43
        assert exact["release_document_count"] == rehearsal_fixture["slice"]["candidate"]["line_count"] == 99007
        assert exact["match_count"] == 0
        assert exact["sample_matches"] == []
        approximate = gates["approximate_decontamination"]
        assert approximate["status"] == "reported"
        assert approximate["reference_document_count"] == 43
        assert approximate["release_document_count"] == 99007
        assert gates["near_duplicate_report"]["document_count"] == 99007
        measurements["exact_decontamination"] = {
            key: exact[key]
            for key in ("reference_document_count", "reference_unique_document_count",
                        "release_document_count", "match_count")
        }
        measurements["approximate_decontamination"] = {
            key: approximate[key]
            for key in ("status", "potential_match_count", "release_indexed_count",
                        "skipped_too_short_count", "candidate_overflow_document_count")
        }
        measurements["near_duplicate_report"] = {
            key: gates["near_duplicate_report"][key]
            for key in ("status", "potential_pair_count", "within_source_pair_count",
                        "indexed_document_count", "skipped_too_short_count")
        }

        manifest_path = _stored_path(worker, database_url, frozen["manifest_object_sha256"])
        assert _sha256_of(manifest_path) == frozen["manifest_sha256"] == frozen["manifest_object_sha256"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["schema_version"] == "derlem.release-manifest.v2"
        assert manifest["contract_snapshot"]["sha256"] == fixture_release["contract_snapshot_sha256"]
        assert manifest["gate_results"] == gates
        assert [source["source_sha256"] for source in manifest["sources"]] == [
            rehearsal_fixture["slice"]["candidate"]["sha256"]
        ]
        measurements["release_manifest_sha256"] = frozen["manifest_sha256"]

        # --- export_release: txt, sonra jsonl ---------------------------------
        input_bytes = rehearsal_fixture["slice"]["candidate"]["byte_size"]
        for export_format in ("txt", "jsonl"):
            with psycopg.connect(database_url) as connection:
                export_id = connection.execute(
                    "INSERT INTO release_exports(release_id, format, created_by) VALUES (%s, %s, %s) RETURNING id::text",
                    (release_id, export_format, rehearsal_fixture["creator_id"]),
                ).fetchone()[0]
                export_job_id = connection.execute(
                    """
                    INSERT INTO background_jobs(job_type, priority, payload, created_by)
                    VALUES ('export_release', 60, %s::jsonb, %s::uuid)
                    RETURNING id::text
                    """,
                    (
                        Jsonb({
                            "release_id": release_id, "export_id": export_id,
                            "format": export_format, "requested_by": rehearsal_fixture["creator_id"],
                        }),
                        rehearsal_fixture["creator_id"],
                    ),
                ).fetchone()[0]
                connection.commit()

            started = time.perf_counter()
            assert worker.run_once() is True
            export_seconds = time.perf_counter() - started
            export_job = _job_row(database_url, export_job_id)
            assert export_job["status"] == "succeeded", export_job["last_error"]

            with psycopg.connect(database_url, row_factory=dict_row) as connection:
                export = connection.execute(
                    "SELECT status, object_sha256, manifest_object_sha256, record_count, byte_size, "
                    "estimated_token_count, token_estimate_lower_bound, token_estimate_upper_bound, "
                    "token_estimate_method, record_type_counts FROM release_exports WHERE id = %s",
                    (export_id,),
                ).fetchone()
            assert export["status"] == "ready"
            assert export["record_count"] == 99007
            assert export["token_estimate_method"] == "unicode-codepoint-range-v1"

            artifact_path = _stored_path(worker, database_url, export["object_sha256"])
            recomputed = _sha256_of(artifact_path)
            assert recomputed == export["object_sha256"]
            assert artifact_path.stat().st_size == export["byte_size"]
            export_manifest = json.loads(
                _stored_path(worker, database_url, export["manifest_object_sha256"]).read_text(encoding="utf-8")
            )
            assert export_manifest["schema_version"] == "derlem.export-manifest.v2"
            assert export_manifest["export"]["format"] == export_format
            assert export_manifest["export"]["sha256"] == recomputed
            assert export_manifest["export"]["byte_size"] == export["byte_size"]
            assert export_manifest["export"]["record_count"] == 99007
            assert export_manifest["release"]["manifest_sha256"] == frozen["manifest_sha256"]
            assert export_manifest["sources"][0]["record_count"] == 99007
            measurements[f"export_{export_format}"] = {
                "seconds": round(export_seconds, 3),
                "output_bytes": export["byte_size"],
                "input_mb_per_second": round(input_bytes / MEGABYTE / export_seconds, 2),
                "output_mb_per_second": round(export["byte_size"] / MEGABYTE / export_seconds, 2),
                "artifact_sha256": recomputed,
                "manifest_sha256_matches": export_manifest["export"]["sha256"] == recomputed,
                "estimated_token_count": export["estimated_token_count"],
                "token_estimate_bounds": [
                    export["token_estimate_lower_bound"], export["token_estimate_upper_bound"]
                ],
                "record_type_counts": export["record_type_counts"],
            }

        with psycopg.connect(database_url) as connection:
            ready = connection.execute(
                "SELECT count(*) FROM release_exports WHERE release_id = %s AND status = 'ready'",
                (release_id,),
            ).fetchone()[0]
        assert ready == 2

    measurements["input_bytes"] = input_bytes
    measurements["freeze_input_mb_per_second"] = round(input_bytes / MEGABYTE / freeze_seconds, 2)
    print("[rehearsal] measurements " + json.dumps(measurements, ensure_ascii=False, indent=2))


def _tampered(fixture: dict) -> dict:
    return copy.deepcopy(fixture)


def _flip_last_hex(value: str) -> str:
    return value[:-1] + ("0" if value[-1] != "0" else "1")


def test_drift_stale_source_snapshot_is_rejected_by_the_database(
    migrated_schema, rehearsal_fixture: dict
) -> None:
    """Kayit defteri (profile_purpose_contract_versions) ile fixture'daki cocuk
    anlik goruntu uyusmazsa yukleme ilk satirda durur."""
    fixture = _tampered(rehearsal_fixture)
    snapshot = fixture["tables"]["release_source_contract_snapshots"][0]
    snapshot["implementation_bundle_sha256"] = _flip_last_hex(snapshot["implementation_bundle_sha256"])
    with migrated_schema("pretrain_rehearsal_drift_child") as database_url:
        with psycopg.connect(database_url) as connection:
            with pytest.raises(psycopg.Error, match="does not match purpose contract"):
                load_fixture_rows(connection, fixture)


def test_drift_stale_release_bundle_is_rejected_by_the_database(
    migrated_schema, rehearsal_fixture: dict
) -> None:
    """Cocuklar gecerli ama sürüm seviyesindeki paket SHA'si eskimisse
    pending -> present gecisi yeniden turetilen degerle uyusmadigi icin durur."""
    fixture = _tampered(rehearsal_fixture)
    release = fixture["tables"]["releases"][0]
    release["contract_snapshot_sha256"] = _flip_last_hex(release["contract_snapshot_sha256"])
    with migrated_schema("pretrain_rehearsal_drift_bundle") as database_url:
        with psycopg.connect(database_url) as connection:
            with pytest.raises(psycopg.Error, match="does not match child snapshots"):
                load_fixture_rows(connection, fixture)
