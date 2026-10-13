"""TASK-043 - olu kaynaklarin ve deneme kayitlarinin kalici temizligi.

Plan dosyasinda adi ve kimligiyle listelenen kaynaklari ve release'leri,
onlara bagli her satirla birlikte veritabanindan siler; yalniz bu satirlarin
referans verdigi ve baska hicbir satirin referans vermedigi storage_objects
kayitlarini da siler ve dosyalarini silmek yerine karantina dizinine TASIR.

Kullanim (repo kokunden):
    python -m derlem_worker.purge_sources --plan deploy/purge_plans/<plan>.json
    python -m derlem_worker.purge_sources --plan <plan>.json --execute \\
        --quarantine-dir var/purge-quarantine/<tarih>

Varsayilan kip --dry-run'dir: her sey READ ONLY bir transaction'da sayilir,
hicbir satir ve dosya degismez, transaction ROLLBACK edilir.

Guvenlik kurallari (kurucu karari 2026-10-13, TASK-043):
- Plan disinda hicbir satir silinmez. FK CASCADE'e guvenilmez: her tablo acik
  bir DELETE ... WHERE <plan kumesi> ile silinir. Silinecek bir satira plan
  disindan referans veren tek bir satir bile varsa (CASCADE/SET NULL olsa da)
  is durur.
- Bir nesneye silinmeyen herhangi bir satir hala referans veriyorsa (FK
  kolonu ya da is/kaynak/release JSON'u) nesnenin satiri da dosyasi da kalir.
- Frozen release'ler yalniz planda adi, surumu ve durumuyla acikca
  listelenmisse silinir.
- Plandaki bir kimlik bulunamazsa ya da adi tutmazsa hicbir sey yapilmaz.
- Koruma tetikleyicileri (append-only/frozen korumalari) yalniz bu
  transaction icinde, yalniz silinecek satiri olan tablolarda ve adlariyla
  kapatilir; commit'ten once yeniden acilir ve acildiklari dogrulanir.
  FK kisitlari ve row_change_events yakalama tetikleyicileri hep acik kalir.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, UTC
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg import sql

PLAN_SCHEMA_VERSION = "derlem.purge-plan.v1"
AUDIT_SCHEMA_VERSION = "derlem.sources-purged.v1"
AUDIT_ACTION = "sources_purged"
TERMINAL_JOB_STATUSES = ("succeeded", "failed", "cancelled")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA256_TOKEN_PATTERN = "([0-9a-f]{64})"
# Bu satir sayisinin ustundeki bir tablonun storage_objects'e giden FK kolonunda
# o kolonla baslayan bir indeks yoksa, storage_objects silinirken her satir icin
# yapilan FK kontrolu tum tabloyu tarar (document_fingerprints: 32M satir).
# Bu durumda transaction icinde gecici bir indeks kurulur ve commit'ten once
# dusurulur; sema degismez.
TEMP_INDEX_MIN_ROWS = 50_000


class PurgeRefused(RuntimeError):
    """Plan uygulanamaz; hicbir sey degismedi."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# --------------------------------------------------------------------------- plan


@dataclass(frozen=True)
class PlanSource:
    id: UUID
    name: str
    manifest_path: str | None = None


@dataclass(frozen=True)
class PlanRelease:
    id: UUID
    name: str
    version: str
    status: str


@dataclass(frozen=True)
class Plan:
    path: Path
    sha256: str
    plan_id: str
    approved_by: str
    reason: str
    sources: tuple[PlanSource, ...]
    releases: tuple[PlanRelease, ...]
    keep_sources: tuple[PlanSource, ...]


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"plan: {label} bos olamaz")
    return value.strip()


def _parse_uuid(value: Any, label: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"plan: {label} gecerli bir UUID degil: {value!r}") from error


def load_plan(path: Path) -> Plan:
    raw = path.read_bytes()
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml  # PyYAML; yalniz YAML plan verilirse gerekir

        document = yaml.safe_load(raw.decode("utf-8"))
    else:
        document = json.loads(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("plan: kok nesne bir sozluk olmali")
    if document.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError(f"plan: schema_version {PLAN_SCHEMA_VERSION!r} olmali")

    def sources_of(key: str) -> tuple[PlanSource, ...]:
        entries = document.get(key) or []
        if not isinstance(entries, list):
            raise ValueError(f"plan: {key} bir liste olmali")
        parsed = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"plan: {key}[{index}] bir sozluk olmali")
            manifest = entry.get("manifest_path")
            parsed.append(
                PlanSource(
                    id=_parse_uuid(entry.get("id"), f"{key}[{index}].id"),
                    name=_require_text(entry.get("name"), f"{key}[{index}].name"),
                    manifest_path=_require_text(manifest, f"{key}[{index}].manifest_path") if manifest else None,
                )
            )
        return tuple(parsed)

    releases = []
    entries = document.get("releases") or []
    if not isinstance(entries, list):
        raise ValueError("plan: releases bir liste olmali")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"plan: releases[{index}] bir sozluk olmali")
        releases.append(
            PlanRelease(
                id=_parse_uuid(entry.get("id"), f"releases[{index}].id"),
                name=_require_text(entry.get("name"), f"releases[{index}].name"),
                version=_require_text(entry.get("version"), f"releases[{index}].version"),
                # Durum acikca yazilir: frozen bir release ancak plan onu "frozen"
                # diye adlandirmissa silinir.
                status=_require_text(entry.get("status"), f"releases[{index}].status"),
            )
        )

    plan = Plan(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        plan_id=_require_text(document.get("plan_id"), "plan_id"),
        approved_by=_require_text(document.get("approved_by"), "approved_by"),
        reason=_require_text(document.get("reason"), "reason"),
        sources=sources_of("sources"),
        releases=tuple(releases),
        keep_sources=sources_of("keep_sources"),
    )
    if not plan.sources and not plan.releases:
        raise ValueError("plan: silinecek kaynak ya da release yok")
    for label, ids in (
        ("sources", [entry.id for entry in plan.sources]),
        ("releases", [entry.id for entry in plan.releases]),
        ("keep_sources", [entry.id for entry in plan.keep_sources]),
    ):
        if len(ids) != len(set(ids)):
            raise ValueError(f"plan: {label} icinde tekrar eden kimlik var")
    overlap = {entry.id for entry in plan.sources} & {entry.id for entry in plan.keep_sources}
    if overlap:
        raise ValueError(f"plan: ayni kaynak hem silinecek hem kalacak: {sorted(map(str, overlap))}")
    return plan


# ---------------------------------------------------------------- table specs


@dataclass(frozen=True)
class TableSpec:
    table: str
    # {a} tablo takma adidir; parametreler compute() icinde hesaplanan kumelerdir.
    predicate: str
    guards: tuple[str, ...] = ()
    self_refs: tuple[str, ...] = ()


