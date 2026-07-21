#!/usr/bin/env bash
set -Eeuo pipefail

export TZ=America/Lima
export HOME=/home/cenate
export ENV_FILE="${ENV_FILE:-.env}"
export DOWNLOAD_ONLY="${DOWNLOAD_ONLY:-true}"

PROJECT_DIR="${PROJECT_DIR:-/home/cenate/rpa_mensual_cronicos}"
PYTHON_BIN="${PYTHON_BIN:-/home/cenate/rpa_cext_diario/.venv/bin/python}"
SCRIPT_PATH="$PROJECT_DIR/src/RPA_CEXT_CRONICOS_MENSUAL.py"
LOCK_FILE="/tmp/rpa_mensual_cronicos.lock"
ENV_PATH="$PROJECT_DIR/$ENV_FILE"
SHARE_PATHS=()
ORCH_LOG_DIR="$PROJECT_DIR/orchestrator_logs"
ORCH_LOG_FILE="$ORCH_LOG_DIR/orchestrator_mensual_cronicos_$(date +%Y%m%d).log"

mkdir -p "$ORCH_LOG_DIR"
exec >>"$ORCH_LOG_FILE" 2>&1

echo "============================================================"
echo "$(date '+%F %T') | ORCH_START | RPA_MENSUAL_CRONICOS"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "$(date '+%F %T') | ERROR | Python del venv no encontrado: $PYTHON_BIN"
  exit 21
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "$(date '+%F %T') | ERROR | Script no encontrado: $SCRIPT_PATH"
  exit 22
fi

env_value() {
  local key="$1"
  [[ -f "$ENV_PATH" ]] || return 0
  grep -m1 "^${key}=" "$ENV_PATH" | cut -d= -f2- | sed 's/\r$//' || true
}

FINAL_PUBLISH_DIR_VALUE="$(env_value FINAL_PUBLISH_DIR)"
FINAL_PUBLISH_MIRRORS_VALUE="$(env_value FINAL_PUBLISH_MIRRORS)"

if [[ -n "$FINAL_PUBLISH_DIR_VALUE" ]]; then
  SHARE_PATHS+=("$FINAL_PUBLISH_DIR_VALUE")
fi

if [[ -n "$FINAL_PUBLISH_MIRRORS_VALUE" ]]; then
  IFS=',' read -r -a MIRROR_PATHS <<< "$FINAL_PUBLISH_MIRRORS_VALUE"
  for mirror_path in "${MIRROR_PATHS[@]}"; do
    mirror_path="$(echo "$mirror_path" | xargs)"
    [[ -n "$mirror_path" ]] && SHARE_PATHS+=("$mirror_path")
  done
fi

if [[ "${#SHARE_PATHS[@]}" -eq 0 ]]; then
  SHARE_PATHS=(
    "//10.0.88.100/bbdd_rpa/Base_Consulta_Externa_2026"
  )
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
