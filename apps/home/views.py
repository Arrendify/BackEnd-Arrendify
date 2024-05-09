"""
Copyright (c) 2019 - present AppSeed.us
"""

from multiprocessing import context
from django import template
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseBadRequest, JsonResponse, Http404
from django.template import loader
from django.urls import reverse
from requests import get
from .models import FraternaContratos, Inmuebles, InmueblesInmobiliario, Inquilino, Arrendador, ImagenInmueble, DocumentosInquilino, Fiador_obligado,Cotizacion,Investigacion,Paquetes
from django.shortcuts import redirect, render, get_object_or_404
from .forms import InquilinosForm, InmueblesForm, ArrendadorForm, ImagenInmuelbeForm, FiadorForm
from time import sleep
import os
from django.core.paginator import Paginator
from django.views.generic import View
from ..api.utils import render_to_pdf
#weasyprint
from weasyprint import HTML, CSS
from django.template.loader import render_to_string
from django.template.loader import get_template
#Aprobado Legal
from num2words import num2words
from datetime import date
from datetime import datetime
from dateutil.relativedelta import relativedelta
#Libreria para obtener el lenguaje en español
import locale


def generate_pdf(request):
    #podemos usar lo modelos de la conexion a la base de datos para mostrarlos desde una variable con f string
    total_personas = Cotizacion.objects.count()
    info = Cotizacion.objects.all().first()
    datos = info.__dict__
    print(datos)
    print(info.nombre_cotizacion)
    return render(request, "home/acp.html", context={"info": info, "total_personas": total_personas})

def pagare(request):
    info = Paquetes.objects.all().first()
    meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
    meses_años = {}
    meses_restantes = {}
    #estabelcemos la fecha
    #fecha_cotizacion = str(date.today())
    fecha_cotizacion = info.datos_arrendamiento['fecha_de_pago']
    # print("SOY EL FORMATO DE FECHA COTIZACION2",fecha_cotizacion2['fecha_de_pago'])
    print("SOY EL FORMATO DE FECHA COTIZACION",fecha_cotizacion)
    fecha_cotizacion_datetime = datetime.strptime(fecha_cotizacion, '%Y-%m-%d')
    dia = fecha_cotizacion_datetime.day
    anio = fecha_cotizacion_datetime.year
    
    # El mes en numero
    mes = fecha_cotizacion_datetime.month
    #si el mes es enero solo realiza una lista
    lista_mes = list(meses.values())[(mes - 1):]
    #iteramos la lista para añadir el año actual
    for i in range(len(lista_mes)):
        meses_años[lista_mes[i]] = anio
    #si no realiza 2
    if(mes != 1):
        lista_mes_restantes = list(meses.values())[(0):(mes-1)]
        #iteramos la lista de los meses restantes para añadir el año siguente        
        for i in range(len(lista_mes_restantes)):
            meses_restantes[lista_mes_restantes[i]] = anio + 1
        #juntamos los 2 dicionarios para mandarlo como contexto
        lista_total = {**meses_años, **meses_restantes}
    else:
        lista_total = meses_años
    
    #la info del paquete que se recibe
    
    datos = info.inmueble
    print(datos.__dict__)
    print(info.fiador.__dict__)
    #obtenermos la renta para pasarla a letra
    number = datos.renta
    number = int(number)
    text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    text_representation = text_representation.capitalize()
    
    context = {'info': info, 'dia':dia ,'lista_fechas':lista_total, 'text_representation':text_representation}
    return render(request, "home/plan.html", context)

def pagare_pdf(request):
    info = Paquetes.objects.all().first()
    meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
    meses_años = {}
    meses_restantes = {}
    #estabelcemos la fecha
    fecha_cotizacion = info.datos_arrendamiento['fecha_de_pago']
    # print("SOY EL FORMATO DE FECHA COTIZACION2",fecha_cotizacion2['fecha_de_pago'])
    print("SOY EL FORMATO DE FECHA COTIZACION",fecha_cotizacion)
    fecha_cotizacion_datetime = datetime.strptime(fecha_cotizacion, '%Y-%m-%d')
    dia = fecha_cotizacion_datetime.day
    anio = fecha_cotizacion_datetime.year
    
    # El mes en numero
    mes = fecha_cotizacion_datetime.month
    #si el mes es enero solo realiza una lista
    lista_mes = list(meses.values())[(mes - 1):]
    #iteramos la lista para añadir el año actual
    for i in range(len(lista_mes)):
        meses_años[lista_mes[i]] = anio
    #si no realiza 2
    if(mes != 1):
        lista_mes_restantes = list(meses.values())[(0):(mes-1)]
        #iteramos la lista de los meses restantes para añadir el año siguente        
        for i in range(len(lista_mes_restantes)):
            meses_restantes[lista_mes_restantes[i]] = anio + 1
        #juntamos los 2 dicionarios para mandarlo como contexto
        lista_total = {**meses_años, **meses_restantes}
    else:
        lista_total = meses_años
    
    #la info del paquete que se recibe
    datos = info.inmueble
    print(datos.__dict__)
    print(info.fiador.__dict__)
    
    #obtenermos la renta para pasarla a letra
    number = datos.renta
    number = int(number)
    text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    text_representation = text_representation.capitalize()
    
    context = {'info': info, 'dia':dia ,'lista_fechas':lista_total, 'text_representation':text_representation}
    template = 'home/plan.html'
    html_string = render_to_string(template, context)

    # Genera el PDF utilizando weasyprint
    pdf_file = HTML(string=html_string).write_pdf()

    # Devuelve el PDF como respuesta
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="mi_pagare.pdf"'
    response.write(pdf_file)

    
    return HttpResponse(response, content_type='application/pdf')

def poliza(request):
    info = Paquetes.objects.all().first()
    meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
   
    #estabelcemos la fecha de inicio 
    fecha_inicio = info.datos_arrendamiento['fecha_inicio_contrato']
    print("SOY EL FORMATO DE FECHA inicio",fecha_inicio)
    fecha_inicio_datetime = datetime.strptime(fecha_inicio, '%Y-%m-%d')
    dia = fecha_inicio_datetime.day
    mes = fecha_inicio_datetime.month
    mes_inicio = meses[mes]
    anio = fecha_inicio_datetime.year
    datos_inicio = {'dia':dia, 'anio':anio ,'mes':mes_inicio}
    
    #estabelcemos la fecha de fin
    fecha_fin = info.datos_arrendamiento['fecha_fin_contrato']
    fecha_fin_datetime = datetime.strptime(fecha_fin, '%Y-%m-%d')
    dia_fin = fecha_fin_datetime.day
    mes2 = fecha_fin_datetime.month
    mes_fin = meses[mes2]
    anio_fin = fecha_fin_datetime.year
    datos_fin = {'dia':dia_fin, 'anio':anio_fin ,'mes':mes_fin}
    
    #estabelcemos la fecha de fin
    fecha_firma = info.datos_arrendamiento['fecha_firma']
    fecha_firma_datetime = datetime.strptime(fecha_firma, '%Y-%m-%d')
    dia_firma = fecha_firma_datetime.day
    mes3 = fecha_firma_datetime.month
    mes_firma = meses[mes3]
    anio_firma = fecha_firma_datetime.year
    datos_firma = {'dia':dia_firma, 'anio':anio_firma ,'mes':mes_firma}
        
    datos = info.inmueble
    print(datos.__dict__)
    print(info.fiador.__dict__)
    #obtenermos la renta para pasarla a letra
    number = datos.renta
    number = int(number)
    text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    text_representation = text_representation.capitalize()
    #obtenermos el precio de la poliza para pasarla a letra
    precio = info.cotizacion.monto
    precio = int(precio)
    print(precio)
    precio_texto = num2words(precio, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    precio_texto = precio_texto.capitalize()
    
    context = {'info': info, 'datos_inicio':datos_inicio, 'datos_fin':datos_fin,'datos_firma':datos_firma, 'text_representation':text_representation,'precio_texto':precio_texto}

    return render(request, "home/poliza_platino.html", context)

def poliza_pdf(request):
    info = Paquetes.objects.all().first()
    meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
   
    #estabelcemos la fecha de inicio 
    fecha_inicio = info.datos_arrendamiento['fecha_inicio_contrato']
    print("SOY EL FORMATO DE FECHA inicio",fecha_inicio)
    fecha_inicio_datetime = datetime.strptime(fecha_inicio, '%Y-%m-%d')
    dia = fecha_inicio_datetime.day
    mes = fecha_inicio_datetime.month
    mes_inicio = meses[mes]
    anio = fecha_inicio_datetime.year
    datos_inicio = {'dia':dia, 'anio':anio ,'mes':mes_inicio}
    
    #estabelcemos la fecha de fin
    fecha_fin = info.datos_arrendamiento['fecha_fin_contrato']
    fecha_fin_datetime = datetime.strptime(fecha_fin, '%Y-%m-%d')
    dia_fin = fecha_fin_datetime.day
    mes2 = fecha_fin_datetime.month
    mes_fin = meses[mes2]
    anio_fin = fecha_fin_datetime.year
    datos_fin = {'dia':dia_fin, 'anio':anio_fin ,'mes':mes_fin}
    
    #estabelcemos la fecha de fin
    fecha_firma = info.datos_arrendamiento['fecha_firma']
    fecha_firma_datetime = datetime.strptime(fecha_firma, '%Y-%m-%d')
    dia_firma = fecha_firma_datetime.day
    mes3 = fecha_firma_datetime.month
    mes_firma = meses[mes3]
    anio_firma = fecha_firma_datetime.year
    datos_firma = {'dia':dia_firma, 'anio':anio_firma ,'mes':mes_firma}
        
    datos = info.inmueble
    print(datos.__dict__)
    print(info.fiador.__dict__)
    #obtenermos la renta para pasarla a letra
    number = datos.renta
    number = int(number)
    text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    text_representation = text_representation.capitalize()
    #obtenermos el precio de la poliza para pasarla a letra
    precio = info.cotizacion.monto
    precio = int(precio)
    print(precio)
    precio_texto = num2words(precio, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    precio_texto = precio_texto.capitalize()
    
    context = {'info': info, 'datos_inicio':datos_inicio, 'datos_fin':datos_fin,'datos_firma':datos_firma, 'text_representation':text_representation,'precio_texto':precio_texto}

    template = 'home/poliza_plata.html'
    html_string = render_to_string(template, context)

    # Genera el PDF utilizando weasyprint
    pdf_file = HTML(string=html_string).write_pdf()

    # Devuelve el PDF como respuesta
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
    response.write(pdf_file)

    return HttpResponse(response, content_type='application/pdf')

def contrato(request):
    info = Paquetes.objects.all().first()
    meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
   
    #estabelcemos la fecha de inicio 
    fecha_inicio = info.datos_arrendamiento['fecha_inicio_contrato']
    print("SOY EL FORMATO DE FECHA inicio",fecha_inicio)
    fecha_inicio_datetime = datetime.strptime(fecha_inicio, '%Y-%m-%d')
    dia = fecha_inicio_datetime.day
    mes = fecha_inicio_datetime.month
    mes_inicio = meses[mes]
    anio = fecha_inicio_datetime.year
    datos_inicio = {'dia':dia, 'anio':anio ,'mes':mes_inicio}
    
    #estabelcemos la fecha de fin
    fecha_fin = info.datos_arrendamiento['fecha_fin_contrato']
    fecha_fin_datetime = datetime.strptime(fecha_fin, '%Y-%m-%d')
    dia_fin = fecha_fin_datetime.day
    mes2 = fecha_fin_datetime.month
    mes_fin = meses[mes2]
    anio_fin = fecha_fin_datetime.year
    datos_fin = {'dia':dia_fin, 'anio':anio_fin ,'mes':mes_fin}
    
    #estabelcemos la fecha de fin
    fecha_firma = info.datos_arrendamiento['fecha_firma']
    fecha_firma_datetime = datetime.strptime(fecha_firma, '%Y-%m-%d')
    dia_firma = fecha_firma_datetime.day
    mes3 = fecha_firma_datetime.month
    mes_firma = meses[mes3]
    anio_firma = fecha_firma_datetime.year
    datos_firma = {'dia':dia_firma, 'anio':anio_firma ,'mes':mes_firma}
        
    datos = info.inmueble
    print(datos.__dict__)
    print(info.fiador.__dict__)
    #obtenermos la renta para pasarla a letra
    number = datos.renta
    number = int(number)
    text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    text_representation = text_representation.capitalize()
    #obtenermos el precio de la poliza para pasarla a letra
    precio = info.cotizacion.monto
    precio = int(precio)
    print(precio)
    precio_texto = num2words(precio, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    precio_texto = precio_texto.capitalize()
    
    #Comprobacion de mobiliario
    mobiliario = InmueblesInmobiliario.objects.all().filter(inmuebles = info.inmueble.id)
    campos_mobiliario = mobiliario.__dict__
    print("campos mobiliario",campos_mobiliario)
    
    # obtenemos la fecha de pago y extraemos el dia
    dia_pago = datetime.strptime(info.datos_arrendamiento['fecha_de_pago'], '%Y-%m-%d')
    dia_pago = dia_pago.day
    print(dia_pago)
    
    #variables de informacion arrendador
    tipo_documento_arrendador= "INE"
    no_doc_arrendador = "5513837024"
    #variables de informacion arrendatario
    tipo_documento_arrendatario= "INE"
    no_doc_arrendatario = "5513837024" 
    #variables de informacion fiador
    tipo_documento_fiador= "PASAPORTE"
    no_doc_fiador = "1819181918"
    doc_indentificacion = {'tipo_documento_arrendador':tipo_documento_arrendador, 'no_doc_arrendador':no_doc_arrendador,
                           'tipo_documento_arrendatario':tipo_documento_arrendatario, 'no_doc_arrendatario':no_doc_arrendatario,
                           'tipo_documento_fiador':tipo_documento_fiador, 'no_doc_fiador':no_doc_fiador}
   
    #variables que selecciona el inquilino
    #Giro
    if info.inmueble.uso_inmueble == "Comercial":
        giro_comercial = "Venta de Bistek"
    else:
        giro_comercial = ""
        
    #Dias de anticipo
    vig_c3 = "103" #tiene que ser de 15 o 30
    vig_c15 = "115" #tiene que ser de 30 con inclementos de 5 en 5 hasta 60
    vig_c23 = "123" # tiene que ser 15, 30 o 60
    vig_c25 = "125" #tiene que ser de 30 con inclementos de 5 en 5 hasta 60
    vig = {'vig_c3':vig_c3, 'vig_c15':vig_c15, 'vig_c23':vig_c23, 'vig_c25':vig_c25}
    context = {'info': info, 'datos_inicio':datos_inicio, 'datos_fin':datos_fin,'datos_firma':datos_firma, 'text_representation':text_representation,'precio_texto':precio_texto, 'doc_indentificacion':doc_indentificacion, "dia_pago":dia_pago, 'giro_comercial':giro_comercial, 'vig':vig, 'mobiliario':mobiliario, "campos_mobiliario":campos_mobiliario}

    return render(request, "home/contrato.html", context)

def contrato_pdf(request):
    info = Paquetes.objects.all().first()
    meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
   
    #estabelcemos la fecha de inicio 
    fecha_inicio = info.datos_arrendamiento['fecha_inicio_contrato']
    print("SOY EL FORMATO DE FECHA inicio",fecha_inicio)
    fecha_inicio_datetime = datetime.strptime(fecha_inicio, '%Y-%m-%d')
    dia = fecha_inicio_datetime.day
    mes = fecha_inicio_datetime.month
    mes_inicio = meses[mes]
    anio = fecha_inicio_datetime.year
    datos_inicio = {'dia':dia, 'anio':anio ,'mes':mes_inicio}
    
    #estabelcemos la fecha de fin
    fecha_fin = info.datos_arrendamiento['fecha_fin_contrato']
    fecha_fin_datetime = datetime.strptime(fecha_fin, '%Y-%m-%d')
    dia_fin = fecha_fin_datetime.day
    mes2 = fecha_fin_datetime.month
    mes_fin = meses[mes2]
    anio_fin = fecha_fin_datetime.year
    datos_fin = {'dia':dia_fin, 'anio':anio_fin ,'mes':mes_fin}
    
    #estabelcemos la fecha de fin
    fecha_firma = info.datos_arrendamiento['fecha_firma']
    fecha_firma_datetime = datetime.strptime(fecha_firma, '%Y-%m-%d')
    dia_firma = fecha_firma_datetime.day
    mes3 = fecha_firma_datetime.month
    mes_firma = meses[mes3]
    anio_firma = fecha_firma_datetime.year
    datos_firma = {'dia':dia_firma, 'anio':anio_firma ,'mes':mes_firma}
        
    datos = info.inmueble
    print(datos.__dict__)
    print(info.fiador.__dict__)
    #obtenermos la renta para pasarla a letra
    number = datos.renta
    number = int(number)
    text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    text_representation = text_representation.capitalize()
    #obtenermos el precio de la poliza para pasarla a letra
    precio = info.cotizacion.monto
    precio = int(precio)
    print(precio)
    precio_texto = num2words(precio, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    precio_texto = precio_texto.capitalize()
    
    #Comprobacion de mobiliario
    mobiliario = InmueblesInmobiliario.objects.all().filter(inmuebles = info.inmueble.id)
    print("soy mobiliario",mobiliario)
    
    # obtenemos la fecha de pago y extraemos el dia
    dia_pago = datetime.strptime(info.datos_arrendamiento['fecha_de_pago'], '%Y-%m-%d')
    dia_pago = dia_pago.day
    print(dia_pago)
 
    #variables de informacion arrendador
    tipo_documento_arrendador = info.ides['ides_arrendador']
    no_doc_arrendador = info.ides['no_ide_arrendador']
    
    #variables de informacion arrendatario
    tipo_documento_arrendatario = info.ides['ides_arrendatario']
    no_doc_arrendatario = info.ides['no_ide_arrendatario']
    
    #variables de informacion fiador
    tipo_documento_fiador = info.ides['ides_fiador']
    no_doc_fiador = info.ides['no_ide_fiador']
    doc_indentificacion = {'tipo_documento_arrendador':tipo_documento_arrendador, 'no_doc_arrendador':no_doc_arrendador,
                           'tipo_documento_arrendatario':tipo_documento_arrendatario, 'no_doc_arrendatario':no_doc_arrendatario,
                           'tipo_documento_fiador':tipo_documento_fiador, 'no_doc_fiador':no_doc_fiador}
   
    #variables que selecciona el inquilino        
    #plazos
    vig_c3 = "103" #tiene que ser de 15 o 30
    vig_c15 = "115" #tiene que ser de 30 con inclementos de 5 en 5 hasta 60
    vig_c23 = "123" # tiene que ser 15, 30 o 60
    vig_c25 = "125" #tiene que ser de 30 con inclementos de 5 en 5 hasta 60
    vig = {'vig_c3':vig_c3, 'vig_c15':vig_c15, 'vig_c23':vig_c23, 'vig_c25':vig_c25}
    
    #//////////////////////////////////////////////////////////////hasta aqui
    
    context = {'info': info, 'datos_inicio':datos_inicio, 'datos_fin':datos_fin,'datos_firma':datos_firma, 'text_representation':text_representation,'precio_texto':precio_texto, 'doc_indentificacion':doc_indentificacion, "dia_pago":dia_pago, 'vig':vig, 'mobiliario':mobiliario}
    
    template = 'home/contrato.html'
    html_string = render_to_string(template, context)

    # Genera el PDF utilizando weasyprint
    pdf_file = HTML(string=html_string).write_pdf()

    # Devuelve el PDF como respuesta
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
    response.write(pdf_file)

    return HttpResponse(response, content_type='application/pdf')

def contrato_fraterna_pdf(request):
    info = FraternaContratos.objects.all().first()
    print(info.__dict__)
    meses={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
    
    #obtenermos la renta para pasarla a letra
    habitantes = int(info.habitantes)
    habitantes_texto = num2words(habitantes, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    #obtenemos renta y costo poliza para letra
    renta = int(info.renta)
    renta_texto = num2words(renta, lang='es').capitalize()
    #obtener la tipologia
    # Definir las opciones y sus correspondientes valores para la variable "plano"
    opciones = {
        'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
        'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
        'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
        'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
        'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
        'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
        'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png"
    }
    tipologia = info.tipologia
    if tipologia in opciones:
        plano = opciones[tipologia]
        print(f"Tu Tipologia es: {tipologia}, URL: {plano}")
    #obtener la url de el plano que sube fraterna
    plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
   
    
 
    context = {'info': info, 'habitantes_texto':habitantes_texto, 'renta_texto':renta_texto, 'plano':plano, 'plan_loc':plan_loc}
    template = 'home/contrato_fraterna.html'
    html_string = render_to_string(template,context)

    # Genera el PDF utilizando weasyprint
    pdf_file = HTML(string=html_string).write_pdf()

    # Devuelve el PDF como respuesta
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
    response.write(pdf_file)

    return HttpResponse(response, content_type='application/pdf')

def generar_pdf_aprobado(request):
       # Renderiza el template HTML
        today = date.today().strftime('%d/%m/%Y')
        info = Investigacion.objects.all().first()
        avales = info.inquilino.aval.all().first()
        inquilinos = info.inquilino
        print("yo soy info de los inquilinos",info.__dict__)
        print("yo soy info de los avales",avales.__dict__)        
        
        ingreso = "Recibo de nómina"
      
        
        if avales.recibos == "Si":
            ingreso_obligado = "Recibo de nómina"   
        else:
            ingreso_obligado = "Estado de cuenta" 
        
        number = info.inquilino.ingreso_men
        number = int(number)
        
        number_2 = avales.ingreso_men_fiador
        number_2 = int(number)
        
        text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
        text_representation = text_representation.capitalize()
       
        text_representation2 = num2words(number_2, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
        text_representation2 = text_representation2.capitalize()
        
        context = {
        'info':info,
        'fiador':avales,
        'fecha_actual':today,
        'number': number,
        'number_2': number_2,
        'text_representation': text_representation,
        'text_representation2': text_representation2,
        'ingreso':ingreso,
        'ingreso_obligado':ingreso_obligado,
    }
        template = 'home/aprobado_fiador.html'
        html_string = render_to_string(template, context)

        # Genera el PDF utilizando weasyprint
        pdf_file = HTML(string=html_string).write_pdf()

        # Devuelve el PDF como respuesta
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="mi_pdf.pdf"'
        response.write(pdf_file)

        return response
    
class generar_pdf_prueba(View):
    def get(self,request,*args, **kwargs):
        info = Cotizacion.objects.all().first()
        data = {"info": info}
        pdf = render_to_pdf('home/acp.html',data)
        return HttpResponse(pdf, content_type='application/pdf')

def correo(request):
    #podemos usar lo modelos de la conexion a la base de datos para mostrarlos desde una variable con f string
    info = Cotizacion.objects.all().first()
    datos = info.__dict__
    print(datos)
    print(info.nombre_cotizacion)
    return render(request, "home/prueba.html", context={"info": info})
    
def generar_pdf(request):
    # Renderiza el template HTML
    info = Cotizacion.objects.all().first()
    context = {"info": info}  # Ejemplo de contexto de datos
    temp = get_template("home/acp.html")
    #template = 'home/acp.html'
    #html_string = render_to_string(temp, context)
    html_template = temp.render(context)
    HTML(string=html_template).write_pdf(target="prueba.pdf")
    print("pdf realizado")
    # Genera el PDF utilizando weasyprint
    #pdf_file = HTML(string=html_string).write_pdf()
    # Devuelve el PDF como respuesta
    
    # response = HttpResponse(content_type='application/pdf')
    # response['Content-Disposition'] = 'attachment; filename="mi_pdf.pdf"'
    #response.write(pdf_file)
    print("terminado")
    return HttpResponse({'msj':"Se logro"})

def pdf_descarga(request):
    # Renderiza el template HTML
    info = Cotizacion.objects.all().first()
    context = {"info": info}  # Ejemplo de contexto de datos
    template = 'home/acp.html'
    html_string = render_to_string(template, context)

    # Genera el PDF utilizando weasyprint
    pdf_file = HTML(string=html_string).write_pdf()

    # Devuelve el PDF como respuesta
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="mi_pdf.pdf"'
    response.write(pdf_file)

    return response

def pagare_fraterna(request):
    #activamos la libreri de locale para obtener el mes en español
    locale.setlocale(locale.LC_ALL,"es-ES")
    info = FraternaContratos.objects.all().first()
    print(info.__dict__)
    # Definir la fecha inicial
    fecha_inicial = info.fecha_move_in
    print(fecha_inicial)
    #fecha_inicial = datetime(2024, 3, 20)
    #checar si cambiar el primer dia o algo asi
    # fecha inicial move in
    dia = fecha_inicial.day
    
    # Definir la duración en meses
    duracion_meses = info.duracion.split()
    duracion_meses = int(duracion_meses[0])
    print("duracion en meses",duracion_meses)
    # Calcular la fecha final
    fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
    # Lista para almacenar las fechas iteradas (solo meses y años)
    fechas_iteradas = []
    # Iterar sobre todos los meses entre la fecha inicial y la fecha final
    while fecha_inicial < fecha_final:
        nombre_mes = fecha_inicial.strftime("%B")  # %B da el nombre completo del mes
        print("fecha",fecha_inicial.year)
        fechas_iteradas.append((nombre_mes.capitalize(),fecha_inicial.year))      
        fecha_inicial += relativedelta(months=1)
    
    print("fechas_iteradas",fechas_iteradas)
    # Imprimir la lista de fechas iteradas
    for month, year in fechas_iteradas:
        print(f"Año: {year}, Mes: {month}")
     
    #obtenermos la renta para pasarla a letra
    number = info.renta
    number = int(number)
    text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    text_representation = text_representation.capitalize()
    
    context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses}
  
    return render(request, "home/pagare_fraterna.html", context)

def pagare_fraterna_pdf(request):
    #activamos la libreri de locale para obtener el mes en español
    locale.setlocale(locale.LC_ALL,"es-ES")
    info = FraternaContratos.objects.all().first()
    print(info.__dict__)
    # Definir la fecha inicial
    fecha_inicial = info.fecha_move_in
    print(fecha_inicial)
    #fecha_inicial = datetime(2024, 3, 20)
    #checar si cambiar el primer dia o algo asi
    # fecha inicial move in
    dia = fecha_inicial.day
    
    # Definir la duración en meses
    duracion_meses = info.duracion.split()
    duracion_meses = int(duracion_meses[0])
    print("duracion en meses",duracion_meses)
    # Calcular la fecha final
    fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
    # Lista para almacenar las fechas iteradas (solo meses y años)
    fechas_iteradas = []
    # Iterar sobre todos los meses entre la fecha inicial y la fecha final
    while fecha_inicial < fecha_final:
        nombre_mes = fecha_inicial.strftime("%B")  # %B da el nombre completo del mes
        print("fecha",fecha_inicial.year)
        fechas_iteradas.append((nombre_mes.capitalize(),fecha_inicial.year))      
        fecha_inicial += relativedelta(months=1)
    
    print("fechas_iteradas",fechas_iteradas)
    # Imprimir la lista de fechas iteradas
    for month, year in fechas_iteradas:
        print(f"Año: {year}, Mes: {month}")
     
    #obtenermos la renta para pasarla a letra
    number = info.renta
    number = int(number)
    text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    text_representation = text_representation.capitalize()
    
    context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses}
    
    template = 'home/pagare_fraterna.html'
    html_string = render_to_string(template, context)

    # Genera el PDF utilizando weasyprint
    pdf_file = HTML(string=html_string).write_pdf()

    # Devuelve el PDF como respuesta
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
    response.write(pdf_file)

    return HttpResponse(response, content_type='application/pdf')

def nuevo_resultado(request):
    #activamos la libreri de locale para obtener el mes en español
    info = FraternaContratos.objects.all().first()
    print(info.__dict__)
    # Definir la fecha inicial
    today = date.today().strftime('%d/%m/%Y')
    
    # Definir la duración en meses
    duracion_meses = info.duracion.split()
    duracion_meses = int(duracion_meses[0])
    print("duracion en meses",duracion_meses)
    
     
    #obtenermos la renta para pasarla a letra
    number = info.renta
    number = int(number)
    text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
    text_representation = text_representation.capitalize()
    x = "Si"
    y = "No"
    context = {'info': info, "fecha_consulta":today, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'x':x, 'y':y}
    
    #template = 'home/resultado_investigacion_new.html'
    template = 'home/report.html'
    html_string = render_to_string(template, context)

    # Genera el PDF utilizando weasyprint
    pdf_file = HTML(string=html_string).write_pdf()

    # Devuelve el PDF como respuesta
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
    response.write(pdf_file)

    return HttpResponse(response, content_type='application/pdf')
    return render(request, "home/report.html", context)


def index(request):
    context = {'segment': 'index'}
    html_template = loader.get_template('home/page-404.html')
    return HttpResponse(html_template.render(context, request))


@login_required(login_url="/login/")
def subirArch(request):
    if request.method == "POST":
        # Fetching the form data
        ine = request.FILES["ine"]
        user = request.user
        comp_dom = request.FILES["comp_dom"]
        rfc = request.FILES["rfc"]

        # Saving the information in the database
        document = DocumentosInquilino(
            Ine=ine,
            Comp_dom=comp_dom,
            Rfc=rfc,
            user=user,
        )
        document.save()
        print(f'Archivo subido correctamente')

    documents = DocumentosInquilino.objects.all().filter(user_id=request.user)

    return render(request, "home/archivos.html", context={"files": documents})


# MODULO Inquilino #________________________________
def reg_inq(request):
    if request.method == 'POST':
        form_inq = InquilinosForm(request.POST or None)
        if form_inq.is_valid():
            print("Es valido continuar")
            form_inq = form_inq.save(commit=False)
            form_inq.user = request.user
            print(form_inq.user)
            # user = form_inq.save()
            print(form_inq)
            form_inq.save()
            sleep(3)
            print("GUARDADO CON EXITO")
            # print(user)
            return redirect('/inquilinos/')
        else:
            print("No valido")
            print(form_inq.errors)
            form_inq = InquilinosForm()
    return render(request, 'home/inquilinos.html', {'form_inq': form_inq})


def inquilinos(request):
    if request.user.is_authenticated:
        inquilinos = Inquilino.objects.all().filter(user_id=request.user)
        print(inquilinos)
        return render(request, 'home/inquilinos.html', {'inquilinos': inquilinos})
    else:
        return render(request, 'home/page-403.html')


def ver_inquilino(request, id):
    inquilino = Inquilino.objects.get(id=id)
    # personas_f=get_object_or_404(p_fisica, pk=id)
    if inquilino.user == request.user:
        print(inquilino)
        return render(request, 'home/detalles-inquilino.html', {'inquilino': inquilino})
    else:
        return render(request, 'home/page-500.html')


def editar_inq(request, id):
    # fetch the object related to passed id
    inquilinos = Inquilino.objects.all().filter(user_id=request.user)
    print(inquilinos)
    inquilino = Inquilino.objects.get(id=id)
    if inquilino.user == request.user:
        form_inq = InquilinosForm(request.POST or None, instance=inquilino)
        if form_inq.is_valid():
            form_inq = form_inq.save(commit=False)
            print(form_inq)
            form_inq.user = request.user
            print(form_inq.user)
            # user = form_inq.save()
            # obter el valor de cualquir campo en el template
            # print(request.POST['tel_empleo'])
            form_inq.save()
            sleep(3)
            print("ACTUALIZADO CON EXITO")
            # print(user)
            return redirect('/inquilinos/')
        else:
            print(" No valido")
            print(form_inq.errors)

        context = {'inquilino': inquilino, 'inquilinos': inquilinos}
        return render(request, "home/edit_inq.html", context)
    else:
        return render(request, 'home/page-500.html')


def eliminar_inq(request, id):
    inquilino = Inquilino.objects.get(id=id)
    inquilino.delete()

    return redirect('/inquilinos/')
# MODULO Fiador  #________________________________
def reg_fiador(request):
    form_fiador = FiadorForm()
 
    base = Inquilino.objects.all().filter(user_id = request.user)
    #base = Fiador_obligado.objects.all()
    print(base)
    if request.method == 'POST':
        form_fiador = FiadorForm(request.POST or None)
        if form_fiador.is_valid():
            print("Es valido continuar")
            form_fiador = form_fiador.save(commit=False)
            form_fiador.user = request.user
          
            print(form_fiador.user)
            print(form_fiador)
            form_fiador.save()
            sleep(3)
            print("GUARDADO CON EXITO")
            # print(user)
            return redirect('/fiador')
        else:
            print("No valido")
            print(form_fiador.errors)
            form_fiador = InquilinosForm()
    return render(request, 'home/MSFO.html', {'form_fiador': form_fiador, 'base': base})



# MODULO Arrendador  #________________________________
# def arrendadores(request):
#     if request.user.is_authenticated:
#         arrendadores = Arrendador.objects.all().filter(user_id=request.user)
#         print(arrendadores)
#         return render(request, 'home/arrendador.html', {'arrendadores': arrendadores})
#     else:
#         return render(request, 'home/page-403.html')


# def reg_arr(request):
#     if request.method == 'POST':
#         form_arr = ArrendadorForm(request.POST or None)
#         if form_arr.is_valid():
#             print("Es valido continuar")
#             form_arr = form_arr.save(commit=False)
#             form_arr.user = request.user
#             print(form_arr.user)
#             # user = form_arr.save()
#             print(form_arr)
#             form_arr.save()
#             sleep(3)
#             print("GUARDADO CON EXITO")
#             # print(user)
#             return redirect('/arrendadores/')
#         else:
#             print("No valido")
#             print(form_arr.errors)
#             form_arr = ArrendadorForm()
#     return render(request, 'home/arrendador.html', {'form_arr': form_arr})


# def ver_arrendador(request, id):
#     arrendador = Arrendador.objects.get(id=id)
#     # personas_f=get_object_or_404(p_fisica, pk=id)
#     if arrendador.user == request.user:
#         print(arrendador)
#         return render(request, 'home/detalles-arrendador.html', {'arrendador': arrendador})
#     else:
#         return render(request, 'home/page-403.html')


# def editar_arr(request, id):
#     # fetch the object related to passed id
#     arrendadores = Arrendador.objects.all().filter(user_id=request.user)
#     print(arrendadores)
#     arrendador = Arrendador.objects.get(id=id)
#     if arrendador.user == request.user:
#         form_arr = ArrendadorForm(request.POST or None, instance=arrendador)
#         if form_arr.is_valid():
#             form_arr = form_arr.save(commit=False)
#             print(form_arr)
#             form_arr.user = request.user
#             print(form_arr.user)
#             # user = form_inq.save()
#             # obter el valor de cualquir campo en el template
#             # print(request.POST['tel_empleo'])
#             form_arr.save()
#             sleep(3)
#             print("ACTUALIZADO CON EXITO")
#             # print(user)
#             return redirect('/arrendadores/')
#         else:
#             print(" No valido")
#             print(form_arr.errors)

#         context = {'arrendador': arrendador, 'arrendadores': arrendadores}
#         return render(request, "home/edit_arr.html", context)
#     else:
#         return render(request, 'home/page-500.html')


# def eliminar_arr(request, id):
#     arrendador = Arrendador.objects.get(id=id)
#     arrendador.delete()

#     return redirect('/arrendadores/')


# Modulo Inmuebles#________________________________
def reg_inmueble(request):
    user = request.user
    inmuebles = Inmuebles.objects.filter(user=request.user, alias_inmueble=request.POST['alias_inmueble'])
    print("query de inmuebles",inmuebles)
    print(inmuebles.first())
    print("soy request de alias",request.POST['alias_inmueble'])
   
    if inmuebles:
        print("NO carnal, ese Alias de inmueble ya inmueble ya existe")
        alias_inmueble = request.POST['alias_inmueble'] + "" + str(inmuebles.count())
        print("nuevo nombre",alias_inmueble)
         
    if request.method == 'POST':
        form = InmueblesForm(request.POST)
        fotos_form = ImagenInmuelbeForm(request.POST, request.FILES)
        images = request.FILES.getlist('imagenes')  # field name in model
        img = len(images)
        print(img)
        if img <= 5:
            if form.is_valid() and fotos_form.is_valid():
                print("valido")
                inmueble_instance = form.save(commit=False)
                inmueble_instance.user = user
                if inmuebles:
                    inmueble_instance.alias_inmueble = alias_inmueble
                inmueble_instance.save()
                for f in images:
                    foto_instance = ImagenInmueble(imagenes=f, inmueble=inmueble_instance)
                    print(foto_instance)
                    foto_instance.user = user
                    foto_instance.save()
                sleep(1)
                return redirect('/inmuebles/')
            else:
                print("No valido")
                print(form.errors)
                form = InquilinosForm()
                fotos_form = ImagenInmuelbeForm()
        else:
            return render(request, 'home/page-007.html')

    return render(request, 'home/page-007.html', {'form': form, 'fotos_form': fotos_form})


def listarInmueble(request):
    inmuebles = Inmuebles.objects.all().filter(user_id=request.user)
    print(inmuebles)
    lookup_field = 'slug'
    # registros = request.POST.get('no_registros',5)
    records_per_page = request.GET.get('records_per_page', 5)
    records_per_page = int(records_per_page)
    page = request.GET.get('page', 1)

    print("registros", records_per_page)
    print("page", page)
    try:
        # paginator = Paginator(inmuebles, registros) # Show 25 contacts per page.
        paginator = Paginator(inmuebles, records_per_page)
        page_obj = paginator.get_page(page)
        print("yo soy page obj", page_obj)

    except:
        raise Http404
    return render(request, 'home/inmuebles.html',
                  {'page_obj': page_obj, 'records_per_page': records_per_page, 'paginator': paginator})


def verInmueble(request, slug):
    verinmueble = Inmuebles.objects.filter(user_id=request.user).get(slug=slug)
    print(verinmueble)
    print("yo soy", verinmueble.id)
    return render(request, 'home/detalles-inmueble.html', {'verinmueble': verinmueble})


def editarInmueble(request, slug):
    # consulta slug
    print("Esta en editar")
    verinmueble = Inmuebles.objects.filter(user_id=request.user).get(slug=slug)
    # asignar id desde la consulta slug
    id = verinmueble.id
    # consulta tabla
    inmuebles = Inmuebles.objects.all().filter(user_id=request.user)
    # consulta objeto a editar
    objin = Inmuebles.objects.get(id=id)
    print("Paso a 5")
    imagen = get_object_or_404(ImagenInmueble, pk=11)
    print("Paso a 6")
    fotos_old = ImagenInmueble.objects.all().filter(inmueble_id=11)
    print("Paso a 7")
    # print(fotos_old.__getitem__(4).imagenes)
    print("contador de fotos old", fotos_old.count())
    print("imagen imagenes", imagen.imagenes)
    
    if request.method == 'POST':
        form = InmueblesForm(request.POST or None, instance=objin)
        fotos_form = ImagenInmuelbeForm(request.POST, request.FILES, instance=imagen)

        if fotos_old.count() <= 5:
            if form.is_valid() and fotos_form.is_valid():
                print("valido")
                inmueble_instance = form.save(commit=False)
                inmueble_instance.user = request.user
                inmueble_instance.save()
                ids_eliminar = request.POST.getlist('eliminar[]')
                print("ids a eliminar", ids_eliminar)
                imagenes_eliminar = ImagenInmueble.objects.filter(id__in=ids_eliminar)
                print("imagenes a eliminar", imagenes_eliminar)
                if imagenes_eliminar != 0:
                    for imagen in imagenes_eliminar:
                        imagen.delete()
                        os.remove(imagen.imagenes.path)
                        print("se elimino correctamente la imagen", imagen)

                images = request.FILES.getlist('imagenes')  # field name in model
                img = len(images)
                print("imagens a cargar:", img)
                contador = fotos_old.count()
                print("contadador 2: =", contador)
                contador2 = 5 - contador
                if contador != 5 or contador2 != 0:
                    if img <= contador2:
                        for f in images:
                            foto_instance = ImagenInmueble(imagenes=f, inmueble=inmueble_instance)
                            print(foto_instance)
                            foto_instance.user = request.user
                            foto_instance.save()

                    else:
                        return render(request, 'home/page-007.html')
                sleep(2)
                return redirect('/inmuebles/')
            else:
                print("No valido")
                print(form.errors)
                form = InquilinosForm()
                fotos_form = ImagenInmuelbeForm()
        else:
            messages.error(request, 'Se ha producido un error. Por favor solo subir 5 Fotos como MAXIMO ')

    context = {'objin': objin, 'inmuebles': inmuebles, 'verinmueble': verinmueble}

    return render(request, "home/edit_inmueble.html", context)


def removerInmueble(request, id):
    objin = Inmuebles.objects.get(id=id)
    objin.delete()

    return HttpResponseRedirect(reverse('listarInmueble'))



def pages(request):
    context = {}
    # All resource paths end in .html.
    # Pick out the html file name from the url. And load that template.
    try:

        load_template = request.path.split('/')[-1]
        if load_template == 'admin':
            return HttpResponseRedirect(reverse('admin:index'))
        context['segment'] = load_template

        html_template = loader.get_template('home/' + load_template)
        return HttpResponse(html_template.render(context, request))

    except template.TemplateDoesNotExist:

        html_template = loader.get_template('home/page-404.html')
        return HttpResponse(html_template.render(context, request))

    except:
        html_template = loader.get_template('home/page-500.html')
        return HttpResponse(html_template.render(context, request))
