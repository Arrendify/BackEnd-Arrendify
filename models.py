# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from calendar import c
from pyexpat import model
from tabnanny import verbose
from tkinter.tix import Tree
from unittest.util import _MAX_LENGTH
from django.db import models
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify

class Rol(models.Model):
      id = models.AutoField(primary_key=True)
      Name=models.CharField(max_length=20)
      created=models.DateTimeField(auto_now_add=True)
      updated=models.DateTimeField(auto_now_add=True)
      class Meta:
            verbose_name="Rol"
            verbose_name_plural="Roles"
      def __str__(self):
            return self.Name

class Profile(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    roles =models.ManyToManyField(Rol)
    direccion=models.CharField(max_length=10,null=True)


class Inquilino(models.Model):
    # datos personales
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    p_fom=models.CharField(max_length=30, blank=True)
    nombre=models.CharField(max_length=30, blank=True)
    apellido= models.CharField(max_length=30, null=True, blank=True)
    apellido1=models.CharField(max_length=30, null=True, blank=True)
    rfc=models.CharField(max_length=13, null=True, blank=True)
    estado_civil=models.CharField(max_length=30,null=True, blank=True)
    n_conyuge=models.CharField(max_length=30, null=True, blank=True)
    a_conyuge=models.CharField(max_length=30, null=True, blank=True)
    a1_conyuge=models.CharField(max_length=30, null=True, blank=True)    
    numeroTel=models.PositiveIntegerField(null=True, blank=True) 
    numeroTel1=models.PositiveIntegerField(null=True, blank=True) 
    email=models.EmailField()
   
    # datos domiciliarios
    calle=models.CharField(max_length=30, null=True, blank=True)
    num_int=models.PositiveIntegerField(null=True, blank=True)
    num_ext=models.CharField(max_length=30,null=True, blank=True)
    colonia=models.CharField(max_length=30, null=True, blank=True)
    estado=models.CharField(max_length=30, null=True, blank=True)
    codigopostal=models.PositiveIntegerField(null=True, blank=True)
    municipio_alcaldia=models.CharField(max_length=30, null=True, blank=True)
    referencias=models.CharField(max_length=100, null=True, blank=True)
    
    #Datos Empleo
    profesion=models.CharField(max_length=30, null=True, blank=True)
    antiguedad=models.PositiveIntegerField(null=True, blank=True)
    puesto=models.CharField(max_length=30, null=True, blank=True)
    tel_empleo=models.PositiveIntegerField(null=True, blank=True)
    ingreso_men=models.PositiveIntegerField(null=True, blank=True)
    nombre_empresa=models.CharField(max_length=30, null=True, blank=True)
    email_empresarial=models.EmailField(null=True, blank=True)
    cel_empleo=models.PositiveIntegerField(null=True, blank=True)
    
    #Jefe
    jefe=models.CharField(max_length=30, null=True, blank=True)
    puesto_jefe=models.CharField(max_length=30, null=True, blank=True)
    pagina_web=models.CharField(max_length=30, null=True, blank=True)
    giro=models.CharField(max_length=30, null=True, blank=True)
    tel_jefe=models.PositiveIntegerField(null=True, blank=True)
    email_jefe=models.EmailField(null=True, blank=True)

    #acta constitutiva
    empresa_constituida = models.CharField(max_length=50, null=True, blank=True)
    escritura_numero_ac = models.CharField(max_length=50, null=True, blank=True)
    fecha_ac = models.DateTimeField(auto_now=False, auto_now_add=False, null=True, blank=True)
    nombre_notario_ac = models.CharField(max_length=50, null=True, blank=True)
    coe = models.CharField(max_length=30, null=True, blank=True)
    folio_mercantil = models.PositiveIntegerField(null=True, blank=True)

    #Direccion empleo
    calle_empleo=models.CharField(max_length=60, null=True, blank=True)
    num_int_empleo=models.PositiveIntegerField(null=True, blank=True)
    num_ext_empleo=models.CharField(max_length=30,null=True, blank=True)
    colonia_empleo=models.CharField(max_length=30,null=True, blank=True)
    ciudad_empleo=models.CharField(max_length=30, null=True, blank=True)
    codigo_postal_empleo=models.PositiveIntegerField(null=True, blank=True)
    municipio_empleo=models.CharField(max_length=30, null=True, blank=True)
    
      # Referencia del Arrendatario Anterior
    rentado_antes=models.CharField(max_length=2, null=True, blank=True)
    nombre_aa=models.CharField(max_length=30, null=True, blank=True)
    monto_renta_aa=models.PositiveIntegerField(null=True, blank=True)
    telefono_aa=models.PositiveIntegerField(null=True, blank=True)
    motivo_cambio=models.CharField(max_length=100, null=True, blank=True)
    renta_compartida = models.CharField(max_length=2, null=True, blank=True)
    no_renta_compartida = models.CharField(max_length=5, null=True, blank=True)
    #Dom Inmueble Arrendado
    calle_dia=models.CharField(max_length=30, null=True, blank=True)
    num_int_dia=models.PositiveIntegerField(null=True, blank=True)
    num_ext_dia=models.CharField(max_length=30,null=True, blank=True)
    colonia_dia=models.CharField(max_length=30,null=True, blank=True)
    ciudad_dia=models.CharField(max_length=30, null=True, blank=True)
    codigo_postal_dia=models.PositiveIntegerField(null=True, blank=True)
    municipio_dia=models.CharField(max_length=30, null=True, blank=True)
    
    # Referencias Personales
    n_ref1=models.CharField(max_length=30, null=True, blank=True)
    p_ref1=models.CharField(max_length=30, null=True, blank=True)
    tel_ref1=models.PositiveIntegerField(null=True, blank=True)
    n_ref2=models.CharField(max_length=30, null=True, blank=True)
    p_ref2=models.CharField(max_length=30, null=True, blank=True)
    tel_ref2=models.PositiveIntegerField(null=True, blank=True)
    n_ref3=models.CharField(max_length=30, null=True, blank=True)
    p_ref3=models.CharField(max_length=30, null=True, blank=True)
    tel_ref3=models.PositiveIntegerField(null=True, blank=True)
    
    # Inquilinos
    no_inquilinos = models.PositiveIntegerField(null=True, blank=True)
    n_inquilino1=models.CharField(max_length=30, null=True, blank=True)
    p_inquilino1=models.CharField(max_length=30, null=True, blank=True)
    n_inquilino2=models.CharField(max_length=30, null=True, blank=True)
    p_inquilino2=models.CharField(max_length=30, null=True, blank=True)
    n_inquilino3=models.CharField(max_length=30, null=True, blank=True)
    p_inquilino3=models.CharField(max_length=30, null=True, blank=True)
    n_inquilino4=models.CharField(max_length=30, null=True, blank=True)
    p_inquilino4=models.CharField(max_length=30, null=True, blank=True)
    n_inquilino5=models.CharField(max_length=30, null=True, blank=True)
    p_inquilino5=models.CharField(max_length=30, null=True, blank=True)
    
    created=models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated=models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        db_table = 'inquilinos'

class Fiador_obligado(models.Model):
    # fiador/oblicado
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    inquilino = models.ForeignKey(Inquilino, null=True, blank=True, on_delete=models.CASCADE,related_name="inquilino")
    fiador_obligado = models.CharField(max_length=35, null=True, blank=True)
   
    #  Datos Del Fiador Solidario flata agregar el empreo y antiguedad
    n_fiador=models.CharField(max_length=30, null=True, blank=True)
    a_fiador=models.CharField(max_length=30, null=True, blank=True)
    a2_fiador=models.CharField(max_length=30, null=True, blank=True)
    rfc_fiador=models.CharField(max_length=30, null=True, blank=True)
    p_fiador=models.CharField(max_length=30, null=True, blank=True)
    estado_civil_fiador=models.CharField(max_length=30, null=True, blank=True)
    
    
    # Datos Domiciliarios del Fiador solidario
    calle_fiador=models.CharField(max_length=30, null=True, blank=True)
    municipio_fiador=models.CharField(max_length=30, null=True, blank=True)
    colonia_fiador=models.CharField(max_length=30,null=True, blank=True)
    estado_fiador=models.CharField(max_length=30, null=True, blank=True)
    n_ext_fiador=models.CharField(max_length=30,null=True, blank=True)
    n_int_fiador=models.PositiveIntegerField(null=True, blank=True)
    cp_fiador=models.PositiveIntegerField(null=True, blank=True)
    tel_fiador=models.PositiveIntegerField(null=True, blank=True)
    tel2_fiador=models.PositiveIntegerField(null=True, blank=True)
    email_fiador=models.EmailField(null=True, blank=True)
    
    prof_fiador=models.CharField(max_length=30, null=True, blank=True)
    empresa_fiador=models.CharField(max_length=30, null=True, blank=True)
    tel_em_fiador=models.PositiveIntegerField(null=True, blank=True)
    ingreso_men_fiador=models.PositiveIntegerField(null=True, blank=True)
    
    # Datos de sus escrituras fiador solidario
    escritura_publica=models.PositiveIntegerField(null=True, blank=True)
    fecha_propiedad=models.DateTimeField(auto_now=False, auto_now_add=False, null=True, blank=True)
    numero_notario=models.PositiveIntegerField(null=True, blank=True)
    nombre_notario=models.CharField(max_length=30, null=True, blank=True)
    
    # recibos
    recibos=models.CharField(max_length=2, null=True, blank=True)
    
    # OBLIGADO PERSONA MORAL
    #Datos empresa del obligado PM
    nombre_comercial=models.CharField(max_length=30, null=True, blank=True)
    rfc_fiador_em=models.CharField(max_length=30, null=True, blank=True)
    ingreso_fiador_opm=models.PositiveIntegerField(null=True, blank=True)
    antiguedad_opm=models.PositiveIntegerField(null=True, blank=True)
    tel_opm=models.PositiveIntegerField(null=True, blank=True)
    cel_opm=models.PositiveIntegerField(null=True, blank=True)
    email_em_opm=models.EmailField(null=True, blank=True)
    pagina_web_f=models.CharField(max_length=100, null=True, blank=True)
    
    # acta constituida
    escritura_publica_ac = models.CharField(max_length=50, null=True, blank=True)
    fecha_propiedad_ac = models.DateTimeField(auto_now=False, auto_now_add=False, null=True, blank=True)
    nombre_notario_ac = models.CharField(max_length=50, null=True, blank=True)
    coe = models.CharField(max_length=30, null=True, blank=True)
    folio_mercantil = models.PositiveIntegerField(null=True, blank=True)
    
    # Direccion fiscal empresa Fiador solidario PM
    calle_em_pm=models.CharField(max_length=30, null=True, blank=True)
    n_ext_em_pm=models.CharField(max_length=30,null=True, blank=True)
    n_int_em_pm=models.PositiveIntegerField(null=True, blank=True)
    colonia_em_pm=models.CharField(max_length=30,null=True, blank=True)
    cp_em_pm=models.PositiveIntegerField(null=True, blank=True)
    municipio_em_pm=models.CharField(max_length=30, null=True, blank=True)
    estado_em_pm=models.CharField(max_length=30, null=True, blank=True)
    
    # Datos Generales representante legal
    nombre_rl=models.CharField(max_length=30, null=True, blank=True)
    apellido_rl=models.CharField(max_length=30, null=True, blank=True)
    apellido1_rl=models.CharField(max_length=30, null=True, blank=True)
    cel_rl=models.PositiveIntegerField(null=True, blank=True)
    email_rl=models.EmailField(null=True, blank=True)
    pagina_rl=models.CharField(max_length=100, null=True, blank=True)
    
    # Direccion representante legal Fiador solidario PM
    calle_rl=models.CharField(max_length=50, null=True, blank=True)
    n_ext_rl=models.CharField(max_length=30,null=True, blank=True)
    n_int_rl=models.PositiveIntegerField(null=True, blank=True)
    colonia_rl=models.CharField(max_length=30,null=True, blank=True)
    cp_rl=models.PositiveIntegerField(null=True, blank=True)
    municipio_rl=models.CharField(max_length=30, null=True, blank=True)
    estado_rl=models.CharField(max_length=30, null=True, blank=True)
    
     # referencia1
    nombre_empresa=models.CharField(max_length=30, null=True, blank=True)
    nombre_contacto=models.CharField(max_length=30,null=True, blank=True)
    tiempo_relacion=models.CharField(max_length=30,null=True, blank=True)
    tel_ref=models.PositiveIntegerField(null=True, blank=True)
    email_ref=models.EmailField(null=True, blank=True)
    cel_ref=models.PositiveIntegerField(null=True, blank=True)
    relacion_comercial = models.CharField(max_length=50, null=True, blank=True)
    
    # referencia2
    nombre_empresa2=models.CharField(max_length=30, null=True, blank=True)
    nombre_contacto2=models.CharField(max_length=30,null=True, blank=True)
    tiempo_relacion2=models.CharField(max_length=30,null=True, blank=True)
    tel_ref2=models.PositiveIntegerField(null=True, blank=True)
    email_ref2=models.EmailField(null=True, blank=True)
    cel_ref2=models.PositiveIntegerField(null=True, blank=True)
    relacion_comercial2 = models.CharField(max_length=50, null=True, blank=True)
        
    created=models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated=models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        db_table = 'fiador_obligado'

class Zip_code(models.Model):
    id = models.AutoField(primary_key=True)
    d_codigo = models.CharField(max_length=100, null=True,blank=True)
    d_asenta = models.CharField(max_length=100, null=True,blank=True)
    d_tipo_asenta = models.CharField(max_length=100, null=True,blank=True)
    d_mnpio = models.CharField(max_length=100, null=True,blank=True)
    d_estado = models.CharField(max_length=100, null=True,blank=True)
    d_ciudad = models.CharField(max_length=100, null=True,blank=True)
    
    class Meta:
        db_table = 'zip_codes'

class Arrendador(models.Model):
    # inmueble = models.ForeignKey(Inmueble, null=True, blank=True, on_delete=models.SET_NULL)
    
    # datos personales
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    pmoi = models.CharField(max_length=30) 
    dir_ac = models.CharField(max_length=150, null=True, blank=True) 
    nombre=models.CharField(max_length=30, blank=True)
    apellido= models.CharField(max_length=30, null=True, blank=True)
    apellido1=models.CharField(max_length=30, null=True, blank=True)
    rfc=models.CharField(max_length=13, null=True, blank=True)
    estado_civil=models.CharField(max_length=30,null=True, blank=True)
    n_conyuge=models.CharField(max_length=30, null=True, blank=True)
    a_conyuge=models.CharField(max_length=30, null=True, blank=True)
    a1_conyuge=models.CharField(max_length=30, null=True, blank=True)    
    numeroTel=models.PositiveIntegerField(null=True, blank=True) 
    numeroTel1=models.PositiveIntegerField(null=True, blank=True) 
    email=models.EmailField(null=True, blank=True)
   
    # datos domiciliarios
    calle=models.CharField(max_length=30, null=True, blank=True)
    num_int=models.PositiveIntegerField(null=True, blank=True)
    num_ext=models.CharField(max_length=30,null=True, blank=True)
    colonia=models.CharField(max_length=30, null=True, blank=True)
    estado=models.CharField(max_length=30, null=True, blank=True)
    codigopostal=models.PositiveIntegerField(null=True, blank=True)
    municipio_alcaldia=models.CharField(max_length=30, null=True, blank=True)
    referencias=models.CharField(max_length=100, null=True, blank=True)
    
    #acta constitutiva
    empresa_constituida = models.CharField(max_length=50, null=True, blank=True)
    escritura_numero_ac = models.CharField(max_length=50, null=True, blank=True)
    fecha_ac = models.DateField(auto_now=False, auto_now_add=False, null=True, blank=True)
    nombre_notario_ac = models.CharField(max_length=50, null=True, blank=True)
    coe = models.CharField(max_length=30, null=True, blank=True)
    folio_mercantil = models.PositiveIntegerField(null=True, blank=True)

    #Direccion empleo
    calle_empleo=models.CharField(max_length=60, null=True, blank=True)
    num_int_empleo = models.PositiveIntegerField(null=True, blank=True)
    num_ext_empleo = models.CharField(max_length=30,null=True, blank=True)
    colonia_empleo = models.CharField(max_length=30,null=True, blank=True)
    ciudad_empleo = models.CharField(max_length=30, null=True, blank=True)
    codigo_postal_empleo = models.PositiveIntegerField(null=True, blank=True)
    municipio_empleo=models.CharField(max_length=30, null=True, blank=True)
    
    #inmobiliaria
    n_inmobiliaria = models.CharField(max_length=50, null=True, blank=True)
    per_sol = models.CharField(max_length=50, null=True, blank=True)
    cel = models.PositiveIntegerField(null=True, blank=True)
    tel = models.PositiveIntegerField(null=True, blank=True)
    email_in = models.EmailField(null=True,blank=True)
    #Datos Del Propietario
    doc = models.CharField(max_length=50, null=True, blank=True)
    n_propietario = models.CharField(max_length=50, null=True, blank=True)
    rfc_propietario = models.CharField(max_length=13, null=True, blank=True)
    ecp = models.CharField(max_length=50, null=True, blank=True)
    #Domicilio Particular
    calle_prop = models.CharField(max_length=30, null=True, blank=True)
    num_int_prop = models.PositiveIntegerField(null=True, blank=True)
    num_ext_prop = models.CharField(max_length=30,null=True, blank=True)
    colonia_prop = models.CharField(max_length=30, null=True, blank=True)
    estado_prop = models.CharField(max_length=30, null=True, blank=True)
    codigo_postal_prop = models.PositiveIntegerField(null=True, blank=True)
    municipio_prop = models.CharField(max_length=30, null=True, blank=True)
    #contacto y extras
    tel_arr = models.PositiveIntegerField(null=True, blank=True)
    cel_arr = models.PositiveIntegerField(null=True, blank=True)
    email_arr = models.EmailField(null=True,blank=True)
    tipo_pago = models.CharField(max_length=30, null=True, blank=True)
    banco = models.CharField(max_length=30, null=True, blank=True)
    titular = models.CharField(max_length=30, null=True, blank=True)
    no_cuenta = models.PositiveIntegerField(null=True, blank=True)
    clabe = models.PositiveIntegerField(null=True, blank=True)

    observaciones= models.CharField(max_length=200, null=True, blank=True)

    # Datos De Inicio Contrato
    fecha_solicitud = models.DateField(null=True, blank=True)
    fecha_firma = models.DateField(null=True, blank=True)
    hora_firma = models.TimeField(null=True, blank=True)
    lugar_firma = models.CharField(max_length=100, null=True, blank=True)
    
    created=models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated=models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        db_table = 'arrendador'

def get_ine_upload_path(request, filename):
    return f'{request.user}/INE/{filename}'
def get_dom_upload_path(request, filename):
    return f'{request.user}/Comprobante de domicilio/{filename}'
def get_rfc_upload_path(request, filename):
    return f'{request.user}/RFC/{filename}'

class DocumentosInquilino(models.Model):
    id = models.AutoField(primary_key=True)
    user=models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    Ine = models.FileField(upload_to=get_ine_upload_path)
    Comp_dom = models.FileField(upload_to =get_dom_upload_path)
    Rfc = models.FileField(upload_to = get_rfc_upload_path)
    dateTimeOfUpload = models.DateTimeField(auto_now = True)
    class Meta:
        db_table = 'documentos_inquilino'

class DocumentosArrendador(models.Model):
    id = models.AutoField(primary_key=True)
    user=models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ine = models.FileField(upload_to=get_ine_upload_path)
    comp_dom = models.FileField(upload_to =get_dom_upload_path)
    predial = models.FileField(upload_to = get_rfc_upload_path,null=True, blank=True)
    escrituras_titulo = models.FileField(upload_to = get_rfc_upload_path,)

    dateTimeOfUpload = models.DateTimeField(auto_now = True)
    class Meta:
        db_table = 'documentos_arrendador'

class Inmuebles(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    alias_inmueble = models.CharField(max_length=30, null=True, blank=True)
    estatus_inmueble = models.CharField(max_length=30, null=True, blank=True)
    renta = models.PositiveIntegerField(null=True, blank=True)
    venta = models.PositiveIntegerField(null=True, blank=True)
    clave_catastral = models.CharField(max_length=30, null=True, blank=True)
    estatus_gravamen = models.CharField(max_length=30, null=True, blank=True)
    valor_catastral = models.PositiveIntegerField(null=True, blank=True)
    cuota_mantenimiento= models.PositiveIntegerField(null=True, blank=True)
    tipo_inmueble = models.CharField(max_length=30, null=True, blank=True)
    uso_inmueble= models.CharField(max_length=30, null=True, blank=True)
    op_compra = models.CharField(max_length=30, null=True, blank=True)
    municipio_alcaldia = models.CharField(max_length=30, null=True, blank=True)
    colonia = models.CharField(max_length=30, null=True, blank=True)
    postal_code = models.CharField(max_length=30, null=True, blank=True)
    estado  = models.CharField(max_length=30, null=True, blank=True)
    calle = models.CharField(max_length=30, null=True, blank=True)
    numeroExterior = models.CharField(max_length=30, null=True, blank=True)
    numeroInterior = models.CharField(max_length=30, null=True, blank=True)
    calle1 = models.CharField(max_length=30, null=True, blank=True)
    calle2 = models.CharField(max_length=30, null=True, blank=True)
    referencias = models.CharField(max_length=100, null=True, blank=True)
    n_baños = models.PositiveIntegerField(null=True, blank=True)
    n_medios_baños = models.PositiveIntegerField(null=True, blank=True)
    n_recamaras = models.PositiveIntegerField(null=True, blank=True)
    n_pisos = models.PositiveIntegerField(null=True, blank=True)
    estacionamiento_cajones = models.PositiveIntegerField(null=True, blank=True)
    terrenoConstruido  = models.PositiveIntegerField(null=True, blank=True)
    terrenoTotal = models.PositiveIntegerField(null=True, blank=True)    
    año_contruccion = models.PositiveIntegerField(null=True, blank=True)
    garage = models.CharField(max_length=30, null=True, blank=True)
    bodega = models.CharField(max_length=30, null=True, blank=True)
    terraza =  models.CharField(max_length=30, null=True, blank=True)
    alberca =  models.CharField(max_length=30, null=True, blank=True)
    cocina =  models.CharField(max_length=30, null=True, blank=True)
    amueblado = models.CharField(max_length=30, null=True, blank=True)
    cuarto_lavado =models.CharField(max_length=30, null=True, blank=True)
    gym = models.CharField(max_length=30, null=True, blank=True)
    bar = models.CharField(max_length=30, null=True, blank=True)
    restaurante_bar=models.CharField(max_length=30, null=True, blank=True)
    sala_cine = models.CharField(max_length=30, null=True, blank=True)
    salon_estudio = models.CharField(max_length=30, null=True, blank=True)
    area_comun = models.CharField(max_length=30, null=True, blank=True)
    sala_juegos = models.CharField(max_length=30, null=True, blank=True)
    salon_eventos = models.CharField(max_length=30, null=True, blank=True)
    espacio_deportivo = models.CharField(max_length=30, null=True, blank=True)
    busisness_center = models.CharField(max_length=30, null=True, blank=True)
    roof_garden = models.CharField(max_length=30, null=True, blank=True)
    otroA = models.CharField(max_length=30, null=True, blank=True)
    internet  = models.CharField(max_length=30, null=True, blank=True)
    electricidad  = models.CharField(max_length=30, null=True, blank=True)    
    agua_potable = models.CharField(max_length=30, null=True, blank=True)
    televisionCable = models.CharField(max_length=30, null=True, blank=True)
    gas = models.CharField(max_length=30, null=True, blank=True)
    lineaTelefonica = models.CharField(max_length=30, null=True, blank=True)
    drenaje = models.CharField(max_length=30, null=True, blank=True)
    seguridad = models.CharField(max_length=30, null=True, blank=True)
    camarasSeguridad  = models.CharField(max_length=30, null=True, blank=True)
    area_juegos = models.CharField(max_length=30, null=True, blank=True)
    otroS = models.CharField(max_length=30, null=True, blank=True)
    
   

    descripcion= models.CharField(max_length=200, null=True, blank=True)
    terminos_condiciones = models.CharField(max_length=30, null=True, blank=True)
    
    codigo = models.PositiveIntegerField(null=True, blank=True)
    slug = models.SlugField(null=True, blank=True)
    created=models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated=models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.id:    
            # Obtener el último registro creado por persona y sumar 1 al código.
            ultimo_registro = Inmuebles.objects.filter(user=self.user).last()
            self.codigo = 1 if not ultimo_registro else ultimo_registro.codigo + 1
            
            if not self.codigo:
                #slug repetido con code
                slu= self.alias_inmueble + str(self.codigo)
                #slu= self.alias_inmueble  + str(self.codigo) if Inmuebles.objects.filter(alias_inmueble = self.alias_inmueble).exists() else self.alias_inmueble 
                self.slug = slugify(slu)
            else:
                #slug sin code
                slu= self.alias_inmueble
                self.slug = slugify(slu)
        else:
            verinmueble=Inmuebles.objects.filter(user_id=self.user).get(id=self.id)
            print("ver inmuebel:",verinmueble)
            self.codigo = verinmueble.codigo
            self.slug = verinmueble.slug
            print("codigo",self.codigo)
            print("slug",self.slug)    
        super().save(*args, **kwargs)
        
    def get_absolute_url(self):
        return reverse('Actualizacion', kwargs={'pk': self.pk})

    def __str__(self):
        return f"{self.alias_inmueble} {self.tipo_inmueble}"

    class Meta:
        db_table = 'inmuebles'
        
class ImagenInmueble (models.Model):
    def get_img_inmueble_upload_path(self,filename):
        return f'{self.user}/Inmuebles/{self.inmueble.alias_inmueble}/{filename}'
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    imagenes = models.ImageField(upload_to=get_img_inmueble_upload_path)
    inmueble = models.ForeignKey(Inmuebles, on_delete=models.CASCADE,related_name="fotos")
    print(Inmuebles.alias_inmueble)
    
    class Meta:
        db_table = 'imagenes_inmueble'

# class productos(models.Model):
#     id = models.AutoField(primary_key=True)
#     tipo_producto = models.CharField(max_length=30, null=True, blank=True)
#     nombre_producto = models.CharField(max_length=30, null=True, blank=True) 
#     categoria_producto = models.CharField(max_length=50, null=True, blank=True)
#     etiqueta_producto = models.CharField(max_length=50, null=True, blank=True)
#     costo_producto = models.CharField(max_length=50, null=True, blank=True)
#     descripción_producto = models.CharField(max_length=50, null=True, blank=True)

#     class Meta:
#         db_table = 'Productos'

# class paquetes(models.Model):
#     id = models.AutoField(primary_key=True)
#     producto = models.ForeignKey(productos, null = True, blank = True, on_delete=models.CASCADE)
#     tipo_paquete = models.CharField(max_length=30, null=True, blank=True)
#     nombre_paquete = models.CharField(max_length=30, null=True, blank=True) 
#     categoria_paquete = models.CharField(max_length=50, null=True, blank=True)
#     etiqueta_paquete = models.CharField(max_length=50, null=True, blank=True)
#     costo_paquete = models.CharField(max_length=50, null=True, blank=True)
#     descripción_paquete = models.CharField(max_length=50, null=True, blank=True)

#     class Meta:
#         db_table = 'Paquetes'
