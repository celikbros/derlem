from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

import psycopg
from psycopg.rows import dict_row

from derlem_worker.config import load_config


DEFAULT_MANIFEST = Path(r"C:\CELIKBROS PROJECTS\gardash\docs\TOKENIZER_V3_8_FINAL_CORPUS_MANIFEST_FAZ2.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Catalog the Gardas Faz 2 corpus in Derlem")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--actor-email")
    parser.add_argument("--license", default="unknown")
    parser.add_argument("--rights-status", choices=("unknown", "cleared", "restricted", "blocked"), default="unknown")
    parser.add_argument("--license-evidence-ref")
    parser.add_argument("--verify-sha256", action="store_true")
    parser.add_argument("--queue-ingest", action="store_true")
    args = parser.parse_args()

    config = load_config()
    actor_email = args.actor_email or os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "")
    if not actor_email:
        parser.error("--actor-email or BOOTSTRAP_ADMIN_EMAIL is required")
    if args.rights_status == "cleared" and not args.license_evidence_ref:
        parser.error("--license-evidence-ref is required when rights are cleared")

    seed = load_seed_manifest(args.manifest)
    if args.verify_sha256:
        actual_sha256 = compute_sha256(seed["text_path"])
        if actual_sha256 != seed["declared_sha256"]:
            raise RuntimeError(f"SHA256 mismatch: manifest={seed['declared_sha256']} actual={actual_sha256}")

    with psycopg.connect(config.database_url, row_factory=dict_row) as connection:
        result = catalog_seed(
            connection,
            seed,
            actor_email=actor_email,
            license_name=args.license,
            rights_status=args.rights_status,
            license_evidence_ref=args.license_evidence_ref,
        )
        if args.queue_ingest:
            ensure_ingest_capacity(config.storage_root, seed["declared_byte_size"])
            result["job_id"] = queue_ingest(connection, result["source_id"], seed["text_path"], result["actor_id"])
        connection.commit()

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def load_seed_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    corpus = manifest.get("corpus")
    if not isinstance(corpus, dict):
        raise ValueError("Manifest corpus object is required")

    required = ("name", "text_path", "line_count", "raw_bytes", "sha256")
    missing = [field for field in required if corpus.get(field) in (None, "")]
    if missing:
        raise ValueError(f"Manifest corpus fields are missing: {', '.join(missing)}")

    text_path = Path(str(corpus["text_path"])).resolve(strict=True)
    declared_size = int(corpus["raw_bytes"])
    declared_lines = int(corpus["line_count"])
    declared_sha256 = str(corpus["sha256"]).lower()
    if len(declared_sha256) != 64 or any(character not in "0123456789abcdef" for character in declared_sha256):
        raise ValueError("Manifest SHA256 is invalid")
    actual_size = text_path.stat().st_size
    if actual_size != declared_size:
        raise ValueError(f"File size mismatch: manifest={declared_size} actual={actual_size}")

    seed_key = f"gardas:{manifest_path.as_posix().lower()}"
    metadata = {
        "seed_key": seed_key,
        "source_system": "CELIK-GARDASH",
        "manifest_path": str(manifest_path),
        "manifest_schema_version": manifest.get("schema_version"),
        "frozen": bool(corpus.get("frozen")),
        "format": corpus.get("format"),
        "dedup": manifest.get("dedup", {}),
        "mixture": manifest.get("mixture", []),
        "normalization": manifest.get("normalization", {}),
        "document_boundaries": manifest.get("document_boundaries", {}),
        "handoff_reference": manifest.get("handoff_reference", {}),
    }
    return {
        "seed_key": seed_key,
        "name": str(corpus["name"]),
        "manifest_path": manifest_path,
        "text_path": text_path,
        "declared_sha256": declared_sha256,
        "declared_byte_size": declared_size,
        "declared_line_count": declared_lines,
        "metadata": metadata,
    }


