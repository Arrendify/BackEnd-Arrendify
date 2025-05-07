
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
#variable para correo HTMl



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

class ContratosViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Contratos.objects.all()
    serializer_class = ContratosDashSerializer
    
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
            print("Llegando a create de residentes")
            print("Paso 1")
            user_session = request.user
            print("llega el request, hay que separar lo que llega",request.data)
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
            user_session = request.user
            print("LLegando a eliminar residente")
            Residentes = self.get_object()
            if Residentes:
                Residentes.delete()
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
  
    def almacenar_datos(self, request, *args, **kwargs):
        try:
            print("LLegando a alamacenar")
            user_session = request.user            
            info = request.data
            aviso ={}        
            print("")
            print("Esto es el request data en almacenar datos.",info)
            print("")
            print("tipo de contrato",info["tipo_contrato"])
            #comprueba si el inquilino ya esta registrado
            arrendatario =  info.get("arrendatario")
            print("este que valor tiene?",arrendatario)
            if arrendatario != None:
                arrendatario = dict(arrendatario)

                if arrendatario.get("inquilino"):
                    print("hay informacion del arrendatario hay que hacer una busqueda de id")
                    inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                else:
                    print("no hay informacion del inquilino hay que Guardarlo pero hay que ver si ya existe")
                    #Hay que saber el regimen fiscal primero
                    if arrendatario.get("regimen_fiscal") == "Persona Fisica":
                        print("nombre_completo", arrendatario["nombre_completo"])
                        inquilino = Arrendatario.objects.all().filter(nombre_completo = arrendatario["nombre_completo"], user = user_session).first()
                    else:
                        print("nombre_empresa", arrendatario["nombre_empresa"])
                        inquilino = Arrendatario.objects.all().filter(nombre_empresa = arrendatario["nombre_empresa"], user = user_session).first()
                    
                    if inquilino:
                        print("ya existe el inquilino")
                        aviso["inquilino"] = "Ya existe el inquilino"
                        #return Response({'error': 'Ya existe el inquilino'}, status=status.HTTP_400_BAD_REQUEST)
                    else:
                        print("no existe el inquilino")
                        serializer_inquilino = InquilinoSerializers(data=arrendatario)
                        serializer_inquilino.is_valid(raise_exception=True)
                        inquilino = serializer_inquilino.save(user = user_session)
                        print("Se guardo al nuevo el inquilino")    
                        print("saber el numero de inquilino id", inquilino.id)
               
            #AVAL
            print("")
            aval = info.get("fiador")
            if aval != None:
                aval = dict(aval) 
                print("Esto es el aval",aval)           
                if aval.get("aval"):
                    print("hay informacion del aval hay que hacer una busqueda de id")
                    fiador = Aval.objects.all().filter(id = info["fiador"]["aval"]).first()
                    aviso["fiador"] = "Ya existe el fiador"
                
                elif aval.get("registro_aval") == "No":
                    print("no quiere tener aval vamos a darle un valor o ver que hacemos")
                    aviso["aval"] = "No"
                
                else:
                    print("no hay informacion del fiador hay que Guardarlo pero hay que ver si ya existe")
                    #Hay que saber el regimen fiscal primero
                    if aval.get("tipo_aval") == "Obligado Solidario Persona Fisica" or aval.get("tipo_aval") == "Fiador Solidario Persona Fisica":    
                        print("nombre_completo", aval["nombre_completo"])
                        fiador = Aval.objects.all().filter(nombre_completo = aval["nombre_completo"], user = user_session).first()
                    
                    else:
                        print("nombre_empresa", aval["nombre_empresa"])
                        fiador = Aval.objects.all().filter(nombre_empresa = aval["nombre_empresa"], user = user_session).first()
                    
                    if fiador:
                        print("ya existe el fiador")
                        
                    else:
                        print("no existe el fiador")
                        serializer_fiador = AvalSerializer(data=aval)
                        serializer_fiador.is_valid(raise_exception=True)
                        fiador = serializer_fiador.save(user = user_session)
                        print("Se guardo al nuevo el fiador")    
                        print("saber el numero de arrendador id", fiador.id)    
                
            #Propietario
            print("")
            #propietario = dict(info["arrendador"])
            propietario = info.get("arrendador") 
            print("Esto es el propietario", propietario)           
            if propietario != None:
                propietario = dict(propietario) 
                
                if propietario.get("propietario"):
                    print("hay informacion del propietario hay que hacer una busqueda de id")
                    arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                    print("nombre del arrendador",arrendador)
                
                else:
                    print("no hay información del propietario hay que Guardarlo pero hay que ver si ya existe")
                    #Hay que saber el regimen fiscal primero
                    if propietario.get("regimen_fiscal") == "Persona Fisica":    
                        print("nombre_completo", propietario["nombre_completo"])
                        arrendador = Propietario.objects.all().filter(nombre_completo = propietario["nombre_completo"], user = user_session).first()
                    
                    else:
                        print("nombre_empresa", propietario["nombre_empresa"])
                        arrendador = Propietario.objects.all().filter(nombre_empresa = propietario["nombre_empresa"], user = user_session).first()
                    
                    if arrendador:
                        print("ya existe el propietario")
                        
                    else:
                        print("no existe el propietario hay que guardar la variable arrendador para asignarla en el data del contrato")
                        serializer_arrendador = ArrendadorSerializer(data=propietario)
                        serializer_arrendador.is_valid(raise_exception=True)
                        arrendador = serializer_arrendador.save(user = user_session)
                        
                        print("Se guardo al nuevo el propietario")
                        print("Saber el numero de arrendador id", arrendador.id)

            #Inmueble
            print("")
            print("Vamos a checar si tenemos inmueble")
            if info.get("inmueble"):
                inmueble= dict(info["inmueble"])
                print("Esto es el inmueble", inmueble) 
                
                if inmueble.get("inmueble"):
                    print("hay informacion del propietario hay que hacer una busqueda de id")
                    propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                    print("nombre del arrendador",propiedad)
            
                else:
                    print("no hay información del propiedad hay que Guardarlo pero hay que ver si ya existe")
                    #Hay que saber si ya tenemos el inmueble registrado
                    propiedad = Inmuebles.objects.all().filter(alias_inmueble = info["inmueble"]["alias_inmueble"], user = user_session).first()
            
                    if propiedad:
                        print("ya existe el propietario")
                        
                    else:
                        print("no existe la propiedad hay que guardar la variable arrendador para asignarla en el data del contrato")
                        serializer_inmueble = InmueblesSerializer(data=inmueble)
                        serializer_inmueble.is_valid(raise_exception=True)
                        propiedad = serializer_inmueble.save(user = user_session)
                        
                        print("Se guardo al nuevo inmueble")
                        print("Saber el numero de id del inmueble", propiedad.id)
                    
            #Tocaria juntar todo en una instancia de contratos
            informacion_del_contrato = info["datos_contratos"]
            
            print("informacion_del_contrato", informacion_del_contrato)
            print("")
            print("Este es el tipo de contrato:",info["tipo_contrato"]) 
            
            codigo_paquete = ""
            
            if info["tipo_contrato"] == "Arrendamiento" or info["tipo_contrato"] == "Poliza" or info["tipo_contrato"] == "Arrendamiento+Pagares" or info["tipo_contrato"] == "Contrato Renta con opcion a venta" or info["tipo_contrato"] == "Contrato Renta con opcion a venta + Pagares":

                if  aval is not None and aval.get("aval"):
                    data_contrato = {
                        'propietario': f"{arrendador.id}",
                        'inmueble': f"{propiedad.id}",
                        'arrendatario': f"{inquilino.id}",
                        'aval': f"{fiador.id}",
                        'tipo_contrato': info["tipo_contrato"],
                        'datos_contratos': informacion_del_contrato,
                        "id_pago": info["id_pago"]
                        }
                    
                else:
                    data_contrato = {
                    'propietario': f"{arrendador.id}",
                    'inmueble': f"{propiedad.id}",
                    'arrendatario': f"{inquilino.id}",
                    'tipo_contrato': info["tipo_contrato"],
                    'datos_contratos': informacion_del_contrato,
                    "id_pago": info["id_pago"]
                    }
                   
                print("Soy el data del contrato que no es pagare",data_contrato)
                contrato = Contratos.objects.all().filter(arrendatario__in = data_contrato["arrendatario"], propietario__in = data_contrato["propietario"], tipo_contrato__in = info["tipo_contrato"])
                
            elif info["tipo_contrato"] == "Pagares":
                
                if aval.get("aval"):
                    data_contrato = {
                    'propietario': f"{arrendador.id}",
                    'arrendatario': f"{inquilino.id}",
                    'tipo_contrato': "Pagares",
                    'datos_contratos': informacion_del_contrato,
                    "id_pago": info["id_pago"]
                    }
                    
                else:
                    data_contrato = {
                        'propietario': f"{arrendador.id}",
                        'arrendatario': f"{inquilino.id}",
                        'aval': f"{fiador.id}",
                        'tipo_contrato': "Pagares",
                        'datos_contratos': informacion_del_contrato,
                        "id_pago": info["id_pago"]
                        }
                    
                print("Soy el data del contrato en pagare",data_contrato)
                contrato = Contratos.objects.all().filter(arrendatario__in = data_contrato["arrendatario"], propietario__in = data_contrato["propietario"], tipo_contrato = "Pagare")
            
            elif info["tipo_contrato"] == "Corretaje (Inmobiliaria)":
                data_contrato = {
                        'propietario': f"{arrendador.id}",
                        'inmueble': f"{propiedad.id}",
                        'tipo_contrato': "Corretaje (Inmobiliaria)",
                        'datos_contratos': informacion_del_contrato,
                        "id_pago": info["id_pago"]
                        }
                print("Soy el data del contrato en corretaje",data_contrato)
                contrato = Contratos.objects.all().filter(inmueble__in = data_contrato["inmueble"], propietario__in = data_contrato["propietario"], tipo_contrato = "Corretaje (Inmobiliaria)")                

            elif info["tipo_contrato"] == "Contrato de Compra/Venta":
                data_contrato = {
                        'tipo_contrato': info["tipo_contrato"],
                        'datos_contratos': informacion_del_contrato,
                        "id_pago": info["id_pago"]
                        }
                print("Soy el data del contrato en corretaje",data_contrato)
                contrato = Contratos.objects.filter(datos_contratos__nombre_vendedor = info["datos_contratos"]["nombre_vendedor"], datos_contratos__nombre_comprador = info["datos_contratos"]["nombre_comprador"])       
                print("contrato compra venta",contrato)
            
            elif info["tipo_contrato"] == "Contrato de Promesa":
                data_contrato = {
                        'tipo_contrato': info["tipo_contrato"],
                        'datos_contratos': informacion_del_contrato,
                        "id_pago": info["id_pago"]
                        }
                print("Soy el data del contrato en corretaje",data_contrato)
                contrato = Contratos.objects.filter(datos_contratos__promitente_vendedor_nombre = info["datos_contratos"]["promitente_vendedor_nombre"], datos_contratos__promitente_comprador_nombre = info["datos_contratos"]["promitente_comprador_nombre"])       
                print("contrato promesa",contrato)
             
            #comprobar que no se duplique el registro del contrato
            if contrato:
                print("ya existen los datos de contrato, ignoramos")
                return Response({'aviso': aviso}, status=302)
            else:
                print("vamos a guardar")
                serializer_contratos = ContratosDashSerializer(data=data_contrato)
                serializer_contratos.is_valid(raise_exception=True)
                print("serializer_contratos", serializer_contratos)
                serializer_contratos.save(user = user_session)
                print("Se guardo el contrato")
                return Response({'Contrato': serializer_contratos.data}, status=status.HTTP_201_CREATED)
                 
            
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_pagare(self, request, *args, **kwargs):  
        try:
            print("Generar pagare")
            # user_session = request.user
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            arrendatario = dict(info["arrendatario"]) 
            if arrendatario.get("inquilino"):
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                info["arrendatario"] = inquilino

            aval = dict(info["fiador"])         
            if aval.get("aval"):
                print("hay informacion del aval hay que hacer una busqueda de id")
                fiador = Aval.objects.all().filter(id = info["fiador"]["aval"]).first()
                info["fiador"] = fiador
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador

            print("")
            print("Contimuamos el proceso para el arrendatario")
            print("")
            #print("Veamos si tenemos info",info["arrendatario"]["inquilino"])
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(fecha_inicial, "%Y-%m-%d").date()
            print("fecha OK",fecha_inicial)
          
            dia = fecha_ok.day
            
            print("")
            print("dia",dia)
            
            # Definir la duración en meses
            
            duracion_meses = int(info["datos_contratos"]['duracion'])
            print("duracion en meses",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_ok + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_ok < fecha_final:
                nombre_mes = fecha_ok.strftime("%B")  # %B da el nombre completo del mes
                print("fecha",fecha_ok.year)
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_ok.year))      
                fecha_ok += relativedelta(months=1)
            
            print("fechas_iteradas",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            for month, year in fechas_iteradas:
                print(f"Año: {year}, Mes: {month}")
            
            renta = info["datos_contratos"]
            if renta.get("renta"):
                print("vengo desde pagare Sin Poliza")
                #obtenermos la renta para pasarla a letra
                if "." not in info["datos_contratos"]['renta']:
                    print("no hay yaya")
                    number = int(info["datos_contratos"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    renta_completa = info["datos_contratos"]['renta'].split(".")
                    info.renta = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
            else:
                print("vengo desde poliza o arrendamiento con una propiedad existente")
                inmueble = info["inmueble"]
                if inmueble.get("inmueble"):
                    propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                    info["inmueble"] = propiedad
                    #checamos que no tenga decimales
                    if "." not in str(propiedad.renta):
                        number = int(propiedad.renta)
                        renta_decimal = "00"
                        text_representation = num2words(number, lang='es').capitalize()
                    else:
                        print("tengo punto en renta pendiente de saber que hacer")
                else: 
                    if "." not in str(info["inmueble"]["renta"]):
                        print("no hay yaya")
                        number = int(info["inmueble"]["renta"])
                        renta_decimal = "00"
                        text_representation = num2words(number, lang='es').capitalize()
                    else:
                        print("tengo punto en renta pendiente de saber que hacer")
                    
            print("")
            print(f"renta {number}, letra: {text_representation}")
            #imprimir el nombre de la las fechas
            print("fechas_iteradas",fechas_iteradas)
            print("fechas_iteradas como diccionario",dict(fechas_iteradas))
            
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'renta_decimal':renta_decimal}
            
            template = 'home/dash/pagare_prueba_completos.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
        
           
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_preview_pagare(self, request, *args, **kwargs):  
        try:
            print("Generar pagare preview")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            arrendatario = dict(info["arrendatario"]) 
            if arrendatario.get("inquilino"):
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                info["arrendatario"] = inquilino

            aval = dict(info["fiador"])         
            if aval.get("aval"):
                print("hay informacion del aval hay que hacer una busqueda de id")
                fiador = Aval.objects.all().filter(id = info["fiador"]["aval"]).first()
                info["fiador"] = fiador
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
                

            print("Esto es el request data.",info)
            print("")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(fecha_inicial, "%Y-%m-%d").date()
            print("fecha OK",fecha_inicial)
          
            dia = fecha_ok.day
            
            print("")
            print("dia",dia)
            
            # Definir la duración en meses
            
            duracion_meses = int(info["datos_contratos"]['duracion'])
            print("duracion en meses",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_ok + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_ok < fecha_final:
                nombre_mes = fecha_ok.strftime("%B")  # %B da el nombre completo del mes
                print("fecha",fecha_ok.year)
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_ok.year))      
                fecha_ok += relativedelta(months=1)
            
            print("fechas_iteradas",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            for month, year in fechas_iteradas:
                print(f"Año: {year}, Mes: {month}")
                
            #obtenermos la renta para pasarla a letra
            propiedad = dict(info["inmueble"])  
            if propiedad.get("renta"):
                print("vengo desde pagare Sin Poliza")
                #obtenermos la renta para pasarla a letra
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    renta_completa = info["datos_contratos"]['renta'].split(".")
                    info.renta = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
            else:
                print("vengo desde inmueble con poliza")
                #propiedad = Inmuebles.objects.all()
                propiedad = dict(info["inmueble"])  
                #info["inmueble"] = propiedad 
                print("Datos Inmueble Pagare:",propiedad)
                
                #checamos que no tenga decimales
                
                if "." not in str(propiedad.renta):
                    print("no hay yaya")
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
            
            print("")
            print(f"renta {number}, letra: {text_representation}")
            #imprimir el nombre de la las fechas
            print("fechas_iteradas",fechas_iteradas)
            print("fechas_iteradas como diccionario",dict(fechas_iteradas))
                        
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'renta_decimal':renta_decimal}
            
            template = 'home/dash/pagare_prueba.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_preview_contrato_arrendamiento(self, request, *args, **kwargs):  
        try:
            print("")
            print("Generar contrato preview")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            arrendatario = dict(info["arrendatario"]) 
            print("soy el arrendatario vamos a ver quye pdo",arrendatario)
            if arrendatario.get("inquilino"):
                print("hay informacion del arrendatarios hay que hacer una busqueda de id")
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                # print("Inquilino", inquilino)

                info["arrendatario"] = inquilino

            aval = dict(info["fiador"])         
            
            if aval.get("aval"):
                print("hay informacion del aval hay que hacer una busqueda de id")
                fiador = Aval.objects.all().filter(id = info["fiador"]["aval"]).first()
                info["fiador"] = fiador
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
            
             
            inmueble= dict(info["inmueble"])
            print("Esto es el inmueble", inmueble) 
            if inmueble.get("inmueble"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                print("nombre del arrendatario",propiedad.__dict__)
                print("mi renta es",propiedad.renta)
                info["inmueble"] = propiedad
                #checamos que no tenga decimales
                if "." not in str(propiedad.renta):
                    print("no hay yaya")
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
                    
            else:
                print("no hay informacion del inmueble")
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()

            print("Esto es el request data.",info)
            print("")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(info["datos_contratos"]['fecha_celebracion'], "%Y-%m-%d").date()
            fecha_off = datetime.strptime(info["datos_contratos"]['fecha_termino'], "%Y-%m-%d").date()
            print("fecha OK",fecha_inicial)
          
         
            datos_inicio = {'dia':fecha_ok.day, 'mes':fecha_ok.strftime("%B").upper() ,'anio':fecha_ok.year}
            datos_termino = {'dia':fecha_off.day, 'mes':fecha_off.strftime("%B").upper()  ,'anio':fecha_off.year}
            
            
            # Definir la duración en meses
            
            duracion_meses = int(info["datos_contratos"]['duracion'])
            print("duracion en meses",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_ok + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_ok < fecha_final:
                nombre_mes = fecha_ok.strftime("%B")  # %B da el nombre completo del mes
                print("fecha",fecha_ok.year)
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_ok.year))      
                fecha_ok += relativedelta(months=1)
            
            print("fechas_iteradas",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            for month, year in fechas_iteradas:
                print(f"Año: {year}, Mes: {month}")
                
            # obtenermos la renta para pasarla a letra            
            print("")
            print(f"renta {number}, letra: {text_representation}")
            #imprimir el nombre de la las fechas
            print("fechas_iteradas",fechas_iteradas)
            print("fechas_iteradas como diccionario",dict(fechas_iteradas))
                        
            context = {'info': info,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'renta_decimal':renta_decimal, "datos_inicio":datos_inicio, 'datos_termino':datos_termino}
            
            template = 'home/dash/contrato_arrendamiento_preview.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
             
    def generar_contrato_arrendamiento(self, request, *args, **kwargs):  
        try:
            print("")
            print("Generar contrato preview")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            arrendatario = dict(info["arrendatario"]) 
            print("soy el arrendatario vamos a ver quye pdo",arrendatario)
            if arrendatario.get("inquilino"):
                print("hay informacion del arrendatarios hay que hacer una busqueda de id")
                print("Inquilino ID", info["arrendatario"]["inquilino"])
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                print("Inquilino", inquilino)

                info["arrendatario"] = inquilino

            aval = dict(info["fiador"])         
            if aval.get("aval"):
                print("hay informacion del aval hay que hacer una busqueda de id")
                fiador = Aval.objects.all().filter(id = info["fiador"]["aval"]).first()
                info["fiador"] = fiador
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
            
             
            propiedad= dict(info["inmueble"])
            print("Esto es el inmueble", propiedad) 
            if propiedad.get("renta"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                propiedad = Inmuebles.objects.all()
                print("nombre del arrendatario",propiedad.__dict__)
                print("mi renta es",info["inmueble"]["renta"])
                #esto es lo nuevo en mantenimiento
                if info["inmueble"]["mantenimiento"] == "No Incluido":
                    pass
                    # info["inmueble"]["cuota_letra"] == num2words(propiedad.cuota_mantenimiento, lang='es').capitalize()
                    # print("cuota con letra", info["inmueble"]["cuota_letra"])
                
                #checamos que no tenga decimales
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
                    
            else:
                #esto es lo nuevo en mantenimiento
                if info["inmueble"]["mantenimiento"] == "No Incluido":
                    info["inmueble"]["cuota_letra"] == num2words(info["inmueble"]["cuota_mantenimiento"], lang='es').capitalize()
                    print("cuota con letra", info["inmueble"]["cuota_letra"])
                
                print("no hay informacion del inmueble")
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()

            print("Esto es el request data.",info)
            print("")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(info["datos_contratos"]['fecha_celebracion'], "%Y-%m-%d").date()
            fecha_off = datetime.strptime(info["datos_contratos"]['fecha_termino'], "%Y-%m-%d").date()
            print("fecha OK",fecha_inicial)
          
            datos_inicio = {'dia':fecha_ok.day, 'mes':fecha_ok.strftime("%B").upper() ,'anio':fecha_ok.year}
            datos_termino = {'dia':fecha_off.day, 'mes':fecha_off.strftime("%B").upper()  ,'anio':fecha_off.year}
            
            # obtenermos la renta para pasarla a letra            
            print("")
            print(f"renta {number}, letra: {text_representation}")
            
            #si tiene mantenimiento incluido hay que pasarlo a letra
                        
            context = {'info': info, 'text_representation':text_representation, 'renta_decimal':renta_decimal, "datos_inicio":datos_inicio, 'datos_termino':datos_termino}
            
            template = 'home/dash/contrato_arrendamiento.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Contrato_arrendamiento.pdf"'
            response.write(pdf_file)
            print("Se genero el contrato")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_preview_poliza(self, request, *args, **kwargs):
        try:
            print("")
            print("Generar Poliza")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data
            
            print("")
            print("Esto es el request data.",info)
            print("")

            arrendatario = dict(info["arrendatario"]) 
            print("soy el arrendatario vamos a ver quye pdo",arrendatario)
            if arrendatario.get("inquilino"):
                print("hay informacion del arrendatarios hay que hacer una busqueda de id")
                print("Inquilino ID", info["arrendatario"]["inquilino"])
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                print("Inquilino", inquilino)
                info["arrendatario"] = inquilino

            aval = dict(info["fiador"])         
            if aval.get("aval"):
                print("hay informacion del aval hay que hacer una busqueda de id")
                fiador = Aval.objects.all().filter(id = info["fiador"]["aval"]).first()
                info["fiador"] = fiador
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
            
             
            inmueble= dict(info["inmueble"])
            print("Esto es el inmueble", inmueble) 
            
            if inmueble.get("inmueble"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                
                #checamos que no tenga decimales
                
                if "." not in str(propiedad.renta):
                    print("no hay yaya")
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
                    # if info["inmueble"]['renta']:
                    #     renta_completa = info["inmueble"]['renta'].split(".")
                    # else:
                    #     renta_completa = propiedad.renta.split(".")
                    
                    # info["inmueble"]['renta'] = renta_completa[0]
                    # renta_decimal = renta_completa[1]
                    # text_representation = num2words(renta_completa[0], lang='es').capitalize()
                
                print("hay que sacar sus impuestos")
                info["inmueble"] = propiedad  
                impuestos = propiedad.impuestos  
            else: #ahora si no hay inmueble registrado
                print("no hay informacion del inmueble")
                print("hay que sacar sus impuestos",info["inmueble"]['impuestos'])
                impuestos = info["inmueble"]['impuestos']
                
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    # if info["inmueble"]['renta']:
                    #     renta_completa = info["inmueble"]['renta'].split(".")
                    # else:
                    #     renta_completa = propiedad.renta.split(".")
                    
                    # info["inmueble"]['renta'] = renta_completa[0]
                    # renta_decimal = renta_completa[1]
                    # text_representation = num2words(renta_completa[0], lang='es').capitalize()

            # obtenermos el monto de la poliza
            plata = 3920 
            oro = 4900
            platino = 9800
            if info["tipo_poliza"] == "Plata":
                #Declaramos el template
                template = 'home/dash/poliza_plata_preview.html'
                #Despues evaluamos el impueto y el valos de la poliza
                if number <= 14000:
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = plata + (plata*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = plata
                else:
                    total_poliza = (number * 0.28)
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = total_poliza + (total_poliza*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = total_poliza
                    
            elif info["tipo_poliza"] == "Oro":
                #Declaramos el template
                template = 'home/dash/poliza_oro.html'
                #Despues evaluamos el impueto y el valos de la poliza
                if number <= 14000:
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = oro + (oro*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = oro
                else:
                    total_poliza = (number * 0.35)
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = total_poliza + (total_poliza*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = total_poliza
            
            elif info["tipo_poliza"] == "Platino":
                #Declaramos el template
                template = 'home/dash/poliza_platino.html'
                #Despues evaluamos el impueto y el valos de la poliza
                if number <= 14000:
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = platino + (platino*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = platino
                else:
                    total_poliza = (number * 0.70);
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = total_poliza + (total_poliza*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = total_poliza
                        
            # obtenermos la renta para pasarla a letra        
                
            print("")
            print(f"renta {number}, letra: {text_representation}")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(info["datos_contratos"]['fecha_celebracion'], "%Y-%m-%d").date()
            fecha_off = datetime.strptime(info["datos_contratos"]['fecha_termino'], "%Y-%m-%d").date()
            fecha_firma = datetime.strptime(info["datos_contratos"]['fecha_firma'], "%Y-%m-%d").date()
             
            print("fecha OK",fecha_inicial)
          
            datos_inicio = {'dia':fecha_ok.day, 'mes':fecha_ok.strftime("%B").upper() ,'anio':fecha_ok.year}
            datos_termino = {'dia':fecha_off.day, 'mes':fecha_off.strftime("%B").upper()  ,'anio':fecha_off.year}
            datos_firma = {'dia':fecha_firma.day, 'mes':fecha_firma.strftime("%B").capitalize()  ,'anio':fecha_firma.year}
            
            #obtenermos el precio de la poliza para pasarla a letra
            precio = int(info["datos_contratos"]["monto_total"])
           
            print("Mi precio es: ",precio)
            precio_texto = num2words(precio, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            precio_texto = precio_texto.capitalize()
            
        
            context = {'info': info, 'text_representation':text_representation, 'renta_decimal':renta_decimal, "datos_inicio":datos_inicio, 'datos_termino':datos_termino,'precio_texto':precio_texto,'datos_firma':datos_firma}
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Contrato_arrendamiento.pdf"'
            response.write(pdf_file)
            print("Se genero el contrato")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_poliza(self, request, *args, **kwargs):
        try:
            print("")
            print("Generar Poliza")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data
            
            
            print("")
            print("Esto es el request data.",info)
            print("")

            arrendatario = dict(info["arrendatario"]) 
            print("soy el arrendatario vamos a ver quye pdo",arrendatario)
            if arrendatario.get("inquilino"):
                print("hay informacion del arrendatarios hay que hacer una busqueda de id")
                print("Inquilino ID", info["arrendatario"]["inquilino"])
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                print("Inquilino", inquilino)
                info["arrendatario"] = inquilino

            aval = dict(info["fiador"])         
            if aval.get("aval"):
                print("hay informacion del aval hay que hacer una busqueda de id")
                fiador = Aval.objects.all().filter(id = info["fiador"]["aval"]).first()
                info["fiador"] = fiador
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
            
             
            inmueble= dict(info["inmueble"])
            print("Esto es el inmueble", inmueble) 
            
            if inmueble.get("inmueble"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                
                #checamos que no tenga decimales
                
                if "." not in str(propiedad.renta):
                    print("no hay yaya")
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
                    # if info["inmueble"]['renta']:
                    #     renta_completa = info["inmueble"]['renta'].split(".")
                    # else:
                    #     renta_completa = propiedad.renta.split(".")
                    
                    # info["inmueble"]['renta'] = renta_completa[0]
                    # renta_decimal = renta_completa[1]
                    # text_representation = num2words(renta_completa[0], lang='es').capitalize()
                
                print("hay que sacar sus impuestos")
                info["inmueble"] = propiedad  
                impuestos = propiedad.impuestos  
            else: #ahora si no hay inmueble registrado
                print("no hay informacion del inmueble")
                print("hay que sacar sus impuestos",info["inmueble"]['impuestos'])
                impuestos = info["inmueble"]['impuestos']
                
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    # if info["inmueble"]['renta']:
                    #     renta_completa = info["inmueble"]['renta'].split(".")
                    # else:
                    #     renta_completa = propiedad.renta.split(".")
                    
                    # info["inmueble"]['renta'] = renta_completa[0]
                    # renta_decimal = renta_completa[1]
                    # text_representation = num2words(renta_completa[0], lang='es').capitalize()

            # obtenermos el monto de la poliza
            plata = 3920 
            oro = 4900
            platino = 9800
            if info["tipo_poliza"] == "Plata":
                #Declaramos el template
                template = 'home/dash/poliza_plata.html'
                #Despues evaluamos el impueto y el valos de la poliza
                if number <= 14000:
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = plata + (plata*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = plata
                else:
                    total_poliza = (number * 0.28)
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = total_poliza + (total_poliza*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = total_poliza
                    
            elif info["tipo_poliza"] == "Oro":
                #Declaramos el template
                template = 'home/dash/poliza_oro.html'
                #Despues evaluamos el impueto y el valos de la poliza
                if number <= 14000:
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = oro + (oro*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = oro
                else:
                    total_poliza = (number * 0.35)
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = total_poliza + (total_poliza*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = total_poliza
            
            elif info["tipo_poliza"] == "Platino":
                #Declaramos el template
                template = 'home/dash/poliza_platino.html'
                #Despues evaluamos el impueto y el valos de la poliza
                if number <= 14000:
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = platino + (platino*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = platino
                else:
                    total_poliza = (number * 0.70);
                    if impuestos == "Si":
                        info["datos_contratos"]["monto_total"] = total_poliza + (total_poliza*0.16)
                    else:
                        info["datos_contratos"]["monto_total"] = total_poliza
                        
            # obtenermos la renta para pasarla a letra        
                
            print("")
            print(f"renta {number}, letra: {text_representation}")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(info["datos_contratos"]['fecha_celebracion'], "%Y-%m-%d").date()
            fecha_off = datetime.strptime(info["datos_contratos"]['fecha_termino'], "%Y-%m-%d").date()
            fecha_firma = datetime.strptime(info["datos_contratos"]['fecha_firma'], "%Y-%m-%d").date()
             
            print("fecha OK",fecha_inicial)
         
            datos_inicio = {'dia':fecha_ok.day, 'mes':fecha_ok.strftime("%B").upper() ,'anio':fecha_ok.year}
            datos_termino = {'dia':fecha_off.day, 'mes':fecha_off.strftime("%B").upper()  ,'anio':fecha_off.year}
            datos_firma = {'dia':fecha_firma.day, 'mes':fecha_firma.strftime("%B").capitalize()  ,'anio':fecha_firma.year}

            print("datos_inicio",datos_inicio["mes"])
            nombre_mes = fecha_ok.strftime("%B").capitalize()
            print("nombre del mes",nombre_mes)
            
            #obtenermos el precio de la poliza para pasarla a letra
            precio = int(info["datos_contratos"]["monto_total"])
           
            print("Mi precio es: ",precio)
            precio_texto = num2words(precio, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            precio_texto = precio_texto.capitalize()
            
        
            context = {'info': info, 'text_representation':text_representation, 'renta_decimal':renta_decimal, "datos_inicio":datos_inicio, 'datos_termino':datos_termino,'precio_texto':precio_texto,'datos_firma':datos_firma}
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Contrato_arrendamiento.pdf"'
            response.write(pdf_file)
            print("Se genero el contrato")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_corretaje_preview(self, request, *args, **kwargs):  
        try:
            print("Generar corretaje")
            # user_session = request.user
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador

            inmueble= dict(info["inmueble"])
            print("Esto es el inmueble", inmueble) 
            if inmueble.get("inmueble"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                info["inmueble"] = propiedad
                #esto es lo nuevo en mantenimiento
          
            context = {'info': info}
            
            template = 'home/dash/contrato_corretaje_preview.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="contrato_corretaje.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
        
           
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_corretaje(self, request, *args, **kwargs):  
        try:
            print("Generar corretaje")
            # user_session = request.user
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            propietario = dict(info["arrendador"])
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador

            inmueble= dict(info["inmueble"])
            print("Esto es el inmueble", inmueble)
            if inmueble.get("inmueble"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                info["inmueble"] = propiedad
                #esto es lo nuevo en mantenimiento
          
            context = {'info': info}
        
            template = 'home/dash/contrato_corretaje.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="contrato_corretaje.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
           
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_contrato_comodato_preview(self, request, *args, **kwargs):  
        try:
            print("")
            print("Generar contrato comodato")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            arrendatario = dict(info["arrendatario"]) 
            print("soy el arrendatario vamos a ver quye pdo",arrendatario)
            if arrendatario.get("inquilino"):
                print("hay informacion del arrendatarios hay que hacer una busqueda de id")
                print("Inquilino ID", info["arrendatario"]["inquilino"])
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                print("Inquilino", inquilino)
                info["arrendatario"] = inquilino
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
            
             
            inmueble= dict(info["inmueble"])
            print("Esto es el inmueble", inmueble) 
            if inmueble.get("inmueble"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                print("nombre del arrendatario",propiedad.__dict__)
                print("mi renta es",propiedad.renta)
                info["inmueble"] = propiedad
                #esto es lo nuevo en mantenimiento
                if propiedad.mantenimiento == "No Incluido":
                    pass
                    # info["inmueble"]["cuota_letra"] == num2words(propiedad.cuota_mantenimiento, lang='es').capitalize()
                    # print("cuota con letra", info["inmueble"]["cuota_letra"])
                
                #checamos que no tenga decimales
                if "." not in str(propiedad.renta):
                    print("no hay yaya")
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
                    
            else:
                #esto es lo nuevo en mantenimiento
                if info["inmueble"]["mantenimiento"] == "No Incluido":
                    info["inmueble"]["cuota_letra"] == num2words(info["inmueble"]["cuota_mantenimiento"], lang='es').capitalize()
                    print("cuota con letra", info["inmueble"]["cuota_letra"])
                
                print("no hay informacion del inmueble")
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()

            print("Esto es el request data.",info)
            print("")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(info["datos_contratos"]['fecha_celebracion'], "%Y-%m-%d").date()
            fecha_off = datetime.strptime(info["datos_contratos"]['fecha_termino'], "%Y-%m-%d").date()
            print("fecha OK",fecha_inicial)
          
            datos_inicio = {'dia':fecha_ok.day, 'mes':fecha_ok.strftime("%B").upper() ,'anio':fecha_ok.year}
            datos_termino = {'dia':fecha_off.day, 'mes':fecha_off.strftime("%B").upper()  ,'anio':fecha_off.year}
            
            # obtenermos la renta para pasarla a letra            
            print("")
            print(f"renta {number}, letra: {text_representation}")
            
            #si tiene mantenimiento incluido hay que pasarlo a letra
                        
            context = {'info': info, 'text_representation':text_representation, 'renta_decimal':renta_decimal, "datos_inicio":datos_inicio, 'datos_termino':datos_termino}
            
            template = 'home/dash/contrato_comodato.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Contrato_arrendamiento.pdf"'
            response.write(pdf_file)
            print("Se genero el contrato")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_contrato_comodato(self, request, *args, **kwargs):  
        try:
            print("")
            print("Generar contrato comodato")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            arrendatario = dict(info["arrendatario"]) 
            print("soy el arrendatario vamos a ver quye pdo",arrendatario)
            if arrendatario.get("inquilino"):
                print("hay informacion del arrendatarios hay que hacer una busqueda de id")
                print("Inquilino ID", info["arrendatario"]["inquilino"])
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                print("Inquilino", inquilino)

                info["arrendatario"] = inquilino

            # aval = dict(info["fiador"])         
            # if aval.get("aval"):
            #     print("hay informacion del aval hay que hacer una busqueda de id")
            #     fiador = Aval.objects.all().filter(id = info["fiador"]["aval"]).first()
            #     info["fiador"] = fiador
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
            
             
            inmueble= dict(info["inmueble"])
            print("Esto es el inmueble", inmueble) 
            if inmueble.get("inmueble"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                print("nombre del arrendatario",propiedad.__dict__)
                print("mi renta es",propiedad.renta)
                info["inmueble"] = propiedad
                #esto es lo nuevo en mantenimiento
                if propiedad.mantenimiento == "No Incluido":
                    pass
                    # info["inmueble"]["cuota_letra"] == num2words(propiedad.cuota_mantenimiento, lang='es').capitalize()
                    # print("cuota con letra", info["inmueble"]["cuota_letra"])
                
                #checamos que no tenga decimales
                if "." not in str(propiedad.renta):
                    print("no hay yaya")
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
                    
            else:
                #esto es lo nuevo en mantenimiento
                if info["inmueble"]["mantenimiento"] == "No Incluido":
                    info["inmueble"]["cuota_letra"] == num2words(info["inmueble"]["cuota_mantenimiento"], lang='es').capitalize()
                    print("cuota con letra", info["inmueble"]["cuota_letra"])
                
                print("no hay informacion del inmueble")
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()

            print("Esto es el request data.",info)
            print("")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(info["datos_contratos"]['fecha_celebracion'], "%Y-%m-%d").date()
            fecha_off = datetime.strptime(info["datos_contratos"]['fecha_termino'], "%Y-%m-%d").date()
            print("fecha OK",fecha_inicial)
          
            datos_inicio = {'dia':fecha_ok.day, 'mes':fecha_ok.strftime("%B").upper() ,'anio':fecha_ok.year}
            datos_termino = {'dia':fecha_off.day, 'mes':fecha_off.strftime("%B").upper()  ,'anio':fecha_off.year}
            
            # obtenermos la renta para pasarla a letra            
            print("")
            print(f"renta {number}, letra: {text_representation}")
            
            #si tiene mantenimiento incluido hay que pasarlo a letra
                        
            context = {'info': info, 'text_representation':text_representation, 'renta_decimal':renta_decimal, "datos_inicio":datos_inicio, 'datos_termino':datos_termino}
            
            template = 'home/dash/contrato_comodato.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Contrato_Comodato.pdf"'
            response.write(pdf_file)
            print("Se genero el contrato")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_compraventa_preview(self, request, *args, **kwargs):  
        try:
            print("Generar compraventa")
            # user_session = request.user
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            # Definir la fecha inicial
            fecha_entrega = datetime.strptime(info["datos_contratos"]['fecha_entrega'], "%Y-%m-%d").date()

          
            datos_entrega = {'dia':fecha_entrega.day, 'mes':fecha_entrega.strftime("%B") ,'anio':fecha_entrega.year}
          
            context = {'info': info, 'datos_entrega':datos_entrega}
        
            template = 'home/dash/contrato_compraventa_preview.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="contrato_corretaje.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
           
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_compraventa(self, request, *args, **kwargs):  
        try:
            print("Generar compraventa")
            # user_session = request.user
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            # Definir la fecha inicial
            fecha_entrega = datetime.strptime(info["datos_contratos"]['fecha_entrega'], "%Y-%m-%d").date()

          
            datos_entrega = {'dia':fecha_entrega.day, 'mes':fecha_entrega.strftime("%B") ,'anio':fecha_entrega.year}
          
            context = {'info': info, 'datos_entrega':datos_entrega}
        
            template = 'home/dash/contrato_compraventa.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="contrato_corretaje.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
           
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_promesa_preview(self, request, *args, **kwargs):  
        try:
            print("Generar promesa")
            # user_session = request.user
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data
            print("info",info)
            context = {'info': info}
        
            template = 'home/dash/contrato_promesa_preview.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="contrato_promesa.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
           
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_promesa(self, request, *args, **kwargs):  
        try:
            print("Generar promesa")
            # user_session = request.user
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data
            print("info",info)
            context = {'info': info}
        
            template = 'home/dash/contrato_promesa.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="contrato_promesa.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
           
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_renta_op_venta_preview(self, request, *args, **kwargs):  
        try:
            print("Generar renta op venta preview")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            arrendatario = dict(info["arrendatario"]) 
            if arrendatario.get("inquilino"):
                print("hay informacion del arrendatarios hay que hacer una busqueda de id")
                print("Inquilino ID", info["arrendatario"]["inquilino"])
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                print("Inquilino", inquilino)
                info["arrendatario"] = inquilino
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
            
            inmueble= dict(info["inmueble"])
            print("Esto es el inmueble", inmueble) 
            if inmueble.get("inmueble"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                print("nombre del arrendatario",propiedad.__dict__)
                print("mi renta es",propiedad.renta)
                info["inmueble"] = propiedad
                #esto es lo nuevo en mantenimiento
                if propiedad.mantenimiento == "No Incluido":
                    pass
                    # info["inmueble"]["cuota_letra"] == num2words(propiedad.cuota_mantenimiento, lang='es').capitalize()
                    # print("cuota con letra", info["inmueble"]["cuota_letra"])
                
                #checamos que no tenga decimales
                if "." not in str(propiedad.renta):
                    print("no hay yaya")
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
                    
            else:
                #esto es lo nuevo en mantenimiento
                if info["inmueble"]["mantenimiento"] == "No Incluido":
                    info["inmueble"]["cuota_letra"] == num2words(info["inmueble"]["cuota_mantenimiento"], lang='es').capitalize()
                    print("cuota con letra", info["inmueble"]["cuota_letra"])
                
                print("no hay informacion del inmueble")
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()

            print("Esto es el request data.",info)
            print("")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(info["datos_contratos"]['fecha_celebracion'], "%Y-%m-%d").date()
            fecha_off = datetime.strptime(info["datos_contratos"]['fecha_termino'], "%Y-%m-%d").date()
            print("fecha OK",fecha_inicial)
          
            datos_inicio = {'dia':fecha_ok.day, 'mes':fecha_ok.strftime("%B"),'anio':fecha_ok.year}
            datos_termino = {'dia':fecha_off.day, 'mes':fecha_off.strftime("%B"),'anio':fecha_off.year}
            
            # obtenermos la renta para pasarla a letra            
            print("")
            print(f"renta {number}, letra: {text_representation}")
            
            #si tiene mantenimiento incluido hay que pasarlo a letra
                        
            context = {'info': info, 'text_representation':text_representation, 'renta_decimal':renta_decimal, "datos_inicio":datos_inicio, 'datos_termino':datos_termino}
            
            template = 'home/dash/contrato_renta_op_venta_preview.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Contrato.pdf"'
            response.write(pdf_file)
            print("Se genero el contrato")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_renta_op_venta(self, request, *args, **kwargs):  
        try:
            print("Generar renta op venta")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data
            arrendatario = dict(info["arrendatario"]) 

            if arrendatario.get("inquilino"):
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                info["arrendatario"] = inquilino
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
            
            inmueble= dict(info["inmueble"])
            print("Esto es el inmueble", inmueble) 
            if inmueble.get("inmueble"):
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                #esto es lo nuevo en mantenimiento
                if propiedad.mantenimiento == "No Incluido":
                    pass
                    # info["inmueble"]["cuota_letra"] == num2words(propiedad.cuota_mantenimiento, lang='es').capitalize()
                    # print("cuota con letra", info["inmueble"]["cuota_letra"])
                
                #checamos que no tenga decimales
                if "." not in str(propiedad.renta):
                    print("no hay yaya")
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
                    
            else:
                #esto es lo nuevo en mantenimiento
                if info["inmueble"]["mantenimiento"] == "No Incluido":
                    info["inmueble"]["cuota_letra"] == num2words(info["inmueble"]["cuota_mantenimiento"], lang='es').capitalize()
                    
                
                print("no hay informacion del inmueble")
                if "." not in info["inmueble"]['renta']:
                    print("no hay yaya")
                    number = int(info["inmueble"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    if info["inmueble"]['renta']:
                        renta_completa = info["inmueble"]['renta'].split(".")
                    else:
                        renta_completa = propiedad.renta.split(".")
                    
                    info["inmueble"]['renta'] = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()

            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(info["datos_contratos"]['fecha_celebracion'], "%Y-%m-%d").date()
            fecha_off = datetime.strptime(info["datos_contratos"]['fecha_termino'], "%Y-%m-%d").date()
           
          
            datos_inicio = {'dia':fecha_ok.day, 'mes':fecha_ok.strftime("%B"),'anio':fecha_ok.year}
            datos_termino = {'dia':fecha_off.day, 'mes':fecha_off.strftime("%B"),'anio':fecha_off.year}
            
            #si tiene mantenimiento incluido hay que pasarlo a letra
                        
            context = {'info': info, 'text_representation':text_representation, 'renta_decimal':renta_decimal, "datos_inicio":datos_inicio, 'datos_termino':datos_termino}
            
            template = 'home/dash/contrato_renta_op_venta.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Contrato.pdf"'
            response.write(pdf_file)
            print("Se genero el contrato")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_preview_pagare_extra(self, request, *args, **kwargs):  
        try:
            print("Generar cotrato + pagare preview")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            arrendatario = dict(info["arrendatario"]) 
            if arrendatario.get("inquilino"):
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                info["arrendatario"] = inquilino
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
                
            print("Esto es el request data.",info)
            print("")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(fecha_inicial, "%Y-%m-%d").date()
            print("fecha OK",fecha_inicial)
          
            dia = fecha_ok.day
            
            print("")
            print("dia",dia)
            
            # Definir la duración en meses
            
            duracion_meses = int(info["datos_contratos"]['duracion'])
            print("duracion en meses",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_ok + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_ok < fecha_final:
                nombre_mes = fecha_ok.strftime("%B")  # %B da el nombre completo del mes
                print("fecha",fecha_ok.year)
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_ok.year))      
                fecha_ok += relativedelta(months=1)
            
            print("fechas_iteradas",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            # for month, year in fechas_iteradas:
            #     print(f"Año: {year}, Mes: {month}")
                
            #obtenermos la renta para pasarla a letra
            renta = info["datos_contratos"]
            if renta.get("renta"):
                print("vengo desde pagare Sin Poliza")
                #obtenermos la renta para pasarla a letra
                if "." not in info["datos_contratos"]['renta']:
                    print("no hay yaya")
                    number = int(info["datos_contratos"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    renta_completa = info["datos_contratos"]['renta'].split(".")
                    info.renta = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
            else:
                print("vengo desde inmueble con poliza")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                info["inmueble"] = propiedad 
                print("spy datos del inmueble en pagare-poliza",info["inmueble"])
                
                #checamos que no tenga decimales
                
                if "." not in str(propiedad.renta):
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
            
            print("")
            print(f"renta {number}, letra: {text_representation}")
            #imprimir el nombre de la las fechas
            print("fechas_iteradas",fechas_iteradas)
            print("fechas_iteradas como diccionario",dict(fechas_iteradas))
                        
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'renta_decimal':renta_decimal}
            
            template = 'home/dash/pagare_extra_preview.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_pagare_extra(self, request, *args, **kwargs):  
        try:
            print("Generar cotrato + pagare preview")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            info = request.data

            arrendatario = dict(info["arrendatario"]) 
            if arrendatario.get("inquilino"):
                inquilino = Arrendatario.objects.all().filter(id = info["arrendatario"]["inquilino"]).first()
                info["arrendatario"] = inquilino
            
            propietario = dict(info["arrendador"])        
            if propietario.get("propietario"):
                print("hay informacion del propietario hay que hacer una busqueda de id")
                arrendador = Propietario.objects.all().filter(id = info["arrendador"]["propietario"]).first()
                info["arrendador"] = arrendador
                
            print("Esto es el request data.",info)
            print("")
            
            # Definir la fecha inicial
            fecha_inicial = info["datos_contratos"]['fecha_celebracion']
            fecha_ok = datetime.strptime(fecha_inicial, "%Y-%m-%d").date()
            print("fecha OK",fecha_inicial)
          
            dia = fecha_ok.day
            
            print("")
            print("dia",dia)
            
            # Definir la duración en meses
            
            duracion_meses = int(info["datos_contratos"]['duracion'])
            print("duracion en meses",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_ok + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_ok < fecha_final:
                nombre_mes = fecha_ok.strftime("%B")  # %B da el nombre completo del mes
                print("fecha",fecha_ok.year)
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_ok.year))      
                fecha_ok += relativedelta(months=1)
            
            print("fechas_iteradas",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            # for month, year in fechas_iteradas:
            #     print(f"Año: {year}, Mes: {month}")
                
            #obtenermos la renta para pasarla a letra
            renta = info["datos_contratos"]
            if renta.get("renta"):
                print("vengo desde pagare Sin Poliza")
                #obtenermos la renta para pasarla a letra
                if "." not in info["datos_contratos"]['renta']:
                    print("no hay yaya")
                    number = int(info["datos_contratos"]['renta'])
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                
                else:
                    print("tengo punto en renta")
                    renta_completa = info["datos_contratos"]['renta'].split(".")
                    info.renta = renta_completa[0]
                    renta_decimal = renta_completa[1]
                    text_representation = num2words(renta_completa[0], lang='es').capitalize()
            else:
                print("vengo desde inmueble con poliza")
                propiedad = Inmuebles.objects.all().filter(id = info["inmueble"]["inmueble"]).first()
                info["inmueble"] = propiedad 
                print("spy datos del inmueble en pagare-poliza",info["inmueble"])
                
                #checamos que no tenga decimales
                
                if "." not in str(propiedad.renta):
                    number = int(propiedad.renta)
                    renta_decimal = "00"
                    text_representation = num2words(number, lang='es').capitalize()
                else:
                    print("tengo punto en renta")
            
            print("")
            print(f"renta {number}, letra: {text_representation}")
            #imprimir el nombre de la las fechas
            print("fechas_iteradas",fechas_iteradas)
            print("fechas_iteradas como diccionario",dict(fechas_iteradas))
                        
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'renta_decimal':renta_decimal}
            
            template = 'home/dash/pagare_extra.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Se genero el preview")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(f"Hubo un error: {e} en la línea {exc_tb.tb_lineno}")
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)