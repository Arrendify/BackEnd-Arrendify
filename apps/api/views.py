from django.shortcuts import render, get_object_or_404
from rest_framework.response import Response
from .serializers import *
from rest_framework.decorators import api_view


from ..home.models import *
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework import viewsets
from django.db.models import Subquery

from apps.authentication.authentication_mixins import Authentication

from rest_framework.decorators import action
from django.core.paginator import Paginator

#s3
import boto3
from botocore.exceptions import ClientError
from botocore.exceptions import NoCredentialsError
from django.db.models import Q
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
#PDF
#weasyprint
from weasyprint import HTML, CSS
from django.template.loader import render_to_string
from django.template.loader import get_template
from django.http import HttpResponse

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
#pdf reduccion
import requests
from django.core.files.storage import default_storage

# Para autenticacion
import os
import json
#variables
from .variables import *
#Legal
from datetime import date
from num2words import num2words
# Token
from rest_framework.authtoken.models import Token
from django.contrib.auth.tokens import default_token_generator
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
# Password
from django.utils import timezone
from datetime import timedelta

#  Importacion contacto
from .plantillas_mensaje_contacto.mensaje_contacto import Contacto
from datetime import datetime

#nuevo modelo user
from ..accounts.models import CustomUser, Post
User = CustomUser

#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)

# Heath Check
from django.http import JsonResponse

#LIBRERIAS PARA NOTIFICAR
#loader model
from swapper import load_model
#buit-in signals
from django.db.models.signals import post_save
#signals 
from .utils.signals import notificar 

# Create your views here.
# ----------------------------------Metodos Extras----------------------------------------------- #
def eliminar_archivo_s3(file_name):
    s3 = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
             )
    print("soy el valor de s3",s3.__dict__)
   
    try:
        print("entre en el Try")
        s3.delete_object(Bucket="arrendifystorage", Key=f"static/{str(file_name)}")
        print("El archivo se eliminó correctamente de S3.")
    except NoCredentialsError:
        print("No se encontraron las credenciales de AWS.")
# ----------------------------------pagina 404----------------------------------------------- #
def pagina_404(request):
    return render(request, 'home/page-404.html')

# ----------------------------------Health Check----------------------------------------------- #
@api_view(['GET'])
def health_check(request):
    return JsonResponse({"status": "OK"})
