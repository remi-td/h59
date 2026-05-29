from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_web_assets_parse() -> None:
    package = json.loads((ROOT / "dashboard" / "web" / "package.json").read_text())
    assert package["name"] == "h59-dashboard-web"
    assert "react" in package["dependencies"]


def test_dashboard_stack_files_exist() -> None:
    expected = [
        ROOT / "dashboard" / "README.md",
        ROOT / "dashboard" / "docker-compose.yml",
        ROOT / "dashboard" / "run.sh",
        ROOT / "dashboard" / ".env.example",
        ROOT / "dashboard" / "Makefile",
        ROOT / "dashboard" / "api" / "pyproject.toml",
        ROOT / "dashboard" / "api" / "Dockerfile",
        ROOT / "dashboard" / "web" / "package.json",
        ROOT / "dashboard" / "web" / "Dockerfile",
        ROOT / "dashboard" / "web" / "index.html",
        ROOT / "dashboard" / "web" / "nginx.conf",
    ]
    for path in expected:
        assert path.exists(), path
