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

from apps.authentication.serializers import UserTokenSerializer, CustomUserSerializer, UserListSerializer, User2Inmobiliaria, UserSerializer,User2Serializer, PasswordSerializer,User2Residente
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
import json, string, random
#variables
from .variables import *



class UserToken(APIView):
    def get(self, request, *args, **kwargs):
        username = request.GET.get('username')
        print(username)
        try:
            user_token = Token.objects.get(user = UserTokenSerializer().Meta.model.objects.filter(username = username).first())
            return Response({'token': user_token.key})
        except:
            return Response({'error':'Credenciales enviadas incorrectas'},status=status.HTTP_400_BAD_REQUEST)
            

class UserInfoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = UserSerializer(user)
        return Response(serializer.data)

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password')

        if not user.check_password(old_password):
            return Response({'error': 'La contraseña actual no es correcta.'}, status=400)

        serializer = PasswordSerializer(data=request.data)
        if serializer.is_valid():
            user.set_password(serializer.validated_data['password'])
            user.save()
            return Response({'message': 'La contraseña se cambió exitosamente.'}, status=200)

        return Response(serializer.errors, status=400)
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
                residente_user = User2Residente(user)

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
                     elif residente_user.data['rol'] == "Residente":
                        print("Residente")
                        return Response({'token':token.key, 
                                      'user':residente_user.data,
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
    def post(self, request, *args, **kwargs):
        entrada = request.data.copy()
        user_serializar = UserSerializer(data=entrada)
        print("soy request data", entrada)

        # Generar contraseña aleatoria si está vacía
        if not entrada.get('password') or not entrada.get('password2'):
            generated_password = self.generar_password()
            entrada['password'] = generated_password
            entrada['password2'] = generated_password
            enviar_password = True
        else:
            enviar_password = False

        if entrada.get('password') == entrada.get('password2'):
            if user_serializar.is_valid():
                print("serializer válido")
                if entrada["rol"] == "Inmobiliaria":
                    print("Soy Inmobiliaria")                  
                    user_serializar.save()
                    info = User.objects.get(username=entrada["username"])
                    self.enviar_codigo(info)
                    if enviar_password:
                        self.enviar_password(info.email, entrada['password'])
                    print("usuario guardado")

                elif entrada["rol"] == "Agente":
                    print("Soy Agente")
                    try:
                        inmo_ag = User.objects.get(name_inmobiliaria=entrada["pertenece_a"])
                    except User.DoesNotExist:
                        return Response({'error': "No se encontró la inmobiliaria indicada", 'status': 102})

                    codigo = entrada["c_inmobiliaria"]
                    if codigo == inmo_ag.code_inmobiliaria:
                        print("Bienvenido Agente, código correcto")
                        user_serializar.save()
                        info = User.objects.get(username=entrada["username"])
                        if enviar_password:
                            self.enviar_password(info.email, entrada['password'])
                        print("usuario guardado")
                    else:
                        return Response({'error': "El código que proporcionaste no es correcto", 'status': 101})

                elif entrada["rol"] == "Normal":
                    print("Normalito")
                    user_serializar.save()
                    info = User.objects.get(username=entrada["username"])
                    if enviar_password:
                        self.enviar_password(info.email, entrada['password'])
                    print("usuario guardado")
                
                elif entrada["rol"] == "Residente":
                    try:
                        inmo_ag = User.objects.get(name_inmobiliaria=entrada["pertenece_a"])
                    except User.DoesNotExist:
                        return Response({'error': "No se encontró la inmobiliaria indicada", 'status': 102})

                    codigo = entrada["c_inmobiliaria"]
                    if codigo == inmo_ag.code_inmobiliaria:
                        print("Bienvenido Residente, código correcto")
                        user_serializar.save()
                        info = User.objects.get(username=entrada["username"])
                        if enviar_password:
                            self.enviar_password(info.email, entrada['password'])
                        print("usuario guardado")
                    else:
                        return Response({'error': "El código que proporcionaste no es correcto", 'status': 101})


                print("ya voy a retornar la info")
                return Response(user_serializar.data)
            else:
                # Manejo de errores específicos de duplicado
                errores = user_serializar.errors
                if 'username' in errores and any('unique' in e.lower() for e in errores['username']):
                    print("error de username")
                    return Response({'error': "El nombre de usuario ya está registrado", 'status': 106})
                if 'email' in errores and any('unique' in e.lower() for e in errores['email']):
                    print("error de email")
                    return Response({'error': "El correo electrónico ya está registrado", 'status': 107})
                if 'name_inmobiliaria' in errores and any('unique' in e.lower() for e in errores['name_inmobiliaria']):
                    print("error de name inmobiliaria")
                    return Response({'error': "El nombre de la inmobiliaria ya está registrado", 'status': 108})

        # Error por contraseñas diferentes o validaciones fallidas
        return Response({'error': user_serializar.errors, 'status': 205})

    def generar_password(self, length=10):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    def enviar_codigo(self, info):
        print("que onda")
        print("soy info despues de entrar al metodo", info)
        print(info.__dict__)
        codigo = info.code_inmobiliaria
        email = info.email
        html = codigo_inmobiliaria(codigo)
        msg = MIMEMultipart()
        msg['From'] = 'notificaciones_arrendify@outlook.com'
        msg['To'] = email
        msg['Subject'] = 'Registro Exitoso - Tu código de inmobiliaria'
        msg.attach(MIMEText(html, 'html'))

        smtp_server = 'mail.arrendify.com'
        smtp_port = 587
        smtp_username = config('mine_smtp_u')
        smtp_password = config('mine_smtp_pw')

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, email, msg.as_string())
            print("Código enviado")

    def enviar_password(self, email, password):
        subject = "Tu cuenta generada por Contrato.pro"
        html = nuevo_usuario_zoho(email,password)
        msg = MIMEMultipart()
        msg['From'] = 'notificaciones@arrendify.com'
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(html, 'html'))

        smtp_server = 'mail.arrendify.com'
        smtp_port = 587
        smtp_username = config('mine_smtp_u')
        smtp_password = config('mine_smtp_pw')

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, email, msg.as_string())
            print("Contraseña enviada")
            

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

