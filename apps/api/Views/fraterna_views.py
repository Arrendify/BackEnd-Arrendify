from rest_framework import viewsets
from rest_framework.response import Response
from ...home.models import *
from ...home.models import DocumentosArrendamientosFraterna as DocumentosArrendamientosFraternaModel
from ...home.models import IncidenciasFraterna as IncidenciasFraternaModel
from ..serializers import *
from rest_framework import status
from ...accounts.models import CustomUser
User = CustomUser
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponse
from django.forms.models import model_to_dict

#s3
import boto3
from botocore.exceptions import ClientError
from botocore.exceptions import NoCredentialsError
from django.db.models import Q
from django.core.exceptions import ValidationError
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, API_TOKEN_ZAPSIGN, API_URL_ZAPSIGN
#weasyprint
from weasyprint import HTML, CSS
from django.template.loader import render_to_string
from django.template.loader import get_template
#Legal
from num2words import num2words
from datetime import date
from datetime import datetime

#Libreria para obtener el lenguaje en español
import locale

import re
#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)

#variables para el correo
from ..variables import *

#enviar por correo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from smtplib import SMTPException
from django.core.files.base import ContentFile
from decouple import config

# Para combinación de PDFs
import base64, io, sys
import requests
from rest_framework.decorators import action
from collections import defaultdict

from pypdf import PdfReader, PdfWriter
from datetime import datetime as dt
from datetime import datetime, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta

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
        print("No se encontraron las credenciales de AWS.",{NoCredentialsError})
        
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
# ----------------------------------Metodos Extras----------------------------------------------- #

