"""Derlem restore tatbikatı.

Verilen yedek kökünden en yeni DB dump'ını ayrı bir tatbikat veritabanına
geri yükler, tablo sayımlarını yedek manifestiyle karşılaştırır ve yedek
aynasındaki HER nesnenin SHA256'sını yeniden hesaplayıp dosya adıyla
doğrular. Ayrıca geri yüklenen katalogdaki her storage_objects kaydının ve
frozen release manifest nesnesinin yedekte bulunduğunu kanıtlar.

Kullanım:
    python deploy/scripts/derlem_restore_drill.py --backup-root D:/DERLEM-BACKUP
    python deploy/scripts/derlem_restore_drill.py --backup-root D:/DERLEM-BACKUP --passphrase-env BACKUP_PASSPHRASE --keep

Çıkış kodu 0 = tatbikat başarılı; herhangi bir tutarsızlıkta 1.
"""

from __future__ import annotations

import argparse
from datetime import datetime, UTC
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit

from derlem_backup import find_pg_tool, load_env, sha256_of


def swap_database(database_url: str, new_database: str) -> str:
    parts = urlsplit(database_url)
    path = "/" + new_database
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def run_sql(psql: str, admin_url: str, sql: str) -> None:
    subprocess.run([psql, "--dbname", admin_url, "--no-psqlrc", "--command", sql], check=True,
                   stdout=subprocess.DEVNULL)


def latest_dump(backup_root: Path) -> tuple[Path, dict[str, object]]:
    manifests = sorted((backup_root / "manifests").glob("backup_*.json"))
    if not manifests:
        raise SystemExit("Yedek manifesti bulunamadı; önce derlem_backup.py çalıştırın.")
    manifest = json.loads(manifests[-1].read_text(encoding="utf-8"))
    dump_file = backup_root / "db" / str(manifest["database_dump"]["file"])
    if not dump_file.exists():
        raise SystemExit(f"Dump dosyası yok: {dump_file}")
    return dump_file, manifest


def restore_dump(dump_file: Path, manifest: dict[str, object], drill_url: str,
                 pg_bin: str | None, passphrase: str | None) -> None:
    pg_restore = find_pg_tool("pg_restore", pg_bin)
    restore_source = dump_file
    temp_plain: Path | None = None
    if manifest["database_dump"].get("encrypted"):
        if not passphrase:
            raise SystemExit("Dump şifreli; --passphrase-env verin.")
        openssl = shutil.which("openssl")
        if not openssl:
            raise SystemExit("openssl bulunamadı.")
        handle, temp_name = tempfile.mkstemp(suffix=".dump")
        os.close(handle)
        temp_plain = Path(temp_name)
        subprocess.run(
            [openssl, "enc", "-d", "-aes-256-cbc", "-pbkdf2",
             "-in", str(dump_file), "-out", str(temp_plain), "-pass", "env:DERLEM_BACKUP_PASS"],
            check=True,
            env={**os.environ, "DERLEM_BACKUP_PASS": passphrase},
        )
        expected = manifest["database_dump"].get("plain_sha256")
        if expected and sha256_of(temp_plain) != expected:
            temp_plain.unlink()
            raise SystemExit("Şifre çözülen dump'ın SHA256'sı manifestle uyuşmuyor.")
        restore_source = temp_plain
    try:
        subprocess.run(
            [pg_restore, "--no-owner", "--no-privileges", "--dbname", drill_url, str(restore_source)],
            check=True,
        )
    finally:
        if temp_plain is not None and temp_plain.exists():
            temp_plain.unlink()


def verify_counts(drill_url: str, expected: dict[str, int]) -> list[str]:
    import psycopg

    problems: list[str] = []
    with psycopg.connect(drill_url) as connection, connection.cursor() as cursor:
        for table, expected_count in expected.items():
            cursor.execute(f"SELECT count(*) FROM {table}")
            actual = int(cursor.fetchone()[0])
            if actual != expected_count:
                problems.append(f"tablo {table}: beklenen {expected_count}, bulunan {actual}")
    return problems


