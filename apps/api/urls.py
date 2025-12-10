"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.urls import path 
from ..api.routers import *
from django.urls import include
from .Views.arrendadorView import *
from .Views.inquilinos_view import *
from .Views.contratos_dash_view import *
from .Views.investigaciones_views import *
from .Views.stripe_view import CreateStripeCheckoutSession
from .Views.notificaciones_views import NotificacionViewSet


urlpatterns = [
    # Password
    path('RecuperarPassword/recupera_password/', RecuperarPassword.as_view({'post': 'recuperar_password'}), name='recuperar_password'),
    path('nuevo-password', RecuperarPassword.as_view({'post': 'reset_password'}), name='nuevo-password'),
    #Amigos
    path('friendrequest/', Amigos.as_view({'post': 'send_friend_request'}), name='friendrequest'),
    
    #Fiador/Obligado Documentos
    #path('actualiza_documentos/', DocumentosFoo.as_view({'put': 'actualiza_documentos'}), name='documentos_foo'),
    
    #Notificaciones
    path('notificaciones/', NotificacionViewSet.as_view({'get': 'list'}), name='notificaciones_list'),
    path('notificaciones/no_leidas/', NotificacionViewSet.as_view({'get': 'no_leidas'}), name='notificaciones_no_leidas'),
    path('notificaciones/<int:pk>/marcar_leida/', NotificacionViewSet.as_view({'post': 'marcar_leida'}), name='notificaciones_marcar_leida'),
    path('notificaciones/marcar_todas_leidas/', NotificacionViewSet.as_view({'post': 'marcar_todas_leidas'}), name='notificaciones_marcar_todas_leidas'),
    
    #Investigacion
    path('aprobar_prospecto/', investigaciones.as_view({'post': 'aprobar_prospecto'}), name='aprobar_prospecto'),
    path('investigacion_francis/', investigaciones.as_view({'get': 'investigacion_francis'}), name='investigacion_francis'),
    
    #Investigaciones
    path('resultado_inquilino/', InvestigacionInquilinoViewSet.as_view({'post':'investigacion_inquilino'}), name= 'investigacion_inquilino'),
    path('resultado_laboral/', InvestigacionLaboralViewSet.as_view({'post':'investigacion_laboral'}), name='investigacion_laboral'),
    path('resultado_financiera/', InvestigacionFinancieraViewSet.as_view({'post':'investigacion_financiera'}), name='investigacion_financiera'),
    path('resultado_judicial/', InvestigacionJudicialViewSet.as_view({'post':'investigacion_judicial'}), name = 'investigacion_judicial'),
    
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
    path('fraterna/renovar_contrato/', fraterna_views.Contratos_fraterna.as_view({'post': 'renovar_contrato_fraterna'}), name='renovar_contrato_frat'),
    path('fraterna/generar_paquete_completo/', fraterna_views.Contratos_fraterna.as_view({'post': 'generar_paquete_completo_fraterna'}), name='generar_paquete_completo_frat'),
    path('fraterna/generar_urls_firma/', fraterna_views.Contratos_fraterna.as_view({'post': 'generar_urls_firma_fraterna'}), name='generar_urls_firma_frat'),
    path('fraterna/mostrar_urls_firma_documento/', fraterna_views.Contratos_fraterna.as_view({'post': 'mostrar_urls_firma_documento_fraterna'}), name='mostrar_urls_firma_documento_frat'),
    
    #contrato semillero purisima
    path('semillero/aprobar_contrato/', fraterna_views.Contratos_semillero.as_view({'put': 'aprobar_contrato_semillero'}), name='aprobar_contrato_semillero'),
    path('semillero/desaprobar_contrato/', fraterna_views.Contratos_semillero.as_view({'put': 'desaprobar_contrato_semillero'}), name='desaprobar_contrato_frat'),
    path('semillero/generar_pagare/', fraterna_views.Contratos_semillero.as_view({'post': 'generar_pagare_semillero'}), name='generar_pagare_semillero'),
    path('semillero/generar_poliza/', fraterna_views.Contratos_semillero.as_view({'post': 'generar_poliza_semillero'}), name='generar_poliza_semillero'),
    path('semillero/generar_contrato/', fraterna_views.Contratos_semillero.as_view({'post': 'generar_contrato_semillero'}), name='generar_contrato_semillero'),
    path('semillero/aprobar_residente/',fraterna_views.InvestigacionSemillero.as_view({'post': 'aprobar_residente_semillero'}), name='aprobar_residente_semillero'),
    
    #contrato Garza Sada
    path('garzasada/aprobar_contrato/', fraterna_views.Contratos_GarzaSada.as_view({'put': 'aprobar_contrato_garzasada'}), name='aprobar_contrato_garzasada'),
    path('garzasada/desaprobar_contrato/', fraterna_views.Contratos_GarzaSada.as_view({'put': 'desaprobar_contrato_garzasada'}), name='desaprobar_contrato_garzasada'),
    path('garzasada/generar_pagare/', fraterna_views.Contratos_GarzaSada.as_view({'post': 'generar_pagare_garzasada'}), name='generar_pagare_garzasada'),
    path('garzasada/generar_poliza/', fraterna_views.Contratos_GarzaSada.as_view({'post': 'generar_poliza_garzasada'}), name='generar_poliza_garzasada'),
    path('garzasada/generar_contrato/', fraterna_views.Contratos_GarzaSada.as_view({'post': 'generar_contrato_garzasada'}), name='generar_contrato_garzasada'),
    path('garzasada/aprobar_residente/',fraterna_views.InvestigacionGarzaSada.as_view({'post': 'aprobar_residente_garzasada'}), name='aprobar_residente_garzasada'),
    path('garzasada/generar_paquete_completo/', fraterna_views.Contratos_GarzaSada.as_view({'post': 'generar_paquete_completo_garzasada'}), name='generar_paquete_completo_gs'),
    path('garzasada/generar_urls_firma/', fraterna_views.Contratos_GarzaSada.as_view({'post': 'generar_urls_firma_gs'}), name='generar_urls_firma_gs'),
    path('garzasada/mostrar_urls_firma_documento/', fraterna_views.Contratos_GarzaSada.as_view({'post': 'mostrar_urls_firma_documento_gs'}), name='mostrar_urls_firma_documento_gs'),
    path('garzasada/posicionar_y_generar_urls/', fraterna_views.Contratos_GarzaSada.as_view({'post': 'posicionar_y_generar_urls_gs'}), name='posicionar_y_generar_urls_gs'),
    path('garzasada/posicionar_sobre_existente/', fraterna_views.Contratos_GarzaSada.as_view({'post': 'posicionar_sobre_existente_gs'}), name='posicionar_sobre_existente_gs'),
    path('garzasada/descargar_contrato_base64/', fraterna_views.Contratos_GarzaSada.as_view({'post': 'descargar_contrato_base64'}), name='descargar_contrato_base64_gs'),
    path('garzasada/aprobar_prospecto/', fraterna_views.InvestigacionGarzaSada.as_view({'post': 'aprobar_prospecto_garza_sada'}), name='aprobar_prospecto_garza_sada'),
    
    #Contratos Dash
    path('dash/almacenar_datos/', ContratosViewSet.as_view({'post': 'almacenar_datos'}), name='guardar_datos_dash'),
    path('dash/generar_preview_pagare/', ContratosViewSet.as_view({'post': 'generar_preview_pagare'}), name='generar_preview_pagare'),
    path('dash/generar_pagare/', ContratosViewSet.as_view({'post': 'generar_pagare'}), name='generar_pagare'),
    path('dash/generar_preview_contrato_arrenamiento/', ContratosViewSet.as_view({'post': 'generar_preview_contrato_arrendamiento'}), name='generar_preview_contrato_arrendamiento'),
    path('dash/generar_contrato_arrenamiento/', ContratosViewSet.as_view({'post': 'generar_contrato_arrendamiento'}), name='generar_preview_contrato_arrendamiento'),
    path('dash/generar_preview_poliza/', ContratosViewSet.as_view({'post': 'generar_preview_poliza'}), name='generar_preview_poliza'),
    path('dash/generar_poliza/', ContratosViewSet.as_view({'post': 'generar_poliza'}), name='generar_poliza'),
    path('dash/generar_corretaje_preview/', ContratosViewSet.as_view({'post': 'generar_corretaje_preview'}), name='generar_corretaje_preview'),
    path('dash/generar_corretaje/', ContratosViewSet.as_view({'post': 'generar_corretaje'}), name='generar_corretaje'),
    path('dash/generar_comodato_preview/', ContratosViewSet.as_view({'post': 'generar_contrato_comodato_preview'}), name='generar_contrato_comodato_preview'),
    path('dash/generar_comodato/', ContratosViewSet.as_view({'post': 'generar_contrato_comodato'}), name='generar_contrato_comodato'),
    path('dash/generar_compraventa_preview/', ContratosViewSet.as_view({'post': 'generar_compraventa_preview'}), name='generar_compraventa_preview'),
    path('dash/generar_compraventa/', ContratosViewSet.as_view({'post': 'generar_compraventa'}), name='generar_compraventa'),
    path('dash/generar_promesa_preview/', ContratosViewSet.as_view({'post': 'generar_promesa_preview'}), name='generar_promesa_preview'),
    path('dash/generar_promesa/', ContratosViewSet.as_view({'post': 'generar_promesa'}), name='generar_promesa'),
    path('dash/generar_renta_op_venta/', ContratosViewSet.as_view({'post': 'generar_renta_op_venta'}), name='generar_renta_op_venta'),
    path('dash/generar_renta_op_venta_preview/', ContratosViewSet.as_view({'post': 'generar_renta_op_venta_preview'}), name='generar_renta_op_venta_preview'),
    path('dash/generar_preview_pagare_extra/', ContratosViewSet.as_view({'post': 'generar_preview_pagare_extra'}), name='generar_preview_pagare_extra'),
    path('dash/generar_pagare_extra/', ContratosViewSet.as_view({'post': 'generar_pagare_extra'}), name='generar_pagare_extra'),
    path('dash/generar_cotizacion/', ContratosViewSet.as_view({'post': 'generar_cotizacion'}), name='generar_cotizacion'),
    
    #STRIPE
    path('stripe-webhook/', stripe_webhook, name='stripe-webhook'),
    path('check-payment-status/', CheckPaymentStatus.as_view(), name='check-payment-status'),
    #manejamos el index con la pag404
    path('health/', health_check, name='health_check'),
  
    #manejamos el index con la pag404
    path('', pagina_404, name='error'),   
    path('', include(router.urls)),
]
# urlpatterns += router.urls