########################## F R A T E R N A ######################################
class ResidenteViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Residentes.objects.all()
    serializer_class = ResidenteSerializers
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
                print("Esta entrando a listar Residentes")
                residentes =  Residentes.objects.all().order_by('-id')
                serializer = self.get_serializer(residentes, many=True)
                return Response(serializer.data, status= status.HTTP_200_OK)
            
           elif user_session.rol == "Inmobiliaria" or user_session.username == "ElbaJ": 
                #tengo que busca a los inquilinos que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de Residentes propios y registrados por mis agentes
                inquilinos_a_cargo = Residentes.objects.filter(user_id__in = agentes)
                inquilinos_mios = Residentes.objects.filter(user_id = user_session)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
                mios = mios.order_by('-id')
               
                serializer = self.get_serializer(mios, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                
                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['inmobiliaria'] = True
                    
                return Response(serialized_data)      
            
           elif user_session.rol == "Agente":  
                print("soy Agente", user_session.first_name)
                #obtengo mis inquilinos
                residentes_ag = Residentes.objects.filter(user_id = user_session)
                residentes_ag = residentes_ag.order_by('-id')
                #tengo que obtener a mis inquilinos vinculados
              
                serializer = self.get_serializer(residentes_ag, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)
           else:
                print("Esta entrando a listar Residentes fil")
                fiadores_obligados =  Residentes.objects.all().filter(user_id = user_session)
                serializer = self.get_serializer(fiadores_obligados, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print("Llegando a create de residentes")
            print(request.data)
            residente_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            print(residente_serializer)
            if residente_serializer.is_valid(raise_exception=True):
                residente_serializer.save( user = user_session)
                print("Guardado residente")
                return Response({'Residentes': residente_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion")
                return Response({'errors': residente_serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def update(self, request, *args, **kwargs):
        try:
            print("Esta entrando a actualizar Residentes")
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print(request.data)
            instance = self.get_object()
            print("instance",instance)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            #print(serializer)
            if serializer.is_valid(raise_exception=True):
                # Guardar los cambios explícitamente
                self.perform_update(serializer)
                # Refrescar la instancia desde la base de datos para asegurar que tenemos los datos actualizados
                instance.refresh_from_db()
                # Volver a serializar para obtener los datos actualizados
                serializer = self.get_serializer(instance)
                print("edito residente")
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            user_session = request.user
            print("Entrando a retrieve")
            modelos = Residentes.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            Residentes = modelos.filter(slug=slug)
            if Residentes:
                serializer_Residentes = ResidenteSerializers(Residentes, many=True)
                return Response(serializer_Residentes.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            print("LLegando a eliminar residente")
            Residentes = self.get_object()
            if Residentes:
                Residentes.delete()
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
  
    def mandar_aprobado(self, request, *args, **kwargs):  
        try:
            print("Aprobar al residente")
            info = request.data
            print("el id que llega", info )
            print("accediendo a informacion", info["estado_civil"])
            today = date.today().strftime('%d/%m/%Y')
            ingreso = int(info["ingreso"])
            ingreso_texto = num2words(ingreso, lang='es').capitalize()
            context = {'info': info, "fecha_consulta":today, 'ingreso':ingreso, 'ingreso_texto':ingreso_texto}
        
            # Renderiza el template HTML  
            template = 'home/aprobado_fraterna.html'
    
            html_string = render_to_string(template, context)# lo comvertimos a string
            pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
            print("pdf realizado")
            
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
            print("antes de enviar_archivo",context)
            self.enviar_archivo(archivo, info)
            print("PDF ENVIADO")
            return Response({'Mensaje': 'Todo Bien'},status= status.HTTP_200_OK)
        
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
                  
    def enviar_archivo(self, archivo, info, comentario="nada"):
        print("")
        print("entrando a enviar archivo")
        print("soy pdf content",archivo)
        print("soy comentario",comentario)
        arrendatario = info["nombre_arrendatario"]
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            # destinatario = 'jsepulvedaarrendify@gmail.com'
            destinatario = 'jcasados@fraterna.mx'
            # destinatario2 = 'juridico.arrendify1@gmail.com'
            destinatario2 = 'smosqueda@fraterna.mx'
            
            
            asunto = f"Resultado Investigación Arrendatario {arrendatario}"
            
           
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Cc'] = destinatario2
            msg['Subject'] = asunto
            print("paso objeto mime")
           
            # Estilo del mensaje
            #variable resultado_html_fraterna
            pdf_html = aprobado_fraterna(info)
          
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("pase el msg attach 1")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Resultado_investigación.pdf')
            msg.attach(pdf_part)
            print("pase el msg attach 2")
            
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
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})
        
class DocumentosRes(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosResidentes.objects.all()
    serializer_class = DRSerializer
   
    def list(self, request, *args, **kwargs):
        try:
            content = {
                'user': str(request.user),
                'auth': str(request.auth),
            }
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def create (self, request, *args,**kwargs):
        try: 
            user_session = str(request.user.id)
            data = request.data
            data = {
                    "Ine": request.FILES.get('Ine', None),
                    "Ine_arr": request.FILES.get('Ine_arr', None),
                    "Comp_dom": request.FILES.get('Comp_dom', None),
                    "Rfc": request.FILES.get('Rfc', None),
                    "Ingresos": request.FILES.get('Ingresos', None),
                    "Extras": request.FILES.get('Extras', None),
                    "Recomendacion_laboral": request.FILES.get('Recomendacion_laboral', None),
                    "residente":request.data['residente'],
                    "user":user_session
                }
          
            if data:
                documentos_serializer = self.get_serializer(data=data)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save()
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            documentos_inquilinos = self.get_object()
            documento_inquilino_serializer = self.serializer_class(documentos_inquilinos)
            print("Soy ine", documento_inquilino_serializer.data['ine'])
            print("1")
            if documentos_inquilinos:
                ine = documento_inquilino_serializer.data['ine']
                print("Soy ine 2", ine)
                comp_dom= documento_inquilino_serializer.data['comp_dom']
                rfc= documento_inquilino_serializer.data['escrituras_titulo']
                print("Soy RFC", rfc)
                ruta_ine = 'apps/static'+ ine
                print("Ruta ine", ruta_ine)
                ruta_comprobante_domicilio = 'apps/static'+ comp_dom
                ruta_rfc = 'apps/static'+ rfc
                print("Ruta com", ruta_comprobante_domicilio)
                print("Ruta RFC", ruta_rfc)
            
                # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
                documentos_inquilinos.delete()
                return Response({'message': 'Archivo eliminado correctamente'}, status=204)
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
        
    def retrieve(self, request, pk=None):
        try:
            documentos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            inquilino = documentos.filter(id=pk)
            serializer_inquilino = DISerializer(inquilino, many=True)
            print(serializer_inquilino.data)
            ine = serializer_inquilino.data[0]['ine']
            print(ine)
            # documentos_arrendador = self.get_object()
            # print(documentos_arrendador)
            return Response(serializer_inquilino.data)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
   
    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print(request.data)
            # Verificar si se proporciona un nuevo archivo adjunto
            if 'Ine' in request.data:
                print("entro aqui")
                Ine = request.data['Ine']
                archivo = instance.Ine
                eliminar_archivo_s3(archivo)
                instance.Ine = Ine  # Actualizar el archivo adjunto sin eliminar el anterior
            
            if 'Ine_arr' in request.data:
                print("arr")
                Ine_arr = request.data['Ine_arr']
                archivo = instance.Ine_arr
                eliminar_archivo_s3(archivo)
                instance.Ine_arr = Ine_arr  # Actualizar el archivo adjunto sin eliminar el anterior
                
            if 'Comp_dom' in request.data:
                Comp_dom = request.data['Comp_dom']
                archivo = instance.Comp_dom
                print(archivo)
                eliminar_archivo_s3(archivo)
                instance.Comp_dom = Comp_dom  # Actualizar el archivo adjunto sin eliminar el anterior
                
            if 'Rfc' in request.data:
                Rfc = request.data['Rfc']
                archivo = instance.Rfc
                eliminar_archivo_s3(archivo)
                instance.Rfc = Rfc  # Actualizar el archivo adjunto sin eliminar el anterior
            
            if 'Extras' in request.data:
                Extras = request.data['Extras']
                archivo = instance.Extras
                eliminar_archivo_s3(archivo)
                instance.Extras = Extras  # Actualizar el archivo adjunto sin eliminar el anterior
            
            if 'Ingresos' in request.data:
                Ingresos = request.data['Ingresos']
                archivo = instance.Ingresos
                eliminar_archivo_s3(archivo)
                instance.Ingresos = Ingresos  # Actualizar el archivo adjunto sin eliminar el anterior
            
            if 'Recomendacion_laboral' in request.data:
                Recomendacion_laboral = request.data['Recomendacion_laboral']
                archivo = instance.Recomendacion_laboral
                eliminar_archivo_s3(archivo)
                instance.Recomendacion_laboral = Recomendacion_laboral  # Actualizar el archivo adjunto sin eliminar el anterior
            
        
            serializer.update(instance, serializer.validated_data)
            print(serializer.data['Ine'])# Actualizar el archivo adjunto sin eliminar el anterior
            print(serializer)# Actualizar el archivo adjunto sin eliminar el anterior
            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)  
        
#////////////////////////CONTRATOS///////////////////////////////
class Contratos_fraterna(viewsets.ModelViewSet):
    # authentication_classes = [TokenAuthentication, SessionAuthentication]
    # permission_classes = [IsAuthenticated]
    queryset = FraternaContratos.objects.all()
    serializer_class = ContratoFraternaSerializer
    
    def list(self, request, *args, **kwargs):
        try:
           user_session = request.user       
           if user_session.is_staff:
               print("Esta entrando a listar contratos semullero")
               contratos =  FraternaContratos.objects.all().order_by('-id')
               serializer = self.get_serializer(contratos, many=True)
               serialized_data = serializer.data
                
               # Agregar el campo 'is_staff'
               for item in serialized_data:
                 item['is_staff'] = True
                
               return Response(serialized_data)
           
           elif user_session.rol == "Inmobiliaria":
               #primero obtenemos mis agentes.
               print("soy inmobiliaria en listar contratos", user_session.name_inmobiliaria)
               agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
               #obtenemos los contratos
               contratos_mios = FraternaContratos.objects.filter(user_id = user_session.id)
               contratos_agentes = FraternaContratos.objects.filter(user_id__in = agentes.values("id"))
               contratos_all = contratos_mios.union(contratos_agentes)
               contratos_all = contratos_all.order_by('-id')
               
               print("es posible hacer esto:", contratos_all)
               
               serializer = self.get_serializer(contratos_all, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
               
           elif user_session.rol == "Agente":
               print(f"soy Agente: {user_session.first_name} en listar contrato")
               residentes_ag = FraternaContratos.objects.filter(user_id = user_session).order_by('-id')
              
               serializer = self.get_serializer(residentes_ag, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
                 
        #    else:
        #        print(f"soy normalito: {user_session.first_name} en listar contrato")
        #        residentes_ag = FraternaContratos.objects.filter(user_id = user_session)
              
        #        serializer = self.get_serializer(residentes_ag, many=True)
        #        return Response(serializer.data, status= status.HTTP_200_OK)
           
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print(user_session)
            print("RD",request.data)
            print("Request",request)
            print("Llegando a create de contrato para fraterna")
            
            fecha_actual = date.today()
            contrato_serializer = self.serializer_class(data = request.data) #Usa el serializer_class
            if contrato_serializer.is_valid():
                nuevo_proceso = ProcesoContrato.objects.create(usuario = user_session, fecha = fecha_actual, status_proceso = "En Revisión")
                if nuevo_proceso:
                    print("ya la armamos")
                    print(nuevo_proceso.id)
                    info = contrato_serializer.save(user = user_session)
                    nuevo_proceso.contrato = info
                    nuevo_proceso.save()
                    send_noti_varios(FraternaContratos, request, title="Nueva solicitud de contrato en Fraterna", text=f"A nombre del Arrendatario {info.residente.nombre_arrendatario}", url = f"fraterna/contrato/#{info.residente.id}_{info.cama}_{info.no_depa}")
                    print("despues de metodo send_noti")
                    print("Se Guardado solicitud")
                    return Response({'Residentes': contrato_serializer.data}, status=status.HTTP_201_CREATED)
                else:
                    print("no se creo el proceso")
                    return Response({'msj':'no se creo el proceso'}, status=status.HTTP_204_NO_CONTENT) 
            
            else:
                print("serializer no valido")
                return Response({'msj':'no es valido el serializer'}, status=status.HTTP_204_NO_CONTENT)     
            
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try:
            #primero verificamos que tenga contadores activos
            print("Esta entrando a actualizar Contratos Fraterna")
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
           
            # Verificar si se proporciona un nuevo archivo adjunto
            if 'plano_localizacion' in request.data:
                print("entro aqui")
                nuevo = request.data['plano_localizacion']
                archivo = instance.plano_localizacion
                eliminar_archivo_s3(archivo)
                instance.plano_localizacion = nuevo  # Actualizar el archivo adjunto sin eliminar el anterior
                        
            proceso = ProcesoContrato.objects.all().get(contrato_id = instance.id)
            print("el contador es: ",proceso.contador)
            if (proceso.contador > 0 ):
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                if serializer.is_valid(raise_exception=True):
                    self.perform_update(serializer)
                    # proceso.contador = proceso.contador - 1
                    # proceso.save()
                    print("edito proceso contrato")
                    send_noti_varios(FraternaContratos, request, title="Se a modificado el contrato de:", text=f"FRATERNA VS {instance.residente.nombre_arrendatario} - {instance.residente.nombre_residente}".upper(), url = f"fraterna/contrato/#{instance.residente.id}_{instance.cama}_{instance.no_depa}")
                    return Response(serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response({'errors': serializer.errors})
            else:
                return Response({'msj': 'LLegaste al limite de tus modificaciones en el proceso'}, status=status.HTTP_205_RESET_CONTENT)
      
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy(self,request, *args, **kwargs):
        try:
            residente = self.get_object()
            if residente:
                residente.delete()
                return Response({'message': 'residente eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def aprobar_contrato(self, request, *args, **kwargs):
        try:
            print("update status contrato")
            print("Request",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("mi id es: ",instance.id)
            print(instance.__dict__)
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def desaprobar_contrato(self, request, *args, **kwargs):
        try:
            print("desaprobar Contrato")
            instance = self.queryset.get(id = request.data["id"])
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = "En Revisión"
            proceso.contador = 2 # en vista que me indiquen lo contrario lo dejamos asi
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a desaprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_pagare(self, request, *args, **kwargs):
        try:
            #activamos la libreri de locale para obtener el mes en español
            print("Generar Pagare Fraterna")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            id_paq = request.data["id"]
            pagare_distinto = request.data["pagare_distinto"]
            
            if pagare_distinto == "Si":
                if "." not in request.data["cantidad_pagare"]:
                    print("no hay yaya pagare")
                    cantidad_pagare = request.data["cantidad_pagare"]
                    cantidad_decimal = "00"
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
                
                else:
                    cantidad_completa = request.data["cantidad_pagare"].split(".")
                    cantidad_pagare = cantidad_completa[0]
                    cantidad_decimal = cantidad_completa[1]
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
            else:
                cantidad_pagare = 0
                cantidad_decimal = "00"
                cantidad_letra = num2words(cantidad_pagare, lang='es')
            
            print(pagare_distinto)
            print(cantidad_pagare)   

            # id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)       
            # Definir la fecha inicial
            fecha_inicial = info.fecha_move_in
            print(fecha_inicial)
            #fecha_inicial = datetime(2024, 3, 20)
            #checar si cambiar el primer dia o algo asi
            # fecha inicial move in
            dia = fecha_inicial.day
            
            # Definir la duración en meses
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            print("duracion en meses",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_inicial < fecha_final:
                nombre_mes = fecha_inicial.strftime("%B")  # %B da el nombre completo del mes
                print("fecha",fecha_inicial.year)
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_inicial.year))      
                fecha_inicial += relativedelta(months=1)
            
            print("fechas_iteradas",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            for month, year in fechas_iteradas:
                print(f"Año: {year}, Mes: {month}")
            
            #obtenermos la renta para pasarla a letra
            if "." not in info.renta:
                print("no hay yaya")
                number = int(info.renta)
                renta_decimal = "00"
                text_representation = num2words(number, lang='es').capitalize()
               
            else:
                print("tengo punto en renta")
                renta_completa = info.renta.split(".")
                info.renta = renta_completa[0]
                renta_decimal = renta_completa[1]
                text_representation = num2words(renta_completa[0], lang='es').capitalize()

            # 'es' para español, puedes cambiarlo según el idioma deseado
            
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'pagare_distinto':pagare_distinto , 'cantidad_pagare':cantidad_pagare, 'cantidad_letra':cantidad_letra, 'cantidad_decimal':cantidad_decimal, 'renta_decimal':renta_decimal}
            
            template = 'home/pagare_fraterna.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)

            return HttpResponse(response, content_type='application/pdf')
    
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_poliza(self, request, *args, **kwargs):
        try:
            print("Generar Poliza Fraterna")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)
            
            #vamos a genenrar el numero de contrato
            arrendatario = info.residente.nombre_arrendatario
            primera_letra = arrendatario[0].upper()  # Obtiene la primera letra
            ultima_letra = arrendatario[-1].upper()  # Obtiene la última letra

            year = info.fecha_celebracion.strftime("%g")
            month = info.fecha_celebracion.strftime("%m")
            
            nom_contrato = f"AFY{month}{year}CX51{info.id}CA{primera_letra}{ultima_letra}"  
            print("Nombre del contrato", nom_contrato)     
            #obtenemos renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
       
            context = {'info': info, 'renta_texto':renta_texto, 'nom_contrato':nom_contrato,}
            template = 'home/poliza_fraterna.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO POLIZA")
            return HttpResponse(response, content_type='application/pdf')
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_contrato(self, request, *args, **kwargs):
        try:
            print("Generar contrato Fraterna")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)       
            #obtenermos la renta para pasarla a letra
            habitantes = int(info.habitantes)
            habitantes_texto = num2words(habitantes, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            #obtenemos renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            #obtener la tipologia
            # Definir las opciones y sus correspondientes valores para la variable "plano"
            opciones = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png"
            }
            
            inventario = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.png"
            }
            
            tipologia = info.tipologia
            if tipologia in opciones and tipologia in inventario:
                plano = opciones[tipologia]
                tabla_inventario = inventario[tipologia]
                print(f"Tu Tipologia es: {tipologia}, URL: {plano}")
                print(f"Tu Tipologia es: {tipologia}, Inventario: {tabla_inventario}")
            
            #obtener la url de el plano que sube fraterna
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
           
            context = {'info': info, 'habitantes_texto':habitantes_texto, 'renta_texto':renta_texto, 'plano':plano, 'plan_loc':plan_loc, 'tabla_inventario':tabla_inventario}
            template = 'home/contrato_fraterna.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO CONTRATO")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST) 
        
    def generar_comodato(self, request, *args, **kwargs):
        try:
            print("Generar comodato Fraterna")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)       
            #obtenermos la duracion para pasarla a letra
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            duracion_texto = num2words(duracion_meses, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            #obtenemos renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            #obtener la tipologia
            # Definir las opciones y sus correspondientes valores para la variable "plano"
            opciones = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png"
            }
            
            inventario = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.png"
            }
            
            tipologia = info.tipologia
            if tipologia in opciones and tipologia in inventario:
                plano = opciones[tipologia]
                tabla_inventario = inventario[tipologia]
                print(f"Tu Tipologia es: {tipologia}, URL: {plano}")
                print(f"Tu Tipologia es: {tipologia}, Inventario: {tabla_inventario}")
            
            #obtener la url de el plano que sube fraterna
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
           
            context = {'info': info, 'duracion_meses':duracion_meses, 'duracion_texto':duracion_texto, 'renta_texto':renta_texto, 'plano':plano, 'plan_loc':plan_loc, 'tabla_inventario':tabla_inventario}
            template = 'home/comodato_fraterna.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO CONTRATO")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST) 
    
    def _generar_paquete_fraterna_pdf(self, id_paq, pagare_distinto="No", cantidad_pagare="0"):
        """
        Función auxiliar que genera un paquete PDF combinado con los siguientes documentos:
        1. Comodato
        2. Contrato
        3. Manual UTO (descargado desde AWS)
        4. Póliza
        5. Pagarés

        Parámetros:
            - id_paq: ID del contrato
            - pagare_distinto: "Sí" o "No"
            - cantidad_pagare: Cantidad de pagarés si aplica

        Devuelve:
            - tuple: (nombre_archivo, bytes del PDF combinado)
        """
        # Guardar el registro de paginas totales para usar en coordenadas de firmantes
        total_paginas = {
            "comodato": 0,
            "arrendamiento": 0,
            "manual": 0,
            "poliza": 0,
            "pagares": 0,
        }

        print("Generando paquete PDF para Fraterna...")
        locale.setlocale(locale.LC_ALL, "es_MX.utf8")

        # Obtener información del contrato
        info = self.queryset.filter(id=id_paq).first()
        if not info:
            raise ValueError("Contrato no encontrado")

        pdf_writer = PdfWriter()

        # 1. Comodato
        print("Generando Comodato...")
        comodato_pdf = self._generar_comodato_interno(info)
        comodato_reader = PdfReader(io.BytesIO(comodato_pdf))
        total_paginas["comodato"] = len(comodato_reader.pages)
        for page in comodato_reader.pages:
            pdf_writer.add_page(page)

        # 2. Contrato
        print("Generando Contrato...")
        contrato_pdf = self._generar_contrato_interno(info)
        contrato_reader = PdfReader(io.BytesIO(contrato_pdf))
        total_paginas["arrendamiento"] = len(contrato_reader.pages)
        for page in contrato_reader.pages:
            pdf_writer.add_page(page)

        # 3. Manual UTO desde AWS
        print("Descargando Manual UTO desde AWS...")
        manual_url = "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/ManualUtower.pdf"
        try:
            response_manual = requests.get(manual_url, timeout=30)
            response_manual.raise_for_status()
            manual_reader = PdfReader(io.BytesIO(response_manual.content))
            total_paginas["manual"] = len(manual_reader.pages)
            for page in manual_reader.pages:
                pdf_writer.add_page(page)
            print("Manual UTO agregado exitosamente")
        except Exception as e:
            print(f"Error al descargar manual UTO: {e}")

        # 4. Póliza
        print("Generando Póliza...")
        poliza_pdf = self._generar_poliza_interno(info)
        poliza_reader = PdfReader(io.BytesIO(poliza_pdf))
        total_paginas["poliza"] = len(poliza_reader.pages)
        for page in poliza_reader.pages:
            pdf_writer.add_page(page)

        # 5. Pagarés
        print("Generando Pagarés...")
        pagare_pdf = self._generar_pagare_interno(info, pagare_distinto, cantidad_pagare)
        pagare_reader = PdfReader(io.BytesIO(pagare_pdf))
        total_paginas["pagares"] = len(pagare_reader.pages)
        for page in pagare_reader.pages:
            pdf_writer.add_page(page)

        # PDF final
        output_pdf = io.BytesIO()
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)

        # Nombre con fecha
        fecha_actual = dt.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"Paquete_Completo_Fraterna_{info.residente.nombre_arrendatario}_{fecha_actual}.pdf"

        return nombre_archivo, output_pdf.getvalue(), total_paginas


    def build_payload_to_zapsign(self, contrato_data):
        """ Datos del contrado: contrato_data = {"id", "filename", "base64_pfd", "residente"}
            Aquí armamos el payload que se va enviar para la solicitud
            de creacion del documento 

        """
        data = contrato_data
        singer = data["residente"]
        brand_logo = "https://pagosprueba.s3.us-east-1.amazonaws.com/ZapSign/logo-contratodearrendamiento.webp"

        return {
            "name": data["filename"],                                          # Nombre del documento que verá el usuario
            "base64_pdf": data["base64_pfd"],                                  # PDF codificado en base64 (sin encabezado data:...)
            "external_id": data["id"],                                         # ID opcional para enlazar con sistema externo

            "signers": [  # Lista de personas que deben firmar
                {
                    "name": "FRATERNA ADMINISTRADORA DE PROYECTOS, S.A. DE C.V.'' REPRESENTADA POR CARLOS MANUEL PADILLA SILVA",
                    "phone_country": "52",

                },
                {
                    "name": singer["nombre_arrendatario"],
                    "email": singer["correo_arrendatario"],
                    "phone_country": "52",
                    "phone_number": singer["celular_arrendatario"],
                    "send_automatic_email": True,
                    "send_automatic_whatsapp": False,
                },
                {
                    "name": singer["nombre_residente"],
                    "email": singer["correo_residente"],
                    "phone_country": "52",
                    "phone_number": singer["celular_residente"],
                    "send_automatic_email": True,
                    "send_automatic_whatsapp": False,
                },
                {
                    "name": "JONATHAN GUADARRAMA SALGADO",
                    "email": "genaro.guadarrama@arrendify.com",
                    "phone_country": "52",
                    "phone_number": "5531398629",
                    "send_automatic_email": True,
                }
                # Campos extras para el firmante, consultar documentación, 
                # ya que algunos tienen costos extra
                # {
                #     "name": "Uriel Aguilar Ortega",                          # Nombre del firmante
                #     "email": "desarrolloewmx2024@gmail.com",                 # Email al que se enviará solicitud de firma
                #     "auth_mode": "assinaturaTela",                           # Tipo de autenticación (pantalla sin verificación extra)
                #     "send_automatic_email": True,                            # Enviar correo automáticamente
                #     "send_automatic_whatsapp": False,                        # Enviar WhatsApp automáticamente (si hay teléfono)
                #     "order_group": None,                                     # Agrupación para firmar por orden (si se activa)
                #     "custom_message": "",                                    # Mensaje personalizado en correo de firma
                #     "phone_country": "52",                                   # Código de país (México = 52)
                #     "lock_email": False,                                     # Evita que edite su correo en la pantalla de firma
                #     "blank_email": False,                                    # Oculta email en la interfaz
                #     "hide_email": False,                                     # Oculta completamente el campo email
                #     "lock_phone": False,                                     # Bloquea el número telefónico
                #     "blank_phone": False,                                    # Oculta teléfono en la interfaz
                #     "hide_phone": False,                                     # Oculta completamente el campo teléfono
                #     "lock_name": False,                                      # Bloquea el nombre (no editable)
                #     "require_cpf": False,                                    # Exigir CPF (solo Brasil)
                #     "cpf": "",                                               # Número de CPF (si se requiere)
                #     #"require_selfie_photo": True,                            # Solicita selfie al firmar
                #     "require_document_photo": True,                          # Solicita foto de documento (INE, pasaporte)
                #     "selfie_validation_type": "liveness-document-match",     # Tipo de validación de selfie (verifica con documento)
                #     "selfie_photo_url": "",                                  # URL opcional de la selfie previa
                #     "document_photo_url": "",                                # URL de la foto del documento frontal
                #     "document_verse_photo_url": "",                          # URL del reverso del documento (si aplica)
                #     "qualification": "",                                     # Cargo o rol (opcional, visible en certificado)
                #     "external_id": "",                                       # ID externo único para este firmante
                #     "redirect_link": ""                                      # URL de redirección post-firma (opcional)
                # }
            ],

            "lang": "es",                                                    # Idioma del documento e interfaz de firma
            "disable_signer_emails": False,                                  # Desactiva todos los correos a firmantes
            "brand_logo": brand_logo,                                        # URL del logotipo de tu marca
            "brand_primary_color": "#672584",                                # Color primario (hex) de tu marca
            "brand_name": "Arrendify",                                       # Nombre de la marca que aparece en la firma
            "folder_path": "/FRATERNA",                                      # Carpeta donde se guarda el documento
            "created_by": "juridico.arrendify1@gmail.com",                    # Email del creador del documento
            #"date_limit_to_sign": "2025-07-18T17:45:00.000000Z",             # Fecha límite para firmar el documento
            "signature_order_active": False,                                 # Requiere que los firmantes firmen en orden
            # "observers": [                                                   # Lista de emails que solo observarán el proceso
            #     "urielaguilarortega@gmail.com",
            #     "desarrolloweb.ewmx@gmail.com"
            # ],
            "reminder_every_n_days": 0,                                      # Intervalo de recordatorios automáticos (0 = sin recordatorios)
            "allow_refuse_signature": True,                                  # Permite al firmante rechazar la firma
            "disable_signers_get_original_file": False                       # Bloquea que los firmantes descarguen el documento final
        }
    
    def armar_payload_posiciones_firma(self, signer_tokens, total_paginas, residente):
        rubricas = []

        # Calcular offsets por sección
        offsets = {}
        acumulador = 0
        for nombre, paginas in total_paginas.items():
            offsets[nombre] = acumulador
            acumulador += paginas

        # Definir posiciones por sección
        posiciones_por_seccion = {
            "comodato": [
                (0, 1.5, 5.0, 0),
                (0, 1.5, 75.0, 1),
                (1, 13.0, 18.0, 0),
                (1, 13.0, 65.0, 1),
                (2, 5.0, 75.0, 1),
                (3, 26.5, 18.0, 1)
            ],
            "arrendamiento": [],
            "manual": [],
            "poliza": [],
            "pagares": []
        }

        # ARRRENDAMIENTO: [0, 1, 2] en cada página (izq-centro-der)
        arr_total = total_paginas["arrendamiento"]
        for i in range(arr_total):
            posiciones_por_seccion["arrendamiento"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 2)
            ])

        # MANUAL: [1, 2] más separados en la parte baja derecha
        man_total = total_paginas["manual"]
        for i in range(man_total):
            posiciones_por_seccion["manual"].extend([
                (i, 5.0, 55.0, 1),
                (i, 5.0, 80.0, 2)
            ])

        # POLIZA: [0, 1, 3] (izq-centro-der)
        pol_total = total_paginas["poliza"]
        for i in range(pol_total):
            posiciones_por_seccion["poliza"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 3)
            ])

        # PAGARES: firmantes condicionales según residente.aval y edad
        pag_total = total_paginas["pagares"]

        aval = residente.get("aval", "").strip()
        edad = int(residente.get("edad", 0))

        for i in range(pag_total):
            # Firmante 2 (residente) siempre firma
            posiciones_por_seccion["pagares"].append((i, 16.0, 55.0, 2))

            # Si la condición se cumple, también firma el firmante 1 (arrendatario)
            if aval == "Si" and edad >= 18:
                posiciones_por_seccion["pagares"].append((i, 33.0, 55.0, 1))

        # Construcción final del payload con offset aplicado
        for seccion, posiciones in posiciones_por_seccion.items():
            offset = offsets[seccion]
            for page, bottom, left, signer_index in posiciones:
                if signer_index < len(signer_tokens):
                    rubricas.append({
                        "page": page + offset,
                        "relative_position_bottom": bottom,
                        "relative_position_left": left,
                        "relative_size_x": 19.55,
                        "relative_size_y": 9.42,
                        "type": "signature",
                        "signer_token": signer_tokens[signer_index]
                    })

        return {"rubricas": rubricas}


    def subir_documento_a_zapsign(self, contrato_data):
        # Armar payload para subir documento
        payload = self.build_payload_to_zapsign(contrato_data)

        headers = {
            'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}',
            'Content-Type': 'application/json'
        }
        print("Solicitando documento a Zapsign")

        url = f'{API_URL_ZAPSIGN}docs/'

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()

            try:
                response_data = response.json()
            except ValueError:
                print("⚠️ La respuesta no está en formato JSON.")
                response_data = {"raw_response": response.text}

            # Extraer token del documento
            doc_token = response_data.get("token")

            # Extraer tokens de firmantes
            signer_tokens = [s.get("token") for s in response_data.get("signers", []) if s.get("token")]

            if not doc_token:
                raise ValueError("No se pudo obtener el token del documento desde la respuesta.")

            print("Token del documento generado:", doc_token)
            print("ID del contrato que se va a actualizar:", contrato_data["id"])

            # Guardar token en la base de datos
            info = self.queryset.filter(id=contrato_data["id"]).first()
            if not info:
                raise ValueError("Contrato no encontrado en la base de datos.")

            info.token = doc_token
            info.save()
            print("Token guardado exitosamente en la base de datos.")            

            # Armar y enviar payload de rubricas
            rubricas_payload = self.armar_payload_posiciones_firma(signer_tokens, contrato_data["total_paginas"], contrato_data["residente"])
            posicionar_url = f'{API_URL_ZAPSIGN}docs/{doc_token}/place-signatures/'
            print("📤 Enviando posiciones de firmas...")

            posicionar_response = requests.post(
                posicionar_url,
                headers=headers,
                json=rubricas_payload,
                timeout=60
            )

            posicionar_response.raise_for_status()
            print("Posiciones de firmas configuradas correctamente.")

            return {
                "payload": payload,
                "doc_token": doc_token,
                "zapsign_new_doc": response_data,
                "rubricas_payload": rubricas_payload,
                "rubricas_response": posicionar_response.text or "Sin contenido"
            }

        except requests.exceptions.Timeout:
            print("Error: Tiempo de espera agotado al comunicar con ZapSign.")
        except requests.exceptions.RequestException as e:
            print(f"Error en la solicitud a Zap-Sign: {e}")
        except Exception as e:
            print(f"Error inesperado: {e}")

        return None

    def generar_urls_firma_fraterna(self, request, *args, **kwargs):
        """
        Devuelve el paquete combinado en base64 para uso en proceso de firma
        con la plataforma de zapsign.
        """
        try:
            print("Generando urls zapsign")
            data = request.data
            if isinstance(data, dict):
                id_paq = data["id_contrato"]
                pagare_distinto = data.get("pagare_distinto", "No")
                cantidad_pagare = data.get("cantidad_pagare", "0")
            else:
                id_paq = data
                pagare_distinto = "No"
                cantidad_pagare = "0"

            
            nombre_archivo, pdf_bytes, total_paginas = self._generar_paquete_fraterna_pdf(id_paq, pagare_distinto, cantidad_pagare)
            base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
            print("Paquete EN BASE 64")

            contrato_data = {
                "id": id_paq, 
                "filename": nombre_archivo, 
                "base64_pfd": base64_pdf, 
                "residente": data["residente_contrato"],
                "total_paginas": total_paginas
                }
            #funcion de prueba solicitar documento a zapsign
            resultado = self.subir_documento_a_zapsign(contrato_data)
            return Response({
                "filename": "simula nombre",
                "pdf_base64": "base64_pdfj89d789a8su39889",
                "respuestaZS": resultado
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error en generar_urls_a_firmar_paquete_fraterna: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                        f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def generar_paquete_completo_fraterna(self, request, *args, **kwargs):
        """
        Devuelve el paquete combinado en formato PDF descargable para visualizar en el front.
        """
        try:
            print("Generando paquete completo Fraterna")
            data = request.data
            if isinstance(data, dict):
                id_paq = data["id"]
                pagare_distinto = data.get("pagare_distinto", "No")
                cantidad_pagare = data.get("cantidad_pagare", "0")
            else:
                id_paq = data
                pagare_distinto = "No"
                cantidad_pagare = "0"

            nombre_archivo, pdf_bytes, total_paginas = self._generar_paquete_fraterna_pdf(id_paq, pagare_distinto, cantidad_pagare)

            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
            response.write(pdf_bytes)

            print("Paquete completo generado exitosamente")
            return response

        except Exception as e:
            print(f"Error en generar_paquete_completo_fraterna: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                        f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def mostrar_urls_firma_documento_fraterna(self, request, *args, **kwargs):
        try:
            doc_token = request.data.get("token")
            if not doc_token or not isinstance(doc_token, str):
                return Response({'error': 'Token inválido o no proporcionado.'}, status=status.HTTP_400_BAD_REQUEST)

            print(f"Solicitando documento a Zapsign {API_URL_ZAPSIGN}docs/{doc_token}/")
            url = f'{API_URL_ZAPSIGN}docs/{doc_token}/'
            headers = {'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'}

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                return Response({
                    'error': 'Error al obtener información de ZapSign.',
                    'status_code': response.status_code,
                    'response': response.text
                }, status=response.status_code)

            try:
                response_data = response.json()
            except ValueError:
                return Response({
                    'error': 'La respuesta de ZapSign no es un JSON válido.',
                    'raw_response': response.text
                }, status=status.HTTP_502_BAD_GATEWAY)

            # Validar que existan campos clave
            required_keys = ['name', 'status', 'original_file', 'signed_file', 'signers']
            if not all(k in response_data for k in required_keys):
                return Response({
                    'error': 'Respuesta incompleta de ZapSign.',
                    'received_keys': list(response_data.keys())
                }, status=status.HTTP_502_BAD_GATEWAY)

            return Response(response_data, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException as e:
            logger.error(f"{dt.now()} Error de conexión con ZapSign: {e}")
            return Response({
                'error': 'Error de conexión con ZapSign.',
                'details': str(e)
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Error inesperado en {exc_tb.tb_frame.f_code.co_name} línea {exc_tb.tb_lineno}: {e}")
            return Response({
                'error': 'Error inesperado al procesar la solicitud.',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    

    def _generar_comodato_interno(self, info):
        """Función interna para generar el PDF del comodato"""
        try:
            # Obtener la duración para pasarla a letra
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            duracion_texto = num2words(duracion_meses, lang='es')
            
            # Obtener renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            # Obtener la tipología
            opciones = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png"
            }
            
            inventario = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.png"
            }
            
            tipologia = info.tipologia
            plano = opciones.get(tipologia, "")
            tabla_inventario = inventario.get(tipologia, "")
            
            # Obtener la URL del plano que sube fraterna
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
            
            context = {
                'info': info, 
                'duracion_meses': duracion_meses, 
                'duracion_texto': duracion_texto, 
                'renta_texto': renta_texto, 
                'plano': plano, 
                'plan_loc': plan_loc, 
                'tabla_inventario': tabla_inventario
            }
            
            template = 'home/comodato_fraterna.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando comodato interno: {e}")
            raise e
    
    def _generar_contrato_interno(self, info):
        """Función interna para generar el PDF del contrato"""
        try:
            # Obtener la cantidad de habitantes para pasarla a letra
            habitantes = int(info.habitantes)
            habitantes_texto = num2words(habitantes, lang='es')
            
            # Obtener renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            # Obtener la tipología
            opciones = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png"
            }
            
            inventario = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.png"
            }
            
            tipologia = info.tipologia
            plano = opciones.get(tipologia, "")
            tabla_inventario = inventario.get(tipologia, "")
            
            # Obtener la URL del plano que sube fraterna
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
            
            context = {
                'info': info, 
                'habitantes_texto': habitantes_texto, 
                'renta_texto': renta_texto, 
                'plano': plano, 
                'plan_loc': plan_loc, 
                'tabla_inventario': tabla_inventario
            }
            
            template = 'home/contrato_fraterna.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando contrato interno: {e}")
            raise e
    
    def _generar_poliza_interno(self, info):
        """Función interna para generar el PDF de la póliza"""
        try:
            # Generar el número de contrato
            arrendatario = info.residente.nombre_arrendatario
            primera_letra = arrendatario[0].upper()
            ultima_letra = arrendatario[-1].upper()
            
            year = info.fecha_celebracion.strftime("%g")
            month = info.fecha_celebracion.strftime("%m")
            
            nom_contrato = f"AFY{month}{year}CX51{info.id}CA{primera_letra}{ultima_letra}"
            
            # Obtener renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            context = {
                'info': info, 
                'renta_texto': renta_texto, 
                'nom_contrato': nom_contrato
            }
            
            template = 'home/poliza_fraterna.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando póliza interna: {e}")
            raise e
    
    def _generar_pagare_interno(self, info, pagare_distinto, cantidad_pagare):
        """Función interna para generar el PDF del pagaré"""
        try:
            # Procesar cantidad del pagaré
            if pagare_distinto == "Si":
                if "." not in str(cantidad_pagare):
                    cantidad_pagare_num = cantidad_pagare
                    cantidad_decimal = "00"
                    cantidad_letra = num2words(cantidad_pagare_num, lang='es')
                else:
                    cantidad_completa = str(cantidad_pagare).split(".")
                    cantidad_pagare_num = cantidad_completa[0]
                    cantidad_decimal = cantidad_completa[1]
                    cantidad_letra = num2words(cantidad_pagare_num, lang='es')
            else:
                cantidad_pagare_num = 0
                cantidad_decimal = "00"
                cantidad_letra = num2words(cantidad_pagare_num, lang='es')
            
            # Definir la fecha inicial
            fecha_inicial = info.fecha_move_in
            dia = fecha_inicial.day
            
            # Definir la duración en meses
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            
            # Calcular la fecha final
            fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
            
            # Lista para almacenar las fechas iteradas
            fechas_iteradas = []
            fecha_temp = fecha_inicial
            
            while fecha_temp < fecha_final:
                nombre_mes = fecha_temp.strftime("%B")
                fechas_iteradas.append((nombre_mes.capitalize(), fecha_temp.year))
                fecha_temp += relativedelta(months=1)
            
            # Obtener la renta para pasarla a letra
            if "." not in info.renta:
                number = int(info.renta)
                renta_decimal = "00"
                text_representation = num2words(number, lang='es').capitalize()
            else:
                renta_completa = info.renta.split(".")
                number = int(renta_completa[0])
                renta_decimal = renta_completa[1]
                text_representation = num2words(number, lang='es').capitalize()
            
            context = {
                'info': info, 
                'dia': dia,
                'lista_fechas': fechas_iteradas, 
                'text_representation': text_representation, 
                'duracion_meses': duracion_meses, 
                'pagare_distinto': pagare_distinto,
                'cantidad_pagare': cantidad_pagare_num, 
                'cantidad_letra': cantidad_letra, 
                'cantidad_decimal': cantidad_decimal, 
                'renta_decimal': renta_decimal
            }
            
            template = 'home/pagare_fraterna.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando pagaré interno: {e}")
            raise e
        
    def renovar_contrato_fraterna(self, request, *args, **kwargs):
        try:
            print("Renovar el contrato pa")
            print("Request",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("mi id es: ",instance.id)
            print(instance.__dict__)
            #Mandar Whats con lo datos del contrato a Miri
            remitente = 'notificaciones@arrendify.com'
            destinatario = 'desarrolloarrendify@gmail.com'

            print(instance.residente.nombre_residente)
            asunto = f"Renovacion de Contrato del arrendatario {instance.residente.nombre_arrendatario}"
            
           
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Subject'] = asunto
            print("paso objeto mime")

            pdf_html = renovacion_aviso_fraterna(instance)

            msg.attach(MIMEText(pdf_html, 'html'))
            print("pase el msg attach 1")
        
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                server.sendmail(remitente, destinatario, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            # proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            # print("proceso",proceso.__dict__)
            # proceso.status_proceso = request.data["status"]
            # proceso.save()
            
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)


class DocumentosArrendamientosFraterna(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendamientosFraternaModel.objects.all()
    serializer_class = FraternaArrendamientosSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendamiento Fraterna....📄")
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list documentos arrendamientos es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Documentos Arrendamiento Fraterna....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            print("FILES ===>", request.FILES)
            
            # Verificar si viene contrato_id directamente (desde Admin Fraterna)
            contrato_id = data.get('contrato_id', None)
            sin_recibo = data.get('sin_recibo', 'false').lower() == 'true'
            numero_pago_manual = data.get('numero_pago', None)
            
            print(f"Contrato ID: {contrato_id}, Sin Recibo: {sin_recibo}, Número Pago Manual: {numero_pago_manual}")
            
            if contrato_id:
                # Flujo para usuario Admin Fraterna con contrato específico
                print(f"Flujo Admin Fraterna - Buscando contrato ID: {contrato_id}")
                try:
                    contrato = FraternaContratos.objects.get(id=contrato_id)
                    arrendatario = contrato.residente
                    print(f"Contrato y residente encontrados: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm}")
                except FraternaContratos.DoesNotExist:
                    return Response({'error': f'Contrato ID {contrato_id} no encontrado'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Flujo original para usuarios normales
                # Usar first_name del usuario autenticado para buscar arrendatario
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                # Intentar diferentes estrategias de búsqueda
                arrendatario = None
                
                # Estrategia 1: Buscar por nombre completo
                arrendatario = Residentes.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario)
                ).first()
                
                # Estrategia 2: Si no encuentra, buscar por primer nombre
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    print(f"Buscando por primer nombre: {primer_nombre}")
                    arrendatario = Residentes.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(nombre_empresa_pm__icontains=primer_nombre)
                    ).first()
                
                # Estrategia 3: Si aún no encuentra, buscar por palabras individuales
                if not arrendatario:
                    palabras = nombre_usuario.split()
                    for palabra in palabras:
                        if len(palabra) > 2:  # Solo palabras de más de 2 caracteres
                            print(f"Buscando por palabra: {palabra}")
                            arrendatario = Residentes.objects.filter(
                                Q(nombre_arrendatario__icontains=palabra) |
                                Q(nombre_empresa_pm__icontains=palabra)
                            ).first()
                            if arrendatario:
                                break
                
                # Estrategia 4: Buscar por relación directa con el usuario
                if not arrendatario:
                    print("Buscando arrendatario asociado directamente al usuario")
                    arrendatario = Residentes.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                print(f"Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm} (ID: {arrendatario.id})")
                
                # Buscar contrato relacionado
                try:
                    contrato = FraternaContratos.objects.get(residente=arrendatario)
                    print(f"Contrato encontrado: {contrato.id}")
                except FraternaContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Buscar proceso relacionado
            try:
                proceso = ProcesoContrato.objects.get(contrato=contrato)
                print(f"Proceso encontrado: {proceso.id}")
            except ProcesoContrato.DoesNotExist:
                return Response({'error': f'Proceso no encontrado para el contrato ID: {contrato.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            duracion_meses = self.extraer_duracion_meses(contrato.duracion)
            print(f"Duración extraída: {duracion_meses} meses")

            # Determinar número de pago
            if numero_pago_manual:
                # Usar número de pago manual si viene
                numero_pago_actual = int(numero_pago_manual)
                print(f"Usando número de pago manual: {numero_pago_actual}")
                
                # VALIDACIÓN: Verificar que no exista ya un pago con este número
                pago_existente = self.get_queryset().filter(
                    contrato=contrato,
                    proceso=proceso,
                    numero_pago=numero_pago_actual
                ).first()
                
                if pago_existente:
                    return Response({
                        'error': f'Ya existe un pago registrado con el número {numero_pago_actual} para este contrato',
                        'detalles': {
                            'numero_pago': numero_pago_actual,
                            'contrato_id': contrato.id,
                            'proceso_id': proceso.id,
                            'fecha_registro': pago_existente.dateTimeOfUpload.strftime('%Y-%m-%d %H:%M:%S') if pago_existente.dateTimeOfUpload else 'N/A'
                        }
                    }, status=status.HTTP_400_BAD_REQUEST)
                
            else:
                # Contar pagos existentes para este contrato
                pagos_existentes = DocumentosArrendamientosFraternaModel.objects.filter(contrato=contrato).count()
                numero_pago_actual = pagos_existentes + 1
                print(f"Número de pago calculado automáticamente: {numero_pago_actual}")

            # Calcular renta total
            renta_total = Decimal(str(contrato.renta)) * duracion_meses if contrato.renta else Decimal('0')

            # Calcular interés por retraso (12% anual) - SOLO si no es un pago sin recibo
            interes_aplicado = Decimal('0')
            fecha_vencimiento = datetime.now().date() + timedelta(days=30)  # 30 días para pagar

            if not sin_recibo:  # Solo calcular intereses si hay recibo físico
                # Verificar si hay retraso en pagos anteriores
                if numero_pago_actual > 1:
                    ultimo_pago = DocumentosArrendamientosFraternaModel.objects.filter(
                        contrato=contrato
                    ).order_by('-dateTimeOfUpload').first()
                    
                    if ultimo_pago and ultimo_pago.fecha_vencimiento:
                        dias_retraso = (datetime.now().date() - ultimo_pago.fecha_vencimiento).days
                        if dias_retraso > 0:
                            # Aplicar 12% anual = 1% mensual
                            interes_mensual = Decimal('0.01')
                            meses_retraso = Decimal(str(dias_retraso)) / Decimal('30')
                            interes_aplicado = Decimal(str(contrato.renta)) * interes_mensual * meses_retraso
            
            # Obtener archivo - puede ser None si sin_recibo=true
            comp_pago_file = request.FILES.get('comp_pago', None)
            
            # Validar que si no es sin_recibo, debe venir archivo
            if not sin_recibo and not comp_pago_file:
                return Response({
                    'error': 'Se requiere archivo de recibo para registrar el pago'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Obtener referencia de pago del request
            referencia_pago = data.get('referencia_pago', '')
            print(f"📝 Referencia de pago recibida: '{referencia_pago}'")
            
            # Crear documento
            documento_data = {
                "user": user_session.id,
                "arrendatario": arrendatario.id,
                "contrato": contrato.id,
                "proceso": proceso.id,
                "comp_pago": comp_pago_file,  # Puede ser None si sin_recibo=true
                "referencia_pago": referencia_pago,  
                "numero_pago": numero_pago_actual,
                "total_pagos": duracion_meses,
                "renta_total": renta_total,
                "interes_aplicado": interes_aplicado,
                "fecha_vencimiento": fecha_vencimiento,
            }
            
            tipo_registro = "SIN RECIBO" if sin_recibo else "CON RECIBO"
            print(f"Pago {numero_pago_actual} de {duracion_meses} ({tipo_registro}) - Renta total: ${renta_total} - Interés: ${interes_aplicado}")
            
            arrendamientos_serializer = self.get_serializer(data=documento_data)
            arrendamientos_serializer.is_valid(raise_exception=True)
            arrendamientos_serializer.save()
            
            print("Documento ligado correctamente....✅")
            return Response(arrendamientos_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def extraer_duracion_meses(self, duracion_texto):
        """
        Extrae la duración en meses de un texto.
        Ejemplos: "6 meses" -> 6, "12 meses" -> 12, "24 meses" -> 24
        """
        if not duracion_texto:
            return 1
        
        # Convertir a string y buscar números
        texto = str(duracion_texto).lower().strip()
        
        # Buscar números en el texto
        numeros = re.findall(r'\d+', texto)
        
        if numeros:
            duracion = int(numeros[0])
            # Validar que sea un número razonable (entre 1 y 60 meses)
            if 1 <= duracion <= 60:
                return duracion
            else:
                print(f"Advertencia: Duración inusual detectada: {duracion} meses")
                return duracion
        
        # Si no encuentra números, intentar palabras
        palabras_meses = {
            'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6,
            'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10, 'once': 11, 'doce': 12,
            'dieciocho': 18, 'veinticuatro': 24, 'treinta': 30, 'treinta y seis': 36
        }
        
        for palabra, valor in palabras_meses.items():
            if palabra in texto:
                return valor
        
        print(f"No se pudo extraer duración de: '{duracion_texto}', usando 1 mes por defecto")
        return 1
        
    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            print("Eliminando Documentos Arrendamiento Garza Sada....🗑️")
            documentos_arrendamiento = self.get_object()
            documento_arrendamiento_serializer = self.serializer_class(documentos_arrendamiento)
            if documentos_arrendamiento:
                comp_pago = documento_arrendamiento_serializer.data['comp_pago']
                print("Eliminando Comprobante de Pago....", comp_pago)
                
                documentos_arrendamiento.delete()
                print("Documentos Arrendamiento Garza Sada eliminados correctamente....✅")
                return Response({'message': 'Archivo eliminado correctamente'}, status=204) 
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:  
            print(f"el error es en documentos arrendamiento destroy es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando Documentos Arrendatario Garza Sada....🔄")
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print("Datos Actuales ====>",request.data)
            
            # Verificar si se proporciona un nuevo archivo adjunto
            keys = request.data.keys()
    
            # Convertir las llaves a una lista y obtener la primera
            first_key = list(keys)[0]
            #first_key = str(first_key)
            print(first_key)
            
            # Acceder dinámicamente al atributo de instance usando first_key
            if hasattr(instance, first_key):
                archivo_anterior = getattr(instance, first_key)
                print("Archivo anterior ====>", archivo_anterior)
                eliminar_archivo_s3(archivo_anterior)
                print("Archivo eliminado de S3 desde Fraterna....✅")
            else:
                print(f"El atributo '{first_key}' no existe en la instancia.")
            
            serializer.update(instance, serializer.validated_data)
            print("Se actualizó correctamente el documento del residente Fraterna....✅")
            return Response(serializer.data)

        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], url_path='reporte_completo_fraterna')
    def reporte_completo(self, request):
        """Genera reporte PDF completo de arrendamientos Fraterna"""
        try:
            from django.http import HttpResponse
            from django.template.loader import render_to_string
            from weasyprint import HTML
            from collections import defaultdict
            
            print("Generando reporte completo Fraterna....📊")
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            arrendatario_id = request.query_params.get('arrendatario_id', None)
            queryset = DocumentosArrendamientosFraternaModel.objects.select_related('arrendatario', 'contrato', 'proceso')
            if es_admin:
                if arrendatario_id:
                    queryset = queryset.filter(arrendatario_id=arrendatario_id)
            else:
                nombre_usuario = request.user.first_name.strip()
                arrendatario = Residentes.objects.filter(Q(nombre_arrendatario__icontains=nombre_usuario) | Q(nombre_residente__icontains=nombre_usuario) | Q(user=request.user)).first()
                if not arrendatario:
                    return Response({'error': 'No se encontró información'}, status=status.HTTP_404_NOT_FOUND)
                queryset = queryset.filter(arrendatario=arrendatario)
            
            recibos = queryset.order_by('arrendatario__nombre_arrendatario', 'numero_pago')
            arrendatarios_data = defaultdict(lambda: {'arrendatario': {}, 'contrato': {}, 'recibos': [], 'estadisticas': {'total_pagos': 0, 'pagos_realizados': 0, 'pagos_pendientes': 0, 'renta_mensual': 0, 'renta_total': 0, 'total_pagado': 0, 'total_pendiente': 0, 'interes_total': 0, 'porcentaje_completado': 0}})
            
            for recibo in recibos:
                if not recibo.arrendatario:
                    continue
                arr_id = recibo.arrendatario.id
                
                if not arrendatarios_data[arr_id]['arrendatario']:
                    nombre = recibo.arrendatario.nombre_arrendatario or recibo.arrendatario.nombre_residente or 'Sin nombre'
                    email = recibo.arrendatario.correo_arrendatario or recibo.arrendatario.correo_residente or 'No especificado'
                    telefono = recibo.arrendatario.celular_arrendatario or recibo.arrendatario.celular_residente or 'No especificado'
                    tipo = 'Persona Física' if recibo.arrendatario.nombre_arrendatario else 'Residente'
                    arrendatarios_data[arr_id]['arrendatario'] = {'nombre': nombre, 'email': email, 'telefono': telefono, 'tipo': tipo}
                
                if recibo.contrato and not arrendatarios_data[arr_id]['contrato']:
                    contrato = recibo.contrato
                    arrendatarios_data[arr_id]['contrato'] = {'no_depa': contrato.no_depa or 'N/A', 'duracion': contrato.duracion or 'No especificada', 'fecha_celebracion': contrato.fecha_celebracion.strftime('%d/%m/%Y') if contrato.fecha_celebracion else 'N/A', 'fecha_vigencia': contrato.fecha_vigencia.strftime('%d/%m/%Y') if contrato.fecha_vigencia else 'N/A', 'renta': float(contrato.renta) if contrato.renta else 0}
                
                estado = 'Sin fecha'
                dias_retraso = 0
                if recibo.fecha_vencimiento:
                    hoy = date.today()
                    dias_restantes = (recibo.fecha_vencimiento - hoy).days
                    if dias_restantes < 0:
                        estado = 'Vencido'
                        dias_retraso = abs(dias_restantes)
                    elif dias_restantes <= 7:
                        estado = 'Próximo a vencer'
                    else:
                        estado = 'Al día'
                
                renta_mensual = float(recibo.contrato.renta) if recibo.contrato and recibo.contrato.renta else 0
                interes_aplicado = float(recibo.interes_aplicado) if recibo.interes_aplicado else 0
                monto_pagado = renta_mensual if recibo.comp_pago else 0
                monto_pendiente = renta_mensual - monto_pagado
                usuario_subio = recibo.user.first_name or recibo.user.username if recibo.user else 'Sin usuario'
                referencia_pago = recibo.referencia_pago if recibo.referencia_pago else f"FR-{recibo.id:06d}" if recibo.id else 'N/A'
                
                recibo_data = {'numero_pago': recibo.numero_pago or 0, 'fecha_subida': recibo.dateTimeOfUpload.strftime('%d/%m/%Y %H:%M') if recibo.dateTimeOfUpload else 'N/A', 'fecha_vencimiento': recibo.fecha_vencimiento.strftime('%d/%m/%Y') if recibo.fecha_vencimiento else 'N/A', 'interes': interes_aplicado, 'estado': estado}
                
                if es_admin:
                    recibo_data.update({'departamento': recibo.contrato.no_depa if recibo.contrato else 'N/A', 'referencia_pago': referencia_pago, 'monto': renta_mensual, 'monto_pagado': monto_pagado, 'monto_pendiente': monto_pendiente, 'dias_retraso': dias_retraso, 'penalizacion': interes_aplicado, 'usuario': usuario_subio})
                
                arrendatarios_data[arr_id]['recibos'].append(recibo_data)
                stats = arrendatarios_data[arr_id]['estadisticas']
                stats['total_pagos'] = recibo.total_pagos or 0
                stats['pagos_realizados'] = len(arrendatarios_data[arr_id]['recibos'])
                stats['pagos_pendientes'] = stats['total_pagos'] - stats['pagos_realizados']
                stats['renta_total'] = float(recibo.renta_total) if recibo.renta_total else 0
                stats['interes_total'] += interes_aplicado
                if recibo.contrato and recibo.contrato.renta:
                    stats['renta_mensual'] = float(recibo.contrato.renta)
                    stats['total_pagado'] = stats['renta_mensual'] * stats['pagos_realizados']
                    stats['total_pendiente'] = stats['renta_mensual'] * stats['pagos_pendientes']
                if stats['total_pagos'] > 0:
                    stats['porcentaje_completado'] = round((stats['pagos_realizados'] / stats['total_pagos']) * 100, 1)
            
            pagos_atrasados = sum(1 for arr in arrendatarios_data.values() for r in arr['recibos'] if r.get('estado') == 'Vencido')
            totales_generales = {'total_arrendatarios': len(arrendatarios_data), 'total_recibos': recibos.count(), 'ingresos_totales': sum(arr['estadisticas']['total_pagado'] for arr in arrendatarios_data.values()), 'pendientes_totales': sum(arr['estadisticas']['total_pendiente'] for arr in arrendatarios_data.values()), 'intereses_totales': sum(arr['estadisticas']['interes_total'] for arr in arrendatarios_data.values()), 'contratos_por_vencer': 0, 'pagos_atrasados': pagos_atrasados}
            context = {'arrendatarios': list(arrendatarios_data.values()), 'totales': totales_generales, 'fecha_generacion': datetime.now().strftime('%d/%m/%Y %H:%M'), 'usuario_generador': request.user.first_name or request.user.username}
            template_name = 'home/reporte_arrendamientos_fraterna_admin.html' if es_admin else 'home/reporte_arrendamientos_fraterna.html'
            html_string = render_to_string(template_name, context)
            html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
            pdf = html.write_pdf()
            response = HttpResponse(pdf, content_type='application/pdf')
            filename_suffix = '_admin' if es_admin else ''
            response['Content-Disposition'] = f'attachment; filename="reporte_fraterna{filename_suffix}_{date.today().strftime("%Y%m%d")}.pdf"'
            print("Reporte Fraterna generado exitosamente....✅")
            return response
        except Exception as e:
            print(f"Error al generar reporte Fraterna: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en reporte Fraterna: {e}")
            return Response({'error': f'Error al generar el reporte: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='lista_arrendatarios_fraterna')
    def lista_arrendatarios(self, request):
        """Lista de residentes Fraterna con contratos"""
        try:
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            if not es_admin:
                return Response({'error': 'Sin permisos'}, status=status.HTTP_403_FORBIDDEN)
            
            arrendatarios = Residentes.objects.filter(residente_contrato__isnull=False).distinct().values('id', 'nombre_arrendatario', 'nombre_residente')
            lista = [{'id': arr['id'], 'nombre': arr['nombre_arrendatario'] or arr['nombre_residente']} for arr in arrendatarios if arr['nombre_arrendatario'] or arr['nombre_residente']]
            print(f"Residentes Fraterna: {len(lista)}")
            return Response(lista, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error lista Fraterna: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class IncidenciasFraterna(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = IncidenciasFraternaModel.objects.all()
    serializer_class = IncidenciasFraternaSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendamiento Garza Sada....📄")
            queryset = self.filter_queryset(self.get_queryset())
            IncidenciasSerializers = self.get_serializer(queryset, many=True)
            return Response(IncidenciasSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list documentos arrendamientos es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Solicitud de Incidencia....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            
            # Verificar si es usuario autorizado para incidencias Arrendify
            usuarios_autorizados = ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            es_usuario_autorizado = (
                user_session.is_staff or 
                user_session.is_superuser or 
                user_session.username in usuarios_autorizados or
                getattr(user_session, 'pertenece_a', None) in usuarios_autorizados
            )
            
            arrendatario = None
            contrato = None
            
            if es_usuario_autorizado:
                print(f"Usuario autorizado para incidencias Arrendify: {user_session.username}")
                # Para usuarios autorizados, usar arrendatario/contrato del request si se proporcionan
                arrendatario_id = data.get('arrendatario', None)
                contrato_id = data.get('contrato', None)
                
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": arrendatario_id,
                    "contrato": contrato_id,
                    "incidencia": data.get('incidencia', ''),
                    "tipo_incidencia": data.get('tipo_incidencia', ''),
                    "prioridad": data.get('prioridad', 'Media'),
                    "status": "Pendiente de Revisión",
                }
                print(f"Creando incidencia Arrendify - User={user_session.id}, Arrendatario={arrendatario_id}, Contrato={contrato_id}")
            else:
                # Lógica original para usuarios regulares
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                # Intentar diferentes estrategias de búsqueda
                arrendatario = None
                
                # Estrategia 1: Buscar por nombre completo
                arrendatario = Residentes.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario)
                ).first()
                
                # Estrategia 2: Si no encuentra, buscar por primer nombre
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    print(f"Buscando por primer nombre: {primer_nombre}")
                    arrendatario = Residentes.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(nombre_empresa_pm__icontains=primer_nombre)
                    ).first()
                
                # Estrategia 3: Si aún no encuentra, buscar por palabras individuales
                if not arrendatario:
                    palabras = nombre_usuario.split()
                    for palabra in palabras:
                        if len(palabra) > 2:  # Solo palabras de más de 2 caracteres
                            print(f"Buscando por palabra: {palabra}")
                            arrendatario = Residentes.objects.filter(
                                Q(nombre_arrendatario__icontains=palabra) |
                                Q(nombre_empresa_pm__icontains=palabra)
                            ).first()
                            if arrendatario:
                                break
                
                # Estrategia 4: Buscar por relación directa con el usuario
                if not arrendatario:
                    print("Buscando arrendatario asociado directamente al usuario")
                    arrendatario = Residentes.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                print(f"Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm} (ID: {arrendatario.id})")
                
                # Buscar contrato relacionado
                try:
                    contrato = FraternaContratos.objects.get(arrendatario=arrendatario)
                    print(f"Contrato encontrado: {contrato.id}")
                except FraternaContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Crear Incidencia para usuario regular
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": arrendatario.id,
                    "contrato": contrato.id,
                    "incidencia": data.get('incidencia', ''),
                    "status": "Pendiente de Revisión",
                }
                print(f"Creando incidencia regular con: User={user_session.id}, Arrendatario={arrendatario.id}, Contrato={contrato.id}")
            
            arrendamientos_serializer = self.get_serializer(data=incidencia_data)
            arrendamientos_serializer.is_valid(raise_exception=True)
            arrendamientos_serializer.save()
            
            print("Incidencia creada exitosamente....✅")
            return Response(arrendamientos_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST) 


########################## F R A T E R N A ######################################        

########################## S E M I L L E R O  P U R I S I M A ######################################
class Arrendatarios_semilleroViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Arrendatarios_semillero.objects.all()
    serializer_class = Arrentarios_semilleroSerializers
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
                print("Esta entrando a listar Residentes")
                arrendatarios =  self.get_queryset().order_by('-id')
                serializer = self.get_serializer(arrendatarios, many=True)
                return Response(serializer.data, status= status.HTTP_200_OK)
            
           elif user_session.rol == "Inmobiliaria":
                #tengo que busca a los inquilinos que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de Residentes propios y registrados por mis agentes
                inquilinos_a_cargo = self.get_queryset().filter(user_id__in = agentes)
                inquilinos_mios = self.get_queryset().filter(user_id = user_session)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
                mios = mios.order_by('-id')
               
                serializer = self.get_serializer(mios, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                
                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['inmobiliaria'] = True
                    
                return Response(serialized_data)      
            
           elif user_session.rol == "Agente":  
                print("soy Agente", user_session.first_name)
                #obtengo mis inquilinos
                residentes_ag = self.get_queryset().filter(user_id = user_session).order_by('-id')
              
                #tengo que obtener a mis inquilinos vinculados
              
                serializer = self.get_serializer(residentes_ag, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)
         
           return Response(serializer.data, status= status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print("Llegando a create de arrendatarios semillero")
            print(request.data)
            arrendatarios_semillero_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            print(arrendatarios_semillero_serializer)
            if arrendatarios_semillero_serializer.is_valid(raise_exception=True):
                arrendatarios_semillero_serializer.save(user = user_session)
                print("Guardado arrendatarios_semillero")
                return Response({'arrendatarios_semilleros': arrendatarios_semillero_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion")
                return Response({'errors': arrendatarios_semillero_serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def update(self, request, *args, **kwargs):
        try:
            print("Esta entrando a actualizar Residentes")
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print(request.data)
            instance = self.get_object()
            print("instance",instance)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            print(serializer)
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("edito residente")
                # return redirect('myapp:my-url')
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            user_session = request.user
            print("Entrando a retrieve")
            modelos = Residentes.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            Residentes = modelos.filter(slug=slug)
            if Residentes:
                serializer_Residentes = ResidenteSerializers(Residentes, many=True)
                return Response(serializer_Residentes.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            print("LLegando a eliminar residente")
            Residentes = self.get_object()
            if Residentes:
                Residentes.delete()
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
  
    def mandar_aprobado(self, request, *args, **kwargs):  
        try:
            print("Aprobar al residente")
            info = request.data
            print("el id que llega", info )
            print("accediendo a informacion", info["estado_civil"])
            today = date.today().strftime('%d/%m/%Y')
            ingreso = int(info["ingreso"])
            ingreso_texto = num2words(ingreso, lang='es').capitalize()
            context = {'info': info, "fecha_consulta":today, 'ingreso':ingreso, 'ingreso_texto':ingreso_texto}
        
            # Renderiza el template HTML  
            template = 'home/aprobado_fraterna.html'
    
            html_string = render_to_string(template, context)# lo comvertimos a string
            pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
            print("pdf realizado")
            
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
            print("antes de enviar_archivo",context)
            self.enviar_archivo(archivo, info)
            print("PDF ENVIADO")
            return Response({'Mensaje': 'Todo Bien'},status= status.HTTP_200_OK)
        
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
                  
    def enviar_archivo(self, archivo, info, comentario="nada"):
        print("")
        print("entrando a enviar archivo")
        print("soy pdf content",archivo)
        print("soy comentario",comentario)
        arrendatario = info["nombre_arrendatario"]
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            # destinatario = 'jsepulvedaarrendify@gmail.com'
            destinatario = 'jcasados@fraterna.mx'
            # destinatario2 = 'juridico.arrendify1@gmail.com'
            destinatario2 = 'smosqueda@fraterna.mx'
            
            
            asunto = f"Resultado Investigación Arrendatario {arrendatario}"
            
            destinatarios = [destinatario,destinatario2]
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Cc'] = destinatario2
            msg['Subject'] = asunto
            print("paso objeto mime")
           
            # Estilo del mensaje
            #variable resultado_html_fraterna
            pdf_html = aprobado_fraterna(info)
          
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("pase el msg attach 1")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Resultado_investigación.pdf')
            msg.attach(pdf_part)
            print("pase el msg attach 2")
            
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
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})
        
class DocumentosArrendatario_semillero(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendatarios_semilleros.objects.all()
    serializer_class = DASSerializer
   
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def create (self, request, *args,**kwargs):
        try: 
            user_session = str(request.user.id)
            data = request.data
            data = {
                    "Ine_arrendatario": request.FILES.get('Ine_arrendatario', None),
                    "Ine_obligado": request.FILES.get('Ine_obligado', None),
                    "Comp_dom_arrendatario": request.FILES.get('Comp_dom_arrendatario', None),
                    "Comp_dom_obligado": request.FILES.get('Comp_dom_obligado', None),
                    "Rfc_arrendatario": request.FILES.get('Rfc_arrendatario', None),
                    "Ingresos_arrendatario": request.FILES.get('Ingresos_arrendatario', None),
                    "Ingresos2_arrendatario": request.FILES.get('Ingresos2_arrendatario', None),
                    "Ingresos3_arrendatario": request.FILES.get('Ingresos3_arrendatario', None),
                    "Ingresos_obligado": request.FILES.get('Ingresos_obligado', None),
                    "Ingresos2_obligado": request.FILES.get('Ingresos_obligado2', None),
                    "Ingresos3_obligado": request.FILES.get('Ingresos_obligado3', None),
                    "Extras": request.FILES.get('Extras', None),
                    "Recomendacion_laboral": request.FILES.get('Recomendacion_laboral', None),
                    "arrendatario":request.data['arrendatario'],
                    "user":user_session
                }
          
            if data:
                documentos_serializer = self.get_serializer(data=data)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save()
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            documentos_inquilinos = self.get_object()
            documento_inquilino_serializer = self.serializer_class(documentos_inquilinos)
            print("Soy ine", documento_inquilino_serializer.data['ine'])
            print("1")
            if documentos_inquilinos:
                ine = documento_inquilino_serializer.data['ine']
                print("Soy ine 2", ine)
                comp_dom= documento_inquilino_serializer.data['comp_dom']
                rfc= documento_inquilino_serializer.data['escrituras_titulo']
                print("Soy RFC", rfc)
                ruta_ine = 'apps/static'+ ine
                print("Ruta ine", ruta_ine)
                ruta_comprobante_domicilio = 'apps/static'+ comp_dom
                ruta_rfc = 'apps/static'+ rfc
                print("Ruta com", ruta_comprobante_domicilio)
                print("Ruta RFC", ruta_rfc)
            
                # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
                documentos_inquilinos.delete()
                return Response({'message': 'Archivo eliminado correctamente'}, status=204)
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
        
    def retrieve(self, request, pk=None):
        try:
            documentos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            inquilino = documentos.filter(id=pk)
            serializer_inquilino = DISerializer(inquilino, many=True)
            print(serializer_inquilino.data)
            ine = serializer_inquilino.data[0]['ine']
            print(ine)
            # documentos_arrendador = self.get_object()
            # print(documentos_arrendador)
            return Response(serializer_inquilino.data)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
   
    def update(self, request, *args, **kwargs):
        try:
            print("Entre en el update")
            instance = self.get_object()
            print("paso instance")
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print(request.data)
            
            # Verificar si se proporciona un nuevo archivo adjunto
            keys = request.data.keys()
    
            # Convertir las llaves a una lista y obtener la primera
            first_key = list(keys)[0]
            #first_key = str(first_key)
            print(first_key)
            
            # Acceder dinámicamente al atributo de instance usando first_key
            if hasattr(instance, first_key):
                archivo_anterior = getattr(instance, first_key)
                print("arc", archivo_anterior)
                eliminar_archivo_s3(archivo_anterior)
            else:
                print(f"El atributo '{first_key}' no existe en la instancia.")
            
            print("archivo",archivo_anterior)
            serializer.update(instance, serializer.validated_data)
            print("finalizado")
            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
#////////////////////////CONTRATOS SEMILLERO///////////////////////////////
class Contratos_semillero(viewsets.ModelViewSet):
    # authentication_classes = [TokenAuthentication, SessionAuthentication]
    # permission_classes = [IsAuthenticated]
    queryset = SemilleroContratos.objects.all()
    serializer_class = ContratoSemilleroSerializer
    
    def list(self, request, *args, **kwargs):
        try:
           user_session = request.user       
           if user_session.is_staff:
               print("Esta entrando a listar cotizacion")
               contratos =  SemilleroContratos.objects.all().order_by('-id')
               serializer = self.get_serializer(contratos, many=True)
               serialized_data = serializer.data
                
               # Agregar el campo 'is_staff'
               for item in serialized_data:
                 item['is_staff'] = True
                
               return Response(serialized_data)
           
           elif user_session.rol == "Inmobiliaria":
               #primero obtenemos mis agentes.
               print("soy inmobiliaria en listar contratos", user_session.name_inmobiliaria)
               agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
               #obtenemos los contratos
               contratos_mios = SemilleroContratos.objects.filter(user_id = user_session.id)
               contratos_agentes = SemilleroContratos.objects.filter(user_id__in = agentes.values("id"))
               contratos_all = contratos_mios.union(contratos_agentes)
               contratos_all = contratos_all.order_by('-id')
               
               print("es posible hacer esto:", contratos_all)
               
               serializer = self.get_serializer(contratos_all, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
               
           elif user_session.rol == "Agente":
               print(f"soy Agente: {user_session.first_name} en listar contrato")
               residentes_ag = SemilleroContratos.objects.filter(user_id = user_session).order_by('-id')
              
               serializer = self.get_serializer(residentes_ag, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print(user_session)
            print("RD",request.data)
            print("Request",request)
            print("Llegando a create de contrato para fraterna")
            
            fecha_actual = date.today()
            contrato_serializer = self.serializer_class(data = request.data) #Usa el serializer_class
            if contrato_serializer.is_valid():
                nuevo_proceso = ProcesoContrato_semillero.objects.create(usuario = user_session, fecha = fecha_actual, status_proceso = "En Revisión")
                if nuevo_proceso:
                    print("ya la armamos")
                    print(nuevo_proceso.id)
                    info = contrato_serializer.save(user = user_session)
                    nuevo_proceso.contrato = info
                    nuevo_proceso.save()
                    #send_noti_varios(FraternaContratos, request, title="Nueva solicitud de contrato en Fraterna", text=f"A nombre del Arrendatario {info.residente.nombre_arrendatario}", url = f"fraterna/contrato/#{info.residente.id}_{info.cama}_{info.no_depa}")
                    print("despues de metodo send_noti")
                    print("Se Guardado solicitud")
                    return Response({'Semillero': contrato_serializer.data}, status=status.HTTP_201_CREATED)
                else:
                    print("no se creo el proceso")
                    return Response({'msj':'no se creo el proceso'}, status=status.HTTP_204_NO_CONTENT) 
            
            else:
                print("serializer no valido")
                return Response({'msj':'no es valido el serializer'}, status=status.HTTP_204_NO_CONTENT)     
            
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try:
            #primero verificamos que tenga contadores activos
            print("Esta entrando a actualizar Contratos Semillero")
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
           
                        
            proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            print("el contador es: ",proceso.contador)
            if (proceso.contador > 0 ):
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                if serializer.is_valid(raise_exception=True):
                    self.perform_update(serializer)
                    #proceso.contador = proceso.contador - 1
                    #proceso.save()
                    print("edito proceso contrato")
                    #send_noti_varios(SemilleroContratos, request, title="Se a modificado el contrato de:", text=f"FRATERNA VS {instance.residente.nombre_arrendatario} - {instance.residente.nombre_residente}".upper(), url = f"fraterna/contrato/#{instance.residente.id}_{instance.cama}_{instance.no_depa}")
                    return Response(serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response({'errors': serializer.errors})
            else:
                return Response({'msj': 'LLegaste al limite de tus modificaciones en el proceso'}, status=status.HTTP_205_RESET_CONTENT)
      
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy(self,request, *args, **kwargs):
        try:
            residente = self.get_object()
            if residente:
                residente.delete()
                return Response({'message': 'residente eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def aprobar_contrato_semillero(self, request, *args, **kwargs):
        try:
            print("update status contrato")
            print("Request",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("mi id es: ",instance.id)
            print(instance.__dict__)
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def desaprobar_contrato_semillero(self, request, *args, **kwargs):
        try:
            print("desaprobar Contrato")
            instance = self.queryset.get(id = request.data["id"])
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = "En Revisión"
            # proceso.contador = 2 # en vista que me indiquen lo contrario lo dejamos asi
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a desaprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_pagare_semillero(self, request, *args, **kwargs):
        try:
            #activamos la libreri de locale para obtener el mes en español
            print("Generar Pagare Semillero")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            print("rd",request.data)
            id_paq = request.data["id"]
            pagare_distinto = request.data["pagare_distinto"]

            if pagare_distinto == "Si":
                if "." not in request.data["cantidad_pagare"]:
                    print("no hay yaya pagare")
                    cantidad_pagare = request.data["cantidad_pagare"]
                    cantidad_decimal = "00"
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
                
                else:
                    cantidad_completa = request.data["cantidad_pagare"].split(".")
                    cantidad_pagare = cantidad_completa[0]
                    cantidad_decimal = cantidad_completa[1]
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
            else:
                cantidad_pagare = 0
                cantidad_decimal = "00"
                cantidad_letra = num2words(cantidad_pagare, lang='es')
            print(pagare_distinto)
            print(cantidad_pagare)
            
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)
            # Definir la fecha inicial
            fecha_inicial = info.fecha_celebracion
            print(fecha_inicial)
            #fecha_inicial = datetime(2024, 3, 20)
            #checar si cambiar el primer dia o algo asi
            # fecha inicial move in
            dia = fecha_inicial.day
            
            # Definir la duración en meses
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            print("duracion en meses",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_inicial < fecha_final:
                nombre_mes = fecha_inicial.strftime("%B")  # %B da el nombre completo del mes
                print("fecha",fecha_inicial.year)
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_inicial.year))      
                fecha_inicial += relativedelta(months=1)
            
            print("fechas_iteradas",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            for month, year in fechas_iteradas:
                print(f"Año: {year}, Mes: {month}")
            
            #obtenermos la renta para pasarla a letra
            if "." not in info.renta:
                print("no hay yaya")
                number = int(info.renta)
                renta_decimal = "00"
                text_representation = num2words(number, lang='es').capitalize()
               
            else:
                print("tengo punto en renta")
                renta_completa = info.renta.split(".")
                info.renta = renta_completa[0]
                renta_decimal = renta_completa[1]
                text_representation = num2words(renta_completa[0], lang='es').capitalize()
           
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'pagare_distinto':pagare_distinto , 'cantidad_pagare':cantidad_pagare, 'cantidad_letra':cantidad_letra,'cantidad_decimal':cantidad_decimal, 'renta_decimal':renta_decimal}
            print("pasamos el context")
            
            template = 'home/pagare_semillero.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("generamos correctamente")
            return HttpResponse(response, content_type='application/pdf')
    
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_poliza_semillero(self, request, *args, **kwargs):
        try:
            print("Generar Poliza Semillero")
            print("Data ====>", request.data)
            id_paq = request.data["id"]
            testigo1 = request.data["testigo1"]
            testigo2 = request.data["testigo2"]
            print(testigo1)
            print(testigo2)
            print("el id que llega", id_paq)
            info = self.queryset.filter(id=id_paq).first()
            print(info.__dict__)

            print("vamos a generar el codigo")
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            if info.id < 9:
                info.id = f"0{info.id}"
                print("")
            print("fec", fec)

            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" + f"{info.id}" + "CA" + na
            print("paqueton", nom_paquete.upper())

            # ✅ Conversión correcta de renta
            renta = float(info.renta)
            print("la renta es:", renta)
            parte_entera = int(renta)
            centavos = round((renta - parte_entera) * 100)

            renta_texto = f"{num2words(parte_entera, lang='es')} pesos"
            if centavos > 0:
                renta_texto += f" con {num2words(centavos, lang='es')} centavos"
            renta_texto = renta_texto.capitalize()

            # ✅ Cálculo de la póliza
            if renta > 14999:
                resultado = renta * 0.17
                valor_poliza = int(round(resultado))  # Redondear y convertir a int si se quiere solo entero
                print("resultado esperado", valor_poliza)
            else:
                valor_poliza = 2500

            poliza_texto = num2words(valor_poliza, lang='es').capitalize()

            context = {
                'info': info,
                'renta_texto': renta_texto,
                'nom_paquete': nom_paquete,
                'valor_poliza': valor_poliza,
                'poliza_texto': poliza_texto,
                "testigo1": testigo1,
                "testigo2": testigo2
            }

            template = 'home/poliza_semillero.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO POLIZA")
            return HttpResponse(response, content_type='application/pdf')

        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def generar_contrato_semillero(self, request, *args, **kwargs):
        try:
            print("Generar contrato Semillero")
            print("Data Entrante ====>", request.data)
            id_paq = request.data["id"]
            testigo1 = request.data["testigo1"]
            testigo2 = request.data["testigo2"]
            print("Testigo 1 ====>",testigo1)
            print("Testigo 2 ====>",testigo2)
            print("ID ====>", id_paq)
            info = self.queryset.filter(id=id_paq).first()
            print("Diccionario ====>",info.__dict__)
            
            # 🧠 Convertir renta con centavos a texto
            renta = float(info.renta)
            parte_entera = int(renta)
            centavos = round((renta - parte_entera) * 100)
            renta_texto = f"{num2words(parte_entera, lang='es')} pesos"
            if centavos > 0:
                renta_texto += f" con {num2words(centavos, lang='es')} centavos"
            renta_texto = renta_texto.capitalize()
            
            # Obtener los datos de la vigencia
            vigencia = info.duracion.split(" ")
            num_vigencia = vigencia[0]
            print(num_vigencia)

            print("Generando Codigo de paquete...")
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            if info.id < 9:
                info.id = f"0{info.id}"
            print("Fecha Celebracion ====>", fec)

            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            print("Dia ====>", dia)
            print("Mes ====>", mes)
            print("Año ====>", anio)
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" + f"{info.id}" + "CA" + na
            print("Numero Paquete ====>", nom_paquete.upper())

            context = {
                'info': info,
                'renta_texto': renta_texto,
                'num_vigencia': num_vigencia,
                'nom_paquete': nom_paquete,
                "testigo1": testigo1,
                "testigo2": testigo2
            }
            # Para depurar el contexto
            print("Context ===> ",context)

            template = 'home/contrato_arr_frat.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("Generado con Exito")

            return HttpResponse(response, content_type='application/pdf')

        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST) 
        
    def renovar_contrato_semillero(self, request, *args, **kwargs):
        try:
            print("Renovacion de contrato Semillero")
            print("Data ====>",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("ID ====>",instance.id)
            print(instance.__dict__)
            #Mandar Whats con lo datos del contrato a Miri
            
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            print("Proceso ====>",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)


class InvestigacionSemillero(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Arrendatarios_semillero.objects.all()
    serializer_class = Arrentarios_semilleroSerializers
   
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        if user_session.username == "Arrendatario1" or user_session.username == "Legal" or  user_session.username == "Investigacion" or user_session.username == "AndresMtzO" or user_session.username == "MIRIAM" or user_session.username == "jon_admin" or user_session.username == "SUArrendify" or user_session.username == "Becarios":
            print("USUARIO STAFF")
            qs = request.GET.get('nombre')     
            try:
                if qs:
                    inquilino = Arrendatarios_semillero.objects.all().order_by('-id')
                    serializer = Arrentarios_semilleroSerializers(inquilino, many=True)                    
                    return Response(serializer.data)
                    
                else:
                        print("Listar Investigacion Semillero")
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
                    inquilino = Arrendatarios_semillero.objects.all().filter(nombre__icontains = qs)
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
                        inquilino = Arrendatarios_semillero.objects.all().filter(user_id = francis.id)
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
        print("Enviar Investigacion Semillero")
        print("PDF ====>",archivo)
        print("Estatus Investigacion ====>",estatus)
        print("DATA ====>",info.__dict__)
        print("ID USUARIO ====>",info.user_id)
   
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
            print("Destinatario ====> ",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
            #Destino=['desarrolloarrendify@gmail.com']
            #Destino=['juridico.arrendify1@gmail.com']
            asunto = f"Resultado Investigación Prospecto {info.nombre_arrendatario}"
            
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
            print("Creacion de Mail ====>")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("Mail Creado ====>")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("TLS ====>")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("LOGIN ====>")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("CORREO ENVIADO ====>")
            return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
    def enviar_archivo_semillero(self, archivo, info, estatus):
        #cuan(do francis este registrado regresar todo como estaba
        print("Enviar Archivo Investigacion Semillero ====>")
        print("PDF ====>",archivo)
        print("Estatus Investigacion ====>",estatus)
        print("INFO Investigacion ====>",info.__dict__)
        print("ID USUARIO ====>",info.user_id)
   
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            destinatario = info.correo_arrendatario
            pdf_html = contenido_pdf_aprobado_semillero(info,estatus)
            print("Destinatario ====>",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
            #Destino=['desarrolloarrendify@gmail.com']
            #Destino=['juridico.arrendify1@gmail.com']
            asunto = f"Resultado Investigación Prospecto {info.nombre_arrendatario}"
            
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
            print("Creacion de Mail ====>")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("Mail Creado ====>")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("TLS ====>")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("LOGIN ====>")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("CORREO ENVIADO ====>")
            return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
        
    def aprobar_residente_semillero(self, request, *args, **kwargs):
        try:
            print("Aprobar Prospecto semillero")
            #Consulata para obtener el inquilino y establecemos fecha de hoy
            today = date.today().strftime('%d/%m/%Y')
            req_dat = request.data
            info = Arrendatarios_semillero.objects.filter(id = req_dat["id"]).first()
            print("DATA ====>",info.__dict__)   
                 
                 
            redes_negativo = req_dat.get("redes_negativo")
            print("DATA ====>",req_dat)
            print("ID DATA ====>", req_dat["id"])
            print("")
            print("Arrendatario ====>",info.nombre_arrendatario)       
            print("Diccionario ====>",info.__dict__)
            print("")                                                                 
            print("")
            print("Redes Negativas ====>", redes_negativo)            
            print("")
            
            requisitos = ['referencia1', 'referencia2', 'referencia3'] # una lista para verificar las referencias 1,2 y 3
            presentes = [req for req in requisitos if req in request.data and request.data[req]]
            print("Referencias presentes ====>",presentes)
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
                        print("Clave ====>", clave)
                        print("Frase ====>", frase)
                        print("Comentarios Redes ====>", redes_comentarios)
                    elif valor == "Si" and clave not in conductas:
                        print(f"No hay una frase definida para la clave: {clave}")
            else:
                redes_comentarios = "no tengo datos"
                print("Comentarios Redes ====>",redes_comentarios)
        
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
            print("ANTECEDENTES ====>",antecedentes)
            if antecedentes:
                # del antecedentes["civil_mercantil_demandado"] 
                print("CIVIL O FAMILIAR ====>",antecedentes)
                if antecedentes.get("civil_mercantil_demandado") and len(antecedentes) == 1: #tiene antecedentes de civil o de familiar? los excentamos si no delincuente
                    print("Historial Crediticio ====>")
                    #evaluar el historial crediticio  
                    
                    if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                        print("Rechazado ====>")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                    
                    elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                        print("Aprobado ====>")
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                        status = "Aprobado"
                        motivo = "No hay motivo de rechazo"
                    
                    elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                        print("A Considerar ====>")
                        conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                        status = "Aprobado_pe"
                        motivo = "1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                        
                elif antecedentes.get("antecedentes_aval_si") and len(antecedentes) == 1: #tiene antecedentes de aval
                        print("AVAL CON ANTECEDENTES")
                        print("Solicitar cambio Aval")
                        
                        if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                            print("Rechazado ====>")
                            conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                            status = "Declinado"
                            motivo = f"1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                            print("Aprobado ====>")
                            conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                            status = "Aprobado"
                            motivo =  f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                            print("A Considerar ====>")
                            conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                            status = "Aprobado_pe"
                            motivo = f"1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse.\n3.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                    
                elif antecedentes and tipo_score_pp == "Malo" or antecedentes and tipo_score_ingreso == "Malo":
                        print("Rechazado ====>")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."    
                        
                else:
                    print("Antecedentes")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."
            else: #No tiene Antecedentes
                
                #evaluar el historial crediticio  
                if tipo_score_pp == "Malo":
                    print("Rechazado ====>")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Buro: Se cuenta con un buro con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                
                elif tipo_score_ingreso == "Malo":
                    print("Rechazado ====>")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Ingresos: Los ingresos comprobados no son suficientes para garantizar el cumplimiento de sus obligaciones financieras."
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                    print("Aprobado ====>")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = ""   
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente" and antecedentes.get("antecedentes_aval_si") and antecedentes != None :
                    print("Aprobado ====>")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos." 
                
                elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                    print("A Considerar ====>")
                    conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                    status = "Aprobado_pe"
                    motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                
                 
                    
            context = {'info': info, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                       "redes_comentarios":redes_comentarios, 'referencias':referencias, 'antecedentes':antecedentes,'status':status, 'conclusion':conclusion, 'motivo':motivo}
            
            template = 'home/report_semillero.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            print("Generando PDF")
            pdf_file = HTML(string=html_string).write_pdf()

            # #aqui hacia abajo es para enviar por email
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
        
            print("DATOS ARCHIVO ====>",context)
            correo = self.enviar_archivo_semillero(archivo, context["info"], context["status"])
            print("CORREO ====>",correo)
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
        

########################## S E M I L L E R O  P U R I S I M A ######################################
        
########################## G A R Z A  S A D A ######################################
class Arrendatarios_GarzaSadaViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Arrendatarios_garzasada.objects.all()
    serializer_class = Arrentarios_GarzaSadaSerializers
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
            if user_session.is_staff or user_session.username == "GarzaSada": #Muestra todos los arrendatarios
                print("Listar Residentes Garza Sada")
                arrendatarios =  self.get_queryset().order_by('-id')
                serializer = self.get_serializer(arrendatarios, many=True)
                return Response(serializer.data, status= status.HTTP_200_OK)
            
            # elif user_session.rol == "Inmobiliaria": #Muestra los arrendatarios de la inmobiliaria y los que hayan registrado los agentes
            #     print("Soy Inmobiliaria ====>", user_session.name_inmobiliaria)
            #     agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
            #     inquilinos_agentes = self.get_queryset().filter(user_id__in = agentes)#Buscamos inquilinos con base en los agentes que pertenecen a la inmobiliaria
            #     inquilinos_inmobiliaria = self.get_queryset().filter(user_id = user_session)
            #     all_inquilinos = inquilinos_agentes.union(inquilinos_inmobiliaria)#Une ambas consultas de agentes y la inmobiliaria
            #     all_inquilinos = all_inquilinos.order_by('-id') #ordena por id descendente
               
            #     serializer = self.get_serializer(all_inquilinos, many=True)
            #     serialized_data = serializer.data
                
            #     if not serialized_data:
            #         print("No hay datos disponibles")
            #         return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                
            #     # Agregar el campo 'is_staff'
            #     for item in serialized_data:
            #         item['inmobiliaria'] = True
                    
            #     return Response(serialized_data)      
            
            elif user_session.rol == "Agente":  
                print("Soy Agente ====>", user_session.first_name)
                residentes_agente = self.get_queryset().filter(user_id = user_session).order_by('-id')#Buscamos inquilinos del agente y los ordenamos por id descendente
              
                serializer = self.get_serializer(residentes_agente, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("No hay datos disponibles")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)
            
            elif user_session.rol == "Residente":
                print("Soy Residente ====>", user_session.first_name)
                nombre_busqueda = (user_session.first_name).strip()

                # Si no hay nombre para filtrar, retorna lista vacía por seguridad
                if not nombre_busqueda:
                    return Response([], status=status.HTTP_200_OK)

                residente = (
                    Arrendatarios_garzasada.objects
                    .filter(
                        Q(nombre_arrendatario__icontains=nombre_busqueda) |
                        Q(nombre_empresa_pm__icontains=nombre_busqueda)
                    )
                    .order_by('-id')
                )
                
                for arrendatario in residente:
                    arrendatario_dict = model_to_dict(arrendatario)
                    print(f"ARRENDATARIO COMPLETO ====> {arrendatario_dict}")
                
                print("Residente encontrado ====>", residente)

                serializer = self.get_serializer(residente, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)           
        
        except Exception as e:
            print(f"el error desde list arrendatarios garza sada es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print("Creando arrendatario Garza Sada....")
            print("Arrendatario ====>",request.data)
            arrendatarios_garzasada_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            print(arrendatarios_garzasada_serializer)
            if arrendatarios_garzasada_serializer.is_valid(raise_exception=True):
                arrendatarios_garzasada_serializer.save(user = user_session)
                print("Guardo arrendatario Garza Sada....✅")
                return Response({'arrendatarios_semilleros': arrendatarios_garzasada_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion...❌")
                return Response({'errors': arrendatarios_garzasada_serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando arrendatario Garza Sada....🔄")
            partial = kwargs.pop('partial', False)
            print("partials====>",partial)
            print(request.data)
            instance = self.get_object()
            print("instance ====>",instance)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            print(serializer)
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("Residente actualizado correctamente....✅")
                # return redirect('myapp:my-url')
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            user_session = request.user
            print("Entrando a retrieve")
            modelos = Residentes.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            Residentes = modelos.filter(slug=slug)
            if Residentes:
                serializer_Residentes = Arrentarios_GarzaSadaSerializers(Residentes, many=True)
                return Response(serializer_Residentes.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            print("Eliminando arrendatario Garza Sada....🗑 ️")
            Residentes = self.get_object()
            if Residentes:
                Residentes.delete()
                print("Residente eliminado correctamente....✅")
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
  
    def mandar_aprobado(self, request, *args, **kwargs):  
        try:
            print("Aprobar al residente Garza Sada....")
            info = request.data
            print("Residente a Aprobar ====>", info )
            today = date.today().strftime('%d/%m/%Y')
            ingreso = int(info["ingreso"])
            ingreso_texto = num2words(ingreso, lang='es').capitalize()
            context = {'info': info, "fecha_consulta":today, 'ingreso':ingreso, 'ingreso_texto':ingreso_texto}
        
            # Renderiza el template HTML  
            template = 'home/aprobado_fraterna.html'
    
            html_string = render_to_string(template, context)# lo comvertimos a string
            pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
            print("PDF creado correctamente....✅")
            
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
            print("Contenido PDF....",context)
            self.enviar_archivo(archivo, info)
            print("PDF enviado por correo....✅")
            return Response({'Mensaje': 'Todo Bien'},status= status.HTTP_200_OK)
        
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
                  
    def enviar_archivo(self, archivo, info, comentario="nada"):
        print("Enviando archivo por correo electrónico Garza Sada....📫")
        print("Comentarios....💬",comentario)
        arrendatario = info["nombre_arrendatario"]
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            # destinatario = 'jsepulvedaarrendify@gmail.com'
            destinatario = 'jcasados@fraterna.mx'
            # destinatario2 = 'juridico.arrendify1@gmail.com'
            destinatario2 = 'smosqueda@fraterna.mx'
            
            
            asunto = f"Resultado Investigación Arrendatario {arrendatario}"
            
            destinatarios = [destinatario,destinatario2]
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Cc'] = destinatario2
            msg['Subject'] = asunto
            print("Cabecera de correo electrónico creada....✅")
           
            # Estilo del mensaje
            #variable resultado_html_fraterna
            pdf_html = aprobado_fraterna(info)
          
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("PDf adjuntado al mensaje....✅")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Resultado_investigación.pdf')
            msg.attach(pdf_part)
            print("Se creo el mail con el PDF adjunto....✅")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                server.sendmail(remitente, destinatarios, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
            print("Correo electrónico enviado correctamente....✅")
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})
        
class DocumentosArrendatario_GarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendatarios_garzasada.objects.all()
    serializer_class = DAGSSerializer
   
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendatarios Garza Sada....📄")
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def create (self, request, *args,**kwargs):
        try: 
            print("Creando Documentos Arrendatarios Garza Sada....📄")
            user_session = str(request.user.id)
            
            # Verificar si el arrendatario existe
            arrendatario_id = request.data.get('arrendatario')
            print(f"🔍 Verificando arrendatario con ID: {arrendatario_id} (tipo: {type(arrendatario_id)})")
            
            if not arrendatario_id:
                return Response({'error': 'El ID del arrendatario es requerido'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Convertir a entero
            try:
                arrendatario_id = int(arrendatario_id)
                print(f"✅ ID convertido a entero: {arrendatario_id}")
            except (ValueError, TypeError):
                return Response({'error': f'ID del arrendatario inválido: {arrendatario_id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Verificar si existe el arrendatario en la base de datos
            try:
                arrendatario = Arrendatarios_garzasada.objects.get(id=arrendatario_id)
                print(f"✅ Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm}")
            except Arrendatarios_garzasada.DoesNotExist:
                print(f"❌ El arrendatario con ID {arrendatario_id} NO EXISTE en la base de datos")
                # Listar arrendatarios disponibles
                arrendatarios_disponibles = Arrendatarios_garzasada.objects.all().values('id', 'nombre_arrendatario', 'nombre_empresa_pm')
                print(f"📋 Arrendatarios disponibles: {list(arrendatarios_disponibles)}")
                return Response({
                    'error': f'El arrendatario con ID {arrendatario_id} no existe',
                    'arrendatarios_disponibles': list(arrendatarios_disponibles)
                }, status=status.HTTP_400_BAD_REQUEST)
            
            data = {
                    "Ine_arrendatario": request.FILES.get('Ine_arrendatario', None),
                    "Ine_obligado": request.FILES.get('Ine_obligado', None),
                    "Comp_dom_arrendatario": request.FILES.get('Comp_dom_arrendatario', None),
                    "Comp_dom_obligado": request.FILES.get('Comp_dom_obligado', None),
                    "Rfc_arrendatario": request.FILES.get('Rfc_arrendatario', None),
                    "Ingresos_arrendatario": request.FILES.get('Ingresos_arrendatario', None),
                    "Ingresos2_arrendatario": request.FILES.get('Ingresos2_arrendatario', None),
                    "Ingresos3_arrendatario": request.FILES.get('Ingresos3_arrendatario', None),
                    "Ingresos_obligado": request.FILES.get('Ingresos_obligado', None),
                    "Ingresos2_obligado": request.FILES.get('Ingresos_obligado2', None),
                    "Ingresos3_obligado": request.FILES.get('Ingresos_obligado3', None),
                    "Extras": request.FILES.get('Extras', None),
                    "Recomendacion_laboral": request.FILES.get('Recomendacion_laboral', None),
                    "arrendatario":arrendatario_id,
                    "user":user_session
                }
          
            if data:
                documentos_serializer = self.get_serializer(data=data)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save()
                print("Documentos Arrendatarios Garza Sada guardados correctamente....✅")
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            print("Eliminando Documentos Arrendatario Garza Sada....🗑️")
            documentos_inquilinos = self.get_object()
            documento_inquilino_serializer = self.serializer_class(documentos_inquilinos)
            if documentos_inquilinos:
                ine = documento_inquilino_serializer.data['ine']
                print("Eliminando INE....", ine)
                comp_dom= documento_inquilino_serializer.data['comp_dom']
                rfc= documento_inquilino_serializer.data['escrituras_titulo']
                print("Eliminando RFC....", rfc)
                ruta_ine = 'apps/static'+ ine
                print("Ruta ine", ruta_ine)
                ruta_comprobante_domicilio = 'apps/static'+ comp_dom
                ruta_rfc = 'apps/static'+ rfc
                print("Ruta com", ruta_comprobante_domicilio)
                print("Ruta RFC", ruta_rfc)
            
                # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
                documentos_inquilinos.delete()
                print("Documentos Arrendatario Garza Sada eliminados correctamente....✅")
                return Response({'message': 'Archivo eliminado correctamente'}, status=204)
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
        
    def retrieve(self, request, pk=None):
        try:
            documentos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            inquilino = documentos.filter(id=pk)
            serializer_inquilino = DISerializer(inquilino, many=True)
            print(serializer_inquilino.data)
            ine = serializer_inquilino.data[0]['ine']
            print(ine)
            # documentos_arrendador = self.get_object()
            # print(documentos_arrendador)
            return Response(serializer_inquilino.data)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
   
    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando Documentos Arrendatario Garza Sada....🔄")
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print("Datos Actuales ====>",request.data)
            
            # Verificar si se proporciona un nuevo archivo adjunto
            keys = request.data.keys()
    
            # Convertir las llaves a una lista y obtener la primera
            first_key = list(keys)[0]
            #first_key = str(first_key)
            print(first_key)
            
            # Acceder dinámicamente al atributo de instance usando first_key
            if hasattr(instance, first_key):
                archivo_anterior = getattr(instance, first_key)
                print("Archivo anterior ====>", archivo_anterior)
                eliminar_archivo_s3(archivo_anterior)
            else:
                print(f"El atributo '{first_key}' no existe en la instancia.")
            
            serializer.update(instance, serializer.validated_data)
            print("Se actualizó correctamente el documento del arrendatario Garza Sada....✅")
            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
class DocumentosArrendamiento_GarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendamientos_garzasada.objects.all()
    serializer_class = GarzaSadaArrendamientosSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendamiento Garza Sada....📄")
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list documentos arrendamientos es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Documentos Arrendamiento Garza Sada....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            print("FILES ===>", request.FILES)
            
            # Verificar si viene contrato_id directamente (desde GarzaSada)
            contrato_id = data.get('contrato_id', None)
            sin_recibo = data.get('sin_recibo', 'false').lower() == 'true'
            numero_pago_manual = data.get('numero_pago', None)
            
            print(f"Contrato ID: {contrato_id}, Sin Recibo: {sin_recibo}, Número Pago Manual: {numero_pago_manual}")
            
            if contrato_id:
                # Flujo para usuario GarzaSada con contrato específico
                print(f"Flujo GarzaSada - Buscando contrato ID: {contrato_id}")
                try:
                    contrato = GarzaSadaContratos.objects.get(id=contrato_id)
                    arrendatario = contrato.arrendatario
                    print(f"Contrato y arrendatario encontrados: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm}")
                except GarzaSadaContratos.DoesNotExist:
                    return Response({'error': f'Contrato ID {contrato_id} no encontrado'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Flujo original para usuarios normales
                # Usar first_name del usuario autenticado para buscar arrendatario
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                # Intentar diferentes estrategias de búsqueda
                arrendatario = None
                
                # Estrategia 1: Buscar por nombre completo
                arrendatario = Arrendatarios_garzasada.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario)
                ).first()
                
                # Estrategia 2: Si no encuentra, buscar por primer nombre
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    print(f"Buscando por primer nombre: {primer_nombre}")
                    arrendatario = Arrendatarios_garzasada.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(nombre_empresa_pm__icontains=primer_nombre)
                    ).first()
                
                # Estrategia 3: Si aún no encuentra, buscar por palabras individuales
                if not arrendatario:
                    palabras = nombre_usuario.split()
                    for palabra in palabras:
                        if len(palabra) > 2:  # Solo palabras de más de 2 caracteres
                            print(f"Buscando por palabra: {palabra}")
                            arrendatario = Arrendatarios_garzasada.objects.filter(
                                Q(nombre_arrendatario__icontains=palabra) |
                                Q(nombre_empresa_pm__icontains=palabra)
                            ).first()
                            if arrendatario:
                                break
                
                # Estrategia 4: Buscar por relación directa con el usuario
                if not arrendatario:
                    print("Buscando arrendatario asociado directamente al usuario")
                    arrendatario = Arrendatarios_garzasada.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                print(f"Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm} (ID: {arrendatario.id})")
                
                # Buscar contrato relacionado
                try:
                    contrato = GarzaSadaContratos.objects.get(arrendatario=arrendatario)
                    print(f"Contrato encontrado: {contrato.id}")
                except GarzaSadaContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Buscar proceso relacionado
            try:
                proceso = ProcesoContrato_garzasada.objects.get(contrato=contrato)
                print(f"Proceso encontrado: {proceso.id}")
            except ProcesoContrato_garzasada.DoesNotExist:
                return Response({'error': f'Proceso no encontrado para el contrato ID: {contrato.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            duracion_meses = self.extraer_duracion_meses(contrato.duracion)
            print(f"Duración extraída: {duracion_meses} meses")

            # Determinar número de pago
            if numero_pago_manual:
                # Usar número de pago manual si viene
                numero_pago_actual = int(numero_pago_manual)
                print(f"Usando número de pago manual: {numero_pago_actual}")
                
                # ✅ VALIDACIÓN: Verificar que no exista ya un pago con este número
                pago_existente = DocumentosArrendamientos_garzasada.objects.filter(
                    contrato=contrato,
                    proceso=proceso,
                    numero_pago=numero_pago_actual
                ).first()
                
                if pago_existente:
                    return Response({
                        'error': f'Ya existe un pago registrado con el número {numero_pago_actual} para este contrato',
                        'detalles': {
                            'numero_pago': numero_pago_actual,
                            'contrato_id': contrato.id,
                            'proceso_id': proceso.id,
                            'fecha_registro': pago_existente.dateTimeOfUpload.strftime('%Y-%m-%d %H:%M:%S') if pago_existente.dateTimeOfUpload else 'N/A'
                        }
                    }, status=status.HTTP_400_BAD_REQUEST)
                
            else:
                # Contar pagos existentes para este contrato
                pagos_existentes = DocumentosArrendamientos_garzasada.objects.filter(contrato=contrato).count()
                numero_pago_actual = pagos_existentes + 1
                print(f"Número de pago calculado automáticamente: {numero_pago_actual}")

            # Calcular renta total
            renta_total = Decimal(str(contrato.renta)) * duracion_meses if contrato.renta else Decimal('0')

            # Calcular interés por retraso (12% anual) - SOLO si no es un pago sin recibo
            interes_aplicado = Decimal('0')
            fecha_vencimiento = datetime.now().date() + timedelta(days=30)  # 30 días para pagar

            if not sin_recibo:  # Solo calcular intereses si hay recibo físico
                # Verificar si hay retraso en pagos anteriores
                if numero_pago_actual > 1:
                    ultimo_pago = DocumentosArrendamientos_garzasada.objects.filter(
                        contrato=contrato
                    ).order_by('-dateTimeOfUpload').first()
                    
                    if ultimo_pago and ultimo_pago.fecha_vencimiento:
                        dias_retraso = (datetime.now().date() - ultimo_pago.fecha_vencimiento).days
                        if dias_retraso > 0:
                            # Aplicar 12% anual = 1% mensual
                            interes_mensual = Decimal('0.01')
                            meses_retraso = Decimal(str(dias_retraso)) / Decimal('30')
                            interes_aplicado = Decimal(str(contrato.renta)) * interes_mensual * meses_retraso
            
            # Obtener archivo - puede ser None si sin_recibo=true
            comp_pago_file = request.FILES.get('comp_pago', None)
            
            # Validar que si no es sin_recibo, debe venir archivo
            if not sin_recibo and not comp_pago_file:
                return Response({
                    'error': 'Se requiere archivo de recibo para registrar el pago'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Obtener referencia de pago del request
            referencia_pago = data.get('referencia_pago', '')
            print(f"📝 Referencia de pago recibida: '{referencia_pago}'")
            
            # Crear documento
            documento_data = {
                "user": user_session.id,
                "arrendatario": arrendatario.id,
                "contrato": contrato.id,
                "proceso": proceso.id,
                "comp_pago": comp_pago_file,  # Puede ser None si sin_recibo=true
                "referencia_pago": referencia_pago,  
                "numero_pago": numero_pago_actual,
                "total_pagos": duracion_meses,
                "renta_total": renta_total,
                "interes_aplicado": interes_aplicado,
                "fecha_vencimiento": fecha_vencimiento,
            }
            
            tipo_registro = "SIN RECIBO" if sin_recibo else "CON RECIBO"
            print(f"Pago {numero_pago_actual} de {duracion_meses} ({tipo_registro}) - Renta total: ${renta_total} - Interés: ${interes_aplicado}")
            
            arrendamientos_serializer = self.get_serializer(data=documento_data)
            arrendamientos_serializer.is_valid(raise_exception=True)
            arrendamientos_serializer.save()
            
            print("Documento ligado correctamente....✅")
            return Response(arrendamientos_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def extraer_duracion_meses(self, duracion_texto):
        """
        Extrae la duración en meses de un texto.
        Ejemplos: "6 meses" -> 6, "12 meses" -> 12, "24 meses" -> 24
        """
        if not duracion_texto:
            return 1
        
        # Convertir a string y buscar números
        texto = str(duracion_texto).lower().strip()
        
        # Buscar números en el texto
        numeros = re.findall(r'\d+', texto)
        
        if numeros:
            duracion = int(numeros[0])
            # Validar que sea un número razonable (entre 1 y 60 meses)
            if 1 <= duracion <= 60:
                return duracion
            else:
                print(f"Advertencia: Duración inusual detectada: {duracion} meses")
                return duracion
        
        # Si no encuentra números, intentar palabras
        palabras_meses = {
            'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6,
            'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10, 'once': 11, 'doce': 12,
            'dieciocho': 18, 'veinticuatro': 24, 'treinta': 30, 'treinta y seis': 36
        }
        
        for palabra, valor in palabras_meses.items():
            if palabra in texto:
                return valor
        
        print(f"No se pudo extraer duración de: '{duracion_texto}', usando 1 mes por defecto")
        return 1
        
    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            print("Eliminando Documentos Arrendamiento Garza Sada....🗑️")
            documentos_arrendamiento = self.get_object()
            documento_arrendamiento_serializer = self.serializer_class(documentos_arrendamiento)
            if documentos_arrendamiento:
                comp_pago = documento_arrendamiento_serializer.data['comp_pago']
                print("Eliminando Comprobante de Pago....", comp_pago)
                
                documentos_arrendamiento.delete()
                print("Documentos Arrendamiento Garza Sada eliminados correctamente....✅")
                return Response({'message': 'Archivo eliminado correctamente'}, status=204) 
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:  
            print(f"el error es en documentos arrendamiento destroy es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando Documentos Arrendatario Garza Sada....🔄")
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print("Datos Actuales ====>",request.data)
            
            # Verificar si se proporciona un nuevo archivo adjunto
            keys = request.data.keys()
    
            # Convertir las llaves a una lista y obtener la primera
            first_key = list(keys)[0]
            #first_key = str(first_key)
            print(first_key)
            
            # Acceder dinámicamente al atributo de instance usando first_key
            if hasattr(instance, first_key):
                archivo_anterior = getattr(instance, first_key)
                print("Archivo anterior ====>", archivo_anterior)
                eliminar_archivo_s3(archivo_anterior)
                print("Archivo eliminado de S3 desde GarzaSada....✅")
            else:
                print(f"El atributo '{first_key}' no existe en la instancia.")
            
            serializer.update(instance, serializer.validated_data)
            print("Se actualizó correctamente el documento del arrendatario Garza Sada....✅")
            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='reporte_completo')
    def reporte_completo(self, request):
        """
        Genera un reporte PDF completo con información detallada de arrendamientos
        
        Control de acceso:
        - Usuarios normales: Solo su información
        - Administradores: Todos los arrendamientos o filtrados por arrendatario_id
        
        Query params:
        - arrendatario_id (opcional): Filtrar por ID de arrendatario específico
        """
        try:
            from django.http import HttpResponse
            from django.template.loader import render_to_string
            from weasyprint import HTML
            from collections import defaultdict
            
            print("Generando reporte completo de arrendamientos Fraterna....📊")
            
            # Verificar si es administrador
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            
            # Obtener parámetro de filtro (solo para admin)
            arrendatario_id = request.query_params.get('arrendatario_id', None)
            
            # Construir queryset base
            queryset = DocumentosArrendamientosFraternaModel.objects.select_related(
                'arrendatario',
                'contrato',
                'proceso'
            )
            
            if es_admin:
                print(f"Usuario administrador: {request.user.username}")
                # Administrador puede ver todos o filtrar por arrendatario_id
                if arrendatario_id:
                    queryset = queryset.filter(arrendatario_id=arrendatario_id)
                    print(f"Filtrando por arrendatario ID: {arrendatario_id}")
            else:
                print(f"Usuario normal: {request.user.username}")
                # Usuario normal: solo sus propios datos
                # Buscar arrendatario asociado al usuario
                nombre_usuario = request.user.first_name.strip()
                arrendatario = Residentes.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario) |
                    Q(user=request.user)
                ).first()
                
                if not arrendatario:
                    return Response({
                        'error': 'No se encontró información de arrendamiento para este usuario'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                queryset = queryset.filter(arrendatario=arrendatario)
                print(f"Filtrando por arrendatario: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm}")
            
            # Ordenar resultados
            recibos = queryset.order_by('arrendatario__nombre_arrendatario', 'numero_pago')
            
            # Agrupar información por arrendatario
            arrendatarios_data = defaultdict(lambda: {
                'arrendatario': {},
                'contrato': {},
                'recibos': [],
                'estadisticas': {
                    'total_pagos': 0,
                    'pagos_realizados': 0,
                    'pagos_pendientes': 0,
                    'renta_mensual': 0,
                    'renta_total': 0,
                    'total_pagado': 0,
                    'total_pendiente': 0,
                    'interes_total': 0,
                    'porcentaje_completado': 0,
                }
            })
            
            for recibo in recibos:
                if not recibo.arrendatario:
                    continue
                
                arr_id = recibo.arrendatario.id
                
                # Información del arrendatario (solo la primera vez)
                if not arrendatarios_data[arr_id]['arrendatario']:
                    nombre = recibo.arrendatario.nombre_arrendatario or recibo.arrendatario.nombre_empresa_pm
                    
                    # Determinar email y teléfono según el tipo
                    if recibo.arrendatario.nombre_arrendatario:
                        # Persona Física
                        email = recibo.arrendatario.correo or 'No especificado'
                        telefono = recibo.arrendatario.celular or 'No especificado'
                        tipo = 'Persona Física'
                    else:
                        # Persona Moral
                        email = recibo.arrendatario.correo or 'No especificado'
                        telefono = recibo.arrendatario.telefono_empresa_pm or 'No especificado'
                        tipo = 'Persona Moral'
                    
                    arrendatarios_data[arr_id]['arrendatario'] = {
                        'nombre': nombre,
                        'email': email,
                        'telefono': telefono,
                        'tipo': tipo,
                    }
                
                # Información del contrato (solo la primera vez)
                if recibo.contrato and not arrendatarios_data[arr_id]['contrato']:
                    contrato = recibo.contrato
                    arrendatarios_data[arr_id]['contrato'] = {
                        'no_depa': contrato.no_depa or 'N/A',
                        'num_inq': contrato.num_inq or 'N/A',
                        'duracion': contrato.duracion or 'No especificada',
                        'fecha_celebracion': contrato.fecha_celebracion.strftime('%d/%m/%Y') if contrato.fecha_celebracion else 'N/A',
                        'fecha_vigencia': contrato.fecha_vigencia.strftime('%d/%m/%Y') if contrato.fecha_vigencia else 'N/A',
                        'renta': float(contrato.renta) if contrato.renta else 0,
                    }
                
                # Calcular estado del pago y días de retraso
                estado = 'Sin fecha'
                dias_retraso = 0
                if recibo.fecha_vencimiento:
                    hoy = date.today()
                    dias_restantes = (recibo.fecha_vencimiento - hoy).days
                    if dias_restantes < 0:
                        estado = 'Vencido'
                        dias_retraso = abs(dias_restantes)
                    elif dias_restantes <= 7:
                        estado = 'Próximo a vencer'
                    else:
                        estado = 'Al día'
                
                # Calcular montos y datos adicionales para admin
                renta_mensual = float(recibo.contrato.renta) if recibo.contrato and recibo.contrato.renta else 0
                interes_aplicado = float(recibo.interes_aplicado) if recibo.interes_aplicado else 0
                penalizacion = interes_aplicado
                monto_pagado = renta_mensual if recibo.comp_pago else 0
                monto_pendiente = renta_mensual - monto_pagado
                usuario_subio = 'Sin usuario'
                if recibo.user:
                    usuario_subio = recibo.user.first_name or recibo.user.username
                referencia_pago = f"GS-{recibo.id:06d}" if recibo.id else 'N/A'
                
                # Agregar recibo con campos básicos
                recibo_data = {
                    'numero_pago': recibo.numero_pago or 0,
                    'fecha_subida': recibo.dateTimeOfUpload.strftime('%d/%m/%Y %H:%M') if recibo.dateTimeOfUpload else 'N/A',
                    'fecha_vencimiento': recibo.fecha_vencimiento.strftime('%d/%m/%Y') if recibo.fecha_vencimiento else 'N/A',
                    'interes': interes_aplicado,
                    'estado': estado,
                }
                
                # Campos adicionales para administrador
                if es_admin:
                    recibo_data.update({
                        'departamento': recibo.contrato.no_depa if recibo.contrato else 'N/A',
                        'num_inq': recibo.contrato.num_inq if recibo.contrato else 'N/A',
                        'referencia_pago': referencia_pago,
                        'monto': renta_mensual,
                        'monto_pagado': monto_pagado,
                        'monto_pendiente': monto_pendiente,
                        'dias_retraso': dias_retraso,
                        'penalizacion': penalizacion,
                        'usuario': usuario_subio,
                    })
                
                arrendatarios_data[arr_id]['recibos'].append(recibo_data)
                
                # Actualizar estadísticas
                stats = arrendatarios_data[arr_id]['estadisticas']
                stats['total_pagos'] = recibo.total_pagos or 0
                stats['pagos_realizados'] = len(arrendatarios_data[arr_id]['recibos'])
                stats['pagos_pendientes'] = stats['total_pagos'] - stats['pagos_realizados']
                stats['renta_total'] = float(recibo.renta_total) if recibo.renta_total else 0
                stats['interes_total'] += interes_aplicado
                
                if recibo.contrato and recibo.contrato.renta:
                    stats['renta_mensual'] = float(recibo.contrato.renta)
                    stats['total_pagado'] = stats['renta_mensual'] * stats['pagos_realizados']
                    stats['total_pendiente'] = stats['renta_mensual'] * stats['pagos_pendientes']
                
                # Calcular porcentaje
                if stats['total_pagos'] > 0:
                    stats['porcentaje_completado'] = round((stats['pagos_realizados'] / stats['total_pagos']) * 100, 1)
            
            # Calcular contratos por vencer (próximos 30 días)
            hoy = date.today()
            fecha_limite = hoy + timedelta(days=30)
            contratos_por_vencer = 0
            pagos_atrasados = 0
            
            for arr_data in arrendatarios_data.values():
                # Contar contratos por vencer
                fecha_vigencia_str = arr_data['contrato'].get('fecha_vigencia', '')
                if fecha_vigencia_str and fecha_vigencia_str != 'N/A':
                    try:
                        fecha_vigencia = datetime.strptime(fecha_vigencia_str, '%d/%m/%Y').date()
                        if hoy <= fecha_vigencia <= fecha_limite:
                            contratos_por_vencer += 1
                    except:
                        pass
                
                # Contar pagos atrasados (solo los que ya pasaron su fecha de vencimiento)
                for recibo in arr_data['recibos']:
                    # Solo contar como atrasado si el estado es 'Vencido'
                    # Esto significa que la fecha de vencimiento ya pasó
                    if recibo.get('estado', '') == 'Vencido':
                        pagos_atrasados += 1
            
            # Calcular totales generales
            totales_generales = {
                'total_arrendatarios': len(arrendatarios_data),
                'total_recibos': recibos.count(),
                'ingresos_totales': sum(arr['estadisticas']['total_pagado'] for arr in arrendatarios_data.values()),
                'pendientes_totales': sum(arr['estadisticas']['total_pendiente'] for arr in arrendatarios_data.values()),
                'intereses_totales': sum(arr['estadisticas']['interes_total'] for arr in arrendatarios_data.values()),
                'contratos_por_vencer': contratos_por_vencer,
                'pagos_atrasados': pagos_atrasados,
            }
            
            # Contexto para el template
            context = {
                'arrendatarios': list(arrendatarios_data.values()),
                'totales': totales_generales,
                'fecha_generacion': datetime.now().strftime('%d/%m/%Y %H:%M'),
                'usuario_generador': request.user.first_name or request.user.username,
            }
            
            # Seleccionar template según tipo de usuario
            template_name = 'home/reporte_arrendamientos_garzasada_admin.html' if es_admin else 'home/reporte_arrendamientos_garzasada_v2.html'
            print(f"Usando template: {template_name}")
            
            # Renderizar HTML
            html_string = render_to_string(template_name, context)
            
            # Generar PDF
            html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
            pdf = html.write_pdf()
            
            # Crear respuesta HTTP
            response = HttpResponse(pdf, content_type='application/pdf')
            filename_suffix = '_admin' if es_admin else ''
            response['Content-Disposition'] = f'attachment; filename="reporte_arrendamientos_garzasada{filename_suffix}_{date.today().strftime("%Y%m%d")}.pdf"'
            
            print("Reporte generado exitosamente....✅")
            return response
            
        except Exception as e:
            print(f"Error al generar reporte: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': f'Error al generar el reporte: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='lista_arrendatarios')
    def lista_arrendatarios(self, request):
        """
        Obtiene la lista completa de arrendatarios con contratos activos.
        Solo disponible para administradores.
        Útil para filtros en el frontend.
        """
        try:
            # Verificar si es administrador
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            
            if not es_admin:
                return Response({
                    'error': 'No tienes permisos para acceder a esta información'
                }, status=status.HTTP_403_FORBIDDEN)
            
            print(f"Admin {request.user.username} solicitando lista de arrendatarios")
            
            # Obtener arrendatarios únicos con contratos
            arrendatarios = Arrendatarios_garzasada.objects.filter(
                contratos_garzasada__isnull=False
            ).distinct().values(
                'id',
                'nombre_arrendatario',
                'nombre_empresa_pm'
            )
            
            # Formatear respuesta
            lista = []
            for arr in arrendatarios:
                nombre = arr['nombre_arrendatario'] or arr['nombre_empresa_pm']
                if nombre:
                    lista.append({
                        'id': arr['id'],
                        'nombre': nombre
                    })
            
            print(f"Se encontraron {len(lista)} arrendatarios")
            return Response(lista, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error al obtener lista de arrendatarios: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class IncidenciasGarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = IncidenciasGarzaSada.objects.all()
    serializer_class = IncidenciasGarzaSadaSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendamiento Garza Sada....📄")
            queryset = self.filter_queryset(self.get_queryset())
            IncidenciasSerializers = self.get_serializer(queryset, many=True)
            return Response(IncidenciasSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list documentos arrendamientos es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Solicitud de Incidencia....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            
            # Verificar si es usuario autorizado para incidencias Arrendify
            usuarios_autorizados = ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            es_usuario_autorizado = (
                user_session.is_staff or 
                user_session.is_superuser or 
                user_session.username in usuarios_autorizados or
                getattr(user_session, 'pertenece_a', None) in usuarios_autorizados
            )
            
            arrendatario = None
            contrato = None
            
            if es_usuario_autorizado:
                print(f"Usuario autorizado para incidencias Arrendify: {user_session.username}")
                # Para usuarios autorizados, crear incidencia sin arrendatario/contrato
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": None,
                    "contrato": None,
                    "incidencia": data.get('incidencia', ''),
                    "tipo_incidencia": data.get('tipo_incidencia', ''),
                    "prioridad": data.get('prioridad', 'Media'),
                    "status": "Pendiente de Revisión",
                }
                print(f"Creando incidencia Arrendify sin asociaciones: User={user_session.id}")
            else:
                # Lógica original para usuarios regulares
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                # Intentar diferentes estrategias de búsqueda
                arrendatario = None
                
                # Estrategia 1: Buscar por nombre completo
                arrendatario = Arrendatarios_garzasada.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario)
                ).first()
                
                # Estrategia 2: Si no encuentra, buscar por primer nombre
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    print(f"Buscando por primer nombre: {primer_nombre}")
                    arrendatario = Arrendatarios_garzasada.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(nombre_empresa_pm__icontains=primer_nombre)
                    ).first()
                
                # Estrategia 3: Si aún no encuentra, buscar por palabras individuales
                if not arrendatario:
                    palabras = nombre_usuario.split()
                    for palabra in palabras:
                        if len(palabra) > 2:  # Solo palabras de más de 2 caracteres
                            print(f"Buscando por palabra: {palabra}")
                            arrendatario = Arrendatarios_garzasada.objects.filter(
                                Q(nombre_arrendatario__icontains=palabra) |
                                Q(nombre_empresa_pm__icontains=palabra)
                            ).first()
                            if arrendatario:
                                break
                
                # Estrategia 4: Buscar por relación directa con el usuario
                if not arrendatario:
                    print("Buscando arrendatario asociado directamente al usuario")
                    arrendatario = Arrendatarios_garzasada.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                print(f"Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm} (ID: {arrendatario.id})")
                
                # Buscar contrato relacionado
                try:
                    contrato = GarzaSadaContratos.objects.get(arrendatario=arrendatario)
                    print(f"Contrato encontrado: {contrato.id}")
                except GarzaSadaContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Crear Incidencia para usuario regular
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": arrendatario.id,
                    "contrato": contrato.id,
                    "incidencia": data.get('incidencia', ''),
                    "status": "Pendiente de Revisión",
                }
                print(f"Creando incidencia regular con: User={user_session.id}, Arrendatario={arrendatario.id}, Contrato={contrato.id}")
            
            arrendamientos_serializer = self.get_serializer(data=incidencia_data)
            arrendamientos_serializer.is_valid(raise_exception=True)
            arrendamientos_serializer.save()
            
            print("Incidencia creada exitosamente....✅")
            return Response(arrendamientos_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)       
        
#////////////////////////CONTRATOS GARZA SADA///////////////////////////////
class Contratos_GarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = GarzaSadaContratos.objects.all()
    serializer_class = ContratoGarzaSadaSerializer
    
    def list(self, request, *args, **kwargs):
        try:
           user_session = request.user       
           if user_session.is_staff or user_session.username == "GarzaSada":
               print("Listar contratos Garza Sada....")
               # ✅ Incluir datos del arrendatario con select_related
               contratos =  GarzaSadaContratos.objects.select_related('arrendatario').all().order_by('-id')
               serializer = self.get_serializer(contratos, many=True)
               serialized_data = serializer.data
                
               # Agregar el campo 'is_staff'
               for item in serialized_data:
                 item['is_staff'] = True
                
               return Response(serialized_data)
           
           elif user_session.rol == "Inmobiliaria":#La inmobiliaria ve todos los contratos de sus agentes y los suyos
               print("Inmobiliaria ====>", user_session.name_inmobiliaria)
               agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) #primero obtenemos mis agentes.
               contratos_inmobiliaria = GarzaSadaContratos.objects.filter(user_id = user_session.id)#Obetenemos los contratos de la inmobiliaria
               contratos_agentes = GarzaSadaContratos.objects.filter(user_id__in = agentes.values("id"))#Obtenemos los contratos de los agentes que pertenecen a la inmobiliaria
               contratos_all = contratos_inmobiliaria.union(contratos_agentes)#Hacemos union de los contratos de la inmobiliaria y los agentes
               contratos_all = contratos_all.order_by('-id')#Ordenamos por id descendente
               
               serializer = self.get_serializer(contratos_all, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
               
           elif user_session.rol == "Agente":#El agente solo ve sus contratos
               print("Agente ====>", user_session.first_name)
               residentes_agente = GarzaSadaContratos.objects.filter(user_id = user_session).order_by('-id')#Obtenemos los contratos del agente y oredenamos por id descendente
               serializer = self.get_serializer(residentes_agente , many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
           
           elif user_session.rol == "Residente" and user_session.pertenece_a == "GarzaSada":#El residente ve sus contratos
                print("Residente ====>", user_session.first_name)
                nombre_busqueda = (user_session.first_name).strip()

                # Si no hay nombre para filtrar, retorna lista vacía por seguridad
                if not nombre_busqueda:
                    return Response([], status=status.HTTP_200_OK)

                contratos_residente = (
                    GarzaSadaContratos.objects
                    .filter(
                        Q(arrendatario__nombre_arrendatario__icontains=nombre_busqueda) |
                        Q(arrendatario__nombre_empresa_pm__icontains=nombre_busqueda)
                    )
                    .order_by('-id')
                )

                serializer = self.get_serializer(contratos_residente, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)

           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print("Datos a Guardar ====>",request.data)
            print("Creando contrato Garza Sada....📑")
            
            fecha_actual = date.today()
            contrato_serializer = self.serializer_class(data = request.data) #Usa el serializer_class
            if contrato_serializer.is_valid():
                nuevo_proceso = ProcesoContrato_garzasada.objects.create(usuario = user_session, fecha = fecha_actual, status_proceso = "En Revisión")
                if nuevo_proceso:
                    print("ID Contrato nuevo ====>",nuevo_proceso.id)
                    info = contrato_serializer.save(user = user_session)
                    nuevo_proceso.contrato = info
                    nuevo_proceso.save()
                    #send_noti_varios(FraternaContratos, request, title="Nueva solicitud de contrato en Fraterna", text=f"A nombre del Arrendatario {info.residente.nombre_arrendatario}", url = f"fraterna/contrato/#{info.residente.id}_{info.cama}_{info.no_depa}")
                    #print("despues de metodo send_noti")#descomentar para notificaciones
                    print("Se genero nueva solicitud de contrato Garza Sada....✅")
                    return Response({'Semillero': contrato_serializer.data}, status=status.HTTP_201_CREATED)
                else:
                    print("No se creo el proceso de contrato Garza Sada....❌")
                    return Response({'msj':'no se creo el proceso'}, status=status.HTTP_204_NO_CONTENT) 
            
            else:
                print("serializer no valido")
                return Response({'msj':'no es valido el serializer'}, status=status.HTTP_204_NO_CONTENT)     
            
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando contrato Garza Sada....🔄")
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
           
                        
            proceso = ProcesoContrato_garzasada.objects.all().get(contrato_id = instance.id)
            print("Contador ====> ",proceso.contador)
            if (proceso.contador > 0 ):
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                if serializer.is_valid(raise_exception=True):
                    self.perform_update(serializer)
                    proceso.contador = proceso.contador - 1
                    proceso.save()
                    print("Edito contrato Garza Sada correctamente....✅")
                    #send_noti_varios(SemilleroContratos, request, title="Se a modificado el contrato de:", text=f"FRATERNA VS {instance.residente.nombre_arrendatario} - {instance.residente.nombre_residente}".upper(), url = f"fraterna/contrato/#{instance.residente.id}_{instance.cama}_{instance.no_depa}")
                    return Response(serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response({'errors': serializer.errors})
            else:
                return Response({'msj': 'LLegaste al limite de tus modificaciones en el proceso'}, status=status.HTTP_205_RESET_CONTENT)
      
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy(self,request, *args, **kwargs):
        try:
            print("Eliminando contrato Garza Sada....🗑️")
            residente = self.get_object()
            if residente:
                residente.delete()
                print("Contrato eliminado correctamente....✅")
                return Response({'message': 'residente eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
    @action(detail=False, methods=['post'], url_path='subir_contrato_pdf')
    def subir_contrato_pdf(self, request, *args, **kwargs):
        """
        Sube un contrato PDF (modo 'subir').
        Body:
          - arrendatario: ID del arrendatario (FK)
          - filename: nombre del archivo (sugerido)
          - mimetype: application/pdf
          - size: tamaño bytes (informativo)
          - data_base64: PDF en base64 (sin encabezado data:)
          - no_depa: (opcional) para asociar
        """
        try:
            data = request.data
            arr_id = data.get('arrendatario')
            filename = data.get('filename') or 'contrato.pdf'
            b64 = data.get('data_base64')
            no_depa = data.get('no_depa')

            if not arr_id or not b64:
                return Response({'error': 'arrendatario y data_base64 son requeridos'}, status=400)

            # decodificar
            try:
                file_bytes = base64.b64decode(b64)
            except Exception:
                return Response({'error': 'data_base64 inválido'}, status=400)

            # crear contrato mínimo
            arr = Arrendatarios_garzasada.objects.filter(pk=arr_id).first()
            if not arr:
                return Response({'error': 'Arrendatario no encontrado'}, status=404)

            contrato = GarzaSadaContratos.objects.create(
                user=request.user if request.user.is_authenticated else None,
                arrendatario=arr,
                no_depa=no_depa or None,
            )

            # guardar archivo
            contrato.contrato_pdf.save(filename, ContentFile(file_bytes), save=True)

            # crear proceso “En Revisión”, igual que en create()
            fecha_actual = date.today()
            proceso = ProcesoContrato_garzasada.objects.create(
                usuario=request.user,
                fecha=fecha_actual,
                status_proceso="En Revisión",
                contrato=contrato
            )

            return Response({
                'id': contrato.id,
                'arrendatario': contrato.arrendatario_id,
                'no_depa': contrato.no_depa,
                'archivo': contrato.contrato_pdf.url if contrato.contrato_pdf else None,
                'proceso': proceso.status_proceso,
            }, status=201)

        except Exception as e:
            print(f"error subir_contrato_pdf: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en {exc_tb.tb_frame.f_code.co_name} línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=400)
    
    
    def aprobar_contrato_garzasada(self, request, *args, **kwargs):
        try:
            print("Aprobar Contrato Garza Sada")
            print("Contrato a Aprobar ====>",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("ID ====>",instance.id)
            print(instance.__dict__)
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_garzasada.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            print("Proceso aprobado correctamente....✅")
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def desaprobar_contrato_garzasada(self, request, *args, **kwargs):
        try:
            print("Desaprobar Contrato Garza Sada")
            instance = self.queryset.get(id = request.data["id"])
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_garzasada.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = "En Revisión"
            # proceso.contador = 2 # en vista que me indiquen lo contrario lo dejamos asi
            proceso.save()
            print("Proceso desaprobado correctamente....✅")
            return Response({'Exito': 'Se cambio el estatus a desaprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
   
    def generar_paquete_completo_garzasada(self, request, *args, **kwargs):
        """
        Devuelve el paquete combinado en formato PDF descargable para visualizar en el front.
        """
        try:
            print("Generando paquete completo Garza Sada...")
            data = request.data
            if isinstance(data, dict):
                id_paq = data["id"]
                pagare_distinto = data.get("pagare_distinto", "No")
                cantidad_pagare = data.get("cantidad_pagare", "0")
                testigo1 = data.get("testigo1", "")
                testigo2 = data.get("testigo2", "")
            else:
                id_paq = data
                pagare_distinto = "No"
                cantidad_pagare = "0"

            nombre_archivo, pdf_bytes, total_paginas = self.generar_paquete_garzasada_pdf(id_paq, pagare_distinto, cantidad_pagare, testigo1, testigo2)

            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Paquete Garza Sada {nombre_archivo}"'
            response.write(pdf_bytes)
            print("paginas totales ====>", total_paginas)

            print("Paquete completo generado exitosamente")
            return response

        except Exception as e:
            print(f"Error en generar_paquete_completo_garzasada: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                        f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def generar_paquete_garzasada_pdf(self, id_paq, pagare_distinto="No", cantidad_pagare="0", testigo1="", testigo2=""):
            total_paginas = {"arrendamiento": 0, "poliza": 0, "pagares": 0}
            
            print("Soy el self",self)

            info = self.queryset.filter(id=id_paq).first()
            if not info:
                raise ValueError("Contrato no encontrado")

            pdf_writer = PdfWriter()

            # ===== 1) CONTRATO =====
            # Prioridad: 1) base64, 2) FileField, 3) generar desde plantilla
            if info.contrato_pdf_b64:
                print("Usando contrato PDF desde base64 subido...")
                import base64
                contrato_bytes = base64.b64decode(info.contrato_pdf_b64)
                contrato_reader = PdfReader(io.BytesIO(contrato_bytes))
            else:
                print("Generando contrato desde plantilla...")
                contrato_pdf = self._generar_contrato_garzasada_interno(info, testigo1=testigo1, testigo2=testigo2)
                contrato_reader = PdfReader(io.BytesIO(contrato_pdf))

            total_paginas["arrendamiento"] = len(contrato_reader.pages)
            for page in contrato_reader.pages:
                pdf_writer.add_page(page)

            # ===== 2) POLIZA =====
            poliza_pdf = self._generar_poliza_garzasada_interno(info)
            poliza_reader = PdfReader(io.BytesIO(poliza_pdf))
            total_paginas["poliza"] = len(poliza_reader.pages)
            for page in poliza_reader.pages:
                pdf_writer.add_page(page)

            # ===== 3) PAGARÉS =====
            pagare_pdf = self._generar_pagare_garzasada_interno(info, pagare_distinto, cantidad_pagare)
            pagare_reader = PdfReader(io.BytesIO(pagare_pdf))
            total_paginas["pagares"] = len(pagare_reader.pages)
            for page in pagare_reader.pages:
                pdf_writer.add_page(page)

            output_pdf = io.BytesIO()
            pdf_writer.write(output_pdf)
            output_pdf.seek(0)

            fecha_actual = dt.now().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"Paquete_Completo_GarzaSada_{info.arrendatario.nombre_arrendatario}_{fecha_actual}.pdf"

            return nombre_archivo, output_pdf.getvalue(), total_paginas
        
    def generar_pagare_garzasada(self, request, *args, **kwargs):
        try:
            #activamos la libreri de locale para obtener el mes en español
            print("Generar Pagare Garza Sada")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            print("data pagare ====>",request.data)
            id_paq = request.data["id"]
            pagare_distinto = request.data["pagare_distinto"]

            if pagare_distinto == "Si":
                if "." not in request.data["cantidad_pagare"]:
                    print("No tiene decimales....")
                    cantidad_pagare = request.data["cantidad_pagare"]
                    cantidad_decimal = "00"
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
                
                else:
                    cantidad_completa = request.data["cantidad_pagare"].split(".")
                    cantidad_pagare = cantidad_completa[0]
                    cantidad_decimal = cantidad_completa[1]
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
            else:
                cantidad_pagare = 0
                cantidad_decimal = "00"
                cantidad_letra = num2words(cantidad_pagare, lang='es')
            print(pagare_distinto)
            print(cantidad_pagare)
            
            print("ID ====>", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print("Datos Inquilino ====>",info.__dict__)
            # Definir la fecha inicial
            fecha_inicial = info.fecha_celebracion
            print("Fecha Celebracion ====>",fecha_inicial)
            #fecha_inicial = datetime(2024, 3, 20)
            #checar si cambiar el primer dia o algo asi
            # fecha inicial move in
            dia = fecha_inicial.day
            
            # Definir la duración en meses
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            print("MESES ====>",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_inicial < fecha_final:
                nombre_mes = fecha_inicial.strftime("%B")  # %B da el nombre completo del mes
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_inicial.year))      
                fecha_inicial += relativedelta(months=1)
            
            print("Fechas Iteradas ====>",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            for month, year in fechas_iteradas:
                print(f"Año: {year}, Mes: {month}")
            
            #obtenermos la renta para pasarla a letra
            if "." not in info.renta:
                print("No hay decimales en renta")
                number = int(info.renta)
                renta_decimal = "00"
                text_representation = num2words(number, lang='es').capitalize()
               
            else:
                print("Hay decimales en renta")
                renta_completa = info.renta.split(".")
                info.renta = renta_completa[0]
                renta_decimal = renta_completa[1]
                text_representation = num2words(renta_completa[0], lang='es').capitalize()
           
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'pagare_distinto':pagare_distinto , 'cantidad_pagare':cantidad_pagare, 'cantidad_letra':cantidad_letra,'cantidad_decimal':cantidad_decimal, 'renta_decimal':renta_decimal}
            
            template = 'home/pagare_garzasada.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Se genero el pagare correctamente....✅")
            return HttpResponse(response, content_type='application/pdf')
    
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_poliza_garzasada(self, request, *args, **kwargs):
        try:
            print("Generar Poliza Garza Sada")
            id_paq = request.data
            print("ID ====>", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)
            
            #vamos a genenrar el numero de contrato
            arrendatario = info.arrendatario.nombre_arrendatario
            primera_letra = arrendatario[0].upper()  # Obtiene la primera letra
            ultima_letra = arrendatario[-1].upper()  # Obtiene la última letra

            year = info.fecha_celebracion.strftime("%g")
            month = info.fecha_celebracion.strftime("%m")
            
            nom_contrato = f"AFY{month}{year}CX51{info.id}CA{primera_letra}{ultima_letra}"  
            print("Nombre del contrato", nom_contrato)     
            #obtenemos renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
       
            context = {'info': info, 'renta_texto':renta_texto, 'nom_contrato':nom_contrato,}
            template = 'home/poliza_garzasada.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO POLIZA")
            return HttpResponse(response, content_type='application/pdf')
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_contrato_garzasada(self, request, *args, **kwargs):
        try:
            print("Generar contrato Garza Sada")
            print("Data Entrante ====>", request.data)
            id_paq = request.data["id"]
            testigo1 = request.data["testigo1"]
            testigo2 = request.data["testigo2"]
            print("Testigo 1 ====>",testigo1)
            print("Testigo 2 ====>",testigo2)
            print("ID ====>", id_paq)
            info = self.queryset.filter(id=id_paq).first()
            print("Diccionario ====>",info.__dict__)
            
            #convertir m2 a texto
            superficie = float(info.superficie)
            superficie_texto=f"{num2words(float(superficie), lang='es')}"
            
            # 🧠 Convertir renta con centavos a texto
            renta = float(info.renta)
            parte_entera = int(renta)
            centavos = round((renta - parte_entera) * 100)
            renta_texto = f"{num2words(parte_entera, lang='es')} pesos"
            if centavos > 0:
                renta_texto += f" con {num2words(centavos, lang='es')} centavos"
            renta_texto = renta_texto.capitalize()
            
            # 🧠 Convertir deposito con centavos a texto
            deposito = float(info.deposito)
            parte_entera_deposito = int(deposito)
            centavos_deposito = round((deposito - parte_entera_deposito) * 100)
            deposito_texto = f"{num2words(parte_entera_deposito, lang='es')} pesos"
            if centavos_deposito > 0:
                deposito_texto += f" con {num2words(centavos, lang='es')} centavos"
            deposito_texto = deposito_texto.capitalize()
            
            #Obtener rentas antiicipadas
            anticipadas = float(info.anticipadas)
            rentas_anticipadas = float(anticipadas * renta)
            anticipadas_texto = f"{num2words(float(rentas_anticipadas), lang='es')} pesos"
            
            # Obtener los datos de la vigencia
            vigencia = info.duracion.split(" ")
            num_vigencia = vigencia[0]
            print("Vigencia ====>",num_vigencia)

            print("Generando Codigo de paquete...")
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            if info.id < 9:
                info.id = f"0{info.id}"
            print("Fecha Celebracion ====>", fec)
            
            # Obtener mes correspondiente a pago de renta
            # Generar rango del mes siguiente basado en la fecha de celebración
            fecha_celebracion = info.fecha_celebracion

            # Obtener el primer día del mes siguiente
            primer_dia_siguiente = fecha_celebracion.replace(day=1) + relativedelta(months=1)

            # Obtener el último día del mes siguiente
            ultimo_dia_siguiente = primer_dia_siguiente + relativedelta(months=1) - relativedelta(days=1)

            # Diccionario de meses en español
            meses_espanol = {
                1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
                5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
                9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
            }

            # Formatear las fechas en español
            rango_mes_siguiente = f"{primer_dia_siguiente.day:02d} de {meses_espanol[primer_dia_siguiente.month]} {primer_dia_siguiente.year} al {ultimo_dia_siguiente.day:02d} de {meses_espanol[ultimo_dia_siguiente.month]} {ultimo_dia_siguiente.year}"

            print("Rango del mes siguiente ====>", rango_mes_siguiente)
            
            # Calcular 1 mes antes de la fecha de vigencia
            fecha_vigencia = info.fecha_terminacion
            if fecha_vigencia:
                # Obtener 1 mes antes de la fecha de vigencia
                fecha_un_mes_antes_vigencia = fecha_vigencia - relativedelta(months=1)
                
                # Formatear la fecha en español
                mes_antes_vigencia = f"{fecha_un_mes_antes_vigencia.day:02d} de {meses_espanol[fecha_un_mes_antes_vigencia.month]} {fecha_un_mes_antes_vigencia.year}"
                
                print("Un mes antes de vigencia ====>", mes_antes_vigencia)
            else:
                # Si no hay fecha de vigencia, calcular basándose en fecha de celebración + duración
                duracion_meses = int(num_vigencia)  # Ya tienes num_vigencia calculado
                fecha_fin_vigencia = fecha_celebracion + relativedelta(months=duracion_meses)
                fecha_un_mes_antes_vigencia = fecha_fin_vigencia - relativedelta(months=1)
                
                # Formatear la fecha en español
                mes_antes_vigencia = f"{fecha_un_mes_antes_vigencia.day:02d} de {meses_espanol[fecha_un_mes_antes_vigencia.month]} {fecha_un_mes_antes_vigencia.year}"
                
                print("Un mes antes de vigencia (calculado) ====>", mes_antes_vigencia)

            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" + f"{info.id}" + "CA" + na
            print("Numero Paquete ====>", nom_paquete.upper())

            context = {
                'info': info,
                'renta_texto': renta_texto,
                'deposito_texto': deposito_texto,
                'superficie_texto': superficie_texto,
                'rentas_anticipadas': rentas_anticipadas,
                'anticipadas_texto': anticipadas_texto,
                'num_vigencia': num_vigencia,
                'nom_paquete': nom_paquete,
                'rango_mes_siguiente': rango_mes_siguiente,
                'mes_antes_vigencia': mes_antes_vigencia,
                "testigo1": testigo1,
                "testigo2": testigo2
            }
            # Para depurar el contexto
            print("Context ===> ",context)

            template = 'home/contrato_ga_sa.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("Contrato generado correctamente....✅")

            return HttpResponse(response, content_type='application/pdf')

        except Exception as e:
            print(f"el error en generar_contrato_garzasada es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST) 
        
    @action(detail=False, methods=['post'], url_path='descargar_contrato_base64')
    def descargar_contrato_base64(self, request, *args, **kwargs):
        """Descarga el contrato subido (almacenado en base64) como PDF"""
        try:
            print("Descargar contrato desde base64")
            print("Data Entrante ====>", request.data)
            
            id_contrato = request.data.get("id")
            if not id_contrato:
                return Response({'error': 'ID de contrato requerido'}, status=status.HTTP_400_BAD_REQUEST)
            
            info = self.queryset.filter(id=id_contrato).first()
            if not info:
                return Response({'error': 'Contrato no encontrado'}, status=status.HTTP_404_NOT_FOUND)
            
            if not info.contrato_pdf_b64:
                return Response({'error': 'No hay contrato en base64 para este registro'}, status=status.HTTP_404_NOT_FOUND)
            
            # Decodificar base64 a bytes
            import base64
            pdf_bytes = base64.b64decode(info.contrato_pdf_b64)
            
            # Devolver como PDF
            response = HttpResponse(content_type=info.contrato_mimetype or 'application/pdf')
            filename = info.contrato_filename or f'contrato_{id_contrato}.pdf'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.write(pdf_bytes)
            
            print(f"Contrato base64 descargado correctamente: {filename} ✅")
            return response
            
        except Exception as e:
            print(f"Error en descargar_contrato_base64: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def _generar_contrato_garzasada_interno(self, info, testigo1="", testigo2=""):
        """Función interna para generar el PDF del contrato de Garza Sada"""
        try:
            print(" Generando contrato Garza Sada interno...")
            print(f"   - Arrendatario: {info.arrendatario.nombre_arrendatario if info.arrendatario else 'NONE'}")
            print(f"   - Testigo1: {testigo1}, Testigo2: {testigo2}")
            
            # Convertir m2 a texto
            superficie = float(info.superficie) if info.superficie else 0
            print(f"   - Superficie: {superficie} m2")
            superficie_texto = f"{num2words(float(superficie), lang='es')}"
            
            # Convertir renta con centavos a texto
            renta = float(info.renta) if info.renta else 0
            print(f"   - Renta: ${renta}")
            parte_entera = int(renta)
            centavos = round((renta - parte_entera) * 100)
            renta_texto = f"{num2words(parte_entera, lang='es')} pesos"
            if centavos > 0:
                renta_texto += f" con {num2words(centavos, lang='es')} centavos"
            renta_texto = renta_texto.capitalize()
            
            # Convertir deposito con centavos a texto
            deposito = float(info.deposito)
            parte_entera_deposito = int(deposito)
            centavos_deposito = round((deposito - parte_entera_deposito) * 100)
            deposito_texto = f"{num2words(parte_entera_deposito, lang='es')} pesos"
            if centavos_deposito > 0:
                deposito_texto += f" con {num2words(centavos_deposito, lang='es')} centavos"
            deposito_texto = deposito_texto.capitalize()
            
            # Obtener rentas anticipadas
            anticipadas = float(info.anticipadas)
            rentas_anticipadas = float(anticipadas * renta)
            anticipadas_texto = f"{num2words(float(rentas_anticipadas), lang='es')} pesos"
            
            # Obtener los datos de la vigencia
            vigencia = info.duracion.split(" ")
            num_vigencia = vigencia[0]
            
            # Generar código de paquete
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            id_formatted = f"0{info.id}" if info.id < 9 else str(info.id)
            
            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" + id_formatted + "CA" + na
            
            # Generar rango del mes siguiente basado en la fecha de celebración
            fecha_celebracion = info.fecha_celebracion
            primer_dia_siguiente = fecha_celebracion.replace(day=1) + relativedelta(months=1)
            ultimo_dia_siguiente = primer_dia_siguiente + relativedelta(months=1) - relativedelta(days=1)
            
            # Diccionario de meses en español
            meses_espanol = {
                1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
                5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
                9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
            }
            
            rango_mes_siguiente = f"{primer_dia_siguiente.day:02d} de {meses_espanol[primer_dia_siguiente.month]} {primer_dia_siguiente.year} al {ultimo_dia_siguiente.day:02d} de {meses_espanol[ultimo_dia_siguiente.month]} {ultimo_dia_siguiente.year}"
            
            # Calcular 1 mes antes de la fecha de vigencia
            fecha_vigencia = info.fecha_terminacion
            if fecha_vigencia:
                fecha_un_mes_antes_vigencia = fecha_vigencia - relativedelta(months=1)
                mes_antes_vigencia = f"{fecha_un_mes_antes_vigencia.day:02d} de {meses_espanol[fecha_un_mes_antes_vigencia.month]} {fecha_un_mes_antes_vigencia.year}"
            else:
                duracion_meses = int(num_vigencia)
                fecha_fin_vigencia = fecha_celebracion + relativedelta(months=duracion_meses)
                fecha_un_mes_antes_vigencia = fecha_fin_vigencia - relativedelta(months=1)
                mes_antes_vigencia = f"{fecha_un_mes_antes_vigencia.day:02d} de {meses_espanol[fecha_un_mes_antes_vigencia.month]} {fecha_un_mes_antes_vigencia.year}"
            
            context = {
                'info': info,
                'renta_texto': renta_texto,
                'deposito_texto': deposito_texto,
                'superficie_texto': superficie_texto,
                'rentas_anticipadas': rentas_anticipadas,
                'anticipadas_texto': anticipadas_texto,
                'num_vigencia': num_vigencia,
                'nom_paquete': nom_paquete,
                'rango_mes_siguiente': rango_mes_siguiente,
                'mes_antes_vigencia': mes_antes_vigencia,
                "testigo1": testigo1,
                "testigo2": testigo2
            }
            
            template = 'home/contrato_ga_sa.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando contrato Garza Sada interno: {e}")
            raise e

    def _generar_poliza_garzasada_interno(self, info):
        """Función interna para generar el PDF de la póliza de Garza Sada"""
        try:
            print("Generando póliza Garza Sada interno...")
            
            # Generar el número de contrato
            arrendatario = info.arrendatario.nombre_arrendatario
            primera_letra = arrendatario[0].upper()
            ultima_letra = arrendatario[-1].upper()
            
            year = info.fecha_celebracion.strftime("%g")
            month = info.fecha_celebracion.strftime("%m")
            
            nom_contrato = f"AFY{month}{year}CX51{info.id}CA{primera_letra}{ultima_letra}"
            
            # Obtener renta y costo poliza para letra
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            context = {
                'info': info, 
                'renta_texto': renta_texto, 
                'nom_contrato': nom_contrato
            }
            
            template = 'home/poliza_garzasada.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando póliza Garza Sada interno: {e}")
            raise e

    def _generar_pagare_garzasada_interno(self, info, pagare_distinto="No", cantidad_pagare="0"):
        """Función interna para generar el PDF del pagaré de Garza Sada"""
        try:
            print("Generando pagaré Garza Sada interno...")
            locale.setlocale(locale.LC_ALL, "es_MX.utf8")
            
            # Procesar cantidad del pagaré
            if pagare_distinto == "Si":
                if "." not in str(cantidad_pagare):
                    cantidad_decimal = "00"
                    cantidad_letra = num2words(int(cantidad_pagare), lang='es')
                else:
                    cantidad_completa = str(cantidad_pagare).split(".")
                    cantidad_pagare = cantidad_completa[0]
                    cantidad_decimal = cantidad_completa[1]
                    cantidad_letra = num2words(int(cantidad_pagare), lang='es')
            else:
                cantidad_pagare = 0
                cantidad_decimal = "00"
                cantidad_letra = num2words(0, lang='es')
            
            # Definir la fecha inicial
            fecha_inicial = info.fecha_celebracion
            dia = fecha_inicial.day
            
            # Definir la duración en meses
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            
            # Calcular la fecha final
            fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
            
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            fecha_temp = fecha_inicial
            
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_temp < fecha_final:
                nombre_mes = fecha_temp.strftime("%B")
                fechas_iteradas.append((nombre_mes.capitalize(), fecha_temp.year))
                fecha_temp += relativedelta(months=1)
            
            # Obtener la renta para pasarla a letra
            if "." not in str(info.renta):
                number = int(info.renta)
                renta_decimal = "00"
                text_representation = num2words(number, lang='es').capitalize()
            else:
                renta_completa = str(info.renta).split(".")
                renta_valor = renta_completa[0]
                renta_decimal = renta_completa[1]
                text_representation = num2words(int(renta_valor), lang='es').capitalize()
            
            context = {
                'info': info, 
                'dia': dia,
                'lista_fechas': fechas_iteradas, 
                'text_representation': text_representation, 
                'duracion_meses': duracion_meses, 
                'pagare_distinto': pagare_distinto,
                'cantidad_pagare': cantidad_pagare, 
                'cantidad_letra': cantidad_letra,
                'cantidad_decimal': cantidad_decimal, 
                'renta_decimal': renta_decimal
            }
            
            template = 'home/pagare_garzasada.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando pagaré Garza Sada interno: {e}")
            raise e
        
#////////////////INICIO INTEGRACION ZAPSIGN/////////////////////    
    
    def _construir_firmantes_garzasada(self, singer):
        """Construye la lista de firmantes para contratos Garza Sada"""
        firmantes = []
        
        # Firmante 0: Fraterna (representa a Garza Sada)
        firmantes.append({
            "name": "FRATERNA ADMINISTRADORA DE PROYECTOS, S.A. DE C.V.'' REPRESENTADA POR CARLOS MANUEL PADILLA SILVA",
            "phone_country": "52",
            # TODO: Agregar email y teléfono del representante de Garza Sada
        })
        
        # Firmante 1: Arrendatario
        firmantes.append({
            "name": singer["nombre_arrendatario"],
            "email": singer["correo_arrendatario"],
            "phone_country": "52",
            "phone_number": singer["celular_arrendatario"],
            "send_automatic_email": True,
            "send_automatic_whatsapp": False,
        })
        
        # Firmante 2: Obligado solidario (solo si existe)
        nombre_obligado = singer.get("nombre_obligado", "").strip()
        if nombre_obligado:
            firmantes.append({
                "name": nombre_obligado,
                "email": singer.get("correo_obligado", singer["correo_arrendatario"]),
                "phone_country": "52",
                "phone_number": singer.get("celular_obligado", singer["celular_arrendatario"]),
                "send_automatic_email": True,
                "send_automatic_whatsapp": False,
            })
        
        # Firmante final: Jonathan Guadarrama
        firmantes.append({
            "name": "JONATHAN GUADARRAMA SALGADO",
            "email": "genaro.guadarrama@arrendify.com",
            "phone_country": "52",
            "phone_number": "5531398629",
            "send_automatic_email": True,
        })
        
        return firmantes

    def build_payload_to_zapsign(self, contrato_data):
        """ Datos del contrado: contrato_data = {"id", "filename", "base64_pfd", "residente"}
            Aquí armamos el payload que se va enviar para la solicitud
            de creacion del documento 

        """
        data = contrato_data
        singer = data["arrendatario"]
        brand_logo = "https://pagosprueba.s3.us-east-1.amazonaws.com/ZapSign/logo-contratodearrendamiento.webp"

        payload = {
            "base64_pdf": data["base64_pdf"],
            "name": data["filename"],
            "signers": self._construir_firmantes_garzasada(singer),
            "lang": "es",
            "disable_signer_emails": False,
            "brand_logo": brand_logo,
            "brand_primary_color": "#672584",
            "brand_name": "Arrendify",
            "folder_path": "/GARZASADA",
            "created_by": "juridico.arrendify1@gmail.com",
            "signature_order_active": False,
            "reminder_every_n_days": 0,
            "allow_refuse_signature": True,
            "disable_signers_get_original_file": False
        }
        
        return payload
    
    def armar_payload_posiciones_firma(self, signer_tokens, total_paginas, arrendatario):
        rubricas = []

        # Calcular offsets por sección
        offsets = {}
        acumulador = 0
        for nombre, paginas in total_paginas.items():
            offsets[nombre] = acumulador
            acumulador += paginas

        # Definir posiciones por sección
        posiciones_por_seccion = {
            "comodato": [
                (0, 5.0, 5.0, 0),
                (0, 5.0, 75.0, 1),
                (1, 13.0, 18.0, 0),
                (1, 13.0, 65.0, 1),
                (2, 5.0, 75.0, 1),
                (3, 26.5, 18.0, 1)
            ],
            "arrendamiento": [],
            "manual": [],
            "poliza": [],
            "pagares": []
        }

        # ARRRENDAMIENTO: [0, 1, 2] en cada página (izq-centro-der)
        arr_total = total_paginas["arrendamiento"]
        for i in range(arr_total):
            posiciones_por_seccion["arrendamiento"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 2)
            ])

        # MANUAL: [1, 2] más separados en la parte baja derecha
        man_total = total_paginas["manual"]
        for i in range(man_total):
            posiciones_por_seccion["manual"].extend([
                (i, 5.0, 55.0, 1),
                (i, 5.0, 80.0, 2)
            ])

        # POLIZA: [0, 1, 3] (izq-centro-der)
        pol_total = total_paginas["poliza"]
        for i in range(pol_total):
            posiciones_por_seccion["poliza"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 3)
            ])

        # PAGARES: firmantes condicionales según residente.aval y edad
        pag_total = total_paginas["pagares"]

        aval = arrendatario.get("aval", "").strip()
        edad = int(arrendatario.get("edad", 0))

        for i in range(pag_total):
            # Firmante 2 (residente) siempre firma
            posiciones_por_seccion["pagares"].append((i, 16.0, 55.0, 2))

            # Si la condición se cumple, también firma el firmante 1 (arrendatario)
            if aval == "Si" and edad >= 18:
                posiciones_por_seccion["pagares"].append((i, 33.0, 55.0, 1))

        # Construcción final del payload con offset aplicado
        for seccion, posiciones in posiciones_por_seccion.items():
            offset = offsets[seccion]
            for page, bottom, left, signer_index in posiciones:
                if signer_index < len(signer_tokens):
                    rubricas.append({
                        "page": page + offset,
                        "relative_position_bottom": bottom,
                        "relative_position_left": left,
                        "relative_size_x": 19.55,
                        "relative_size_y": 9.42,
                        "type": "signature",
                        "signer_token": signer_tokens[signer_index]
                    })

        return {"rubricas": rubricas}


    def subir_documento_a_zapsign(self, contrato_data):
        # Armar payload para subir documento
        payload = self.build_payload_to_zapsign(contrato_data)

        headers = {
            'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}',
            'Content-Type': 'application/json'
        }
        print("Solicitando documento a Zapsign")

        url = f'{API_URL_ZAPSIGN}docs/'

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()

            try:
                response_data = response.json()
            except ValueError:
                print("⚠️ La respuesta no está en formato JSON.")
                response_data = {"raw_response": response.text}

            # Extraer token del documento
            doc_token = response_data.get("token")

            # Extraer tokens de firmantes
            signer_tokens = [s.get("token") for s in response_data.get("signers", []) if s.get("token")]

            if not doc_token:
                raise ValueError("No se pudo obtener el token del documento desde la respuesta.")

            print("Token del documento generado:", doc_token)
            print("ID del contrato que se va a actualizar:", contrato_data["id"])

            # Guardar token en la base de datos
            info = self.queryset.filter(id=contrato_data["id"]).first()
            if not info:
                raise ValueError("Contrato no encontrado en la base de datos.")

            info.token = doc_token
            info.save()
            print("Token guardado exitosamente en la base de datos.")            

            # Comportamiento configurable: si contrato_data incluye "_omit_place"=True,
            # NO se colocan rúbricas aquí (se hará después con posiciones visuales).
            do_place = not contrato_data.get("_omit_place", False)
            if do_place:
                # Armar y enviar payload de rúbricas (layout por defecto actual)
                rubricas_payload = self.armar_payload_posiciones_firma(signer_tokens, contrato_data["total_paginas"], contrato_data["arrendatario"])
                posicionar_url = f'{API_URL_ZAPSIGN}docs/{doc_token}/place-signatures/'
                print("📤 Enviando posiciones de firmas (layout por defecto)...")

                posicionar_response = requests.post(
                    posicionar_url,
                    headers=headers,
                    json=rubricas_payload,
                    timeout=60
                )

                posicionar_response.raise_for_status()
                print("Posiciones de firmas configuradas correctamente.")

                return {
                    "payload": payload,
                    "doc_token": doc_token,
                    "zapsign_new_doc": response_data,
                    "rubricas_payload": rubricas_payload,
                    "rubricas_response": posicionar_response.text or "Sin contenido"
                }

            # Si omitimos place-signatures, devolvemos solo datos del documento creado
            return {
                "payload": payload,
                "doc_token": doc_token,
                "zapsign_new_doc": response_data,
            }

        except requests.exceptions.Timeout:
            print("Error: Tiempo de espera agotado al comunicar con ZapSign.")
        except requests.exceptions.RequestException as e:
            print(f"Error en la solicitud a Zap-Sign: {e}")
        except Exception as e:
            print(f"Error inesperado en subir documento zapsign: {e}")

        return None

    def armar_payload_posiciones_custom(self, positions, signer_tokens):
        """Construye payload de rúbricas desde posiciones personalizadas del frontend."""
        rubricas = []
        if not isinstance(positions, list):
            return {"rubricas": rubricas}
        for pos in positions:
            try:
                page = int(pos.get("page", 0))
                bottom = float(pos.get("bottom", 0))
                left = float(pos.get("left", 0))
                size_x = float(pos.get("size_x", 19.55))
                size_y = float(pos.get("size_y", 9.42))
                signer_index = int(pos.get("signer_index", 0))
                if signer_index < 0 or signer_index >= len(signer_tokens):
                    continue
                rubricas.append({
                    "page": page,
                    "relative_position_bottom": bottom,
                    "relative_position_left": left,
                    "relative_size_x": size_x,
                    "relative_size_y": size_y,
                    "type": "signature",
                    "signer_token": signer_tokens[signer_index]
                })
            except Exception:
                continue
        return {"rubricas": rubricas}

    def posicionar_y_generar_urls_gs(self, request, *args, **kwargs):
        """Crea/obtiene doc ZapSign y aplica posiciones.
        - Si NO hay PDF cargado: usa posicionamiento automático (como Fraterna)
        - Si SÍ hay PDF cargado: usa posicionamiento visual del frontend
        Acceso: username == 'GarzaSada' o staff."""
        try:
            user_session = request.user
            if not (user_session.is_staff or getattr(user_session, "username", "") == "GarzaSada"):
                return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

            data = request.data or {}
            contrato_id = data.get("contrato_id")
            arr_cto = data.get("arrendatario_contrato")
            positions = data.get("positions", [])
            doc_tipo = data.get("doc_tipo", "contrato")
            print(f"📥 Datos recibidos: contrato_id={contrato_id}, doc_tipo={doc_tipo}, positions={len(positions)}")
            
            if not contrato_id:
                return Response({"error": "contrato_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

            info = self.queryset.filter(id=contrato_id).first()
            if not info:
                return Response({"error": "Contrato no encontrado"}, status=status.HTTP_404_NOT_FOUND)
            
            print(f"✅ Contrato encontrado: ID={info.id}, Arrendatario={info.arrendatario.nombre_arrendatario if info.arrendatario else 'None'}")

            # Verificar si hay PDF cargado
            tiene_pdf_cargado = bool(info.contrato_pdf_b64)
            print(f"{'✅ PDF cargado detectado' if tiene_pdf_cargado else '⚠️ No hay PDF cargado - usará generación automática'}")

            doc_token = getattr(info, "token", None)
            if not doc_token:
                print("📄 Creando documento en ZapSign...")
                
                # Preparar PDF
                if tiene_pdf_cargado:
                    print("📄 Usando PDF cargado por el usuario")
                    pdf_bytes = base64.b64decode(info.contrato_pdf_b64)
                    total_paginas = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
                else:
                    print("🔨 Generando PDF automáticamente")
                    if not info.arrendatario:
                        return Response({"error": "El contrato no tiene arrendatario asociado"}, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Generar según tipo de documento
                    if doc_tipo == "paquete":
                        testigo1 = data.get("testigo1", "Angelina Castillo González")
                        testigo2 = data.get("testigo2", "Marcelo André Trujillo Moncada")
                        pagare_distinto = data.get("pagare_distinto", "No")
                        cantidad_pagare = data.get("cantidad_pagare", "")
                        
                        # Generar paquete completo
                        pdf_contrato = self._generar_contrato_garzasada_interno(info, testigo1=testigo1, testigo2=testigo2)
                        pdf_poliza = self._generar_poliza_garzasada_interno(info)
                        pdf_pagare = self._generar_pagare_garzasada_interno(info, pagare_distinto=pagare_distinto, cantidad_pagare=cantidad_pagare)
                        
                        # Fusionar PDFs
                        from PyPDF2 import PdfMerger
                        merger = PdfMerger()
                        merger.append(io.BytesIO(pdf_contrato))
                        merger.append(io.BytesIO(pdf_poliza))
                        merger.append(io.BytesIO(pdf_pagare))
                        
                        output = io.BytesIO()
                        merger.write(output)
                        merger.close()
                        pdf_bytes = output.getvalue()
                        
                        # Calcular páginas por sección
                        total_paginas = {
                            "arrendamiento": len(PdfReader(io.BytesIO(pdf_contrato)).pages),
                            "poliza": len(PdfReader(io.BytesIO(pdf_poliza)).pages),
                            "pagares": len(PdfReader(io.BytesIO(pdf_pagare)).pages),
                            "manual": 0,
                            "comodato": 0
                        }
                    else:
                        testigo1 = data.get("testigo1", "Angelina Castillo González")
                        testigo2 = data.get("testigo2", "Marcelo André Trujillo Moncada")
                        pdf_bytes = self._generar_contrato_garzasada_interno(info, testigo1=testigo1, testigo2=testigo2)
                        total_paginas = {
                            "arrendamiento": len(PdfReader(io.BytesIO(pdf_bytes)).pages),
                            "poliza": 0,
                            "pagares": 0,
                            "manual": 0,
                            "comodato": 0
                        }
                    
                    print(f"✅ PDF generado: {len(pdf_bytes)} bytes")

                nombre_archivo = f"Contrato Garza Sada - {info.arrendatario.nombre_arrendatario}"
                base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                
                if not arr_cto:
                    return Response({"error": "arrendatario_contrato es requerido"}, status=status.HTTP_400_BAD_REQUEST)
                
                # Configurar contrato_data según si hay PDF cargado o no
                contrato_data = {
                    "id": contrato_id,
                    "filename": nombre_archivo,
                    "base64_pdf": base64_pdf,
                    "arrendatario": arr_cto,
                    "total_paginas": total_paginas if not tiene_pdf_cargado else len(PdfReader(io.BytesIO(pdf_bytes)).pages),
                    "_omit_place": tiene_pdf_cargado,  # Si hay PDF cargado, omitir posicionamiento automático
                }
                
                creado = self.subir_documento_a_zapsign(contrato_data)
                if not creado or not creado.get("doc_token"):
                    return Response({"error": "No fue posible crear el documento en ZapSign"}, status=status.HTTP_502_BAD_GATEWAY)
                doc_token = creado["doc_token"]
                info.refresh_from_db()
                
                # Si NO hay PDF cargado, las posiciones ya se aplicaron automáticamente
                if not tiene_pdf_cargado:
                    print("✅ Posiciones automáticas ya aplicadas")
                    return Response({
                        "doc_token": doc_token,
                        "message": "Documento creado con posicionamiento automático",
                        "signers": creado.get("zapsign_new_doc", {}).get("signers", [])
                    }, status=status.HTTP_200_OK)

            # Si llegamos aquí, hay PDF cargado y necesitamos aplicar posiciones del frontend
            print("🎯 Aplicando posiciones del frontend...")
            
            # Obtener tokens de firmantes del doc en ZapSign
            url_doc = f"{API_URL_ZAPSIGN}docs/{doc_token}/"
            headers = {'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'}
            resp = requests.get(url_doc, headers=headers, timeout=30)
            if resp.status_code != 200:
                return Response({"error": "Error al consultar documento ZapSign", "status_code": resp.status_code, "response": resp.text}, status=resp.status_code)
            try:
                doc_json = resp.json()
            except ValueError:
                return Response({"error": "Respuesta de ZapSign no es JSON"}, status=status.HTTP_502_BAD_GATEWAY)
            
            # Extraer información de los firmantes
            signers = doc_json.get("signers", [])
            signer_tokens = [s.get("token") for s in signers if s.get("token")]
            
            # Obtener nombres y emails de los firmantes
            signers_info = []
            for signer in signers:
                signers_info.append({
                    "token": signer.get("token"),
                    "name": signer.get("name"),
                    "email": signer.get("email"),
                    "status": signer.get("status"),
                    "sign_url": signer.get("sign_url")
                })
            
            print(f"👥 Firmantes encontrados: {[s['name'] for s in signers_info]}")
            
            # Aplicar posiciones del frontend
            rubricas_payload = self.armar_payload_posiciones_custom(positions, signer_tokens)

            posicionar_url = f"{API_URL_ZAPSIGN}docs/{doc_token}/place-signatures/"
            pos_resp = requests.post(posicionar_url, headers=headers, json=rubricas_payload, timeout=60)
            if pos_resp.status_code not in (200, 201, 204):
                return Response({"error": "Error al colocar firmas", "status_code": pos_resp.status_code, "response": pos_resp.text}, status=pos_resp.status_code)

            return Response({
                "doc_token": doc_token,
                "signers": signers_info,
                "rubricas_payload": rubricas_payload,
                "zapsign_place_response": pos_resp.text or "Sin contenido"
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Error en posicionar_y_generar_urls_gs línea {exc_tb.tb_lineno}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def posicionar_sobre_existente_gs(self, request, *args, **kwargs):
        """Aplica posiciones sobre documento existente en ZapSign.
        Acceso: username == 'GarzaSada' o staff."""
        try:
            user_session = request.user
            if not (user_session.is_staff or getattr(user_session, "username", "") == "GarzaSada"):
                return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

            data = request.data or {}
            contrato_id = data.get("contrato_id")
            positions = data.get("positions", [])
            if not contrato_id:
                return Response({"error": "contrato_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

            info = self.queryset.filter(id=contrato_id).first()
            if not info or not getattr(info, "token", None):
                return Response({"error": "Contrato o token no encontrado"}, status=status.HTTP_404_NOT_FOUND)

            doc_token = info.token
            url_doc = f"{API_URL_ZAPSIGN}docs/{doc_token}/"
            headers = {'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'}
            resp = requests.get(url_doc, headers=headers, timeout=30)
            if resp.status_code != 200:
                return Response({"error": "Error al consultar documento ZapSign", "status_code": resp.status_code, "response": resp.text}, status=resp.status_code)
            try:
                doc_json = resp.json()
            except ValueError:
                return Response({"error": "Respuesta de ZapSign no es JSON"}, status=status.HTTP_502_BAD_GATEWAY)
            signer_tokens = [s.get("token") for s in doc_json.get("signers", []) if s.get("token")]
            rubricas_payload = self.armar_payload_posiciones_custom(positions, signer_tokens)

            posicionar_url = f"{API_URL_ZAPSIGN}docs/{doc_token}/place-signatures/"
            pos_resp = requests.post(posicionar_url, headers=headers, json=rubricas_payload, timeout=60)
            if pos_resp.status_code not in (200, 201, 204):
                return Response({"error": "Error al colocar firmas", "status_code": pos_resp.status_code, "response": pos_resp.text}, status=pos_resp.status_code)

            return Response({
                "doc_token": doc_token,
                "rubricas_payload": rubricas_payload,
                "zapsign_place_response": pos_resp.text or "Sin contenido"
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Error en posicionar_sobre_existente_gs línea {exc_tb.tb_lineno}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#////////////////FIN INTEGRACION ZAPSIGN/////////////////////        
        
        
    def renovar_contrato_garzasada(self, request, *args, **kwargs):
        try:
            print("Renovacion de contrato Garza Sada")
            print("Data ====>",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("ID ====>",instance.id)
            print(instance.__dict__)
            #Mandar Whats con lo datos del contrato a Miri
            
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_garzasada.objects.all().get(contrato_id = instance.id)
            print("Proceso ====>",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            print("Contrato renovado correctamente....✅")
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)


class InvestigacionGarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Arrendatarios_garzasada.objects.all()
    serializer_class = Arrentarios_GarzaSadaSerializers
   
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        if user_session.username == "Arrendatario1" or user_session.username == "Legal" or  user_session.username == "Investigacion" or user_session.username == "AndresMtzO" or user_session.username == "MIRIAM" or user_session.username == "jon_admin" or user_session.username == "SUArrendify" or user_session.username == "Becarios":
            print("USUARIO STAFF")
            qs = request.GET.get('nombre')     
            try:
                if qs:
                    inquilino = Arrendatarios_garzasada.objects.all().order_by('-id')
                    serializer = Arrentarios_GarzaSadaSerializers(inquilino, many=True)                    
                    return Response(serializer.data)
                    
                else:
                        print("Listar Investigacion Garza Sada")
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
    

    def update(self, request, *args, **kwargs):
        pass
        
    def retrieve(self, request, pk=None, *args, **kwargs):
        user_session = request.user
        try:
            print("Entrando a retrieve")
            modelos = Investigacion.objects.all() #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
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
        print("Enviar Investigacion Garza Sada ====>")
        print("PDF ====>",archivo)
        print("Estatus Investigacion ====>",estatus)
        print("DATA ====>",info.__dict__)
        print("ID USUARIO ====>",info.user_id)
   
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
            print("Destinatario ====> ",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
            #Destino=['desarrolloarrendify@gmail.com']
            #Destino=['juridico.arrendify1@gmail.com']
            asunto = f"Resultado Investigación Prospecto {info.nombre_arrendatario}"
            
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
            print("Creacion de Mail ====>")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("Mail Creado ====>")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("TLS ====>")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("LOGIN ====>")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("CORREO ENVIADO ====>")
            return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
    def enviar_archivo_semillero(self, archivo, info, estatus):
        #cuando francis este registrado regresar todo como estaba
        print("Enviar Archivo Investigacion Semillero ====>")
        print("PDF ====>",archivo)
        print("Estatus Investigacion ====>",estatus)
        print("INFO Investigacion ====>",info.__dict__)
        print("ID USUARIO ====>",info.user_id)
   
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            destinatario = info.correo_arrendatario
            pdf_html = contenido_pdf_aprobado_semillero(info,estatus)
            print("Destinatario ====>",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
            #Destino=['desarrolloarrendify@gmail.com']
            #Destino=['juridico.arrendify1@gmail.com']
            asunto = f"Resultado Investigación Prospecto {info.nombre_arrendatario}"
            
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
            print("Creacion de Mail ====>")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("Mail Creado ====>")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("TLS ====>")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("LOGIN ====>")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("CORREO ENVIADO ====>")
            return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
        
    def aprobar_residente_semillero(self, request, *args, **kwargs):
        try:
            print("Aprobar Prospecto semillero")
            #Consulata para obtener el inquilino y establecemos fecha de hoy
            today = date.today().strftime('%d/%m/%Y')
            req_dat = request.data
            info = Arrendatarios_semillero.objects.filter(id = req_dat["id"]).first()
            print("DATA ====>",info.__dict__)   
                 
                 
            redes_negativo = req_dat.get("redes_negativo")
            print("DATA ====>",req_dat)
            print("ID DATA ====>", req_dat["id"])
            print("")
            print("Arrendatario ====>",info.nombre_arrendatario)       
            print("Diccionario ====>",info.__dict__)
            print("")                                                                 
            print("")
            print("Redes Negativas ====>", redes_negativo)            
            print("")
            
            requisitos = ['referencia1', 'referencia2', 'referencia3'] # una lista para verificar las referencias 1,2 y 3
            presentes = [req for req in requisitos if req in request.data and request.data[req]]
            print("Referencias presentes ====>",presentes)
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
                        print("Clave ====>", clave)
                        print("Frase ====>", frase)
                        print("Comentarios Redes ====>", redes_comentarios)
                    elif valor == "Si" and clave not in conductas:
                        print(f"No hay una frase definida para la clave: {clave}")
            else:
                redes_comentarios = "no tengo datos"
                print("Comentarios Redes ====>",redes_comentarios)
        
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
            print("ANTECEDENTES ====>",antecedentes)
            if antecedentes:
                # del antecedentes["civil_mercantil_demandado"] 
                print("CIVIL O FAMILIAR ====>",antecedentes)
                if antecedentes.get("civil_mercantil_demandado") and len(antecedentes) == 1: #tiene antecedentes de civil o de familiar? los excentamos si no delincuente
                    print("Historial Crediticio ====>")
                    #evaluar el historial crediticio  
                    
                    if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                        print("Rechazado ====>")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                    
                    elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                        print("Aprobado ====>")
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                        status = "Aprobado"
                        motivo = "No hay motivo de rechazo"
                    
                    elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                        print("A Considerar ====>")
                        conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                        status = "Aprobado_pe"
                        motivo = "1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                        
                elif antecedentes.get("antecedentes_aval_si") and len(antecedentes) == 1: #tiene antecedentes de aval
                        print("AVAL CON ANTECEDENTES")
                        print("Solicitar cambio Aval")
                        
                        if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                            print("Rechazado ====>")
                            conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                            status = "Declinado"
                            motivo = f"1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                            print("Aprobado ====>")
                            conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                            status = "Aprobado"
                            motivo =  f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                            print("A Considerar ====>")
                            conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                            status = "Aprobado_pe"
                            motivo = f"1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse.\n3.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                    
                elif antecedentes and tipo_score_pp == "Malo" or antecedentes and tipo_score_ingreso == "Malo":
                        print("Rechazado ====>")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."    
                        
                else:
                    print("Antecedentes")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."
            else: #No tiene Antecedentes
                
                #evaluar el historial crediticio  
                if tipo_score_pp == "Malo":
                    print("Rechazado ====>")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Buro: Se cuenta con un buro con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                
                elif tipo_score_ingreso == "Malo":
                    print("Rechazado ====>")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Ingresos: Los ingresos comprobados no son suficientes para garantizar el cumplimiento de sus obligaciones financieras."
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                    print("Aprobado ====>")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = ""   
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente" and antecedentes.get("antecedentes_aval_si") and antecedentes != None :
                    print("Aprobado ====>")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos." 
                
                elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                    print("A Considerar ====>")
                    conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                    status = "Aprobado_pe"
                    motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                
                 
                    
            context = {'info': info, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                       "redes_comentarios":redes_comentarios, 'referencias':referencias, 'antecedentes':antecedentes,'status':status, 'conclusion':conclusion, 'motivo':motivo}
            
            template = 'home/report_semillero.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            print("Generando PDF")
            pdf_file = HTML(string=html_string).write_pdf()

            # #aqui hacia abajo es para enviar por email
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
        
            print("DATOS ARCHIVO ====>",context)
            correo = self.enviar_archivo_semillero(archivo, context["info"], context["status"])
            print("CORREO ====>",correo)
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
        
        
########################## G A R Z A  S A D A ######################################