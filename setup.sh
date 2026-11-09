#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if command -v python3.12 >/dev/null 2>&1; then
  PROCTOR_PYTHON=python3.12
else
  PROCTOR_PYTHON=python3
fi
"$PROCTOR_PYTHON" -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,14), "Install Python 3.11, 3.12, or 3.13"'
"$PROCTOR_PYTHON" -m venv .venv
.venv/bin/python -m pip install -c requirements.lock -e '.[test]'
.venv/bin/python -m screenproctor.cli prepare-models --models models
.venv/bin/python -m pytest -q
echo 'Setup complete. Start the UI with ./run.sh'
