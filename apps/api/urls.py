
"""
Copyright (c) 2019 - present AppSeed.us
"""
from . import views
from django.urls import path 
from ..api.routers import *
from django.urls import include
from .Views.arrendador.arrendadorView import *

urlpatterns = [
    path('v1/inquilino_registro/', views.inquilino_registro.as_view()), 
    path('v1/inquilinos_delete/', views.inquilinos_delete.as_view()),
    path('v1/inq_list/', views.inquilinos_list_all),
    path('v1/editar_inquilino/', views.editar_inquilino),
    # -*- encoding: utf-8 -*-
    path('arrendadores/crear_documentos/', ArrendadorViewSet.as_view({'post': 'create_documentos'}), name='crear_documentos'),
    path('arrendadores/investigacion/<str:slug>/', ArrendadorViewSet.as_view({'put': 'investigacion'}), name='investigacion'),
    path('arrendadores/enviar_pdf/<str:slug>/', ArrendadorViewSet.as_view({'put': 'investigacion_arrendador_pdf'}), name='investigacion_arrendador_pdf'),
    # Password
    path('RecuperarPassword/recupera_password/', RecuperarPassword.as_view({'post': 'recuperar_password'}), name='recuperar_password'),
    path('nuevo-password', RecuperarPassword.as_view({'post': 'reset_password'}), name='nuevo-password'),
    #Amigos
    path('friendrequest/', Amigos.as_view({'post': 'send_friend_request'}), name='friendrequest'),
    
    #Investigacion
    path('aprobar_prospecto/', investigaciones.as_view({'post': 'aprobar_prospecto'}), name='aprobar_prospecto'),
    path('investigacion_francis/', investigaciones.as_view({'get': 'investigacion_francis'}), name='investigacion_francis'),
    
    #paquetes
    path('paquetes/generar_pagare/', Paks.as_view({'post': 'generar_pagare'}), name='generar_pagare'),
    path('paquetes/generar_poliza/', Paks.as_view({'post': 'generar_poliza'}), name='generar_poliza'),
    path('paquetes/generar_contrato/', Paks.as_view({'post': 'generar_contrato'}), name='generar_contrato'),
    
    #residentes fraterna
    path('fraterna/aprobar_residente/', fraterna_views.ResidenteViewSet.as_view({'post': 'mandar_aprobado'}), name='mandar_aprobado'),
    #contrato fraterna
    path('fraterna/aprobar_contrato/', fraterna_views.Contratos_fraterna.as_view({'put': 'aprobar_contrato'}), name='aprobar_contrato_frat'),
    path('fraterna/desaprobar_contrato/', fraterna_views.Contratos_fraterna.as_view({'put': 'desaprobar_contrato'}), name='desaprobar_contrato_frat'),
    path('fraterna/generar_pagare/', fraterna_views.Contratos_fraterna.as_view({'post': 'generar_pagare'}), name='generar_pagare_frat'),
    path('fraterna/generar_poliza/', fraterna_views.Contratos_fraterna.as_view({'post': 'generar_poliza'}), name='generar_poliza_frat'),
    path('fraterna/generar_contrato/', fraterna_views.Contratos_fraterna.as_view({'post': 'generar_contrato'}), name='generar_contrato_frat'),
    path('fraterna/generar_comodato/', fraterna_views.Contratos_fraterna.as_view({'post': 'generar_comodato'}), name='generar_comodato_frat'),
    
    #notificaiones por usuario
    path('notificaciones_usuario/',notis_prueba.as_view({'get': 'notificaiones_por_usuario'}), name='notificaiones_por_usuario'),
    path('send_noti/',notis_prueba.as_view({'post': 'send_noti'}), name='send_noti'),
    path('leer_todas/',notis_prueba.as_view({'post': 'leer_todas'}), name='leer_todas'),
    # path('notificaciones_usuario/',notis_prueba.as_view({'get': 'notificaiones_por_usuario'}), name='notificaiones_por_usuario'),
    
    #manejamos el index con la pag404
    path('health/', health_check, name='health_check'),
    
    #manejamos el index con la pag404
    path('', pagina_404, name='error'),   
    path('', include(router.urls)),
]
# urlpatterns += router.urls