def verify_objects(backup_objects: Path) -> tuple[int, list[str]]:
    problems: list[str] = []
    checked = 0
    for path in sorted(backup_objects.rglob("*")):
        if not path.is_file():
            continue
        checked += 1
        if sha256_of(path) != path.name:
            problems.append(f"bozuk nesne: {path}")
    return checked, problems


def verify_catalog_chain(drill_url: str, backup_objects: Path) -> tuple[int, list[str]]:
    import psycopg

    problems: list[str] = []
    referenced = 0
    with psycopg.connect(drill_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT sha256 FROM storage_objects")
        hashes = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT name, version, manifest_object_sha256 FROM releases WHERE manifest_object_sha256 IS NOT NULL")
        releases = cursor.fetchall()
    for digest in hashes:
        referenced += 1
        candidate = backup_objects / "sha256" / digest[:2] / digest[2:4] / digest
        if not candidate.exists():
            problems.append(f"katalog nesnesi yedekte yok: {digest}")
    for name, version, digest in releases:
        candidate = backup_objects / "sha256" / digest[:2] / digest[2:4] / digest
        if not candidate.exists():
            problems.append(f"frozen manifest nesnesi yedekte yok: {name}-{version} {digest}")
    return referenced, problems


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Derlem restore tatbikatı.")
    parser.add_argument("--backup-root", default=os.environ.get("DERLEM_BACKUP_ROOT"))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--pg-bin", default=os.environ.get("PG_BIN"))
    parser.add_argument("--drill-db", default="derlem_restore_drill")
    parser.add_argument("--passphrase-env", default=None)
    parser.add_argument("--keep", action="store_true", help="Tatbikat veritabanını silme.")
    args = parser.parse_args()

    if not args.backup_root:
        raise SystemExit("--backup-root zorunludur (veya DERLEM_BACKUP_ROOT).")
    backup_root = Path(args.backup_root)

    repo_root = Path(__file__).resolve().parents[2]
    env = load_env(repo_root / args.env_file)
    database_url = env.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL bulunamadı.")

    passphrase = None
    if args.passphrase_env:
        passphrase = os.environ.get(args.passphrase_env)
        if not passphrase:
            raise SystemExit(f"{args.passphrase_env} ortam değişkeni boş.")

    admin_url = swap_database(database_url, "postgres")
    drill_url = swap_database(database_url, args.drill_db)
    psql = find_pg_tool("psql", args.pg_bin)

    dump_file, manifest = latest_dump(backup_root)
    print(f"Tatbikat dump'ı: {dump_file.name}")

    run_sql(psql, admin_url, f'DROP DATABASE IF EXISTS "{args.drill_db}"')
    run_sql(psql, admin_url, f'CREATE DATABASE "{args.drill_db}"')

    started = datetime.now(UTC)
    problems: list[str] = []
    try:
        restore_dump(dump_file, manifest, drill_url, args.pg_bin, passphrase)
        problems += verify_counts(drill_url, dict(manifest.get("table_counts", {})))
        checked_objects, object_problems = verify_objects(backup_root / "objects")
        problems += object_problems
        referenced, chain_problems = verify_catalog_chain(drill_url, backup_root / "objects")
        problems += chain_problems
    finally:
        if not args.keep:
            run_sql(psql, admin_url, f'DROP DATABASE IF EXISTS "{args.drill_db}"')

    report = {
        "schema_version": "derlem.restore-drill-report.v1",
        "backup_manifest": manifest.get("started_at"),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "tables_verified": len(dict(manifest.get("table_counts", {}))),
        "backup_objects_rehashed": checked_objects,
        "catalog_objects_checked": referenced,
        "problems": problems,
        "result": "PASS" if not problems else "FAIL",
    }
    report_path = backup_root / "manifests" / f"restore_drill_{started.strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