# ----------------------------------Metodo para disparar notificaciones de manera individual----------------------------------------------- #
def send_noti(self, request, *args, **kwargs):
        print("entramos al metodo de notificaiones independientes")
        print("lo que llega es en self",self)
        print("lo que llega es en kwargs",kwargs["title"])
        print("lo que llega es en kwargs",kwargs['text'])
        print("lo que llega es en kwargs",kwargs['url'])
        
        print("request: ",request.data)
        print("")
        actor = User.objects.all().filter(username = 'Arrendatario1').first()
        print("request verbo",kwargs["title"])
        
        try:
            print("entramos en el tri")
            user_session = request.user
            print("el que envia usuario es: ", user_session)
            print("el que recibe actor es: ",actor)
          
            data_noti = {'title':kwargs["title"], 'text':kwargs["text"], 'user':user_session.id, 'url':kwargs['url']}
          
            print("Post serializer a continuacion")
            post_serializer = PostSerializer(data=data_noti) #Usa el serializer_class
            if post_serializer.is_valid(raise_exception=True):
                print("hola es valido el serializer")
                datos = post_serializer.save(user = actor)
                print('datos',datos)
                return Response({'Post': post_serializer.data}, status=status.HTTP_201_CREATED)
            
            else:
                print("Error en validacion", post_serializer.errors)
                return Response({'errors': post_serializer.errors})
            
        except Exception as e:
            print("error",e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# ----------------------------------Metodo para disparar notificaciones a varios destinos----------------------------------------------- #
def send_noti_varios(self, request, *args, **kwargs):
        print("entramos al metodo de notificaiones independientes")
        print("lo que llega es en self",self)
        print("lo que llega es en kwargs",kwargs["title"])
        print("lo que llega es en kwargs",kwargs['text'])
        print("lo que llega es en kwargs",kwargs['url'])
        print("request: ",request.data)
        print("")
        
        print("request verbo",kwargs["title"])
        try:
            print("entramos en el try")
            user_session = request.user
            print("el que envia usuario es: ", user_session)
            
            destinatarios = User.objects.all().filter(pertenece_a = 'Arrendify')
            
            print("actores:",destinatarios)
            
            data_noti = {'title':kwargs["title"], 'text':kwargs["text"], 'user':user_session.id, 'url':kwargs['url']}
            print("Post serializer a continuacion")
        
            for destiny in destinatarios:
                post_serializer = PostSerializer(data=data_noti) #Usa el serializer_class
                if post_serializer.is_valid(raise_exception=True):
                    print("hola")
                    print("destinyes",destiny)
                    datos = post_serializer.save(user = destiny)
                    print("Guardado residente")
                    print('datos',datos)
                else:
                    print("Error en validacion",post_serializer.errors)
            return Response({'Post': post_serializer.data}, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print("error",e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# ----------------------------------Fin de metodos----------------------------------------------- 
    
# ---------------------------------- Investigacion ---------------------------------- #  
class investigaciones(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Arrendatario.objects.all()
    serializer_class = InquilinoSerializers
   
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        if user_session.username == "Arrendatario1" or user_session.username == "Legal" or  user_session.username == "Investigacion" or user_session.username == "AndresMtzO" or user_session.username == "MIRIAM" or user_session.username == "jon_admin" or user_session.username == "SUArrendify" or user_session.username == "Becarios":
            print("Si eres el elegido")
            qs = request.GET.get('nombre')     
            try:
                if qs:
                    inquilino = Arrendatario.objects.all().order_by('-id')
                    serializer = InquilinoSerializers(inquilino, many=True)                    
                    return Response(serializer.data)
                    
                else:
                        print("Esta entrando a listar inquilino desde invetigacion")
                        print("sin barra de busqueda")
                        #todo el codigo comentado es el filtro para separar las investigaciones de francis con las demas que haya 
                        # francis = User.objects.all().filter(name_inmobiliaria = "Francis Calete").first()
                        # inquilino = Arrendatario.objects.all().filter(user_id = francis.id)
                        # print("excluimos el resultado:",inquilino)
                        # id_inq = []
                        # for inq in inquilino:
                        #     id_inq.append(inq.id)
                        # investigar = Investigacion.objects.all().exclude(inquilino__in = id_inq)
                        investigar = Arrendatario.objects.all().order_by('-id')
                        serializer = InquilinoSerializers(investigar, many=True)
                        return Response(serializer.data)
                
                #    return Response(serializer.data, status= status.HTTP_200_OK)
            except Exception as e:
                print(f"el error es: {e}")
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
                return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'No estas autorizado'}, status=status.HTTP_401_UNAUTHORIZED)
    
    def investigacion_francis(self, request, *args, **kwargs):
        user_session = request.user       
        if user_session.username == "Arrendatario1" or user_session.username == "Legal":
            print("Si eres el elegido")
            qs = request.GET.get('nombre')     
            try:
                if qs:
                    inquilino = Arrendatario.objects.all().filter(nombre__icontains = qs)
                    id_inq = []
                    for inq in inquilino:
                        id_inq.append(inq.id)
                    investigar = Investigacion.objects.all().filter(inquilino__in = id_inq)
                    serializer = self.get_serializer(investigar, many=True)
                    return Response(serializer.data)
                    
                else:
                        print("Esta entrando a listar inquilino desde investigacion francis calete")
                        francis = User.objects.all().filter(name_inmobiliaria = "Francis Calete").first()
                        print(francis)
                        print(francis.id)
                        inquilino = Arrendatario.objects.all().filter(user_id = francis.id)
                        print(inquilino)
                        id_inq = []
                        for inq in inquilino:
                            id_inq.append(inq.id)
                        investigar = Investigacion.objects.all().filter(inquilino__in = id_inq)
                        # investigar =  Investigacion.objects.filter(user_id = user_session)
                        serializer = self.get_serializer(investigar, many=True)
                        return Response(serializer.data)
                
                #    return Response(serializer.data, status= status.HTTP_200_OK)
            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'No estas autorizado'}, status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        pass
        # try:
        #     print("Esta entrando a actualizar inv")
        #     partial = kwargs.pop('partial', False)
        #     print("partials",partial)
        #     print("soy el request",request.data)
        #     print("soy el status que llega",request.data["status"])
        #     instance = self.get_object()
        #     print("instance",instance)
        #     print("id",instance.id)
            
        #     #Consulata para obtener el inquilino y establecemos fecha de hoy
        #     today = date.today().strftime('%d/%m/%Y')
        #     inquilino_mod =  Arrendatario.objects.all().filter(id = instance.id)
        #     primer_inquilino = inquilino_mod.first()
        #     print("soy nombre de inquilino",primer_inquilino.nombre)
        #     #Consulata para obtener el fiador confirme a la fk y releated name 
        #     fiador = primer_inquilino.aval.all().first()
        #     #primero comprobar si hay aval
        #     if fiador:
        #         print("si hay fiador")
        #         print("yo soy info de los fiadores",fiador.__dict__)
                
        #         #si hay fiador hacemos el proceso de aprobar           
        #         if request.data["status"] == "Aprobado":
        #             print("APROBADO")
        #             primer_inquilino.status = "1"
        #             print("status cambiado",primer_inquilino.status)
        #             primer_inquilino.save()
        #             print("fiador.fiador_obligado",fiador.fiador_obligado)
        #             #asignacion de variables dependiendo del Regimen fiscal del Fiador
        #             if primer_inquilino.p_fom == "Persona Moral":
        #                 print("Soy persona moral")
        #             else: 
                        
        #                 if fiador.fiador_obligado == "Obligado Solidario Persona Moral":
        #                     print("No agregamos nada")
        #                 else:
        #                     ingreso = request.data["roe_inquilino"]
        #                     ine_inquilino = request.data["ine_inquilino"]
        #                     ine_fiador = request.data["ine_fiador"]
                            
        #                     if fiador.recibos == "Si":
        #                         ingreso_obligado = "Recibo de nómina"   
        #                     else:
        #                         ingreso_obligado = "Estado de cuenta" 
        #                         #combierte el salario mensual a letra prospecto
                                
        #                     number = primer_inquilino.ingreso_men
        #                     number = int(number)
        #                     text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
        #                     text_representation = text_representation.capitalize()
        #                     #combierte el salario mensual de aval
        #                     number_2 = fiador.ingreso_men_fiador
        #                     number_2 = int(number_2)
        #                     text_representation2 = num2words(number_2, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
        #                     text_representation2 = text_representation2.capitalize()
        #             print("Pasamo el if de obligado ")
                
        #             #hacer el proceso de enviar archivo especial para persona moral
        #             if primer_inquilino.p_fom == "Persona Moral":
        #                 print("soy persona moral")
        #                 archivo = request.data["doc_rec"]                        
        #                 archivo = request.data["doc_rec"]
        #                 comentario = "nada"
        #                 self.enviar_archivo(archivo,primer_inquilino,comentario)
                           
        #             else:    
        #                 if fiador.fiador_obligado == "Fiador Solidario":
        #                     print("Hola soy Fiador Solidario")
        #                     context = {
        #                     'info':primer_inquilino,
        #                     'fiador':fiador,
        #                     'fecha_actual':today,
        #                     'ine_inquilino':ine_inquilino,
        #                     'ine_fiador':ine_fiador,
        #                     'number': number,
        #                     'number_2': number_2,
        #                     'text_representation': text_representation,
        #                     'text_representation2': text_representation2,
        #                     'ingreso':ingreso,
        #                     'ingreso_obligado':ingreso_obligado,
        #                     'template':"home/aprobado_fiador.html",
        #                     }
        #                     self.generar_archivo(context)  
                        
        #                 elif fiador.fiador_obligado == "Obligado Solidario Persona Fisica":
        #                     context = {
        #                     'info':primer_inquilino,
        #                     'fiador':fiador,
        #                     'fecha_actual':today,
        #                     'ine_inquilino':ine_inquilino,
        #                     'ine_fiador':ine_fiador,
        #                     'number': number,
        #                     'number_2': number_2,
        #                     'text_representation': text_representation,
        #                     'text_representation2': text_representation2,
        #                     'ingreso':ingreso,
        #                     'ingreso_obligado':ingreso_obligado,
        #                     'template':"home/aprobado_obligado.html",
        #                     }
        #                     self.generar_archivo(context)  
                        
        #                 else:
        #                     print("Obligado Solidario Persona Moral")
        #                     print("Otro proceso")
        #                     archivo = request.data["doc_rec"]
        #                     comentario = "nada"
        #                     self.enviar_archivo(archivo,primer_inquilino,comentario)      
                
        #         if request.data["status"] == "Rechazado":
        #             print("rechazado con aval")
        #             primer_inquilino.status = "0"
        #             print("status cambiado",primer_inquilino.status)
        #             primer_inquilino.save()
        #             comentario = request.data["comentario"]
        #             archivo =request.data["doc_rec"]
        #             self.enviar_archivo(archivo,primer_inquilino,comentario)   
                

        #         elif request.data["status"] == "En espera":
        #             primer_inquilino.status = "1"
        #             print("status cambiado",primer_inquilino.status)
        #             primer_inquilino.save()
        #             print("paso save")
        #     # S I N A V A L            
        #     else:
        #         print("no hay aval aprobado")
        #         if request.data["status"] == "Aprobado":
        #             print("APROBADO SIN AVAL")
        #             primer_inquilino.status = "1"
        #             primer_inquilino.fiador = "no hay"
        #             primer_inquilino.save()
        #             print("status cambiado",primer_inquilino.status)
        #             comentario = "nada"
        #             print(comentario)
                    
        #             if "doc_sa" in request.data:
        #                 print("si existo")
        #                 archivo_sa = request.data["doc_sa"]
        #                 print(archivo_sa)
        #             else:
        #                 print("no existo")
        #                 archivo_sa = request.data["doc_rec"] 
        #                 print(archivo_sa)
                    
        #             self.enviar_archivo(archivo_sa,primer_inquilino,comentario)  
                
        #         if request.data["status"] == "Rechazado":
        #                 print("Rechazado sin Aval")
        #                 primer_inquilino.status = "0"
        #                 primer_inquilino.fiador = "no hay"
        #                 print("status cambiado",primer_inquilino.status)
        #                 primer_inquilino.save()
        #                 comentario = request.data["comentario"]
        #                 archivo =request.data["doc_rec"]
        #                 self.enviar_archivo(archivo,primer_inquilino,comentario)    
            
        #         elif request.data["status"] == "En espera":
        #             primer_inquilino.status = "1"
        #             primer_inquilino.fiador = "no hay"
        #             print("status cambiado",primer_inquilino.status)
        #             primer_inquilino.save()
        #             print("paso save")  
            
        #     serializer = self.get_serializer(instance, data=request.data, partial=partial)
            
        #     if serializer.is_valid(raise_exception=True):
        #         self.perform_update(serializer)
        #         print("edite investigacion")
            
        #         return Response(serializer.data, status=status.HTTP_200_OK)
        #     else:
        #         return Response({'errors': serializer.errors})
        # except Exception as e:
        #     return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, pk=None, *args, **kwargs):
        user_session = request.user
        try:
            print("Entrando a retrieve")
            modelos = Investigacion.objects.all() #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            # id = 3
            print(pk)
            inv = modelos.filter(id=pk)
            if inv:
                serializer_investigacion = InvestigacionSerializers(inv, many=True)
                return Response(serializer_investigacion.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay investigacion en estos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)             
        
    def enviar_archivo(self, archivo, info, estatus):
        #cuando francis este registrado regresar todo como estaba
        # francis = User.objects.all().filter(name_inmobiliaria = "Francis Calete").first()
        print("entre en el enviar archivo")
        print("soy pdf content",archivo)
        print("soy status",estatus)
        print("soy info de investigacion",info.__dict__)
        print("info id",info.user_id)
   
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            # if info.user_id == francis.id:
            #     print("Es el mismo usuaio, envialo a francis calete")
            #     # destinatario = 'el que meden @francis o algo asi'
            #     pdf_html = contenido_pdf_aprobado_francis(info,estatus)
            #     print("destinatario Francis", destinatario)
            # else:
            #destinatario = 'jsepulvedaarrendify@gmail.com'
            destinatario = info.email
            pdf_html = contenido_pdf_aprobado(info,estatus)
            print("destinatario normalito",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
            #Destino=['desarrolloarrendify@gmail.com']
            #Destino=['juridico.arrendify1@gmail.com']
            asunto = f"Resultado Investigación Prospecto {info.nombre_completo}"
            
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = ','.join(Destino)
            msg['Subject'] = asunto
            print("paso objeto mime")
            
            #Evalua si tiene este atributo
            # if hasattr(info, 'fiador'):
            #     print("SOY info.fiador",info.fiador)
            
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("pase el msg attach 1")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("pase el msg attach 2")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("tls")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("login")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("sendmail")
            return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
    def enviar_archivo_arrendify(self, archivo, info, estatus):
        #cuan(do francis este registrado regresar todo como estaba
        print("entre en el enviar archivo arrendify")
        print("soy pdf content",archivo)
        print("soy status",estatus)
        print("soy info de investigacion",info.__dict__)
        print("info id",info.user_id)
   
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            destinatario = info.email
            pdf_html = contenido_pdf_aprobado(info,estatus)
            print("destinatario normalito",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
            #Destino=['desarrolloarrendify@gmail.com']
            #Destino=['juridico.arrendify1@gmail.com']
            asunto = f"Resultado Investigación Prospecto {info.nombre_completo}"
            
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = ','.join(Destino)
            msg['Subject'] = asunto
            print("paso objeto mime")
            
            #Evalua si tiene este atributo
            # if hasattr(info, 'fiador'):
            #     print("SOY info.fiador",info.fiador)
            
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("pase el msg attach 1")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("pase el msg attach 2")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("tls")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("login")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("sendmail")
            return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
        
    def aprobar_prospecto(self, request, *args, **kwargs):
        try:
            print("entrando en Aprobar prospecto")
            #Consulata para obtener el inquilino y establecemos fecha de hoy
            today = date.today().strftime('%d/%m/%Y')
            req_dat = request.data
            info = Arrendatario.objects.filter(id = req_dat["id"]).first()
            print("soy INFO",info.__dict__)   
                 
                 
            aval = info.aval.all().first()
            redes_negativo = req_dat.get("redes_negativo")
            print("request.data",req_dat)
            print("el id que llega", req_dat["id"])
            print("")
            print("soy la info del",info.nombre_completo)       
            print(info.__dict__)
            print("")        
            print("soy la info del aval",aval)                                                           
            print("")
            print("redes negativo", redes_negativo)            
            print("")
            
            requisitos = ['referencia1', 'referencia2', 'referencia3'] # una lista para verificar las referencias 1,2 y 3
            presentes = [req for req in requisitos if req in request.data and request.data[req]]
            print("Referencias presentes: ",presentes)
            if len(presentes) == 3:
                referencias = "En consideración a lo referido por las referencias podemos constatar que la informacion brindada por el prospecto al inicio del tramite es verídica, lo cual nos permite estimar que cuenta con buenos comentarios hacia su persona."
            elif len(presentes) > 0:
                referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con alguna(s) referencias proporcionadas, por lo tanto, no podemos corroborar por completo la veracidad de la información proporcionada en la solicitud de arrendamiento. "
            else:
                referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con ninguna de las referencias proporcionadas, por lo tanto, no podemos corroborar la veracidad de la información proporcionada en la solicitud de arrendamiento. "
            
            #comentarios de redes para walden
            if redes_negativo:
                redes_negativo = dict(redes_negativo)
                #inicializamos la lista 
                redes_comentarios = []
                #establecemos las frases
                conductas = {
                'conducta_violenta': "Conducta violenta o agresiva: Publicaciones que muestran armas de fuego u otros objetos peligrosos.",
                'conducta_discriminatoria': "Conducta discriminatoria o racista: Comentarios, imágenes o memes que promueven el racismo, sexismo, homofobia, transfobia u otro tipo de discriminación.",
                'contenido_ofensivo_odio': "Contenido ofensivo o de odio: Publicaciones que contienen discursos de odio contra diversos grupos étnicos, religiosos, de orientación sexual, género, etc",
                'bullying_acoso': "Bullying o acoso: Participación en o incitación al acoso, ya sea ciberacoso o en la vida real.",
                'contenido_inapropiado': "Contenido inapropiado o explícito: Publicaciones de contenido sexual explícito o inapropiado.",
                'desinformacion_teoria': "Desinformación y teorías conspirativas: Difusión de información falsa o engañosa, así como la promoción de teorías conspirativas sin fundamento que puedan poner en peligro la tranquilidad y orden dentro de la comunidad.",
                'lenguaje_vulgar': "Lenguaje vulgar o inapropiado: Uso excesivo de lenguaje vulgar o soez en sus publicaciones.",
                'contenido_poco_profesional': "Conducta poco profesional: Publicaciones que muestran comportamientos inapropiados en contextos profesionales.",
                'falta_integridad': "Falta de integridad: Inconsistencias en la información compartida en diferentes plataformas, o indicios de comportamientos engañosos o fraudulentos.",
                'divulgacion_info': "Divulgación de información confidencial: Publicaciones que revelan información privada o confidencial de empresas, clientes o individuos.",
                'exceso_negatividad': "Exceso de negatividad: Publicaciones predominantemente negativas o quejumbrosas.",
                'falta_respeto_priv': "Falta de respeto hacia la privacidad: Compartir información privada de otras personas sin su consentimiento.",
                'ausencia_diversidad': "Ausencia de diversidad y tolerancia: Falta de representación de diversas perspectivas y falta de respeto por la diversidad en sus publicaciones."
                }
                # Bucle para generar las frases basadas en los valores de redes_negativo
                for clave, valor in redes_negativo.items(): #hacemos un for basado en la clave valor del dicciones redes_negativo en el .items al ser un diccionario
                    if valor == "Si" and clave in conductas:
                        frase = conductas[clave]
                        #lo agregamos a la lista redes_comentarios
                        redes_comentarios.append(frase)
                        print("clave:", clave)
                        print("frase:", frase)
                        print("lista finalizada:", redes_comentarios)
                    elif valor == "Si" and clave not in conductas:
                        print(f"No hay una frase definida para la clave: {clave}")
            else:
                redes_comentarios = "no tengo datos"
                print("redes coments",redes_comentarios)
        
            #opciones para el score interno de nosotros
            opciones = {
                'Excelente': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_excelente.png",
                'Bueno': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_bueno.png",
                'Regular': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_regular.png",
                'Malo': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_malo.png"
            }
            
            tipo_score_ingreso = req_dat["tipo_score_ingreso"]
            tipo_score_pp = req_dat["tipo_score_pp"]
            tipo_score_credito = req_dat["tipo_score_credito"]
            
            if tipo_score_ingreso and tipo_score_pp and tipo_score_credito in opciones:
                tsi = opciones[tipo_score_ingreso]
                tspp = opciones[tipo_score_pp]
                tsc = opciones[tipo_score_credito]
                print(f"Tu Tipo de score ingresos es: {tipo_score_ingreso}, URL: {tsi}")
                print(f"Tu Tipo de score de pagos puntuales es: {tipo_score_pp}, URL: {tspp}")
                print(f"Tu Tipo de score de credito es: {tipo_score_credito}, URL: {tsc}")
            
               
            #Dar conclusion dinamica
            antecedentes = request.data.get('antecedentes') # Obtenemos todos los antecedentes del prospecto
            print("ANTECEDENTES",antecedentes)
            if antecedentes:
                # del antecedentes["civil_mercantil_demandado"] 
                print("tienes antecedences, vamos a ver si es civil o familiar",antecedentes)
                if antecedentes.get("civil_mercantil_demandado") and len(antecedentes) == 1: #tiene antecedentes de civil o de familiar? los excentamos si no delincuente
                    print("Tiene antecedentes civiles o familiares")
                    print("Checamos el historial")
                    #evaluar el historial crediticio  
                    
                    if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                        print("rechazado")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                    
                    elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                        print("aprobado")
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                        status = "Aprobado"
                        motivo = "No hay motivo de rechazo"
                    
                    elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                        print("a considerar")
                        conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                        status = "Aprobado_pe"
                        motivo = "1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                        
                elif antecedentes.get("antecedentes_aval_si") and len(antecedentes) == 1: #tiene antecedentes de aval
                        print("el aval tiene antecedentes")
                        print("Cambiamos el Aval")
                        
                        if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                            print("rechazado")
                            conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                            status = "Declinado"
                            motivo = f"1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                            print("aprobado imprimi la primer conclusion")
                            conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                            status = "Aprobado"
                            motivo =  f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                            print("a considerar")
                            conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                            status = "Aprobado_pe"
                            motivo = f"1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse.\n3.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                    
                elif antecedentes and tipo_score_pp == "Malo" or antecedentes and tipo_score_ingreso == "Malo":
                        print("rechazado")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."    
                        
                else:
                    print("eres un delincuente")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."
            else: #No tiene Antecedentes
                
                #evaluar el historial crediticio  
                if tipo_score_pp == "Malo":
                    print("rechazado")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Buro: Se cuenta con un buro con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                
                elif tipo_score_ingreso == "Malo":
                    print("rechazado")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Ingresos: Los ingresos comprobados no son suficientes para garantizar el cumplimiento de sus obligaciones financieras."
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                    print("aprobado")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = ""   
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente" and antecedentes.get("antecedentes_aval_si") and antecedentes != None :
                    print("aprobado imprimi la segunda conclusion")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos." 
                
                elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                    print("a considerar")
                    conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                    status = "Aprobado_pe"
                    motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                
                 
                    
            context = {'info': info, 'aval':aval, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                       "redes_comentarios":redes_comentarios, 'referencias':referencias, 'antecedentes':antecedentes,'status':status, 'conclusion':conclusion, 'motivo':motivo}
            
            template = 'home/report.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            print("Generando el pdf")
            pdf_file = HTML(string=html_string).write_pdf()

            # #aqui hacia abajo es para enviar por email
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
        
            print("antes de enviar_archivo",context)
            correo = self.enviar_archivo_arrendify(archivo, context["info"], context["status"])
            print("soy correo papito",correo)
            if correo.status_code == 200:
                 # Aprobar o desaprobar
                if status == "Aprobado_pe" or status == "Aprobado":  
                     info.status = "Aprobado"
                     info.save()
                else:
                     info.status = "Rechazado"
                     info.save()
                
                print("Correo ENVIADO")
            
            else:
                print("valio chetos")
                print("Correo NO ENVIADO")
                Response({"Error":"no se envio el correo"},status = 409)
            
            return Response({'mensaje': "Todo salio bien, pdf enviado"}, status = 200)
           
            #de aqui hacia abajo Devuelve el PDF como respuesta
            # response = HttpResponse(content_type='application/pdf')
            # response['Content-Disposition'] = 'inline; filename="Pagare.pdf"'
            # response.write(pdf_file)
            # print("Finalizamos el proceso de aprobado") 
            # return response
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status = "404") 



# ----------------------------------Cotizador---------------------------------- #        
class Arrendador_Cotizador(viewsets.ModelViewSet):
    queryset = Propietario.objects.all()
    serializer_class = ArrendadorSerializer
    
    def list(self, request, *args, **kwargs): 
        user_session = self.request.user
        try:
            qs = request.GET.get('tipo') 
            tipo_persona = ""
            
            if qs == "Arrendador":
                tipo_persona = "Persona Fisica" 
                
            if qs == "Inmobiliaria":
                tipo_persona = "Inmobiliaria"        
            print("el valor de qs",qs)
            
            if user_session.rol == "Inmobiliaria":  
                #tengo que buscar a los arrendadores que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                if tipo_persona == 'Persona Fisica':
                    #busqueda de arrendadores propios y registrados por mis agentes
                    arrendadores_a_cargo = Arrendador.objects.filter(user_id__in = agentes).exclude(pmoi="Inmobiliaria")
                    arrendadores_mios = Arrendador.objects.filter(user_id = user_session).exclude(pmoi="Inmobiliaria")
                    mios = arrendadores_a_cargo.union(arrendadores_mios)
                    print("ya excluimos las inmobi", mios)
                    
                    #busqueda de arrendador vinculado y excluimos el inmuebiliaria
                    pertenece2 = Arrendador.objects.filter(mi_agente_es__icontains = agentes.values("first_name")).exclude(pmoi="Inmobiliaria")
                    pertenece = Arrendador.objects.filter(mi_agente_es__in = agentes.values("first_name")).exclude(pmoi="Inmobiliaria")
                    pertenece = pertenece.union(pertenece2)
                    arrendador_all = mios.union(pertenece)
                    print("all",arrendador_all)  
                    
                else:
                    #busqueda de arrendadores propios y registrados por mis agentes
                    arrendadores_a_cargo = Arrendador.objects.filter(user_id__in = agentes, pmoi="Inmobiliaria")
                    arrendadores_mios = Arrendador.objects.filter(user_id = user_session, pmoi="Inmobiliaria")
                    mios = arrendadores_a_cargo.union(arrendadores_mios)
                    print("ya excluimos las inmobi", mios)
                    
                    #busqueda de arrendador vinculado y excluimos el inmuebiliaria
                    pertenece2 = Arrendador.objects.filter(mi_agente_es__icontains = agentes.values("first_name"), pmoi="Inmobiliaria")
                    pertenece = Arrendador.objects.filter(mi_agente_es__in = agentes.values("first_name"), pmoi="Inmobiliaria")
                    pertenece = pertenece.union(pertenece2)
                    arrendador_all = mios.union(pertenece)
                    print("all",arrendador_all)  
                
                serializer = ArrendadorSerializer(arrendador_all, many=True)
                serialized_data = serializer.data
                return Response(serialized_data)      
            
            elif user_session.rol == "Agente":  
                print("soy agente", user_session.first_name)
                
                if tipo_persona == 'Persona Fisica':
                    agente_qs = Arrendador.objects.filter(user_id = user_session).exclude(pmoi="Inmobiliaria")
                    pertenece = Arrendador.objects.filter(mi_agente_es__icontains = user_session.first_name).exclude(pmoi="Inmobiliaria")
                    arredores_a_cargo = agente_qs.union(pertenece)
                    
                else:
                    agente_qs = Arrendador.objects.filter(user_id = user_session, pmoi="Inmobiliaria")
                    pertenece = Arrendador.objects.filter(mi_agente_es__icontains = user_session.first_name, pmoi="Inmobiliaria")
                    arredores_a_cargo = agente_qs.union(pertenece)
                
                serializer = ArrendadorSerializer(arredores_a_cargo, many=True)
                serialized_data = serializer.data
            
                return Response(serialized_data)
                
            else:
                if tipo_persona == 'Persona Fisica':
                    print("Arrendador pf y pm")   
                    queryset = self.queryset.exclude(pmoi="Inmobiliaria").filter(user=user_session)
                    #queryset = self.queryset.filter(Q(pmoi='Persona Fisica') | Q(pmoi='Persona Moral'))
                else:
                    print("Inmobiliaria")
                    queryset = self.queryset.filter(pmoi="Inmobiliaria",user=user_session)
                
                serializer = self.get_serializer(queryset, many=True)
                return Response(serializer.data)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            

class Cotizacion_ap(viewsets.ModelViewSet):
  
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Cotizacion.objects.all()
    serializer_class = CotizacionSerializers
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
               print("Esta entrando a listar cotizacion")
               cotizaciones =  Cotizacion.objects.all()
               serializer = self.get_serializer(cotizaciones, many=True)
               return Response(serializer.data)
           
           elif user_session.rol == "Inmobiliaria":
               #primero obtenemos mis agentes.
               print("soy inmobiliaria en listar cotizacion", user_session.name_inmobiliaria)
               agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
               
               #a continuacion obtenemos los inquilinos
               inquilinos_a_cargo = Arrendatario.objects.filter(user_id__in = agentes)
               inquilinos_mios = Arrendatario.objects.filter(user_id = user_session)
               mios = inquilinos_a_cargo.union(inquilinos_mios)
               pertenece2 = Arrendatario.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
               pertenece = Arrendatario.objects.filter(mi_agente_es__in = agentes.values("first_name"))
               pertenece = pertenece.union(pertenece2)
               inquilinos_all = mios.union(pertenece) 
               
               #obtenemos los arrendadores
               arrendadores_a_cargo = Arrendador.objects.filter(user_id__in = agentes)
               arrendadores_mios = Arrendador.objects.filter(user_id = user_session)
               mios2 = arrendadores_a_cargo.union(arrendadores_mios)
               pertenece2 = Arrendador.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
               pertenece = Arrendador.objects.filter(mi_agente_es__in = agentes.values("first_name"))
               pertenece = pertenece.union(pertenece2)
               arrendador_all = mios2.union(pertenece)
               
               print("inquilinos_all",inquilinos_all)
               print("Todos los arrendadores",arrendador_all)
               
               #obtenemos las cotizaciones
               cotizaciones_mias = Cotizacion.objects.filter(user_id = user_session.id)
               cotizaciones_inquilinos = Cotizacion.objects.filter(inquilino_id__in = inquilinos_all.values("id"))
               cotizaciones_arrendador = Cotizacion.objects.filter(arrendador_id__in = arrendador_all.values("id"))
               cotizaciones_all = cotizaciones_mias.union(cotizaciones_arrendador, cotizaciones_inquilinos)
               print("mis cotizaciones", cotizaciones_mias)
               print("cotizacion inquilinos all", cotizaciones_inquilinos)
               print("cotizaciones de arrendadores",cotizaciones_arrendador)
               print("es posible hacer esto:", cotizaciones_all)
               
               serializer = self.get_serializer(cotizaciones_all, many=True)
               return Response(serializer.data)
               
           elif user_session.rol == "Agente":
               print(f"soy Agente: {user_session.first_name} en listar cotizacion")
               inquilinos_ag = Arrendatario.objects.filter(user_id = user_session, status = 1)
               pertenece = Arrendatario.objects.filter(mi_agente_es__icontains = user_session.first_name)
               inquilinos_all = inquilinos_ag.union(pertenece)
                
               agente_qs = Arrendador.objects.filter(user_id = user_session)
               pertenece = Arrendador.objects.filter(mi_agente_es__icontains = user_session.first_name)
               arredores_a_cargo = agente_qs.union(pertenece)
               
               print("inquilinos_all",inquilinos_all)
               print("Todos los arrendadores",arredores_a_cargo)
               
               #obtenemos las cotizaciones
               cotizaciones_mias = Cotizacion.objects.filter(user_id = user_session.id)
               cotizaciones_inquilinos = Cotizacion.objects.filter(inquilino_id__in = inquilinos_all.values("id"))
               cotizaciones_arrendador = Cotizacion.objects.filter(arrendador_id__in = arredores_a_cargo.values("id"))
               cotizaciones_all = cotizaciones_mias.union(cotizaciones_arrendador, cotizaciones_inquilinos)
               print("mis cotizaciones", cotizaciones_mias)
               print("cotizacion inquilinos all", cotizaciones_inquilinos)
               print("cotizaciones de arrendadores",cotizaciones_arrendador)
               print("es posible hacer esto:", cotizaciones_all)
               
               serializer = self.get_serializer(cotizaciones_all, many=True)
               return Response(serializer.data)
                 
           else:
               # Obtener las consultas de cotizacion y paquetes
               cotizaciones = Cotizacion.objects.filter(user_id = user_session.id)
               paquetes =  Paquetes_legales.objects.all().filter(user_id = user_session.id)
               # Obtener las cotizaciones del usuario que no tienen un paquete asociado
               cotizaciones_sin_paquete = cotizaciones.exclude(id__in = paquetes.values_list('cotizacion_id', flat=True))
               print("soy cotizaciones_sin_paquete",cotizaciones_sin_paquete)                                                
               serializer = self.get_serializer(cotizaciones_sin_paquete, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        user_session = request.user
        print(user_session)
     
        try:
            print("Llegando a create de cotizador")
            #Toda La onda para que el usuario solo tenga 3 intentos
            usuario = user_session
            fecha_actual = date.today()
            acciones_realizadas = Accion.objects.filter(usuario=usuario)
            
            if acciones_realizadas.exists():
                accion = acciones_realizadas.first()
                if(accion.fecha == fecha_actual):
                    if accion.contador > 0:
                        accion.contador = accion.contador - 1
                        accion.save()
                    else:
                        return Response({'msj':'haz alcanzado el limite de cotizacion diario, intenta mañana'},status=status.HTTP_204_NO_CONTENT)     
                else:
                    print("Renovando fecha")
                    accion.fecha = fecha_actual
                    accion.contador = 3
                    accion.contador = accion.contador - 1
                    accion.save()
            else:
                print("crealo")
                nuevo = Accion.objects.create(usuario=usuario,fecha=fecha_actual)
                nuevo.contador = nuevo.contador - 1
                nuevo.save()
                
            cotizador_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            if cotizador_serializer.is_valid(raise_exception=True):
                print("entro al IF")
                info = cotizador_serializer.save(user = user_session)
                print("soy INFO",info.__dict__)
                print(info.nombre_cotizacion)
                print("soy poliza",info.tipo_poliza)
                if info.arrendador:
                    print("sou arrendador",info.arrendador.__dict__)
                else:
                    print("soy inquilino",info.inquilino.__dict__)
                context = {"info": info}  # Ejemplo de contexto de datos
                
                if info.tipo_poliza == "Plata":
                     # Renderiza el template HTML
                    template = 'home/acp.html' #obtenemos template
                    html_string = render_to_string(template, context)# lo comvertimos a string
                    pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
                    print("pdf realizado")
                    print(pdf_file)
                    
                    pdf_file2 = ContentFile(pdf_file, name='cotizacion.pdf') # lo guarda como content raw para enviar el correo
                    print("pdf_file2",pdf_file2)
                    # Devuelve el PDF como respuesta
                    response = HttpResponse(content_type='application/pdf')
                    response['Content-Disposition'] = 'attachment; filename="mi_pdf.pdf"'
                    response.write(pdf_file)
                    print("terminado")
                    
                    data = {
                        "cotizacion_archivo" : info.id, 
                        "documento_cotizacion" : pdf_file2,
                        "fecha_vigencia" : info.fecha_vigencia
                        }
                    print("despues de data",data)
                    
                    gen_serializer = Cotizacion_genSerializer(data=data) 
                    print(gen_serializer)
                    
                    if gen_serializer.is_valid(raise_exception=True):
                        print("el serializer es valido")
                        self.enviar_pdf(pdf_file2, info)
                        gen_serializer.save()
                    else:
                        print("el serializer es invalido")
                        return Response({'errors': gen_serializer.errors})
                    print("despues del seri<lizer")
                    
                   
                    print("PDF ENVIADO")
                    return response
                
                elif info.tipo_poliza == "Oro":
                    # Renderiza el template HTML
                    template = 'home/aco.html' #obtenemos template
                    html_string = render_to_string(template, context)# lo comvertimos a string
                    print("llego hasta aqui")
                    pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
                    print("pdf realizado")
                    print(pdf_file)
                    
                    pdf_file2 = ContentFile(pdf_file, name='cotizacion.pdf') # lo guarda como content raw para enviar el correo
                    print("pdf_file2",pdf_file2)
                    # Devuelve el PDF como respuesta
                    response = HttpResponse(content_type='application/pdf')
                    response['Content-Disposition'] = 'attachment; filename="mi_pdf.pdf"'
                    response.write(pdf_file)
                    print("terminado")
                    
                    data = {
                        "cotizacion_archivo" : info.id, 
                        "documento_cotizacion" : pdf_file2,
                        "fecha_vigencia" : info.fecha_vigencia
                        }
                    print("despues de data",data)
                    
                    gen_serializer = Cotizacion_genSerializer(data=data) 
                    print(gen_serializer)
                    
                    if gen_serializer.is_valid(raise_exception=True):
                        print("el serializer es valido")
                        self.enviar_pdf(pdf_file2, info)
                        gen_serializer.save()
                    else:
                        print("el serializer es invalido")
                        return Response({'errors': gen_serializer.errors})
                    print("despues del seri<lizer")
                    
                    print("PDF ENVIADO")
                    return response
                
                elif info.tipo_poliza == "Platino":
                    # Renderiza el template HTML
                    template = 'home/acptn.html' #obtenemos template
                    html_string = render_to_string(template, context)# lo comvertimos a string
                    pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
                    print("pdf realizado")
                    print(pdf_file)
                    
                    pdf_file2 = ContentFile(pdf_file, name='cotizacion.pdf') # lo guarda como content raw para enviar el correo
                    print("pdf_file2",pdf_file2)
                    # Devuelve el PDF como respuesta
                    response = HttpResponse(content_type='application/pdf')
                    response['Content-Disposition'] = 'attachment; filename="mi_pdf.pdf"'
                    response.write(pdf_file)
                    print("terminado")
                    
                    data = {
                        "cotizacion_archivo" : info.id, 
                        "documento_cotizacion" : pdf_file2,
                        "fecha_vigencia" : info.fecha_vigencia
                        }
                    print("despues de data",data)

                    gen_serializer = Cotizacion_genSerializer(data=data) 
                    print(gen_serializer)
                    
                    if gen_serializer.is_valid(raise_exception=True):
                        print("el serializer es valido")
                        self.enviar_pdf(pdf_file2, info)
                        print("ya envie pdf")
                        gen_serializer.save()
                    else:
                        print("el serializer es invalido")
                        return Response({'errors': gen_serializer.errors})
                    print("despues del seri<lizer")                   
                    print("PDF ENVIADO")
                    return response
                else:
                    print("Error en poliza")
                    return Response({'errors': "por alguna razon no habia poliza"},status=status.HTTP_204_NO_CONTENT)
                    
            else:
                print("Error en validacion")
                return Response({'errors': cotizador_serializer.errors})
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    # probando con variables de entorno
    def enviar_pdf(self, pdf_content, info):
        print("soy pdf content",pdf_content)
        print("soy info de enviar_pdf",info)
        print("soy correo de agentify",info.agentify.__dict__)
        # Configura los detalles del correo electrónico
        try:
            print("entre en el try")
            remitente = 'notificaciones@arrendify.com'
            destinatario2 = info.agentify.correo
            if info.arrendador:
                if info.arrendador.pmoi == "Inmobiliaria":
                    print("si entre a inmobiliaria")
                    destinatario = (info.arrendador.email_arr).lower()
                else:
                    print("ni entre a inmobiliaria")
                    destinatario = info.arrendador.email
            else:
                destinatario = info.inquilino.email
            destinatarios = [destinatario,destinatario2]
            print("destinatario",destinatario)
            print("ejecutivo comercial ",destinatario2)
            asunto = f"Cotización Arrendify Póliza {info.tipo_poliza} {info.cliente}"

            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Subject'] = asunto
            #msg['Cc'] = destinatario2
            print("pase mime")
            # Estilo del mensaje
            if info.arrendador:
                contenido_html = (
                    """
               <html>
                <head>
                    <style>
                    /* Estilos CSS para el mensaje */
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background-color: #f2f2f2;
                    }

                    .container {
                        max-width: 600px;
                        margin: 0 auto;
                        background-color: #fff;
                        padding: 20px;
                        border-radius: 5px;
                        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                    }

                    h1 {
                        color: #333;
                        font-size: 24px;
                        margin-bottom: 20px;
                    }

                    p {
                        color: #555;
                        font-size: 16px;
                        line-height: 1.5;
                        margin-bottom: 10px;
                    }
                    </style>
                </head>
                <body>
                    <div class="container">
                   <img src="https://arrendify.com/wp-content/uploads/2021/02/logo-arrendafy.png" alt="logo_arrendify" align="right" style="width: 200px; height: auto;">
                   <br>
                    """
                     
                    f'<h1>Estimado/a {info.cliente}</h1>' 
                    
                    """
                    <p>Espero que este se encuentre bien.</p>
                    <p>Nos complace adjuntarle el archivo PDF de la cotización, como solicitó recientemente.</p>
                    <p>En el archivo adjunto, encontrará todos los detalles y la información relevante relacionada con la valoración de su propiedad. Hemos realizado una evaluación exhaustiva y hemos tenido en cuenta diversos factores para proporcionarle una estimación precisa y justa.</p>
                    <p>Si tiene alguna pregunta o inquietud sobre la cotización adjunta, no dude en ponerse en contacto con su Agentify. Estamos aquí para brindarle cualquier aclaración adicional o asistencia que pueda necesitar.</p>
                    <p>Agradezco su interés en nuestros servicios y espero que esta cotización sea útil para usted. Si está satisfecho/a con nuestra evaluación, estaríamos encantados de discutir los próximos pasos y cualquier otro detalle relacionado con la contratacion nuestros servicios.</p>
                    <br>
                    <p>Le agradezco su atención y quedo a la espera de sus respuesta.</p>
                    <p>Nota: Le Recuerdo que se tiene que pagar el monto que aparece en la cotización en maximo 3 dias para poder inciar el proceso de investigación.</p>
                    <br>
                    <hr style="color: #0056b2;" />
                    <table>
                      <tbody><tr>
                        <td align="center" bgcolor="#efefef" style="padding:0;Margin:0;background-color:#efefef;background-image:url(https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/15921614697745363.png);background-repeat:no-repeat;background-position:left top" background="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/15921614697745363.png">
                         <table class="es-footer-body" align="center" cellpadding="0" cellspacing="0" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px;background-color:transparent;width:600px">
                           <tbody><tr>
                            <td align="left" style="padding:0;Margin:0;padding-top:20px;padding-left:20px;padding-right:20px"><!--[if mso]><table style="width:560px" cellpadding="0" 
                                      cellspacing="0"><tr><td style="width:245px" valign="top"><![endif]-->
                             <table cellpadding="0" cellspacing="0" class="es-left" align="left" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px;float:left">
                               <tbody><tr>
                                <td class="es-m-p20b" align="left" style="padding:0;Margin:0;width:245px">
                                 <table cellpadding="0" cellspacing="0" width="100%" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                   <tbody><tr>
                                    <td align="left" class="es-m-txt-c" style="padding:0;Margin:0;font-size:0px"><a target="_blank" href="https://arrendify.com" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img src="https://arrendify.com/wp-content/uploads/2021/02/logo-arrendafy.png" alt="" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic" height="50" width="200"></a></td>
                                   </tr>
                                   <tr>
                                    <td align="left" style="padding:0;Margin:0;padding-top:10px;padding-bottom:10px"><p style="Margin:0;-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;font-family:arial, 'helvetica neue', helvetica, sans-serif;line-height:21px;color:#333333;font-size:14px">Lo hacemos con pasión o no lo hacemos.</p></td>
                                   </tr>
                                 </tbody></table></td>
                               </tr>
                             </tbody>
                            </table>
                             <table cellpadding="0" cellspacing="0" class="es-right" align="right" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px;float:right">
                               <tbody><tr>
                                <td align="left" style="padding:0;Margin:0;width:295px">
                                 <table cellpadding="0" cellspacing="0" width="100%" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                   <tbody><tr>
                                    <td align="left" style="padding:0;Margin:0;padding-top:20px"><h3 style="Margin:0;line-height:24px;mso-line-height-rule:exactly;font-family:arial, 'helvetica neue', helvetica, sans-serif;font-size:20px;font-style:normal;font-weight:bold;color:#333333">Contacto</h3></td>
                                   </tr>
                                   <tr>
                                    <td style="padding:0;Margin:0">
                                     <table cellpadding="0" cellspacing="0" width="100%" class="es-menu" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                       <tbody><tr class="links-images-left">
                                        <td align="left" valign="top" width="100%" id="esd-menu-id-0" style="Margin:0;padding-left:5px;padding-right:5px;padding-top:10px;padding-bottom:7px;border:0"><a Estamos aquí" href="#" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:none;display:block;color:#666666;font-size:14px"><img src="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/39781614763048410.png" alt="30 Commercial Road Fratton, Australia" title="30 Commercial Road Fratton, Australia" align="absmiddle" width="20" style="display:inline-block !important;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;padding-right:5px;vertical-align:middle"> Blvrd Manuel Ávila Camacho 80, Int 204, El Parque, 53398 Naucalpan de Juárez, MEX</a></td>
                                       </tr>
                                     </tbody></table></td>
                                   </tr>
                                   <tr>
                                    <td style="padding:0;Margin:0">
                                     <table cellpadding="0" cellspacing="0" width="100%" class="es-menu" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                       <tbody><tr class="links-images-left">
                                        <td align="left" valign="top" width="100%" id="esd-menu-id-0" style="Margin:0;padding-left:5px;padding-right:5px;padding-top:7px;padding-bottom:7px;border:0"><a Estamos aquí" href="#" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:none;display:block;color:#666666;font-size:14px"><img src="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/95711614763048218.png" alt="1-888-452-1505" title="1-888-452-1505" align="absmiddle" width="20" style="display:inline-block !important;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;padding-right:5px;vertical-align:middle">(55) 7258 9136</a></td>
                                       </tr>
                                     </tbody></table></td>
                                   </tr>
                                   <tr>
                                    <td style="padding:0;Margin:0">
                                     <table cellpadding="0" cellspacing="0" width="100%" class="es-menu" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                       <tbody><tr class="links-images-left">
                                        <td align="left" valign="top" width="100%" id="esd-menu-id-0" style="Margin:0;padding-left:5px;padding-right:5px;padding-top:7px;padding-bottom:10px;border:0"><a Estamos aquí" href="#" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:none;display:block;color:#666666;font-size:14px"><img src="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/97961614763048410.png" alt="Mon - Sat: 8am - 5pm, Sunday: CLOSED" title="Mon - Sat: 8am - 5pm, Sunday: CLOSED" align="absmiddle" width="20" style="display:inline-block !important;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;padding-right:5px;vertical-align:middle">Lun - Sab: 8:30am - 6pm, Domingo: Cerrado</a></td>
                                       </tr>
                                     </tbody></table></td>
                                   </tr>
                                 </tbody></table></td>
                               </tr>
                             </tbody></table><!--[if mso]></td></tr></table><![endif]--></td>
                           </tr>
                           <tr>
                            <td align="left" style="padding:20px;Margin:0">
                             <table cellpadding="0" cellspacing="0" width="100%" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                               <tbody><tr>
                                <td align="center" valign="top" style="padding:0;Margin:0;width:560px">
                                 <table cellpadding="0" cellspacing="0" width="100%" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                   <tbody><tr>
                                    <td align="center" style="padding:0;Margin:0;font-size:0">
                                     <table cellpadding="0" cellspacing="0" class="es-table-not-adapt es-social" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                       <tbody><tr>
                                        <td align="center" valign="top" style="padding:0;Margin:0;padding-right:25px"><a target="_blank" href="https://www.facebook.com/Arrendify-110472377752254" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Facebook" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/facebook-logo-black.png" alt="Fb" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                        <td align="center" valign="top" style="padding:0;Margin:0;padding-right:25px"><a target="_blank" href="https://twitter.com/Arrendify/" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Twitter" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/twitter-logo-black.png" alt="Tw" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                        <td align="center" valign="top" style="padding:0;Margin:0;padding-right:25px"><a target="_blank" href="https://www.instagram.com/Arrendify/" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Instagram" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/instagram-logo-black.png" alt="Inst" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                        <td align="center" valign="top" style="padding:0;Margin:0"><a target="_blank" href="https://www.youtube.com/channel/UCSUDtH0ybV9O-AnZHjI-_Xg" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Youtube" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/youtube-logo-black.png" alt="Yt" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                       </tr>
                                     </tbody></table></td>
                                   </tr>
                                 </tbody></table></td>
                               </tr>
                             </tbody></table></td>
                           </tr>
                         </tbody></table></td>
                       </tr>
                     </tbody>
                    </table>
                    
                    <br>
                    <!-- <img src="apps/static/assets/media/img/logo-arrendafy.png" alt="logo_arrendify" style="width: 200px; height: auto;"> -->
                    </div>
                </body>
                </html>
                 """)
              
            else:
                contenido_html = (
                """
               <html>
                <head>
                    <style>
                    /* Estilos CSS para el mensaje */
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background-color: #f2f2f2;
                    }

                    .container {
                        max-width: 600px;
                        margin: 0 auto;
                        background-color: #fff;
                        padding: 20px;
                        border-radius: 5px;
                        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                    }

                    h1 {
                        color: #333;
                        font-size: 24px;
                        margin-bottom: 20px;
                    }

                    p {
                        color: #555;
                        font-size: 16px;
                        line-height: 1.5;
                        margin-bottom: 10px;
                    }
                    </style>
                </head>
                <body>
                    <div class="container">
                   <img src="https://arrendify.com/wp-content/uploads/2021/02/logo-arrendafy.png" alt="logo_arrendify" align="right" style="width: 200px; height: auto;">
                   <br>
                    """
                     
                    f'<h1>Estimado/a {info.cliente}</h1>' 
                    
                    """
                    <p>Espero que este se encuentre bien.</p>
                    <p>Nos complace adjuntarle el archivo PDF de la cotización, como solicitó recientemente.</p>
                    <p>En el archivo adjunto, encontrará todos los detalles y la información relevante relacionada con la valoración de su presupuesto de renta. Hemos realizado una evaluación exhaustiva y hemos tenido en cuenta diversos factores para proporcionarle una estimación precisa y justa.</p>
                    <p>Si tiene alguna pregunta o inquietud sobre la cotización adjunta, no dude en ponerse en contacto con su Agentify. Estamos aquí para brindarle cualquier aclaración adicional o asistencia que pueda necesitar.</p>
                    <p>Agradezco su interés en nuestros servicios y espero que esta cotización sea útil para usted. Si está satisfecho/a con nuestra evaluación, estaríamos encantados de discutir los próximos pasos y cualquier otro detalle relacionado a la contratación de nuestros servicios.</p>
                    <br>
                    <p>Le agradezco su atención y quedo a la espera de su respuesta.</p>
                    <p>Nota: Le Recuerdo que se tiene que pagar el monto que aparece en la cotización en maximo 3 dias para poder inciar el proceso de investigación.</p>
                    <hr style="color: #0056b2;" />
                    <table>
                      <tbody><tr>
                        <td align="center" bgcolor="#efefef" style="padding:0;Margin:0;background-color:#efefef;background-image:url(https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/15921614697745363.png);background-repeat:no-repeat;background-position:left top" background="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/15921614697745363.png">
                         <table class="es-footer-body" align="center" cellpadding="0" cellspacing="0" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px;background-color:transparent;width:600px">
                           <tbody><tr>
                            <td align="left" style="padding:0;Margin:0;padding-top:20px;padding-left:20px;padding-right:20px"><!--[if mso]><table style="width:560px" cellpadding="0" 
                                      cellspacing="0"><tr><td style="width:245px" valign="top"><![endif]-->
                             <table cellpadding="0" cellspacing="0" class="es-left" align="left" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px;float:left">
                               <tbody><tr>
                                <td class="es-m-p20b" align="left" style="padding:0;Margin:0;width:245px">
                                 <table cellpadding="0" cellspacing="0" width="100%" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                   <tbody><tr>
                                    <td align="left" class="es-m-txt-c" style="padding:0;Margin:0;font-size:0px"><a target="_blank" href="https://arrendify.com" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img src="https://arrendify.com/wp-content/uploads/2021/02/logo-arrendafy.png" alt="" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic" height="50" width="200"></a></td>
                                   </tr>
                                   <tr>
                                    <td align="left" style="padding:0;Margin:0;padding-top:10px;padding-bottom:10px"><p style="Margin:0;-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;font-family:arial, 'helvetica neue', helvetica, sans-serif;line-height:21px;color:#333333;font-size:14px">Lo hacemos con pasión o no lo hacemos.</p></td>
                                   </tr>
                                 </tbody></table></td>
                               </tr>
                             </tbody>
                            </table>
                             <table cellpadding="0" cellspacing="0" class="es-right" align="right" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px;float:right">
                               <tbody><tr>
                                <td align="left" style="padding:0;Margin:0;width:295px">
                                 <table cellpadding="0" cellspacing="0" width="100%" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                   <tbody><tr>
                                    <td align="left" style="padding:0;Margin:0;padding-top:20px"><h3 style="Margin:0;line-height:24px;mso-line-height-rule:exactly;font-family:arial, 'helvetica neue', helvetica, sans-serif;font-size:20px;font-style:normal;font-weight:bold;color:#333333">Contacto</h3></td>
                                   </tr>
                                   <tr>
                                    <td style="padding:0;Margin:0">
                                     <table cellpadding="0" cellspacing="0" width="100%" class="es-menu" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                       <tbody><tr class="links-images-left">
                                        <td align="left" valign="top" width="100%" id="esd-menu-id-0" style="Margin:0;padding-left:5px;padding-right:5px;padding-top:10px;padding-bottom:7px;border:0"><a " href="#" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:none;display:block;color:#666666;font-size:14px"><img src="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/39781614763048410.png" alt="30 Commercial Road Fratton, Australia" title="30 Commercial Road Fratton, Australia" align="absmiddle" width="20" style="display:inline-block !important;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;padding-right:5px;vertical-align:middle"> Blvrd Manuel Ávila Camacho 80, Int 204, El Parque, 53398 Naucalpan de Juárez, MEX</a></td>
                                       </tr>
                                     </tbody></table></td>
                                   </tr>
                                   <tr>
                                    <td style="padding:0;Margin:0">
                                     <table cellpadding="0" cellspacing="0" width="100%" class="es-menu" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                       <tbody><tr class="links-images-left">
                                        <td align="left" valign="top" width="100%" id="esd-menu-id-0" style="Margin:0;padding-left:5px;padding-right:5px;padding-top:7px;padding-bottom:7px;border:0"><a " href="#" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:none;display:block;color:#666666;font-size:14px"><img src="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/95711614763048218.png" alt="1-888-452-1505" title="1-888-452-1505" align="absmiddle" width="20" style="display:inline-block !important;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;padding-right:5px;vertical-align:middle">(55) 7258 9136</a></td>
                                       </tr>
                                     </tbody></table></td>
                                   </tr>
                                   <tr>
                                    <td style="padding:0;Margin:0">
                                     <table cellpadding="0" cellspacing="0" width="100%" class="es-menu" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                       <tbody><tr class="links-images-left">
                                        <td align="left" valign="top" width="100%" id="esd-menu-id-0" style="Margin:0;padding-left:5px;padding-right:5px;padding-top:7px;padding-bottom:10px;border:0"><a " href="#" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:none;display:block;color:#666666;font-size:14px"><img src="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/97961614763048410.png" alt="Mon - Sat: 8am - 5pm, Sunday: CLOSED" title="Mon - Sat: 8am - 5pm, Sunday: CLOSED" align="absmiddle" width="20" style="display:inline-block !important;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;padding-right:5px;vertical-align:middle">Lun - Sab: 8:30am - 6pm, Domingo: Cerrado</a></td>
                                       </tr>
                                     </tbody></table></td>
                                   </tr>
                                 </tbody></table></td>
                               </tr>
                             </tbody></table><!--[if mso]></td></tr></table><![endif]--></td>
                           </tr>
                           <tr>
                            <td align="left" style="padding:20px;Margin:0">
                             <table cellpadding="0" cellspacing="0" width="100%" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                               <tbody><tr>
                                <td align="center" valign="top" style="padding:0;Margin:0;width:560px">
                                 <table cellpadding="0" cellspacing="0" width="100%" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                   <tbody><tr>
                                    <td align="center" style="padding:0;Margin:0;font-size:0">
                                     <table cellpadding="0" cellspacing="0" class="es-table-not-adapt es-social" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                       <tbody><tr>
                                        <td align="center" valign="top" style="padding:0;Margin:0;padding-right:25px"><a target="_blank" href="https://www.facebook.com/Arrendify-110472377752254" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Facebook" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/facebook-logo-black.png" alt="Fb" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                        <td align="center" valign="top" style="padding:0;Margin:0;padding-right:25px"><a target="_blank" href="https://twitter.com/Arrendify/" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Twitter" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/twitter-logo-black.png" alt="Tw" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                        <td align="center" valign="top" style="padding:0;Margin:0;padding-right:25px"><a target="_blank" href="https://www.instagram.com/Arrendify/" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Instagram" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/instagram-logo-black.png" alt="Inst" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                        <td align="center" valign="top" style="padding:0;Margin:0"><a target="_blank" href="https://www.youtube.com/channel/UCSUDtH0ybV9O-AnZHjI-_Xg" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Youtube" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/youtube-logo-black.png" alt="Yt" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                       </tr>
                                     </tbody></table></td>
                                   </tr>
                                 </tbody></table></td>
                               </tr>
                             </tbody></table></td>
                           </tr>
                         </tbody></table></td>
                       </tr>
                     </tbody>
                    </table>
                    
                    <br>
                    <!-- <img src="apps/static/assets/media/img/logo-arrendafy.png" alt="logo_arrendify" style="width: 200px; height: auto;"> -->
                    </div>
                </body>
                </html>
                 """)
            
            print("pasamos variables contido_html")
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(contenido_html, 'html'))
            # msg.attach(MIMEText(mensaje, 'plain'))
            print("pasamos msg.attach 1")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(pdf_content.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='cotizacion.pdf')
            msg.attach(pdf_part)
            print("pasamos msg.attach 2")

            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                server.sendmail(remitente, destinatarios, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", e)
            return Response({'message': 'Error al enviar el correo electrónico.'})
        
    

class RecuperarPassword(viewsets.ViewSet):
    @action(detail=False, methods=['post'], url_path='recuperar_password')
    def recuperar_password(self, request):
        try: 
            print("Llego a recuperar password")
            print("req",request.data)
            email = request.data.get('email')
            print(email)
            try:
                user = User.objects.filter(email=email).first()
                
            except user.DoesNotExist:
                print("El correo electrónico no está registrado.")
                return Response({'message': 'El correo electrónico no está registrado.'}, status=404)

            # Verificar si ya se ha generado un token para el usuario
            print("antes de token")
            print("soy user",user)
            
            token, _ = CustomToken.objects.get_or_create(user=user)
            print("llego hasta token",_)
            print("llego hasta token",token)
            
            # Verificar también que el token no haya expirado
            if token.expires_at and token.expires_at >= timezone.now():
                # Si ya se ha generado un token y no ha expirado, retornar mensaje de solicitud ya enviada
                print("ya existe un solicitud de recuperación de contraseña")
                return Response({'message': 'Ya se ha enviado una solicitud de recuperación de contraseña.'}, status=201)
            
            # Asignamos la fecha de expiración
            expiration = timezone.now() + timedelta(minutes=30)
            token.expires_at = expiration
            token.save()
            
            # switch server
            #server = "'http://192.168.1.192:8000'"
            #server = "http://192.168.3.2:8000"
            server = "http://192.168.1.141:8000"
            #server = "https://arrendify.app"
            
            #variable
            html = correo_pas(server, token)
            # Envío de la notificación por correo electrónico
            msg = MIMEMultipart()
            msg['From'] = 'notificaciones_arrendify@outlook.com'
            msg['To'] = email
            msg['Subject'] = 'Recuperación de contraseña'
            message = f'Haz clic en el siguiente enlace para recuperar tu contraseña: {server}/guardar_password?token={token.key}'
            msg.attach(MIMEText(html, 'html'))
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw') 

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.sendmail(smtp_username, email, msg.as_string())
                print("Si envio")

            return Response({'message': 'Recuperación de contraseña enviada correctamente.',"correo":email})
        except Exception as e:
            print(f"error {e}")
            return Response({'message:Error': e}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='reset_password')
    def reset_password(self, request):
        print("Vamos a generar tu nuevo password")
        print("request", request.data)
        token = request.data.get('token')
        password = request.data.get('password')
        # Verificar si el token es válido y está asociado a un usuario en tu base de datos
        try:
            token_obj = CustomToken.objects.get(key=token)
            if token_obj.expires_at < timezone.now():
                # Si el token ha expirado, retornar mensaje de token inválido o expirado
                return Response({'message': 'El token no es válido o ha expirado.'}, status=status.HTTP_400_BAD_REQUEST)
            user = token_obj.user
        except Token.DoesNotExist:
            return Response({'message': 'El token no es válido o ha expirado.'}, status=status.HTTP_400_BAD_REQUEST)

        # Actualizar la contraseña del usuario
        user.set_password(password)
        user.save()

        # Eliminar el token utilizado
        token_obj.delete()
        print("borre el token")

        return Response({'message': 'La contraseña se ha actualizado correctamente.'})
    
# Vista para el manejo de el envío de un contacto
class ContactoDatos(viewsets.ViewSet):
    def create(self, request, *args, **kwargs):
        try: 
            print("Lleho a html" ,request.data)
            # Crea un objeto MIMEMultipart para el correo electrónico
            print("asunto", request.data.get('asunto'))
            html = Contacto(request)
            
            msg = MIMEMultipart()
            msg = MIMEMultipart()
            msg['From'] = 'notificaciones_arrendify@outlook.com'
            msg['To'] = 'leonramirezrivero@gmail.com'
            msg['Subject'] = request.data.get('asunto')

            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(html, 'html'))
            # msg.attach(MIMEText(mensaje, 'plain'))

            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server: #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                server.sendmail(msg['From'], msg['To'], msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})


# ----------------------------------Comentarios-------------------------------
class Comentario(viewsets.ModelViewSet):      
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Comentario.objects.all()
    serializer_class = ComentarioSerializer
    
    def create(self, request, *args, **kwargs):
        user_session = request.user
        try:
            print(user_session.id)
            comentario_serializer = self.serializer_class(data=request.data)
            if comentario_serializer.is_valid(raise_exception=True):
                comentario_serializer.save(user = user_session)
                return Response(comentario_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'errors': comentario_serializer.errors})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            print("edito")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'errors': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
# ----------------------------------Paquetes---------------------------------- #
class Paks(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Paquetes_legales.objects.all()
    serializer_class = PaquetesSerializer
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        qs = request.GET.get('codigo')  
        print("yo soy codigo",qs)
        try:
           if user_session.is_staff:
                if qs:
                    paquetes =  Paquetes_legales.objects.all().filter(codigo_paquete__icontains = qs)
                    print("soy el query set de paquetes",paquetes)
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
                else:
                    print("No hay codigo que buscar")
                    paquetes =  Paquetes_legales.objects.all()
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
                
           elif user_session.rol == "Inmobiliaria":
                print("soy Inmobiliaria en paqs", user_session.first_name)
                if qs:
                    paquetes =  Paquetes_legales.objects.all().filter(codigo_paquete__icontains = qs)
                    print("soy el query set de paquetes",paquetes)
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
                else:
                    paquetes =  Paquetes_legales.objects.all()
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
           
           elif user_session.rol == "Agente":
                if qs:
                    paquetes =  Paquetes_legales.objects.all().filter(codigo_paquete__icontains = qs)
                    print("soy el query set de paquetes",paquetes)
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
                else:
                    print("soy Agente", user_session.first_name)
                    paquetes =  Paquetes_legales.objects.all()
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
           else:
                print("Esta entrando a listar Paquetes fil")
                paquetes =  Paquetes_legales.objects.all().filter(user_id = user_session)
                print("soy paquetes",paquetes)
                # Filtrar los paquetes basados en algún valor dentro de datos_arrendamiento
                paquetes_filtrado =  paquetes.filter(datos_arrendamiento__deposito_rendimiento = "Si")
                print(paquetes_filtrado)
                # Reemplaza 'deposito_garantia' y '10000' con la clave y el valor específicos que estás buscando dentro de datos_arrendamiento para el rendimiento
               
                serializer = self.get_serializer(paquetes, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def create(self, request, *args, **kwargs):
        user_session = request.user
        request.data["status"] = "En Revision"
        print(user_session)
        print(request.data)
        print(request.data["status"])
     
        try:
            print("Llegando a create de paquetes")                
            paquete_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            print(paquete_serializer)
            if paquete_serializer.is_valid(raise_exception=True):
                print("entro al IF")
                paquete_serializer.save(user = user_session)
                print("Ya Guarde")
                return Response(paquete_serializer.data, status= status.HTTP_200_OK)     
            else:
                print("Error en validacion")
                return Response({'errors': paquete_serializer.errors})
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try:
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print("Request",request.data)
            instance = self.get_object()
            instance.status = request.data["status"]
            instance.ides = request.data["ides"]
            print("instance",instance.__dict__)
            instance.save()
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def generar_pagare(self, request, *args, **kwargs):
        id_paq = request.data
        print("el ID que llegas es: ",id_paq)
        info = self.queryset.filter(id = id_paq).first()
        print(info.__dict__)
        
        meses = {1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
        meses_años = {}
        meses_restantes = {}
        #estabelcemos la fecha
        fecha_cotizacion = info.datos_arrendamiento['fecha_de_pago']
        print("SOY EL FORMATO DE FECHA COTIZACION",fecha_cotizacion)
        fecha_cotizacion_datetime = datetime.strptime(fecha_cotizacion, '%Y-%m-%d')
        dia = fecha_cotizacion_datetime.day
        anio = fecha_cotizacion_datetime.year
        
        # El mes en numero
        mes = fecha_cotizacion_datetime.month
        
        #si el mes es enero solo realiza una lista
        lista_mes = list(meses.values())[(mes - 1):]
        #iteramos la lista para añadir el año actual
        for i in range(len(lista_mes)):
            meses_años[lista_mes[i]] = anio
        #si no realiza 2
        if(mes != 1):
            lista_mes_restantes = list(meses.values())[(0):(mes-1)]
            #iteramos la lista de los meses restantes para añadir el año siguente        
            for i in range(len(lista_mes_restantes)):
                meses_restantes[lista_mes_restantes[i]] = anio + 1
            #juntamos los 2 dicionarios para mandarlo como contexto
            lista_total = {**meses_años, **meses_restantes}
        else:
            lista_total = meses_años
        
        #la info del paquete que se recibe
        datos = info.inmueble
        print(datos.__dict__)
        print(info.fiador.__dict__)
        
        #obtenermos la renta para pasarla a letra
        number = datos.renta
        number = int(number)
        text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
        text_representation = text_representation.capitalize()
        print("se obtuvo la renta")

        context = {'info': info, 'dia':dia ,'lista_fechas':lista_total, 'text_representation':text_representation}
        template = 'home/plan.html'
        html_string = render_to_string(template, context)
        print("se obtuvo el contexto el y el template")
        print("Generando el PDF...")
        instanteInicial = datetime.now()
        # Genera el PDF utilizando weasyprint
        pdf_file = HTML(string=html_string).write_pdf()
        print("se genero el pdf")
        # al final de la partida
        instanteFinal = datetime.now()
        tiempo = instanteFinal - instanteInicial # Devuelve un objeto timedelta
        segundos = tiempo.seconds
        print(f"me tarde {segundos} segundos")

        # Devuelve el PDF como respuesta
        response = HttpResponse(content_type='application/pdf')
        print("se crea la respuesta")
        response['Content-Disposition'] = 'attachment; filename="mi_pagare.pdf"'
        print("se escribe la respuesta")
        response.write(pdf_file)
        print("se envia la respuesta")
        return response
    
    def generar_poliza(self, request, *args, **kwargs):
        id_paq = request.data
        print("el ID que llegas es: ",id_paq)
        info = self.queryset.filter(id = id_paq).first()
        print(info.__dict__)
        meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
    
        #estabelcemos la fecha de inicio 
        fecha_inicio = info.datos_arrendamiento['fecha_inicio_contrato']
        print("SOY EL FORMATO DE FECHA inicio",fecha_inicio)
        fecha_inicio_datetime = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        dia = fecha_inicio_datetime.day
        mes = fecha_inicio_datetime.month
        mes_inicio = meses[mes]
        anio = fecha_inicio_datetime.year
        datos_inicio = {'dia':dia, 'anio':anio ,'mes':mes_inicio}
        
        #estabelcemos la fecha de fin
        fecha_fin = info.datos_arrendamiento['fecha_fin_contrato']
        fecha_fin_datetime = datetime.strptime(fecha_fin, '%Y-%m-%d')
        dia_fin = fecha_fin_datetime.day
        mes2 = fecha_fin_datetime.month
        mes_fin = meses[mes2]
        anio_fin = fecha_fin_datetime.year
        datos_fin = {'dia':dia_fin, 'anio':anio_fin ,'mes':mes_fin}
        
        #estabelcemos la fecha de fin
        fecha_firma = info.datos_arrendamiento['fecha_firma']
        fecha_firma_datetime = datetime.strptime(fecha_firma, '%Y-%m-%d')
        dia_firma = fecha_firma_datetime.day
        mes3 = fecha_firma_datetime.month
        mes_firma = meses[mes3]
        anio_firma = fecha_firma_datetime.year
        datos_firma = {'dia':dia_firma, 'anio':anio_firma ,'mes':mes_firma}
            
        datos = info.inmueble
        print(datos.__dict__)
        print(info.fiador.__dict__)
        #obtenermos la renta para pasarla a letra
        number = datos.renta
        number = int(number)
        text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
        text_representation = text_representation.capitalize()
        #obtenermos el precio de la poliza para pasarla a letra
        precio = info.cotizacion.monto
        precio = int(precio)
        print(precio)
        precio_texto = num2words(precio, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
        precio_texto = precio_texto.capitalize()
        
        print("Tu Póliza es: ",info.cotizacion.tipo_poliza)
        if info.cotizacion.tipo_poliza == "Plata":
            template = 'home/poliza_plata.html'
            
        elif info.cotizacion.tipo_poliza == "Oro":
            template = 'home/poliza_oro.html'
            
        elif info.cotizacion.tipo_poliza == "Platino":
            template = 'home/poliza_platino.html'
       
        context = {'info': info, 'datos_inicio':datos_inicio, 'datos_fin':datos_fin,'datos_firma':datos_firma, 'text_representation':text_representation,'precio_texto':precio_texto}
        html_string = render_to_string(template, context)

        # Genera el PDF utilizando weasyprint
        pdf_file = HTML(string=html_string).write_pdf()

        # Devuelve el PDF como respuesta
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
        response.write(pdf_file)

        return response
    
    def generar_contrato(self, request, *args, **kwargs):
        try:   
            print("Generando el contrato")
            id_paq = request.data['id']
            info = self.queryset.filter(id = id_paq).first()
            meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
            
            #estabelcemos la fecha de inicio 
            fecha_inicio = info.datos_arrendamiento['fecha_inicio_contrato']
            
            fecha_inicio_datetime = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            dia = fecha_inicio_datetime.day
            mes = fecha_inicio_datetime.month
            mes_inicio = meses[mes]
            anio = fecha_inicio_datetime.year
            datos_inicio = {'dia':dia, 'anio':anio ,'mes':mes_inicio}
            
            #estabelcemos la fecha de fin
            fecha_fin = info.datos_arrendamiento['fecha_fin_contrato']
            fecha_fin_datetime = datetime.strptime(fecha_fin, '%Y-%m-%d')
            dia_fin = fecha_fin_datetime.day
            mes2 = fecha_fin_datetime.month
            mes_fin = meses[mes2]
            anio_fin = fecha_fin_datetime.year
            datos_fin = {'dia':dia_fin, 'anio':anio_fin ,'mes':mes_fin}
            
            #estabelcemos la fecha de fin
            fecha_firma = info.datos_arrendamiento['fecha_firma']
            fecha_firma_datetime = datetime.strptime(fecha_firma, '%Y-%m-%d')
            dia_firma = fecha_firma_datetime.day
            mes3 = fecha_firma_datetime.month
            mes_firma = meses[mes3]
            anio_firma = fecha_firma_datetime.year
            datos_firma = {'dia':dia_firma, 'anio':anio_firma ,'mes':mes_firma}
                
            datos = info.inmueble
        
            #obtenermos la renta para pasarla a letra
            number = datos.renta
            number = int(number)
            text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            text_representation = text_representation.capitalize()
            #obtenermos el precio de la poliza para pasarla a letra
            precio = info.cotizacion.monto
            print(precio)
            precio = float(precio)
        
            precio_texto = num2words(precio, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            precio_texto = precio_texto.capitalize()
            
            #Comprobacion de mobiliario
            mobiliario = InmueblesInmobiliario.objects.all().filter(inmuebles = info.inmueble.id)
        
            # obtenemos la fecha de pago y extraemos el dia
            dia_pago = datetime.strptime(info.datos_arrendamiento['fecha_de_pago'], '%Y-%m-%d')
            dia_pago = dia_pago.day
        
            #variables de informacion arrendador
            tipo_documento_arrendador = info.ides['ides_arrendador']
            no_doc_arrendador = info.ides['no_ide_arrendador']
            
            #variables de informacion arrendatario
            tipo_documento_arrendatario = info.ides['ides_arrendatario']
            no_doc_arrendatario = info.ides['no_ide_arrendatario']
            
            #variables de informacion fiador
            tipo_documento_fiador = info.ides['ides_fiador']
            no_doc_fiador = info.ides['no_ide_fiador']
            doc_indentificacion = {'tipo_documento_arrendador':tipo_documento_arrendador, 'no_doc_arrendador':no_doc_arrendador,
                                'tipo_documento_arrendatario':tipo_documento_arrendatario, 'no_doc_arrendatario':no_doc_arrendatario,
                                'tipo_documento_fiador':tipo_documento_fiador, 'no_doc_fiador':no_doc_fiador}
        
            #variables que selecciona el inquilino        
            #plazos
            vig_c3 = request.data['plazos']['vig_c3']#tiene que ser de 15 o 30
            vig_c15 = request.data['plazos']['vig_c15'] #tiene que ser de 30 con inclementos de 5 en 5 hasta 60
            vig_c23 = request.data['plazos']['vig_c23'] # tiene que ser 15, 30 o 60
            vig_c25 = request.data['plazos']['vig_c25'] #tiene que ser de 30 con inclementos de 5 en 5 hasta 60
            vig = {'vig_c3':vig_c3, 'vig_c15':vig_c15, 'vig_c23':vig_c23, 'vig_c25':vig_c25}
            
            context = {'info': info, 'datos_inicio':datos_inicio, 'datos_fin':datos_fin,'datos_firma':datos_firma, 'text_representation':text_representation,'precio_texto':precio_texto, 'doc_indentificacion':doc_indentificacion, "dia_pago":dia_pago, 'vig':vig, 'mobiliario':mobiliario}
            
            template = 'home/contrato.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)

            return HttpResponse(response, content_type='application/pdf')
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
class Amigos(viewsets.ModelViewSet):
    queryset = Friends.objects.all()
    def send_friend_request(self, request, *args, **kwargs):
        print(request.data)
        try:
            codeI = request.data.get('codeI')
            inqui = Inquilino.objects.get(codigo_amigo=codeI)
            print(codeI)
            if inqui.codigo_amigo == codeI:
                codeA = request.data.get('codeA')
                print(codeA)
                arren = Arrendador.objects.get(codigo_amigo=codeA)
                # friendship = self.queryset.filter('to_user'== inqui, 'from_user' == arren)
                friendship = self.queryset.filter(sender=inqui.id, receiver=arren.id)
                if friendship.exists():
                    return Response({'comentario':'Ya existe este inquilino'}, status=status.HTTP_205_RESET_CONTENT)
                else:
                    Friends.objects.create(receiver=arren, sender=inqui)
                    return Response({'comentario': 'Inquilino agregado'}, status=status.HTTP_201_CREATED)
            else:
                return Response({'comentario':'Codigo Inquilino Incorrecto'},status=status.HTTP_204_NO_CONTENT)
       
        except ValidationError as e:
                return Response({'errors': e.detail}, status=status.HTTP_401_UNAUTHORIZED)

class Encuestas(viewsets.ModelViewSet):      
    queryset = Encuesta.objects.all()
    serializer_class = EncuestaSerializer
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
                print("Esta entrando a listar cotizacion")
                encuestas =  self.get_queryset()
                serializer = self.get_serializer(encuestas, many=True)
                
           else:
                print("Esta entrando a encuestas")
                # Contar las respuestas "Muy Fácil" y "Muy Difícil" para cada pregunta
                encuestas =  Encuesta.objects.all()
               
                p1r1 =  Encuesta.objects.all().filter(pregunta1 = "Muy Buena")
                print(p1r1)
                p1r2 =  Encuesta.objects.all().filter(pregunta1 = "Buena")
                p1r3 =  Encuesta.objects.all().filter(pregunta1 = "Regular")
                p1r4 =  Encuesta.objects.all().filter(pregunta1 = "Mala")
                p1r5 =  Encuesta.objects.all().filter(pregunta1 = "Muy Mala")
                # Crear un diccionario con la cuenta de respuestas
                pregunta1 = {
                    'muy_facil': p1r1,
                    'facil': p1r2,
                    'regular': p1r3,
                    'dificil': p1r4,
                    'muy_dificil': p1r5,
                }

                p2r1 =  Encuesta.objects.all().filter(pregunta2 = "Muy Buena").count()
                p2r2 =  Encuesta.objects.all().filter(pregunta2 = "Buena")
                p2r3 =  Encuesta.objects.all().filter(pregunta2 = "Regular")
                p2r4 =  Encuesta.objects.all().filter(pregunta2 = "Mala")
                p2r5 =  Encuesta.objects.all().filter(pregunta2 = "Muy Mala")
                pregunta2 = {
                    'muy_facil': p2r1,
                    'facil': p2r2,
                    'regular': p2r3,
                    'dificil': p2r4,
                    'muy_dificil': p2r5,
                }
                
                serializer = self.get_serializer(encuestas, many=True)
            
        
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def create(self, request, *args, **kwargs):
        try:
            print(request)
            encuesta_serializer = self.serializer_class(data=request.data)
            if encuesta_serializer.is_valid(raise_exception=True):
                encuesta_serializer.save()
                return Response({'comentario': encuesta_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                return Response({'serializer no valido': encuesta_serializer.errors})
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class Inventario_fotografico(viewsets.ModelViewSet):     
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated] 
    
    queryset = Inventario_foto.objects.all()
    serializer_class = Inventario_fotoSerializer
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
                print("Esta entrando a listar inventario foto")
                inventario_fotografico =  self.get_queryset()
                serializer = self.get_serializer(inventario_fotografico, many=True)
                
           else:
                print("Esta entrando a listar inventario foto")
                inventario_fotografico =  self.get_queryset()
                serializer = self.get_serializer(inventario_fotografico, many=True)
     
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    


    def create(self, request, *args, **kwargs):
        try:
            inventario_serializer = self.serializer_class(data=request.data)
            archivo = request.FILES['inv_fotografico']  # 'archivo' es el nombre del campo de archivo en tu formulario
            tamaño = archivo.size
            print(f"El archivo que entre es {archivo} y su peso es {tamaño} bytes")
            #paso 1, hay que autenticarnos
            api_key = {'public_key': "project_public_306f10caefca911ddc39bd560343d779_gqanEb7d559d1f1d40b67136ea41e5c048457"}
            auth = requests.post("https://api.ilovepdf.com/v1/auth", api_key)
            token = auth.json()
            token_solo = token["token"]
            print("soy token",token_solo)
            
            #paso 2 iniciar el proceso
            headers = {
            'Authorization': f'Bearer {token_solo}',
            'Cookie': '_csrf=Yw9SsIIKedwL6MlLorEVBirpKi66Wfq0'
            }
            start = requests.get("https://api.ilovepdf.com/v1/start/compress", headers = headers, data = {})
            start = start.json()
            task = start["task"]
            server = start["server"]
            remaining_files = start["remaining_files"]
            print(remaining_files)
           
            if remaining_files > 0:
                print("eres mayor a cero aun hay archivos")
                #paso 3 subir el archivo a la api, Juntamos la info del archivo que requiere la peticion para enviarla
                filename = archivo.name
                file_data = ('file', (filename, archivo.file, archivo.content_type))
                files = [file_data]
    
                headers = {
                'Authorization': f'Bearer {token_solo}'
                }
                
                upload = requests.post(f"https://{server}/v1/upload", headers = headers, data = {'task': task}, files = files)
                upload = upload.json()
                server_filename = upload["server_filename"]
               
                #paso 4 comprimir el archivo
                payload = json.dumps({
                "task": task,
                "tool": "compress",
                "files": [
                    {
                    "server_filename": server_filename,
                    "filename": f"{filename}"
                    }
                ],
                "compression_level": "recommended"
                })
              
                headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token_solo}'
                }

                proceso = requests.post(f"https://{server}/v1/process", headers = headers, data = payload)
                print("proceso text",proceso.text)
                print("antes de proceso.json",proceso)
                proceso = proceso.json()
                print("despues de proceso.json",proceso)
                proceso_status = proceso["status"]
                print(proceso_status)
                
                if proceso_status == "TaskSuccess":
                    print("entre al if del status")
                    #paso 5 Obtener el archivo comprimido
                    payload = {}
                    descarga = requests.get(f"https://{server}/v1/download/{task}", headers=headers, data=payload)
                    print("sin texto plano",descarga)
                    
                    if descarga.status_code == 200:
                        print("tengo status 200")
                        print(f"esto es valido? 'compress_{filename}'")
                        with open(f'{filename}', 'wb') as f:
                            for chunk in descarga.iter_content(chunk_size=128):
                                f.write(chunk)
                        
                    #paso 6 Eliminar el archivo temporal del servidor del api
                    print("vamos a borrar")
                    payload = json.dumps({
                    "task": task,
                    "server_filename": server_filename
                    })
                    
                    headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token_solo}'
                    }
                    
                    print(f"https://{server}/v1/upload/{task}/{server_filename}")
                    borrar = requests.delete(f"https://{server}/v1/upload/{task}/{server_filename}", headers=headers)
                    

                    print(borrar.text)
                    
                else:
                    print("No se completo el proceso")
                    return Response( {"error en el proceso":"error en el proceso"}, status=status.HTTP_409_CONFLICT)
                
                print("el proceso salio bien")
                if inventario_serializer.is_valid():
                    print("soy valido")
                    
                    #inventario_serializer["paquete_asociado"] = request.data.id
                    #inventario_serializer.save()
                    
                    return Response( {"writer":descarga}, status=status.HTTP_100_CONTINUE)
                else:
                    return Response({'serializer no valido': inventario_serializer.errors})
            else:
                print("eres igual a cero aun hay archivos")
                return Response( {"0 archivos":"no hay compresiones restantes"}, status=status.HTTP_204_NO_CONTENT)
            
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# ---------------------------------- Notificaciones ---------------------------------- #


class notis_prueba(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
   
    def list(self, request, *args, **kwargs):
        print("entramos a list de notificaiones")
        user_session = request.user       
        Notify = load_model("api","Notification")
        post_con = Post.objects.all().filter(user_id = user_session)
        print("post con",post_con)
        consulta = Notification.objects.all().filter(destiny_id = user_session).order_by('-id')
        consulta2 = Notify.objects.all().filter(destiny_id = user_session)
        print("soy notify",Notify)
        print("Consulta",consulta)
        print("Consulta2",consulta2)
        print("")
        serializer2 = PostSerializer(post_con,many=True)
      
        try:
           if user_session.is_staff:
                print("Estamos entrando a listar todas las notificaciones")
                notificaciones =  self.get_queryset().order_by('-id')
                serializer = self.get_serializer(notificaciones, many=True)  
                
           else:
                print("Estamos entrando a listar todas las notificaciones de un usuario en concreto")
                serializer = self.get_serializer(consulta, many=True)
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        
    def notificaiones_por_usuario(self, request, *args, **kwargs):
        print("entramos a prueba notis")
        user_session = request.user       
        try:
            user = User.objects.get(id=user_session.id)
            posts = Post.objects.filter(user=user).order_by('-id')[:7]
            notificaciones = Notification.objects.filter(destiny=user).order_by('-id')[:7]

            data = {
                'posts': PostSerializer(posts, many=True).data,
                'notificaciones': NotificationSerializer(notificaciones, many=True).data
            }

            return Response(data)
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"el error es: {e} en la linea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)

    def send_noti(self, request, *args, **kwargs):
        try:
            #Sumar dos días a la fecha actual
            now = date.today()
            #now = datetime(2024, 7, 14) 
            rango1 = now - timedelta(days=11)
            rango2 = now - timedelta(days=4)
            print(rango1)
            print(rango2)
            print(f"el rango de fechas es del {rango1} al {rango2}")
                
        
            posts = Post.objects.filter(timestamp__range=[rango1, rango2])
            notificaciones = Notification.objects.filter(timestamp__range=[rango1, rango2])
            print('post',posts)
            posts.delete()
            notificaciones.delete()
            print('post',posts)
            # print('notificaiones',notificaciones)
            
            return Response({'notificaciones y posts eliminados': "simon" }, status=status.HTTP_400_BAD_REQUEST)  
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"el error es: {e} en la linea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)


      
    
        
    
    # def send_noti(self, request, *args, **kwargs):
    #     user_session = request.user
        
    #     print("el que envia es: ", user_session)
    #     print("request",request.data)
    #     destinatarios = User.objects.all().filter(pertenece_a = 'Arrendify')
    #     destinies = list[destinatarios]
    #     print(destinies)
    #     destinatarios2 = User.objects.all().filter(username = 'AndresMtzO')
    #     print("destinatarios",destinatarios)
    #     print("destinatarios2",destinatarios2)
    #     print("request verbo",request.data['title'])
    #     try:
    #         print("entramos en el tri")
    #         user_session = request.user
    #         print("user",user_session)
    #         actor = destinatarios2.first()
    #         print("actor",actor)
    #         request.data._mutable=True
    #         request.data['user'] = user_session.id
            
          
    #         print(request.data)
    #         print("Llegando a create de post")
    #         post_serializer = PostSerializer(data=request.data) #Usa el serializer_class
    #         if post_serializer.is_valid(raise_exception=True):
    #             for destiny in destinatarios:
    #                 print("hola")
    #                 print("destinyes",destiny)
    #                 datos = post_serializer.save(user = actor)
    #                 print("Guardado residente")
    #                 print('datos',datos)
    #             # notify_post(Post, datos, created=True, actor=actor)
    #             return Response({'Post': post_serializer.data}, status=status.HTTP_201_CREATED)
    #         else:
    #             print("Error en validacion")
    #             return Response({'errors': post_serializer.errors})
            
    #     except Exception as e:
    #         return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def leer_todas(self, request, *args, **kwargs):
        print("entramos a leer todo")
        user_session = request.user  
        try:
            notificaciones = Notification.objects.filter(destiny=user_session, read = False)
            print("notificaiones mias papi",notificaciones)
            if notificaciones:
                print("vamos a leer")
                for noti in notificaciones:
                    print("noti.read",noti.read)
                    noti.read = True
                    noti.save()
                return Response({'leidas':'leidas'})

            return Response({'No hay notis nueva':'No hay notis nueva'})
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"el error es: {e} en la linea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)