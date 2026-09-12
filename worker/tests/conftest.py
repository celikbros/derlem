import os
from pathlib import Path
import re
import sys
import time
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import pytest

ENV_VAR = "DERLEM_TEST_DATABASE_URL"
SKIP_ENV_VAR = "DERLEM_SKIP_DB_TESTS"

# internal/testdb ile ayni kurallar ve ayni sema adi bicimi:
# derlem_<etiket>_test_<unixnano>_<8 hex>. Zaman tasimayan adlar asla eslesmez.
LEAKED_SCHEMA_AGE_SECONDS = 3600
TEST_SCHEMA_PATTERN = re.compile(r"^derlem_[a-z0-9_]+_test_([0-9]{19})(?:_[0-9a-f]{8})?$")


def _database_name(raw_url: str) -> str:
    return str(conninfo_to_dict(raw_url).get("dbname", ""))


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Veritabanina bagli testlerin adresi; internal/testdb (Go) ile ayni iki kural.

    1. Adres yoksa test SESSIZCE ATLANMAZ: DERLEM_SKIP_DB_TESTS=1 ile acikca
       atlanir, aksi halde kirmizi olur.
    2. Adi _test ile bitmeyen veritabanina hicbir test dokunmaz (testler sema
       acip CASCADE ile dusurur; 2026-08-21'de calisma DB'sine sema kalmisti).
    """
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        if os.environ.get(SKIP_ENV_VAR, "").strip():
            pytest.skip(f"{ENV_VAR} is not set and {SKIP_ENV_VAR} is set: database-backed test skipped deliberately")
        pytest.fail(
            f"{ENV_VAR} is not set. Point it at a scratch database whose name ends in _test "
            f"(scripts/test.ps1 derives it from .env), or set {SKIP_ENV_VAR}=1 to skip database-backed tests on purpose.",
            pytrace=False,
        )
    name = _database_name(raw)
    if not name.endswith("_test"):
        pytest.fail(
            f"{ENV_VAR}: database {name!r} is not a scratch database: the name must end in _test "
            "(integration tests create and drop schemas with CASCADE; never point this at the working database)",
            pytrace=False,
        )
    return raw


@pytest.fixture(scope="session")
def isolated_schema_name():
    """Adinda olusturulma zamanini tasiyan izole sema adi uretir.

    Supurucu yalniz adindaki zamana gore kanitlanabilir bicimde eski semalari
    dusurur; eszamanli kosan baska bir test surecinin canli semasina dokunmaz.
    """

    def make(label: str) -> str:
        return f"derlem_{label}_test_{time.time_ns()}_{uuid4().hex[:8]}"

    return make


def sweep_leaked_schemas(
    raw_url: str,
    older_than_seconds: int = LEAKED_SCHEMA_AGE_SECONDS,
) -> tuple[list[str], list[str]]:
    """Adindaki olusturulma zamani esikten eski test semalarini dusurur.

    (dusurulenler, eklenti icerdigi icin bilerek dusurulmeyenler) dondurur.
    Eklenti iceren sema dusurulmez: CASCADE eklentiyi veritabaninin tamamindan
    siler (pgcrypto yarisi, 2026-09).
    """
    name = _database_name(raw_url)
    if not name.endswith("_test"):
        raise ValueError(f"refusing to sweep non-scratch database {name!r}: the name must end in _test")
    cutoff_ns = time.time_ns() - older_than_seconds * 1_000_000_000
    dropped: list[str] = []
    skipped: list[str] = []
    with psycopg.connect(raw_url, autocommit=True) as connection:
        schemas = [row[0] for row in connection.execute("SELECT nspname FROM pg_namespace")]
        for schema in schemas:
            match = TEST_SCHEMA_PATTERN.match(schema)
            if match is None or int(match.group(1)) >= cutoff_ns:
                continue
            extension_count = connection.execute(
                """
                SELECT count(*) FROM pg_extension AS extension
                JOIN pg_namespace AS namespace ON namespace.oid = extension.extnamespace
                WHERE namespace.nspname = %s
                """,
                (schema,),
            ).fetchone()[0]
            if extension_count:
                skipped.append(schema)
                continue
            connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
            dropped.append(schema)
    return dropped, skipped


@pytest.fixture(scope="session")
def schema_sweeper():
    return sweep_leaked_schemas


def pytest_sessionstart(session) -> None:
    # Supurme temizliktir: adres yoksa ya da test veritabani degilse hicbir sey
    # yapmaz (o durumu test_database_url kirmizi gosterir); hata testleri
    # durdurmaz ama gorunur yazilir.
    try:
        raw = os.environ.get(ENV_VAR, "").strip()
        if not raw or not _database_name(raw).endswith("_test"):
            return
        dropped, skipped = sweep_leaked_schemas(raw)
    except Exception as error:  # noqa: BLE001 - supurme hicbir kosuyu dusurmemeli
        print(f"testdb: leaked schema sweep failed: {error}", file=sys.stderr)
        return
    for schema in dropped:
        print(f"testdb: dropped leaked test schema {schema}", file=sys.stderr)
    for schema in skipped:
        print(
            f"testdb: NOT dropping leaked test schema {schema}: it contains an extension, and CASCADE would "
            "remove that extension from the whole database. Move it first (ALTER EXTENSION ... SET SCHEMA public).",
            file=sys.stderr,
        )


def pytest_configure(config) -> None:
    # Windows kullanıcı TEMP dizini bazı ortamlarda tmp_path fixture'ına izin
    # vermiyor; testler env ayarı gerektirmeden repo içindeki gitignore'lu
    # var/pytest-tmp altında çalışır. --basetemp verilirse ona dokunulmaz.
    # Üst dizinler (temiz CI checkout'unda var/ yoktur) burada oluşturulur.
    if config.option.basetemp is None:
        basetemp = Path(__file__).resolve().parents[2] / "var" / "pytest-tmp"
        basetemp.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = basetemp
