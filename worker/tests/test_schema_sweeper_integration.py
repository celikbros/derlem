from __future__ import annotations

import time
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

# Supurme testinin "eski" semasi 11 dakika once olusturulmus gibi adlandirilir ve
# 10 dakika esigiyle supurulur. Oturum baslangicindaki varsayilan supurucu 1 saat
# esigi kullanir; bu yas onun altinda kaldigi icin baska bir kosu bu testin
# semasini ondan once silemez.
SWEEP_TEST_THRESHOLD_SECONDS = 600


def _schema_name(label: str, age_seconds: int) -> str:
    created_ns = time.time_ns() - age_seconds * 1_000_000_000
    return f"derlem_{label}_test_{created_ns}_{uuid4().hex[:8]}"


def test_sweeper_drops_only_provably_old_schemas(test_database_url: str, schema_sweeper) -> None:
    old = _schema_name("sweeper_worker_old", 11 * 60)
    fresh = _schema_name("sweeper_worker_fresh", 0)
    with psycopg.connect(test_database_url, autocommit=True) as admin:
        for schema in (old, fresh):
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        dropped, skipped = schema_sweeper(test_database_url, SWEEP_TEST_THRESHOLD_SECONDS)

        assert old in dropped
        assert fresh not in dropped
        with psycopg.connect(test_database_url) as connection:
            present = {
                row[0]
                for row in connection.execute(
                    "SELECT nspname FROM pg_namespace WHERE nspname IN (%s, %s)",
                    (old, fresh),
                )
            }
        assert present == {fresh}
    finally:
        with psycopg.connect(test_database_url, autocommit=True) as admin:
            for schema in (old, fresh):
                admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def test_sweeper_refuses_a_non_scratch_database_before_connecting(schema_sweeper) -> None:
    # Baglanti kurulmadan reddedilmeli: calisma veritabaninda asla sema dusurulmez.
    with pytest.raises(ValueError, match="non-scratch"):
        schema_sweeper("postgresql://nobody:nothing@127.0.0.1:1/derlem")
