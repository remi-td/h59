"""CLI configuration for h59-local."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEVICE_CLOCK_MODES = ("utc", "local")
DEFAULT_DEVICE_CLOCK_MODE = "utc"


def default_config_dir() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / "h59"
    return Path.home() / ".config" / "h59"


def default_config_path() -> Path:
    return default_config_dir() / "config.json"


def read_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path).expanduser() if path is not None else default_config_path()
    if not config_path.exists():
        return {}
    try:
        payload = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def write_config(config: dict[str, Any], path: str | Path | None = None) -> Path:
    config_path = Path(path).expanduser() if path is not None else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    return config_path


def resolve_device_clock_mode(*, cli_value: str | None = None, config_path: str | Path | None = None) -> str:
    if cli_value is not None:
        mode = cli_value
    else:
        mode = read_config(config_path).get("device_clock", DEFAULT_DEVICE_CLOCK_MODE)
    if mode not in DEVICE_CLOCK_MODES:
        return DEFAULT_DEVICE_CLOCK_MODE
    return mode
