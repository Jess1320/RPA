#!/usr/bin/env bash
set -Eeuo pipefail

export TZ=America/Lima
export HOME=/home/cenate
export ENV_FILE="${ENV_FILE:-.env}"

PROJECT_DIR="/home/cenate/rpa_cext_diario"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
SCRIPT_PATH="$PROJECT_DIR/RPA_CEXT_PROD_DIARIO.py"
LOCK_FILE="/tmp/rpa_cext_diario.lock"
SHARE_PATH="/mnt/abandonos/BASES_DIARIAS"
ORCH_LOG_DIR="$PROJECT_DIR/orchestrator_logs"
ORCH_LOG_FILE="$ORCH_LOG_DIR/orchestrator_$(date +%Y%m%d).log"
PREFLIGHT_RETRY_EXIT_CODE="${PREFLIGHT_RETRY_EXIT_CODE:-4}"
PREFLIGHT_RETRY_MAX="${PREFLIGHT_RETRY_MAX:-1}"
PREFLIGHT_RETRY_DELAY_SECONDS="${PREFLIGHT_RETRY_DELAY_SECONDS:-90}"

mkdir -p "$ORCH_LOG_DIR"
exec >>"$ORCH_LOG_FILE" 2>&1

echo "============================================================"
echo "$(date '+%F %T') | ORCH_START | RPA_DIARIO"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "$(date '+%F %T') | ERROR | Python del venv no encontrado: $PYTHON_BIN"
  exit 21
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "$(date '+%F %T') | ERROR | Script no encontrado: $SCRIPT_PATH"
  exit 22
fi

if [[ ! -d "$SHARE_PATH" || ! -w "$SHARE_PATH" ]]; then
  echo "$(date '+%F %T') | ERROR | La ruta compartida no esta disponible para escritura: $SHARE_PATH"
  exit 23
fi

cd "$PROJECT_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date '+%F %T') | SKIP | Ya existe una ejecucion en curso"
  exit 24
fi

ATTEMPT=1
MAX_ATTEMPTS=$((PREFLIGHT_RETRY_MAX + 1))

while true; do
  echo "$(date '+%F %T') | RUN | attempt=$ATTEMPT/$MAX_ATTEMPTS | Ejecutando $SCRIPT_PATH"

  set +e
  "$PYTHON_BIN" -u "$SCRIPT_PATH"
  RC=$?
  set -e

  echo "$(date '+%F %T') | ORCH_ATTEMPT_END | attempt=$ATTEMPT/$MAX_ATTEMPTS | exit_code=$RC"

  if [[ "$RC" -eq "$PREFLIGHT_RETRY_EXIT_CODE" && "$ATTEMPT" -lt "$MAX_ATTEMPTS" ]]; then
    echo "$(date '+%F %T') | ORCH_RETRY | reason=CHROMEDRIVER_PREFLIGHT_FAIL | sleep_seconds=$PREFLIGHT_RETRY_DELAY_SECONDS"
    sleep "$PREFLIGHT_RETRY_DELAY_SECONDS"
    ATTEMPT=$((ATTEMPT + 1))
    continue
  fi

  break
done

echo "$(date '+%F %T') | ORCH_END | attempts=$ATTEMPT | exit_code=$RC"
exit "$RC"
