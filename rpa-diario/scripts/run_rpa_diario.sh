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
CHROME_TMP_ROOT="${CHROME_TMP_ROOT:-$PROJECT_DIR/tmp_chrome}"
PREFLIGHT_RETRY_EXIT_CODE="${PREFLIGHT_RETRY_EXIT_CODE:-4}"
PREFLIGHT_RETRY_MAX="${PREFLIGHT_RETRY_MAX:-2}"
PREFLIGHT_RETRY_DELAY_SECONDS="${PREFLIGHT_RETRY_DELAY_SECONDS:-120}"

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

cleanup_chrome_before_retry() {
  echo "$(date '+%F %T') | ORCH_CHROME_CLEANUP_START | root=$CHROME_TMP_ROOT"

  case "$CHROME_TMP_ROOT" in
    "$PROJECT_DIR"/tmp_chrome*) ;;
    *)
      echo "$(date '+%F %T') | ORCH_CHROME_CLEANUP_SKIP | root_fuera_de_proyecto=$CHROME_TMP_ROOT"
      return 0
      ;;
  esac

  pkill -u "$(id -u)" -f "$CHROME_TMP_ROOT/chrome-profile-" 2>/dev/null || true
  pkill -u "$(id -u)" -f "[c]hromedriver" 2>/dev/null || true

  if [[ -d "$CHROME_TMP_ROOT" ]]; then
    find "$CHROME_TMP_ROOT" -maxdepth 1 -type d -name "chrome-profile-preflight-*" -mmin +0 -print -exec rm -rf {} + 2>/dev/null || true
  fi

  echo "$(date '+%F %T') | ORCH_CHROME_CLEANUP_END"
}

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
    cleanup_chrome_before_retry
    sleep "$PREFLIGHT_RETRY_DELAY_SECONDS"
    ATTEMPT=$((ATTEMPT + 1))
    continue
  fi

  break
done

echo "$(date '+%F %T') | ORCH_END | attempts=$ATTEMPT | exit_code=$RC"
exit "$RC"
