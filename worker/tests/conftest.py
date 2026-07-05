from pathlib import Path


def pytest_configure(config) -> None:
    # Windows kullanıcı TEMP dizini bazı ortamlarda tmp_path fixture'ına izin
    # vermiyor; testler env ayarı gerektirmeden repo içindeki gitignore'lu
    # var/pytest-tmp altında çalışır. --basetemp verilirse ona dokunulmaz.
    if config.option.basetemp is None:
        config.option.basetemp = Path(__file__).resolve().parents[2] / "var" / "pytest-tmp"