# Silme sirasi: cocuklar once. Her satir kumesi acik bir yuklemle secilir;
# hicbir tablo FK CASCADE ile dolayli silinmez.
DELETE_SPECS: tuple[TableSpec, ...] = (
    TableSpec("document_review_reversals", "{a}.review_id = ANY(%(DR)s::uuid[])",
              ("document_review_reversals_no_delete",)),
    TableSpec("active_document_reviews",
              "({a}.review_id = ANY(%(DR)s::uuid[]) OR {a}.document_id = ANY(%(D)s::uuid[]))",
              ("active_document_reviews_trigger_writes_only",)),
    TableSpec("document_review_claims",
              "({a}.document_id = ANY(%(D)s::uuid[]) OR {a}.review_campaign_id = ANY(%(C)s::uuid[]))"),
    TableSpec("document_reviews", "{a}.id = ANY(%(DR)s::uuid[])", ("document_reviews_no_delete",)),
    TableSpec("document_sample_memberships",
              "({a}.source_id = ANY(%(S)s::uuid[]) OR {a}.document_id = ANY(%(D)s::uuid[]))",
              ("document_sample_memberships_no_delete_v24",)),
    TableSpec("release_source_contract_snapshots", "{a}.release_id = ANY(%(R)s::uuid[])",
              ("release_source_contract_snapshots_no_delete",)),
    TableSpec("review_campaigns", "{a}.id = ANY(%(C)s::uuid[])", ("review_campaigns_no_delete",)),
    TableSpec("document_sample_generations", "{a}.source_id = ANY(%(S)s::uuid[])",
              ("document_sample_generations_protect_identity",)),
    TableSpec("document_versions", "{a}.document_id = ANY(%(D)s::uuid[])"),
    TableSpec("documents", "{a}.id = ANY(%(D)s::uuid[])"),
    TableSpec("document_fingerprints", "{a}.source_id = ANY(%(S)s::uuid[])"),
    TableSpec("pii_scans", "{a}.source_id = ANY(%(S)s::uuid[])"),
    TableSpec("reviews", "{a}.source_id = ANY(%(S)s::uuid[])"),
    TableSpec("similarity_pair_reviews", "{a}.pair_id = ANY(%(P)s::uuid[])",
              ("similarity_pair_reviews_no_delete",)),
    TableSpec("similarity_review_pairs", "{a}.id = ANY(%(P)s::uuid[])",
              ("similarity_review_pairs_no_delete",)),
    TableSpec("similarity_calibration_runs", "{a}.id = ANY(%(RUN)s::uuid[])",
              ("similarity_calibration_runs_no_delete",)),
    TableSpec("source_lineage_inputs", "{a}.source_id = ANY(%(S)s::uuid[])"),
    TableSpec("release_sources", "{a}.release_id = ANY(%(R)s::uuid[])", ("release_sources_protect_frozen",)),
    TableSpec("release_exports", "{a}.release_id = ANY(%(R)s::uuid[])", ("release_exports_protect_ready",)),
    TableSpec("releases", "{a}.id = ANY(%(R)s::uuid[])", ("releases_protect_frozen",)),
    TableSpec("sources", "{a}.id = ANY(%(S)s::uuid[])",
              self_refs=("derived_from_source_id", "duplicate_of_source_id")),
    TableSpec("production_run_completions", "{a}.production_run_id = ANY(%(PR)s::uuid[])",
              ("production_run_completions_no_delete",)),
    TableSpec("production_runs", "{a}.id = ANY(%(PR)s::uuid[])", ("production_runs_no_delete",),
              self_refs=("parent_run_id",)),
    TableSpec("background_jobs", "{a}.id = ANY(%(J)s::uuid[])"),
)
SPEC_BY_TABLE = {spec.table: spec for spec in DELETE_SPECS}
STORAGE_GUARDS = ("storage_objects_no_delete",)

# Yuklemi FK yuklemiyle birebir ayni olan kenarlar: cocuk satirlar tanim geregi
# silinir; 20M satirlik document_fingerprints'i bosuna taramamak icin atlanir.
COVERED_EDGES = {("document_fingerprints", ("source_id",), "sources")}

# storage_objects'e FK ile baglanan her kolon ve satirin sahipligi (hangi plan
# kaynagi/release'i adina silindigi). Katalogdaki FK listesi bununla birebir
# eslesmezse (yeni migration yeni bir referans eklediyse) is durur.
OBJECT_REFS: tuple[tuple[str, str, str, str], ...] = (
    ("sources", "object_sha256", "ARRAY[{a}.id]", "NULL::uuid[]"),
    ("documents", "current_object_sha256", "ARRAY[{a}.source_id]", "NULL::uuid[]"),
    ("document_versions", "object_sha256",
     "(SELECT array_agg(d.source_id) FROM documents d WHERE d.id = {a}.document_id)", "NULL::uuid[]"),
    ("document_reviews", "object_sha256",
     "(SELECT array_agg(d.source_id) FROM documents d WHERE d.id = {a}.document_id)", "NULL::uuid[]"),
    ("document_sample_memberships", "object_sha256", "ARRAY[{a}.source_id]", "NULL::uuid[]"),
    ("document_sample_generations", "source_sha256", "ARRAY[{a}.source_id]", "NULL::uuid[]"),
    ("pii_scans", "object_sha256", "ARRAY[{a}.source_id]", "NULL::uuid[]"),
    ("review_campaigns", "sample_source_sha256", "ARRAY[{a}.source_id]", "NULL::uuid[]"),
    ("similarity_review_pairs", "left_object_sha256", "ARRAY[{a}.left_source_id]", "NULL::uuid[]"),
    ("similarity_review_pairs", "right_object_sha256", "ARRAY[{a}.right_source_id]", "NULL::uuid[]"),
    ("similarity_calibration_runs", "report_object_sha256",
     "(SELECT array_agg(DISTINCT x) FROM similarity_review_pairs p, "
     "unnest(ARRAY[p.left_source_id, p.right_source_id]) AS x WHERE p.run_id = {a}.id)", "NULL::uuid[]"),
    ("release_sources", "source_sha256", "NULL::uuid[]", "ARRAY[{a}.release_id]"),
    ("releases", "manifest_object_sha256", "NULL::uuid[]", "ARRAY[{a}.id]"),
    ("release_exports", "object_sha256", "NULL::uuid[]", "ARRAY[{a}.release_id]"),
    ("release_exports", "manifest_object_sha256", "NULL::uuid[]", "ARRAY[{a}.release_id]"),
    ("release_source_contract_snapshots", "sample_source_sha256", "NULL::uuid[]", "ARRAY[{a}.release_id]"),
    ("release_source_contract_snapshots", "production_run_output_manifest_sha256", "NULL::uuid[]",
     "ARRAY[{a}.release_id]"),
    ("release_source_contract_snapshots", "production_run_output_sha256", "NULL::uuid[]",
     "ARRAY[{a}.release_id]"),
    ("production_run_completions", "output_manifest_sha256",
     "(SELECT array_agg(s.id) FROM sources s WHERE s.production_run_id = {a}.production_run_id)", "NULL::uuid[]"),
    ("production_run_completions", "output_sha256",
     "(SELECT array_agg(s.id) FROM sources s WHERE s.production_run_id = {a}.production_run_id)", "NULL::uuid[]"),
    # document_fingerprints.source_sha256 ayri ele alinir (bkz. _fingerprint_pairs).
)
FINGERPRINT_REF = ("document_fingerprints", "source_sha256")


