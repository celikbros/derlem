from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Config:
    database_url: str
    storage_root: Path
    staging_root: Path
    poll_interval_seconds: float


def load_config() -> Config:
    _load_dotenv(Path(".env"))
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    storage_root = Path(os.environ.get("STORAGE_ROOT", "./var/storage")).resolve()
    staging_root = Path(os.environ.get("STAGING_ROOT", "./var/staging")).resolve()
    poll_value = os.environ.get("WORKER_POLL_INTERVAL", "2s").strip()
    return Config(
        database_url=database_url,
        storage_root=storage_root,
        staging_root=staging_root,
        poll_interval_seconds=_parse_duration_seconds(poll_value),
    )


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _parse_duration_seconds(value: str) -> float:
    units = {"ms": 0.001, "s": 1.0, "m": 60.0}
    for suffix, multiplier in units.items():
        if value.endswith(suffix):
            amount = float(value[: -len(suffix)])
            if amount <= 0:
                break
            return amount * multiplier
    raise RuntimeError(f"Unsupported WORKER_POLL_INTERVAL: {value!r}")
