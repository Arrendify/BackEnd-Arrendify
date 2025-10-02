#!/usr/bin/env bash
set -euo pipefail

# Rutas en EC2
PROJECT_DIR="/home/ubuntu/BackEnd-Arrendify"
VENV_DIR="/home/ubuntu/env"

# Logs
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/verificar_contratos.log"

# Entorno Django (ajusta si usas otro settings)
export DJANGO_SETTINGS_MODULE="config.settings.prod"
export PYTHONUNBUFFERED=1

# Opcional: PATH para cron
# export PATH="$VENV_DIR/bin:/usr/local/bin:/usr/bin:$PATH"

# Opcional: cargar .env si lo usas
# if [ -f "$PROJECT_DIR/.env" ]; then
#   set -a
#   . "$PROJECT_DIR/.env"
#   set +a
# fi

mkdir -p "$LOG_DIR"

timestamp() {
  date "+[%d-%m-%Y %H:%M:%S]"
}

echo "$(timestamp) Iniciando verificar_contratos_vencimiento $*" >> "$LOG_FILE"

# Activar venv y ejecutar
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$PROJECT_DIR"

python manage.py verificar_contratos_vencimiento "$@" >> "$LOG_FILE" 2>&1
EXITCODE=$?

echo "$(timestamp) Finalizado. ExitCode=${EXITCODE}" >> "$LOG_FILE"
exit $EXITCODE