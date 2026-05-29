#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
ENV_FILE="$ROOT_DIR/.env"
API_DIR="$ROOT_DIR/api"
WEB_DIR="$ROOT_DIR/web"
PROJECT_SRC_DIR="$PROJECT_ROOT/src"
API_VENV_DIR="$API_DIR/.venv"
API_ENV_STAMP="$RUN_DIR/api-env.stamp"
WEB_DEPS_STAMP="$WEB_DIR/node_modules/.package-lock.json"

mkdir -p "$RUN_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

API_HOST="${H59_DASHBOARD_API_HOST:-127.0.0.1}"
API_PORT="${H59_API_DEV_PORT:-8000}"
WEB_HOST="${H59_DASHBOARD_WEB_HOST:-127.0.0.1}"
WEB_PORT="${H59_WEB_DEV_PORT:-5173}"
API_PYTHON="${H59_DASHBOARD_API_PYTHON:-}"
API_RELOAD="${H59_DASHBOARD_API_RELOAD:-0}"
RUNNER_PYTHON="${H59_DASHBOARD_RUNNER_PYTHON:-$(command -v python3 2>/dev/null || true)}"

api_pid_file() { echo "$RUN_DIR/api.pid"; }
web_pid_file() { echo "$RUN_DIR/web.pid"; }
api_log_file() { echo "$RUN_DIR/api.log"; }
web_log_file() { echo "$RUN_DIR/web.log"; }

is_running_pid() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

python_has_uvicorn() {
  local candidate="$1"
  [[ -x "$candidate" ]] || return 1
  "$candidate" - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("uvicorn") else 1)
PY
}

ensure_api_env() {
  if [[ -n "$API_PYTHON" ]]; then
    if python_has_uvicorn "$API_PYTHON"; then
      return 0
    fi
    echo "Configured H59_DASHBOARD_API_PYTHON does not provide uvicorn: $API_PYTHON" >&2
    return 1
  fi

  local needs_sync=0
  if [[ ! -x "$API_VENV_DIR/bin/python" ]]; then
    needs_sync=1
  elif [[ ! -f "$API_ENV_STAMP" || "$API_DIR/pyproject.toml" -nt "$API_ENV_STAMP" ]]; then
    needs_sync=1
  fi

  if command_exists uv; then
    if [[ "$needs_sync" -eq 1 ]]; then
      echo "Syncing dashboard/api virtualenv with uv..." >&2
      (cd "$API_DIR" && uv sync --extra dev >&2)
      touch "$API_ENV_STAMP"
    fi
    return 0
  fi

  local bootstrap_python
  bootstrap_python="$(command -v python3 2>/dev/null || true)"
  if [[ -z "$bootstrap_python" ]]; then
    echo "python3 is required to create dashboard/api/.venv" >&2
    return 1
  fi

  if [[ ! -x "$API_VENV_DIR/bin/python" ]]; then
    echo "Creating dashboard/api virtualenv with $bootstrap_python..." >&2
    "$bootstrap_python" -m venv "$API_VENV_DIR"
    needs_sync=1
  fi

  if [[ "$needs_sync" -eq 1 ]]; then
    echo "Installing dashboard/api dependencies into $API_VENV_DIR..." >&2
    (
      cd "$API_DIR"
      "$API_VENV_DIR/bin/python" -m pip install --upgrade pip >&2
      "$API_VENV_DIR/bin/python" -m pip install -e ".[dev]" >&2
    ) 
    touch "$API_ENV_STAMP"
  fi
}

resolve_api_python() {
  if [[ -n "$API_PYTHON" ]]; then
    echo "$API_PYTHON"
    return 0
  fi

  ensure_api_env
  if [[ -x "$API_VENV_DIR/bin/python" ]]; then
    echo "$API_VENV_DIR/bin/python"
    return 0
  fi

  echo "dashboard/api virtualenv is missing after setup: $API_VENV_DIR" >&2
  return 1
}

running_from_file() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  local pid
  pid="$(cat "$file")"
  [[ -n "$pid" ]] || return 1
  is_running_pid "$pid"
}

ensure_web_deps() {
  if [[ ! -d "$WEB_DIR/node_modules" || ! -f "$WEB_DEPS_STAMP" || "$WEB_DIR/package-lock.json" -nt "$WEB_DEPS_STAMP" || "$WEB_DIR/package.json" -nt "$WEB_DEPS_STAMP" ]]; then
    echo "Installing dashboard/web dependencies..."
    (cd "$WEB_DIR" && npm install)
  fi
}

