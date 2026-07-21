#!/usr/bin/env bash
set -Eeuo pipefail

export TZ="${TZ:-America/Lima}"
export PYTHONUNBUFFERED=1
export ENV_FILE="${ENV_FILE:-.env}"

PROJECT_DIR="${PROJECT_DIR:-/home/cenate/rpa_orquestador_cronicos}"
PYTHON_BIN="${PYTHON_BIN:-/home/cenate/rpa_cext_diario/.venv/bin/python}"
SCRIPT_PATH="$PROJECT_DIR/src/orquestador_cronicos.py"
LOCK_FILE="${LOCK_FILE:-/tmp/rpa_orquestador_cronicos.lock}"
ORCH_LOG_DIR="$PROJECT_DIR/orchestrator_logs"
ORCH_LOG_FILE="$ORCH_LOG_DIR/orchestrator_cronicos_$(date +%Y%m%d).log"

mkdir -p "$ORCH_LOG_DIR"
exec >>"$ORCH_LOG_FILE" 2>&1

echo "============================================================"
echo "$(date '+%F %T') | ORCH_WRAPPER_START | RPA_ORQUESTADOR_CRONICOS"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "$(date '+%F %T') | ERROR | Python no encontrado: $PYTHON_BIN"
  exit 21
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "$(date '+%F %T') | ERROR | Script no encontrado: $SCRIPT_PATH"
  exit 22
fi

cd "$PROJECT_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date '+%F %T') | SKIP | Ya existe una ejecucion del orquestador en curso"
  exit 24
fi

set +e
"$PYTHON_BIN" -u "$SCRIPT_PATH"
RC=$?
set -e

echo "$(date '+%F %T') | ORCH_WRAPPER_END | exit_code=$RC"
exit "$RC"
