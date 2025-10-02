#!/usr/bin/env bash
set -e

# Rutas en EC2
PROJECT_DIR="/home/ubuntu/BackEnd-Arrendify"
VENV_DIR="/home/ubuntu/env"

# Logs
LOG_DIR="$PROJECT_DIR/Logs"
LOG_FILE="$LOG_DIR/verificar_contratos.log"

# Entorno Django
export DJANGO_SETTINGS_MODULE="core.settings"
export PYTHONUNBUFFERED=1

# PATH para cron
export PATH="$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

mkdir -p "$LOG_DIR"

timestamp() {
  date "+[%d-%m-%Y %H:%M:%S]"
}

echo "$(timestamp) Iniciando verificar_contratos_vencimiento $*" >> "$LOG_FILE" 2>&1

# Activar venv y ejecutar
source "$VENV_DIR/bin/activate" >> "$LOG_FILE" 2>&1
cd "$PROJECT_DIR"

python manage.py verificar_contratos_vencimiento "$@" >> "$LOG_FILE" 2>&1
EXITCODE=$?

echo "$(timestamp) Finalizado. ExitCode=${EXITCODE}" >> "$LOG_FILE" 2>&1
exit $EXITCODE