def catalog_seed(
    connection: psycopg.Connection,
    seed: dict[str, Any],
    *,
    actor_email: str,
    license_name: str,
    rights_status: str,
    license_evidence_ref: str | None,
) -> dict[str, Any]:
    actor = connection.execute(
        "SELECT id, email FROM users WHERE email = lower(%s) AND status = 'active'",
        (actor_email.strip(),),
    ).fetchone()
    if actor is None:
        raise ValueError(f"Active actor was not found: {actor_email}")

    existing = connection.execute(
        """
        SELECT id, declared_sha256, declared_byte_size, declared_line_count, approval_status
        FROM sources
        WHERE source_metadata->>'seed_key' = %s
        FOR UPDATE
        """,
        (seed["seed_key"],),
    ).fetchone()
    created = existing is None
    if existing is None:
        status = "source_registered" if rights_status == "cleared" else "license_review"
        existing = connection.execute(
            """
            INSERT INTO sources(
                name, source_type, content_purpose, license, rights_status,
                language, domain, license_evidence_ref, lineage_ref,
                declared_sha256, declared_byte_size, declared_line_count,
                source_metadata, approval_status, created_by
            )
            VALUES (%s, 'text_corpus', 'pretrain', %s, %s, 'tr', 'mixed', %s, %s,
                    %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id, declared_sha256, declared_byte_size, declared_line_count, approval_status
            """,
            (
                seed["name"], license_name, rights_status, license_evidence_ref,
                str(seed["manifest_path"]), seed["declared_sha256"],
                seed["declared_byte_size"], seed["declared_line_count"],
                json.dumps(seed["metadata"], ensure_ascii=False), status, actor["id"],
            ),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
            VALUES (
                %s, 'source.seed_cataloged', 'source', %s,
                jsonb_build_object(
                    'seed_key', %s::text, 'manifest_path', %s::text,
                    'declared_sha256', %s::text, 'declared_byte_size', %s::bigint,
                    'declared_line_count', %s::bigint
                )
            )
            """,
            (
                actor["id"], existing["id"], seed["seed_key"], str(seed["manifest_path"]),
                seed["declared_sha256"], seed["declared_byte_size"], seed["declared_line_count"],
            ),
        )
    else:
        declared = (
            str(existing["declared_sha256"]),
            int(existing["declared_byte_size"]),
            int(existing["declared_line_count"]),
        )
        expected = (seed["declared_sha256"], seed["declared_byte_size"], seed["declared_line_count"])
        if declared != expected:
            raise RuntimeError("Existing Gardas catalog record does not match the manifest")

    return {
        "source_id": str(existing["id"]),
        "actor_id": str(actor["id"]),
        "created": created,
        "approval_status": existing["approval_status"],
        "declared_sha256": seed["declared_sha256"],
        "declared_byte_size": seed["declared_byte_size"],
        "declared_line_count": seed["declared_line_count"],
        "ingest_queued": False,
    }


def queue_ingest(connection: psycopg.Connection, source_id: str, text_path: Path, actor_id: str) -> str:
    source = connection.execute(
        "SELECT object_sha256 FROM sources WHERE id = %s FOR UPDATE",
        (source_id,),
    ).fetchone()
    if source is None:
        raise ValueError("Catalog source was not found")
    if source["object_sha256"] is not None:
        raise ValueError("Catalog source is already ingested")
    active = connection.execute(
        """
        SELECT id FROM background_jobs
        WHERE payload->>'source_id' = %s
          AND job_type IN ('ingest_local_file', 'ingest_staged_file')
          AND status IN ('queued', 'running')
        """,
        (source_id,),
    ).fetchone()
    if active is not None:
        return str(active["id"])

    job = connection.execute(
        """
        INSERT INTO background_jobs(job_type, payload, created_by)
        VALUES ('ingest_local_file', jsonb_build_object('source_id', %s::text, 'local_path', %s::text), %s)
        RETURNING id
        """,
        (source_id, str(text_path), actor_id),
    ).fetchone()
    connection.execute(
        """
        INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
        VALUES (%s, 'source.ingest_queued', 'source', %s,
                jsonb_build_object('job_id', %s::text, 'job_type', 'ingest_local_file', 'mode', 'gardas_seed'))
        """,
        (actor_id, source_id, str(job["id"])),
    )
    return str(job["id"])


def ensure_ingest_capacity(storage_root: Path, byte_size: int) -> None:
    storage_root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(storage_root).free
    required = int(byte_size * 1.05)
    if free < required:
        raise RuntimeError(f"Insufficient storage: required={required} free={free}")


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise
