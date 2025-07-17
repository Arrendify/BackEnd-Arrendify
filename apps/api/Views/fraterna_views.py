from rest_framework import viewsets
from rest_framework.response import Response
from ...home.models import *
from ..serializers import *
from rest_framework import status
from ...accounts.models import CustomUser
User = CustomUser
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponse

#s3
import boto3
from botocore.exceptions import ClientError
from botocore.exceptions import NoCredentialsError
from django.db.models import Q
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
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
import io
import requests
from pypdf import PdfReader, PdfWriter
from datetime import datetime as dt
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
            
           elif user_session.rol == "Inmobiliaria":  
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
    
    def generar_paquete_completo_fraterna(self, request, *args, **kwargs):
        """
        Genera un PDF combinado con todos los documentos de Fraterna en el siguiente orden:
        1. Comodato
        2. Contrato
        3. Manual UTO (desde AWS bucket)
        4. Póliza
        5. Pagares
        """
        try:
            print("Generando paquete completo Fraterna")
            
            # Activamos la librería de locale para obtener el mes en español
            locale.setlocale(locale.LC_ALL, "es_MX.utf8")
            
            # Manejar tanto request.data como entero directo o diccionario
            if isinstance(request.data, dict):
                id_paq = request.data["id"]
                pagare_distinto = request.data.get("pagare_distinto", "No")
                cantidad_pagare = request.data.get("cantidad_pagare", "0")
            else:
                # Si request.data es un entero directamente
                id_paq = request.data
                pagare_distinto = "No"
                cantidad_pagare = "0"
            
            print(f"ID del paquete: {id_paq}")
            print(f"Pagare distinto: {pagare_distinto}")
            
            # Obtener información del contrato
            info = self.queryset.filter(id=id_paq).first()
            if not info:
                return Response({'error': 'Contrato no encontrado'}, status=status.HTTP_404_NOT_FOUND)
            
            # Crear un writer para combinar los PDFs
            pdf_writer = PdfWriter()
            
            # 1. GENERAR Y AGREGAR COMODATO
            print("Generando Comodato...")
            comodato_pdf = self._generar_comodato_interno(info)
            comodato_reader = PdfReader(io.BytesIO(comodato_pdf))
            for page in comodato_reader.pages:
                pdf_writer.add_page(page)
            
            # 2. GENERAR Y AGREGAR CONTRATO
            print("Generando Contrato...")
            contrato_pdf = self._generar_contrato_interno(info)
            contrato_reader = PdfReader(io.BytesIO(contrato_pdf))
            for page in contrato_reader.pages:
                pdf_writer.add_page(page)
            
            # 3. DESCARGAR Y AGREGAR MANUAL UTO DESDE AWS
            print("Descargando Manual UTO desde AWS...")
            manual_url = "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/ManualUtower.pdf"
            try:
                response_manual = requests.get(manual_url, timeout=30)
                response_manual.raise_for_status()
                manual_reader = PdfReader(io.BytesIO(response_manual.content))
                for page in manual_reader.pages:
                    pdf_writer.add_page(page)
                print("Manual UTO agregado exitosamente")
            except Exception as e:
                print(f"Error al descargar manual UTO: {e}")
                # Continuar sin el manual si hay error
            
            # 4. GENERAR Y AGREGAR PÓLIZA
            print("Generando Póliza...")
            poliza_pdf = self._generar_poliza_interno(info)
            poliza_reader = PdfReader(io.BytesIO(poliza_pdf))
            for page in poliza_reader.pages:
                pdf_writer.add_page(page)
            
            # 5. GENERAR Y AGREGAR PAGARÉS
            print("Generando Pagarés...")
            pagare_pdf = self._generar_pagare_interno(info, pagare_distinto, cantidad_pagare)
            pagare_reader = PdfReader(io.BytesIO(pagare_pdf))
            for page in pagare_reader.pages:
                pdf_writer.add_page(page)
            
            # Crear el PDF final combinado
            output_pdf = io.BytesIO()
            pdf_writer.write(output_pdf)
            output_pdf.seek(0)
            
            # Generar nombre del archivo con fecha
            fecha_actual = dt.now().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"Paquete_Completo_Fraterna_{info.residente.nombre_arrendatario}_{fecha_actual}.pdf"
            
            # Devolver el PDF combinado
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
            response.write(output_pdf.getvalue())
            
            print("Paquete completo generado exitosamente")
            return response
            
        except Exception as e:
            print(f"Error en generar_paquete_completo_fraterna: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
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
        

#////////////////////////////////////SEMILLERO PURISIMA////////////////////////////////////////////
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
            print("rd", request.data)
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
            print("rd", request.data)
            id_paq = request.data["id"]
            testigo1 = request.data["testigo1"]
            testigo2 = request.data["testigo2"]
            print(testigo1)
            print(testigo2)
            print("el id que llega", id_paq)
            info = self.queryset.filter(id=id_paq).first()
            print(info.__dict__)
            
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

            print("vamos agenerar el codigo")
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            if info.id < 9:
                info.id = f"0{info.id}"
                print("")
            print("fec", fec)

            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            print("dia", dia)
            print("mes", mes)
            print("año", anio)
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" + f"{info.id}" + "CA" + na
            print("paqueton", nom_paquete.upper())

            context = {
                'info': info,
                'renta_texto': renta_texto,
                'num_vigencia': num_vigencia,
                'nom_paquete': nom_paquete,
                "testigo1": testigo1,
                "testigo2": testigo2
            }

            template = 'home/contrato_arr_frat.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("finalizado")

            return HttpResponse(response, content_type='application/pdf')

        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST) 
        
    def renovar_contrato_semillero(self, request, *args, **kwargs):
        try:
            print("Renovar el contrato pa")
            print("Request",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("mi id es: ",instance.id)
            print(instance.__dict__)
            #Mandar Whats con lo datos del contrato a Miri
            
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


class InvestigacionSemillero(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Arrendatarios_semillero.objects.all()
    serializer_class = Arrentarios_semilleroSerializers
   
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        if user_session.username == "Arrendatario1" or user_session.username == "Legal" or  user_session.username == "Investigacion" or user_session.username == "AndresMtzO" or user_session.username == "MIRIAM" or user_session.username == "jon_admin" or user_session.username == "SUArrendify" or user_session.username == "Becarios":
            print("Si eres el elegido")
            qs = request.GET.get('nombre')     
            try:
                if qs:
                    inquilino = Arrendatarios_semillero.objects.all().order_by('-id')
                    serializer = Arrentarios_semilleroSerializers(inquilino, many=True)                    
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
    
    def enviar_archivo_semillero(self, archivo, info, estatus):
        #cuan(do francis este registrado regresar todo como estaba
        print("entre en el enviar archivo semillero")
        print("soy pdf content",archivo)
        print("soy status",estatus)
        print("soy info de investigacion",info.__dict__)
        print("info id",info.user_id)
   
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            destinatario = info.correo_arrendatario
            pdf_html = contenido_pdf_aprobado_semillero(info,estatus)
            print("destinatario normalito",destinatario)
            
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
    
        
    def aprobar_residente_semillero(self, request, *args, **kwargs):
        try:
            print("entrando en Aprobar prospecto semillero")
            #Consulata para obtener el inquilino y establecemos fecha de hoy
            today = date.today().strftime('%d/%m/%Y')
            req_dat = request.data
            info = Arrendatarios_semillero.objects.filter(id = req_dat["id"]).first()
            print("soy INFO",info.__dict__)   
                 
                 
            redes_negativo = req_dat.get("redes_negativo")
            print("request.data",req_dat)
            print("el id que llega", req_dat["id"])
            print("")
            print("soy la info del",info.nombre_arrendatario)       
            print(info.__dict__)
            print("")                                                                 
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
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
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
                            conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                            status = "Aprobado"
                            motivo =  f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
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
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = ""   
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente" and antecedentes.get("antecedentes_aval_si") and antecedentes != None :
                    print("aprobado imprimi la segunda conclusion")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos." 
                
                elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                    print("a considerar")
                    conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                    status = "Aprobado_pe"
                    motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                
                 
                    
            context = {'info': info, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                       "redes_comentarios":redes_comentarios, 'referencias':referencias, 'antecedentes':antecedentes,'status':status, 'conclusion':conclusion, 'motivo':motivo}
            
            template = 'home/report_semillero.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            print("Generando el pdf")
            pdf_file = HTML(string=html_string).write_pdf()

            # #aqui hacia abajo es para enviar por email
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
        
            print("antes de enviar_archivo",context)
            correo = self.enviar_archivo_semillero(archivo, context["info"], context["status"])
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