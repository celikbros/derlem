from pathlib import Path


def pytest_configure(config) -> None:
    # Windows kullanıcı TEMP dizini bazı ortamlarda tmp_path fixture'ına izin
    # vermiyor; testler env ayarı gerektirmeden repo içindeki gitignore'lu
    # var/pytest-tmp altında çalışır. --basetemp verilirse ona dokunulmaz.
    # Üst dizinler (temiz CI checkout'unda var/ yoktur) burada oluşturulur.
    if config.option.basetemp is None:
        basetemp = Path(__file__).resolve().parents[2] / "var" / "pytest-tmp"
        basetemp.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = basetemp
