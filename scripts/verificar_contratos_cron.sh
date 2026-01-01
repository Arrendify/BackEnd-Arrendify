#!/bin/bash
# Script para ejecutar verificación de contratos próximos a vencer
# Configurado para ejecutarse automáticamente en AWS EC2

# ============================================
# CONFIGURACIÓN
# ============================================

# Ruta al proyecto Django (MODIFICAR SEGÚN TU INSTALACIÓN)
PROJECT_DIR="/home/ubuntu/Back-end-wesy"

# Ruta al entorno virtual (MODIFICAR SEGÚN TU INSTALACIÓN)
VENV_DIR="/home/ubuntu/venv"

# Email del administrador para recibir resumen
ADMIN_EMAIL="desarrolloarrendify@gmail.com"

# Archivo de log
LOG_FILE="/var/log/django/verificar_contratos.log"

# ============================================
# SCRIPT
# ============================================

# Crear directorio de logs si no existe
mkdir -p "$(dirname "$LOG_FILE")"

# Timestamp
echo "========================================" >> "$LOG_FILE"
echo "Iniciando verificación de contratos: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# Activar entorno virtual
source "$VENV_DIR/bin/activate"

# Cambiar al directorio del proyecto
cd "$PROJECT_DIR"

# Ejecutar comando Django
python manage.py verificar_contratos_vencimiento --notify-email="$ADMIN_EMAIL" >> "$LOG_FILE" 2>&1

# Capturar código de salida
EXIT_CODE=$?

# Log del resultado
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Verificación completada exitosamente" >> "$LOG_FILE"
else
    echo "❌ Error en la verificación (código: $EXIT_CODE)" >> "$LOG_FILE"
fi

echo "Finalizado: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Desactivar entorno virtual
deactivate

exit $EXIT_CODE
