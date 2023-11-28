# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.urls import path, re_path
from apps.home import views

urlpatterns = [

    # The home page
    path('', views.index, name='home'),    
    path('inquilinos/', views.path_inq, name='inquilinos'),    
    path('detalles_inquilino/<int:id>', views.path_inq_detalles, name='inquilinos_detalles'),    
    path('editar_inq/<int:id>', views.path_inq_edit, name='inquilinos_editar'),    

    path('inmuebles/', views.path_inmuebles, name='inmuebles'),   
    path('fiador_obligado/', views.path_foo, name='fiador_obligado'),   
    path('detalles_fiador/<str:slug>', views.path_foo_detalles, name='inquilinos_detalles'),    
    path('editar_fiador/<int:id>', views.path_foo_edit, name='inquilinos_editar'),  

    # Matches any html file
    re_path(r'^.*\.*', views.pages, name='pages'),

]
