# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""
from . import views
from django.urls import path, re_path, include
from apps.home import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # The home page
    path('', views.index, name='home'),
    path("archivos", views.subirArch, name = "subirArch"),
    
    
    path('pdf', views.generate_pdf, name='pdf'),
    path('generar-pdf/', views.generar_pdf, name='generar_pdf'),
    path('pdf_descarga/', views.pdf_descarga, name='pdf_descarga'),
    path('correo/', views.correo, name='correo'),
    path('poliza/', views.poliza, name='poliza'),
    path('poliza_pdf/', views.poliza_pdf, name='poliza_pdf'),
    path('pagare/', views.pagare, name='pagare'),
    path('pagare_fraterna/', views.pagare_fraterna, name='pagare'),
    path('pagare_fraterna_pdf/', views.pagare_fraterna_pdf, name='pagare'),
    path('pagare_pdf/', views.pagare_pdf, name='pagare_pdf'),
    path('contrato/', views.contrato, name='contrato'),
    path('contrato_pdf/', views.contrato_pdf, name='contrato_pdf'),
    path('contrato_fraterna_pdf/', views.contrato_fraterna_pdf, name='contrato_fraterna_pdf'),
    path('aprobado_pdf/', views.generar_pdf_aprobado, name='generar_pdf_aprobado'),
    path('nuevo_resultado_pdf/', views.nuevo_resultado, name='nuevo_resultado'),
    path('contrato_arr_frat/', views.contrato_arrendify_fraterna_pdf, name='contrato_arr_frat'),

    #Pruebas Renovacion
    path('renovar_contrato/', views.renovar_contrato, name='renovar_contrato'),
 
    
    # #Rutas Arrendador
    # path('registro_arr/', views.reg_arr, name='reg_arr'),   
    # path('arrendadores/', views.arrendadores, name='arrendadores'),
    # path('detalles_arr/<str:id>', views.ver_arrendador, name='Det_arr'), 
    # path('editar_arr/<str:id>', views.editar_arr, name='editar_arr'),
    # path('eliminar_arr/<str:id>', views.eliminar_arr, name='eliminar_arr'),


    # Rutas arrendador API
    # path('usuarios/', include('apps.api.urls')),
    
    #Rutas Inmuebles
    # path('reg_inmueble', views.reg_inmueble, name='createin'),
    # path('inmuebles/', views.listarInmueble, name='listarInmueble'),
    # path('editarin/<slug:slug>', views.editarInmueble, name='editarin'),
    # path('removerin/<id>', views.removerInmueble, name='removerin'),
    
    
   
    # Matches any html file
    re_path(r'^.*\.*', views.pages, name='pages'),
    # path("", include("apps.home.urls")), 

]
if settings.DEBUG: 
    urlpatterns += static(
        settings.MEDIA_URL, 
        document_root = settings.MEDIA_ROOT
    )