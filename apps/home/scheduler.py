"""Centraliza jobs en ensure_scheduler_started() y evita day="31".
Coloca este archivo como apps/home/scheduler.py

Requisitos:
- TIME_ZONE definido en settings (p.ej. 'America/Mexico_City')
- Llamar ensure_scheduler_started() desde HomeAppConfig.ready()
- No usar day="31": los recordatorios mensuales se ejecutan DIARIO y la lógica filtra por 30–31 días.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_EXECUTED

from django.conf import settings
from django.utils import timezone
from django.core.management import call_command

from datetime import date, timedelta
import logging

# ----- Importa tus modelos y helpers reales -----
from ..home.models import Cotizacion_gen, FraternaContratos
from ..api.variables import renovacion_fraterna

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from decouple import config
import boto3

logger = logging.getLogger(__name__)


# ========================= TAREAS ========================= #

def eliminar_archivo_s3(file_name: str):
    s3 = boto3.client(
        's3',
        aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
        aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
    )
    bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
    try:
        if bucket and file_name:
            s3.delete_object(Bucket=bucket, Key=file_name)
            logger.info(f"Archivo eliminado de S3: {file_name}")
    except Exception as e:
        logger.exception(f"Error eliminando de S3 {file_name}: {e}")


def eliminar_vencidos():
    logger.info("Ejecutando eliminación automática de cotizaciones vencidas…")
    hoy = timezone.now().date()
    # Si quieres una referencia fija, cámbiala aquí; de lo contrario compara con hoy
    vencidos = Cotizacion_gen.objects.filter(fecha_vigencia__lt=hoy)
    for v in vencidos:
        try:
            if getattr(v, 'documento_cotizacion', None) and v.documento_cotizacion.name:
                eliminar_archivo_s3(v.documento_cotizacion.name)
            v.delete()
        except Exception:
            logger.exception(f"Error eliminando cotización {v.id}")


def _enviar_correo_html(destino: str, asunto: str, html: str):
    remitente = 'notificaciones@arrendify.com'
    smtp_server = 'mail.arrendify.com'
    smtp_port = 587
    smtp_username = config('mine_smtp_u')
    smtp_password = config('mine_smtp_pw')

    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destino
    msg['Subject'] = asunto
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(remitente, destino, msg.as_string())


def renovar_contrato():
    """Lógica diaria: encuentra contratos que vencen en 30–31 días y notifica.
    Evita repetir correos implementando tu propia marca (ej. campo booleano) si es necesario.
    """
    try:
        hoy = timezone.now().date()
        en_30 = hoy + timedelta(days=30)
        en_31 = hoy + timedelta(days=31)

        contratos = FraternaContratos.objects.filter(
            fecha_vigencia__gte=en_30,
            fecha_vigencia__lte=en_31,
        )

        for con in contratos:
            try:
                html = renovacion_fraterna(con)
                asunto = f"Recordatorio Renovación de Póliza {getattr(con.residente, 'nombre_arrendatario', 'Residente')}"
                destino = "development@arrendify.com"  # reemplaza por el real
                _enviar_correo_html(destino, asunto, html)
                logger.info(f"Notificación enviada para contrato {con.id}")
            except Exception:
                logger.exception(f"Error notificando contrato {getattr(con, 'id', 'N/A')}")
    except Exception:
        logger.exception("Error en renovar_contrato")


def verificar_contratos_vencimiento():
    """Ejecuta el management command diariamente a las 09:00."""
    try:
        call_command('verificar_contratos_vencimiento')
        logger.info(f"Verificación de contratos ejecutada - {timezone.now()}")
    except Exception:
        logger.exception("Error ejecutando verificación de contratos")


# ========================= SCHEDULER ========================= #

def _listener(event):
    if event.exception:
        logger.error(f"Job {event.job_id} falló o se perdió")
    else:
        logger.info(f"Job {event.job_id} ejecutado correctamente")


def ensure_scheduler_started():
    """Crea un scheduler global en settings y registra TODOS los jobs aquí.
    Llamar desde HomeAppConfig.ready().
    """
    tz = getattr(settings, 'TIME_ZONE', 'UTC')

    # Crear si no existe
    if not hasattr(settings, 'SCHEDULER'):
        settings.SCHEDULER = BackgroundScheduler(timezone=tz)

    sched = settings.SCHEDULER

    # Listener para logs
    sched.add_listener(_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_EXECUTED)

    # ---- Jobs DIARIOS ---- #

    # Verificación diaria 09:00
    sched.add_job(
        verificar_contratos_vencimiento,
        trigger=CronTrigger(hour=9, minute=0, timezone=tz),
        id='verificar_contratos_vencimiento',
        name='Verificación diaria de contratos próximos a vencer',
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # Renovaciones (antes era day="31"): ahora DIARIO a las 09:05
    sched.add_job(
        renovar_contrato,
        trigger=CronTrigger(hour=9, minute=5, timezone=tz),
        id='renovar_contrato_diario',
        name='Recordatorios de renovación (ventana 30–31 días)',
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # Limpieza de cotizaciones vencidas DIARIO 12:59
    sched.add_job(
        eliminar_vencidos,
        trigger=CronTrigger(hour=12, minute=59, timezone=tz),
        id='eliminar_vencidos_diario',
        name='Eliminar cotizaciones vencidas',
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # Inicia si no está corriendo
    if not getattr(sched, 'running', False):
        sched.start()
        logger.warning("Scheduler iniciado - jobs diarios registrados")
    else:
        logger.info("Scheduler ya estaba iniciado")
