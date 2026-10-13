"""TASK-043 - purge_sources: gercek migration'larla kurulmus izole semada.

Fixture: 3 kaynak ve 1 frozen release.
- A "Kalacak Kaynak": plan disi, korunur; nesnesi B ile PAYLASILIR.
- B "Silinecek Paylasimli": nesnesi A ile ayni; belgesi, incelemesi, ornek
  nesli, PII taramasi, parmak izi, kaynak incelemesi ve isi var.
- C "Silinecek Turev": B'den turemis (derived_from + soy girdisi), kendi
  nesnesi, belgesi ve sonucu JSON'da bir manifest nesnesi anan isi var.
- R1 frozen release: A'yi icerir; manifest ve hazir bir export'u var.

Fixture satirlari session_replication_role=replica ile yazilir (var olan veri
gibi; dogrulama tetikleyicilerinden gecirmek bu testin konusu degil). Silme
ise normal rolde kosar: append-only/frozen tetikleyicileri ve FK'lar aciktir.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import time
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

from derlem_worker import purge_sources
from derlem_worker.purge_sources import load_plan, main

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "internal" / "database" / "migrations"


@pytest.fixture(scope="module")
def migrated_url(test_database_url: str, isolated_schema_name):
    schema = isolated_schema_name("purge_sources")
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
        print(f"[purge] migrated {schema} in {time.perf_counter() - started:.1f}s")
        yield url
    finally:
        with psycopg.connect(test_database_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture()
def world(migrated_url: str, tmp_path: Path):
    """Her test icin bos tablolar + taze fixture satirlari ve dosyalari."""
    store = tmp_path / "storage"
    with psycopg.connect(migrated_url, autocommit=True) as connection:
        connection.execute("SET session_replication_role = replica")
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
                "AND tablename NOT IN ('schema_migrations', 'contract_spec_artifacts', 'data_policy_versions', "
                "'data_profile_versions', 'data_profile_purposes', 'export_contract_versions', "
                "'profile_purpose_contract_versions', 'review_protocol_versions', 'review_rubric_versions', 'roles')"
            )
        ]
        connection.execute(
            sql.SQL("TRUNCATE {} RESTART IDENTITY").format(sql.SQL(", ").join(sql.Identifier(t) for t in tables))
        )
        ids = _seed(connection, store)
    return {"url": migrated_url, "store": store, "tmp": tmp_path, **ids}


def _object(connection, store: Path, label: str) -> str:
    content = f"derlem purge fixture: {label}\n".encode("utf-8")
    sha = hashlib.sha256(content).hexdigest()
    key = f"objects/sha256/{sha[:2]}/{sha[2:4]}/{sha}"
    path = store / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    connection.execute(
        "INSERT INTO storage_objects(sha256, storage_key, byte_size) VALUES (%s, %s, %s)",
        (sha, key, len(content)),
    )
    return sha


def _seed(connection, store: Path) -> dict:
    user = uuid4()
    connection.execute(
        "INSERT INTO users(id, email, password_hash, display_name) VALUES (%s, 'purge@derlem.local', 'x', 'Purge')",
        (user,),
    )
    obj = {label: _object(connection, store, label) for label in (
        "shared", "a_doc", "b_doc", "c_src", "c_doc", "c_json", "r_manifest", "r_export", "r_export_manifest",
    )}
    a, b, c = uuid4(), uuid4(), uuid4()

    def source(source_id, name, sha, **extra):
        columns = {
            "id": source_id, "name": name, "source_type": "jsonl", "content_purpose": "instruction",
            "license": "internal-test", "language": "tr", "domain": "test", "lineage_ref": "fixture",
            "object_sha256": sha, "created_by": user, **extra,
        }
        connection.execute(
            sql.SQL("INSERT INTO sources ({}) VALUES ({})").format(
                sql.SQL(", ").join(sql.Identifier(k) for k in columns),
                sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            ),
            list(columns.values()),
        )

    source(a, "Kalacak Kaynak", obj["shared"])
    source(b, "Silinecek Paylasimli", obj["shared"], duplicate_status="duplicate", duplicate_of_source_id=a)
    source(c, "Silinecek Turev", obj["c_src"], derived_from_source_id=b)
    connection.execute("INSERT INTO source_lineage_inputs(source_id, input_source_id) VALUES (%s, %s)", (c, b))

    jobs = {}
    for label, job_type, payload, result in (
        ("a", "sample_documents", {"source_id": str(a), "object_sha256": obj["shared"]}, {}),
        ("b", "sample_documents", {"source_id": str(b), "object_sha256": obj["shared"]}, {}),
        ("c", "distill_source", {"source_id": str(c)}, {"manifest_sha256": obj["c_json"]}),
    ):
        jobs[label] = uuid4()
        connection.execute(
            "INSERT INTO background_jobs(id, job_type, status, payload, result, created_by) "
            "VALUES (%s, %s, 'succeeded', %s::jsonb, %s::jsonb, %s)",
            (jobs[label], job_type, json.dumps(payload), json.dumps(result), user),
        )
    docs = {}
    for label, source_id, sha in (("a", a, obj["a_doc"]), ("b", b, obj["b_doc"]), ("c", c, obj["c_doc"])):
        docs[label] = uuid4()
        connection.execute(
            "INSERT INTO documents(id, source_id, source_ordinal, current_object_sha256, text_preview, byte_size, "
            "char_count) VALUES (%s, %s, 1, %s, 'onizleme', 10, 10)",
            (docs[label], source_id, sha),
        )
        connection.execute(
            "INSERT INTO document_versions(document_id, version, object_sha256, byte_size, char_count, actor_type) "
            "VALUES (%s, 1, %s, 10, 10, 'system')",
            (docs[label], sha),
        )
    for label, source_id in (("a", a), ("b", b)):
        connection.execute(
            "INSERT INTO document_sample_generations(source_id, generation, source_sha256, sampling_method, status, "
            "sample_count, job_id) VALUES (%s, 1, %s, 'reservoir-sha256-v1', 'active', 1, %s)",
            (source_id, obj["shared"], jobs[label]),
        )
        connection.execute(
            "INSERT INTO document_sample_memberships(source_id, generation, document_id, source_ordinal, "
            "object_sha256, risk_score, document_version) VALUES (%s, 1, %s, 1, %s, 0, 1)",
            (source_id, docs[label], obj[f"{label}_doc"]),
        )
        connection.execute(
            "INSERT INTO pii_scans(source_id, job_id, object_sha256, scanner_version, status) "
            "VALUES (%s, %s, %s, 'v1', 'clear')",
            (source_id, jobs[label], obj["shared"]),
        )
    review = uuid4()
    connection.execute(
        "INSERT INTO document_reviews(id, document_id, reviewer_id, decision, quality_score, document_version, "
        "object_sha256, rubric_version) VALUES (%s, %s, %s, 'approved', 4, 1, %s, 'overall-v1')",
        (review, docs["b"], user, obj["b_doc"]),
    )
    connection.execute(
        "INSERT INTO active_document_reviews(review_id, document_id, document_version, reviewer_id) "
        "VALUES (%s, %s, 1, %s)",
        (review, docs["b"], user),
    )
    connection.execute(
        "INSERT INTO reviews(source_id, reviewer_id, decision) VALUES (%s, %s, 'approved')", (b, user)
    )
    for source_id, sha in ((a, obj["shared"]), (b, obj["shared"]), (c, obj["c_src"])):
        connection.execute(
            "INSERT INTO document_fingerprints(source_id, source_sha256, source_ordinal, normalized_sha256, "
            "normalized_char_count) VALUES (%s, %s, 1, %s, 10)",
            (source_id, sha, hashlib.sha256(sha.encode()).hexdigest()),
        )
    release = uuid4()
    connection.execute(
        "INSERT INTO releases(id, name, version, content_purpose, status, manifest_object_sha256, manifest_sha256, "
        "created_by, frozen_by, frozen_at, contract_snapshot_status) "
        "VALUES (%s, 'Test Release', 'v1', 'instruction', 'frozen', %s, %s, %s, %s, now(), 'absent_pre_registry')",
        (release, obj["r_manifest"], obj["r_manifest"], user, user),
    )
    connection.execute(
        "INSERT INTO release_sources(release_id, source_id, source_sha256, source_version, source_name, source_type, "
        "license, rights_status, language, domain, lineage_ref) "
        "VALUES (%s, %s, %s, 1, 'Kalacak Kaynak', 'jsonl', 'internal-test', 'cleared', 'tr', 'test', 'fixture')",
        (release, a, obj["shared"]),
    )
    connection.execute(
        "INSERT INTO release_exports(release_id, format, status, object_sha256, manifest_object_sha256, record_count, "
        "byte_size, created_by, completed_at) VALUES (%s, 'jsonl', 'ready', %s, %s, 1, 10, %s, now())",
        (release, obj["r_export"], obj["r_export_manifest"], user),
    )
    jobs["r"] = uuid4()
    connection.execute(
        "INSERT INTO background_jobs(id, job_type, status, payload, created_by) "
        "VALUES (%s, 'freeze_release', 'succeeded', %s::jsonb, %s)",
        (jobs["r"], json.dumps({"release_id": str(release)}), user),
    )
    return {"user": user, "a": a, "b": b, "c": c, "release": release, "obj": obj, "jobs": jobs, "docs": docs}


def _plan(world: dict, path: Path, *, sources=None, releases=None, keep=None) -> Path:
    document = {
        "schema_version": "derlem.purge-plan.v1",
        "plan_id": "test-plan",
        "approved_by": "kurucu, test",
        "reason": "test temizligi",
        "sources": sources if sources is not None else [
            {"id": str(world["b"]), "name": "Silinecek Paylasimli"},
            {"id": str(world["c"]), "name": "Silinecek Turev"},
        ],
        "releases": releases if releases is not None else [
            {"id": str(world["release"]), "name": "Test Release", "version": "v1", "status": "frozen"},
        ],
        "keep_sources": keep if keep is not None else [{"id": str(world["a"]), "name": "Kalacak Kaynak"}],
    }
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def _run(world: dict, plan: Path, *extra: str) -> tuple[int, str]:
    report = world["tmp"] / f"report-{uuid4().hex[:6]}.txt"
    code = main([
        "--plan", str(plan), "--database-url", world["url"], "--storage-root", str(world["store"]),
        "--env-file", str(world["tmp"] / "no.env"), "--log", str(world["tmp"] / "purged_objects.jsonl"),
        "--report", str(report), *extra,
    ])
    return code, report.read_text(encoding="utf-8")


def _snapshot(world: dict) -> dict:
    state = {}
    with psycopg.connect(world["url"]) as connection:
        tables = [row[0] for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() ORDER BY 1"
        )]
        for table in tables:
            state[table] = connection.execute(
                sql.SQL("SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM {} AS t")
                .format(sql.Identifier(table))
            ).fetchone()
        state["__triggers__"] = connection.execute(
            "SELECT string_agg(tgname::text || tgenabled::text, ',' ORDER BY tgname) FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid WHERE c.relnamespace = "
            "(SELECT oid FROM pg_namespace WHERE nspname = current_schema())"
        ).fetchone()
    state["__files__"] = sorted(p.relative_to(world["store"]).as_posix() for p in world["store"].rglob("*") if p.is_file())
    return state


def _count(world: dict, query: str, *params) -> int:
    with psycopg.connect(world["url"]) as connection:
        return int(connection.execute(query, params).fetchone()[0])


def test_dry_run_changes_nothing_and_reports_the_plan(world: dict) -> None:
    before = _snapshot(world)
    code, report = _run(world, _plan(world, world["tmp"] / "plan.json"))
    assert code == 0, report
    assert _snapshot(world) == before
    assert not (world["tmp"] / "purged_objects.jsonl").exists()
    obj = world["obj"]
    assert "DRY-RUN" in report and "ROLLBACK" in report
    for label in ("b_doc", "c_src", "c_doc", "c_json", "r_manifest", "r_export", "r_export_manifest"):
        assert f"\n{obj[label]} | " in report, label
    assert f"\n{obj['shared']} | " not in report
    kept_section = report.split("## KALACAK paylasilan nesneler", 1)[1]
    assert obj["shared"] in kept_section and "sources.object_sha256" in kept_section
    assert "| sources | 2 |" in report and "| documents | 2 |" in report and "| releases | 1 |" in report
    assert "| background_jobs | 3 |" in report and "| storage_objects | 7 |" in report


def test_execute_purges_plan_keeps_shared_object_and_records_everything(
    world: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Gecici indeks yolunu da kostur (canlida document_fingerprints icin gerekir).
    monkeypatch.setattr(purge_sources, "TEMP_INDEX_MIN_ROWS", 0)
    quarantine = world["tmp"] / "quarantine"
    code, report = _run(world, _plan(world, world["tmp"] / "plan.json"), "--execute", "--quarantine-dir", str(quarantine))
    assert code == 0, report
    obj, url = world["obj"], world["url"]
    purged = sorted(obj[label] for label in (
        "b_doc", "c_src", "c_doc", "c_json", "r_manifest", "r_export", "r_export_manifest"))

    # Plan kayitlari ve bagli her satir gitti.
    for table, column, value in (
        ("sources", "id", world["b"]), ("sources", "id", world["c"]), ("releases", "id", world["release"]),
        ("documents", "source_id", world["b"]), ("documents", "source_id", world["c"]),
        ("document_fingerprints", "source_id", world["b"]), ("pii_scans", "source_id", world["b"]),
        ("reviews", "source_id", world["b"]), ("document_sample_generations", "source_id", world["b"]),
        ("document_sample_memberships", "source_id", world["b"]), ("source_lineage_inputs", "source_id", world["c"]),
        ("release_sources", "release_id", world["release"]), ("release_exports", "release_id", world["release"]),
        ("background_jobs", "id", world["jobs"]["b"]), ("background_jobs", "id", world["jobs"]["c"]),
        ("background_jobs", "id", world["jobs"]["r"]),
    ):
        assert _count(world, f"SELECT count(*) FROM {table} WHERE {column} = %s", value) == 0, (table, value)
    assert _count(world, "SELECT count(*) FROM document_reviews") == 0
    assert _count(world, "SELECT count(*) FROM active_document_reviews") == 0

    # Plan disi kaynak A ve her satiri yerinde.
    a = world["a"]
    for table, column in (
        ("sources", "id"), ("documents", "source_id"), ("document_fingerprints", "source_id"),
        ("pii_scans", "source_id"), ("document_sample_generations", "source_id"),
        ("document_sample_memberships", "source_id"),
    ):
        assert _count(world, f"SELECT count(*) FROM {table} WHERE {column} = %s", a) == 1, table
    assert _count(world, "SELECT count(*) FROM background_jobs WHERE id = %s", world["jobs"]["a"]) == 1
    assert _count(world, "SELECT count(*) FROM document_versions") == 1

    # Paylasilan nesne: satir da dosya da kalir; A'nin belge nesnesi de.
    for label in ("shared", "a_doc"):
        sha = obj[label]
        assert _count(world, "SELECT count(*) FROM storage_objects WHERE sha256 = %s", sha) == 1
        assert (world["store"] / "objects" / "sha256" / sha[:2] / sha[2:4] / sha).is_file()
        assert not (quarantine / "sha256" / sha[:2] / sha[2:4] / sha).exists()
    # Silinenler: satir yok, dosya depoda yok, karantinada var (silinmedi, tasindi).
    for sha in purged:
        assert _count(world, "SELECT count(*) FROM storage_objects WHERE sha256 = %s", sha) == 0
        assert not (world["store"] / "objects" / "sha256" / sha[:2] / sha[2:4] / sha).exists()
        moved = quarantine / "sha256" / sha[:2] / sha[2:4] / sha
        assert hashlib.sha256(moved.read_bytes()).hexdigest() == sha

    # Silme gunlugu: deterministik sira, beklenen alanlar.
    lines = (world["tmp"] / "purged_objects.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [r["sha256"] for r in records] == purged
    by_sha = {r["sha256"]: r for r in records}
    assert by_sha[obj["c_src"]]["source_ids"] == [str(world["c"])]
    assert by_sha[obj["r_export"]]["release_ids"] == [str(world["release"])]
    assert by_sha[obj["r_export"]]["manifest_sha256"] == obj["r_export_manifest"]
    assert by_sha[obj["c_json"]]["source_ids"] == [str(world["c"])]
    assert all(r["approved_by"] == "kurucu, test" and r["reason"] == "test temizligi" for r in records)
    assert all(r["quarantined"] is True and r["purged_at"].endswith("Z") for r in records)

    # Audit satiri ve row_change_events izleri.
    with psycopg.connect(url) as connection:
        audit = connection.execute(
            "SELECT actor_type, details FROM audit_events WHERE action = 'sources_purged'"
        ).fetchall()
        assert len(audit) == 1
        details = audit[0][1]
        assert details["actor"] == "kurucu, test"
        assert details["deleted_rows"]["sources"] == 2
        assert details["purged_objects"]["count"] == 7
        assert [k["sha256"] for k in details["kept_shared_objects"]] == [obj["shared"]]
        assert connection.execute(
            "SELECT count(*) FROM row_change_events WHERE operation = 'DELETE' AND table_name = 'sources'"
        ).fetchone()[0] == 2
        # Koruma tetikleyicileri yeniden acik; gecici indeks kalmadi.
        assert connection.execute(
            "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid WHERE NOT t.tgisinternal "
            "AND t.tgenabled <> 'O' AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM pg_indexes WHERE schemaname = current_schema() AND indexname LIKE 'purge_tmp_%%'"
        ).fetchone()[0] == 0
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            connection.execute("DELETE FROM storage_objects WHERE sha256 = %s", (obj["shared"],))


@pytest.mark.parametrize("case", ["unknown_source", "wrong_name", "unknown_release", "frozen_not_acknowledged"])
def test_unresolvable_plan_changes_nothing(world: dict, case: str) -> None:
    sources = [
        {"id": str(world["b"]), "name": "Silinecek Paylasimli"},
        {"id": str(world["c"]), "name": "Silinecek Turev"},
    ]
    releases = [{"id": str(world["release"]), "name": "Test Release", "version": "v1", "status": "frozen"}]
    if case == "unknown_source":
        sources.append({"id": str(uuid4()), "name": "Hayalet"})
    elif case == "wrong_name":
        sources[0]["name"] = "Baska Ad"
    elif case == "unknown_release":
        releases.append({"id": str(uuid4()), "name": "Hayalet", "version": "v0", "status": "frozen"})
    else:
        releases[0]["status"] = "draft"
    before = _snapshot(world)
    plan = _plan(world, world["tmp"] / "plan.json", sources=sources, releases=releases)
    quarantine = world["tmp"] / "quarantine"
    code, report = _run(world, plan, "--execute", "--quarantine-dir", str(quarantine))
    assert code == 1
    assert "SORUNLAR" in report and "REDDEDILDI" in report
    assert _snapshot(world) == before
    assert not quarantine.exists()
    assert not (world["tmp"] / "purged_objects.jsonl").exists()


@pytest.mark.parametrize("case", ["derived_child_outside_plan", "release_outside_plan"])
def test_reference_from_outside_the_plan_stops_everything(world: dict, case: str) -> None:
    if case == "derived_child_outside_plan":
        # B silinmek isteniyor ama C (B'den turemis, soy girdisi B) planda degil.
        sources = [{"id": str(world["b"]), "name": "Silinecek Paylasimli"}]
        expected = ("sources(derived_from_source_id)", "source_lineage_inputs(input_source_id)")
        releases = [{"id": str(world["release"]), "name": "Test Release", "version": "v1", "status": "frozen"}]
        keep = None
    else:
        # A silinmek isteniyor ama A'yi iceren frozen R1 planda degil.
        sources = [
            {"id": str(world["a"]), "name": "Kalacak Kaynak"},
            {"id": str(world["b"]), "name": "Silinecek Paylasimli"},
            {"id": str(world["c"]), "name": "Silinecek Turev"},
        ]
        expected = ("release_sources(source_id)",)
        releases, keep = [], []
    before = _snapshot(world)
    plan = _plan(world, world["tmp"] / "plan.json", sources=sources, releases=releases, keep=keep)
    code, report = _run(world, plan, "--execute", "--quarantine-dir", str(world["tmp"] / "quarantine"))
    assert code == 1, report
    for fragment in expected:
        assert f"plan disi referans: {fragment}" in report
    assert _snapshot(world) == before


def test_plan_loader_rejects_overlapping_keep_and_delete(world: dict) -> None:
    plan = _plan(
        world, world["tmp"] / "plan.json",
        keep=[{"id": str(world["b"]), "name": "Silinecek Paylasimli"}],
    )
    with pytest.raises(ValueError, match="hem silinecek hem kalacak"):
        load_plan(plan)


def test_execute_requires_quarantine_dir(world: dict) -> None:
    with pytest.raises(SystemExit):
        main(["--plan", str(_plan(world, world["tmp"] / "plan.json")), "--execute",
              "--database-url", world["url"], "--env-file", str(world["tmp"] / "no.env")])
