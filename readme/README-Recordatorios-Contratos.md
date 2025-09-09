# Sistema de Recordatorios Automáticos para Contratos Próximos a Vencer

## Descripción General

Este sistema permite enviar recordatorios automáticos cuando los contratos de arrendamiento están próximos a vencer. Los recordatorios se envían en fechas específicas (3 meses, 2 meses y 1 mes antes del vencimiento) tanto como notificaciones internas en la plataforma como por correo electrónico.

## Características Principales

- ✅ **Recordatorios automáticos** en fechas específicas (no constantes)
- ✅ **Notificaciones internas** en la página web
- ✅ **Envío por correo electrónico**
- ✅ **Soporte para todos los tipos de contrato**: Fraterna, Semillero, Garza Sada, General
- ✅ **Verificación diaria automática** mediante tarea programada
- ✅ **API REST completa** para gestión desde el frontend

## Componentes del Sistema

### 1. Modelo de Base de Datos

**Tabla:** `notificaciones`

**Campos principales:**
- `tipo_notificacion`: recordatorio_3_meses, recordatorio_2_meses, recordatorio_1_mes
- `tipo_contrato`: fraterna, semillero, garzasada, general
- `titulo`: Título del recordatorio
- `mensaje`: Mensaje detallado del recordatorio
- `fecha_vencimiento_contrato`: Fecha de vencimiento del contrato
- `fecha_programada`: Fecha en que debe enviarse el recordatorio
- `enviado_email`: Control de envío por email
- `leida`: Control de lectura de la notificación

### 2. Comando de Django

**Archivo:** `apps/home/management/commands/verificar_contratos_vencimiento.py`

**Uso manual:**
```bash
# Verificación normal
python manage.py verificar_contratos_vencimiento

# Modo de prueba (no envía emails ni crea notificaciones)
python manage.py verificar_contratos_vencimiento --dry-run

# Forzar envío aunque ya existan recordatorios
python manage.py verificar_contratos_vencimiento --force
```

### 3. API REST Endpoints

**Base URL:** `/api/notificaciones/`

#### Endpoints Disponibles:

- `GET /api/notificaciones/` - Listar todas las notificaciones del usuario
- `GET /api/notificaciones/no_leidas/` - Obtener solo notificaciones no leídas
- `GET /api/notificaciones/resumen/` - Resumen de notificaciones (total, no leídas, urgentes)
- `GET /api/notificaciones/por_contrato/` - Notificaciones agrupadas por tipo de contrato
- `GET /api/notificaciones/proximas_vencer/?dias=30` - Contratos que vencen en X días
- `POST /api/notificaciones/{id}/marcar_leida/` - Marcar notificación como leída
- `POST /api/notificaciones/marcar_todas_leidas/` - Marcar todas como leídas
- `DELETE /api/notificaciones/{id}/` - Eliminar notificación

#### Ejemplos de Respuesta:

**Resumen de notificaciones:**
```json
{
  "total": 15,
  "no_leidas": 8,
  "urgentes": 3,
  "por_tipo": {
    "recordatorio_1_mes": {
      "descripcion": "Recordatorio 1 mes antes",
      "count": 3
    }
  }
}
```

**Notificación individual:**
```json
{
  "id": 1,
  "titulo": "Recordatorio: Contrato próximo a vencer (1 mes)",
  "mensaje": "Le recordamos que su contrato vencerá en 1 mes...",
  "tipo_notificacion": "recordatorio_1_mes",
  "tipo_contrato": "fraterna",
  "fecha_vencimiento_contrato": "2025-10-15",
  "leida": false,
  "contrato_info": {
    "id": 123,
    "tipo": "fraterna",
    "inmueble": "Depto 101",
    "arrendatario": "Juan Pérez",
    "renta": "15000"
  }
}
```

### 4. Tarea Programada (Scheduler)

**Configuración:** Se ejecuta automáticamente todos los días a las 9:00 AM

**Archivo:** `apps/home/scheduler.py`

La tarea se configura automáticamente al iniciar la aplicación Django.

## Configuración y Instalación

### 1. Aplicar Migraciones

```bash
python manage.py makemigrations
python manage.py migrate
```

### 2. Configurar Email (settings.py)

```python
# Configuración de email para envío de recordatorios
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'tu-email@gmail.com'
EMAIL_HOST_PASSWORD = 'tu-password'
DEFAULT_FROM_EMAIL = 'noreply@arrendify.com'
```

### 3. Instalar APScheduler (Opcional)

```bash
pip install apscheduler
```

Si no instalas APScheduler, puedes usar cron jobs del sistema operativo.

