from django.shortcuts import render, redirect
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from ..accounts.models import CustomUser
from datetime import datetime, timedelta
from django.utils import timezone
import uuid
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from decouple import config

User = CustomUser

class RecuperarPasswordView(APIView):
    """
    Vista para manejar la recuperación de contraseñas.
    No requiere autenticación ya que los usuarios olvidaron sus credenciales.
    """
    
    def post(self, request):
        """
        Recibe un correo electrónico y envía un enlace de restablecimiento si el usuario existe.
        """
        email = request.data.get('email')
        
        if not email:
            return Response({'error': 'El correo electrónico es obligatorio'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Por seguridad, no revelamos si el usuario existe o no
            return Response({'message': 'Si el correo existe en nuestra base de datos, recibirás instrucciones para restablecer tu contraseña.'}, status=status.HTTP_200_OK)
        
        # Verificar si ya se ha enviado una solicitud en los últimos 30 minutos
        ahora = timezone.now()
        tiempo_limite = ahora - timedelta(minutes=30)
        
        if user.reset_password_token_created_at and user.reset_password_token_created_at > tiempo_limite:
            # Ya se envió una solicitud reciente
            return Response({'message': 'Ya se ha enviado una solicitud de recuperación de contraseña.'}, status=status.HTTP_200_OK, headers={'correo': email})
        
        # Generar token único y guardarlo en el usuario
        token = str(uuid.uuid4())
        user.reset_password_token = token
        user.reset_password_token_created_at = ahora
        user.save()
        
        # Enviar correo con enlace para restablecer contraseña
        self.enviar_correo_recuperacion(email, token)
        
        return Response({
            'message': 'Se han enviado instrucciones para restablecer tu contraseña.',
            'correo': email
        }, status=status.HTTP_200_OK)

    def enviar_correo_recuperacion(self, email, token):
        """
        Envía un correo con un enlace para restablecer la contraseña.
        """
        # URL del frontend para restablecer contraseña
        reset_url = f"https://contrato.pro/#/reset-password/{token}"
        #reset_url = f"https://192.168.1.141:8000/reset-password/{token}"
        
        # Crear el mensaje
        subject = "Recuperación de contraseña - Arrendify"
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4a6cf7; color: white; padding: 10px; text-align: center; }}
                .content {{ padding: 20px; }}
                .button {{ display: inline-block; background-color: #4a6cf7; color: white; padding: 10px 20px; 
                          text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Recuperación de Contraseña</h2>
                </div>
                <div class="content">
                    <p>Hola,</p>
                    <p>Hemos recibido una solicitud para restablecer la contraseña de tu cuenta Arrendify.</p>
                    <p>Para crear una nueva contraseña, haz clic en el siguiente enlace:</p>
                    <p><a href="{reset_url}" class="button">Restablecer mi contraseña</a></p>
                    <p>Este enlace expirará en 24 horas.</p>
                    <p>Si no solicitaste un restablecimiento de contraseña, puedes ignorar este mensaje.</p>
                    <p>Gracias,<br>El equipo de Arrendify</p>
                </div>
                <div class="footer">
                    <p>Este es un correo electrónico automático, por favor no respondas a este mensaje.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = MIMEMultipart()
        msg['From'] = 'notificaciones@arrendify.com'
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(html, 'html'))

        smtp_server = 'mail.arrendify.com'
        smtp_port = 587
        smtp_username = config('mine_smtp_u')
        smtp_password = config('mine_smtp_pw')

        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.sendmail(smtp_username, email, msg.as_string())
                print(f"Correo de recuperación enviado a {email}")
        except Exception as e:
            print(f"Error al enviar correo: {str(e)}")


class ResetPasswordView(APIView):
    """
    Vista para establecer una nueva contraseña usando un token de restablecimiento.
    """
    
    def post(self, request):
        """
        Recibe un token y una nueva contraseña, verifica el token y actualiza la contraseña.
        """
        token = request.data.get('token')
        password = request.data.get('password')
        
        if not token or not password:
            return Response({'error': 'Se requiere token y contraseña'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            user = User.objects.get(reset_password_token=token)
        except User.DoesNotExist:
            return Response({'error': 'Token inválido o expirado'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar si el token ha expirado (24 horas)
        ahora = timezone.now()
        tiempo_limite = ahora - timedelta(hours=24)
        
        if not user.reset_password_token_created_at or user.reset_password_token_created_at < tiempo_limite:
            return Response({'error': 'El token ha expirado'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Actualizar contraseña
        user.set_password(password)
        # Limpiar token después de usar
        user.reset_password_token = None
        user.reset_password_token_created_at = None
        user.save()
        
        return Response({'message': 'Contraseña restablecida exitosamente'}, status=status.HTTP_200_OK)
