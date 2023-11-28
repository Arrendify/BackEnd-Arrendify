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
from django.contrib.auth.models import User

from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from apps.authentication.serializers import UserTokenSerializer, CustomUserSerializer, UserListSerializer, User2Serializer
from rest_framework.decorators import api_view



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
                if created:
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
       user_serializar = CustomUserSerializer(data = request.data)
       qs = User.objects.all()
       print(request.data)
       print("query setr chido",qs)
      
       if request.data.get('password') == request.data.get('password2'):
        
           if user_serializar.is_valid():
               user_serializar.save()
               return Response(user_serializar.data)
       return Response({'error':user_serializar.errors, 'status':205})

@api_view(['GET'])
def user_unico(request):
    if request.method == 'GET':
        user = str(request.user)
        print(user)
        if user != 'AnonymousUser':
            print("entre estoy logeado")
            return Response({'user':True}, status= status.HTTP_200_OK)
    return Response({'user':False}, status= status.HTTP_401_UNAUTHORIZED)
