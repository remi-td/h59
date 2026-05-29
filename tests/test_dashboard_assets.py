from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_json_assets_parse() -> None:
    dashboards = [
        ROOT / "dashboard" / "dashboards" / "h59_overview.json",
        ROOT / "dashboard" / "dashboards" / "h59_sleep_recovery.json",
        ROOT / "dashboard" / "dashboards" / "h59_data_quality.json",
    ]
    for path in dashboards:
        payload = json.loads(path.read_text())
        assert payload["title"].startswith("H59 ")
        assert payload["uid"].startswith("h59-")
        assert payload["panels"]


def test_dashboard_stack_files_exist() -> None:
    expected = [
        ROOT / "dashboard" / "README.md",
        ROOT / "dashboard" / "docker-compose.yml",
        ROOT / "dashboard" / ".env.example",
        ROOT / "dashboard" / "Makefile",
        ROOT / "dashboard" / "provisioning" / "datasources" / "sqlite.yml",
        ROOT / "dashboard" / "provisioning" / "dashboards" / "dashboards.yml",
        ROOT / "dashboard" / "sql" / "views.sql",
        ROOT / "dashboard" / "sql" / "dashboard_summary.sql",
        ROOT / "dashboard" / "sql" / "example_queries.sql",
    ]
    for path in expected:
        assert path.exists(), path
