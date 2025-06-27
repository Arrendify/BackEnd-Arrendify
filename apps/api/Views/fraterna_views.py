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
from ..variables import aprobado_fraterna, renovacion_aviso_fraterna

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
            print(serializer)
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
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
            renta = int(info.renta)
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
            renta = int(info.renta)
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
            renta = int(info.renta)
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
            renta = int(info.renta)
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
            renta = int(info.renta)
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
            renta = int(info.renta)
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
            print("rd",request.data)
            id_paq = request.data["id"]
            testigo1 = request.data["testigo1"]
            testigo2 = request.data["testigo2"]
            print(testigo1)
            print(testigo2)
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)
            
            print("vamos a generar el codigo")    
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            if info.id < 9:
                info.id = f"0{info.id}"
                print("")
            print("fec",fec)
        
            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" +  f"{info.id}" + "CA" +  na 
            print("paqueton",nom_paquete.upper())    
            #obtenemos renta y costo poliza para letra
            renta = int(info.renta)
            print("la renta es:", renta)
            renta_texto = num2words(renta, lang='es').capitalize()
            if renta > 14999:
                #redondeamos el resultado para que no salga numeros decimales en la operacion de resultado, ya que al trabajar un int con un float se producen decimales para cubrir el resto de la operacion
                resultado = renta * 0.17
                valor_poliza = int(round(resultado, 2))
                print("resultado esperado",valor_poliza)
                
            else:
                valor_poliza = 2500
            poliza_texto = num2words(valor_poliza, lang='es').capitalize()
            
       
            context = {'info': info, 'renta_texto':renta_texto, 'nom_paquete':nom_paquete, 'valor_poliza':valor_poliza, 'poliza_texto':poliza_texto, "testigo1":testigo1, "testigo2":testigo2}
            template = 'home/poliza_semillero.html'
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