### 4. Configurar Cron Job (Alternativa)

```bash
# Editar crontab
crontab -e

# Agregar línea para ejecutar diariamente a las 9:00 AM
0 9 * * * cd /ruta/al/proyecto && python manage.py verificar_contratos_vencimiento
```

## Uso del Sistema

### Para Desarrolladores

#### 1. Crear Notificaciones Manuales

```python
from apps.home.models import Notificacion, FraternaContratos
from django.contrib.auth.models import User

# Crear notificación manual
notificacion = Notificacion.objects.create(
    user=usuario,
    tipo_notificacion='recordatorio_1_mes',
    tipo_contrato='fraterna',
    contrato_fraterna=contrato,
    titulo='Contrato próximo a vencer',
    mensaje='Su contrato vence en 1 mes...',
    fecha_vencimiento_contrato=fecha_vencimiento,
    fecha_programada=date.today()
)
```

#### 2. Consultar Notificaciones

```python
# Notificaciones no leídas del usuario
notificaciones = Notificacion.objects.filter(
    user=request.user,
    leida=False
).order_by('-fecha_creacion')

# Marcar como leída
notificacion.marcar_como_leida()
```

### Para Frontend

#### 1. Obtener Notificaciones

```javascript
// Obtener resumen de notificaciones
fetch('/api/notificaciones/resumen/')
  .then(response => response.json())
  .then(data => {
    console.log(`Tienes ${data.no_leidas} notificaciones no leídas`);
  });

// Obtener notificaciones no leídas
fetch('/api/notificaciones/no_leidas/')
  .then(response => response.json())
  .then(data => {
    data.results.forEach(notif => {
      console.log(notif.titulo);
    });
  });
```

#### 2. Marcar como Leída

```javascript
// Marcar notificación específica como leída
fetch(`/api/notificaciones/${notificationId}/marcar_leida/`, {
  method: 'POST',
  headers: {
    'Authorization': 'Token ' + userToken,
    'Content-Type': 'application/json'
  }
})
.then(response => response.json())
.then(data => {
  console.log('Notificación marcada como leída');
});
```

## Tipos de Contratos Soportados

### 1. Contratos Fraterna
- **Campo de fecha:** `fecha_vigencia`
- **Información mostrada:** Número de departamento, residente, renta

### 2. Contratos Semillero
- **Campo de fecha:** Calculada desde `fecha_celebracion` + `duracion`
- **Información mostrada:** ID de propiedad, arrendatario, renta

### 3. Contratos Garza Sada
- **Campo de fecha:** Calculada desde `fecha_celebracion` + `duracion`
- **Información mostrada:** ID de propiedad, arrendatario, renta

### 4. Contratos Generales
- **Campo de fecha:** `datos_contratos.fecha_vigencia`
- **Información mostrada:** Inmueble, arrendatario

## Cronograma de Recordatorios

| Tiempo antes del vencimiento | Tipo de recordatorio | Acción |
|------------------------------|---------------------|---------|
| 3 meses | `recordatorio_3_meses` | Notificación + Email |
| 2 meses | `recordatorio_2_meses` | Notificación + Email |
| 1 mes | `recordatorio_1_mes` | Notificación + Email |

## Troubleshooting

### Problema: No se envían emails

**Solución:**
1. Verificar configuración de email en `settings.py`
2. Comprobar que el usuario tenga email configurado
3. Revisar logs de errores

### Problema: No se crean notificaciones automáticamente

**Solución:**
1. Verificar que el scheduler esté funcionando
2. Ejecutar manualmente: `python manage.py verificar_contratos_vencimiento --dry-run`
3. Revisar logs del comando

### Problema: Duplicación de notificaciones

**Solución:**
El sistema tiene protección contra duplicados mediante `unique_together`. Si necesitas recrear notificaciones, usa el flag `--force`.

## Logs y Monitoreo

### Verificar Ejecución Manual

```bash
# Ver qué haría sin ejecutar
python manage.py verificar_contratos_vencimiento --dry-run

# Ver logs detallados
python manage.py verificar_contratos_vencimiento --verbosity=2
```

### Logs del Sistema

Los logs se guardan en `Logs/` y incluyen:
- Errores de envío de email
- Contratos procesados
- Notificaciones creadas

## Extensiones Futuras

- [ ] Notificaciones push para móviles
- [ ] Recordatorios personalizables por usuario
- [ ] Integración con WhatsApp
- [ ] Dashboard de métricas de vencimientos
- [ ] Exportación de reportes de vencimientos

## Soporte

Para soporte técnico o reportar bugs, contacta al equipo de desarrollo de Arrendify.
