#!/usr/bin/env bash
# Run MH5 backend pytest suites by layer.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-python3}"
if [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
fi

run() {
  echo "==> $*"
  "$PY" -m pytest "$@"
}

case "${1:-all}" in
  unit)        run tests/unit -m unit ;;
  integration) run tests/integration -m integration ;;
  regression)  run tests/regression -m regression ;;
  functional)  run tests/functional -m functional ;;
  e2e)         run tests/e2e -m e2e ;;
  fast)        run tests/unit tests/regression -m "unit or regression" ;;
  all)         run tests/ ;;
  *)
    echo "Usage: $0 {unit|integration|regression|functional|e2e|fast|all}"
    exit 1
    ;;
esac
