
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
    
    #paquetes
    path('paquetes/generar_pagare/', Paks.as_view({'post': 'generar_pagare'}), name='generar_pagare'),
    path('paquetes/generar_poliza/', Paks.as_view({'post': 'generar_poliza'}), name='generar_poliza'),
    path('paquetes/generar_contrato/', Paks.as_view({'post': 'generar_contrato'}), name='generar_contrato'),
    
    #contrato fraterna
    path('fraterna/aprobar_contrato/', fraterna_views.Contratos_fraterna.as_view({'put': 'aprobar_contrato'}), name='aprobar_contrato_frat'),
    path('fraterna/generar_pagare/', fraterna_views.Contratos_fraterna.as_view({'post': 'generar_pagare'}), name='generar_pagare_frat'),
    path('fraterna/generar_poliza/', fraterna_views.Contratos_fraterna.as_view({'post': 'generar_poliza'}), name='generar_poliza_frat'),
    path('fraterna/generar_contrato/', fraterna_views.Contratos_fraterna.as_view({'post': 'generar_contrato'}), name='generar_contrato_frat'),
    
    
    #manejamos el index con la pag404
    
    
    #manejamos el index con la pag404
    path('', pagina_404, name='error'),   
    path('', include(router.urls)),
]
# urlpatterns += router.urls

