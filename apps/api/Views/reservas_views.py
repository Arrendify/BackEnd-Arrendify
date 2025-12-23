from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from ...home.models import ReservaAsador, ReservaAsadorFraterna
from ..serializers import ReservaAsadorSerializer, ReservaAsadorFraternaSerializer

User = get_user_model()

class ReservaAsadorViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = ReservaAsador.objects.all().order_by('-fecha', 'asador', 'hora_inicio')
    serializer_class = ReservaAsadorSerializer

    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            data = request.data.copy()

            # Si el que llama es admin (staff/superuser), permitir crear a nombre del usuario enviado
            if (getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)) and data.get('user'):
                try:
                    user_session = User.objects.get(pk=data.get('user'))
                except User.DoesNotExist:
                    return Response({'detail': 'Usuario no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            instancia = serializer.save(user=user_session, usuario_nombre=getattr(user_session, 'first_name', ''))
            return Response(self.get_serializer(instancia).data, status=status.HTTP_201_CREATED)
        except ValidationError as ve:
            detalle = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({'detail': detalle}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='disponibilidad')
    def disponibilidad(self, request):
        try:
            asador_param = request.query_params.get('asador')
            fecha = request.query_params.get('fecha')  # YYYY-MM-DD
            if not asador_param or not fecha:
                return Response({'detail': 'Parámetros asador y fecha son requeridos.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                asador = int(asador_param)
            except ValueError:
                return Response({'detail': 'El parámetro asador debe ser numérico.'}, status=status.HTTP_400_BAD_REQUEST)

            reservas = ReservaAsador.objects.filter(asador=asador, fecha=fecha).order_by('hora_inicio')
            lista = [{'inicio': r.hora_inicio.strftime('%H:%M'), 'fin': r.hora_fin.strftime('%H:%M')} for r in reservas]

            # Determinar si el día está completamente reservado (08:00-22:00 sin huecos)
            def dia_completo(intervalos):
                if not intervalos:
                    return False
                if len(intervalos) == 1 and intervalos[0]['inicio'] == '08:00' and intervalos[0]['fin'] == '22:00':
                    return True
                cursor = '08:00'
                for it in intervalos:
                    if it['inicio'] > cursor:
                        return False
                    if it['fin'] > cursor:
                        cursor = it['fin']
                    if cursor >= '22:00':
                        return True
                return False

            return Response({'reservas': lista, 'dia_completo': dia_completo(lista)}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        
class ReservaAsadorFraternaViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = ReservaAsadorFraterna.objects.all().order_by('-fecha', 'asador', 'hora_inicio')
    serializer_class = ReservaAsadorFraternaSerializer

    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            data = request.data.copy()

            # Si el que llama es admin (staff/superuser), permitir crear a nombre del usuario enviado
            if (getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)) and data.get('user'):
                try:
                    user_session = User.objects.get(pk=data.get('user'))
                except User.DoesNotExist:
                    return Response({'detail': 'Usuario no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            instancia = serializer.save(user=user_session, usuario_nombre=getattr(user_session, 'first_name', ''))
            return Response(self.get_serializer(instancia).data, status=status.HTTP_201_CREATED)
        except ValidationError as ve:
            detalle = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({'detail': detalle}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='disponibilidad')
    def disponibilidad(self, request):
        try:
            asador_param = request.query_params.get('asador')
            fecha = request.query_params.get('fecha')  # YYYY-MM-DD
            if not asador_param or not fecha:
                return Response({'detail': 'Parámetros asador y fecha son requeridos.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                asador = int(asador_param)
            except ValueError:
                return Response({'detail': 'El parámetro asador debe ser numérico.'}, status=status.HTTP_400_BAD_REQUEST)

            reservas = ReservaAsadorFraterna.objects.filter(asador=asador, fecha=fecha).order_by('hora_inicio')
            lista = [{'inicio': r.hora_inicio.strftime('%H:%M'), 'fin': r.hora_fin.strftime('%H:%M')} for r in reservas]

            # Determinar si el día está completamente reservado (08:00-22:00 sin huecos)
            def dia_completo(intervalos):
                if not intervalos:
                    return False
                if len(intervalos) == 1 and intervalos[0]['inicio'] == '08:00' and intervalos[0]['fin'] == '22:00':
                    return True
                cursor = '08:00'
                for it in intervalos:
                    if it['inicio'] > cursor:
                        return False
                    if it['fin'] > cursor:
                        cursor = it['fin']
                    if cursor >= '22:00':
                        return True
                return False

            return Response({'reservas': lista, 'dia_completo': dia_completo(lista)}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