start_api() {
  if running_from_file "$(api_pid_file)"; then
    echo "api already running (pid=$(cat "$(api_pid_file)"))"
    return
  fi
  local api_python
  local pid
  local -a uvicorn_args
  api_python="$(resolve_api_python)"
  uvicorn_args=(-m uvicorn h59_dashboard_api.main:app --host "$API_HOST" --port "$API_PORT")
  if [[ "$API_RELOAD" == "1" || "$API_RELOAD" == "true" || "$API_RELOAD" == "yes" ]]; then
    uvicorn_args+=(--reload)
  fi
  echo "Starting api on http://$API_HOST:$API_PORT"
  echo "  python: $api_python"
  (
    cd "$ROOT_DIR"
    pid="$(spawn_detached "$(api_log_file)" env VIRTUAL_ENV="$API_VENV_DIR" PATH="$API_VENV_DIR/bin:$PATH" PYTHONPATH="$API_DIR/src:$PROJECT_SRC_DIR${PYTHONPATH:+:$PYTHONPATH}" H59_DB_PATH="${H59_DB_PATH:-$PROJECT_ROOT/data/h59.sqlite}" "$api_python" "${uvicorn_args[@]}")"
    echo "$pid" >"$(api_pid_file)"
  )
  sleep 1
  if ! running_from_file "$(api_pid_file)"; then
    echo "api failed to stay up. Recent log output:" >&2
    tail -n 40 "$(api_log_file)" >&2 || true
    rm -f "$(api_pid_file)"
    return 1
  fi
}

start_web() {
  if running_from_file "$(web_pid_file)"; then
    echo "web already running (pid=$(cat "$(web_pid_file)"))"
    return
  fi
  local pid
  ensure_web_deps
  echo "Starting web on http://$WEB_HOST:$WEB_PORT"
  (
    cd "$WEB_DIR"
    pid="$(spawn_detached "$(web_log_file)" npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT")"
    echo "$pid" >"$(web_pid_file)"
  )
}

stop_service() {
  local name="$1"
  local pid_file="$2"
  if ! [[ -f "$pid_file" ]]; then
    echo "$name not running"
    return
  fi
  local pid
  pid="$(cat "$pid_file")"
  if [[ -z "$pid" ]]; then
    rm -f "$pid_file"
    echo "$name not running"
    return
  fi
  if is_running_pid "$pid"; then
    echo "Stopping $name (pid=$pid)"
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      if is_running_pid "$pid"; then
        sleep 0.2
      else
        break
      fi
    done
    if is_running_pid "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  else
    echo "$name not running"
  fi
  rm -f "$pid_file"
}

status_service() {
  local name="$1"
  local pid_file="$2"
  local url="$3"
  local log_file="$4"
  if running_from_file "$pid_file"; then
    echo "$name running (pid=$(cat "$pid_file"))"
    echo "  url: $url"
    echo "  log: $log_file"
  else
    echo "$name stopped"
  fi
}

logs_service() {
  local name="$1"
  local log_file="$2"
  if [[ ! -f "$log_file" ]]; then
    echo "No log file for $name yet: $log_file"
    return 1
  fi
  tail -f "$log_file"
}

spawn_detached() {
  local log_file="$1"
  shift
  if [[ -z "$RUNNER_PYTHON" ]]; then
    echo "python3 is required to detach dashboard services" >&2
    return 1
  fi
  "$RUNNER_PYTHON" - "$log_file" "$@" <<'PY'
from __future__ import annotations

import os
import subprocess
import sys

log_path = sys.argv[1]
command = sys.argv[2:]

with open(log_path, "ab", buffering=0) as log_file:
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
        cwd=os.getcwd(),
        env=os.environ.copy(),
    )

print(process.pid)
PY
}

usage() {
  cat <<EOF
Usage:
  ./run.sh start [api|web|all]
  ./run.sh stop [api|web|all]
  ./run.sh restart [api|web|all]
  ./run.sh status [api|web|all]
  ./run.sh logs [api|web]

Defaults:
  target defaults to all
  api url: http://$API_HOST:$API_PORT
  web url: http://$WEB_HOST:$WEB_PORT
EOF
}

command="${1:-status}"
target="${2:-all}"

case "$command" in
  start)
    case "$target" in
      api) start_api ;;
      web) start_web ;;
      all) start_api; start_web ;;
      *) usage; exit 1 ;;
    esac
    ;;
  stop)
    case "$target" in
      api) stop_service "api" "$(api_pid_file)" ;;
      web) stop_service "web" "$(web_pid_file)" ;;
      all) stop_service "web" "$(web_pid_file)"; stop_service "api" "$(api_pid_file)" ;;
      *) usage; exit 1 ;;
    esac
    ;;
  restart)
    "$0" stop "$target"
    "$0" start "$target"
    ;;
  status)
    case "$target" in
      api) status_service "api" "$(api_pid_file)" "http://$API_HOST:$API_PORT" "$(api_log_file)" ;;
      web) status_service "web" "$(web_pid_file)" "http://$WEB_HOST:$WEB_PORT" "$(web_log_file)" ;;
      all)
        status_service "api" "$(api_pid_file)" "http://$API_HOST:$API_PORT" "$(api_log_file)"
        status_service "web" "$(web_pid_file)" "http://$WEB_HOST:$WEB_PORT" "$(web_log_file)"
        ;;
      *) usage; exit 1 ;;
    esac
    ;;
  logs)
    case "$target" in
      api) logs_service "api" "$(api_log_file)" ;;
      web) logs_service "web" "$(web_log_file)" ;;
      all)
        tail -f "$(api_log_file)" "$(web_log_file)"
        ;;
      *) usage; exit 1 ;;
    esac
    ;;
  *)
    usage
    exit 1
    ;;
esac
