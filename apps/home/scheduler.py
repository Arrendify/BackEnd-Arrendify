from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from ..home.models import Cotizacion_gen
import boto3
# from django.conf import settings
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME
from datetime import date

def eliminar_vencidos():
    print("Ejecutando eliminación automática...")
    fecha_actual = timezone.now().date()
    print("fecha actual", fecha_actual)
    fecha_vigencia = date(2022, 8, 27)  # Utiliza la fecha de referencia para la comparación
    vencidos = Cotizacion_gen.objects.filter(fecha_vigencia__lt=fecha_vigencia)
    print("vencidos", vencidos)
    for vencido in vencidos:
        eliminar_archivo_s3(vencido.documento_cotizacion.name)
        vencido.delete()

# Eliminar amazon
def eliminar_archivo_s3(file_name):
    print("Eliminado de Amazon")
    s3 = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )

    try:
        s3.delete_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=file_name)
        print("El archivo se eliminó correctamente de S3.")
    except Exception as e:
        print("Error al eliminar el archivo:", str(e))

# Inicia la function
def start_scheduler():
    print("Esta llegando a la funcion automatica")
    scheduler = BackgroundScheduler() # programar y ejecutar tareas en segundo plano
    print("Soy scheduler", scheduler)
    scheduler.add_job(eliminar_vencidos, 'cron', hour=12, minute=59) # Agrega una tarea programada
    print("Elimino")
    scheduler.start() # Inicia la ejecución de las tareas programadas
