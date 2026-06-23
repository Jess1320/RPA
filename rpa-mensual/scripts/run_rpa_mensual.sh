#!/usr/bin/env bash
set -euo pipefail

cd /home/cenate/rpa_cext_diario
source .venv/bin/activate
export ENV_FILE=.env_mensual

python -u RPA_CEXT_PROD_MENSUAL.py