# ---------------------------------------------------------------- computation


@dataclass
class PurgeObject:
    sha256: str
    byte_size: int
    storage_key: str
    file_present: bool
    file_size: int | None
    source_ids: set[UUID] = field(default_factory=set)
    release_ids: set[UUID] = field(default_factory=set)
    manifest_sha256: str | None = None


@dataclass
class KeptObject:
    sha256: str
    byte_size: int
    kept_by: list[str]
    source_ids: set[UUID] = field(default_factory=set)
    release_ids: set[UUID] = field(default_factory=set)


@dataclass
class Computation:
    plan: Plan
    schema: str
    params: dict[str, Any] = field(default_factory=dict)
    source_rows: list[dict[str, Any]] = field(default_factory=list)
    release_rows: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    objects: list[PurgeObject] = field(default_factory=list)
    kept: list[KeptObject] = field(default_factory=list)
    guards: list[tuple[str, str]] = field(default_factory=list)
    temp_indexes: list[tuple[str, str]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def purge_bytes(self) -> int:
        return sum(item.byte_size for item in self.objects)


def _pred(spec_table: str, alias: str) -> str:
    spec = SPEC_BY_TABLE.get(spec_table)
    if spec is None:
        return "false"
    return spec.predicate.replace("{a}", alias)


def _ids(connection: psycopg.Connection, query: str, params: dict[str, Any]) -> list[UUID]:
    return sorted({row[0] for row in connection.execute(query, params) if row[0] is not None})


def _fk_edges(connection: psycopg.Connection) -> list[tuple[str, str, tuple[str, ...], str, tuple[str, ...], str]]:
    rows = connection.execute(
        """
        SELECT con.conname, child.relname, array_agg(ca.attname ORDER BY k.ord),
               parent.relname, array_agg(pa.attname ORDER BY k.ord), con.confdeltype
        FROM pg_constraint AS con
        JOIN pg_class AS child ON child.oid = con.conrelid
        JOIN pg_class AS parent ON parent.oid = con.confrelid
        CROSS JOIN LATERAL unnest(con.conkey, con.confkey) WITH ORDINALITY AS k(ck, pk, ord)
        JOIN pg_attribute AS ca ON ca.attrelid = con.conrelid AND ca.attnum = k.ck
        JOIN pg_attribute AS pa ON pa.attrelid = con.confrelid AND pa.attnum = k.pk
        WHERE con.contype = 'f'
          AND child.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())
        GROUP BY con.conname, child.relname, parent.relname, con.confdeltype
        ORDER BY child.relname, con.conname
        """
    ).fetchall()
    return [(r[0], r[1], tuple(r[2]), r[3], tuple(r[4]), str(r[5])) for r in rows]


def _fingerprint_pairs(connection: psycopg.Connection) -> list[tuple[UUID, str]]:
    """document_fingerprints'teki farkli (source_id, source_sha256) ciftleri.

    Tablo 32M satirdir; DISTINCT tum tabloyu tarar. (source_id, source_sha256)
    indeksi uzerinde gevsek indeks taramasi her cift icin tek bir indeks
    aramasi yapar (birkac duzine cift).
    """
    pairs: list[tuple[UUID, str]] = []
    row = connection.execute(
        "SELECT source_id, source_sha256 FROM document_fingerprints ORDER BY source_id, source_sha256 LIMIT 1"
    ).fetchone()
    while row is not None:
        pairs.append((row[0], str(row[1]).strip()))
        row = connection.execute(
            """
            SELECT source_id, source_sha256 FROM document_fingerprints
            WHERE (source_id, source_sha256) > (%s, %s)
            ORDER BY source_id, source_sha256 LIMIT 1
            """,
            (row[0], row[1]),
        ).fetchone()
    return pairs


def _expected_storage_key(sha: str) -> str:
    return f"objects/sha256/{sha[:2]}/{sha[2:4]}/{sha}"


def quarantine_path(quarantine_dir: Path, sha: str) -> Path:
    return quarantine_dir / "sha256" / sha[:2] / sha[2:4] / sha


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute(
    connection: psycopg.Connection,
    plan: Plan,
    storage_root: Path,
    quarantine_dir: Path | None = None,
    base_dir: Path | None = None,
) -> Computation:
    """Plani okur, hicbir sey yazmaz. Bulunan her sorun problems'a eklenir."""
    schema = connection.execute("SELECT current_schema()").fetchone()[0]
    result = Computation(plan=plan, schema=schema)
    problems = result.problems
    S = sorted(entry.id for entry in plan.sources)
    R = sorted(entry.id for entry in plan.releases)

    # --- 1. kimlik dogrulama: bulunamayan ya da adi tutmayan her kayit isi durdurur
    rows = connection.execute(
        """
        SELECT s.id, s.name, s.content_purpose, s.approval_status, s.object_sha256, so.byte_size,
               s.derived_from_source_id, s.duplicate_of_source_id
        FROM sources AS s LEFT JOIN storage_objects AS so ON so.sha256 = s.object_sha256
        WHERE s.id = ANY(%s::uuid[])
        """,
        (S + [entry.id for entry in plan.keep_sources],),
    ).fetchall()
    by_id = {row[0]: row for row in rows}
    for entry in plan.sources:
        row = by_id.get(entry.id)
        if row is None:
            problems.append(f"plan kaynagi veritabaninda yok: {entry.id} ({entry.name})")
        elif row[1] != entry.name:
            problems.append(f"plan kaynaginin adi tutmuyor: {entry.id} planda {entry.name!r}, DB'de {row[1]!r}")
        else:
            result.source_rows.append({
                "id": row[0], "name": row[1], "content_purpose": row[2], "approval_status": row[3],
                "object_sha256": (str(row[4]).strip() if row[4] else None), "byte_size": row[5],
            })
    for entry in plan.keep_sources:
        row = by_id.get(entry.id)
        if row is None:
            problems.append(f"kalacak kaynak veritabaninda yok: {entry.id} ({entry.name})")
        elif row[1] != entry.name:
            problems.append(f"kalacak kaynagin adi tutmuyor: {entry.id} planda {entry.name!r}, DB'de {row[1]!r}")
    release_by_id = {
        row[0]: row
        for row in connection.execute(
            """
            SELECT id, name, version, status, content_purpose, manifest_object_sha256
            FROM releases WHERE id = ANY(%s::uuid[])
            """,
            (R,),
        )
    }
    for entry in plan.releases:
        row = release_by_id.get(entry.id)
        if row is None:
            problems.append(f"plan release'i veritabaninda yok: {entry.id} ({entry.name} {entry.version})")
        elif (row[1], row[2]) != (entry.name, entry.version):
            problems.append(
                f"plan release'inin adi/surumu tutmuyor: {entry.id} planda {entry.name!r} {entry.version!r}, "
                f"DB'de {row[1]!r} {row[2]!r}"
            )
        elif row[3] != entry.status:
            problems.append(
                f"plan release'inin durumu tutmuyor: {entry.id} {entry.name} {entry.version} planda "
                f"{entry.status!r}, DB'de {row[3]!r} (frozen bir release ancak acikca 'frozen' yazilirsa silinir)"
            )
        else:
            result.release_rows.append({
                "id": row[0], "name": row[1], "version": row[2], "status": row[3],
                "content_purpose": row[4], "manifest_object_sha256": (str(row[5]).strip() if row[5] else None),
            })
    manifest_by_source: dict[UUID, str] = {}
    for entry in plan.sources:
        if not entry.manifest_path:
            continue
        manifest = Path(entry.manifest_path)
        if not manifest.is_absolute() and base_dir is not None:
            manifest = base_dir / manifest
        if not manifest.is_file():
            problems.append(f"plan kaynaginin manifest dosyasi yok: {entry.name}: {manifest}")
            continue
        manifest_by_source[entry.id] = _sha256_file(manifest)
    if problems:
        return result

    # --- 2. silinecek satir kumeleri
    params: dict[str, Any] = {"S": S, "R": R}
    params["S_text"] = [str(value) for value in S]
    params["R_text"] = [str(value) for value in R]
    params["D"] = _ids(connection, "SELECT id FROM documents WHERE source_id = ANY(%(S)s::uuid[])", params)
    params["C"] = _ids(connection, "SELECT id FROM review_campaigns WHERE source_id = ANY(%(S)s::uuid[])", params)
    params["DR"] = _ids(
        connection,
        """
        SELECT id FROM document_reviews
        WHERE document_id = ANY(%(D)s::uuid[]) OR review_campaign_id = ANY(%(C)s::uuid[])
        """,
        params,
    )
    params["P"] = _ids(
        connection,
        """
        SELECT id FROM similarity_review_pairs
        WHERE left_source_id = ANY(%(S)s::uuid[]) OR right_source_id = ANY(%(S)s::uuid[])
        """,
        params,
    )
    params["RUN"] = _ids(
        connection, "SELECT DISTINCT run_id FROM similarity_review_pairs WHERE id = ANY(%(P)s::uuid[])", params
    )
    for run_id, outside in connection.execute(
        """
        SELECT run_id, count(*) FROM similarity_review_pairs
        WHERE run_id = ANY(%(RUN)s::uuid[]) AND NOT (id = ANY(%(P)s::uuid[]))
        GROUP BY run_id
        """,
        params,
    ):
        problems.append(
            f"benzerlik kalibrasyon kosusu {run_id} karisik: {outside} cifti plan disi kaynaklara ait "
            "(kosu bolunerek silinmez)"
        )
    params["PR"] = _ids(
        connection,
        """
        SELECT production_run_id FROM sources
        WHERE id = ANY(%(S)s::uuid[]) AND production_run_id IS NOT NULL
        EXCEPT
        SELECT production_run_id FROM sources
        WHERE NOT (id = ANY(%(S)s::uuid[])) AND production_run_id IS NOT NULL
        """,
        params,
    )
    params["J"] = _ids(
        connection,
        """
        SELECT id FROM background_jobs
        WHERE payload->>'source_id' = ANY(%(S_text)s::text[])
           OR payload->>'release_id' = ANY(%(R_text)s::text[])
        UNION SELECT job_id FROM document_sample_generations WHERE source_id = ANY(%(S)s::uuid[])
        UNION SELECT job_id FROM pii_scans WHERE source_id = ANY(%(S)s::uuid[])
        UNION SELECT sample_job_id FROM review_campaigns WHERE id = ANY(%(C)s::uuid[])
        UNION SELECT job_id FROM production_run_completions WHERE production_run_id = ANY(%(PR)s::uuid[])
        UNION SELECT sample_job_id FROM release_source_contract_snapshots WHERE release_id = ANY(%(R)s::uuid[])
        """,
        params,
    )
    for job_id, job_type, status in connection.execute(
        """
        SELECT id, job_type, status FROM background_jobs
        WHERE id = ANY(%(J)s::uuid[]) AND NOT (status = ANY(%(terminal)s::text[]))
        ORDER BY id
        """,
        {**params, "terminal": list(TERMINAL_JOB_STATUSES)},
    ):
        problems.append(f"plana bagli is hala acik: {job_id} {job_type} ({status}); once bitmeli ya da iptal edilmeli")
    result.params = params

    # --- 3. satir sayilari
    for spec in DELETE_SPECS:
        query = sql.SQL("SELECT count(*) FROM {table} AS t WHERE " + _pred(spec.table, "t")).format(
            table=sql.Identifier(spec.table)
        )
        result.counts[spec.table] = int(connection.execute(query, params).fetchone()[0])

    # --- 4. plan disi referans: silinecek bir satira plan disindan referans veren satir
    edges = _fk_edges(connection)
    for conname, child, child_cols, parent, parent_cols, deltype in edges:
        if parent not in SPEC_BY_TABLE or result.counts.get(parent, 0) == 0:
            continue
        if (child, child_cols, parent) in COVERED_EDGES:
            continue
        join = " AND ".join(f"p.{pc} = c.{cc}" for cc, pc in zip(child_cols, parent_cols))
        query = (
            f"SELECT count(*) FROM {child} AS c WHERE EXISTS (SELECT 1 FROM {parent} AS p WHERE {join} "
            f"AND {_pred(parent, 'p')}) AND NOT COALESCE({_pred(child, 'c')}, false)"
        )
        outside = int(connection.execute(query, params).fetchone()[0])
        if outside:
            action = {"c": "CASCADE ile silinirdi", "n": "SET NULL ile degisirdi", "d": "SET DEFAULT ile degisirdi"}.get(
                deltype, "silmeyi engeller"
            )
            problems.append(
                f"plan disi referans: {child}({', '.join(child_cols)}) tablosunda {outside} satir silinecek "
                f"{parent} satirlarina bagli ({conname}; {action}). Bu satirlarin sahibi plana eklenmeli ya da "
                "plandan cikarilmali."
            )

    # --- 5. nesneler
    catalog_refs = {(child, cols[0]) for _, child, cols, parent, _, _ in edges if parent == "storage_objects"}
    known_refs = {(table, column) for table, column, _, _ in OBJECT_REFS} | {FINGERPRINT_REF}
    if catalog_refs != known_refs:
        problems.append(
            "storage_objects'e giden FK listesi beklenenle eslesmiyor (sema degismis; purge_sources.OBJECT_REFS "
            f"guncellenmeli): eksik {sorted(catalog_refs - known_refs)}, fazla {sorted(known_refs - catalog_refs)}"
        )
        return result

    candidates: dict[str, tuple[set[UUID], set[UUID]]] = defaultdict(lambda: (set(), set()))

    def add(sha: Any, sources: Any, releases: Any) -> None:
        if sha is None:
            return
        digest = str(sha).strip()
        entry = candidates[digest]
        entry[0].update(value for value in (sources or []) if value is not None)
        entry[1].update(value for value in (releases or []) if value is not None)

    for table, column, source_expr, release_expr in OBJECT_REFS:
        if result.counts.get(table, 0) == 0:
            continue
        query = (
            f"SELECT t.{column}, {source_expr.replace('{a}', 't')}, {release_expr.replace('{a}', 't')} "
            f"FROM {table} AS t WHERE t.{column} IS NOT NULL AND {_pred(table, 't')}"
        )
        for sha, sources, releases in connection.execute(query, params):
            add(sha, sources, releases)
    fingerprint_pairs = _fingerprint_pairs(connection)
    planned_sources = set(S)
    for source_id, sha in fingerprint_pairs:
        if source_id in planned_sources:
            add(sha, [source_id], [])
    # JSON icinde anilan nesneler (or. distill manifestleri, cikarim kaynagi):
    # yalniz silinen is/kaynak/release satirlarinda geciyor ve katalogda varsa aday.
    json_queries = (
        (
            "SELECT m[1], t.payload->>'source_id', t.payload->>'release_id' FROM background_jobs AS t, "
            "regexp_matches(t.payload::text || ' ' || coalesce(t.result::text, ''), %(pattern)s, 'g') AS m "
            "WHERE t.id = ANY(%(J)s::uuid[])"
        ),
        (
            "SELECT m[1], t.id::text, NULL FROM sources AS t, "
            "regexp_matches(t.source_metadata::text, %(pattern)s, 'g') AS m WHERE t.id = ANY(%(S)s::uuid[])"
        ),
        (
            "SELECT m[1], NULL, t.id::text FROM releases AS t, "
            "regexp_matches(t.gate_results::text, %(pattern)s, 'g') AS m WHERE t.id = ANY(%(R)s::uuid[])"
        ),
    )
    json_params = {**params, "pattern": SHA256_TOKEN_PATTERN}
    json_hits: dict[str, tuple[set[UUID], set[UUID]]] = defaultdict(lambda: (set(), set()))
    for query in json_queries:
        for sha, source_text, release_text in connection.execute(query, json_params):
            entry = json_hits[sha]
            if source_text and _is_uuid(source_text) and UUID(source_text) in planned_sources:
                entry[0].add(UUID(source_text))
            if release_text and _is_uuid(release_text) and UUID(release_text) in set(R):
                entry[1].add(UUID(release_text))
    if json_hits:
        existing = {
            str(row[0]).strip()
            for row in connection.execute(
                "SELECT sha256 FROM storage_objects WHERE sha256 = ANY(%s::bpchar[])", (sorted(json_hits),)
            )
        }
        for sha in sorted(existing):
            add(sha, json_hits[sha][0], json_hits[sha][1])

    candidate_list = sorted(candidates)
    object_params = {**params, "O": candidate_list, "pattern": SHA256_TOKEN_PATTERN}
    kept_by: dict[str, list[str]] = defaultdict(list)
    # 5a. silinmeyen satirlarin FK referanslari
    for table, column, _, _ in OBJECT_REFS:
        query = (
            f"SELECT t.{column}, count(*) FROM {table} AS t WHERE t.{column} = ANY(%(O)s::bpchar[]) "
            f"AND NOT COALESCE({_pred(table, 't')}, false) GROUP BY t.{column}"
        )
        for sha, count in connection.execute(query, object_params):
            kept_by[str(sha).strip()].append(f"{table}.{column} ({count} satir)")
    candidate_set = set(candidate_list)
    for source_id, sha in fingerprint_pairs:
        if sha in candidate_set and source_id not in planned_sources:
            kept_by[sha].append(f"document_fingerprints.source_sha256 (kaynak {source_id})")
    # 5b. silinmeyen satirlarin JSON/metin referanslari (temkinli: anilan nesne kalir)
    text_refs = (
        ("background_jobs JSON",
         "SELECT DISTINCT m[1] FROM background_jobs AS t, regexp_matches(t.payload::text || ' ' || "
         "coalesce(t.result::text, ''), %(pattern)s, 'g') AS m WHERE NOT (t.id = ANY(%(J)s::uuid[]))"),
        ("sources metadata/lineage",
         "SELECT DISTINCT m[1] FROM sources AS t, regexp_matches(t.source_metadata::text || ' ' || t.lineage_ref "
         "|| ' ' || coalesce(t.license_evidence_ref, ''), %(pattern)s, 'g') AS m "
         "WHERE NOT (t.id = ANY(%(S)s::uuid[]))"),
        ("releases gate_results",
         "SELECT DISTINCT m[1] FROM releases AS t, regexp_matches(t.gate_results::text, %(pattern)s, 'g') AS m "
         "WHERE NOT (t.id = ANY(%(R)s::uuid[]))"),
    )
    for label, query in text_refs:
        for (sha,) in connection.execute(query, object_params):
            if sha in candidate_set:
                kept_by[sha].append(label)

    storage_rows = {
        str(row[0]).strip(): (int(row[1]), str(row[2]))
        for row in connection.execute(
            "SELECT sha256, byte_size, storage_key FROM storage_objects WHERE sha256 = ANY(%(O)s::bpchar[])",
            object_params,
        )
    }
    export_manifest = {
        str(row[0]).strip(): str(row[1]).strip()
        for row in connection.execute(
            "SELECT object_sha256, manifest_object_sha256 FROM release_exports "
            "WHERE release_id = ANY(%(R)s::uuid[]) AND object_sha256 IS NOT NULL AND manifest_object_sha256 IS NOT NULL",
            params,
        )
    }
    source_object = {row["id"]: row["object_sha256"] for row in result.source_rows}
    for sha in candidate_list:
        sources, releases = candidates[sha]
        byte_size, storage_key = storage_rows.get(sha, (0, ""))
        if sha not in storage_rows:
            problems.append(f"aday nesnenin storage_objects satiri yok: {sha}")
            continue
        if sha in kept_by:
            result.kept.append(KeptObject(sha, byte_size, sorted(kept_by[sha]), set(sources), set(releases)))
            continue
        if not SHA256_RE.match(sha) or storage_key != _expected_storage_key(sha):
            problems.append(f"nesnenin depo anahtari beklenen duzende degil: {sha} -> {storage_key!r}")
            continue
        path = storage_root / storage_key
        present = path.is_file()
        manifest = None
        for source_id in sorted(sources):
            if source_object.get(source_id) == sha and source_id in manifest_by_source:
                manifest = manifest_by_source[source_id]
                break
        if manifest is None and sha in export_manifest:
            manifest = export_manifest[sha]
        result.objects.append(
            PurgeObject(
                sha256=sha,
                byte_size=byte_size,
                storage_key=storage_key,
                file_present=present,
                file_size=path.stat().st_size if present else None,
                source_ids=set(sources),
                release_ids=set(releases),
                manifest_sha256=manifest,
            )
        )
    keep_object_shas = {
        str(row[0]).strip()
        for row in connection.execute(
            "SELECT object_sha256 FROM sources WHERE id = ANY(%s::uuid[]) AND object_sha256 IS NOT NULL",
            ([entry.id for entry in plan.keep_sources],),
        )
    }
    for item in result.objects:
        if item.sha256 in keep_object_shas:
            problems.append(f"kalacak bir kaynagin nesnesi silinecekler arasinda: {item.sha256} (hata; is durdu)")

    # --- 6. execute'ta kapatilacak koruma tetikleyicileri ve gerekirse gecici indeksler
    needed = [(spec.table, guard) for spec in DELETE_SPECS if result.counts[spec.table] for guard in spec.guards]
    if result.objects:
        needed += [("storage_objects", guard) for guard in STORAGE_GUARDS]
    present_triggers = {
        (row[0], row[1])
        for row in connection.execute(
            """
            SELECT cl.relname, t.tgname FROM pg_trigger AS t
            JOIN pg_class AS cl ON cl.oid = t.tgrelid
            WHERE NOT t.tgisinternal
              AND cl.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())
            """
        )
    }
    for table, guard in needed:
        if (table, guard) not in present_triggers:
            problems.append(f"beklenen koruma tetikleyicisi yok: {table}.{guard} (sema degismis)")
    result.guards = needed
    if result.objects:
        for table, column in [(t, c) for t, c, _, _ in OBJECT_REFS] + [FINGERPRINT_REF]:
            if _needs_temp_index(connection, table, column):
                result.temp_indexes.append((table, column))

    # --- 7. karantina on kontrolu (verildiyse)
    if quarantine_dir is not None:
        problems.extend(quarantine_preflight(result, storage_root, quarantine_dir))
    return result


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _needs_temp_index(connection: psycopg.Connection, table: str, column: str) -> bool:
    row = connection.execute(
        """
        SELECT cl.reltuples,
               EXISTS (
                   SELECT 1 FROM pg_index AS i
                   JOIN pg_attribute AS a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
                   WHERE i.indrelid = cl.oid AND a.attname = %s
               )
        FROM pg_class AS cl
        WHERE cl.relname = %s
          AND cl.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())
        """,
        (column, table),
    ).fetchone()
    if row is None:
        return False
    reltuples, indexed = float(row[0]), bool(row[1])
    return not indexed and reltuples >= TEMP_INDEX_MIN_ROWS


def quarantine_preflight(result: Computation, storage_root: Path, quarantine_dir: Path) -> list[str]:
    problems: list[str] = []
    storage_objects = (storage_root / "objects").resolve()
    quarantine = quarantine_dir.resolve()
    if quarantine == storage_objects or storage_objects in quarantine.parents or quarantine in storage_objects.parents:
        problems.append(f"karantina dizini nesne deposuyla ic ice olamaz: {quarantine}")
        return problems
    probe = quarantine
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    if storage_objects.exists() and os.stat(probe).st_dev != os.stat(storage_objects).st_dev:
        problems.append(
            f"karantina dizini nesne deposuyla ayni surucude degil ({quarantine}); os.replace tasiyamaz"
        )
    for item in result.objects:
        target = quarantine_path(quarantine, item.sha256)
        if item.file_present and target.exists():
            problems.append(f"karantinada zaten bir dosya var: {target}")
    return problems


# ---------------------------------------------------------------- execution


def _set_triggers(connection: psycopg.Connection, guards: list[tuple[str, str]], enable: bool) -> None:
    verb = "ENABLE" if enable else "DISABLE"
    for table, trigger in guards:
        connection.execute(
            sql.SQL("ALTER TABLE {table} " + verb + " TRIGGER {trigger}").format(
                table=sql.Identifier(table), trigger=sql.Identifier(trigger)
            )
        )


def _delete(connection: psycopg.Connection, spec: TableSpec, params: dict[str, Any]) -> int:
    if not spec.self_refs:
        query = sql.SQL("DELETE FROM {table} AS t WHERE " + _pred(spec.table, "t")).format(
            table=sql.Identifier(spec.table)
        )
        return connection.execute(query, params).rowcount
    # Kendine referans veren tablo (sources.derived_from_source_id ...): once
    # kumedeki baska bir satirin referans vermedigi satirlar silinir.
    remaining = {
        row[0]
        for row in connection.execute(
            sql.SQL("SELECT t.id FROM {table} AS t WHERE " + _pred(spec.table, "t")).format(
                table=sql.Identifier(spec.table)
            ),
            params,
        )
    }
    deleted = 0
    while remaining:
        referenced: set[UUID] = set()
        for column in spec.self_refs:
            referenced |= {
                row[0]
                for row in connection.execute(
                    sql.SQL("SELECT {column} FROM {table} WHERE id = ANY(%s::uuid[]) AND {column} IS NOT NULL").format(
                        column=sql.Identifier(column), table=sql.Identifier(spec.table)
                    ),
                    (sorted(remaining),),
                )
            }
        batch = remaining - referenced
        if not batch:
            raise RuntimeError(f"{spec.table}: kendine referans dongusu; silme sirasi kurulamadi")
        deleted += connection.execute(
            sql.SQL("DELETE FROM {table} WHERE id = ANY(%s::uuid[])").format(table=sql.Identifier(spec.table)),
            (sorted(batch),),
        ).rowcount
        remaining -= batch
    return deleted


def _temp_index_name(table: str, column: str) -> str:
    return f"purge_tmp_{table}_{column}"[:63]


def audit_details(result: Computation, purged_at: str, quarantine_dir: Path, log_path: Path) -> dict[str, Any]:
    shas = sorted(item.sha256 for item in result.objects)
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "actor": result.plan.approved_by,
        "approved_by": result.plan.approved_by,
        "reason": result.plan.reason,
        "plan_id": result.plan.plan_id,
        "plan_path": result.plan.path.as_posix(),
        "plan_sha256": result.plan.sha256,
        "purged_at": purged_at,
        "sources": [{"id": str(row["id"]), "name": row["name"]} for row in result.source_rows],
        "releases": [
            {"id": str(row["id"]), "name": row["name"], "version": row["version"], "status": row["status"]}
            for row in result.release_rows
        ],
        "deleted_rows": {table: count for table, count in result.counts.items() if count},
        "purged_objects": {
            "count": len(shas),
            "byte_size": result.purge_bytes,
            "files_moved": sum(1 for item in result.objects if item.file_present),
            "files_missing": sum(1 for item in result.objects if not item.file_present),
            "sha256_list_sha256": hashlib.sha256("\n".join(shas).encode("ascii")).hexdigest(),
        },
        "kept_shared_objects": [{"sha256": item.sha256, "kept_by": item.kept_by} for item in result.kept],
        "quarantine_dir": str(quarantine_dir),
        "log_path": log_path.as_posix(),
    }


