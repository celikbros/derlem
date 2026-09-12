import os
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict
import pytest

ENV_VAR = "DERLEM_TEST_DATABASE_URL"
SKIP_ENV_VAR = "DERLEM_SKIP_DB_TESTS"


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
    name = str(conninfo_to_dict(raw).get("dbname", ""))
    if not name.endswith("_test"):
        pytest.fail(
            f"{ENV_VAR}: database {name!r} is not a scratch database: the name must end in _test "
            "(integration tests create and drop schemas with CASCADE; never point this at the working database)",
            pytrace=False,
        )
    return raw


def pytest_configure(config) -> None:
    # Windows kullanıcı TEMP dizini bazı ortamlarda tmp_path fixture'ına izin
    # vermiyor; testler env ayarı gerektirmeden repo içindeki gitignore'lu
    # var/pytest-tmp altında çalışır. --basetemp verilirse ona dokunulmaz.
    # Üst dizinler (temiz CI checkout'unda var/ yoktur) burada oluşturulur.
    if config.option.basetemp is None:
        basetemp = Path(__file__).resolve().parents[2] / "var" / "pytest-tmp"
        basetemp.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = basetemp
