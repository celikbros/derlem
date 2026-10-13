"""TASK-043 - restore tatbikatinin zincir kontrolu ve deploy/purged_objects.jsonl.

Kasitli silinmis (purge_sources gunlugundeki) bir nesne, silmeden ONCE
alinmis bir yedekte eksikse sorun sayilmaz; listede olmayan eksik nesne,
listede olup silmeden SONRAKI katalogda hala gorunen nesne ve listede
olmayan eksik frozen manifest yine sorundur.
"""
from __future__ import annotations

from datetime import datetime, UTC
import hashlib
import importlib
import json
from pathlib import Path
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PURGED_AT = "2026-10-13T12:00:00Z"
BEFORE_PURGE = datetime(2026, 10, 12, tzinfo=UTC)
AFTER_PURGE = datetime(2026, 10, 14, tzinfo=UTC)


@pytest.fixture(scope="module")
def drill():
    sys.path.insert(0, str(REPO_ROOT / "deploy" / "scripts"))
    try:
        yield importlib.import_module("derlem_restore_drill")
    finally:
        sys.path.remove(str(REPO_ROOT / "deploy" / "scripts"))


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


@pytest.fixture()
def catalog(test_database_url: str, isolated_schema_name, tmp_path: Path):
    """Tatbikatin okudugu iki tablo: storage_objects ve releases (yalniz okunan kolonlar)."""
    schema = isolated_schema_name("restore_drill_purged")
    with psycopg.connect(test_database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    settings = conninfo_to_dict(test_database_url)
    settings["options"] = f"-c search_path={schema}"
    url = make_conninfo(**settings)
    present, purged_object, purged_manifest = _sha("present"), _sha("purged-object"), _sha("purged-manifest")
    backup_objects = tmp_path / "objects"
    target = backup_objects / "sha256" / present[:2] / present[2:4] / present
    target.parent.mkdir(parents=True)
    target.write_bytes(b"present")
    try:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute("CREATE TABLE storage_objects (sha256 text PRIMARY KEY)")
            connection.execute("CREATE TABLE releases (name text, version text, manifest_object_sha256 text)")
            for digest in (present, purged_object, purged_manifest):
                connection.execute("INSERT INTO storage_objects VALUES (%s)", (digest,))
            connection.execute("INSERT INTO releases VALUES ('Smoke', 'v1', %s)", (purged_manifest,))
        yield {
            "url": url, "objects": backup_objects, "tmp": tmp_path,
            "purged_object": purged_object, "purged_manifest": purged_manifest,
        }
    finally:
        with psycopg.connect(test_database_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def _log(path: Path, shas: list[str]) -> Path:
    lines = [json.dumps({"sha256": sha, "purged_at": PURGED_AT, "byte_size": 1}) for sha in sorted(shas)]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def test_purged_objects_are_intentional_in_a_pre_purge_backup(drill, catalog) -> None:
    purged = drill.load_purged(_log(catalog["tmp"] / "purged.jsonl",
                                    [catalog["purged_object"], catalog["purged_manifest"]]))
    referenced, known_lost_hits, purged_hits, problems = drill.verify_catalog_chain(
        catalog["url"], catalog["objects"], set(), purged, BEFORE_PURGE
    )
    assert problems == []
    assert (referenced, known_lost_hits, purged_hits) == (3, 0, 2)


def test_sha_removed_from_the_list_turns_the_drill_red(drill, catalog) -> None:
    # Kontrol kosusu: listeden bir SHA cikarilinca tatbikat kirmiziya doner.
    purged = drill.load_purged(_log(catalog["tmp"] / "purged.jsonl", [catalog["purged_manifest"]]))
    _, _, purged_hits, problems = drill.verify_catalog_chain(
        catalog["url"], catalog["objects"], set(), purged, BEFORE_PURGE
    )
    assert purged_hits == 1
    assert problems == [f"katalog nesnesi yedekte yok: {catalog['purged_object']}"]


def test_unlisted_missing_frozen_manifest_is_still_a_problem(drill, catalog) -> None:
    purged = drill.load_purged(_log(catalog["tmp"] / "purged.jsonl", [catalog["purged_object"]]))
    _, _, _, problems = drill.verify_catalog_chain(catalog["url"], catalog["objects"], set(), purged, BEFORE_PURGE)
    assert f"katalog nesnesi yedekte yok: {catalog['purged_manifest']}" in problems
    assert f"frozen manifest nesnesi yedekte yok: Smoke-v1 {catalog['purged_manifest']}" in problems


def test_purged_object_still_in_a_post_purge_catalog_is_a_problem(drill, catalog) -> None:
    purged = drill.load_purged(_log(catalog["tmp"] / "purged.jsonl",
                                    [catalog["purged_object"], catalog["purged_manifest"]]))
    _, _, purged_hits, problems = drill.verify_catalog_chain(
        catalog["url"], catalog["objects"], set(), purged, AFTER_PURGE
    )
    assert purged_hits == 0
    assert len(problems) == 3
    assert all("silmeden sonraki katalogda" in p or "frozen manifest" in p for p in problems)


def test_missing_or_corrupt_log(drill, tmp_path: Path) -> None:
    assert drill.load_purged(tmp_path / "absent.jsonl") == {}
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"sha256": "xyz", "purged_at": "2026-10-13T12:00:00Z"}\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="gecersiz sha256"):
        drill.load_purged(bad)
    bad.write_text("not json\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="bozuk silme kaydi"):
        drill.load_purged(bad)
