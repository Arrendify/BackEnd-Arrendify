from django.shortcuts import render, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import *
from rest_framework import status
from rest_framework.decorators import api_view

#intento de factorizacion 1
from.Views.Inquilinos.inquilinos_view import * 
from.Views import fraterna_views 

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
from ..accounts.models import CustomUser
User = CustomUser

# Heath Check
from django.http import JsonResponse

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
# ----------------------------------Inquilino----------------------------------------------- #
class inquilino_registro(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, format=None):
        user_session = request.user
        try:
            # request.data.user = user_session
            serializer3 = InquilinoSerializers(data=request.data)
            serializer_check = InvestigacionSerializers(data=request.data)
        
            if serializer3.is_valid() and serializer_check.is_valid():
                print("valido")
                nombre = serializer3.validated_data['nombre']
                print(nombre)
                if len(nombre) > 0:
                    print("ya pase el self")
                
                    id = serializer3.save(user = user_session)
                    #serializer3.save(user = user_session)
                    serializer_check.validated_data['inquilino'] = id
                    serializer_check.save()
                    return Response(serializer3.data, status=status.HTTP_201_CREATED)
                else:
                    print("Nombre no valido")
                    return Response("Nombre vacio", status=status.HTTP_400_BAD_REQUEST)
            else:
                print("no valido")
                print(serializer3.errors)
                return Response(serializer3.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def editar_inquilino(request):
    print("Yo soy request", request.data)
    id = request.data.get('id')
    print("Valor de la id", id)
    inquilino = Inquilino.objects.get(id=id)
    print("Inquilinos: ", inquilino)
    user_serializer = InquilinoSerializers(inquilino, data=request.data)

    if user_serializer.is_valid():
        user_serializer.save()
        print("Guardo Inquilino")
        return Response(user_serializer.data, status=status.HTTP_200_OK)
    print("No guardo Inquilino xD")
    return Response(user_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class inquilinos_delete(APIView):
    def post(self, request, format=None):
        print("Si llega a eliminar", request.data)
        id = request.data.get('id')
        print("Valor de la id", id)
        inquilino = Inquilino.objects.get(id=id)
        print(inquilino)
        inquilino.delete()
      
        return Response(status=status.HTTP_204_NO_CONTENT)


class InquilinoFiadorObligadoViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Inquilino.objects.all()
    serializer_class = InquilinoSerializersFiador
    http_method_names = ['get']

    def list(self, request, *args, **kwargs):
        user_session = request.user 
        try:
            if user_session.rol == "Inmobiliaria":   
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #Obtenemos todos los inquilinos
                inquilinos_a_cargo = Inquilino.objects.filter(user_id__in = agentes, status = 1)
                inquilinos_mios = Inquilino.objects.filter(user_id = user_session, status = 1)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
                pertenece2 = Inquilino.objects.filter(mi_agente_es__icontains = agentes.values("first_name"), status = 1)
                pertenece = Inquilino.objects.filter(mi_agente_es__in = agentes.values("first_name"), status = 1)
                pertenece = pertenece.union(pertenece2)
                inquilinos_all = mios.union(pertenece)
                
                #busqueda de arrendadores propios y registrados por mis agentes
                arrendadores_a_cargo = Arrendador.objects.filter(user_id__in = agentes)
                arrendadores_mios = Arrendador.objects.filter(user_id = user_session)
                mios2 = arrendadores_a_cargo.union(arrendadores_mios)
                pertenece2 = Arrendador.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                pertenece = Arrendador.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                pertenece = pertenece.union(pertenece2)
                arrendador_all = mios2.union(pertenece)
                
                #buscamos si tenemos amigos en los arrendadores
                inquilinos_amigos = Inquilino.objects.filter(amigo_inquilino__receiver__in = arrendador_all.values("id"))
                snippets = inquilinos_amigos.union(inquilinos_all)
                
                serializer = self.get_serializer(snippets, many=True)
                serialized_data = serializer.data
                return Response(serialized_data) 
            
            elif user_session.rol == "Agente":
                print("soy Agente", user_session.first_name)
                
                inquilinos_ag = Inquilino.objects.filter(user_id = user_session, status = 1)
                pertenece = Inquilino.objects.filter(mi_agente_es__icontains = user_session.first_name, status = 1)
                inquilinos_all = inquilinos_ag.union(pertenece)
                
                agente_qs = Arrendador.objects.filter(user_id = user_session)
                pertenece = Arrendador.objects.filter(mi_agente_es__icontains = user_session.first_name)
                arredores_a_cargo = agente_qs.union(pertenece)
                
                inquilinos_amigos = Inquilino.objects.filter(amigo_inquilino__receiver__in = arredores_a_cargo.values("id"))
                snippets = inquilinos_amigos.union(inquilinos_all)
                
                serializer = self.get_serializer(snippets, many=True)
                serialized_data = serializer.data
                return Response(serialized_data) 
                
            else:
                if user_session.is_authenticated:
                    #primero obtenemos todos los inquilinos que sean mios y que hayan sido aprobados
                    inquilinos_paks = Inquilino.objects.all().filter(user_id = user_session.id, status = 1)
                    #despues obtenemos los arrendadores
                    arrendadores_amigos = Arrendador.objects.all().filter(user_id = user_session)
                    #despues buscamos todos los inquilinos esten relacionados con un arrendador
                    inquilinos_amigos = Inquilino.objects.filter(amigo_inquilino__receiver__in = arrendadores_amigos)
                    #juntamos y mandamos al serializer
                    snippets = inquilinos_paks.union(inquilinos_amigos)
                    print("mis snippets",snippets)
                    serializer = self.get_serializer(snippets, many=True)
                    return Response(serializer.data)
                else:
                    return Response(status=status.HTTP_403_FORBIDDEN)
            
        except Exception as e:
            print(f"Error: {e}")   
            
class Inquilinos_fiadores(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Inquilino.objects.all()
    serializer_class = InquilinoSerializersFiador
    http_method_names = ['get']

    def list(self, request, *args, **kwargs):
        user_session = request.user
        if user_session.is_authenticated:
       
            inquilinos = Inquilino.objects.filter(user_id=user_session.id)
            id_fiadores_obligados = Fiador_obligado.objects.all().values_list('inquilino', flat=True)
            inquilinos_ocupados = inquilinos.exclude(id__in = Subquery(id_fiadores_obligados))
            
            serializer = self.get_serializer(inquilinos_ocupados, many=True)
            return Response(serializer.data)
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)

class DocumentosInquilino(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosInquilino.objects.all()
    serializer_class = DISerializer
   
    def list(self, request, *args, **kwargs):
        content = {
            'user': str(request.user),
            'auth': str(request.auth),
        }
        queryset = self.filter_queryset(self.get_queryset())
        InquilinoSerializers = self.get_serializer(queryset, many=True)
       
        return Response(InquilinoSerializers.data ,status=status.HTTP_200_OK)
    
    def create (self, request, *args,**kwargs):
        
        user_session = str(request.user.id)
   
        try: 
            data = request.data
         
            data = {
                    "Ine": request.FILES.get('Ine', None),
                    "Comp_dom": request.FILES.get('Comp_dom', None),
                    "Rfc": request.FILES.get('Rfc', None),
                    "Ingresos": request.FILES.get('Ingresos', None),
                    "Extras": request.FILES.get('Extras', None),
                    "Recomendacion_laboral": request.FILES.get('Recomendacion_laboral', None),
                    "Acta_constitutiva":request.data['Acta_constitutiva'],
                    "inquilino":request.data['inquilino'],
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
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

    def destroy(self, request, pk=None, *args, **kwargs):
        # try:
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
            os.remove(ruta_ine)
            os.remove(ruta_comprobante_domicilio)
            os.remove(ruta_rfc)
            # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
            documentos_inquilinos.delete()
            return Response({'message': 'Archivo eliminado correctamente'}, status=204)
        else:
            return Response({'message': 'Error al eliminar archivo'}, status=400)
        # except Exception as e:
        #     return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        
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
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
   
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        print(request.data)
        
        # Verificar si se proporciona un nuevo archivo adjunto
        if 'Ine' in request.data:
            Ine = request.data['Ine']
            archivo = instance.Ine
            eliminar_archivo_s3(archivo)
            instance.Ine = Ine  # Actualizar el archivo adjunto sin eliminar el anterior
            
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
            Ingresos = request.data['Ingresos']
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
    
    

     
# ---------------------------------- Fiador Obligado ---------------------------------- #

class Fiador_obligadoViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Fiador_obligado.objects.all()
    serializer_class = Fiador_obligadoSerializer
    lookup_field = 'slug'
    
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
                print("Esta entrando a listar fiador_obligado fil")
                fiadores_obligados =  Fiador_obligado.objects.all()
                serializer = self.get_serializer(fiadores_obligados, many=True)
                serialized_data = serializer.data
                
                # Agregar el campo 'is_staff' en el arreglo de user
                for item in serialized_data:
                    item['user']['is_staff'] = True
                
                return Response(serialized_data)
            
           elif user_session.rol == "Inmobiliaria":  
                #tengo que busca a los inquilinos que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de inquilino propios y registrados por mis agentes
                inquilinos_a_cargo = Inquilino.objects.filter(user_id__in = agentes)
                inquilinos_mios = Inquilino.objects.filter(user_id = user_session)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
               
                #busqueda de inquilino vinculado
                pertenece2 = Inquilino.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                pertenece = Inquilino.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                pertenece = pertenece.union(pertenece2)
                inquilinos_all = mios.union(pertenece)
                print("Registrados por mi o por un agente directo", mios)
                print("Independientes vinculado(s) a un agente(s)", pertenece)
                print("inquilinos_all",inquilinos_all)
                print("inquilinos_all con ids",inquilinos_all.values("id"))
                
                #toca obtener los fiadores propios y de los agentes e inquilinos
                fiadores_mios = Fiador_obligado.objects.filter(user_id = user_session)
                fiadores_obligados =  Fiador_obligado.objects.filter(inquilino_id__in = inquilinos_all.values("id"))
                fiadores_all = fiadores_obligados.union(fiadores_mios)
                serializer = self.get_serializer(fiadores_all, many=True)
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
                inquilinos_ag = Inquilino.objects.filter(user_id = user_session)
                #tengo que obtener a mis inquilinos vinculados
                pertenece2 = Inquilino.objects.filter(mi_agente_es__icontains = user_session.first_name)
                pertenece = Inquilino.objects.filter(mi_agente_es__in = user_session.first_name)
                pertenece = pertenece.union(pertenece2)
                inquilinos_all = inquilinos_ag.union(pertenece)
                print("mis inquilinos propios:",inquilinos_ag)
                print("mis inquilinos vinculados:",pertenece)
                print("todos mis inquilinos:",inquilinos_all)
                
                fiadores_mios = Fiador_obligado.objects.filter(user_id = user_session)
                fiadores_obligados =  Fiador_obligado.objects.filter(inquilino_id__in = inquilinos_all.values("id"))
                fiadores_all = fiadores_obligados.union(fiadores_mios)
                serializer = self.get_serializer(fiadores_all, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)
           else:
                print("Esta entrando a listar fiador_obligado fil")
                fiadores_obligados =  Fiador_obligado.objects.all().filter(user_id = user_session)
                serializer = self.get_serializer(fiadores_obligados, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        user_session = request.user
        try:
            print("Llegando a create fiador-obligado")
            print(request.data)
            fiador_obligado_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            print(fiador_obligado_serializer)
            if fiador_obligado_serializer.is_valid(raise_exception=True):
                fiador_obligado_serializer.save( user = user_session)
                print("Guardado fiador obligado")
                return Response({'fiador_obligado': fiador_obligado_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion")
                return Response({'errors': fiador_obligado_serializer.errors})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

    def update(self, request, *args, **kwargs):
        try:
            print("Esta entrando a actualizar fiador_obligado")
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print(request.data)
            instance = self.get_object()
            print("instance",instance)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            print(serializer)
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("edito fiador obligado")
                # return redirect('myapp:my-url')
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        user_session = request.user
        try:
            print("Entrando a retrieve")
            modelos = Fiador_obligado.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            fiador_obligado = modelos.filter(slug=slug)
            if fiador_obligado:
                serializer_fiador_obligado = Fiador_obligadoSerializer(fiador_obligado, many=True)
                return Response(serializer_fiador_obligado.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            fiador_obligado = self.get_object()
            if fiador_obligado:
                fiador_obligado.delete()
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
class DocumentosFoo(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosFiador.objects.all()
    serializer_class = DFSerializer
   
    
    def list(self, request, *args, **kwargs):
        content = {
            'user': str(request.user),
            'auth': str(request.auth),
        }
        queryset = self.filter_queryset(self.get_queryset())
        FiadorSerializers = self.get_serializer(queryset, many=True)
       
        return Response(FiadorSerializers.data ,status=status.HTTP_200_OK)
    
    def create (self, request, *args,**kwargs):
        user_session = request.user.id
        print(user_session)
        try: 
            data = request.data
            print("primer print",data)
            data = {
                    "Ine": request.FILES.get('Ine', None),
                    "Comp_dom": request.FILES.get('Comp_dom', None),
                    "Escrituras": request.FILES.get('Escrituras', None),
                    "Estado_cuenta": request.FILES.get('Estado_cuenta', None),
                    "Fiador":request.data['Fiador'],
                    "user":user_session
                }
            print("segundo print",data)
            if data:
                documentos_serializer = self.get_serializer(data=data)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save()
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

    def destroy(self, request, pk=None, *args, **kwargs):
        # try:
        documentos_fiador = self.get_object()
        documento_fiador_serializer = self.serializer_class(documentos_fiador)
        print("Soy ine", documento_fiador_serializer.data['ine'])
        print("1")
        if documentos_fiador:
            ine = documento_fiador_serializer.data['ine']
            print("Soy ine 2", ine)
            comp_dom= documento_fiador_serializer.data['comp_dom']
            rfc= documento_fiador_serializer.data['escrituras_titulo']
            print("Soy RFC", rfc)
            ruta_ine = 'apps/static'+ ine
            print("Ruta ine", ruta_ine)
            ruta_comprobante_domicilio = 'apps/static'+ comp_dom
            ruta_rfc = 'apps/static'+ rfc
            print("Ruta com", ruta_comprobante_domicilio)
            print("Ruta RFC", ruta_rfc)
            os.remove(ruta_ine)
            os.remove(ruta_comprobante_domicilio)
            os.remove(ruta_rfc)
            # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
            documentos_fiador.delete()
            return Response({'message': 'Archivo eliminado correctamente'}, status=status.HTTP_200_OK)
        else:
            return Response({'message': 'Error al eliminar archivo'}, status=status.HTTP_400_BAD_REQUEST)
        # except Exception as e:
        #     return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        
    def retrieve(self, request, pk=None):
        try:
            documentos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            fiador = documentos.filter(id=pk)
            serializer_fiador = DFSerializer(fiador, many=True)
            print(serializer_fiador.data)
            ine = serializer_fiador.data[0]['Ine']
            print(ine)
            # documentos_arrendador = self.get_object()
            # print(documentos_arrendador)
            return Response(serializer_fiador.data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        print(request.data)
        
        # Verificar si se proporciona un nuevo archivo adjunto
        if 'Ine' in request.data:
            print("soy ine")
            Ine = request.data['Ine']
            archivo = instance.Ine
            eliminar_archivo_s3(archivo)
            instance.Ine = Ine  # Actualizar el archivo adjunto sin eliminar el anterior
            
        if 'Comp_dom' in request.data:
            Comp_dom = request.data['Comp_dom']
            archivo = instance.Comp_dom
            eliminar_archivo_s3(archivo)
            instance.Comp_dom = Comp_dom  # Actualizar el archivo adjunto sin eliminar el anterior
            
        if 'Estado_cuenta' in request.data:
            Estado_cuenta = request.data['Estado_cuenta']
            instance.Estado_cuenta = Estado_cuenta  # Actualizar el archivo adjunto sin eliminar el anterior
        
        if 'Escrituras' in request.data:
            Escrituras = request.data['Escrituras']
            archivo = instance.Escrituras
            eliminar_archivo_s3(archivo)
            instance.Escrituras = Escrituras  # Actualizar el archivo adjunto sin eliminar el anterior
        
        serializer.update(instance, serializer.validated_data)
        print(serializer.data['Ine'])# Actualizar el archivo adjunto sin eliminar el anterior
        return Response(serializer.data)    

# ---------------------------------Documentos Arrendador e Historial ----------------------------------------
class HistorialDocumentosArrendadorViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = DocumentosArrendador.objects.all()
    serializer_class = DocumentosArrendadorSerializer

    def update(self, request, *args, **kwargs):
        user_session = request.user 
        print("Soy request data", request.data)
        try:
            instancia_anterior = self.get_object()  # Obtén la instancia anterior
            data = {field: request.FILES[field] for field in ['ine', 'comp_dom', 'predial', 'escrituras_titulo'] if field in request.FILES}

            data['user'] = request.user.id
            #data['arrendador'] = request.data.get('arrendador')
           
            if user_session.is_staff:
                print("que hongo que pex")
            data['comentarios_comp'] = request.data.get('comentarios_comp')
            data['comentarios_ine'] = request.data.get('comentarios_ine')
            data['comentarios_rfc'] = request.data.get('comentarios_rfc')
            data['comentarios_predial'] = request.data.get('comentarios_predial')
             

            serializer = self.get_serializer(instancia_anterior, data=data, partial=True)
            # Comprueba si existen menos de 4 registros en la tabla HistorialDocumentosArrendador 
            # donde el campo previo_escrituras_titulo no sea nulo (isnull=False) y el campo historial_documentos sea igual al valor proporcionado en request.data.get('arrendador').
            if HistorialDocumentosArrendador.objects.filter(previo_predial__isnull=False, historial_documentos=request.data.get('arrendador')).count() < 4:
                if serializer.is_valid(raise_exception=True):
                    print("Hola")
                    for field in ['ine', 'comp_dom', 'predial', 'escrituras_titulo']:
                        print(field)
                        if field in data and getattr(instancia_anterior, field) != serializer.validated_data.get(field): #getattr  permite obtener el valor de un atributo indicando su nombre como una cadena
                            # self.guardar_historial(getattr(instancia_anterior, field), serializer.validated_data.get(field), 'previo_' + field)
                            print("Soy dato a editar", getattr(instancia_anterior, field))
                            eliminar_archivo_s3(getattr(instancia_anterior, field))
                    serializer.save()
                    print("Se guardo")
                    return Response(serializer.data)
                else:
                    return Response(serializer.errors)
            else:
                return Response({"error": "No se permiten más de 3 archivos previo_escrituras_titulo."})
        except Exception as e:
            return Response({'Error': 'Error al actualizar'})
    


# ---------------------------------- Inmuebeles ---------------------------------- #
class inmueblesViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    lookup_field = 'slug'
    queryset = Inmuebles.objects.all()
    serializer_class = InmueblesSerializer
    queryset_imagenes = ImagenInmueble.objects.all()
    serializer_class_imagen = ImagenInmuebleSerializer

    def list(self, request):
        user_session = self.request.user
        if user_session.is_staff:
            inmueble = Inmuebles.objects.all()
            data_serializer = self.serializer_class(inmueble, many=True)
            return Response(data_serializer.data)
        
        elif user_session.rol == "Inmobiliaria":  
                #tengo que busca a los arrendadores que tiene a un agente vinculado
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
                arrendadores_all = mios.union(pertenece)
                print("Registrados por mi o por un agente directo", mios)
                print("Independientes vinculado(s) a un agente(s)", pertenece)
                print("arrendador_all", arrendadores_all)
                print("arrendador_all con ids",arrendadores_all.values("id"))
                
                #toca obtener los inmuebles propios y de los agentes e inquilinos
                inmuebles_mios = Inmuebles.objects.filter(user_id = user_session)
                print("paso1",inmuebles_mios)
                inmuebles =  Inmuebles.objects.filter(arrendador_id__in = arrendadores_all.values("id"))
                print("paso2",)
                inmuebles_all = inmuebles.union(inmuebles_mios)
                print("paso3")
                serializer = self.get_serializer(inmuebles_all, many=True)
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
            arrendadores_ag = Arrendador.objects.filter(user_id = user_session)
            #tengo que obtener a mis inquilinos vinculados
            pertenece2 = Arrendador.objects.filter(mi_agente_es__icontains = user_session.first_name)
            pertenece = Arrendador.objects.filter(mi_agente_es__in = user_session.first_name)
            pertenece = pertenece.union(pertenece2)
            arrendadores_all = arrendadores_ag.union(pertenece)
            print("mis arrendadores propios:",arrendadores_ag)
            print("mis arrendadores vinculados:",pertenece)
            print("todos mis arrendadores:",arrendadores_all)
            
            #toca obtener los inmuebles propios y de los agentes e inquilinos
            inmuebles_mios = Inmuebles.objects.filter(user_id = user_session)
            print("paso1",inmuebles_mios)
            inmuebles =  Inmuebles.objects.filter(arrendador_id__in = arrendadores_all.values("id"))
            print("paso2",)
            inmuebles_all = inmuebles.union(inmuebles_mios)
            print("paso3")
            serializer = self.get_serializer(inmuebles_all, many=True)
            serialized_data = serializer.data
            
            if not serialized_data:
                print("no hay datos mi carnal")
                return Response({"message": "No hay datos disponibles",'asunto' :'2'})

            for item in serialized_data:
                item['agente'] = True
                
            return Response(serialized_data)
    
        else:            
            user_id = self.request.user.id
            snippets = Inmuebles.objects.filter(user_id=user_id)
            data_serializer = self.serializer_class(snippets, many=True)
            return Response(data_serializer.data)

    def create (self, request, *args, **kwargs):
        data = request.data
        data['user'] = request.user.id
        try:
            print("Esta llegando a create")
            print("id user es:",request.user.id)
            print("2")
            
            data = request.data.copy()  # Crear una copia mutable de request.data
            if data.get('reglamento_interno') == 'undefined':
                del data['reglamento_interno']
            
            if data.get('mobiliario') == 'undefined':
                del data['mobiliario']
                
            inmueble_serializer = self.get_serializer(data=data) #Usa el serializer_class para verificar que se  correcto
            if inmueble_serializer.is_valid(raise_exception=True):
                img = request.FILES.getlist('imagenes', None) #aqui llega la lista de imagenes subudas
                if img:#comprobamos que tenga algo
                    if len(img) <= 5:#comprobamos que sea menor o igual de 5 imagenes
                        print("si entre en la condicion tengo 5 imagenes o menos, puedo guardar el inmueble")
                        inmueble = inmueble_serializer.save()
                        for f in img:                            
                            data2 = {
                            "imagenes": f,
                            "inmueble": inmueble.id
                            }
                            imagen_serializer = ImagenInmuebleSerializer(data=data2)
                            imagen_serializer.is_valid(raise_exception=True)
                            imagen_serializer.save()
                            print("guarde",f)
                    else:
                        print(f"Te Pasaste de imagenes agrega menos de 5, la cintidad de img son =",len(img))
                        return Response({'error': str(e)}, status = "007")#retornar un status diferente de 400 para las imagenes
                    
                    print("termine con las fotos, continuamos con el response")
                    return Response({'inmuebles': inmueble_serializer.data, 'imagen': imagen_serializer.data},
                        status=status.HTTP_201_CREATED)
                    
                else:
                    print("imagen esta vacio")
                    return Response({'error': 'Error , falta imagen'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({"error":inmueble_serializer.errors}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    
    def destroy(self, request, slug=None, *args, **kwargs):
        try:
            print("Esta entrando a eliminar Inmueble")
            inmueble = get_object_or_404(Inmuebles.objects.all(), slug=slug)
            print("Soy inmueble", inmueble)
            if inmueble:
                inmueble.delete()
                print("Elimino correctamente")
                return Response({'message': 'Inmueble eliminado correctamente'}, status=204)
            return Response({'message': 'Error al eliminar inmueble'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            print("Entrando a retrieve")
            #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            inmueble = Inmuebles.objects.all().filter(slug=slug)
            serializer_inmueble = InmueblesSerializer(inmueble, many=True)
            id = serializer_inmueble.data[0]['id']
            imagenes = self.queryset_imagenes.filter(inmueble_id=id)
            serializer_img = ImagenInmuebleSerializer(imagenes, many=True)
            total_imagenes = imagenes.count()
     
            dta = {}
            dta['inmueble'] = serializer_inmueble.data
            dta['fotos'] = serializer_img.data
            dta['total_imagenes'] = total_imagenes
            # data = {'data': context}
            # return render(request, 'home/edit_inmueble.html', {'data': dta})
            return Response({'inmuebles': serializer_inmueble.data, 'imagen': serializer_img.data, 'total_imagenes':total_imagenes},
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'Error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
        
    def update(self, request, *args, **kwargs):
        # print("Esta entrando a update Inmueble")
        print("Esta entrando a update Inmueble")
        id_inmueble = request.data.get('id')
        imagenes = self.queryset_imagenes.filter(inmueble_id = id_inmueble)
        try: 
            data_string = request.data.get('eliminar_imagenes')
            data2 = json.loads(data_string)
            print(request.data)
            
            if len(data2) != 0: # Obtenemos imagenes y haces el proceso de eliminado de la imagen seleccionada 
                for key , value in data2.items():
                    print("Valor de las id a eliminar", value)
                    if imagenes.count() > 1:
                        imagen = self.queryset_imagenes.filter(id=value)                      
                        url_base = imagen.first().imagenes
                        print(url_base)
                        imagen.delete() 
                        eliminar_archivo_s3(url_base)
                        print("Eliminada Con exito!")

                        
            print("Actualizar datos Inmueble")
        
            data = request.data
            print("Soy nuevamente data", data)
        
            id_inmueble = request.data.get('id')
            inmueble = self.queryset.get(id = id_inmueble)
            print("Soy inmueble", inmueble)
    
            data = request.data.copy()  # Crear una copia mutable de request.data

            if data.get('reglamento_interno') == 'undefined':
                del data['reglamento_interno']
            
            if data.get('mobiliario') == 'undefined':
                del data['mobiliario']

            
            print("Soy request.data sin archivos", data)
            inmueble_serializer = self.get_serializer(inmueble, data=data, partial=kwargs.pop('partial', False))
            print("6")

            if inmueble_serializer.is_valid(raise_exception=True):
                print("7")
                self.perform_update(inmueble_serializer)
                print("Edito datos Inmuebles")
                print("4")
                print("El valor de la id es:", id)
                print(request.data.get('id'))
                # Magia para subir fotos
               
                if imagenes.count() < 5:
                    print("puedes continual con las fotos el contador es menor a 5")
                    images = request.FILES.getlist('imagenes', None)
                    print("soy el total de imagenes que van a ser cargadas",images)
                    if len(images) != 0: 
                        if images is not None:
                            img = len(images)
                            img_viejas = imagenes.count()
                            img_nuevas = 5 - img_viejas
                            print("contador de imagenes que tengo en el inmueble",img_viejas)
                            print("contadador 2 =",  img_nuevas)
                            print(f"tengo{img_viejas} imagenes guardadas y quiero cargar{img} y tengo estos lugares{img_nuevas}")
                            
                            if  img_viejas != 5 or img_nuevas != 0:
                                if img <= img_nuevas:
                                    print("si entre en la condicion")
                                    for f in images:
                                        data2 = {
                                        "imagenes": f,
                                        "inmueble": request.data.get('id')
                                        }
                                        imagen_serializer = ImagenInmuebleSerializer(data=data2)
                                        imagen_serializer.is_valid(raise_exception=True)
                                        imagen_serializer.save()
                                        print("guarde",f)
                            else:
                                print(f"No tengo mas espacio para guardar las nuevas imagenes quieres cargar {img} imagenes  de {img_nuevas} slots disponibles, borra alguna para continuar")
                                return Response({'error': str(e)}, status = "007")#retornar un status diferente de 400 para las imagenes
                    
                            print("termine con las fotos, continuamos con el response")
                            return Response({'Inmueble': inmueble_serializer.data, 'Imagen': imagen_serializer.data},
                                status=status.HTTP_201_CREATED)  
                    else:
                        print("estoy vacio")   
                        print("no actualice fotos por que estoy vacio, continuamos con el response")
                else:
                    print("Carnal ya tienes 5 fotos no puedes agregar mas")
                    
                print("no actualice fotos por que no cabian mas, continuamos con el response")
                return Response({'Inmueble': inmueble_serializer.data},
                            status=status.HTTP_201_CREATED)
           
            return Response({'author': inmueble_serializer.data})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)    

    @action(detail=False, methods=['put'], url_path='actualizar_status')
    def actualizar_status(self, request, pk=None, *args, **kwargs):
        instance = self.get_object()
        data = request.data.copy()
        data['user'] = request.user.id

        serializer = self.get_serializer(instance, data=data, partial=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data)
        else:
            return Response(serializer.errors)



#  --------------------------------------------------------  Mobiliario -----------------------------------------------------------

class MobiliarioCantidad(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    queryset = InmueblesInmobiliario.objects.all()
    serializer_class = InmueblesMobiliarioSerializer

    def create(self, request, *args, **kwargs):
        print("Soy request", request.data)   
        datos = request.data["datos"]
        print("soy datos",datos)
        print("cantidad",datos[0]["cantidad"])
        
    
        # Eliminar los campos vacíos del diccionario 'data'
        # data = {key: value for key, value in data.items() if value != ''}
        for mobiliario_nuevo in datos:                                 
            data2 = {
            "cantidad": mobiliario_nuevo["cantidad"],
            "mobiliario": mobiliario_nuevo["mobiliario"],
            "observaciones": mobiliario_nuevo["observaciones"],
            "inmuebles": request.data["inmueble"],
            }
            print("obtube los datos",data2)
            print("antes de mobiliario")
            mobiliario = InmueblesMobiliarioSerializer(data=data2)
            print("despues de mobiliario",mobiliario)
            
            mobiliario.is_valid(raise_exception=True)
            print("mobiliario es valido")
            mobiliario.save(user = request.user)
            print(f"Guarde => cantidad: {mobiliario_nuevo['cantidad']}, cantidad: {mobiliario_nuevo['mobiliario']} ,observaciones: {mobiliario_nuevo['cantidad']}")


        return Response(mobiliario.data, status=status.HTTP_201_CREATED)

# ---------------------------------- Investigacion ---------------------------------- #
  
class investigaciones(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Investigacion.objects.all()
    serializer_class = InvestigacionSerializers
   
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        if user_session.username == "Arrendatario1" or user_session.username == "Legal":
            print("Si eres el elegido")
            qs = request.GET.get('nombre')     
            try:
                if qs:
                    inquilino = Inquilino.objects.all().filter(nombre__icontains = qs)
                    id_inq = []
                    for inq in inquilino:
                        id_inq.append(inq.id)
                    investigar = Investigacion.objects.all().filter(inquilino__in = id_inq)
                    serializer = self.get_serializer(investigar, many=True)
                    return Response(serializer.data)
                    
                else:
                        print("Esta entrando a listar inquilino desde invetigacion")
                        print("sin barra de busqueda")
                        investigar =  Investigacion.objects.all()
                        serializer = self.get_serializer(investigar, many=True)
                        return Response(serializer.data)
                
                #    return Response(serializer.data, status= status.HTTP_200_OK)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'No estas autorizado'}, status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        try:
            print("Esta entrando a actualizar inv")
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print("soy el request",request.data)
            print("soy el status que llega",request.data["status"])
            instance = self.get_object()
            print("instance",instance)
            print("id",instance.id)
            
            #Consulata para obtener el inquilino y establecemos fecha de hoy
            today = date.today().strftime('%d/%m/%Y')
            inquilino_mod =  Inquilino.objects.all().filter(id = instance.id)
            primer_inquilino = inquilino_mod.first()
            print("soy nombre de inquilino",primer_inquilino.nombre)
            #Consulata para obtener el fiador confirme a la fk y releated name 
            fiador = primer_inquilino.aval.all().first()
            #primero comprobar si hay aval
            if fiador:
                print("si hay fiador")
                print("yo soy info de los fiadores",fiador.__dict__)
                
                #si hay fiador hacemos el proceso de aprobar           
                if request.data["status"] == "Aprobado":
                    print("APROBADO")
                    primer_inquilino.status = "1"
                    print("status cambiado",primer_inquilino.status)
                    primer_inquilino.save()
                    print("fiador.fiador_obligado",fiador.fiador_obligado)
                    #asignacion de variables dependiendo del Regimen fiscal del Fiador
                    if primer_inquilino.p_fom == "Persona Moral":
                        print("Soy persona moral")
                    else: 
                        
                        if fiador.fiador_obligado == "Obligado Solidario Persona Moral":
                            print("No agregamos nada")
                        else:
                            ingreso = request.data["roe_inquilino"]
                            ine_inquilino = request.data["ine_inquilino"]
                            ine_fiador = request.data["ine_fiador"]
                            
                            if fiador.recibos == "Si":
                                ingreso_obligado = "Recibo de nómina"   
                            else:
                                ingreso_obligado = "Estado de cuenta" 
                                #combierte el salario mensual a letra prospecto
                                
                            number = primer_inquilino.ingreso_men
                            number = int(number)
                            text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
                            text_representation = text_representation.capitalize()
                            #combierte el salario mensual de aval
                            number_2 = fiador.ingreso_men_fiador
                            number_2 = int(number_2)
                            text_representation2 = num2words(number_2, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
                            text_representation2 = text_representation2.capitalize()
                    print("Pasamo el if de obligado ")
                
                    #hacer el proceso de enviar archivo especial para persona moral
                    if primer_inquilino.p_fom == "Persona Moral":
                        print("soy persona moral")
                        archivo = request.data["doc_rec"]                        
                        archivo = request.data["doc_rec"]
                        comentario = "nada"
                        self.enviar_archivo(archivo,primer_inquilino,comentario)
                           
                    else:    
                        if fiador.fiador_obligado == "Fiador Solidario":
                            print("Hola soy Fiador Solidario")
                            context = {
                            'info':primer_inquilino,
                            'fiador':fiador,
                            'fecha_actual':today,
                            'ine_inquilino':ine_inquilino,
                            'ine_fiador':ine_fiador,
                            'number': number,
                            'number_2': number_2,
                            'text_representation': text_representation,
                            'text_representation2': text_representation2,
                            'ingreso':ingreso,
                            'ingreso_obligado':ingreso_obligado,
                            'template':"home/aprobado_fiador.html",
                            }
                            self.generar_archivo(context)  
                        
                        elif fiador.fiador_obligado == "Obligado Solidario Persona Fisica":
                            context = {
                            'info':primer_inquilino,
                            'fiador':fiador,
                            'fecha_actual':today,
                            'ine_inquilino':ine_inquilino,
                            'ine_fiador':ine_fiador,
                            'number': number,
                            'number_2': number_2,
                            'text_representation': text_representation,
                            'text_representation2': text_representation2,
                            'ingreso':ingreso,
                            'ingreso_obligado':ingreso_obligado,
                            'template':"home/aprobado_obligado.html",
                            }
                            self.generar_archivo(context)  
                        
                        else:
                            print("Obligado Solidario Persona Moral")
                            print("Otro proceso")
                            archivo = request.data["doc_rec"]
                            comentario = "nada"
                            self.enviar_archivo(archivo,primer_inquilino,comentario)      
                
                if request.data["status"] == "Rechazado":
                    print("rechazado con aval")
                    primer_inquilino.status = "0"
                    print("status cambiado",primer_inquilino.status)
                    primer_inquilino.save()
                    comentario = request.data["comentario"]
                    archivo =request.data["doc_rec"]
                    self.enviar_archivo(archivo,primer_inquilino,comentario)   
                

                elif request.data["status"] == "En espera":
                    primer_inquilino.status = "1"
                    print("status cambiado",primer_inquilino.status)
                    primer_inquilino.save()
                    print("paso save")
            # S I N A V A L            
            else:
                print("no hay aval aprobado")
                if request.data["status"] == "Aprobado":
                    print("APROBADO SIN AVAL")
                    primer_inquilino.status = "1"
                    primer_inquilino.fiador = "no hay"
                    primer_inquilino.save()
                    print("status cambiado",primer_inquilino.status)
                    comentario = "nada"
                    print(comentario)
                    
                    if "doc_sa" in request.data:
                        print("si existo")
                        archivo_sa = request.data["doc_sa"]
                        print(archivo_sa)
                    else:
                        print("no existo")
                        archivo_sa = request.data["doc_rec"] 
                        print(archivo_sa)
                    
                    self.enviar_archivo(archivo_sa,primer_inquilino,comentario)  
                
                if request.data["status"] == "Rechazado":
                        print("Rechazado sin Aval")
                        primer_inquilino.status = "0"
                        primer_inquilino.fiador = "no hay"
                        print("status cambiado",primer_inquilino.status)
                        primer_inquilino.save()
                        comentario = request.data["comentario"]
                        archivo =request.data["doc_rec"]
                        self.enviar_archivo(archivo,primer_inquilino,comentario)    
            
                elif request.data["status"] == "En espera":
                    primer_inquilino.status = "1"
                    primer_inquilino.fiador = "no hay"
                    print("status cambiado",primer_inquilino.status)
                    primer_inquilino.save()
                    print("paso save")  
            
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("edite investigacion")
            
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
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
        
    def generar_archivo(self,context):
        # Renderiza el template HTML  
        template = context["template"] #obtenemos template
        print("template asignado",template)
        html_string = render_to_string(template, context)# lo comvertimos a string
        pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
        print("pdf realizado")
        print(pdf_file)
        
        archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
       
        print("antes de enviar_archivo",context)
        self.enviar_archivo(archivo, context["info"])
        print("PDF ENVIADO")
             
        
    def enviar_archivo(self, archivo, info, comentario="nada"):
        print("soy pdf content",archivo)
        print("soy comentario",comentario)
        print("soy info de investigacion",info.__dict__)
        
        
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones_arrendify@outlook.com'
            destinatario = info.email
            #destinatario = 'jsepulvedaarrendify@gmail.com'
            #destinatario = 'juridico.arrendify1@gmail.com'
            
            
            asunto = f"Resultado Investigación Prospecto {info.nombre}"
            
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Subject'] = asunto
            print("paso objeto mime")
           
            if hasattr(info, 'fiador'):
                print("SOY info.fiador",info.fiador)
            
            # Estilo del mensaje
            #variable contenido_html_resultado externa jalada de variables.py or info.fiador == "no hay"
            if comentario == "nada" :
                pdf_html = contenido_pdf_aprobado(info)
          
            else:
                pdf_html = contenido_pdf(info,comentario)
          
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
        
        
    def aprobar_prospecto(self, request, *args, **kwargs):
        try:
            print("entrando en Aprobar prospecto")
            today = date.today().strftime('%d/%m/%Y')
            req_dat = request.data
            print("request.data", req_dat)
            print("el id que llega", req_dat["id"])
            info = self.queryset.filter(id = req_dat["id"]).first()
            print(info.__dict__)   
            print("request.data",req_dat)   
            print("soy la info del",info.inquilino.nombre)       
            
            x = "Si"
            y = "No"
            
            #obtener la tipologia
            # Definir las opciones y sus correspondientes valores para la variable "plano"
            opciones = {
                'Excelente': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_excelente.png",
                'Bueno': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_bueno.png",
                'Regular': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_regular.png",
                'Malo': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_malo.png"
            }
            
            tipo_score_ingreso = req_dat["tipo_score_ingreso"]
            tipo_score_pp = req_dat["tipo_score_pp"]
            tipo_score_credito = req_dat["tipo_score_credito"]
            print("score ingreso",req_dat["tipo_score_ingreso"])
            print("score ingreso",tipo_score_pp)
            print("score ingreso",tipo_score_credito)
            
            if tipo_score_ingreso and tipo_score_pp and tipo_score_credito in opciones:
                tsi = opciones[tipo_score_ingreso]
                tspp = opciones[tipo_score_pp]
                tsc = opciones[tipo_score_credito]
                print(f"Tu Tipo de score es: {tipo_score_ingreso}, URL: {tsi}")
                
            
            
            context = {'info': info, "fecha_consulta":today, 'x':x, 'y':y, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc}
            
            #template = 'home/resultado_investigacion_new.html'
            template = 'home/report.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Finalizamos el proceso de aprobado") 
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST) 

# ----------------------------------Cotizador---------------------------------- #        
class Arrendador_Cotizador(viewsets.ModelViewSet):
    queryset = Arrendador.objects.all()
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
            print(f"Error: {e}")
            

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
               inquilinos_a_cargo = Inquilino.objects.filter(user_id__in = agentes)
               inquilinos_mios = Inquilino.objects.filter(user_id = user_session)
               mios = inquilinos_a_cargo.union(inquilinos_mios)
               pertenece2 = Inquilino.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
               pertenece = Inquilino.objects.filter(mi_agente_es__in = agentes.values("first_name"))
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
               inquilinos_ag = Inquilino.objects.filter(user_id = user_session, status = 1)
               pertenece = Inquilino.objects.filter(mi_agente_es__icontains = user_session.first_name)
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
               paquetes =  Paquetes.objects.all().filter(user_id = user_session.id)
               # Obtener las cotizaciones del usuario que no tienen un paquete asociado
               cotizaciones_sin_paquete = cotizaciones.exclude(id__in = paquetes.values_list('cotizacion_id', flat=True))
               print("soy cotizaciones_sin_paquete",cotizaciones_sin_paquete)                                                
               serializer = self.get_serializer(cotizaciones_sin_paquete, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
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
            print(f"Error: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    # probando con variables de entorno
    def enviar_pdf(self, pdf_content, info):
        print("soy pdf content",pdf_content)
        print("soy info de enviar_pdf",info)
        print("soy correo de agentify",info.agentify.__dict__)
        # Configura los detalles del correo electrónico
        try:
            print("entre en el try")
            remitente = 'notificaciones_arrendify@outlook.com'
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
            smtp_server = 'smtp.office365.com'
            smtp_port = 587
            smtp_username = config('smtp_u')
            smtp_password = config('smtp_pw')
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
            #server = "'http://192.168.1.187:8000'"
            #server = "http://192.168.3.2:8000"
            server = "https://arrendify.app"
            
            #variable
            html = correo_pas(server, token)
            # Envío de la notificación por correo electrónico
            msg = MIMEMultipart()
            msg['From'] = 'notificaciones_arrendify@outlook.com'
            msg['To'] = email
            msg['Subject'] = 'Recuperación de contraseña'
            message = f'Haz clic en el siguiente enlace para recuperar tu contraseña: {server}/guardar_password?token={token.key}'
            msg.attach(MIMEText(html, 'html'))
            smtp_server = 'smtp.office365.com'
            smtp_port = 587
            smtp_username = config('smtp_u')
            smtp_password = config('smtp_pw') 

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
            smtp_server = 'smtp.office365.com'
            smtp_port = 587
            smtp_username = config('smtp_u')
            smtp_password = config('smtp_pw')
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
                return Response({'comentario': comentario_serializer.data}, status=status.HTTP_201_CREATED)
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
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
# ----------------------------------Paquetes---------------------------------- #
class Paks(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Paquetes.objects.all()
    serializer_class = PaquetesSerializer
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        qs = request.GET.get('codigo')  
        print("yo soy codigo",qs)
        try:
           if user_session.is_staff:
                if qs:
                    paquetes =  Paquetes.objects.all().filter(codigo_paquete__icontains = qs)
                    print("soy el query set de paquetes",paquetes)
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
                else:
                    print("No hay codigo que buscar")
                    paquetes =  Paquetes.objects.all()
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
                
           elif user_session.rol == "Inmobiliaria":
                print("soy Inmobiliaria en paqs", user_session.first_name)
                if qs:
                    paquetes =  Paquetes.objects.all().filter(codigo_paquete__icontains = qs)
                    print("soy el query set de paquetes",paquetes)
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
                else:
                    paquetes =  Paquetes.objects.all()
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
           
           elif user_session.rol == "Agente":
                if qs:
                    paquetes =  Paquetes.objects.all().filter(codigo_paquete__icontains = qs)
                    print("soy el query set de paquetes",paquetes)
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
                else:
                    print("soy Agente", user_session.first_name)
                    paquetes =  Paquetes.objects.all()
                    serializer = self.get_serializer(paquetes, many=True)
                    return Response(serializer.data)
           else:
                print("Esta entrando a listar Paquetes fil")
                paquetes =  Paquetes.objects.all().filter(user_id = user_session)
                print("soy paquetes",paquetes)
                # Filtrar los paquetes basados en algún valor dentro de datos_arrendamiento
                paquetes_filtrado =  paquetes.filter(datos_arrendamiento__deposito_rendimiento = "Si")
                print(paquetes_filtrado)
                # Reemplaza 'deposito_garantia' y '10000' con la clave y el valor específicos que estás buscando dentro de datos_arrendamiento para el rendimiento
               
                serializer = self.get_serializer(paquetes, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
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
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_pagare(self, request, *args, **kwargs):
        id_paq = request.data
        print("el ID que llegas es: ",id_paq)
        info = self.queryset.filter(id = id_paq).first()
        print(info.__dict__)
        
        meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
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
        precio = int(precio)
    
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
    
    
# class Pagares(viewsets.ModelViewSet):
#     queryset = Cotizacion.objects.all()
#     serializer_class = CotizacionSerializerPagares

#     def create(self, request, *args, **kwargs):
    
#         info = self.queryset.filter(id=1).first()
#         serializer = self.get_serializer(info)
#         template = 'home/plan.html'
#         data = serializer.data
#         fecha_cotizacion = str(date.today())
#         # Convert the fecha_cotizacion string to a datetime object
#         fecha_cotizacion_datetime = datetime.strptime(fecha_cotizacion, '%Y-%m-%d')

#         # Extraer el día y el año del objeto de fecha y hora
#         dia = fecha_cotizacion_datetime.day
#         anio = fecha_cotizacion_datetime.year
#         context = {'info': data, 'dia':dia, 'anio':anio} 
#         html_string = render_to_string(template, context)
#         pdf_file = HTML(string=html_string).write_pdf(target=None)
        
#         response = HttpResponse(content_type='application/pdf')
#         response['Content-Disposition'] = 'attachment; filename="mi_pdf.pdf"'
#         response.write(pdf_file)
#         # agregar logica extra para el pagare, se le tenen que enviar al arrendador ya firmados
#         return response
    
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
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)