#!/usr/bin/env bash
set -Eeuo pipefail

export TZ="${TZ:-America/Lima}"
export PYTHONUNBUFFERED=1
export ENV_FILE="${ENV_FILE:-.env}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
export RPA_USERS_ENV_FILE="${RPA_USERS_ENV_FILE:-$PROJECT_DIR/../shared/config/.env_usuarios}"
export CHROME_PROFILE_BASE_DIR="${CHROME_PROFILE_BASE_DIR:-$PROJECT_DIR/tmp/chrome_profiles}"
export CHROME_PROFILE_MAX_AGE_HOURS="${CHROME_PROFILE_MAX_AGE_HOURS:-12}"
PYTHON_BIN="${PYTHON_BIN:-/home/cenate/rpa_cext_diario/.venv/bin/python}"
SCRIPT_PATH="$PROJECT_DIR/src/RPA_PROG_PROF.py"
LOCK_DIR="${LOCK_DIR:-/tmp/rpa_prog_prof.lock}"
ORCH_LOG_DIR="$PROJECT_DIR/orchestrator_logs"
ORCH_LOG_FILE="$ORCH_LOG_DIR/orchestrator_$(date +%Y%m%d).log"

mkdir -p "$ORCH_LOG_DIR" "$CHROME_PROFILE_BASE_DIR"
exec >>"$ORCH_LOG_FILE" 2>&1

echo "============================================================"
echo "$(date '+%F %T') | ORCH_START | rpa_prog_prof"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "$(date '+%F %T') | ERROR | Python del venv no encontrado: $PYTHON_BIN"
  exit 21
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "$(date '+%F %T') | ERROR | Script no encontrado: $SCRIPT_PATH"
  exit 22
fi

if [[ ! -f "$PROJECT_DIR/$ENV_FILE" && ! -f "$ENV_FILE" ]]; then
  echo "$(date '+%F %T') | ERROR | ENV_FILE no encontrado: $ENV_FILE"
  exit 23
fi

if mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "$$" > "$LOCK_DIR/pid"
  trap 'rm -rf "$LOCK_DIR"' EXIT
else
  if [[ -f "$LOCK_DIR/pid" ]] && kill -0 "$(cat "$LOCK_DIR/pid")" 2>/dev/null; then
    echo "$(date '+%F %T') | SKIP | Ya existe una ejecucion en curso"
    exit 24
  fi
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR"
  echo "$$" > "$LOCK_DIR/pid"
  trap 'rm -rf "$LOCK_DIR"' EXIT
fi

cd "$PROJECT_DIR"

set +e
"$PYTHON_BIN" -u "$SCRIPT_PATH"
RC=$?
set -e

echo "$(date '+%F %T') | ORCH_END | exit_code=$RC"
exit "$RC"