def log_lines(result: Computation, purged_at: str) -> list[str]:
    lines = []
    for item in sorted(result.objects, key=lambda value: value.sha256):
        record = {
            "sha256": item.sha256,
            "byte_size": item.byte_size,
            "source_ids": sorted(str(value) for value in item.source_ids),
            "release_ids": sorted(str(value) for value in item.release_ids),
            "reason": result.plan.reason,
            "approved_by": result.plan.approved_by,
            "purged_at": purged_at,
            "manifest_sha256": item.manifest_sha256,
            "plan_id": result.plan.plan_id,
            "plan_sha256": result.plan.sha256,
            "quarantined": item.file_present,
        }
        lines.append(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return lines


def execute(
    connection: psycopg.Connection,
    result: Computation,
    storage_root: Path,
    quarantine_dir: Path,
    log_path: Path,
    purged_at: str,
) -> None:
    """compute() ile ayni transaction'da cagrilir; basarida COMMIT eder."""
    if result.problems:
        raise PurgeRefused(result.problems)
    params = result.params
    connection.execute("SET LOCAL lock_timeout = '15s'")
    _set_triggers(connection, result.guards, enable=False)
    for spec in DELETE_SPECS:
        expected = result.counts[spec.table]
        if expected == 0:
            continue
        deleted = _delete(connection, spec, params)
        if deleted != expected:
            raise RuntimeError(f"{spec.table}: {expected} satir bekleniyordu, {deleted} silindi; geri alindi")
    purge = sorted(item.sha256 for item in result.objects)
    if purge:
        for table, column in result.temp_indexes:
            connection.execute(
                sql.SQL("CREATE INDEX {name} ON {table} ({column})").format(
                    name=sql.Identifier(_temp_index_name(table, column)),
                    table=sql.Identifier(table),
                    column=sql.Identifier(column),
                )
            )
        # FK kisitlari burada son hakemdir: silinmeyen bir satir hala referans
        # veriyorsa DELETE hata verir ve her sey geri alinir.
        deleted = connection.execute(
            "DELETE FROM storage_objects WHERE sha256 = ANY(%s::bpchar[])", (purge,)
        ).rowcount
        if deleted != len(purge):
            raise RuntimeError(f"storage_objects: {len(purge)} satir bekleniyordu, {deleted} silindi; geri alindi")
        for table, column in result.temp_indexes:
            connection.execute(
                sql.SQL("DROP INDEX {name}").format(name=sql.Identifier(_temp_index_name(table, column)))
            )
    _set_triggers(connection, result.guards, enable=True)
    enabled = {
        (row[0], row[1])
        for row in connection.execute(
            """
            SELECT cl.relname, t.tgname FROM pg_trigger AS t
            JOIN pg_class AS cl ON cl.oid = t.tgrelid
            WHERE NOT t.tgisinternal AND t.tgenabled = 'O'
              AND cl.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())
            """
        )
    }
    disabled = [guard for guard in result.guards if guard not in enabled]
    if disabled:
        raise RuntimeError(f"koruma tetikleyicileri yeniden acilamadi: {disabled}")
    details = audit_details(result, purged_at, quarantine_dir, log_path)
    connection.execute(
        """
        INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
        VALUES ('human', %s, 'purge_plan', %s, %s::jsonb)
        """,
        (AUDIT_ACTION, uuid5(NAMESPACE_URL, f"derlem:purge-plan:{result.plan.sha256}"), json.dumps(details)),
    )

    # Dosyalar commit'ten ONCE tasinir; commit basarisiz olursa geri konur.
    problems = quarantine_preflight(result, storage_root, quarantine_dir)
    if problems:
        raise PurgeRefused(problems)
    moved: list[tuple[Path, Path]] = []
    try:
        for item in result.objects:
            if not item.file_present:
                continue
            source = storage_root / item.storage_key
            target = quarantine_path(quarantine_dir, item.sha256)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            moved.append((source, target))
        connection.commit()
    except BaseException:
        for source, target in reversed(moved):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, source)
            except OSError as error:  # pragma: no cover - yalniz disk arizasinda
                print(f"UYARI: {target} geri tasinamadi: {error}", file=sys.stderr)
        raise

    lines = log_lines(result, purged_at)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as handle:
            for line in lines:
                handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        print("HATA: silme gunlugu yazilamadi; asagidaki satirlari elle ekleyin:", file=sys.stderr)
        for line in lines:
            print(line, file=sys.stderr)
        raise


