#!/bin/sh
set -eu

REPO_URL="${H59_REPO_URL:-git+https://github.com/remi-td/h59.git}"
UV_BIN="${UV_BIN:-uv}"

ensure_uv() {
    if command -v "$UV_BIN" >/dev/null 2>&1; then
        return 0
    fi

    echo "uv not found; installing uv..." >&2
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "error: neither curl nor wget is available, and uv is not installed" >&2
        exit 1
    fi

    UV_FALLBACK="${HOME}/.local/bin/uv"
    if [ -x "$UV_FALLBACK" ]; then
        UV_BIN="$UV_FALLBACK"
    elif ! command -v uv >/dev/null 2>&1; then
        echo "error: uv installation finished but uv is still not on PATH" >&2
        echo "run: ~/.local/bin/uv tool update-shell" >&2
        exit 1
    else
        UV_BIN="uv"
    fi
}

ensure_uv

"$UV_BIN" tool install --force "$REPO_URL"
"$UV_BIN" tool update-shell >/dev/null 2>&1 || true

BIN_DIR="$("$UV_BIN" tool dir --bin 2>/dev/null || true)"
if [ -n "$BIN_DIR" ]; then
    echo "Installed h59 into $BIN_DIR"
else
    echo "Installed h59"
fi
echo "Run: h59 --help"
