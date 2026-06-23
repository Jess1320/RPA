#!/usr/bin/env bash
set -Eeuo pipefail

export TZ=America/Lima
export HOME=/home/cenate
export ENV_FILE=.env_mensual

PROJECT_DIR="/home/cenate/rpa_cext_diario"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
SCRIPT_PATH="$PROJECT_DIR/RPA_CEXT_PROD_MENSUAL.py"
LOCK_FILE="/tmp/rpa_cext_mensual.lock"
SHARE_PATHS=(
  "/mnt/comp_observatorio/BI_2025/Base_Consulta_Externa_2026"
  "/mnt/abandonos/BASES"
)
ORCH_LOG_DIR="$PROJECT_DIR/orchestrator_logs"
ORCH_LOG_FILE="$ORCH_LOG_DIR/orchestrator_mensual_$(date +%Y%m%d).log"

mkdir -p "$ORCH_LOG_DIR"
exec >>"$ORCH_LOG_FILE" 2>&1

echo "============================================================"
echo "$(date '+%F %T') | ORCH_START | RPA_MENSUAL"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "$(date '+%F %T') | ERROR | Python del venv no encontrado: $PYTHON_BIN"
  exit 21
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "$(date '+%F %T') | ERROR | Script no encontrado: $SCRIPT_PATH"
  exit 22
fi

for share_path in "${SHARE_PATHS[@]}"; do
  if [[ ! -d "$share_path" || ! -w "$share_path" ]]; then
    echo "$(date '+%F %T') | ERROR | Ruta compartida no disponible para escritura: $share_path"
    exit 23
  fi
done

cd "$PROJECT_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date '+%F %T') | SKIP | Ya existe una ejecucion mensual en curso"
  exit 24
fi

echo "$(date '+%F %T') | RUN | Ejecutando $SCRIPT_PATH"
"$PYTHON_BIN" -u "$SCRIPT_PATH"
RC=$?

echo "$(date '+%F %T') | ORCH_END | exit_code=$RC"
exit "$RC"
