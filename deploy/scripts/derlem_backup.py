"""Derlem yedekleme aracı.

PostgreSQL metadata dump'ı + içerik adresli object store aynası + raporları,
ayrı bir sürücüdeki yedek köküne alır ve doğrulanabilir bir yedek manifesti
yazar. Object store içerik adresli olduğu için ayna artımlıdır: var olan
nesne asla yeniden kopyalanmaz ve asla silinmez.

Kullanım (repo kökünden, worker venv'iyle):
    python deploy/scripts/derlem_backup.py --backup-root D:/DERLEM-BACKUP
    python deploy/scripts/derlem_backup.py --backup-root D:/DERLEM-BACKUP --passphrase-env BACKUP_PASSPHRASE

Parola verilirse DB dump'ı openssl aes-256-cbc (pbkdf2) ile şifrelenir ve düz
kopya silinir. Object aynası şifrelenmez; yedek sürücüsünde BitLocker gibi
volume şifrelemesi önerilir (bkz. docs/backup_restore.md).
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


DEFAULT_PG_BIN_CANDIDATES = (
    Path(r"C:\Program Files\PostgreSQL\17\bin"),
    Path(r"C:\Program Files\PostgreSQL\16\bin"),
    Path("/usr/lib/postgresql/17/bin"),
    Path("/usr/bin"),
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def find_pg_tool(name: str, pg_bin: str | None) -> str:
    if pg_bin:
        candidate = Path(pg_bin) / f"{name}.exe"
        if candidate.exists():
            return str(candidate)
        candidate = Path(pg_bin) / name
        if candidate.exists():
            return str(candidate)
        raise SystemExit(f"{name} bulunamadı: {pg_bin}")
    found = shutil.which(name)
    if found:
        return found
    for base in DEFAULT_PG_BIN_CANDIDATES:
        for candidate in (base / f"{name}.exe", base / name):
            if candidate.exists():
                return str(candidate)
    raise SystemExit(f"{name} bulunamadı; --pg-bin verin.")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_database(database_url: str, target: Path, pg_bin: str | None, passphrase: str | None) -> dict[str, object]:
    target.parent.mkdir(parents=True, exist_ok=True)
    pg_dump = find_pg_tool("pg_dump", pg_bin)
    subprocess.run(
        [pg_dump, "--format=custom", "--no-owner", "--file", str(target), "--dbname", database_url],
        check=True,
    )
    info: dict[str, object] = {
        "file": target.name,
        "byte_size": target.stat().st_size,
        "sha256": sha256_of(target),
        "encrypted": False,
    }
    if passphrase:
        openssl = shutil.which("openssl")
        if not openssl:
            raise SystemExit("openssl bulunamadı; şifreleme için Git for Windows openssl'i PATH'e ekleyin.")
        encrypted = target.with_suffix(target.suffix + ".enc")
        subprocess.run(
            [openssl, "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
             "-in", str(target), "-out", str(encrypted), "-pass", "env:DERLEM_BACKUP_PASS"],
            check=True,
            env={**os.environ, "DERLEM_BACKUP_PASS": passphrase},
        )
        target.unlink()
        info.update({
            "file": encrypted.name,
            "byte_size": encrypted.stat().st_size,
            "sha256": sha256_of(encrypted),
            "encrypted": True,
            "cipher": "aes-256-cbc-pbkdf2",
            "plain_sha256": info["sha256"],
        })
    return info


def mirror_objects(storage_root: Path, backup_objects: Path) -> dict[str, int]:
    source_objects = storage_root / "objects"
    if not source_objects.exists():
        raise SystemExit(f"Object store bulunamadı: {source_objects}")
    copied = skipped = 0
    copied_bytes = 0
    for source in source_objects.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(source_objects)
        destination = backup_objects / relative
        if destination.exists() and destination.stat().st_size == source.stat().st_size:
            skipped += 1
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1
        copied_bytes += source.stat().st_size
    return {"copied": copied, "skipped_existing": skipped, "copied_bytes": copied_bytes}


def copy_reports(repo_root: Path, backup_root: Path) -> int:
    count = 0
    for name in ("reports",):
        source_dir = repo_root / "var" / name
        if not source_dir.exists():
            continue
        for source in source_dir.rglob("*"):
            if not source.is_file():
                continue
            destination = backup_root / name / source.relative_to(source_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            count += 1
    return count


def snapshot_counts(database_url: str) -> dict[str, int]:
    try:
        import psycopg
    except ImportError:
        return {}
    # Sayım listesi restore tatbikatının doğrulama tabanıdır: burada olmayan bir
    # tablodaki sessiz kayıp tatbikatta yakalanmaz. Bu yüzden liste sabit değil,
    # şemadan türetilir — yeni migration bir tablo eklediğinde otomatik kapsanır.
    # (Yedeğin kendisi zaten tam: pg_dump tabloyu filtrelemez.)
    counts: dict[str, int] = {}
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        tables = [str(row[0]) for row in cursor.fetchall()]
        for table in tables:
            cursor.execute(f'SELECT count(*) FROM "{table}"')
            counts[table] = int(cursor.fetchone()[0])
    return counts


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Derlem yedeği alır.")
    parser.add_argument("--backup-root", default=os.environ.get("DERLEM_BACKUP_ROOT"),
                        help="Yedek kökü (tercihen ayrı fiziksel sürücü).")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--pg-bin", default=os.environ.get("PG_BIN"))
    parser.add_argument("--passphrase-env", default=None,
                        help="DB dump'ını şifrelemek için parolayı taşıyan ortam değişkeni adı.")
    args = parser.parse_args()

    if not args.backup_root:
        raise SystemExit("--backup-root zorunludur (veya DERLEM_BACKUP_ROOT).")

    repo_root = Path(__file__).resolve().parents[2]
    env = load_env(repo_root / args.env_file)
    database_url = env.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL bulunamadı (.env veya ortam).")
    storage_root = Path(env.get("STORAGE_ROOT") or repo_root / "var" / "storage")
    if not storage_root.is_absolute():
        storage_root = repo_root / storage_root

    passphrase = None
    if args.passphrase_env:
        passphrase = os.environ.get(args.passphrase_env)
        if not passphrase:
            raise SystemExit(f"{args.passphrase_env} ortam değişkeni boş.")

    backup_root = Path(args.backup_root)
    started = datetime.now(UTC)
    stamp = started.strftime("%Y%m%d_%H%M%S")

    counts = snapshot_counts(database_url)
    dump_info = dump_database(database_url, backup_root / "db" / f"derlem_{stamp}.dump", args.pg_bin, passphrase)
    object_stats = mirror_objects(storage_root, backup_root / "objects")
    report_count = copy_reports(repo_root, backup_root)

    manifest = {
        "schema_version": "derlem.backup-manifest.v1",
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "database_dump": dump_info,
        "objects": object_stats,
        "reports_copied": report_count,
        "table_counts": counts,
        "storage_root": str(storage_root),
    }
    manifest_path = backup_root / "manifests" / f"backup_{stamp}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nYedek tamam: {backup_root}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
