#!/usr/bin/env bash
# Start the Python bridge. Loads bridge/.env if present.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/bridge"

if [ ! -d ".venv" ]; then
  python3.11 -m venv .venv
  ./.venv/bin/pip install -e ".[dev]"
fi

# shellcheck disable=SC1091
[ -f .env ] && set -a && source .env && set +a

./.venv/bin/python -m bridge.server "$@"
