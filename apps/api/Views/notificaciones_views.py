# -*- encoding: utf-8 -*-
"""
Vistas API para el sistema de notificaciones de recordatorios de contratos
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from ...home.models import Notificacion
from ..serializers import NotificacionSerializer


class NotificacionViewSet(viewsets.ModelViewSet):
    """
    ViewSet para consultar tabla completa de notificaciones
    """
    serializer_class = NotificacionSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Obtiene todas las notificaciones de la tabla sin filtros"""
        return Notificacion.objects.all().order_by('-fecha_creacion')

    @action(detail=False, methods=['post'], url_path='crear_comunicado')
    def crear_comunicado(self, request):
        titulo  = (request.data.get('titulo') or '').strip()
        mensaje = (request.data.get('mensaje') or '').strip()

        if not titulo or not mensaje:
            return Response({"detail": "titulo y mensaje son requeridos."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Si agregaste 'comunicado' a los choices, usa 'comunicado'. Si no, usa
        # temporalmente 'recordatorio_1_mes' para no romper validación.
        TIPO_NOTIF = 'comunicado'   # <-- NO 'garzasada' aquí
        TIPO_CONTR = 'garzasada'    # <-- el tipo de contrato sí es 'garzasada'

        noti = Notificacion.objects.create(
            user=request.user,
            tipo_notificacion=TIPO_NOTIF,         # correcto
            tipo_contrato=TIPO_CONTR,             # correcto
            titulo=titulo,
            mensaje=mensaje,
            fecha_programada=timezone.now().date(),
            # si el campo es obligatorio en DB, pon hoy; si lo hiciste nullable, deja None
            fecha_vencimiento_contrato=timezone.now().date(),
            contrato_general=None,
            contrato_fraterna=None,
            contrato_semillero=None,
            contrato_garzasada=None,
        )

        ser = NotificacionSerializer(noti)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        """Lista todas las notificaciones de la tabla completa"""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            'count': queryset.count(),
            'results': serializer.data
        })

    @action(detail=False, methods=['get'])
    def no_leidas(self, request):
        """Obtiene todas las notificaciones de la tabla (filtrado se hace en frontend)"""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            'count': queryset.count(),
            'results': serializer.data
        })

    @action(detail=True, methods=['post'])
    def marcar_leida(self, request, pk=None):
        """Marca una notificación como leída (leida=True)"""
        try:
            notificacion = self.get_object()
            notificacion.leida = True
            notificacion.fecha_lectura = timezone.now()
            notificacion.save()
            
            return Response({
                'message': 'Notificación marcada como leída',
                'leida': True,
                'fecha_lectura': notificacion.fecha_lectura
            })
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def marcar_todas_leidas(self, request):
        """Marca todas las notificaciones del usuario como leídas"""
        try:
            # Solo marcar las del usuario autenticado
            notificaciones = self.get_queryset().filter(user=request.user, leida=False)
            count = notificaciones.count()
            
            notificaciones.update(
                leida=True,
                fecha_lectura=timezone.now()
            )
            
            return Response({
                'message': f'{count} notificaciones marcadas como leídas',
                'count': count
            })
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
