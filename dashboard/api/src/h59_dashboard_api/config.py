from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_db_path() -> Path:
    return Path(__file__).resolve().parents[4] / "data" / "h59.sqlite"


@dataclass(frozen=True)
class Settings:
    db_path: Path
    read_only: bool
    host: str
    port: int
    cors_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw_origins = os.getenv(
        "H59_DASHBOARD_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080",
    )
    origins = tuple(part.strip() for part in raw_origins.split(",") if part.strip())
    return Settings(
        db_path=Path(os.getenv("H59_DB_PATH", str(_default_db_path()))).expanduser(),
        read_only=_env_flag("H59_DASHBOARD_READONLY", True),
        host=os.getenv("H59_DASHBOARD_HOST", "127.0.0.1"),
        port=int(os.getenv("H59_DASHBOARD_PORT", "8000")),
        cors_origins=origins,
    )
