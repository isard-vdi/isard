#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Install it from https://docs.astral.sh/uv/ and re-run." >&2
    exit 1
fi

uv venv
uv pip install -e .

VENV="$(pwd)/.venv"

cat <<EOF

============================================================
  Setup complete.

  The command is:  anonymize-db   (with a HYPHEN, not _)

  Run it one of these ways:

    1) Without activating the venv, from this directory:
         uv run anonymize-db --help

    2) Activate the venv (per shell), then call directly:
         source ${VENV}/bin/activate
         anonymize-db --help

  See USAGE.md for full options.
============================================================
EOF
