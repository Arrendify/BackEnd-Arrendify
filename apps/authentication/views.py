# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login,logout
from django.contrib.sessions.models import Session
from datetime import datetime

from django.contrib.auth import authenticate

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView #da una vista al login generica

from ..accounts.models import CustomUser
User = CustomUser

from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from apps.authentication.serializers import UserTokenSerializer, CustomUserSerializer, UserListSerializer, User2Inmobiliaria, UserSerializer,User2Serializer
from rest_framework.decorators import api_view
#variables
from ..api.variables import *
#correo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from smtplib import SMTPException
from decouple import config

#ZOHO
import json
import random
import string



class UserToken(APIView):
    def get(self, request, *args, **kwargs):
        username = request.GET.get('username')
        print(username)
        try:
            user_token = Token.objects.get(user = UserTokenSerializer().Meta.model.objects.filter(username = username).first())
            return Response({'token': user_token.key})
        except:
            return Response({'error':'Credenciales enviadas incorrectas'},status=status.HTTP_400_BAD_REQUEST)
            

class Login(ObtainAuthToken):
  
    def post(self, request, *args, **kwargs):
        
        print("soy el request del lg",request.data)
        login_serializer = self.serializer_class(data = request.data, context = {'request': request})
       
        if login_serializer.is_valid():
            print("paso validacion")
            user = login_serializer.validated_data['user']
            print("soy el query user",user)
            if user.is_active:
                print("estoy activo",user)
                token,created = Token.objects.get_or_create(user = user)
                user_serilizer = UserTokenSerializer(user)
                inmobiliaria_user = User2Inmobiliaria(user)
                arrendify_user = User2Serializer(user)

                print("YO SOY USER",user)
                if created:
                     if inmobiliaria_user.data['rol'] == "Inmobiliaria" or inmobiliaria_user.data['rol'] == "Agente":
                        print("estoy entrando a inmo")
                        return Response({'token':token.key, 
                                      'user':inmobiliaria_user.data,
                                      'type':'Token',
                                      'message': 'Inicio de Sesion Existoso'
                                      },status=status.HTTP_201_CREATED)
                     elif arrendify_user.data['is_staff'] == True:
                        print("SOY STAFF")
                        return Response({'token':token.key, 
                                      'user':arrendify_user.data,
                                      'type':'Token',
                                      'message': 'Inicio de Sesion Existoso'
                                      },status=status.HTTP_201_CREATED)
                     else:
                        print("Soy Normalito")
                        return Response({'token':token.key, 
                                      'user':user_serilizer.data,
                                      'type':'Token',
                                      'message': 'Inicio de Sesion Existoso'
                                      },status=status.HTTP_201_CREATED)
                else:
                    #all_sessions = Session.objects.filter(expire_date__gte = datetime.now())
                    # if all_sessions.exists():
                    #     for session in all_sessions:
                    #         session_data = session.get_decoded()
                    #         if user.id == int(session_data.get('_auth_user_id')):
                    #             session.delete()
                            
                    token.delete()
                    token = Token.objects.create(user = user)
                    return Response({'token':token.key, 
                                      'user':user_serilizer.data,
                                      'message': 'Inicio de Sesion Existoso'
                                      },status=status.HTTP_201_CREATED)
            else:
                 print('error: este user no puedes iniciar')
                 return Response({'error': 'este user no puedes iniciar'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            print('error: Contraseña o nombre de usuario incorrectos')
            return Response({'error': 'Contraseña o nombre de usuario incorrectos'}, status = status.HTTP_400_BAD_REQUEST)
        
        return Response({
                #'token': login_serializer.validated_data.get('access'),
                #'refresh-token': login_serializer.validated_data.get('refresh'),
                # 'user': user,
                'message': 'Hola'
            }, status=status.HTTP_200_OK)

class Logout(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self,request):
     #logout(request)
     print(request.user)
     request.user.auth_token.delete()
     return Response ({'msg':'cerró sesion'},status=status.HTTP_200_OK)
    
    #EN API NO LLEGA EL REQUEST.POST, SE DEBE USAR EL REQUEST.DATA PARA OBTENER LOS DATOS
    def get(self,request,*arg,**kwargs):
        #request.user.auth_token.delete()
        try:
            #token = request.GET.get('token') #para ebtener con query params
            token = request.data.get('token') #para obtener desde el body
            #token = request.META.get('HTTP_TOKEN')  # obtenemos el token desde los headers
            print("req",request.data)
            print("token",token)
            token = Token.objects.filter(key = token).first()
            if token:
                user = token.user
                print("usurio de token",user)
                #all_sessions = Session.objects.filter(expire_date__gte = datetime.now())
                    # if all_sessions.exists():
                    #     for session in all_sessions:
                    #         session_data = session.get_decoded()
                    #         if user.id == int(session_data.get('_auth_user_id')):
                    #             session.delete()
                #session_message = 'Sessiones de usuario eliminadas'
                token.delete()
                token_message = 'Token eliminado'
                return Response({'token_messge':token_message,'msg':'Session cerrada pa prrra'}, status= status.HTTP_200_OK)
        
            return Response({'error':'No se ah encontrado usuarios con estas credenciales'}, status= status.HTTP_400_BAD_REQUEST)
        except:
           #Logout(request)
           return Response({'error':'No se ah encontrado Token en la peticion'}, status= status.HTTP_409_CONFLICT)

class Register(APIView):
    #EN API NO LLEGA EL REQUEST.POST, SE DEBE USAR EL REQUEST.DATA PARA OBTENER LOS DATOS
    def post(self,request,*arg,**kwargs):
       user_serializar = UserSerializer(data = request.data)
       entrada = request.data     
       print("soy requesta data",entrada)
 
       #agregar comprobacion del codigo de arrendify proporcionado
       if request.data.get('password') == request.data.get('password2'):
           if user_serializar.is_valid():
               print("serializer valido")
               if entrada["rol"] == "Inmobiliaria": 
                    print("Soy Inmobiliaria")                  
                    user_serializar.save()
                    info = User.objects.all().get(username = entrada["username"])
                    self.enviar_codigo(info)
                    print("usuario guardado")
                
               elif entrada["rol"] == "Agente":
                    print("Soy Agente")
                    #consulta para buscar la inmobiliaria para el codigo
                    inmo_ag = User.objects.all().get(name_inmobiliaria = entrada["pertenece_a"])
                    codigo = entrada["c_inmobiliaria"]
                    if codigo == inmo_ag.code_inmobiliaria:
                        print("Bienvenido Agente, si tienes el codigo correcto")
                        user_serializar.save()
                        print("usuario guardado")
                    else:
                        return Response({'error':"El codigo que proporcionaste no es correcto", 'status':101})
                    
               elif entrada["rol"] == "Normal":
                   print("Normalito")
                   user_serializar.save()
                   print("usuario guardado")
                  
               print("ya voy a retornar la info")
               return Response(user_serializar.data)
       return Response({'error':user_serializar.errors, 'status':205})
    
    def enviar_codigo (self, info):
         #variable
            print("que onda")
            print("soy info despues de entrar al metodo",info)
            #hacemos una llamada a la base que nos devuelve el codigo
            print(info.__dict__)
            codigo = info.code_inmobiliaria
            email = info.email
            html = codigo_inmobiliaria(codigo)
            # Envío de la notificación por correo electrónico
            msg = MIMEMultipart()
            msg['From'] = 'notificaciones_arrendify@outlook.com'
            msg['To'] = email
            msg['Subject'] = 'Registro Exitoso - Tu código de inmobiaria'
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

@api_view(['GET'])
def user_unico(request):
    if request.method == 'GET':
        user = str(request.user)
        print(user)
        if user != 'AnonymousUser':
            print("entre estoy logeado")
            return Response({'user':True}, status= status.HTTP_200_OK)
    return Response({'user':False}, status= status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
def agente_inmobiliaria(request):
    if request.method == 'POST':
        print("entre al metodo")
        entrada_codigo = request.data["code_inmobiliaria"]
        print("entrada_codigo",entrada_codigo)
        inmobiliaria = User.objects.all().filter(code_inmobiliaria = entrada_codigo)
        Inmobiliaria_serializer = User2Inmobiliaria(inmobiliaria, many=True)
        return Response(Inmobiliaria_serializer.data)    
    return Response({'error':"No existe inmobiliarias"}, status= status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
def agente_inquilino(request):
    if request.method == 'POST':
        print("entre al metodo")
        entrada_codigo = request.data["code_agente"]
        print("entrada_codigo",entrada_codigo)
        inmobiliaria = User.objects.all().filter(code_agente = entrada_codigo)
        Inmobiliaria_serializer = User2Inmobiliaria(inmobiliaria, many=True)
        return Response(Inmobiliaria_serializer.data)    
    return Response({'error':"No existe inmobiliarias"}, status= status.HTTP_204_NO_CONTENT)

# @api_view(['GET'])
# def agente_inmobiliaria(request):
#     if request.method == 'GET':
#         print("entre al metodo")
#         inmobiliaria = User.objects.all().filter(rol = "Inmobiliaria")
#         Inmobiliaria_serializer = User2Inmobiliaria(inmobiliaria, many=True)
#         return Response(Inmobiliaria_serializer.data)    
#     return Response({'error':"No existe inmobiliarias"}, status= status.HTTP_204_NO_CONTENT)

import json
import random
import string

from django.core.mail import EmailMultiAlternatives

from django.http import JsonResponse
from django.core.mail import send_mail
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.test import APIRequestFactory

from .views import Register 

from threading import Thread
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from django.http import JsonResponse
from threading import Thread

class ZohoUser(APIView):
    @method_decorator(csrf_exempt, name='dispatch')
    def post(self, request):
        print("🔔 Webhook recibido de Zoho")
        print(f"📥 META: {request.META.get('REMOTE_ADDR')} - {request.META.get('HTTP_USER_AGENT')}")
        print(f"🔑 Headers: {dict(request.headers)}")
        try:
            # Intentamos capturar el cuerpo de la solicitud como raw data
            raw_body = request.body if hasattr(request, 'body') else None
            print(f"📦 Raw Body: {raw_body}")
            
            # Intentar parsear el contenido como JSON para mostrarlo en logs
            try:
                if raw_body:
                    body_json = json.loads(raw_body)
                    print(f"📋 JSON Body: {body_json}")
                else:
                    print(f"📋 POST Data: {request.POST}")
            except:
                print("⚠️ No se pudo parsear el cuerpo como JSON")
                
            # Iniciamos un hilo para procesar todo en segundo plano
            # Esto garantiza que respondamos inmediatamente a Zoho
            Thread(target=self._procesar_request, args=(raw_body, request)).start()
        except Exception as e:
            # Solo registramos el error, no afectamos la respuesta
            print(f"❌ Error al iniciar procesamiento: {str(e)}")
        
        # SIEMPRE respondemos 200 OK inmediatamente
        return JsonResponse({'status': 'success'}, status=200)
    
    def _procesar_request(self, raw_body, request):
        """Procesa la solicitud en segundo plano después de responder a Zoho"""
        try:
            # Extraer datos
            data = {}
            
            # Función para limpiar valores en formato ${valor}
            def limpiar_valor(valor):
                if isinstance(valor, str) and valor.startswith('${') and valor.endswith('}'): 
                    return valor[2:-1]  # Quita ${ del principio y } del final
                return valor
            
            # Intenta obtener datos de request.data
            if hasattr(request, 'data') and request.data:
                data = request.data
            # Si no hay datos en request.data, intenta parsear el body
            elif raw_body:
                try:
                    data = json.loads(raw_body)
                except:
                    try:
            # Manejar datos como x-www-form-urlencoded
                        from urllib.parse import parse_qs
                        parsed = parse_qs(raw_body.decode('utf-8'))
                        data = {k: v[0] for k, v in parsed.items()}
                        print("📩 Datos parseados como form-urlencoded:", data)
                    except Exception as e:
                        print(f"⚠️ No se pudo parsear el body como form-urlencoded: {str(e)}")
                        
                        # Log para depuración
                        print(f"📥 Datos recibidos de Zoho (procesamiento asíncrono): {data}")
                
            # Extraer campos y limpiar formato ${...}
            nombre_completo = limpiar_valor(data.get('nombre_completo', ''))
            email = limpiar_valor(data.get('email', ''))
            tipo = limpiar_valor(data.get('tipo', 'Cliente'))  # Valor por defecto
            telefono = limpiar_valor(data.get('telefono', ''))
            
            # Log de los datos limpios
            print(f"✅ Datos procesados: nombre={nombre_completo}, email={email}, tipo={tipo}, telefono={telefono}")
            
            # Verificar datos mínimos
            if not email or not nombre_completo:
                print(f"⚠️ Datos incompletos: email={email}, nombre={nombre_completo}")
                return
                
            # Generar contraseña y procesar usuario
            password = generar_contrasena()
            self.procesar_usuario(nombre_completo, email, tipo, telefono, password)
            
        except Exception as e:
            print(f"❌ Error en procesamiento asíncrono: {str(e)}")

    def procesar_usuario(self, nombre_completo, email, tipo, telefono, password):
        try:
            print(f"🔄 Procesando usuario: {email}, tipo: {tipo}")
            
            # Verificar si el usuario ya existe
            existing_user = User.objects.filter(email=email).first()
            if existing_user:
                print(f"ℹ️ Usuario ya existe: {email}")
                return
            
            # Intentar crear el usuario usando el registro estándar
            try:
                user_data = {
                    "username": email,
                    "email": email,
                    "first_name": nombre_completo,
                    "telefono": telefono,
                    "rol": tipo,
                    "password": password,
                    "password2": password,
                }

                factory = APIRequestFactory()
                post_request = factory.post('/api/register/', user_data, format='json')
                response = Register.as_view()(post_request)

                if response.status_code == 200:
                    print(f"✅ Usuario creado exitosamente: {email}")
                    # Enviar correo en otro hilo para no bloquear
                    Thread(target=self.enviar_contrasena_correo, args=(email, password)).start()
                else:
                    print(f"❌ Error al crear usuario: {getattr(response, 'data', 'No response data')}")
            except Exception as e:
                print(f"❌ Error al crear usuario mediante Register: {str(e)}")
                # Intentar método alternativo si falla el registro estándar
                try:
                    # Crear usuario directamente
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        password=password,
                        first_name=nombre_completo,
                        telefono=telefono,
                        rol=tipo
                    )
                    print(f"✅ Usuario creado directamente: {email}")
                    # Enviar correo en otro hilo
                    Thread(target=self.enviar_contrasena_correo, args=(email, password)).start()
                except Exception as direct_error:
                    print(f"❌ Error al crear usuario directamente: {str(direct_error)}")
        except Exception as e:
            print(f"❌ Error general en proceso de usuario: {str(e)}")
        
    def enviar_contrasena_correo(self, email_destino, contrasena):
        try:
            asunto = "Registro en Arrendify - Contraseña Generada"
            texto = f"Tu contraseña temporal es: {contrasena}"
            html = f"""
            <p>Hola,</p>
            <p>Te has registrado exitosamente en <strong>Arrendify</strong>.</p>
            <p><strong>Tu contraseña temporal es:</strong> {contrasena}</p>
            <p>Por favor, inicia sesión y cámbiala lo antes posible.</p>
            <p>Saludos,<br>Equipo Arrendify</p>
            """

            # Intentar enviar correo con EmailMultiAlternatives
            try:
                msg = EmailMultiAlternatives(asunto, texto, settings.DEFAULT_FROM_EMAIL, [email_destino])
                msg.attach_alternative(html, "text/html")
                msg.send()
                print(f"✉️ Correo enviado exitosamente a {email_destino}")
            except Exception as email_error:
                print(f"❌ Error al enviar correo con EmailMultiAlternatives: {str(email_error)}")
                # Método alternativo: send_mail básico
                try:
                    send_mail(
                        asunto,
                        texto,
                        settings.DEFAULT_FROM_EMAIL,
                        [email_destino],
                        fail_silently=False,
                    )
                    print(f"✉️ Correo enviado con método alternativo a {email_destino}")
                except Exception as basic_email_error:
                    print(f"❌ Error al enviar correo con método básico: {str(basic_email_error)}")
        except Exception as e:
            print(f"❌ Error general al enviar correo: {str(e)}")
            # No propagamos la excepción para evitar interrumpir el flujo
        
def generar_contrasena(longitud=10):
    caracteres = string.ascii_letters + string.digits + "!@#$%^&*()"
    return ''.join(random.choices(caracteres, k=longitud))


@api_view(['GET', 'POST'])
@csrf_exempt
def zoho_test(request):
    """Endpoint sencillo para probar webhooks de Zoho"""
    print("\n\n🔔 PRUEBA DE WEBHOOK RECIBIDA")
    print(f"📝 Método: {request.method}")
    print(f"🔑 Headers: {dict(request.headers)}")
    
    # Mostrar cuerpo de la solicitud
    if request.body:
        print(f"📦 Raw Body: {request.body}")
        try:
            body_json = json.loads(request.body)
            print(f"📋 JSON Body: {body_json}")
        except:
            print("⚠️ No se pudo parsear el cuerpo como JSON")
    
    # Mostrar datos POST
    if request.POST:
        print(f"📬 POST data: {request.POST}")
        
    # Siempre devolver éxito
    return JsonResponse({
        'status': 'success',
        'message': 'Webhook de prueba recibido correctamente',
        'timestamp': datetime.now().isoformat()
    })