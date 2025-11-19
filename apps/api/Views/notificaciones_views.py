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
        """Obtiene todas las notificaciones de la tabla con reglas para admin"""
        qs = Notificacion.objects.all().order_by('-fecha_creacion')
        # Si es "admin" (por username), por defecto ocultar las marcadas como oculta_admin, a menos que pida incluirlas
        try:
            req = getattr(self, 'request', None)
            if req and getattr(req, 'user', None) and (getattr(req.user, 'is_staff', False) or getattr(req.user, 'username', None) in {"GarzaSada", "Fraterna", "SemilleroPurisima", "ElbaJ", "AngelinaCastillo"}):
                incluir_ocultas = req.query_params.get('incluir_ocultas')
                if not incluir_ocultas:
                    qs = qs.filter(oculta_admin=False)
        except Exception:
            pass
        return qs

    @action(detail=False, methods=['post'], url_path='crear_comunicado')
    def crear_comunicado(self, request):
        titulo  = (request.data.get('titulo') or '').strip()
        mensaje = (request.data.get('mensaje') or '').strip()
        tipo_contrato = (request.data.get('tipo_contrato') or '').strip().lower()

        if not titulo or not mensaje:
            return Response({"detail": "titulo y mensaje son requeridos."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Validar tipo de contrato
        tipos_validos = ['fraterna', 'semillero', 'garzasada', 'general']
        if not tipo_contrato or tipo_contrato not in tipos_validos:
            return Response({
                "detail": f"tipo_contrato es requerido y debe ser uno de: {', '.join(tipos_validos)}"
            }, status=status.HTTP_400_BAD_REQUEST)

        TIPO_NOTIF = 'comunicado'

        noti = Notificacion.objects.create(
            user=request.user,
            tipo_notificacion=TIPO_NOTIF,
            tipo_contrato=tipo_contrato,  # Ahora es dinámico según el módulo
            titulo=titulo,
            mensaje=mensaje,
            fecha_programada=timezone.now().date(),
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

    @action(detail=True, methods=['post'], url_path='ocultar_admin')
    def ocultar_admin(self, request, pk=None):
        """Oculta una notificación solo en la vista del administrador"""
        username = getattr(request.user, 'username', None)
        is_staff = getattr(request.user, 'is_staff', False)
        notificacion = self.get_object()
        tipo_notif = notificacion.tipo_contrato or ''
        
        # Validar permisos según tipo de usuario y tipo de notificación
        tiene_permiso = False
        if is_staff:
            # Staff puede ocultar cualquier notificación
            tiene_permiso = True
        elif username in {"Fraterna", "ElbaJ", "AngelinaCastillo"} and tipo_notif == 'fraterna':
            # Estos usuarios solo pueden ocultar notificaciones de Fraterna
            tiene_permiso = True
        elif username == "GarzaSada" and tipo_notif == 'garzasada':
            # GarzaSada solo puede ocultar notificaciones de GarzaSada
            tiene_permiso = True
        elif username == "SemilleroPurisima" and tipo_notif == 'semillero':
            # SemilleroPurisima solo puede ocultar notificaciones de Semillero
            tiene_permiso = True
            
        if not tiene_permiso:
            return Response({'detail': 'No autorizado para esta notificación'}, status=status.HTTP_403_FORBIDDEN)
            
        notificacion.oculta_admin = True
        notificacion.save(update_fields=['oculta_admin'])
        return Response({'message': 'Notificación ocultada para admin', 'oculta_admin': True})

    @action(detail=True, methods=['post'], url_path='mostrar_admin')
    def mostrar_admin(self, request, pk=None):
        """Revierte la ocultación para administradores"""
        username = getattr(request.user, 'username', None)
        is_staff = getattr(request.user, 'is_staff', False)
        notificacion = self.get_object()
        tipo_notif = notificacion.tipo_contrato or ''
        
        # Validar permisos según tipo de usuario y tipo de notificación
        tiene_permiso = False
        if is_staff:
            # Staff puede mostrar cualquier notificación
            tiene_permiso = True
        elif username in {"Fraterna", "ElbaJ", "AngelinaCastillo"} and tipo_notif == 'fraterna':
            # Estos usuarios solo pueden mostrar notificaciones de Fraterna
            tiene_permiso = True
        elif username == "GarzaSada" and tipo_notif == 'garzasada':
            # GarzaSada solo puede mostrar notificaciones de GarzaSada
            tiene_permiso = True
        elif username == "SemilleroPurisima" and tipo_notif == 'semillero':
            # SemilleroPurisima solo puede mostrar notificaciones de Semillero
            tiene_permiso = True
            
        if not tiene_permiso:
            return Response({'detail': 'No autorizado para esta notificación'}, status=status.HTTP_403_FORBIDDEN)
            
        notificacion.oculta_admin = False
        notificacion.save(update_fields=['oculta_admin'])
        return Response({'message': 'Notificación visible para admin', 'oculta_admin': False})
