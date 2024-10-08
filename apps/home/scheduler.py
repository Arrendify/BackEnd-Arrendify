from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.utils import timezone
from ..home.models import Cotizacion_gen
from ..api.models import Notification
from..accounts.models import Post
import boto3
# from django.conf import settings
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME
from datetime import date , timedelta, datetime
#importamos lo necesario para que funciona los avisos de las renovaciones
from ..home.models import FraternaContratos
from ..api.variables import renovacion_fraterna
#correo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from django.core.mail import send_mail
from smtplib import SMTPException
from django.core.files.base import ContentFile
from decouple import config


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

def eliminar_notis():
        try:
            print("Ejecutando eliminación automática de notificaiones viejas...")
            #Sumar dos días a la fecha actual
            now = date.today()
            rango1 = now - timedelta(days=11)
            rango2 = now - timedelta(days=4)
            print(f"el rango de fechas para elimnar es del {rango1} al {rango2}")
            posts = Post.objects.filter(timestamp__range=[rango1, rango2])
            notificaciones = Notification.objects.filter(timestamp__range=[rango1, rango2])
            posts.delete()
            notificaciones.delete()
            print("Se han eliminado los registros viejos")
            # print('notificaiones',notificaciones)
            
        except Exception as e:
            
            print(f"el error es: {e}")

def renovar_contrato():
    try:
        print("Ejecutando Prueba Renovacion")
        fecha_actual = timezone.now().date()
        print("fecha actual", fecha_actual)
        mes = fecha_actual.month + 1
        #fecha_vigencia = date(2022, 8, 27)  # Utiliza la fecha de referencia para la comparación
        vencidos = FraternaContratos.objects.all().filter(fecha_vigencia__icontains = mes)
        print("vencidos mes", vencidos )
        contratos_a_renovar = []
        for vfec in vencidos:
            print("fev.fecha.actual",vfec.fecha_vigencia)
            diference = vfec.fecha_vigencia - fecha_actual

            print(f"diference: {diference} vfec:{vfec.id}", diference)
        
            if diference.days == 31:
                print(f" yo ya me voy a vencer ----- diference: {diference} vfec:{vfec}", diference)
                print("Tienes 30 dias para renovar tu contrato Bro")
                contratos_a_renovar.append(vfec)
                print("soy contratos",contratos_a_renovar)

        for con_ren in contratos_a_renovar:
            # Configura los detalles del correo electrónico
            try:
                remitente = 'pruebas_arrendify@hotmail.com'
                destino = "desarrolloarrendify@gmail.com"
                pdf_html = renovacion_fraterna(con_ren)
                print(destino)

                
                #hacemos una lista destinatarios para enviar el correo
                asunto = f"Recordatorio Renovacion de Poliza {con_ren.residente.nombre_arrendatario}"
                
                # Crea un objeto MIMEMultipart para el correo electrónico
                msg = MIMEMultipart()
                msg['From'] = remitente
                msg['To'] = destino
                msg['Subject'] = asunto
                print("paso objeto mime")
                
                #Evalua si tiene este atributo
                # if hasattr(info, 'fiador'):
                #     print("SOY info.fiador",info.fiador)
                
                # Adjuntar el contenido HTML al mensaje
                msg.attach(MIMEText(pdf_html, 'html'))
                print("pase el msg attach 1")
                # Adjunta el PDF al correo electrónico
                
                # Establece la conexión SMTP y envía el correo electrónico
                smtp_server = 'mail.arrendify.com'
                smtp_port = 587
                smtp_username = config('mine_smtp_u')
                smtp_password = config('mine_smtp_pw')
                with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                    server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                    print("paso1")
                    
                    server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                    print("paso2")
                    
                    server.sendmail(remitente,destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("se envio el correo")
                
            except SMTPException as e:
                print("Error al enviar el correo electrónico:", str(e))

    except Exception as e:
            print(f"el error es: {e}")       
            

# Inicia la function
def start_scheduler():
    print("Esta llegando a la funcion automatica")
    scheduler = BackgroundScheduler() # programar y ejecutar tareas en segundo plano
    print("Soy scheduler", scheduler)
    scheduler.add_job(eliminar_vencidos, 'cron', hour=12, minute=59) # Agrega una tarea programada
    print("Elimino")
    # scheduler.add_job(eliminar_notis, trigger=CronTrigger(day_of_week="wed", hour="20", minute="21"))
    # print("programando la tarea semanal Eliminar notis")
    scheduler.start() # Inicia la ejecución de las tareas programadas

def start_scheduler_notificaciones():
    scheduler_not = BackgroundScheduler() # programar y ejecutar tareas en segundo plano
    print("Programando la tarea semanal Eliminar notis")
    scheduler_not.add_job(renovar_contrato, trigger=CronTrigger(day="31", hour="12", minute="00"))
    scheduler_not.add_job(eliminar_notis, trigger=CronTrigger(day_of_week="sun", hour="14", minute="30"))
    scheduler_not.start() # Inicia la ejecución de las tareas programadas


