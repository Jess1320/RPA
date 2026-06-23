#!/usr/bin/env bash
set -Eeuo pipefail

export TZ=America/Lima
export HOME=/home/cenate
export ENV_FILE="${ENV_FILE:-.env}"

PROJECT_DIR="/home/cenate/rpa_cext_diario"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
SCRIPT_PATH="$PROJECT_DIR/RPA_CEXT_PROD_DIARIO.py"
LOCK_FILE="/tmp/rpa_cext_diario.lock"
SHARE_MOUNT="/mnt/abandonos"
ORCH_LOG_DIR="$PROJECT_DIR/orchestrator_logs"
ORCH_LOG_FILE="$ORCH_LOG_DIR/orchestrator_$(date +%Y%m%d).log"

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

if ! mountpoint -q "$SHARE_MOUNT"; then
  echo "$(date '+%F %T') | ERROR | La ruta compartida no esta montada: $SHARE_MOUNT"
  exit 23
fi

cd "$PROJECT_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date '+%F %T') | SKIP | Ya existe una ejecucion en curso"
  exit 24
fi

echo "$(date '+%F %T') | RUN | Ejecutando $SCRIPT_PATH"
"$PYTHON_BIN" -u "$SCRIPT_PATH"
RC=$?

echo "$(date '+%F %T') | ORCH_END | exit_code=$RC"
exit "$RC"
