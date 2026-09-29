#!/usr/bin/env bash
# Whole experiment in one go: venv -> install -> tests -> key check -> batch run -> report.
#
#   ./run-all.sh              100 runs
#   ./run-all.sh 20           20 runs
#   ./run-all.sh 50 --seed 1234 --scenario contradictory   extra args go to run.py
#
# Set SKIP_TESTS=1 to skip pytest.
set -euo pipefail
cd "$(dirname "$0")"

RUNS="${1:-100}"
[[ $# -gt 0 ]] && shift
[[ "$RUNS" =~ ^[0-9]+$ && "$RUNS" -ge 1 ]] || { echo "usage: $0 [runs] [run.py args...]" >&2; exit 1; }

step() { printf '\n== %s ==\n' "$1"; }

step "1/5 Python environment"
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  step "2/5 Unit tests (offline)"
  python -m pytest -q
else
  step "2/5 Unit tests (skipped)"
fi

step "3/5 Jev configuration"
python - <<'PY' || exit 2
import sys
from jev.client import ConfigError, load_config
try:
    c = load_config()
except ConfigError as e:
    sys.exit(f"error: {e}")
print("OK: key found, model", c.model)
PY

step "4/5 Experiment ($RUNS runs)"
python run.py --runs "$RUNS" "$@"

step "5/5 Report"
python report.py
