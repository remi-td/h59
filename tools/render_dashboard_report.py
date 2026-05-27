#!/usr/bin/env python3
"""Render a markdown audit report from an H59 SQLite database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from h59_client.report import render_health_dashboard_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a markdown audit report for the H59 dashboard requirements")
    parser.add_argument("--db", default="data/h59.sqlite", help="SQLite database path")
    parser.add_argument("--date", help="report day in YYYY-MM-DD format; defaults to the latest day found in the database")
    parser.add_argument("--device-id", type=int, help="device_id to report on; defaults to the most recently seen device")
    parser.add_argument("--output", help="write the markdown report to this file instead of stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    markdown = render_health_dashboard_report(args.db, report_date=args.date, device_id=args.device_id)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
    else:
        sys.stdout.write(markdown)
        if not markdown.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