# ---------------------------------------------------------------- report


def _n(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _fmt_bytes(value: int) -> str:
    return f"{_n(value)} B ({value / 1e9:.2f} GB)"


def render_report(result: Computation, mode: str, storage_root: Path, quarantine_dir: Path | None) -> str:
    plan = result.plan
    out: list[str] = []
    out.append(f"# derlem_worker.purge_sources - {mode}")
    out.append(f"plan: {plan.path.as_posix()} (sha256 {plan.sha256})")
    out.append(f"plan_id: {plan.plan_id}")
    out.append(f"onaylayan: {plan.approved_by}")
    out.append(f"gerekce: {plan.reason}")
    out.append(f"sema: {result.schema}; depo: {storage_root}")
    if quarantine_dir is not None:
        out.append(f"karantina: {quarantine_dir}")
    out.append("")
    if result.problems:
        out.append(f"## SORUNLAR ({len(result.problems)}) - plan UYGULANAMAZ, hicbir sey degismedi")
        out.extend(f"- {problem}" for problem in result.problems)
        out.append("")
    out.append(f"## Silinecek kaynaklar ({len(result.source_rows)})")
    for row in result.source_rows:
        size = row["byte_size"] if row["byte_size"] is not None else 0
        sha = (row["object_sha256"] or "-")[:12]
        out.append(f"- {row['id']}  {row['name']}  [{row['content_purpose']}, {row['approval_status']}]  "
                   f"nesne {sha}  {_n(size)} B")
    out.append("")
    out.append(f"## Silinecek release'ler ({len(result.release_rows)})")
    for row in result.release_rows:
        out.append(f"- {row['id']}  {row['name']} {row['version']}  [{row['content_purpose']}, {row['status']}]  "
                   f"manifest {(row['manifest_object_sha256'] or '-')[:12]}")
    out.append("")
    if plan.keep_sources:
        out.append(f"## Kalacagi dogrulanan kaynaklar ({len(plan.keep_sources)})")
        out.extend(f"- {entry.id}  {entry.name}" for entry in plan.keep_sources)
        out.append("")
    if result.counts:
        out.append("## Silinecek satirlar (silme sirasiyla)")
        out.append("| tablo | satir |")
        out.append("|---|---:|")
        total = 0
        for table, count in result.counts.items():
            out.append(f"| {table} | {_n(count)} |")
            total += count
        out.append(f"| storage_objects | {_n(len(result.objects))} |")
        total += len(result.objects)
        out.append(f"| **toplam** | **{_n(total)}** |")
        out.append("")
    present = [item for item in result.objects if item.file_present]
    missing = [item for item in result.objects if not item.file_present]
    out.append(
        f"## Tasinacak nesneler: {len(result.objects)} nesne, toplam {_fmt_bytes(result.purge_bytes)}; "
        f"dosyasi var {len(present)} ({_fmt_bytes(sum(i.byte_size for i in present))}), dosyasi yok {len(missing)}"
    )
    by_owner: dict[str, list[PurgeObject]] = defaultdict(list)
    names = {row["id"]: row["name"] for row in result.source_rows}
    releases = {row["id"]: f"{row['name']} {row['version']}" for row in result.release_rows}
    for item in result.objects:
        owners = [f"kaynak {names.get(s, s)}" for s in sorted(item.source_ids)] + [
            f"release {releases.get(r, r)}" for r in sorted(item.release_ids)
        ]
        by_owner[" + ".join(owners) or "(sahipsiz)"].append(item)
    out.append("| sahip (plan kaydi) | nesne | bayt |")
    out.append("|---|---:|---:|")
    for owner in sorted(by_owner):
        items = by_owner[owner]
        out.append(f"| {owner} | {len(items)} | {_n(sum(i.byte_size for i in items))} |")
    out.append("")
    out.append("sha256 | bayt | dosya | manifest_sha256 | sahip")
    for item in sorted(result.objects, key=lambda value: value.sha256):
        state = "var" if item.file_present else "YOK"
        if item.file_present and item.file_size != item.byte_size:
            state = f"var (boyut {item.file_size} != {item.byte_size})"
        owners = ",".join(sorted(str(s)[:8] for s in item.source_ids) + sorted("r:" + str(r)[:8] for r in item.release_ids))
        out.append(f"{item.sha256} | {item.byte_size} | {state} | {item.manifest_sha256 or '-'} | {owners}")
    out.append("")
    out.append(f"## KALACAK paylasilan nesneler ({len(result.kept)}) - satir ve dosya yerinde kalir")
    for item in sorted(result.kept, key=lambda value: value.sha256):
        out.append(f"- {item.sha256}  {item.byte_size} B  kalan referans: {'; '.join(item.kept_by)}")
    out.append("")
    if result.guards:
        out.append("## execute'ta yalniz transaction icinde kapatilacak koruma tetikleyicileri")
        out.extend(f"- {table}.{trigger}" for table, trigger in result.guards)
        out.append("")
    if result.temp_indexes:
        out.append("## execute'ta transaction icinde kurulup dusurulecek gecici indeksler")
        out.extend(f"- {table}({column})" for table, column in result.temp_indexes)
        out.append("")
    out.extend(result.notes)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- CLI


def _load_dotenv(path: Path) -> None:
    from derlem_worker.config import _load_dotenv as load

    load(path)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="python -m derlem_worker.purge_sources",
        description="Plandaki kaynaklari/release'leri ve bagli satirlari siler; nesne dosyalarini karantinaya tasir.",
    )
    parser.add_argument("--plan", type=Path, required=True, help="JSON (ya da YAML) silme plani")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Varsayilan: say, listele, ROLLBACK")
    mode.add_argument("--execute", action="store_true", help="Plani uygula (--quarantine-dir zorunlu)")
    parser.add_argument("--quarantine-dir", type=Path, help="Nesne dosyalarinin tasinacagi dizin (ayni surucu)")
    parser.add_argument("--log", type=Path, default=Path("deploy/purged_objects.jsonl"), help="Silme gunlugu (append)")
    parser.add_argument("--report", type=Path, help="Raporu bu dosyaya da yaz")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--storage-root", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.execute and args.quarantine_dir is None:
        parser.error("--execute icin --quarantine-dir zorunludur")
    _load_dotenv(args.env_file)
    database_url = args.database_url or os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        parser.error("DATABASE_URL bulunamadi (.env, ortam ya da --database-url)")
    storage_root = (args.storage_root or Path(os.environ.get("STORAGE_ROOT", "./var/storage"))).resolve()
    quarantine_dir = args.quarantine_dir.resolve() if args.quarantine_dir else None
    plan = load_plan(args.plan)
    base_dir = Path.cwd()
    mode_label = "EXECUTE" if args.execute else "DRY-RUN"

    with psycopg.connect(database_url) as connection:
        if args.execute:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        else:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        result = compute(connection, plan, storage_root, quarantine_dir, base_dir)
        purged_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if not args.execute:
            result.notes.append("Sonuc: DRY-RUN - hicbir satir ve dosya degismedi; transaction ROLLBACK edildi.")
            connection.rollback()
        elif not result.problems:
            execute(connection, result, storage_root, quarantine_dir, args.log, purged_at)
            result.notes.append(
                f"Sonuc: EXECUTE tamam ({purged_at}); satirlar silindi, {sum(1 for i in result.objects if i.file_present)} "
                f"dosya {quarantine_dir} altina tasindi, gunluk: {args.log.as_posix()}"
            )
        else:
            connection.rollback()
            result.notes.append("Sonuc: EXECUTE REDDEDILDI - hicbir satir ve dosya degismedi.")
    report = render_report(result, mode_label, storage_root, quarantine_dir)
    sys.stdout.write(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8", newline="\n")
    return 1 if result.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
