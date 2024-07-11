from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from ....home.models import *
from ...serializers import *
from rest_framework.decorators import action


from rest_framework.response import Response

#intento de factorizacion 1

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework import viewsets


from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from rest_framework.decorators import action

#nuevo mod user
from ....accounts.models import CustomUser
User = CustomUser

#correo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from smtplib import SMTPException
from decouple import config

#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)

from rest_framework.authentication import TokenAuthentication

class ArrendadorViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    lookup_field = 'slug'
    queryset = Arrendador.objects.all()
    serializer_class = ArrendadorSerializer
    serializer_class_archivos = DocumentosArrendadorSerializer
        
    def list(self, request):
        user_session = self.request.user
        try:
            user_session = self.request.user
            if user_session.is_staff:
                # Crear una copia de los datos serializados
                print("soy staff en arrendador")
                serialized_data = self.serializer_class(self.queryset, many=True).data
                print("self.queryset",self.queryset)
               
                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['is_staff'] = True

                # Devolver la respuesta
                return Response(serialized_data)
            
            elif user_session.rol == "Inmobiliaria":  
                #tengo que buscar a los arrendadores que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de arrendadores propios y registrados por mis agentes
                arrendadores_a_cargo = Arrendador.objects.filter(user_id__in = agentes)
                arrendadores_mios = Arrendador.objects.filter(user_id = user_session)
                mios = arrendadores_a_cargo.union(arrendadores_mios)
                
                #busqueda de inquilino vinculado
                pertenece2 = Arrendador.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                pertenece = Arrendador.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                pertenece = pertenece.union(pertenece2)
                arrendador_all = mios.union(pertenece)
               
                print("Registrados por mi o por un agente directo", mios)
                print("Independientes vinculado(s) a un agente(s)", pertenece)
                print("Todos los arrendadores",arrendador_all)
               # print("inquilinos_all con ids",arrendador_all("id"))
                
                serializer = ArrendadorSerializer(arrendador_all, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                
                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['inmobiliaria'] = True
                    
                return Response(serialized_data)      
        
            elif user_session.rol == "Agente":  
                print("soy agente", user_session.first_name)
                agente_qs = Arrendador.objects.filter(user_id = user_session)
                print(agente_qs)
                pertenece = Arrendador.objects.filter(mi_agente_es__icontains = user_session.first_name)
                print(pertenece)
                arredores_a_cargo = agente_qs.union(pertenece)
                serializer = ArrendadorSerializer(arredores_a_cargo, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})
                
                for item in serialized_data:
                    item['agente'] = True
            
                return Response(serialized_data)
     
            else:
                # Listar muchos a muchos
                # optimizar esto
                # Obtener todos los inquilinos del usuario actual
                arrendadores_propios = self.queryset.filter(user_id = user_session)
                
                # Obtener todos los arrendadores amigos del usuario actual
                inquilinos_amigos = Inquilino.objects.all().filter(user_id = user_session)
            
                # Obtener inquilinos ligados a los arrendadores amigos
                arrendador_amigos = self.queryset.filter(amigo_arrendador__sender__in = inquilinos_amigos)
            
                # Combinar inquilinos propios e inquilinos amigos sin duplicados basados en el ID
                snippets = arrendadores_propios.union(arrendador_amigos)
                data_serializer = self.serializer_class(snippets, many=True)
                return Response(data_serializer.data)
                
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        user_session = self.request.user
        try:
            print("Llegando a create arrendador")
            # request.data['user'] = request.user.id
            arrendador_serializer = self.get_serializer(data=request.data) # Usa el serializer_class
            if arrendador_serializer.is_valid(raise_exception=True):
                arrendador_serializer.save(user = user_session)
                print("Guardado arrendador")
                arrendador = arrendador_serializer.instance
                # Cuando se crea un arrendador ,se crea un registro en validar arrendador
                # El cual servira para validar los documentos del arrendador
                validacion_arrendador = ValidacionArrendador(arrendador_validacion=arrendador)
                validacion_arrendador.user_id = request.user.id
                validacion_arrendador.save()

                return Response({'arrendador': arrendador_serializer.data, 'validacion_arrendador': validacion_arrendador.id}, status=status.HTTP_201_CREATED)
            else:
                print("Error al crear arrendador")
                return Response({'errors': arrendador_serializer.errors})
        except ValidationError as e:
            print(f"el error es: {e.detail}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'errors en el try': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error en el exept': str(e)}, status = status.HTTP_302_FOUND)
        
    
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            print("Entrando a retrieve")
            modelos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            arrendador = modelos.filter(slug=slug)
            if arrendador:
                arrendador_serializer = self.serializer_class(arrendador, many=True)
                # Agregar el campo 'is_staff'
                serialized_data = arrendador_serializer.data
                for item in serialized_data:
                    item['is_staff'] = True
                return Response(serialized_data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            print("edito arrendador ")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'errors': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
    def destroy (self,request, *args, **kwargs):
        try:
            print("Esta entrando a eliminar")
            arrendador = self.get_object()
            if arrendador:
                arrendador.delete()
                return Response({'message': 'Arrendador eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
    @action(detail=False, methods=['post'], url_path='create_documentos')
    def create_documentos (self, request, *args,**kwargs):
        try: 
            data = request.data
            print(data)
            print("Id_arrendador",  request.data.get('arrendador'))
            
            fields = ['ine', 'comp_dom', 'predial', 'escrituras_titulo']
            for field in fields:
                if field in request.FILES:
                    data[field] = request.FILES[field]

            data['user'] = request.user.id
            data['arrendador'] = request.data.get('arrendador')
            print("soy data", data)
            if data:
                print("entre al if")
                documentos_serializer = self.serializer_class_archivos(data=data)
                print(documentos_serializer)
                
                if documentos_serializer.is_valid():
                    documentos_serializer.save()
                else:
                    print("Serializer no es valido")
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_200_OK)
        
    @action(detail=False, methods=['put'], url_path='investigacion_arrendador_pdf')
    def investigacion_arrendador_pdf(self, request, *args, **kwargs):
        try:
            print("Llego a investigacion")
            instance = self.get_object()
            # Obtener el valor de validacion_escrituras y comentarios del modelo hijo
            validacion_escrituras = request.data.get('validacion_escrituras')
            validacion_ine = request.data.get('validacion_ine')
            validacion_comprobante_domicilio = request.data.get('validacion_comprobante_domicilio')
            validacion_predial = request.data.get('validacion_predial')
            comentarios = request.data.get('comentarios')
            estatus_documentos = request.data.get('estatus_documentos')
            # Actualizar el campo estatus_arrendador en el modelo principal
            print("Soy request.data", request.data)
            print("Estatus documentos", estatus_documentos)
            instance.estatus_arrendador = estatus_documentos
            # Guardar la instancia actualizada del modelo principal
            instance.save()
            # Actualizar los campos del modelo hijo
            arrendador_validacion = instance.arrendador_validacion.first()
            arrendador_validacion.validacion_escrituras = validacion_escrituras
            arrendador_validacion.validacion_ine = validacion_ine
            arrendador_validacion.validacion_comprobante_domicilio = validacion_comprobante_domicilio
            arrendador_validacion.validacion_predial = validacion_predial
            arrendador_validacion.comentarios = comentarios
            arrendador_validacion.save()
            
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            self.enviar_archivo(request.FILES.get('pdf', None), request.data.get('comentario'), request.data)
            print("edito arrendador ")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'errors': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        
    @action(detail=False, methods=['put'], url_path='investigacion')
    def investigacion(self, request, *args, **kwargs):
        try:
            print("Llego a investigacion")
            instance = self.get_object()
            # Obtener el valor de validacion_escrituras y comentarios del modelo hijo
            validacion_escrituras = request.data.get('validacion_escrituras')
            validacion_ine = request.data.get('validacion_ine')
            validacion_comprobante_domicilio = request.data.get('validacion_comprobante_domicilio')
            validacion_predial = request.data.get('validacion_predial')
            comentarios = request.data.get('comentarios')
            estatus_documentos = request.data.get('estatus_documentos')
            # Actualizar el campo estatus_arrendador en el modelo principal
            print("Soy request.data", request.data)
            print("Estatus documentos", estatus_documentos)
            instance.estatus_arrendador = estatus_documentos
            # Guardar la instancia actualizada del modelo principal
            instance.save()
            
            # Actualizar los campos del modelo hijo
            arrendador_validacion = instance.arrendador_validacion.first()
            arrendador_validacion.validacion_escrituras = validacion_escrituras
            arrendador_validacion.validacion_ine = validacion_ine
            arrendador_validacion.validacion_comprobante_domicilio = validacion_comprobante_domicilio
            arrendador_validacion.validacion_predial = validacion_predial
            arrendador_validacion.comentarios = comentarios
            arrendador_validacion.save()
            
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            
            print("edito arrendador ")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'errors': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    

    def enviar_archivo(self, archivo, comentario, info):
        # Configura los detalles del correo electrónico
        print("Llego a enviar PDF")
        try:
            remitente = 'notificaciones_arrendify@outlook.com'
            #destinatario = info.email
            destinatario = 'leonramirezrivero@gmail.com'
            #destinatario = 'juridico.arrendify1@gmail.com'
            
            
            asunto = f"Resultado Investigación Prospecto {info.nombre}"
            
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Subject'] = asunto
            print("paso objeto mime")
            # Estilo del mensaje
            #variable contenido_html_resultado externa jalada de variables.py
            pdf_html = contenido_pdf(info,comentario)
        
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            # msg.attach(MIMEText(mensaje, 'plain'))

            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Resultado_investigación.pdf')
            msg.attach(pdf_part)

            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'smtp.office365.com'
            smtp_port = 587
            smtp_username = config('smtp_u')
            smtp_password = config('smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                server.sendmail(remitente, destinatario, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})

class Arrendador_inmuebles(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Arrendador.objects.all()
    serializer_class = ArrendadorSerializer
        
    def list(self, request):
        user_session = self.request.user
        try:
            user_session = self.request.user
            if user_session.is_staff:
                data_serializer = self.serializer_class(self.queryset, many=True)
                return Response(data_serializer.data)
            
            elif user_session.rol == "Inmobiliaria":  
                #tengo que buscar a los arrendadores que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de arrendadores propios y registrados por mis agentes
                arrendadores_a_cargo = Arrendador.objects.filter(user_id__in = agentes)
                arrendadores_mios = Arrendador.objects.filter(user_id = user_session)
                mios = arrendadores_a_cargo.union(arrendadores_mios)
                
                #busqueda de arrendador vinculado
                pertenece2 = Arrendador.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                pertenece = Arrendador.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                pertenece = pertenece.union(pertenece2)
                arrendador_all = mios.union(pertenece)
                
                serializer = ArrendadorSerializer(arrendador_all, many=True)
                serialized_data = serializer.data
                    
                return Response(serialized_data)      
        
            elif user_session.rol == "Agente":  
               
                agente_qs = Arrendador.objects.filter(user_id = user_session)
               
                pertenece = Arrendador.objects.filter(mi_agente_es__icontains = user_session.first_name)
        
                arredores_a_cargo = agente_qs.union(pertenece)
                serializer = ArrendadorSerializer(arredores_a_cargo, many=True)
                serialized_data = serializer.data
            
                return Response(serialized_data)
            
            else:
                snippets = self.queryset.filter(user_id=request.user)
                print(snippets)
                data_serializer = self.serializer_class(snippets, many=True)
                return Response(data_serializer.data)
                
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)