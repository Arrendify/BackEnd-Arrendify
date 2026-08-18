from rest_framework import viewsets
from rest_framework.response import Response
from ...home.models import *
from ...home.models import DocumentosArrendamientosFraterna as DocumentosArrendamientosFraternaModel
from ...home.models import IncidenciasFraterna as IncidenciasFraternaModel
from ..serializers import *
from rest_framework import status
from ...accounts.models import CustomUser
User = CustomUser
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponse, HttpResponseRedirect
from django.forms.models import model_to_dict

#s3
import boto3
from botocore.exceptions import ClientError
from botocore.exceptions import NoCredentialsError
from django.db.models import Q, Func, Max, Count, Prefetch, Subquery, OuterRef, F
from django.db.models.functions import TruncMonth, Coalesce
from django.db import transaction
from django.core.exceptions import ValidationError
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, API_TOKEN_ZAPSIGN, API_URL_ZAPSIGN
from django.conf import settings
#weasyprint
from weasyprint import HTML, CSS
from django.template.loader import render_to_string
from django.template.loader import get_template
#Legal
from num2words import num2words
from datetime import date
from datetime import datetime
from calendar import monthrange
from django.utils import timezone
from django.utils.dateparse import parse_date

#Libreria para obtener el lenguaje en español
import locale

import re
import unicodedata
#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)

# Modo demostraciones (rol="Demo"): marca blanca en PDFs y firmas redirigidas.
# Desde 2026-07-22 (decisión del usuario) la cuenta demo ve y edita todo; el
# candado solo-propios aplica únicamente a firmas/renovación/borrado.
# Ver apps/api/utils/demo_mode.py
from ..utils.demo_mode import (
    es_usuario_demo,
    marca_para,
    contrato_es_del_usuario,
    aplicar_demo_a_payload_zapsign,
)

# Candado por equipo interno (accounts_customuser.rol_interno, solo-BD):
# aprobar/desaprobar, editar contratos aprobados y emitir firmas sin estatus
# Aprobado son exclusivos del equipo Arrendify. Ver utils/roles_internos.py
from ..utils.roles_internos import es_operador_arrendify, puede_ver_credenciales_residente

# Portal del residente (2026-08-13): alta de cuentas de login ligadas al registro
# de residentes (hasta 2: arrendatario y residente). Ver utils/acceso_residente.py
from ..utils import acceso_residente

# Bandeja de recibos (2026-08-18): el calendario de mensualidades se calcula al
# vuelo desde la ronda FIRMADA, con la misma regla que imprime los pagares. El
# revisor lo necesita para saber cuanto se esperaba de ese mes. El import al
# reves (calendario_pagos -> fraterna_views) va DIFERIDO dentro de la funcion,
# asi que esto no hace ciclo.
from ..utils.calendario_pagos import estado_de_cuenta, tramos

# Tope de filas que devuelve la bandeja de recibos en una pasada. Hoy sobra
# (255 vigentes x 12 meses es el techo de un ano entero y la cola real es de
# decenas), pero se declara en la respuesta ("truncado") en vez de cortar en
# silencio: una lista cortada se lee como "ya no hay mas".
TOPE_BANDEJA_RECIBOS = 400


class Unaccent(Func):
    """Aplica unaccent() de Postgres sobre un campo, para busquedas insensibles a acentos.
    Requiere la extension 'unaccent' (ya instalada en local y prod)."""
    function = 'unaccent'
    arity = 1


def _sin_acentos(texto):
    """Quita diacriticos del lado Python para normalizar el termino de busqueda igual
    que unaccent() normaliza la columna en SQL (asi 'jesus' == 'Jesús', 'garcia' == 'García')."""
    if not texto:
        return texto
    return ''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c))


# Nombres de mes 1-based (indice = numero de mes), para las etiquetas del filtro
# "Contrato firmado en <mes>". No usamos locale: en Windows/Linux el nombre de la
# locale española difiere y setlocale() es global al proceso (pisa otros hilos).
MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

# Que cuenta como contrato firmado al filtrar por mes: la ronda llego a firmarse.
# 'firmado' = termino EN PIE; 'expirado' = termino que ya cumplio y fue reemplazado
# por una renovacion (sigue siendo un contrato que se firmo ese mes, por eso entra).
# 'pendiente' (enlaces vivos sin cerrar) y 'cancelado' (intento desechado) NO.
ESTADOS_RONDA_FIRMADA = ('firmado', 'expirado')


def _rondas_con_fecha_de_firma():
    """Rondas ya firmadas, anotadas con `firmado_el` = cuando quedo firmado el
    contrato.

    NO hay un solo campo con esa fecha: el `signed_at` literal que manda ZapSign
    lo guarda el webhook por FIRMANTE (`fraterna_ronda_firmante.firmado_en`, ver
    zapsign_webhook._sync_firmantes), asi que la fecha de la RONDA es la de su
    ULTIMA firma — el momento en que ya firmaron todas las partes.

    Respaldo `cerrado_en` (cuando nuestro webhook cerro la ronda) para rondas sin
    ninguna fecha de firmante. Hoy las 330 rondas firmadas/expiradas tienen al
    menos un firmante fechado, pero el respaldo evita que un caso raro se caiga
    del filtro; `cerrado_en` acierta el mes en 323 de esas 330 (98%).

    Es Subquery en vez de Max(): una agregacion aqui chocaria con el Count() del
    conteo por mes (agregacion anidada), y asi `firmado_el` es una expresion
    normal, filtrable y agrupable como cualquier columna.
    """
    ultima_firma = Subquery(
        FraternaRondaFirmante.objects
        .filter(ronda_id=OuterRef('pk'), firmado_en__isnull=False)
        .order_by('-firmado_en')
        .values('firmado_en')[:1]
    )
    return (FraternaRondaFirma.objects
            .filter(estado__in=ESTADOS_RONDA_FIRMADA)
            .annotate(firmado_el=Coalesce(ultima_firma, F('cerrado_en'))))


def _parsear_anio(valor):
    """'2026' -> 2026 validado. None si no es un año plausible."""
    try:
        anio_i = int(str(valor or '').strip())
    except (ValueError, TypeError):
        return None
    return anio_i if 2000 <= anio_i <= 2100 else None


def _parsear_mes(valor):
    """'8' / '08' -> 8 validado (1-12). None si no es un mes real.

    Acepta tambien 'YYYY-MM' y se queda con el mes, porque el FE que ya esta en
    produccion manda `firmado_mes=2026-08` (formato de un solo select). Ver
    `_parsear_mes_anio` para el par completo.
    """
    texto = str(valor or '').strip()
    if '-' in texto:
        texto = texto.split('-')[-1]
    try:
        mes_i = int(texto)
    except (ValueError, TypeError):
        return None
    return mes_i if 1 <= mes_i <= 12 else None


def _parsear_mes_anio(valor):
    """'YYYY-MM' -> (anio, mes) validado. None si no es un mes real.

    Formato del FE VIEJO (un solo select), que se sigue aceptando para que un
    deploy a medias — FE viejo contra BE nuevo — no rompa el filtro.
    """
    try:
        partes = (valor or '').split('-')
        anio_i, mes_i = int(partes[0]), int(partes[1])
    except (ValueError, IndexError, TypeError):
        return None
    if 1 <= mes_i <= 12 and 2000 <= anio_i <= 2100:
        return anio_i, mes_i
    return None


def _etiqueta_mes(fecha):
    """date/datetime -> 'Agosto 2026' (etiqueta larga, selector de un solo campo)."""
    return f"{MESES_ES[fecha.month]} {fecha.year}"


def _agrupar_meses(rondas_qs, campo):
    """Agrupa un queryset de rondas por mes de `campo` -> opciones del select de
    periodo del FE: [{'mes': 'YYYY-MM', 'etiqueta': 'Agosto 2026', 'n': contratos}].

    `n` cuenta CONTRATOS distintos (no rondas) para que el numero del selector
    cuadre con las filas que el filtro va a listar. Rondas con el campo NULL se
    quedan fuera (sin fecha no hay mes que ofrecer)."""
    filas = (rondas_qs
             .filter(**{f'{campo}__isnull': False})
             .annotate(_mes=TruncMonth(campo))
             .values('_mes')
             .annotate(n=Count('contrato_id', distinct=True))
             .order_by('-_mes'))
    return [{'mes': fila['_mes'].strftime('%Y-%m'),
             'etiqueta': _etiqueta_mes(fila['_mes']),
             'n': fila['n']}
            for fila in filas if fila['_mes']]


# Criterios del filtro especial de fechas que operan sobre la ronda VIGENTE
# (estado='firmado', el termino en pie) cruzada con el rail del contrato:
#   clave -> (estado_contrato requerido, campo de fecha de la ronda)
# 'inicia'    = vigentes cuyo termino en pie ARRANCA en el periodo
# 'termina'   = vigentes cuyo termino en pie VENCE en el periodo (mirada a futuro)
# 'terminado' = expirados cuyo termino en pie vencio en el periodo
# ('firmado' no esta aqui: usa la fecha REAL de firma, ver _rondas_con_fecha_de_firma)
CRITERIOS_RONDA_VIGENTE = {
    'inicia':    ('actual',   'fecha_celebracion'),
    'termina':   ('actual',   'fecha_vigencia'),
    'terminado': ('expirado', 'fecha_vigencia'),
}


def _ordinal_abreviado(n):
    """Ordinal corto en español: 6 -> '6to' (como el '6to (sexto)' de la cláusula Cuarta)."""
    if 11 <= (n % 100) <= 13:
        return f"{n}vo"
    sufijos = {1: 'er', 2: 'do', 3: 'er', 4: 'to', 5: 'to', 6: 'to', 7: 'mo', 8: 'vo', 9: 'no', 0: 'mo'}
    return f"{n}{sufijos[n % 10]}"


def _dia_pago_fraterna(info):
    """Día límite de pago de la renta (1-31). NULL/0 -> 5 (default histórico)."""
    return getattr(info, 'dia_pago', None) or 5


def _num_pagares_fraterna(info):
    """Pagarés que entrega el arrendatario: uno por mes de `duracion` (primer
    token: "12 Meses" -> 12); ilegible/vacío -> 1 (contratos de menos de un mes).
    Fuente ÚNICA para el generador de pagarés y la cláusula Vigésima Primera del
    contrato (antes esa cláusula imprimía el placeholder literal "***")."""
    try:
        meses = int(str(info.duracion).split()[0])
    except (ValueError, IndexError):
        meses = 0
    return meses if meses > 0 else 1


def _contraprestacion_fraterna_context(info):
    """Variables de la cláusula Cuarta (cuota de estacionamiento en letra, renta
    integral y día de pago N/N+1) y de la Vigésima Primera (número de pagarés)."""
    renta_num = int(float(info.renta))
    pe = info.precio_estacionamiento_mxn
    if pe is not None:
        precio_int = int(pe)
        precio_texto = num2words(precio_int, lang='es').capitalize()
    else:
        precio_int = None
        precio_texto = None
    renta_integral_val = renta_num + (precio_int if precio_int is not None else 0)
    renta_integral_texto = num2words(renta_integral_val, lang='es').capitalize()
    dia_pago = _dia_pago_fraterna(info)
    dia_moratorio = dia_pago + 1
    num_pagares = _num_pagares_fraterna(info)
    return {
        'precio_estacionamiento_entero': precio_int,
        'precio_estacionamiento_texto': precio_texto,
        'renta_integral': renta_integral_val,
        'renta_integral_texto': renta_integral_texto,
        'dia_pago_num': dia_pago,
        'dia_pago_texto': num2words(dia_pago, lang='es'),
        'dia_moratorio_abrev': _ordinal_abreviado(dia_moratorio),
        'dia_moratorio_texto': num2words(dia_moratorio, lang='es', to='ordinal'),
        'num_pagares': num_pagares,
        'num_pagares_texto': num2words(num_pagares, lang='es'),
    }


#variables para el correo
from ..variables import *

#enviar por correo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from smtplib import SMTPException
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from decouple import config

# Para combinación de PDFs
import base64, io, sys
import requests
from rest_framework.decorators import action
from collections import defaultdict

from pypdf import PdfReader, PdfWriter
from datetime import datetime as dt
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from dateutil.relativedelta import relativedelta

# ----------------------------------Metodos Extras----------------------------------------------- #
def eliminar_archivo_s3(file_name):
    s3 = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
             )
    print("soy el valor de s3",s3.__dict__)
   
    try:
        print("entre en el Try")
        s3.delete_object(Bucket="arrendifystorage", Key=f"static/{str(file_name)}")
        print("El archivo se eliminó correctamente de S3.")
    except NoCredentialsError:
        print("No se encontraron las credenciales de AWS.",{NoCredentialsError})

# Planos e inventario por tipologia, en S3. Fuera de la vista porque el portal
# del residente rinde el MISMO contrato para su vista previa: si el armado del
# contexto viviera dentro de generar_contrato, habria dos copias que podrian
# divergir y el residente acabaria viendo un documento distinto del que firma.
PLANOS_POR_TIPOLOGIA = {
    'Loft':   "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
    'Twin':   "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
    'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
    'Squad':  "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
    'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
    'Crew':   "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
    'Party':  "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png",
}

INVENTARIO_POR_TIPOLOGIA = {
    tipologia: url.replace('/Fraterna/', '/Fraterna/inventario/inventario_')
    for tipologia, url in PLANOS_POR_TIPOLOGIA.items()
}


def plantilla_contrato_fraterna():
    return ('home/contrato_fraterna_v2.html' if settings.USE_NEW_FRATERNA_CONTRACT
            else 'home/contrato_fraterna.html')


def contexto_contrato_fraterna(info, user):
    """Contexto de la plantilla del contrato Fraterna.

    Lo comparten `generar_contrato` (lo que se manda a firmar) y la vista previa
    del portal del residente, para que sean el mismo documento y no dos que se
    parecen.

    Ojo con `habitantes` y `renta`: son CharField y en prod hay filas con esos
    campos vacios (el alta no los exige). Un int('') revienta la generacion — el
    fallback deja el hueco en el documento en vez de tumbar la peticion, que es
    justo lo que necesita una vista previa.
    """
    try:
        habitantes_texto = num2words(int(info.habitantes), lang='es')
    except (TypeError, ValueError):
        habitantes_texto = ''
    try:
        renta_texto = num2words(int(float(info.renta)), lang='es').capitalize()
    except (TypeError, ValueError):
        renta_texto = ''

    tipologia = info.tipologia
    return {
        'info': info,
        'habitantes_texto': habitantes_texto,
        'renta_texto': renta_texto,
        'plano': PLANOS_POR_TIPOLOGIA.get(tipologia, ''),
        'tabla_inventario': INVENTARIO_POR_TIPOLOGIA.get(tipologia, ''),
        'plan_loc': f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}",
        **_contraprestacion_fraterna_context(info),
        **(marca_para(user) or {}),
    }


def plano_es_exclusivo(path, contrato_id=None):
    """True si ese plano es de UN solo contrato, o sea: si se puede borrar sin danar a nadie.

    Hay tres generaciones de paths conviviendo bajo `Fraterna/plano_localizacion/`:
      - historicos: `PLANOS_PISO_3-11.png` (el nombre crudo del archivo subido). Los
        contratos que subieron un archivo con el mismo nombre acabaron COMPARTIENDO el
        objeto (191 comparten ese). Borrarlos deja el anexo sin plano a todos los demas:
        asi se rompieron 236. Intocables: jamas se limpian.
      - intermedios: `<id>/<uuid8>_PLANO.png` (carpeta por contrato; vida corta, se
        reconocen por si algun upload alcanzo a caer ahi).
      - actuales: `<id>_plano_localizacion.png` / `nuevo_<uuid8>_plano_localizacion.png`
        (key fija por contrato, plana en el root; el alta aun no tiene id, de ahi el uuid).
    Un nombre historico no puede coincidir con los patrones nuevos: exigen id numerico o
    uuid pegados al token exacto `_plano_localizacion`.

    Ademas del patron se verifica contra la BD que NINGUNA otra fila apunte al mismo path:
    los flujos que clonan contratos (p.ej. renovaciones) copian el value del FileField tal
    cual, y ahi una key "exclusiva por construccion" queda compartida entre origen y copia.
    """
    prefijo = 'Fraterna/plano_localizacion/'
    if not path or not path.startswith(prefijo):
        return False
    resto = path[len(prefijo):]
    generacion_nueva = '/' in resto or re.match(r'^(\d+|nuevo_[0-9a-f]{8})_plano_localizacion[^/]*$', resto)
    if not generacion_nueva:
        return False
    otros = FraternaContratos.objects.filter(plano_localizacion=path)
    if contrato_id is not None:
        otros = otros.exclude(id=contrato_id)
    return not otros.exists()

# ----------------------------------Metodo para disparar notificaciones a varios destinos----------------------------------------------- #
def send_noti_varios(self, request, *args, **kwargs):
        print("entramos al metodo de notificaiones independientes")
        print("lo que llega es en self",self)
        print("lo que llega es en kwargs",kwargs["title"])
        print("lo que llega es en kwargs",kwargs['text'])
        print("lo que llega es en kwargs",kwargs['url'])
        print("request: ",request.data)
        print("")
        
        print("request verbo",kwargs["title"])
        try:
            print("entramos en el try")
            user_session = request.user
            print("el que envia usuario es: ", user_session)
            
            destinatarios = User.objects.all().filter(pertenece_a = 'Arrendify')
            
            print("actores:",destinatarios)
            
            data_noti = {'title':kwargs["title"], 'text':kwargs["text"], 'user':user_session.id, 'url':kwargs['url']}
            print("Post serializer a continuacion")
        
            for destiny in destinatarios:
                post_serializer = PostSerializer(data=data_noti) #Usa el serializer_class
                if post_serializer.is_valid(raise_exception=True):
                    print("hola")
                    print("destinyes",destiny)
                    datos = post_serializer.save(user = destiny)
                    print("Guardado residente")
                    print('datos',datos)
                else:
                    print("Error en validacion",post_serializer.errors)
            return Response({'Post': post_serializer.data}, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print("error",e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
# ----------------------------------Metodos Extras----------------------------------------------- #

########################## F R A T E R N A ######################################
class ResidenteViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Residentes.objects.all()
    serializer_class = ResidenteSerializers
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
                print("Esta entrando a listar Residentes")
                residentes =  Residentes.objects.all().order_by('-id')
                serializer = self.get_serializer(residentes, many=True)
                return Response(serializer.data, status= status.HTTP_200_OK)

           elif es_usuario_demo(user_session):
                # Demo: ve todos los residentes (la página se ve poblada);
                # el front le oculta la columna de celular y las acciones ajenas.
                residentes = Residentes.objects.all().order_by('-id')
                serializer = self.get_serializer(residentes, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)

           elif user_session.rol == "Inmobiliaria" or user_session.username == "ElbaJ":
                #tengo que busca a los inquilinos que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de Residentes propios y registrados por mis agentes
                inquilinos_a_cargo = Residentes.objects.filter(user_id__in = agentes)
                inquilinos_mios = Residentes.objects.filter(user_id = user_session)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
                mios = mios.order_by('-id')
               
                serializer = self.get_serializer(mios, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                
                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['inmobiliaria'] = True
                    
                return Response(serialized_data)      
            
           elif user_session.rol == "Agente":  
                print("soy Agente", user_session.first_name)
                #obtengo mis inquilinos
                residentes_ag = Residentes.objects.filter(user_id = user_session)
                residentes_ag = residentes_ag.order_by('-id')
                #tengo que obtener a mis inquilinos vinculados
              
                serializer = self.get_serializer(residentes_ag, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)
           else:
                print("Esta entrando a listar Residentes fil")
                fiadores_obligados =  Residentes.objects.all().filter(user_id = user_session)
                serializer = self.get_serializer(fiadores_obligados, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    @action(detail=False, methods=['get'], url_path='buscar')
    def buscar(self, request, *args, **kwargs):
        """Búsqueda paginada de residentes para el picker del modal de creación de contrato.
        ADITIVO: no altera list() (que sigue devolviendo el array completo para residentes.html).
        Respeta la MISMA visibilidad que list(): staff ve todo; el resto solo lo suyo / su inmobiliaria.
        Query params: q (texto), page (1..), page_size (1..50, def 10).
        """
        from django.core.paginator import Paginator
        try:
            user_session = request.user

            # Mismo gating de visibilidad que list()
            if user_session.is_staff:
                base_qs = Residentes.objects.all()
            elif es_usuario_demo(user_session):
                # Demo: el picker se ve poblado (el front oculta el contacto)
                base_qs = Residentes.objects.all()
            elif user_session.rol == "Inmobiliaria" or user_session.username == "ElbaJ":
                agentes = User.objects.filter(pertenece_a=user_session.name_inmobiliaria)
                base_qs = Residentes.objects.filter(Q(user_id__in=agentes) | Q(user_id=user_session))
            else:
                base_qs = Residentes.objects.filter(user_id=user_session)

            q = (request.query_params.get('q') or '').strip()
            if q:
                base_qs = base_qs.filter(
                    Q(nombre_residente__icontains=q) |
                    Q(nombre_arrendatario__icontains=q) |
                    Q(correo_residente__icontains=q) |
                    Q(correo_arrendatario__icontains=q) |
                    Q(celular_residente__icontains=q)
                )

            base_qs = base_qs.order_by('-id')

            try:
                page = int(request.query_params.get('page', 1))
            except (TypeError, ValueError):
                page = 1
            try:
                page_size = int(request.query_params.get('page_size', 10))
            except (TypeError, ValueError):
                page_size = 10
            page_size = max(1, min(page_size, 50))  # tope defensivo

            # Solo los campos que el picker muestra → payload ligero
            valores = base_qs.values(
                'id', 'nombre_residente', 'nombre_arrendatario',
                'correo_residente', 'celular_residente',
            )

            paginator = Paginator(valores, page_size)
            page_obj = paginator.get_page(page)  # get_page clampea páginas fuera de rango

            return Response({
                'results': list(page_obj.object_list),
                'count': paginator.count,
                'page': page_obj.number,
                'num_pages': paginator.num_pages,
                'page_size': page_size,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en buscar residentes (archivo {exc_tb.tb_frame.f_code.co_filename}, método {exc_tb.tb_frame.f_code.co_name}, línea {exc_tb.tb_lineno}): {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='tabla')
    def tabla(self, request, *args, **kwargs):
        """Endpoint DataTables server-side para la tabla de residentes (residentes.html).
        ADITIVO: NO altera list() (lo consumen contratos_edit + 3 arrendamientos_edit). Misma visibilidad.
        Params DataTables: draw, start, length, search[value], order[0][column], order[0][dir]."""
        from django.core.paginator import Paginator  # noqa: F401 (no usado; slicing manual)
        try:
            user_session = request.user

            # Mismo gating de visibilidad que list()
            if user_session.is_staff:
                base = Residentes.objects.all()
            elif es_usuario_demo(user_session):
                # Demo: la tabla de residentes se ve poblada (el front oculta
                # celular y limita acciones a los propios).
                base = Residentes.objects.all()
            elif user_session.rol == "Inmobiliaria" or user_session.username == "ElbaJ":
                agentes = User.objects.filter(pertenece_a=user_session.name_inmobiliaria)
                base = Residentes.objects.filter(Q(user_id__in=agentes) | Q(user_id=user_session))
            else:
                base = Residentes.objects.filter(user_id=user_session)

            records_total = base.count()
            qs = base

            # Busqueda global (DataTables search[value])
            search_value = (request.query_params.get('search[value]') or '').strip()
            if search_value:
                # Busqueda insensible a acentos en los nombres: unaccent() sobre la columna
                # + termino sin acentos. Asi "jesus" encuentra "Jesús", "garcia" -> "García".
                term_sa = _sin_acentos(search_value)
                qs = qs.annotate(
                    _na_ua=Unaccent('nombre_arrendatario'),
                    _nr_ua=Unaccent('nombre_residente'),
                )
                cond = (
                    Q(_nr_ua__icontains=term_sa) |
                    Q(_na_ua__icontains=term_sa) |
                    Q(correo_arrendatario__icontains=search_value) |
                    Q(correo_residente__icontains=search_value) |
                    Q(celular_arrendatario__icontains=search_value) |
                    Q(celular_residente__icontains=search_value)
                )
                if search_value.isdigit():
                    cond = cond | Q(id=int(search_value))
                qs = qs.filter(cond)

            records_filtered = qs.count()

            # Orden (solo columnas con campo en BD; el resto cae a id)
            col_map = {0: 'id', 2: 'nombre_arrendatario', 3: 'celular_arrendatario', 4: 'nombre_residente'}
            try:
                order_col = int(request.query_params.get('order[0][column]', 0))
            except (TypeError, ValueError):
                order_col = 0
            order_field = col_map.get(order_col, 'id')
            if request.query_params.get('order[0][dir]', 'desc') == 'desc':
                order_field = '-' + order_field
            qs = qs.order_by(order_field)

            # Paginacion por indices (start/length de DataTables)
            try:
                start = int(request.query_params.get('start', 0))
            except (TypeError, ValueError):
                start = 0
            try:
                length = int(request.query_params.get('length', 10))
            except (TypeError, ValueError):
                length = 10
            if length <= 0:
                length = 10
            length = min(length, 100)
            page_qs = qs[start:start + length]

            data = self.get_serializer(page_qs, many=True).data

            try:
                draw = int(request.query_params.get('draw', 1))
            except (TypeError, ValueError):
                draw = 1

            return Response({
                'draw': draw,
                'recordsTotal': records_total,
                'recordsFiltered': records_filtered,
                'data': data,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en tabla residentes (linea {exc_tb.tb_lineno}): {e}")
            return Response({
                'draw': 0, 'recordsTotal': 0, 'recordsFiltered': 0, 'data': [], 'error': str(e),
            }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print("Llegando a create de residentes")
            print(request.data)
            residente_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            print(residente_serializer)
            if residente_serializer.is_valid(raise_exception=True):
                residente = residente_serializer.save( user = user_session)
                print("Guardado residente")

                # Portal del residente: se le generan sus cuentas de login en el
                # acto. Va en try aparte a proposito — si el alta de cuentas o el
                # SMTP fallan, el residente YA quedo guardado y las cuentas se
                # pueden generar despues con el boton del modal.
                acceso = {'creadas': 0, 'pendientes_envio': [], 'error': None}
                try:
                    resumen = acceso_residente.asegurar_accesos(residente, user_session)
                    acceso['creadas'] = resumen['creadas']
                    # El front avisa con un modal cuando quedan credenciales sin
                    # enviar, para que el operador las entregue el mismo.
                    acceso['pendientes_envio'] = resumen['pendientes_envio']
                    print(f"Accesos del residente {residente.id}: {resumen['creadas']} cuenta(s) creada(s)")
                except Exception as e_acc:
                    acceso['error'] = str(e_acc)
                    logger.error(f"{datetime.now()} No se pudieron generar accesos del residente {residente.id}: {e_acc}")

                return Response({
                    'Residentes': residente_serializer.data,
                    'residente_id': residente.id,
                    'acceso': acceso,
                }, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion")
                return Response({'errors': residente_serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def update(self, request, *args, **kwargs):
        try:
            print("Esta entrando a actualizar Residentes")
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print(request.data)
            instance = self.get_object()
            print("instance",instance)
            # Cuentas demo: editar residentes ajenos quedó ABIERTO (decisión del
            # usuario 2026-07-22); borrar y aprobar siguen restringidos abajo.
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            #print(serializer)
            if serializer.is_valid(raise_exception=True):
                # Guardar los cambios explícitamente
                self.perform_update(serializer)
                # Refrescar la instancia desde la base de datos para asegurar que tenemos los datos actualizados
                instance.refresh_from_db()
                # Volver a serializar para obtener los datos actualizados
                serializer = self.get_serializer(instance)
                print("edito residente")
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            user_session = request.user
            print("Entrando a retrieve")
            modelos = Residentes.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            Residentes = modelos.filter(slug=slug)
            if Residentes:
                serializer_Residentes = ResidenteSerializers(Residentes, many=True)
                return Response(serializer_Residentes.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            print("LLegando a eliminar residente")
            Residentes = self.get_object()
            if es_usuario_demo(request.user) and Residentes.user_id != request.user.id:
                return Response(
                    {'error': 'Cuenta de demostración: solo puedes eliminar residentes creados por ti.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if Residentes:
                Residentes.delete()
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
  
    # ------------------------------------------------------------------
    # Portal del residente: cuentas de login ligadas al registro
    # ------------------------------------------------------------------
    def _payload_credencial(self, cuenta, tipo, celular=''):
        """Fila del modal 'Usuario vinculado' para una de las dos cuentas."""
        if cuenta is None:
            return None
        credencial = FraternaCredencialAcceso.objects.filter(cuenta=cuenta).first()
        datos = {
            'tipo': tipo,
            'cuenta_id': cuenta.id,
            'username': cuenta.username,
            'email': cuenta.email or '',
            # Para el botón de compartir por WhatsApp del modal.
            'celular': (celular or '').strip(),
            'activa': cuenta.is_active,
            'password_generada': None,
            'fue_cambiada': False,
            'enviada_por_correo': False,
            'generada_en': None,
        }
        if credencial:
            datos.update({
                'password_generada': credencial.password_generada,
                # Si el residente ya la cambio, la guardada no sirve: la UI avisa
                # en vez de dictar una clave muerta.
                'fue_cambiada': credencial.fue_cambiada(),
                'enviada_por_correo': credencial.enviada_por_correo,
                'generada_en': credencial.generada_en,
            })
        return datos

    @action(detail=True, methods=['get'], url_path='credenciales')
    def credenciales(self, request, pk=None):
        """Usuario y clave generada de las cuentas del residente.

        Devuelve la contrasena EN CLARO, asi que queda cerrado a los equipos que
        operan Fraterna (rol_interno 'fraterna' o 'arrendify'). Cualquier otro
        —incluido el propio residente— recibe 403.
        """
        try:
            if not puede_ver_credenciales_residente(request.user):
                return Response(
                    {'error': 'No tienes permiso para ver las credenciales de acceso.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            residente = self.get_object()
            cel_arr = residente.celular_arrendatario or ''
            # El residente suele no traer celular propio: se cae al del arrendatario.
            cel_res = residente.celular_residente or cel_arr
            arrendatario = self._payload_credencial(residente.arrendatario_cuenta, 'arrendatario', cel_arr)
            # Cuando es el mismo humano los dos FK apuntan a la misma cuenta: se
            # reporta una sola vez, marcada, para no dictar dos veces lo mismo.
            misma = (
                residente.arrendatario_cuenta_id
                and residente.arrendatario_cuenta_id == residente.residente_cuenta_id
            )
            residente_pl = None if misma else self._payload_credencial(residente.residente_cuenta, 'residente', cel_res)
            return Response({
                'residente_id': residente.id,
                'nombre_arrendatario': residente.nombre_arrendatario,
                'nombre_residente': residente.nombre_residente,
                'misma_persona': bool(misma),
                'arrendatario': arrendatario,
                'residente': residente_pl,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='generar_acceso')
    def generar_acceso(self, request, pk=None):
        """Crea las cuentas que le falten al registro (idempotente).

        Sirve para los registros dados de alta antes de esta funcion y para
        cuando el alta automatica fallo (p. ej. SMTP caido).
        """
        try:
            if not puede_ver_credenciales_residente(request.user):
                return Response(
                    {'error': 'No tienes permiso para generar accesos.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            residente = self.get_object()
            resumen = acceso_residente.asegurar_accesos(residente, request.user)
            return Response({
                'mensaje': f"{resumen['creadas']} cuenta(s) creada(s)",
                'creadas': resumen['creadas'],
                'misma_persona': resumen['misma_persona'],
            }, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='regenerar_acceso')
    def regenerar_acceso(self, request, pk=None):
        """Nueva contrasena para una de las dos cuentas. Body: {"tipo": ...}.

        Es el unico salvavidas de las cuentas sin correo: no pueden usar
        'recuperar contrasena' porque no tienen email donde recibir el enlace.
        """
        try:
            if not puede_ver_credenciales_residente(request.user):
                return Response(
                    {'error': 'No tienes permiso para regenerar contraseñas.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            residente = self.get_object()
            tipo = (request.data.get('tipo') or 'arrendatario').strip()
            cuenta = residente.residente_cuenta if tipo == 'residente' else residente.arrendatario_cuenta
            if cuenta is None:
                return Response(
                    {'error': f'Este residente no tiene cuenta de {tipo}.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            password, enviada = acceso_residente.regenerar_credencial(cuenta, request.user)
            if password is None:
                return Response(
                    {'error': 'La cuenta no tiene credencial registrada; genera el acceso primero.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response({
                'username': cuenta.username,
                'password_generada': password,
                'enviada_por_correo': enviada,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def mandar_aprobado(self, request, *args, **kwargs):
        try:
            print("Aprobar al residente")
            # Aprobar dispara correos REALES de resultado de investigación:
            # bloqueado por completo para cuentas de demostración.
            if es_usuario_demo(request.user):
                return Response(
                    {'error': 'Cuenta de demostración: aprobar residentes no está disponible.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            info = request.data
            print("el id que llega", info )
            print("accediendo a informacion", info["estado_civil"])
            today = date.today().strftime('%d/%m/%Y')
            ingreso = int(info["ingreso"])
            ingreso_texto = num2words(ingreso, lang='es').capitalize()
            context = {'info': info, "fecha_consulta":today, 'ingreso':ingreso, 'ingreso_texto':ingreso_texto}
        
            # Renderiza el template HTML  
            template = 'home/aprobado_fraterna.html'
    
            html_string = render_to_string(template, context)# lo comvertimos a string
            pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
            print("pdf realizado")
            
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
            print("antes de enviar_archivo",context)
            self.enviar_archivo(archivo, info)
            print("PDF ENVIADO")
            return Response({'Mensaje': 'Todo Bien'},status= status.HTTP_200_OK)
        
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
                  
    def enviar_archivo(self, archivo, info, comentario="nada"):
        print("")
        print("entrando a enviar archivo")
        print("soy pdf content",archivo)
        print("soy comentario",comentario)
        arrendatario = info["nombre_arrendatario"]
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            # destinatario = 'jsepulvedaarrendify@gmail.com'
            destinatario = 'legal@fraterna.mx'
            # destinatario2 = 'juridico.arrendify1@gmail.com'
            destinatario2 = 'smosqueda@fraterna.mx'
            destinatarios = [destinatario, destinatario2]  # envia a legal@fraterna.mx + smosqueda@fraterna.mx (fix NameError)
            
            
            asunto = f"Resultado Investigación Arrendatario {arrendatario}"
            
           
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Cc'] = destinatario2
            msg['Subject'] = asunto
            print("paso objeto mime")
           
            # Estilo del mensaje
            #variable resultado_html_fraterna
            pdf_html = aprobado_fraterna(info)
          
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("pase el msg attach 1")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Resultado_investigación.pdf')
            msg.attach(pdf_part)
            print("pase el msg attach 2")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                server.sendmail(remitente, destinatarios, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})
        
class DocumentosRes(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosResidentes.objects.all()
    serializer_class = DRSerializer
   
    def list(self, request, *args, **kwargs):
        try:
            content = {
                'user': str(request.user),
                'auth': str(request.auth),
            }
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def create (self, request, *args,**kwargs):
        try: 
            user_session = str(request.user.id)
            data = request.data
            data = {
                    "Ine": request.FILES.get('Ine', None),
                    "Ine_arr": request.FILES.get('Ine_arr', None),
                    "Comp_dom": request.FILES.get('Comp_dom', None),
                    "Rfc": request.FILES.get('Rfc', None),
                    "Ingresos": request.FILES.get('Ingresos', None),
                    "Extras": request.FILES.get('Extras', None),
                    "Recomendacion_laboral": request.FILES.get('Recomendacion_laboral', None),
                    "residente":request.data['residente'],
                    "user":user_session
                }
          
            if data:
                documentos_serializer = self.get_serializer(data=data)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save()
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            documentos_inquilinos = self.get_object()
            documento_inquilino_serializer = self.serializer_class(documentos_inquilinos)
            print("Soy ine", documento_inquilino_serializer.data['ine'])
            print("1")
            if documentos_inquilinos:
                ine = documento_inquilino_serializer.data['ine']
                print("Soy ine 2", ine)
                comp_dom= documento_inquilino_serializer.data['comp_dom']
                rfc= documento_inquilino_serializer.data['escrituras_titulo']
                print("Soy RFC", rfc)
                ruta_ine = 'apps/static'+ ine
                print("Ruta ine", ruta_ine)
                ruta_comprobante_domicilio = 'apps/static'+ comp_dom
                ruta_rfc = 'apps/static'+ rfc
                print("Ruta com", ruta_comprobante_domicilio)
                print("Ruta RFC", ruta_rfc)
            
                # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
                documentos_inquilinos.delete()
                return Response({'message': 'Archivo eliminado correctamente'}, status=204)
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
        
    def retrieve(self, request, pk=None):
        try:
            documentos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            inquilino = documentos.filter(id=pk)
            serializer_inquilino = DISerializer(inquilino, many=True)
            print(serializer_inquilino.data)
            ine = serializer_inquilino.data[0]['ine']
            print(ine)
            # documentos_arrendador = self.get_object()
            # print(documentos_arrendador)
            return Response(serializer_inquilino.data)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
   
    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)

            # Los archivos viejos NO se borran antes de guardar: esas keys pueden estar
            # compartidas (dos registros que subieron un archivo con el mismo nombre, o
            # Ine/Ine_arr apuntando al mismo objeto) y borrarlas dejaba al vecino con
            # AccessDenied. Con el path por id de residente, reemplazar un documento
            # sobrescribe su propia key; solo queda residuo si el reemplazo cambio de
            # key (p.ej. de .pdf a .jpg) y ahi se limpia solo si la key vieja es de la
            # generacion nueva (carpeta por id = exclusiva de este registro).
            campos_archivo = ['Ine', 'Ine_arr', 'Comp_dom', 'Rfc', 'Ingresos', 'Extras', 'Recomendacion_laboral']
            previos = {campo: str(getattr(instance, campo) or '') for campo in campos_archivo}

            self.perform_update(serializer)

            prefijo_propio = f'Fraterna/residente/{instance.residente_id}/'
            for campo in campos_archivo:
                viejo = previos[campo]
                nuevo = str(getattr(instance, campo) or '')
                if viejo and viejo != nuevo and viejo.startswith(prefijo_propio):
                    eliminar_archivo_s3(viejo)

            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)  
        
#////////////////////////CONTRATOS///////////////////////////////
class Contratos_fraterna(viewsets.ModelViewSet):
    # authentication_classes = [TokenAuthentication, SessionAuthentication]
    # permission_classes = [IsAuthenticated]
    queryset = FraternaContratos.objects.all()
    serializer_class = ContratoFraternaSerializer

    def _guard_demo(self, request, id_contrato):
        """Cuentas demo: candado solo-propios. Desde 2026-07-22 aplica SOLO a
        las acciones de firma (generar/regenerar/resetear enlaces), renovación
        y borrado, porque alcanzan firmantes y documentos legales REALES.
        Editar, aprobar y descargas quedaron abiertos en contratos ajenos
        (decisión del usuario). Devuelve Response 403 si el contrato existe y
        es ajeno; None deja seguir (los 404 los resuelve cada método)."""
        if not es_usuario_demo(request.user):
            return None
        try:
            info = self.queryset.filter(id=id_contrato).first()
        except (TypeError, ValueError):
            return None
        if info is None or contrato_es_del_usuario(request.user, info):
            return None
        return Response(
            {'error': 'Cuenta de demostración: esta acción solo está disponible en contratos creados por ti.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    def _guard_firmas_deshabilitadas(self):
        """Candado TEMPORAL (2026-07-29): mientras se ajustan los documentos de
        Fraterna no se emiten enlaces de firma nuevos, porque el PDF queda
        congelado en ZapSign al momento de generarlo. Se controla con
        settings.FIRMAS_FRATERNA_DESHABILITADAS (False = reabre). Devuelve
        Response 503 si esta activo; None deja seguir."""
        if not getattr(settings, 'FIRMAS_FRATERNA_DESHABILITADAS', False):
            return None
        mensaje = getattr(
            settings, 'FIRMAS_FRATERNA_MENSAJE_BLOQUEO',
            'El envío a firma está temporalmente deshabilitado.',
        )
        return Response(
            {'error': mensaje, 'bloqueo': 'firmas_deshabilitadas'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def list(self, request, *args, **kwargs):
        try:
           user_session = request.user
           if user_session.is_staff:
               print("Esta entrando a listar contratos semullero")
               contratos =  FraternaContratos.objects.all().order_by('-id')
               serializer = self.get_serializer(contratos, many=True)
               serialized_data = serializer.data

               # Agregar el campo 'is_staff'
               for item in serialized_data:
                 item['is_staff'] = True

               return Response(serialized_data)

           elif es_usuario_demo(user_session):
               # Demo: misma respuesta completa que staff (decisión del usuario
               # 2026-07-22: la cuenta demo edita cualquier contrato y el form de
               # edición se llena con estos mismos datos).
               contratos = FraternaContratos.objects.all().order_by('-id')
               serializer = self.get_serializer(contratos, many=True)
               return Response(serializer.data, status=status.HTTP_200_OK)

           elif user_session.rol == "Inmobiliaria":
               #primero obtenemos mis agentes.
               print("soy inmobiliaria en listar contratos", user_session.name_inmobiliaria)
               agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
               #obtenemos los contratos
               contratos_mios = FraternaContratos.objects.filter(user_id = user_session.id)
               contratos_agentes = FraternaContratos.objects.filter(user_id__in = agentes.values("id"))
               contratos_all = contratos_mios.union(contratos_agentes)
               contratos_all = contratos_all.order_by('-id')
               
               print("es posible hacer esto:", contratos_all)
               
               serializer = self.get_serializer(contratos_all, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
               
           elif user_session.rol == "Agente":
               print(f"soy Agente: {user_session.first_name} en listar contrato")
               residentes_ag = FraternaContratos.objects.filter(user_id = user_session).order_by('-id')
              
               serializer = self.get_serializer(residentes_ag, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
                 
        #    else:
        #        print(f"soy normalito: {user_session.first_name} en listar contrato")
        #        residentes_ag = FraternaContratos.objects.filter(user_id = user_session)
              
        #        serializer = self.get_serializer(residentes_ag, many=True)
        #        return Response(serializer.data, status= status.HTTP_200_OK)
           
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print(user_session)
            print("RD",request.data)
            print("Request",request)
            print("Llegando a create de contrato para fraterna")
            
            fecha_actual = date.today()
            contrato_serializer = self.serializer_class(data = request.data) #Usa el serializer_class
            if contrato_serializer.is_valid():
                nuevo_proceso = ProcesoContrato.objects.create(usuario = user_session, fecha = fecha_actual, status_proceso = "En Revisión")
                if nuevo_proceso:
                    print("ya la armamos")
                    print(nuevo_proceso.id)
                    info = contrato_serializer.save(user = user_session)
                    nuevo_proceso.contrato = info
                    nuevo_proceso.save()
                    # Las solicitudes de cuentas demo no notifican al staff real.
                    if not es_usuario_demo(user_session):
                        send_noti_varios(FraternaContratos, request, title="Nueva solicitud de contrato en Fraterna", text=f"A nombre del Arrendatario {info.residente.nombre_arrendatario}", url = f"fraterna/contrato/#{info.residente.id}_{info.cama}_{info.no_depa}")
                    print("despues de metodo send_noti")
                    print("Se Guardado solicitud")
                    return Response({'Residentes': contrato_serializer.data}, status=status.HTTP_201_CREATED)
                else:
                    print("no se creo el proceso")
                    return Response({'msj':'no se creo el proceso'}, status=status.HTTP_204_NO_CONTENT) 
            
            else:
                print("serializer no valido")
                return Response({'msj':'no es valido el serializer'}, status=status.HTTP_204_NO_CONTENT)     
            
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], url_path='tabla')
    def tabla(self, request, *args, **kwargs):
        """Endpoint DataTables server-side para la tabla de contratos (propuesta.html).
        ADITIVO: NO altera list() (que otras 4 paginas — departamentos, incidencias,
        cama_historial, arrendamientos — consumen completo). Misma visibilidad que list().
        Params DataTables: draw, start, length, search[value], order[0][column], order[0][dir]
        + filtros custom: tipologia, estado_contrato y el filtro especial de fechas
        `criterio_fecha` ('firmado'|'inicia'|'termina'|'terminado') + `periodo_fecha`
        (YYYY-MM), que anula a tipologia y estado mientras este puesto (la busqueda
        SI se combina: busca dentro del subconjunto). Retrocompat con el
        FE anterior: `firmado_mes` ('YYYY-MM') o `firmado_anio` (+ mes 1-12) siguen
        actuando como criterio 'firmado'. La respuesta lleva ademas `conteo_estados`
        (numeros de los chips) y `periodos_filtro` (opciones del select de periodo,
        por criterio; `meses_firmados` = alias de su clave 'firmado')."""
        try:
            user_session = request.user

            # Mismo gating de visibilidad que list()
            if user_session.is_staff:
                base = FraternaContratos.objects.all()
            elif es_usuario_demo(user_session):
                # Demo: ve todo el universo, misma respuesta que staff (ver
                # nota en list(); decisión del usuario 2026-07-22).
                base = FraternaContratos.objects.all()
            elif user_session.rol == "Inmobiliaria":
                agentes = User.objects.filter(pertenece_a=user_session.name_inmobiliaria)
                base = FraternaContratos.objects.filter(
                    Q(user_id=user_session.id) | Q(user_id__in=agentes.values('id'))
                )
            elif user_session.rol == "Agente":
                base = FraternaContratos.objects.filter(user_id=user_session)
            else:
                base = FraternaContratos.objects.none()

            records_total = base.count()
            qs = base

            # Conteos por estado para los chips del FE: un solo GROUP BY sobre la
            # misma visibilidad del usuario (NULL/'' cuentan como 'pendiente').
            # Viaja en CADA respuesta para que los numeros se refresquen gratis,
            # sin endpoint aparte ni requests extra. (El filtro por fechas de
            # vencimiento se probo y se RETIRO el 2026-07-22 a peticion del usuario.)
            conteo_estados = {'todos': 0, 'pendiente': 0, 'actual': 0,
                              'expirado': 0, 'en_renovacion': 0}
            try:
                for estado_val, n_estado in qs.values_list('estado_contrato').annotate(n=Count('id')):
                    clave = estado_val if estado_val in ('actual', 'expirado', 'en_renovacion') else 'pendiente'
                    conteo_estados[clave] += n_estado
                conteo_estados['todos'] = (conteo_estados['pendiente'] + conteo_estados['actual']
                                           + conteo_estados['expirado'] + conteo_estados['en_renovacion'])
            except Exception as e_conteo:
                logger.error(f"{datetime.now()} tabla contratos: fallo conteo estados: {e_conteo}")

            # Opciones del filtro especial de fechas, POR CRITERIO: para cada uno,
            # los meses que TIENEN contratos con su conteo. El FE puebla su 2do
            # select con la lista del criterio elegido; solo salen periodos con
            # algo que mostrar, asi no se puede escoger uno vacio.
            # Un contrato cuenta UNA vez por periodo aunque tenga dos rondas ahi
            # (solo pasa en 'firmado': inicial expirada + renovacion firmada el
            # mismo mes; los demas criterios miran la UNICA ronda en pie).
            # Viaja en cada respuesta igual que conteo_estados: cero requests extra.
            periodos_filtro = {}
            meses_firmados = []   # alias de periodos_filtro['firmado'] para el FE viejo en prod
            try:
                ids_visibles = base.values('id')
                rondas_firmadas = (_rondas_con_fecha_de_firma()
                                   .filter(contrato_id__in=ids_visibles))
                periodos_filtro['firmado'] = _agrupar_meses(rondas_firmadas, 'firmado_el')
                for criterio, (rail, campo) in CRITERIOS_RONDA_VIGENTE.items():
                    rondas_rail = FraternaRondaFirma.objects.filter(
                        estado='firmado',
                        contrato__estado_contrato=rail,
                        contrato_id__in=ids_visibles,
                    )
                    periodos_filtro[criterio] = _agrupar_meses(rondas_rail, campo)
                meses_firmados = periodos_filtro['firmado']
            except Exception as e_meses:
                logger.error(f"{datetime.now()} tabla contratos: fallo periodos del filtro: {e_meses}")

            # ===== Filtro ESPECIAL de fechas: [criterio] + [periodo YYYY-MM] =====
            # MANDA sobre tipologia y estado: mientras viene el periodo esos dos se
            # ignoran a proposito — regla de producto ("este filtro borra los demas")
            # — y el FE esconde los chips para que la UI no prometa algo distinto de
            # lo que el servidor hace. La BUSQUEDA es la excepcion: si convive con
            # el filtro especial (se aplica abajo, fuera de este if/else).
            #
            # Criterios (`criterio_fecha` + `periodo_fecha`):
            #  'firmado'   -> contratos con una ronda concretada FIRMADA en el
            #                 periodo (fecha real de ZapSign, inicial o renovacion;
            #                 ver _rondas_con_fecha_de_firma).
            #  'inicia'    -> VIGENTES cuyo termino en pie arranca en el periodo
            #                 (fecha_celebracion de su ronda 'firmado').
            #  'termina'   -> VIGENTES cuyo termino en pie vence en el periodo
            #                 (fecha_vigencia de su ronda 'firmado').
            #  'terminado' -> EXPIRADOS cuyo termino vencio en el periodo (misma
            #                 fecha_vigencia; el rail del contrato ya dice expirado).
            # Los 'en_renovacion' no salen en los criterios de rail: al renovar su
            # ronda en pie pasa a 'expirado' y la nueva aun es 'pendiente'.
            #
            # Retrocompat con el FE anterior en prod (solo criterio 'firmado'):
            # `firmado_mes=YYYY-MM`, o `firmado_anio` (+ `firmado_mes` 1-12
            # opcional = AÑO COMPLETO). Se mantiene para que un deploy a medias
            # no deje el filtro muerto.
            criterio_f, anio_f, mes_f = None, None, None
            criterio_param = (request.query_params.get('criterio_fecha') or '').strip().lower()
            periodo_param = _parsear_mes_anio(request.query_params.get('periodo_fecha'))
            if periodo_param and (criterio_param == 'firmado' or criterio_param in CRITERIOS_RONDA_VIGENTE):
                criterio_f = criterio_param
                anio_f, mes_f = periodo_param
            else:
                anio_f = _parsear_anio(request.query_params.get('firmado_anio'))
                mes_f = _parsear_mes(request.query_params.get('firmado_mes'))
                if anio_f is None:
                    compat = _parsear_mes_anio(request.query_params.get('firmado_mes'))
                    if compat:
                        anio_f, mes_f = compat
                if anio_f:
                    criterio_f = 'firmado'
            if criterio_f == 'firmado':
                # Se resuelve PRIMERO que rondas son del periodo y luego se cruzan
                # por id: asi la fecha y el estado los cumple la MISMA ronda.
                # Filtrar el contrato por las dos cosas por separado casaria "una
                # ronda firmada + OTRA ronda del periodo", que no es lo pedido.
                rondas_del_periodo = _rondas_con_fecha_de_firma().filter(firmado_el__year=anio_f)
                if mes_f:
                    rondas_del_periodo = rondas_del_periodo.filter(firmado_el__month=mes_f)
                qs = qs.filter(
                    rondas_firma__id__in=Subquery(rondas_del_periodo.values('id'))
                ).distinct()
            elif criterio_f in CRITERIOS_RONDA_VIGENTE:
                rail, campo = CRITERIOS_RONDA_VIGENTE[criterio_f]
                # Un solo filter(): el estado 'firmado' y la fecha deben cumplirlos
                # la MISMA ronda (aqui ademas hay maximo una 'firmado' por contrato,
                # por constraint, pero el patron se mantiene consistente).
                cond = {'rondas_firma__estado': 'firmado',
                        f'rondas_firma__{campo}__year': anio_f}
                if mes_f:
                    cond[f'rondas_firma__{campo}__month'] = mes_f
                qs = qs.filter(estado_contrato=rail, **cond).distinct()
            else:
                # Filtro por tipologia
                tipologia = (request.query_params.get('tipologia') or '').strip()
                if tipologia:
                    if tipologia == 'Sin tipologia':
                        qs = qs.filter(
                            Q(tipologia__isnull=True) | Q(tipologia='') |
                            Q(tipologia='--------') | Q(tipologia='---------')
                        )
                    else:
                        qs = qs.filter(tipologia__iexact=tipologia)

                # Filtro por estado del contrato (rail estado_contrato). El FE manda
                # 'pendiente' | 'actual' | 'expirado'; 'pendiente' = sin determinar
                # (NULL o vacio). Valor desconocido se ignora.
                estado_param = (request.query_params.get('estado_contrato') or '').strip().lower()
                if estado_param:
                    if estado_param == 'pendiente':
                        qs = qs.filter(Q(estado_contrato__isnull=True) | Q(estado_contrato=''))
                    elif estado_param in ('actual', 'expirado', 'en_renovacion'):
                        qs = qs.filter(estado_contrato=estado_param)

            # Busqueda global (DataTables search[value]): aplica SIEMPRE — sin
            # filtro especial busca en todo el universo; con el, busca DENTRO del
            # subconjunto del criterio ("los firmados en julio que se llamen X").
            # Es el UNICO filtro normal que convive con el especial (pedido
            # 2026-08-11); tipologia y estado siguen anulados mientras haya periodo.
            search_value = (request.query_params.get('search[value]') or '').strip()
            if search_value:
                # Busqueda insensible a acentos en nombres y tipologia: unaccent() sobre la
                # columna + termino sin acentos. "jesus" -> "Jesús", "recamara" -> "Recámara".
                term_sa = _sin_acentos(search_value)
                qs = qs.annotate(
                    _na_ua=Unaccent('residente__nombre_arrendatario'),
                    _nr_ua=Unaccent('residente__nombre_residente'),
                    _tip_ua=Unaccent('tipologia'),
                )
                cond_busqueda = (
                    Q(no_depa__icontains=search_value) |
                    Q(cama__icontains=search_value) |
                    Q(_tip_ua__icontains=term_sa) |
                    Q(_na_ua__icontains=term_sa) |
                    Q(_nr_ua__icontains=term_sa) |
                    # Contacto del registro vinculado (tabla residentes), de AMBAS
                    # personas. Sin unaccent: en BD los celulares son puros digitos
                    # (846/846 verificados 2026-08-11) y los correos ASCII.
                    Q(residente__celular_arrendatario__icontains=search_value) |
                    Q(residente__celular_residente__icontains=search_value) |
                    Q(residente__correo_arrendatario__icontains=search_value) |
                    Q(residente__correo_residente__icontains=search_value)
                )
                if search_value.isdigit():
                    cond_busqueda = cond_busqueda | Q(id=int(search_value))
                qs = qs.filter(cond_busqueda)

            records_filtered = qs.count()

            # Orden (solo columnas con campo en BD; el resto cae a id)
            col_map = {
                0: 'id', 1: 'no_depa',
                2: 'residente__nombre_arrendatario',
                3: 'residente__nombre_residente',
                4: 'fecha_vigencia',
            }
            try:
                order_col = int(request.query_params.get('order[0][column]', 0))
            except (TypeError, ValueError):
                order_col = 0
            order_field = col_map.get(order_col, 'id')
            if request.query_params.get('order[0][dir]', 'desc') == 'desc':
                order_field = '-' + order_field
            qs = qs.order_by(order_field)

            # Paginacion por indices (start/length de DataTables)
            try:
                start = int(request.query_params.get('start', 0))
            except (TypeError, ValueError):
                start = 0
            try:
                length = int(request.query_params.get('length', 10))
            except (TypeError, ValueError):
                length = 10
            if length <= 0:
                length = 10            # DataTables manda -1 para "todos"; lo acotamos
            length = min(length, 100)  # tope defensivo
            page_qs = qs[start:start + length]

            data = self.get_serializer(page_qs, many=True).data
            if user_session.is_staff:
                for item in data:
                    item['is_staff'] = True

            # Bitacora de rondas: adjunta el espejo de firmas por fila (best-effort;
            # si el ledger falla, la tabla sale igual y el FE cae al flujo viejo).
            try:
                data = self._adjuntar_ronda_firma(data)
            except Exception as e_rondas:
                logger.error(f"{datetime.now()} tabla contratos: fallo adjuntando rondas: {e_rondas}")

            try:
                draw = int(request.query_params.get('draw', 1))
            except (TypeError, ValueError):
                draw = 1

            return Response({
                'draw': draw,
                'recordsTotal': records_total,
                'recordsFiltered': records_filtered,
                'data': data,
                'conteo_estados': conteo_estados,
                'periodos_filtro': periodos_filtro,
                'meses_firmados': meses_firmados,   # alias 'firmado' p/el FE viejo en prod
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en tabla contratos (linea {exc_tb.tb_lineno}): {e}")
            return Response({
                'draw': 0, 'recordsTotal': 0, 'recordsFiltered': 0, 'data': [], 'error': str(e),
            }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='conteo_renovaciones')
    def conteo_renovaciones(self, request, *args, **kwargs):
        """GET /contratos_fraterna/conteo_renovaciones/ — mapa {contrato_id: n},
        n = rondas de firma CONCRETADAS del contrato: estado 'firmado' (el termino
        en pie) + 'expirado' (terminos reemplazados por renovacion). 'pendiente' y
        'cancelado' no cuentan. Lectura: 0/ausente = nunca ha firmado, 1 = termino
        inicial, 2+ = ha renovado. Alimenta la columna Renovaciones del export a
        Excel (ADITIVO: el export ya consume list(), esto viaja aparte para no
        tocar su shape compartido). Misma visibilidad que list()/tabla."""
        try:
            user_session = request.user
            rol = getattr(user_session, 'rol', None)  # anonimo no tiene .rol -> mapa vacio
            if user_session.is_staff or es_usuario_demo(user_session):
                base = FraternaContratos.objects.all()
            elif rol == "Inmobiliaria":
                agentes = User.objects.filter(pertenece_a=user_session.name_inmobiliaria)
                base = FraternaContratos.objects.filter(
                    Q(user_id=user_session.id) | Q(user_id__in=agentes.values('id'))
                )
            elif rol == "Agente":
                base = FraternaContratos.objects.filter(user_id=user_session)
            else:
                base = FraternaContratos.objects.none()
            # .order_by() final: el Meta.ordering de la ronda ('-generado_en') se
            # colaria al GROUP BY y partiria los conteos en una fila por ronda.
            conteos = (FraternaRondaFirma.objects
                       .filter(contrato_id__in=base.values('id'),
                               estado__in=('firmado', 'expirado'))
                       .values('contrato_id')
                       .annotate(n=Count('id'))
                       .order_by())
            return Response({str(c['contrato_id']): c['n'] for c in conteos},
                            status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en conteo_renovaciones (linea {exc_tb.tb_lineno}): {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Ventana del AVISO anticipado del calendario de contratos. Es MAS ancha a
    # proposito que VENTANA_POR_RENOVAR_DIAS (30, ver abajo): a 45 dias el equipo
    # VE VENIR el vencimiento en el calendario y puede planear; a 30 el sistema
    # habilita el disparo de renovacion (flag `por_renovar` + job de correos
    # `renovar_contrato`). Escalon deliberado, no dos numeros que se contradicen.
    DIAS_AVISO_TERMINO = 45

    def _base_visible_calendario(self, user_session):
        """Universo de contratos que este usuario puede ver: mismo gating que
        list()/tabla(), extraido para que los dos endpoints del calendario no
        lleven copias que puedan divergir."""
        if user_session.is_staff or es_usuario_demo(user_session):
            # Demo ve el universo completo, igual que staff (decision 2026-07-22).
            return FraternaContratos.objects.all()
        if user_session.rol == "Inmobiliaria":
            agentes = User.objects.filter(pertenece_a=user_session.name_inmobiliaria)
            return FraternaContratos.objects.filter(
                Q(user_id=user_session.id) | Q(user_id__in=agentes.values('id'))
            )
        if user_session.rol == "Agente":
            return FraternaContratos.objects.filter(user_id=user_session)
        return FraternaContratos.objects.none()

    def _leyenda_termino(self, fin, hoy):
        """Cuanto le queda al contrato, en el idioma de la UI."""
        dias = (fin - hoy).days
        if dias == 0:
            return 'Finaliza hoy'
        if dias == 1:
            return 'Finaliza mañana'
        if dias > 1:
            return f'Finalizará en {dias} días'
        if dias == -1:
            return 'Finalizó ayer'
        return f'Finalizó hace {abs(dias)} días'

    @action(detail=False, methods=['get'], url_path='calendario_ficha')
    def calendario_ficha(self, request, *args, **kwargs):
        """Ficha INFORMATIVA de un contrato para el modal del calendario.

        El calendario no navega al detalle (decision del usuario 2026-07-27):
        al hacer clic en un evento se abre un modal de solo lectura con lo que
        el equipo necesita para decidir si renovar y a quien llamar. Endpoint
        aparte del listado del mes a proposito: la lista se queda ligera (130
        eventos en junio) y la ficha pide lo pesado solo del contrato clicado.

        Las fechas salen de la RONDA DE FIRMA ACTIVA (la ultima 'firmado' = el
        termino en pie, la misma que manda en `vigencia_efectiva`), no de la
        fila: la fila es la copia de trabajo del siguiente intento. Un contrato
        legacy sin bitacora cae a las fechas de la fila y lo dice en `fuente`.

        Params: `id` = id del contrato.
        """
        try:
            base = self._base_visible_calendario(request.user)
            try:
                id_contrato = int(request.query_params.get('id') or 0)
            except (TypeError, ValueError):
                return Response({'error': 'id inválido'}, status=status.HTTP_400_BAD_REQUEST)

            con = (base.filter(id=id_contrato)
                   .select_related('residente', 'cama_ref', 'cama_ref__departamento')
                   .prefetch_related(Prefetch(
                       'rondas_firma',
                       queryset=FraternaRondaFirma.objects.filter(
                           estado='firmado').order_by('-numero'),
                       to_attr='rondas_firmadas',
                   )).first())
            if con is None:
                return Response({'error': 'Contrato no encontrado'},
                                status=status.HTTP_404_NOT_FOUND)

            hoy = timezone.now().date()
            fin, fuente = con.vigencia_efectiva()
            firmadas = getattr(con, 'rondas_firmadas', None) or []
            ronda = firmadas[0] if firmadas else None

            def _iso(f):
                return f.isoformat() if f else None

            # Fechas congeladas de la ronda activa; sin bitacora, las de la fila.
            if ronda is not None:
                fechas = {
                    'celebracion': _iso(ronda.fecha_celebracion),
                    'vigencia': _iso(ronda.fecha_vigencia),
                    'move_in': _iso(ronda.fecha_move_in),
                    'move_out': _iso(ronda.fecha_move_out),
                }
                datos_ronda = {
                    'numero': ronda.numero,
                    'uuid': str(ronda.uuid) if ronda.uuid else None,
                    'tipo': ronda.tipo,
                    'estado': ronda.estado,
                    'mono_paquete': ronda.mono_paquete,
                }
            else:
                fechas = {
                    'celebracion': _iso(con.fecha_celebracion),
                    'vigencia': _iso(con.fecha_vigencia),
                    'move_in': _iso(con.fecha_move_in),
                    'move_out': _iso(con.fecha_move_out),
                }
                datos_ronda = None

            res = con.residente
            # Piso: el `nivel` del inventario ("PB", "N7") manda sobre el texto
            # libre de la fila, que lo capturo un humano.
            piso = ''
            if con.cama_ref_id and con.cama_ref and con.cama_ref.departamento_id:
                piso = con.cama_ref.departamento.nivel or ''
            piso = piso or con.piso or ''

            return Response({
                'contrato_id': con.id,
                'estado_contrato': con.estado_contrato,
                'hoy': hoy.isoformat(),
                'ubicacion': {
                    'no_depa': con.no_depa or '',
                    'cama': con.cama or '',
                    'piso': str(piso),
                    'tipologia': con.tipologia or '',
                },
                'fechas': fechas,
                'ronda': datos_ronda,
                'fuente_fechas': fuente,        # 'ronda' | 'contrato'
                'termino': {
                    'fecha': _iso(fin),
                    'dias_restantes': (fin - hoy).days if fin else None,
                    'leyenda': self._leyenda_termino(fin, hoy) if fin else 'Sin fecha de término',
                },
                'arrendatario': {
                    'nombre': getattr(res, 'nombre_arrendatario', '') or '',
                    'correo': getattr(res, 'correo_arrendatario', '') or '',
                    'celular': getattr(res, 'celular_arrendatario', '') or '',
                },
                'residente': {
                    'nombre': getattr(res, 'nombre_residente', '') or '',
                    'correo': getattr(res, 'correo_residente', '') or '',
                    'celular': getattr(res, 'celular_residente', '') or '',
                },
                'renta': con.renta or '',
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en ficha de calendario "
                         f"(linea {exc_tb.tb_lineno}): {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='calendario')
    def calendario(self, request, *args, **kwargs):
        """Eventos del ciclo de vida de los contratos para el "Calendario de
        contratos" (pestana de propuesta.html, junto al Listado).

        ADITIVO: no toca list() ni tabla(). Misma visibilidad por usuario que
        ellos. Solo lee.

        DOS eventos por contrato, ambos derivados de la MISMA fecha:
          · `termino` -> el dia en que el contrato termina;
          · `aviso`   -> `termino` - 45 dias (DIAS_AVISO_TERMINO), la recta final.
        No hay consulta extra para el aviso: sale del mismo registro.

        La fecha la da `FraternaContratos.vigencia_efectiva()`, la MISMA que usa
        el job `expirar_contratos_vencidos` para mandar el contrato a 'expirado'
        — el calendario no puede prometer un dia distinto del que el cron va a
        ejecutar. Manda el DOCUMENTO firmado (ronda 'firmado'), no la fila.

        Solo entran los VIGENTES (`estado_contrato='actual'`), decision del
        usuario 2026-07-27: son los unicos con termino comprometido y firmado.
        Los 'pendiente' traen fechas de borrador editable (inundarian el
        calendario con dias que no comprometen a nadie), los 'expirado' ya
        terminaron y los 'en_renovacion' tienen su termino en reemplazo.

        Params: `mes=YYYY-MM` (default: mes actual).
        Devuelve los eventos de ESE mes + `resumen` de TODOS los meses con
        eventos (el mapa del ano del FE: sin el, con los vencimientos de
        Fraterna concentrados en 2 dias del ciclo escolar, se navega a ciegas
        por meses vacios).
        """
        try:
            base = self._base_visible_calendario(request.user)

            # Mes visible (YYYY-MM). Un valor invalido cae al mes actual en vez
            # de reventar: el calendario siempre pinta algo.
            hoy = timezone.now().date()
            try:
                _a, _m = (request.query_params.get('mes') or '').strip().split('-')
                anio_v, mes_v = int(_a), int(_m)
                if not (1 <= mes_v <= 12 and 1900 <= anio_v <= 2999):
                    raise ValueError('mes fuera de rango')
            except (ValueError, TypeError):
                anio_v, mes_v = hoy.year, hoy.month
            mes_key = f'{anio_v:04d}-{mes_v:02d}'

            # Una sola pasada: prefetch de la ronda firmada (evita el N+1 que
            # haria vigencia_efectiva() contrato por contrato) + el residente,
            # de donde salen los nombres de la fila.
            qs = (base.filter(estado_contrato='actual')
                  .select_related('residente')
                  .prefetch_related(Prefetch(
                      'rondas_firma',
                      queryset=FraternaRondaFirma.objects.filter(
                          estado='firmado').order_by('-numero'),
                      to_attr='rondas_firmadas',
                  )))

            eventos_mes = []
            resumen = {}          # {'YYYY-MM': {'aviso': n, 'termino': n}}
            sin_fecha = 0
            total = 0
            for con in qs:
                total += 1
                fin, fuente = con.vigencia_efectiva()
                if not fin:
                    # Ronda firmada sin fecha de vigencia: no es juzgable (misma
                    # regla que el job, que tampoco la vence). Se cuenta para
                    # poder avisarlo en la UI en vez de desaparecerlo.
                    sin_fecha += 1
                    continue
                res = con.residente
                aviso = fin - timedelta(days=self.DIAS_AVISO_TERMINO)
                for tipo, fecha in (('aviso', aviso), ('termino', fin)):
                    clave = f'{fecha.year:04d}-{fecha.month:02d}'
                    resumen.setdefault(clave, {'aviso': 0, 'termino': 0})[tipo] += 1
                    if clave != mes_key:
                        continue
                    eventos_mes.append({
                        'tipo': tipo,
                        'fecha': fecha.isoformat(),
                        'contrato_id': con.id,
                        'no_depa': con.no_depa or '',
                        'cama': con.cama or '',
                        'tipologia': con.tipologia or '',
                        'arrendatario': getattr(res, 'nombre_arrendatario', '') or '',
                        'residente': getattr(res, 'nombre_residente', '') or '',
                        'fecha_fin': fin.isoformat(),
                        'dias_restantes': (fin - hoy).days,
                        'fuente_fecha': fuente,          # 'ronda' | 'contrato'
                        'estado_contrato': con.estado_contrato,
                    })

            # Orden dentro del mes: por dia, luego departamento (numerico cuando
            # se puede: "803" antes que "1013") y cama.
            def _orden_depa(valor):
                texto = (valor or '').strip()
                try:
                    return (0, int(texto), '')
                except ValueError:
                    return (1, 0, texto.lower())

            eventos_mes.sort(key=lambda ev: (
                ev['fecha'], _orden_depa(ev['no_depa']), ev['cama'] or ''))

            return Response({
                'mes': mes_key,
                'hoy': hoy.isoformat(),
                'dias_aviso': self.DIAS_AVISO_TERMINO,
                'eventos': eventos_mes,
                'resumen': resumen,
                'totales': {'vigentes': total, 'sin_fecha': sin_fecha},
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en calendario de contratos "
                         f"(linea {exc_tb.tb_lineno}): {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # --- Bitacora de rondas: adjunto ADITIVO para la tabla (espejo de firmas) ---

    def _ronda_a_dict(self, ronda):
        """Serializa una ronda + su espejo de firmantes para el FE (columna FIRMAS
        de la tabla y modal "Historial de firmas")."""
        def _url_pdf(key):
            # URL del PDF firmado en NUESTRO S3 (default_storage la arma con el
            # custom domain del bucket, mismo patron que el resto de archivos).
            if not key:
                return None
            try:
                return default_storage.url(key)
            except Exception:
                return None

        return {
            'id': ronda.id,
            'uuid': str(ronda.uuid) if ronda.uuid else None,
            'numero': ronda.numero,
            'tipo': ronda.tipo,
            'estado': ronda.estado,
            'token_1': ronda.token_1,
            'token_2': ronda.token_2,
            'estado_firma_1': ronda.estado_firma_1,
            'estado_firma_2': ronda.estado_firma_2,
            # PDF firmado en NUESTRO S3: existe solo cuando el doc junto las 4
            # firmas (doc-level 'signed' -> el webhook lo baja con reintentos).
            'pdf_firmado_1': ronda.pdf_firmado_1,
            'pdf_firmado_2': ronda.pdf_firmado_2,
            'pdf_firmado_1_url': _url_pdf(ronda.pdf_firmado_1),
            'pdf_firmado_2_url': _url_pdf(ronda.pdf_firmado_2),
            'generado_en': ronda.generado_en.isoformat() if ronda.generado_en else None,
            'cerrado_en': ronda.cerrado_en.isoformat() if ronda.cerrado_en else None,
            'motivo': ronda.motivo,
            'usuario': ronda.usuario,
            # Fechas congeladas del intento (lo que imprimieron sus documentos).
            'fecha_celebracion': ronda.fecha_celebracion.isoformat() if ronda.fecha_celebracion else None,
            'fecha_vigencia': ronda.fecha_vigencia.isoformat() if ronda.fecha_vigencia else None,
            'fecha_move_in': ronda.fecha_move_in.isoformat() if ronda.fecha_move_in else None,
            'fecha_move_out': ronda.fecha_move_out.isoformat() if ronda.fecha_move_out else None,
            'firmantes': [
                {
                    'paquete': f.paquete,
                    'nombre': f.nombre,
                    'rol': f.rol,
                    'email': f.email,
                    'sign_url': f.sign_url,
                    'estado': f.estado,
                    'firmado_en': f.firmado_en.isoformat() if f.firmado_en else None,
                }
                # Orden estable: paquete y luego orden de alta (= ROLES_FIRMANTES_P1).
                for f in sorted(ronda.firmantes.all(), key=lambda f: (f.paquete, f.pk))
            ],
        }

    # Ventana del disparo semi-auto de renovacion (handoff §7): mismo horizonte que
    # el job de correos `renovar_contrato` (scheduler.py, 30 dias).
    VENTANA_POR_RENOVAR_DIAS = 30

    def _estado_por_renovar(self, item, rondas_c):
        """Disparo semi-auto de renovacion (handoff §7), CALCULADO al leer (sin
        columna nueva ni job que marque; no puede quedarse viejo).

        Devuelve (flag, vigencia) donde flag = 'proxima' si la vigencia
        COMPROMETIDA cae dentro de la ventana, 'vencida' si ya paso, None si no
        aplica. Comprometida = `fecha_vigencia` de la ultima ronda 'firmado'
        (la fila del contrato puede estar ya editada para el siguiente intento);
        para contratos sin bitacora, la del contrato SOLO si
        estado_contrato='actual' (unico marcador confiable de termino vivo — asi
        los cientos de contratos historicos no inundan la lista de badges).
        Con una ronda 'pendiente' abierta no aplica: ya hay un intento en curso.
        """
        if any(r.estado == 'pendiente' for r in rondas_c):
            return None, None
        firmada = next((r for r in rondas_c if r.estado == 'firmado'), None)
        if firmada is not None:
            vigencia = firmada.fecha_vigencia
        elif item.get('estado_contrato') == 'actual':
            vigencia = item.get('fecha_vigencia')
            if isinstance(vigencia, str):
                try:
                    vigencia = date.fromisoformat(vigencia)
                except ValueError:
                    vigencia = None
        else:
            return None, None
        if not vigencia:
            return None, None
        hoy = timezone.now().date()
        if vigencia < hoy:
            return 'vencida', vigencia
        if vigencia <= hoy + timedelta(days=self.VENTANA_POR_RENOVAR_DIAS):
            return 'proxima', vigencia
        return None, None

    def _adjuntar_ronda_firma(self, data):
        """Adjunta a cada fila serializada su ronda de firma relevante, con el espejo
        de firmantes, para que el FE pinte FIRMAS desde la BD sin pegarle a ZapSign.

        Relevante = la ronda 'pendiente' y, si no hay abierta, la ultima 'firmado';
        las 'cancelado' no pintan (enlaces desechados). Contratos sin ronda (sin
        backfill) llevan None y el FE cae al flujo viejo por token del contrato.

        Ademas calcula `por_renovar` / `vigencia_comprometida` por fila (badge y
        boton "Renovar contrato" del FE; ver _estado_por_renovar).
        """
        ids = [item.get('id') for item in data if item.get('id')]
        if not ids:
            return data
        rondas = (FraternaRondaFirma.objects
                  .filter(contrato_id__in=ids)
                  .exclude(estado='cancelado')
                  .order_by('-generado_en')
                  .prefetch_related('firmantes'))
        por_contrato = {}
        for ronda in rondas:
            por_contrato.setdefault(ronda.contrato_id, []).append(ronda)
        for item in data:
            rondas_c = por_contrato.get(item.get('id'), [])
            # La ronda RELEVANTE de la lista = el intento vivo ('pendiente') o, si no
            # hay, el termino en pie ('firmado'). Las 'expirado' (renovaciones ya
            # reemplazadas) NO pintan en la lista: viven en el Historial. Un contrato
            # 'en_renovacion' sin intento generado todavia queda con ronda_firma None
            # y el FE pinta "RENOVACION INICIADA" desde estado_contrato.
            ronda = (next((r for r in rondas_c if r.estado == 'pendiente'), None)
                     or next((r for r in rondas_c if r.estado == 'firmado'), None))
            item['ronda_firma'] = self._ronda_a_dict(ronda) if ronda else None
            try:
                flag, vigencia = self._estado_por_renovar(item, rondas_c)
            except Exception as e:
                logger.warning(f"{datetime.now()} por_renovar fallo (contrato "
                               f"{item.get('id')}): {e}")
                flag, vigencia = None, None
            item['por_renovar'] = flag
            item['vigencia_comprometida'] = vigencia.isoformat() if vigencia else None
        return data

    def retrieve(self, request, *args, **kwargs):
        """GET de un contrato. ADITIVO: adjunta `ronda_firma` (bitacora) igual que
        /tabla/, para que la pagina de editar conozca el candado de firma sin
        importar desde que lista se llego (el list() compartido NO la trae)."""
        response = super().retrieve(request, *args, **kwargs)
        try:
            if isinstance(response.data, dict) and response.data.get('id'):
                self._adjuntar_ronda_firma([response.data])
        except Exception as e:
            logger.error(f"{datetime.now()} retrieve: no se pudo adjuntar ronda_firma: {e}")
        return response

    def rondas_firma_historial(self, request, *args, **kwargs):
        """GET /fraterna/rondas_firma/?id=N — historial COMPLETO de rondas de firma
        del contrato (bitacora), de la mas reciente a la mas vieja, con el espejo
        de firmantes. Alimenta el modal "Historial de firmas / renovaciones" del
        FE: auditoria de intentos + enlaces de los finales (Fraterna/Jonathan)
        que siguen pendientes en rondas ya comprometidas (la vigencia no los
        espera; su firma se cobra desde aqui). A diferencia de la columna FIRMAS,
        SI incluye las rondas canceladas: son el rastro de enlaces desechados
        (sus docs quedaron soft-deleted en ZapSign, ya no son firmables).
        """
        try:
            contrato_id = request.query_params.get('id')
            instance = self.queryset.filter(id=contrato_id).first()
            if instance is None:
                return Response({'error': 'Contrato no encontrado'},
                                status=status.HTTP_404_NOT_FOUND)
            rondas = (instance.rondas_firma.all()
                      .order_by('-numero')
                      .prefetch_related('firmantes'))
            return Response({
                'id': instance.id,
                'rondas': [self._ronda_a_dict(r) for r in rondas],
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en rondas_firma_historial "
                         f"(linea {exc_tb.tb_lineno}): {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        try:
            #primero verificamos que tenga contadores activos
            print("Esta entrando a actualizar Contratos Fraterna")
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            # Cuentas demo: editar contratos ajenos quedó ABIERTO (decisión del
            # usuario 2026-07-22); firmas/renovación/borrado siguen con _guard_demo.

            # Candado rol_interno (2026-08-04): un contrato APROBADO solo lo edita
            # el equipo Arrendify. Ventana operativa abierta para los demás: ronda
            # 'pendiente' SIN Paquete 2 (asignación depa/cama tras P1 y captura de
            # fechas/renta en renovación); dentro de ella, los guards de abajo
            # siguen acotando campo por campo.
            if not es_operador_arrendify(request.user):
                aprobado = ProcesoContrato.objects.filter(
                    contrato_id=instance.id, status_proceso='Aprobado').exists()
                ventana_operativa = instance.rondas_firma.filter(
                    estado='pendiente').filter(
                    Q(token_2__isnull=True) | Q(token_2='')).exists()
                if aprobado and not ventana_operativa:
                    return Response(
                        {'error': 'Contrato aprobado: solo el equipo Arrendify '
                                  'puede editarlo. Pide desaprobarlo para hacer '
                                  'cambios.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            # Candado de edicion durante firma (bitacora de rondas): con una ronda
            # 'pendiente', los terminos que ya se mandaron a firmar NO se editan.
            # Va ANTES de cualquier manejo del plano: si el intento esta en firma,
            # el update entero se rechaza.
            campos_bloqueados = self._campos_bloqueados_en_firma(instance, request.data)
            if campos_bloqueados:
                return Response(
                    {'error': 'El contrato esta en proceso de firma; estos campos ya se '
                              'mandaron a firmar y no se pueden editar: '
                              f'{", ".join(campos_bloqueados)}. Para cambiarlos, usa '
                              '"Generar nuevos enlaces de firma" (cancela el intento '
                              'actual) y vuelve a generar el paquete.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Contrato VIGENTE sin renovacion en curso = SELLADO: sus datos son los
            # del termino firmado (rail 'actual') y ningun cambio real se acepta —
            # el guardado fantasma del form (mismos valores) si pasa. La salida es
            # "Renovar contrato" (iniciar_renovacion): abre la ronda de renovacion
            # y con ella el contrato vuelve a ser editable.
            if self._vigente_sellado(instance):
                campos_modelo = [
                    f.name for f in instance._meta.concrete_fields
                    if f.name != 'id' and (not f.is_relation or f.name == 'residente')
                ]
                cambios = self._campos_con_cambio(instance, request.data, campos_modelo)
                if (str(request.data.get('borrar_plano', '')).lower() == 'true'
                        and str(instance.plano_localizacion or '')):
                    cambios.append('plano_localizacion')
                if cambios:
                    return Response(
                        {'error': 'El contrato esta sellado (su termino esta firmado): '
                                  'sus datos no se pueden editar '
                                  f'({", ".join(cambios)}). Para modificarlo usa '
                                  '"Renovar contrato".'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Plano anterior: se limpia DESPUES de guardar (ver mas abajo). Antes se borraba
            # aqui, antes de validar: si el serializer fallaba, el contrato se quedaba sin el
            # viejo y sin el nuevo. El serializer ya asigna el archivo desde request.data.
            plano_anterior = ''
            if 'plano_localizacion' in request.data:
                plano_anterior = str(instance.plano_localizacion or '')
            # El FE manda borrar_plano='true' cuando piden quitar el plano: un <input type=file>
            # no sabe expresar "sin archivo" y DRF rechaza el string vacio en un FileField. Va
            # como campo extra a proposito: el serializer lo ignora (no existe en el modelo).
            borrar_plano = str(request.data.get('borrar_plano', '')).lower() == 'true'
            if borrar_plano:
                plano_anterior = str(instance.plano_localizacion or '')

            proceso = ProcesoContrato.objects.all().get(contrato_id = instance.id)
            print("el contador es: ",proceso.contador)
            if (proceso.contador > 0 ):
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                if serializer.is_valid(raise_exception=True):
                    self.perform_update(serializer)
                    if borrar_plano:
                        instance.plano_localizacion = None
                        instance.save(update_fields=['plano_localizacion'])
                    # El plano nuevo ya esta en S3 (o se quito): recien ahora se limpia el
                    # anterior, y solo si era exclusivo de este contrato (los viejos estan
                    # compartidos: borrarlos deja sin plano a los otros que apuntan al mismo).
                    if plano_anterior and plano_anterior != str(instance.plano_localizacion or ''):
                        if plano_es_exclusivo(plano_anterior, instance.id):
                            eliminar_archivo_s3(plano_anterior)
                    # proceso.contador = proceso.contador - 1
                    # proceso.save()
                    print("edito proceso contrato")
                    send_noti_varios(FraternaContratos, request, title="Se a modificado el contrato de:", text=f"FRATERNA VS {instance.residente.nombre_arrendatario} - {instance.residente.nombre_residente}".upper(), url = f"fraterna/contrato/#{instance.residente.id}_{instance.cama}_{instance.no_depa}")
                    return Response(serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response({'errors': serializer.errors})
            else:
                return Response({'msj': 'LLegaste al limite de tus modificaciones en el proceso'}, status=status.HTTP_205_RESET_CONTENT)
      
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy(self,request, *args, **kwargs):
        try:
            residente = self.get_object()
            if es_usuario_demo(request.user) and not contrato_es_del_usuario(request.user, residente):
                return Response(
                    {'error': 'Cuenta de demostración: solo puedes eliminar contratos creados por ti.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if residente:
                residente.delete()
                return Response({'message': 'residente eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def aprobar_contrato(self, request, *args, **kwargs):
        try:
            print("update status contrato")
            print("Request",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("mi id es: ",instance.id)
            print(instance.__dict__)
            # Candado rol_interno (2026-08-04): aprobar es exclusivo del equipo
            # Arrendify; excepción: cuenta demo sobre sus propios contratos.
            if not es_operador_arrendify(request.user) and not (
                    es_usuario_demo(request.user)
                    and contrato_es_del_usuario(request.user, instance)):
                return Response(
                    {'error': 'Solo el equipo Arrendify puede aprobar contratos.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def desaprobar_contrato(self, request, *args, **kwargs):
        try:
            print("desaprobar Contrato")
            instance = self.queryset.get(id = request.data["id"])
            # Candado rol_interno (2026-08-04): desaprobar es exclusivo del equipo
            # Arrendify; excepción: cuenta demo sobre sus propios contratos.
            if not es_operador_arrendify(request.user) and not (
                    es_usuario_demo(request.user)
                    and contrato_es_del_usuario(request.user, instance)):
                return Response(
                    {'error': 'Solo el equipo Arrendify puede desaprobar contratos.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = "En Revisión"
            proceso.contador = 2 # en vista que me indiquen lo contrario lo dejamos asi
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a desaprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)

    def _guard_solo_arrendify_o_aprobado(self, request, contrato_id):
        """Candado rol_interno (2026-08-04): fuera del equipo Arrendify, emitir o
        resetear enlaces de firma exige que el contrato esté Aprobado. Devuelve
        la Response 403 o None (el equipo Arrendify pasa siempre)."""
        if es_operador_arrendify(request.user):
            return None
        if not ProcesoContrato.objects.filter(
                contrato_id=contrato_id, status_proceso='Aprobado').exists():
            return Response(
                {'error': 'El contrato debe estar Aprobado para generar o '
                          'resetear enlaces de firma.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def _soft_delete_docs_zapsign(self, tokens):
        """Soft-delete de documentos en ZapSign (`DELETE docs/{token}/`), best-effort.

        ZapSign lo documenta como soft delete: el doc deja de ser firmable/visible
        para los firmantes pero sigue en su BD y accesible por API (deleted=true),
        asi que el rastro de una ronda cancelada sigue siendo consultable. Un fallo
        aqui NO tumba el reinicio local: se loggea y se continua (el token viejo ya
        no empareja con nada en el webhook). Devuelve {token: bool}.
        """
        resultados = {}
        headers = {'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'}
        for doc_token in (tokens or ()):
            if not doc_token:
                continue
            try:
                r = requests.delete(f'{API_URL_ZAPSIGN}docs/{doc_token}/', headers=headers, timeout=10)
                resultados[doc_token] = bool(r.ok)
                if not r.ok:
                    logger.error(f"{datetime.now()} soft-delete en ZapSign fallo para el doc {doc_token}: {r.status_code} {r.text[:200]}")
            except Exception as e:
                resultados[doc_token] = False
                logger.error(f"{datetime.now()} soft-delete en ZapSign excepcion para el doc {doc_token}: {e}")
        return resultados

    def ver_documento_firma(self, request, *args, **kwargs):
        """"Ver contrato" del Historial mientras el doc sigue en firma.

        Redirige a la MEJOR version que tenga ZapSign en este momento:
        `signed_file` existe desde la PRIMERA firma (el PDF parcialmente firmado,
        comprobado 2026-07-17 con el doc del 839 en `pending`) y si aun no hay
        ninguna cae a `original_file` (el PDF enviado). Se consulta EN VIVO en
        cada click porque esas URLs de ZapSign expiran. OJO: la ruta publica
        `app.zapsign.co/verificar/{token}` espera el token del FIRMANTE, no el
        del documento (con doc_token da "Documento no encontrado") — por eso
        este redirect. El PDF definitivo (4 firmas) NO pasa por aqui: se sirve
        directo de nuestro S3 (`pdf_firmado_N`).
        """
        try:
            doc_token = (request.query_params.get('token') or '').strip()
            if not doc_token:
                return Response({'error': 'Falta token'}, status=status.HTTP_400_BAD_REQUEST)
            r = requests.get(f'{API_URL_ZAPSIGN}docs/{doc_token}/',
                             headers={'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'},
                             timeout=20)
            if not r.ok:
                return Response({'error': 'ZapSign no encontro el documento.'},
                                status=status.HTTP_404_NOT_FOUND)
            doc = r.json()
            url = doc.get('signed_file') or doc.get('original_file')
            if not url:
                return Response({'error': 'El documento aun no tiene archivo disponible.'},
                                status=status.HTTP_404_NOT_FOUND)
            return HttpResponseRedirect(url)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def resetear_firmas(self, request, *args, **kwargs):
        """Reinicia los enlaces de firma de un contrato Fraterna.

        Con bitacora: cierra la ronda 'pendiente' como 'cancelado' (motivo/usuario/
        cerrado_en, via `_cancelar_ronda_pendiente`). La ronda cancelada conserva
        tokens, snapshot y estado por firmante, asi que REEMPLAZA al INSERT en
        `FraternaFirmaHistorial` (esa tabla queda congelada como historial legacy).
        Sin ronda 'pendiente' (contratos de antes de la bitacora, o cuya ultima
        ronda ya quedo 'firmado'), se mantiene el snapshot viejo al historial.

        `alcance` (opcional en el payload): 'todo' (default) o 'paquete_2'.

        - 'todo': ademas de lo anterior, limpia los tokens/estados (a NULL) en el
          contrato para que se puedan generar enlaces nuevos por el flujo normal
          (Generar Firmas Paquete 1; si la ultima ronda quedo 'firmado', la
          siguiente generacion abre una ronda tipo 'renovacion').
        - 'paquete_2': cancela SOLO el envio del Paquete 2 del intento vivo. La
          ronda sigue 'pendiente' (mismo numero) y el Paquete 1 y sus firmas se
          conservan: limpia token_2/estado_firma_2 + espejo de firmantes P2 +
          token_paquete_2/estado del contrato. Con eso la asignacion (tier P2)
          vuelve a ser editable y el P2 se puede regenerar en el mismo intento.

        Se limpia `estado_firma_paquete_*` JUNTO con cada token: asi una firma del
        documento viejo no puede disparar la ocupacion de cama del webhook
        (`zapsign_webhook.py`, que la activa cuando AMBOS paquetes quedan 'signed').
        NO toca `cama_ref` ni `estado_contrato`: una cama ya ocupada se queda igual.
        Los documentos viejos se SOFT-DELETEAN en ZapSign (dejan de ser firmables;
        siguen en su BD y accesibles por API, junto al rastro de la ronda cancelada
        o el historial legacy) — EXCEPTO los que ya quedaron 'signed' a nivel
        documento Y los de cualquier ronda 'firmado' (cierre por partes: el doc del
        termino vigente puede seguir 'pending' porque faltan los finales; se
        conserva como respaldo legal y para que Fraterna/Jonathan firmen despues).
        """
        try:
            bloqueo_demo = self._guard_demo(request, request.data.get("id"))
            if bloqueo_demo:
                return bloqueo_demo
            instance = self.queryset.get(id=request.data["id"])
            candado_rol = self._guard_solo_arrendify_o_aprobado(request, instance.id)
            if candado_rol:
                return candado_rol
            alcance = str(request.data.get('alcance') or 'todo').strip().lower()
            if alcance not in ('todo', 'paquete_2'):
                return Response(
                    {'error': "Alcance invalido (usa 'todo' o 'paquete_2')."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Contrato VIGENTE sin renovacion en curso: sus firmas respaldan el
            # termino actual y NO se retiran (ni 'todo' ni 'paquete_2'). Con una
            # renovacion en curso el reset si aplica: cancela SOLO la ronda
            # 'pendiente' (los docs de la 'firmado' ya estan protegidos abajo).
            if self._vigente_sellado(instance):
                return Response(
                    {'error': 'El contrato esta sellado (su termino esta firmado): '
                              'sus firmas no se pueden retirar. Para cambios usa '
                              '"Renovar contrato".'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ronda_abierta = instance.rondas_firma.filter(estado='pendiente').first()

            try:
                usuario = (getattr(request.user, 'email', '') or
                           getattr(request.user, 'username', '') or '')
            except Exception:
                usuario = ''
            motivo = (str(request.data.get('motivo') or '').strip() or None)

            # Solo se soft-deletea lo NO firmado: un doc 'signed' es respaldo legal
            # (p.ej. reset de un contrato ya firmado para renovarlo) y borrarlo en
            # ZapSign solo quitaria acceso al PDF firmado sin proteger nada.
            # Igual de protegidos: los docs de cualquier ronda 'firmado' — la ronda
            # cierra cuando firman las PARTES, asi que su doc puede seguir 'pending'
            # a nivel documento (faltan Fraterna/Jonathan); borrarlo al renovar
            # mataria los enlaces que los finales firman despues via el Historial.
            tokens_protegidos = set()
            for r in instance.rondas_firma.filter(estado__in=('firmado', 'expirado')):
                tokens_protegidos.update(t for t in (r.token_1, r.token_2) if t)

            def _borrable(token, estado_firma):
                return (bool(token) and estado_firma != 'signed'
                        and token not in tokens_protegidos)

            if alcance == 'paquete_2':
                token_p2_ronda = (ronda_abierta.token_2 if ronda_abierta else None)
                if not (token_p2_ronda or instance.token_paquete_2):
                    return Response(
                        {'error': 'Este contrato no tiene Paquete 2 en proceso de firma.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                tokens_borrar = set()
                if _borrable(token_p2_ronda, (ronda_abierta.estado_firma_2 if ronda_abierta else None)):
                    tokens_borrar.add(token_p2_ronda)
                if _borrable(instance.token_paquete_2, instance.estado_firma_paquete_2):
                    tokens_borrar.add(instance.token_paquete_2)
                with transaction.atomic():
                    if ronda_abierta:
                        # Revertir el congelado al estado del P1: al generar P2 el
                        # snapshot/fechas se RE-congelan; si el P2 se cancela, la
                        # ronda debe volver a reflejar lo que imprimio el P1 -> se
                        # deshace `_delta_p2` (campo a campo, columnas de fecha
                        # incluidas) y el delta desaparece del snapshot.
                        snapshot = dict(ronda_abierta.datos_snapshot or {})
                        delta_p2 = snapshot.pop('_delta_p2', None) or {}
                        campos_update = ['token_2', 'estado_firma_2', 'datos_snapshot']
                        for campo, par in delta_p2.items():
                            antes = par[0] if isinstance(par, (list, tuple)) and par else None
                            if campo in self.RONDA_CAMPOS_FECHA:
                                setattr(ronda_abierta, campo,
                                        datetime.strptime(antes, '%Y-%m-%d').date() if antes else None)
                                campos_update.append(campo)
                            else:
                                snapshot[campo] = antes
                        ronda_abierta.datos_snapshot = snapshot
                        ronda_abierta.token_2 = None
                        ronda_abierta.estado_firma_2 = None
                        ronda_abierta.save(update_fields=campos_update)
                        ronda_abierta.firmantes.filter(paquete=2).delete()
                    instance.token_paquete_2 = None
                    instance.estado_firma_paquete_2 = None
                    instance.save(update_fields=['token_paquete_2', 'estado_firma_paquete_2'])
                borrados = self._soft_delete_docs_zapsign(tokens_borrar)
                return Response(
                    {
                        'Exito': 'Paquete 2 cancelado; el Paquete 1 y sus firmas se conservan.',
                        'paquete_2_cancelado': True,
                        'ronda': (ronda_abierta.numero if ronda_abierta else None),
                        'docs_zapsign': borrados,
                    },
                    status=status.HTTP_200_OK,
                )

            # alcance == 'todo'
            # Nada que reiniciar si no hay enlaces NI ronda abierta. (En pruebas con
            # persistir_token=False el token vive SOLO en la ronda, no en el contrato.)
            if not (instance.token or instance.token_paquete_2 or ronda_abierta):
                return Response(
                    {'error': 'Este contrato no tiene enlaces de firma generados.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            tokens_borrar = set()
            if _borrable(instance.token, instance.estado_firma_paquete_1):
                tokens_borrar.add(instance.token)
            if _borrable(instance.token_paquete_2, instance.estado_firma_paquete_2):
                tokens_borrar.add(instance.token_paquete_2)
            if ronda_abierta:
                if _borrable(ronda_abierta.token_1, ronda_abierta.estado_firma_1):
                    tokens_borrar.add(ronda_abierta.token_1)
                if _borrable(ronda_abierta.token_2, ronda_abierta.estado_firma_2):
                    tokens_borrar.add(ronda_abierta.token_2)

            with transaction.atomic():
                ronda = self._cancelar_ronda_pendiente(
                    instance, motivo=motivo, usuario=(usuario or None),
                )
                if ronda is None and (instance.token or instance.token_paquete_2):
                    # Flujo viejo (nada que cancelar en la bitacora): snapshot de los
                    # tokens/estados al historial antes de limpiarlos.
                    FraternaFirmaHistorial.objects.create(
                        contrato=instance,
                        token_1_viejo=instance.token,
                        estado_firma_1_viejo=instance.estado_firma_paquete_1,
                        token_2_viejo=instance.token_paquete_2,
                        estado_firma_2_viejo=instance.estado_firma_paquete_2,
                        motivo=motivo,
                        usuario=(usuario or None),
                    )
                instance.token = None
                instance.token_paquete_2 = None
                instance.estado_firma_paquete_1 = None
                instance.estado_firma_paquete_2 = None
                instance.save(update_fields=[
                    'token', 'token_paquete_2',
                    'estado_firma_paquete_1', 'estado_firma_paquete_2',
                ])

            borrados = self._soft_delete_docs_zapsign(tokens_borrar)
            return Response(
                {
                    'Exito': 'Enlaces de firma reiniciados; los anteriores quedaron en la bitacora.',
                    'ronda_cancelada': (ronda.numero if ronda else None),
                    'docs_zapsign': borrados,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def iniciar_renovacion(self, request, *args, **kwargs):
        """Abre la renovacion de un contrato con termino firmado (la salida del sellado).

        Crea la ronda tipo 'renovacion' en 'pendiente' con las fechas/snapshot
        actuales como punto de partida (SIN tokens: los documentos se emiten
        despues con "Generar Firmas Paquete 1", que REUTILIZA esta misma ronda)
        y limpia los tokens/estados espejados en el contrato para el ciclo nuevo.
        Los docs de la ronda 'firmado' NO se tocan en ZapSign: son el respaldo
        legal del termino vigente y ahi siguen firmando los finales. Con la
        ronda abierta el contrato deja de estar sellado: fechas/renta se editan
        libremente hasta generar el P1 (candados por token de siempre). Aplica a
        contratos 'actual' (sellados), 'expirado' (vencidos por el job) y legacy
        con termino firmado sin bitacora.
        """
        try:
            instance = self.queryset.get(id=request.data["id"])
            candado_rol = self._guard_solo_arrendify_o_aprobado(request, instance.id)
            if candado_rol:
                return candado_rol
            tuvo_termino = (getattr(instance, 'estado_contrato', None) in ('actual', 'expirado')
                            or instance.rondas_firma.filter(estado__in=('firmado', 'expirado')).exists())
            if not tuvo_termino:
                return Response(
                    {'error': 'Este contrato aun no tiene un termino firmado que '
                              'renovar; usa el flujo normal de firma.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if instance.rondas_firma.filter(estado='pendiente').exists():
                return Response(
                    {'error': 'Ya hay un proceso de firma en curso para este '
                              'contrato; termina o cancela ese intento primero.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                usuario = (getattr(request.user, 'email', '') or
                           getattr(request.user, 'username', '') or '') or None
            except Exception:
                usuario = None
            motivo = (str(request.data.get('motivo') or '').strip() or 'renovación')

            with transaction.atomic():
                if ((instance.token or instance.token_paquete_2)
                        and not instance.rondas_firma.exists()):
                    # Legacy sin bitacora: snapshot de los tokens al historial viejo
                    # antes de limpiarlos (mismo criterio que resetear_firmas).
                    FraternaFirmaHistorial.objects.create(
                        contrato=instance,
                        token_1_viejo=instance.token,
                        estado_firma_1_viejo=instance.estado_firma_paquete_1,
                        token_2_viejo=instance.token_paquete_2,
                        estado_firma_2_viejo=instance.estado_firma_paquete_2,
                        motivo=motivo,
                        usuario=usuario,
                    )
                # El termino en pie (ronda 'firmado') pasa a 'expirado': queda como una
                # renovacion mas en el historial (su espejo/PDF/snapshot se conservan
                # intactos) y libera el indice unico parcial 'una firmado por contrato'.
                # NO se crea una ronda nueva aqui: la ronda de renovacion se materializa
                # hasta "Generar Firmas Paquete 1" (upsert-reuse crea numero=max+1 con
                # tipo='renovacion' porque el contrato ya tuvo un termino 'expirado').
                # Asi el conteo de renovaciones = las rondas 'expirado' del historial,
                # sin rondas 'pendiente' fantasma por cada click de "Renovar".
                (instance.rondas_firma
                 .filter(estado='firmado')
                 .update(estado='expirado',
                         motivo='termino reemplazado por renovacion manual',
                         cerrado_en=timezone.now()))
                # Contrato entra en 'en_renovacion' (pill del FE) y limpia el espejo de
                # tokens para el ciclo nuevo. Los tokens viejos quedan en su ronda ya
                # 'expirado' (consultables; en ZapSign NO se tocan: los finales aun
                # pueden firmar el termino anterior desde el Historial).
                instance.estado_contrato = 'en_renovacion'
                instance.token = None
                instance.token_paquete_2 = None
                instance.estado_firma_paquete_1 = None
                instance.estado_firma_paquete_2 = None
                instance.save(update_fields=[
                    'estado_contrato', 'token', 'token_paquete_2',
                    'estado_firma_paquete_1', 'estado_firma_paquete_2',
                ])
            return Response(
                {
                    'Exito': 'Renovacion iniciada: actualiza los datos del contrato '
                             'y genera el Paquete 1.',
                    'estado_contrato': 'en_renovacion',
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def generar_pagare(self, request, *args, **kwargs):
        """Descarga el PDF de pagarés. Lee `pagare_distinto` y `cantidad_primer_pagare`
        del propio modelo (capturados en el form de creación/edición del contrato)."""
        try:
            print("Generar Pagare Fraterna")
            locale.setlocale(locale.LC_ALL, "es_MX.utf8")
            data = request.data
            id_paq = data["id"] if isinstance(data, dict) else data

            info = self.queryset.filter(id=id_paq).first()
            if not info:
                return Response({'error': 'Contrato no encontrado'}, status=status.HTTP_404_NOT_FOUND)

            # `_generar_pagare_interno` lee `pagare_distinto` y `cantidad_primer_pagare` del modelo
            pdf_file = self._generar_pagare_interno(info, marca=marca_para(request.user))

            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            return HttpResponse(response, content_type='application/pdf')

        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def generar_poliza(self, request, *args, **kwargs):
        try:
            print("Generar Poliza Fraterna")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)

            #vamos a genenrar el numero de contrato
            arrendatario = info.residente.nombre_arrendatario
            primera_letra = arrendatario[0].upper()  # Obtiene la primera letra
            ultima_letra = arrendatario[-1].upper()  # Obtiene la última letra

            year = info.fecha_celebracion.strftime("%g")
            month = info.fecha_celebracion.strftime("%m")
            
            nom_contrato = f"AFY{month}{year}CX51{info.id}CA{primera_letra}{ultima_letra}"  
            print("Nombre del contrato", nom_contrato)     
            #obtenemos renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
       
            context = {'info': info, 'renta_texto':renta_texto, 'nom_contrato':nom_contrato, **(marca_para(request.user) or {})}
            template = 'home/poliza_fraterna.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO POLIZA")
            return HttpResponse(response, content_type='application/pdf')
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_contrato(self, request, *args, **kwargs):
        try:
            print("Generar contrato Fraterna")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)
            context = contexto_contrato_fraterna(info, request.user)
            html_string = render_to_string(plantilla_contrato_fraterna(), context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO CONTRATO")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST) 
        
    def generar_comodato(self, request, *args, **kwargs):
        try:
            print("Generar comodato Fraterna")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)
            #obtenermos la duracion para pasarla a letra
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            duracion_texto = num2words(duracion_meses, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            #obtenemos renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
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
            
            inventario = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.png"
            }
            
            tipologia = info.tipologia
            plano = ""
            tabla_inventario = ""
            if tipologia in opciones and tipologia in inventario:
                plano = opciones[tipologia]
                tabla_inventario = inventario[tipologia]
                print(f"Tu Tipologia es: {tipologia}, URL: {plano}")
                print(f"Tu Tipologia es: {tipologia}, Inventario: {tabla_inventario}")
            
            #obtener la url de el plano que sube fraterna
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
           
            context = {'info': info, 'duracion_meses':duracion_meses, 'duracion_texto':duracion_texto, 'renta_texto':renta_texto, 'plano':plano, 'plan_loc':plan_loc, 'tabla_inventario':tabla_inventario, **(marca_para(request.user) or {})}
            template = 'home/comodato_fraterna.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO CONTRATO")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST) 
    
    def _generar_paquete_fraterna_pdf(self, id_paq, pagare_distinto=None, cantidad_pagare=None, marca=None):
        """
        Paquete COMPLETO = Paquete 1 + Paquete 2 concatenados.

        Orden final del PDF:
            Paquete 1: Contrato → Manual UTO → Pagarés
            Paquete 2: Comodato → Anexos → Póliza

        `marca`: contexto de marca blanca (cuentas demo); None = Fraterna normal.
        Devuelve: (nombre_archivo, bytes del PDF combinado, total_paginas)
        """
        _, pdf_p1, total_p1 = self._generar_paquete_1_pdf(id_paq, pagare_distinto, cantidad_pagare, marca=marca)
        _, pdf_p2, total_p2 = self._generar_paquete_2_pdf(id_paq, marca=marca)

        pdf_writer = PdfWriter()
        for page in PdfReader(io.BytesIO(pdf_p1)).pages:
            pdf_writer.add_page(page)
        for page in PdfReader(io.BytesIO(pdf_p2)).pages:
            pdf_writer.add_page(page)

        output_pdf = io.BytesIO()
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)

        info = self.queryset.filter(id=id_paq).first()
        nombre_inquilino = info.residente.nombre_arrendatario if info and info.residente else "contrato"
        fecha_actual = dt.now().strftime("%Y%m%d_%H%M%S")
        marca_slug = (marca or {}).get('marca_slug', 'Fraterna')
        nombre_archivo = f"Paquete_Completo_{marca_slug}_{nombre_inquilino}_{fecha_actual}.pdf"
        total_paginas = {**total_p1, **total_p2}
        return nombre_archivo, output_pdf.getvalue(), total_paginas

    def _generar_paquete_fraterna_pdf_legacy(self, id_paq, pagare_distinto="No", cantidad_pagare="0"):
        """LEGACY (no usado por el endpoint actual). Versión antigua del paquete combinado.
        Se mantiene por si se requiere el orden viejo (Comodato + Contrato + Manual + Póliza + Pagarés)."""
        # Guardar el registro de paginas totales para usar en coordenadas de firmantes
        total_paginas = {
            "comodato": 0,
            "arrendamiento": 0,
            "manual": 0,
            "poliza": 0,
            "pagares": 0,
        }

        print("Generando paquete PDF para Fraterna...")
        locale.setlocale(locale.LC_ALL, "es_MX.utf8")

        # Obtener información del contrato
        info = self.queryset.filter(id=id_paq).first()
        if not info:
            raise ValueError("Contrato no encontrado")

        pdf_writer = PdfWriter()

        # 1. Comodato
        print("Generando Comodato...")
        comodato_pdf = self._generar_comodato_interno(info)
        comodato_reader = PdfReader(io.BytesIO(comodato_pdf))
        total_paginas["comodato"] = len(comodato_reader.pages)
        for page in comodato_reader.pages:
            pdf_writer.add_page(page)

        # 2. Contrato
        print("Generando Contrato...")
        contrato_pdf = self._generar_contrato_interno(info)
        contrato_reader = PdfReader(io.BytesIO(contrato_pdf))
        total_paginas["arrendamiento"] = len(contrato_reader.pages)
        for page in contrato_reader.pages:
            pdf_writer.add_page(page)

        # 3. Manual UTO desde AWS
        print("Descargando Manual UTO desde AWS...")
        manual_url = "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/ManualUtower.pdf"
        try:
            response_manual = requests.get(manual_url, timeout=30)
            response_manual.raise_for_status()
            manual_reader = PdfReader(io.BytesIO(response_manual.content))
            total_paginas["manual"] = len(manual_reader.pages)
            for page in manual_reader.pages:
                pdf_writer.add_page(page)
            print("Manual UTO agregado exitosamente")
        except Exception as e:
            print(f"Error al descargar manual UTO: {e}")

        # 4. Póliza
        print("Generando Póliza...")
        poliza_pdf = self._generar_poliza_interno(info)
        poliza_reader = PdfReader(io.BytesIO(poliza_pdf))
        total_paginas["poliza"] = len(poliza_reader.pages)
        for page in poliza_reader.pages:
            pdf_writer.add_page(page)

        # 5. Pagarés
        print("Generando Pagarés...")
        pagare_pdf = self._generar_pagare_interno(info, pagare_distinto, cantidad_pagare)
        pagare_reader = PdfReader(io.BytesIO(pagare_pdf))
        total_paginas["pagares"] = len(pagare_reader.pages)
        for page in pagare_reader.pages:
            pdf_writer.add_page(page)

        # PDF final
        output_pdf = io.BytesIO()
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)

        # Nombre con fecha
        fecha_actual = dt.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"Paquete_Completo_Fraterna_{info.residente.nombre_arrendatario}_{fecha_actual}.pdf"

        return nombre_archivo, output_pdf.getvalue(), total_paginas


    def build_payload_to_zapsign(self, contrato_data, marca=None):
        """ Datos del contrado: contrato_data = {"id", "filename", "base64_pfd", "residente"}
            Aquí armamos el payload que se va enviar para la solicitud
            de creacion del documento

            `marca`: contexto de marca blanca (cuentas demo). Con marca demo, el
            payload sale en sandbox, con firmante 1/testigo ficticios y todos
            los correos redirigidos al usuario demo (ver demo_mode.py).
        """
        data = contrato_data
        singer = data["residente"]
        brand_logo = "https://pagosprueba.s3.us-east-1.amazonaws.com/ZapSign/logo-contratodearrendamiento.webp"

        payload = {
            # Documento REAL (consume créditos y vale como firma). Las cuentas demo
            # lo pasan a sandbox por su cuenta en `aplicar_demo_a_payload_zapsign`
            # (demo_mode.py) — no cambiar esto para probar: usar una cuenta demo.
            "sandbox": False,
            "name": data["filename"],                                          # Nombre del documento que verá el usuario
            "base64_pdf": data["base64_pfd"],                                  # PDF codificado en base64 (sin encabezado data:...)
            "external_id": data["id"],                                         # ID opcional para enlazar con sistema externo

            "signers": [  # Lista de personas que deben firmar
                # NOTA: signature_placement / rubrica_placement permiten posicionar firmas mediante anchors
                # `<<tag>>` impresos (en color blanco) en el HTML del documento. Ver doc:
                # https://docs.zapsign.com.br/english/signatarios/adicionar-signatario
                # Los tags se aplican al documento completo; si NO existen en el PDF, ZapSign cae al
                # método tradicional via `place-signatures` (coordenadas) que sigue activo para Manual UTO y otras secciones.
                {
                    "name": "FRATERNA ADMINISTRADORA DE PROYECTOS, S.A. DE C.V.'' REPRESENTADA POR ALMA GABRIELA GRANADOS CASTILLO",
                    "phone_country": "52",
                    "signature_placement": "<<firma_fraterna>>",
                    "rubrica_placement": "<<rubrica_fraterna>>",
                },
                {
                    "name": singer["nombre_arrendatario"],
                    "email": singer["correo_arrendatario"],
                    "phone_country": "52",
                    "phone_number": singer["celular_arrendatario"],
                    "send_automatic_email": True,
                    "send_automatic_whatsapp": False,
                    "signature_placement": "<<firma_arrendatario>>",
                    "rubrica_placement": "<<rubrica_arrendatario>>",
                },
                {
                    "name": singer["nombre_residente"],
                    "email": singer["correo_residente"],
                    "phone_country": "52",
                    "phone_number": singer["celular_residente"],
                    "send_automatic_email": True,
                    "send_automatic_whatsapp": False,
                    "signature_placement": "<<firma_residente>>",
                    "rubrica_placement": "<<rubrica_residente>>",
                },
                {
                    "name": "JONATHAN GUADARRAMA SALGADO",
                    "email": "genaro.guadarrama@arrendify.com",
                    "phone_country": "52",
                    "phone_number": "5531398629",
                    "send_automatic_email": True,
                    "signature_placement": "<<firma_testigo>>",
                    "rubrica_placement": "<<rubrica_testigo>>",
                }
                # Campos extras para el firmante, consultar documentación, 
                # ya que algunos tienen costos extra
                # {
                #     "name": "Uriel Aguilar Ortega",                          # Nombre del firmante
                #     "email": "desarrolloewmx2024@gmail.com",                 # Email al que se enviará solicitud de firma
                #     "auth_mode": "assinaturaTela",                           # Tipo de autenticación (pantalla sin verificación extra)
                #     "send_automatic_email": True,                            # Enviar correo automáticamente
                #     "send_automatic_whatsapp": False,                        # Enviar WhatsApp automáticamente (si hay teléfono)
                #     "order_group": None,                                     # Agrupación para firmar por orden (si se activa)
                #     "custom_message": "",                                    # Mensaje personalizado en correo de firma
                #     "phone_country": "52",                                   # Código de país (México = 52)
                #     "lock_email": False,                                     # Evita que edite su correo en la pantalla de firma
                #     "blank_email": False,                                    # Oculta email en la interfaz
                #     "hide_email": False,                                     # Oculta completamente el campo email
                #     "lock_phone": False,                                     # Bloquea el número telefónico
                #     "blank_phone": False,                                    # Oculta teléfono en la interfaz
                #     "hide_phone": False,                                     # Oculta completamente el campo teléfono
                #     "lock_name": False,                                      # Bloquea el nombre (no editable)
                #     "require_cpf": False,                                    # Exigir CPF (solo Brasil)
                #     "cpf": "",                                               # Número de CPF (si se requiere)
                #     #"require_selfie_photo": True,                            # Solicita selfie al firmar
                #     "require_document_photo": True,                          # Solicita foto de documento (INE, pasaporte)
                #     "selfie_validation_type": "liveness-document-match",     # Tipo de validación de selfie (verifica con documento)
                #     "selfie_photo_url": "",                                  # URL opcional de la selfie previa
                #     "document_photo_url": "",                                # URL de la foto del documento frontal
                #     "document_verse_photo_url": "",                          # URL del reverso del documento (si aplica)
                #     "qualification": "",                                     # Cargo o rol (opcional, visible en certificado)
                #     "external_id": "",                                       # ID externo único para este firmante
                #     "redirect_link": ""                                      # URL de redirección post-firma (opcional)
                # }
            ],

            "lang": "es",                                                    # Idioma del documento e interfaz de firma
            "disable_signer_emails": False,                                  # Desactiva todos los correos a firmantes
            "brand_logo": brand_logo,                                        # URL del logotipo de tu marca
            "brand_primary_color": "#672584",                                # Color primario (hex) de tu marca
            "brand_name": "Arrendify",                                       # Nombre de la marca que aparece en la firma
            "folder_path": "/FRATERNA",                                      # Carpeta donde se guarda el documento
            "created_by": "juridico.arrendify1@gmail.com",                    # Email del creador del documento
            #"date_limit_to_sign": "2025-07-18T17:45:00.000000Z",             # Fecha límite para firmar el documento
            "signature_order_active": False,                                 # Requiere que los firmantes firmen en orden
            # "observers": [                                                   # Lista de emails que solo observarán el proceso
            #     "urielaguilarortega@gmail.com",
            #     "desarrolloweb.ewmx@gmail.com"
            # ],
            "reminder_every_n_days": 0,                                      # Intervalo de recordatorios automáticos (0 = sin recordatorios)
            "allow_refuse_signature": True,                                  # Permite al firmante rechazar la firma
            "disable_signers_get_original_file": False                       # Bloquea que los firmantes descarguen el documento final
        }

        return aplicar_demo_a_payload_zapsign(payload, marca)

    def armar_payload_posiciones_firma(self, signer_tokens, total_paginas, residente):
        rubricas = []

        # Calcular offsets por sección
        offsets = {}
        acumulador = 0
        for nombre, paginas in total_paginas.items():
            offsets[nombre] = acumulador
            acumulador += paginas

        # Definir posiciones por sección
        posiciones_por_seccion = {
            "comodato": [
                (0, 1.5, 5.0, 0),
                (0, 1.5, 75.0, 1),
                (1, 13.0, 18.0, 0),
                (1, 13.0, 65.0, 1),
                (2, 5.0, 75.0, 1),
                (3, 26.5, 18.0, 1)
            ],
            "arrendamiento": [],
            "manual": [],
            "poliza": [],
            "pagares": []
        }

        # ARRRENDAMIENTO: [0, 1, 2] en cada página (izq-centro-der)
        arr_total = total_paginas["arrendamiento"]
        for i in range(arr_total):
            posiciones_por_seccion["arrendamiento"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 2)
            ])

        # MANUAL: [1, 2] más separados en la parte baja derecha
        man_total = total_paginas["manual"]
        for i in range(man_total):
            posiciones_por_seccion["manual"].extend([
                (i, 5.0, 55.0, 1),
                (i, 5.0, 80.0, 2)
            ])

        # POLIZA: [0, 1, 3] (izq-centro-der)
        pol_total = total_paginas["poliza"]
        for i in range(pol_total):
            posiciones_por_seccion["poliza"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 3)
            ])

        # PAGARES: firmantes condicionales según residente.aval y edad
        pag_total = total_paginas["pagares"]

        aval = residente.get("aval", "").strip()
        edad = int(residente.get("edad", 0))

        for i in range(pag_total):
            # Firmante 2 (residente) siempre firma
            posiciones_por_seccion["pagares"].append((i, 16.0, 55.0, 2))

            # Si la condición se cumple, también firma el firmante 1 (arrendatario)
            if aval == "Si" and edad >= 18:
                posiciones_por_seccion["pagares"].append((i, 33.0, 55.0, 1))

        # Construcción final del payload con offset aplicado
        for seccion, posiciones in posiciones_por_seccion.items():
            offset = offsets[seccion]
            for page, bottom, left, signer_index in posiciones:
                if signer_index < len(signer_tokens):
                    rubricas.append({
                        "page": page + offset,
                        "relative_position_bottom": bottom,
                        "relative_position_left": left,
                        "relative_size_x": 19.55,
                        "relative_size_y": 9.42,
                        "type": "signature",
                        "signer_token": signer_tokens[signer_index]
                    })

        return {"rubricas": rubricas}


    def subir_documento_a_zapsign(self, contrato_data, marca=None):
        # Armar payload para subir documento
        payload = self.build_payload_to_zapsign(contrato_data, marca=marca)

        headers = {
            'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}',
            'Content-Type': 'application/json'
        }
        print("Solicitando documento a Zapsign")

        url = f'{API_URL_ZAPSIGN}docs/'

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()

            try:
                response_data = response.json()
            except ValueError:
                print("⚠️ La respuesta no está en formato JSON.")
                response_data = {"raw_response": response.text}

            # Extraer token del documento
            doc_token = response_data.get("token")

            # Extraer tokens de firmantes
            signer_tokens = [s.get("token") for s in response_data.get("signers", []) if s.get("token")]

            if not doc_token:
                raise ValueError("No se pudo obtener el token del documento desde la respuesta.")

            print("Token del documento generado:", doc_token)
            print("ID del contrato que se va a actualizar:", contrato_data["id"])

            # Guardar token en la base de datos
            info = self.queryset.filter(id=contrato_data["id"]).first()
            if not info:
                raise ValueError("Contrato no encontrado en la base de datos.")

            info.token = doc_token
            info.save()
            print("Token guardado exitosamente en la base de datos.")            

            # Armar y enviar payload de rubricas
            rubricas_payload = self.armar_payload_posiciones_firma(signer_tokens, contrato_data["total_paginas"], contrato_data["residente"])
            posicionar_url = f'{API_URL_ZAPSIGN}docs/{doc_token}/place-signatures/'
            print("📤 Enviando posiciones de firmas...")

            posicionar_response = requests.post(
                posicionar_url,
                headers=headers,
                json=rubricas_payload,
                timeout=60
            )

            posicionar_response.raise_for_status()
            print("Posiciones de firmas configuradas correctamente.")

            return {
                "payload": payload,
                "doc_token": doc_token,
                "zapsign_new_doc": response_data,
                "rubricas_payload": rubricas_payload,
                "rubricas_response": posicionar_response.text or "Sin contenido"
            }

        except requests.exceptions.Timeout:
            print("Error: Tiempo de espera agotado al comunicar con ZapSign.")
        except requests.exceptions.RequestException as e:
            print(f"Error en la solicitud a Zap-Sign: {e}")
        except Exception as e:
            print(f"Error inesperado: {e}")

        return None

    def generar_urls_firma_fraterna(self, request, *args, **kwargs):
        """
        Devuelve el paquete combinado en base64 para uso en proceso de firma
        con la plataforma de zapsign.
        """
        try:
            print("Generando urls zapsign")
            data = request.data
            if isinstance(data, dict):
                id_paq = data["id_contrato"]
                # None = que el generador lea pagare_distinto/cantidad del MODELO
                # (antes el default "No"/"0" pisaba un "Si" guardado cuando el FE
                # no mandaba el campo).
                pagare_distinto = data.get("pagare_distinto") or None
                cantidad_pagare = data.get("cantidad_pagare") or None
            else:
                id_paq = data
                pagare_distinto = None
                cantidad_pagare = None

            
            bloqueo_demo = self._guard_demo(request, id_paq)
            if bloqueo_demo:
                return bloqueo_demo
            candado_rol = self._guard_solo_arrendify_o_aprobado(request, id_paq)
            if candado_rol:
                return candado_rol
            marca = marca_para(request.user)

            # Fix (A) consistencia: firmantes desde la BD (fuente de verdad), no del snapshot del FE.
            info = self.queryset.filter(id=id_paq).first()
            if not info or not info.residente:
                return Response({'error': 'Contrato o residente no encontrado'}, status=status.HTTP_404_NOT_FOUND)
            residente = ResidenteSerializers(info.residente).data

            nombre_archivo, pdf_bytes, total_paginas = self._generar_paquete_fraterna_pdf(id_paq, pagare_distinto, cantidad_pagare, marca=marca)
            base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
            print("Paquete EN BASE 64")

            contrato_data = {
                "id": id_paq,
                "filename": nombre_archivo,
                "base64_pfd": base64_pdf,
                "residente": residente,
                "total_paginas": total_paginas
                }
            #funcion de prueba solicitar documento a zapsign
            resultado = self.subir_documento_a_zapsign(contrato_data, marca=marca)
            return Response({
                "filename": "simula nombre",
                "pdf_base64": "base64_pdfj89d789a8su39889",
                "respuestaZS": resultado
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error en generar_urls_a_firmar_paquete_fraterna: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                        f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def generar_paquete_completo_fraterna(self, request, *args, **kwargs):
        """
        Devuelve el paquete completo (P1 + P2) en formato PDF descargable.
        `pagare_distinto` y `cantidad_primer_pagare` se leen del modelo del contrato.
        """
        try:
            print("Generando paquete completo Fraterna")
            data = request.data
            id_paq = data["id"] if isinstance(data, dict) else data

            nombre_archivo, pdf_bytes, total_paginas = self._generar_paquete_fraterna_pdf(id_paq, marca=marca_para(request.user))

            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
            response.write(pdf_bytes)

            print("Paquete completo generado exitosamente")
            return response

        except Exception as e:
            print(f"Error en generar_paquete_completo_fraterna: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                        f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def mostrar_urls_firma_documento_fraterna(self, request, *args, **kwargs):
        try:
            doc_token = request.data.get("token")
            if not doc_token or not isinstance(doc_token, str):
                return Response({'error': 'Token inválido o no proporcionado.'}, status=status.HTTP_400_BAD_REQUEST)

            print(f"Solicitando documento a Zapsign {API_URL_ZAPSIGN}docs/{doc_token}/")
            url = f'{API_URL_ZAPSIGN}docs/{doc_token}/'
            headers = {'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'}

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                return Response({
                    'error': 'Error al obtener información de ZapSign.',
                    'status_code': response.status_code,
                    'response': response.text
                }, status=response.status_code)

            try:
                response_data = response.json()
            except ValueError:
                return Response({
                    'error': 'La respuesta de ZapSign no es un JSON válido.',
                    'raw_response': response.text
                }, status=status.HTTP_502_BAD_GATEWAY)

            # Validar que existan campos clave
            required_keys = ['name', 'status', 'original_file', 'signed_file', 'signers']
            if not all(k in response_data for k in required_keys):
                return Response({
                    'error': 'Respuesta incompleta de ZapSign.',
                    'received_keys': list(response_data.keys())
                }, status=status.HTTP_502_BAD_GATEWAY)

            return Response(response_data, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException as e:
            logger.error(f"{dt.now()} Error de conexión con ZapSign: {e}")
            return Response({
                'error': 'Error de conexión con ZapSign.',
                'details': str(e)
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Error inesperado en {exc_tb.tb_frame.f_code.co_name} línea {exc_tb.tb_lineno}: {e}")
            return Response({
                'error': 'Error inesperado al procesar la solicitud.',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    

    # =========================================================================
    # NUEVO FLUJO PAQUETE 1 / PAQUETE 2 (Fraterna)
    # Paquete 1: Contrato + Póliza + Pagarés + Manual UTO  (firma primero)
    # Paquete 2: Comodato + Anexos                          (firma después)
    # =========================================================================

    def _generar_anexos_interno(self, info, marca=None):
        """Genera el PDF solo de los anexos (1-6). Usado en Paquete 2."""
        try:
            opciones = {
                'Loft':   "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
                'Twin':   "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
                'Squad':  "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
                'Crew':   "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
                'Party':  "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png",
            }
            inventario = {
                'Loft':   "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.png",
                'Twin':   "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.png",
                'Squad':  "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.png",
                'Crew':   "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.png",
                'Party':  "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.png",
            }
            tipologia = info.tipologia
            plano = opciones.get(tipologia, "")
            tabla_inventario = inventario.get(tipologia, "")
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"

            context = {
                'info': info,
                'plano': plano,
                'plan_loc': plan_loc,
                'tabla_inventario': tabla_inventario,
                **(marca or {}),
            }
            template = 'home/anexos_fraterna_v2.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            return pdf_file
        except Exception as e:
            print(f"Error generando anexos interno: {e}")
            raise e

    def _generar_paquete_1_pdf(self, id_paq, pagare_distinto=None, cantidad_pagare=None, marca=None):
        """Paquete 1 = Contrato + Manual UTO + Pagarés (al final, sin firmas ZapSign).
        La Póliza se movió al Paquete 2 (imprime el nº de departamento, que se asigna
        DESPUÉS del P1; en el P1 salía en blanco/'None'). Ver _generar_paquete_2_pdf.
        `pagare_distinto`/`cantidad_pagare` opcionales: si vienen None se leen del modelo.
        `marca`: contexto de marca blanca (cuentas demo); en demo se OMITE el
        Manual UTO (PDF estático con marca Fraterna) — total_paginas["manual"]=0
        mantiene las coordenadas de firma consistentes.
        Devuelve (nombre, bytes, total_paginas)."""
        total_paginas = {"arrendamiento": 0, "manual": 0, "pagares": 0}
        locale.setlocale(locale.LC_ALL, "es_MX.utf8")

        info = self.queryset.filter(id=id_paq).first()
        if not info:
            raise ValueError("Contrato no encontrado")

        pdf_writer = PdfWriter()

        # 1. Contrato (sin anexos)
        contrato_pdf = self._generar_contrato_interno(info, marca=marca)
        contrato_reader = PdfReader(io.BytesIO(contrato_pdf))
        total_paginas["arrendamiento"] = len(contrato_reader.pages)
        for page in contrato_reader.pages:
            pdf_writer.add_page(page)

        # 2. Manual UTO desde AWS (omitido en demo: es un PDF con marca Fraterna)
        if not (marca and marca.get('es_demo')):
            manual_url = "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/ManualUtower.pdf"
            try:
                response_manual = requests.get(manual_url, timeout=30)
                response_manual.raise_for_status()
                manual_reader = PdfReader(io.BytesIO(response_manual.content))
                total_paginas["manual"] = len(manual_reader.pages)
                for page in manual_reader.pages:
                    pdf_writer.add_page(page)
            except Exception as e:
                print(f"Error al descargar manual UTO: {e}")

        # 3. Pagarés (al final, sin firmas ZapSign — ver armar_payload_firmas_paquete_1)
        pagare_pdf = self._generar_pagare_interno(info, pagare_distinto, cantidad_pagare, marca=marca)
        pagare_reader = PdfReader(io.BytesIO(pagare_pdf))
        total_paginas["pagares"] = len(pagare_reader.pages)
        for page in pagare_reader.pages:
            pdf_writer.add_page(page)

        output_pdf = io.BytesIO()
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)

        fecha_actual = dt.now().strftime("%Y%m%d_%H%M%S")
        marca_slug = (marca or {}).get('marca_slug', 'Fraterna')
        nombre_archivo = f"Paquete_1_{marca_slug}_{info.residente.nombre_arrendatario}_{fecha_actual}.pdf"
        return nombre_archivo, output_pdf.getvalue(), total_paginas

    def _generar_paquete_2_pdf(self, id_paq, marca=None):
        """Paquete 2 = Comodato + Anexos + Póliza. Devuelve (nombre, bytes, total_paginas).

        La Póliza se firma aquí (antes iba en el Paquete 1): imprime el nº de
        departamento en la dirección del arrendatario, dato que ya está asignado al
        llegar al P2 (generar_urls_firma_paquete_2 lo exige). Así deja de salir en
        blanco/'None' como pasaba cuando iba en el P1."""
        total_paginas = {"comodato": 0, "anexos": 0, "poliza": 0}
        locale.setlocale(locale.LC_ALL, "es_MX.utf8")

        info = self.queryset.filter(id=id_paq).first()
        if not info:
            raise ValueError("Contrato no encontrado")

        pdf_writer = PdfWriter()

        # 1. Comodato
        comodato_pdf = self._generar_comodato_interno(info, marca=marca)
        comodato_reader = PdfReader(io.BytesIO(comodato_pdf))
        total_paginas["comodato"] = len(comodato_reader.pages)
        for page in comodato_reader.pages:
            pdf_writer.add_page(page)

        # 2. Anexos
        anexos_pdf = self._generar_anexos_interno(info, marca=marca)
        anexos_reader = PdfReader(io.BytesIO(anexos_pdf))
        total_paginas["anexos"] = len(anexos_reader.pages)
        for page in anexos_reader.pages:
            pdf_writer.add_page(page)

        # 3. Póliza (movida desde el Paquete 1: necesita el depa ya asignado).
        # Sus anchors <<firma_*>> viajan en el HTML → ZapSign las coloca aquí.
        poliza_pdf = self._generar_poliza_interno(info, marca=marca)
        poliza_reader = PdfReader(io.BytesIO(poliza_pdf))
        total_paginas["poliza"] = len(poliza_reader.pages)
        for page in poliza_reader.pages:
            pdf_writer.add_page(page)

        output_pdf = io.BytesIO()
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)

        fecha_actual = dt.now().strftime("%Y%m%d_%H%M%S")
        marca_slug = (marca or {}).get('marca_slug', 'Fraterna')
        nombre_archivo = f"Paquete_2_{marca_slug}_{info.residente.nombre_arrendatario}_{fecha_actual}.pdf"
        return nombre_archivo, output_pdf.getvalue(), total_paginas

    def armar_payload_firmas_paquete_1(self, signer_tokens, total_paginas, residente):
        """Posiciones de firmas para Paquete 1: contrato + manual + pagarés.
        La póliza se firma ahora en el Paquete 2 (ver armar_payload_firmas_paquete_2); el
        testigo (signer 3) igual firma el P1 vía el anchor <<firma_testigo>> del contrato.
        Los pagarés van INCLUIDOS en el PDF pero SIN firmas ZapSign (decisión legal/operativa)."""
        rubricas = []
        offsets = {}
        acumulador = 0
        for nombre, paginas in total_paginas.items():
            offsets[nombre] = acumulador
            acumulador += paginas

        posiciones_por_seccion = {"arrendamiento": [], "manual": [], "pagares": []}

        # Contrato (sin anexos): 3 firmas por página (izq-centro-der)
        for i in range(total_paginas["arrendamiento"]):
            posiciones_por_seccion["arrendamiento"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 2),
            ])

        # Manual UTO: 2 firmas por página
        for i in range(total_paginas["manual"]):
            posiciones_por_seccion["manual"].extend([
                (i, 5.0, 55.0, 1),
                (i, 5.0, 80.0, 2),
            ])

        # Pagarés: SIN firmas ZapSign — pero las páginas están en el PDF al final.
        # (residente sigue siendo signer 2 si en el futuro se quieren reactivar)
        _ = residente  # silenciar lint, no se usa con la decisión actual

        for seccion, posiciones in posiciones_por_seccion.items():
            offset = offsets[seccion]
            for page, bottom, left, signer_index in posiciones:
                if signer_index < len(signer_tokens):
                    rubricas.append({
                        "page": page + offset,
                        "relative_position_bottom": bottom,
                        "relative_position_left": left,
                        "relative_size_x": 19.55,
                        "relative_size_y": 9.42,
                        "type": "signature",
                        "signer_token": signer_tokens[signer_index],
                    })
        return {"rubricas": rubricas}

    def armar_payload_firmas_paquete_2(self, signer_tokens, total_paginas, residente):
        """Posiciones de firmas para Paquete 2: comodato + anexos + póliza.

        Las firmas se colocan por DOBLE vía:
          1. Coordenadas (este `place-signatures`): comodato en sus 6 posiciones específicas;
             anexos con 3 firmas al fondo de cada página (izq-centro-der).
          2. Anchors `<<firma_X>>` (ver `signature_placement` en `build_payload_to_zapsign`):
             ZapSign los detecta automáticamente en los HTMLs y coloca firmas extras encima
             de las líneas pre-impresas (Anexo 4 y 5 hoy; ampliable a contrato/comodato).
        ZapSign acepta ambos sistemas en paralelo sin conflicto.
        """
        rubricas = []
        offsets = {}
        acumulador = 0
        for nombre, paginas in total_paginas.items():
            offsets[nombre] = acumulador
            acumulador += paginas

        posiciones_por_seccion = {
            "comodato": [
                (0, 1.5, 5.0, 0),
                (0, 1.5, 75.0, 1),
                (1, 13.0, 18.0, 0),
                (1, 13.0, 65.0, 1),
                (2, 5.0, 75.0, 1),
                (3, 26.5, 18.0, 1),
            ],
            "anexos": [],
            "poliza": [],
        }

        # Anexos: 3 firmas por página (mismo patrón que el contrato).
        # Coexiste con anchors `<<firma_X>>` en Anexos 4/5 — ZapSign coloca ambas.
        for i in range(total_paginas["anexos"]):
            posiciones_por_seccion["anexos"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 2),
            ])

        # Póliza (movida desde el Paquete 1): 3 firmas por página (signer 0, 1, 3).
        # Mismas posiciones relativas que tenía en el P1. Sus anchors <<firma_*>> viajan
        # en el HTML de la póliza, así que ZapSign también las coloca automáticamente.
        for i in range(total_paginas["poliza"]):
            posiciones_por_seccion["poliza"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 3),
            ])

        for seccion, posiciones in posiciones_por_seccion.items():
            offset = offsets[seccion]
            for page, bottom, left, signer_index in posiciones:
                if signer_index < len(signer_tokens):
                    rubricas.append({
                        "page": page + offset,
                        "relative_position_bottom": bottom,
                        "relative_position_left": left,
                        "relative_size_x": 19.55,
                        "relative_size_y": 9.42,
                        "type": "signature",
                        "signer_token": signer_tokens[signer_index],
                    })
        return {"rubricas": rubricas}

    def _subir_paquete_a_zapsign(self, contrato_data, armar_payload_firmas_fn, persistir_token=True, campo_token='token', marca=None):
        """
        Sube un paquete a ZapSign con la función de posicionamiento dada.
        - persistir_token=True (default) → guarda doc_token en `info.<campo_token>`.
        - campo_token='token'           → Paquete 1 (default).
        - campo_token='token_paquete_2' → Paquete 2.
        - persistir_token=False         → solo lo retorna en la respuesta (legacy).
        - marca                          → marca blanca demo (sandbox ZapSign).
        """
        payload = self.build_payload_to_zapsign(contrato_data, marca=marca)
        headers = {
            'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}',
            'Content-Type': 'application/json',
        }
        url = f'{API_URL_ZAPSIGN}docs/'

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            try:
                response_data = response.json()
            except ValueError:
                response_data = {"raw_response": response.text}

            doc_token = response_data.get("token")
            signer_tokens = [s.get("token") for s in response_data.get("signers", []) if s.get("token")]
            if not doc_token:
                raise ValueError("No se pudo obtener el token del documento desde la respuesta.")

            if persistir_token:
                info = self.queryset.filter(id=contrato_data["id"]).first()
                if info:
                    setattr(info, campo_token, doc_token)
                    # Inicializa el estado de firma del paquete en "pending";
                    # el webhook de ZapSign lo pasará a "signed"/"refused".
                    campo_estado = ('estado_firma_paquete_2'
                                    if campo_token == 'token_paquete_2'
                                    else 'estado_firma_paquete_1')
                    setattr(info, campo_estado, 'pending')
                    info.save()

            rubricas_payload = armar_payload_firmas_fn(
                signer_tokens, contrato_data["total_paginas"], contrato_data["residente"]
            )
            posicionar_url = f'{API_URL_ZAPSIGN}docs/{doc_token}/place-signatures/'
            posicionar_response = requests.post(posicionar_url, headers=headers, json=rubricas_payload, timeout=60)
            posicionar_response.raise_for_status()

            return {
                "payload": payload,
                "doc_token": doc_token,
                "zapsign_new_doc": response_data,
                "rubricas_payload": rubricas_payload,
                "rubricas_response": posicionar_response.text or "Sin contenido",
            }
        except requests.exceptions.Timeout:
            print("Error: Tiempo de espera agotado al comunicar con ZapSign.")
        except requests.exceptions.RequestException as e:
            print(f"Error en la solicitud a Zap-Sign: {e}")
        except Exception as e:
            print(f"Error inesperado: {e}")
        return None

    def generar_anexos(self, request, *args, **kwargs):
        """Endpoint utility: descarga PDF solo de los anexos."""
        try:
            data = request.data
            id_paq = data["id"] if isinstance(data, dict) else data
            info = self.queryset.filter(id=id_paq).first()
            if not info:
                return Response({'error': 'Contrato no encontrado'}, status=status.HTTP_404_NOT_FOUND)

            pdf_file = self._generar_anexos_interno(info, marca=marca_para(request.user))
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Anexos_Fraterna.pdf"'
            response.write(pdf_file)
            return response
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en generar_anexos línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def generar_paquete_1(self, request, *args, **kwargs):
        """Descarga PDF del Paquete 1 (contrato + manual + pagarés).
        `pagare_distinto` y `cantidad_primer_pagare` se leen del modelo del contrato."""
        try:
            data = request.data
            id_paq = data["id"] if isinstance(data, dict) else data

            nombre_archivo, pdf_bytes, _ = self._generar_paquete_1_pdf(id_paq, marca=marca_para(request.user))
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
            response.write(pdf_bytes)
            return response
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en generar_paquete_1 línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def generar_paquete_2(self, request, *args, **kwargs):
        """Descarga PDF del Paquete 2 (comodato + anexos + póliza)."""
        try:
            data = request.data
            id_paq = data["id"] if isinstance(data, dict) else data

            nombre_archivo, pdf_bytes, _ = self._generar_paquete_2_pdf(id_paq, marca=marca_para(request.user))
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
            response.write(pdf_bytes)
            return response
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en generar_paquete_2 línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # Bitácora de rondas de firma (ledger encima de FraternaContratos).
    # Cada generación de enlaces de Paquete 1 abre/refresca la ronda 'pendiente';
    # el Paquete 2 la aumenta; el webhook la cierra; un reset la cancela. Ver
    # handoff "Fraterna - Renovacion de contratos + bitacora de rondas de firma -
    # 2026-07-07". Aditivo: un fallo del ledger NO debe tumbar la firma en ZapSign.
    # =========================================================================

    # Orden de firmantes del Paquete 1, alineado con build_payload_to_zapsign():
    # 0=arrendador (Fraterna), 1=arrendatario, 2=residente, 3=prestador (testigo).
    ROLES_FIRMANTES_P1 = ['arrendador', 'arrendatario', 'residente', 'prestador']
    # Firmantes "finales": firman al final (via "Firmar como arrendador/prestador");
    # NO bloquean la emision del Paquete 2.
    ROLES_FINALES = ('arrendador', 'prestador')

    # Candado de edicion durante firma: campos que los documentos del Paquete 1
    # imprimen -> se bloquean al existir token_1 en la ronda 'pendiente' (editarlos
    # a media firma = docs del intento inconsistentes entre si).
    CAMPOS_BLOQUEO_P1 = ('residente', 'habitantes', 'renta', 'duracion',
                         'fecha_celebracion', 'fecha_vigencia', 'fecha_move_in',
                         'fecha_move_out', 'pagare_distinto', 'cantidad_primer_pagare',
                         'estacionamiento', 'precio_estacionamiento_mxn',
                         'kilowatts_incluidos', 'dia_pago')
    # Campos de la asignacion (Anexo 1 / comodato del P2): editables durante la firma
    # del P1 (el flujo los llena despues), pero se bloquean al existir token_2.
    CAMPOS_BLOQUEO_P2 = ('no_depa', 'cama', 'piso', 'tipologia', 'medidas',
                         'plano_localizacion')

    def _campos_bloqueados_en_firma(self, info, data):
        """Candado de edicion durante firma (el FE espeja esto en editar_proc).

        Devuelve la lista de campos BLOQUEADOS que el payload intenta CAMBIAR de
        valor, o []. Sin ronda 'pendiente' (legacy sin bitacora) no aplica.
        La comparacion normaliza vacios (None == '' == '  ') y numeros ('1160' ==
        '1160.00') para NO rebotar guardados que no cambian nada: el form de editar
        manda '' donde la BD tiene NULL (blanqueo fantasma comprobado 2026-07-08).
        """
        ronda = info.rondas_firma.filter(estado='pendiente').first()
        if ronda is None:
            return []
        bloqueados = ()
        if ronda.token_1:
            bloqueados += self.CAMPOS_BLOQUEO_P1
        if ronda.token_2:
            bloqueados += self.CAMPOS_BLOQUEO_P2
        if not bloqueados:
            return []
        return self._campos_con_cambio(info, data, bloqueados)

    def _campos_con_cambio(self, info, data, campos):
        """De `campos`, los que el payload intenta CAMBIAR de valor de verdad.

        Comparador compartido del candado de firma y del sellado de contrato
        vigente: normaliza vacios (None == '' == '  '), numeros ('1160' ==
        '1160.00') y booleanos (True == 'true') para NO rebotar guardados que
        no cambian nada (el form de editar manda '' donde la BD tiene NULL —
        blanqueo fantasma comprobado 2026-07-08).
        """
        def _norm(v):
            return '' if v is None else str(v).strip()

        def _iguales(a, b):
            na, nb = _norm(a), _norm(b)
            if na == nb:
                return True
            if na.lower() in ('true', 'false') and nb.lower() in ('true', 'false'):
                return na.lower() == nb.lower()
            try:
                return float(na) == float(nb)
            except (ValueError, TypeError):
                return False

        cambiados = []
        for campo in campos:
            if campo not in data:
                continue
            nuevo = data.get(campo)
            if campo == 'residente':
                if isinstance(nuevo, dict):
                    nuevo = nuevo.get('id')
                # vacio no se flaggea (prefill garantiza valor; evitar falso bloqueo)
                if _norm(nuevo) and not _iguales(nuevo, info.residente_id):
                    cambiados.append(campo)
                continue
            if campo == 'plano_localizacion':
                if hasattr(nuevo, 'read'):  # archivo nuevo subido = cambio
                    cambiados.append(campo)
                continue
            actual = getattr(info, campo, None)
            if hasattr(actual, 'isoformat'):
                actual = actual.isoformat()
            if not _iguales(nuevo, actual):
                cambiados.append(campo)
        return cambiados

    def _snapshot_datos_contrato(self, info):
        """Congela los términos NO-fecha del contrato para una ronda (jsonb).

        Las fechas van en columnas dedicadas de la ronda (indexables); aquí va el
        resto. Los Decimal se pasan a str porque el JSONField default no los
        serializa.
        """
        def _dec(v):
            return str(v) if v is not None else None

        residente = getattr(info, 'residente', None)
        return {
            'no_depa': info.no_depa,
            'cama': info.cama,
            'piso': info.piso,
            'habitantes': info.habitantes,
            'tipologia': info.tipologia,
            'medidas': info.medidas,
            'renta': info.renta,
            'estacionamiento': info.estacionamiento,
            'precio_estacionamiento_mxn': _dec(info.precio_estacionamiento_mxn),
            'kilowatts_incluidos': _dec(info.kilowatts_incluidos),
            'duracion': info.duracion,
            'pagare_distinto': info.pagare_distinto,
            'cantidad_primer_pagare': info.cantidad_primer_pagare,
            'dia_pago': info.dia_pago,
            'residente_nombre': getattr(residente, 'nombre_arrendatario', None),
        }

    def _registrar_ronda_p1(self, info, doc_token, signers, usuario=None):
        """Enganche 'Generar Paquete 1': abre o refresca la ronda 'pendiente'.

        - Si ya hay una ronda 'pendiente' para el contrato, la reutiliza (regenerar
          el Paquete 1 sin cancelar = el MISMO intento): refresca fechas, snapshot,
          token_1 y reinyecta los firmantes del Paquete 1.
        - Si no hay ninguna abierta, crea una nueva (numero = max+1). El tipo es
          'renovacion' si el contrato ya tuvo alguna ronda 'firmado'; si no,
          'inicial'.

        `signers` = lista de dicts de la respuesta de ZapSign (name/email/token/
        sign_url) en el mismo orden que build_payload_to_zapsign (ver
        ROLES_FIRMANTES_P1). Devuelve la ronda (o None si falta doc_token).
        """
        if not doc_token:
            return None
        with transaction.atomic():
            ronda = info.rondas_firma.filter(estado='pendiente').first()
            if ronda is None:
                ultimo = info.rondas_firma.aggregate(m=Max('numero'))['m'] or 0
                ya_firmo = info.rondas_firma.filter(estado__in=('firmado', 'expirado')).exists()
                ronda = FraternaRondaFirma(
                    contrato=info,
                    numero=ultimo + 1,
                    tipo='renovacion' if ya_firmo else 'inicial',
                )
            ronda.fecha_celebracion = info.fecha_celebracion
            ronda.fecha_vigencia = info.fecha_vigencia
            ronda.fecha_move_in = info.fecha_move_in
            ronda.fecha_move_out = info.fecha_move_out
            ronda.datos_snapshot = self._snapshot_datos_contrato(info)
            ronda.token_1 = doc_token
            ronda.estado_firma_1 = 'pending'
            if usuario:
                ronda.usuario = usuario
            ronda.save()

            # Refresca los firmantes del Paquete 1 (idempotente al regenerar).
            ronda.firmantes.filter(paquete=1).delete()
            firmantes = []
            for idx, s in enumerate(signers or []):
                firmantes.append(FraternaRondaFirmante(
                    ronda=ronda,
                    paquete=1,
                    nombre=(s.get('name') or '')[:200],
                    rol=(self.ROLES_FIRMANTES_P1[idx]
                         if idx < len(self.ROLES_FIRMANTES_P1) else None),
                    email=s.get('email') or None,
                    sign_url=s.get('sign_url') or None,
                    token_firmante=s.get('token') or None,
                    estado='pendiente',
                ))
            if firmantes:
                FraternaRondaFirmante.objects.bulk_create(firmantes)
        return ronda

    RONDA_CAMPOS_FECHA = ('fecha_celebracion', 'fecha_vigencia', 'fecha_move_in', 'fecha_move_out')

    def _registrar_ronda_p2(self, info, doc_token, signers, usuario=None):
        """Enganche 'Generar Paquete 2': completa la ronda 'pendiente' con el doc P2.

        - Set token_2 + estado_firma_2='pending' + espejo de firmantes del Paquete 2
          (idempotente al regenerar, igual que P1).
        - RE-CONGELA snapshot y fechas (semantica: snapshot = ultima generacion del
          intento, igual que el reuse de P1) y guarda en `_delta_p2` TODO campo que
          cambio desde el Paquete 1: {campo: [antes, despues]}. vacio->valor =
          completar (p.ej. depa/cama asignados despues de P1); valor->valor = drift
          (los docs del intento quedaron inconsistentes entre si; queda el rastro).
        - Al REGENERAR P2 el delta se COMPONE: el "antes" sigue siendo el valor que
          habia al generar P1 (se deshace el delta previo para reconstruir la base);
          un campo que regresa a su valor de P1 sale del delta.
        - Contratos sin ronda 'pendiente' (legacy sin bitacora): no hace nada.
        """
        if not doc_token:
            return None

        def _iso(v):
            return v.isoformat() if v else None

        def _vacio(v):
            return v is None or (isinstance(v, str) and not v.strip())

        with transaction.atomic():
            ronda = info.rondas_firma.filter(estado='pendiente').first()
            if ronda is None:
                return None

            snapshot_viejo = dict(ronda.datos_snapshot or {})
            delta_previo = snapshot_viejo.pop('_delta_p2', None) or {}
            snapshot_nuevo = self._snapshot_datos_contrato(info)

            # Base "al momento de P1": el snapshot vigente deshaciendo el delta de un
            # P2 anterior (solo aplica si esto es una regeneracion del P2).
            base_p1 = dict(snapshot_viejo)
            base_p1.update({k: par[0] for k, par in delta_previo.items()
                            if k not in self.RONDA_CAMPOS_FECHA})

            delta = {}
            for k in set(base_p1) | set(snapshot_nuevo):
                antes, despues = base_p1.get(k), snapshot_nuevo.get(k)
                # None <-> '' NO es cambio (los forms guardan '' donde habia NULL).
                if antes != despues and not (_vacio(antes) and _vacio(despues)):
                    delta[k] = [antes, despues]
            for campo in self.RONDA_CAMPOS_FECHA:
                antes = (delta_previo[campo][0] if campo in delta_previo
                         else _iso(getattr(ronda, campo)))
                despues = _iso(getattr(info, campo))
                if antes != despues:
                    delta[campo] = [antes, despues]

            if delta:
                snapshot_nuevo['_delta_p2'] = delta

            ronda.fecha_celebracion = info.fecha_celebracion
            ronda.fecha_vigencia = info.fecha_vigencia
            ronda.fecha_move_in = info.fecha_move_in
            ronda.fecha_move_out = info.fecha_move_out
            ronda.datos_snapshot = snapshot_nuevo
            ronda.token_2 = doc_token
            ronda.estado_firma_2 = 'pending'
            if usuario:
                ronda.usuario = usuario
            ronda.save()

            # Espejo de firmantes del Paquete 2 (mismo builder de signers que P1 ->
            # mismos 4 roles por orden).
            ronda.firmantes.filter(paquete=2).delete()
            firmantes = []
            for idx, s in enumerate(signers or []):
                firmantes.append(FraternaRondaFirmante(
                    ronda=ronda,
                    paquete=2,
                    nombre=(s.get('name') or '')[:200],
                    rol=(self.ROLES_FIRMANTES_P1[idx]
                         if idx < len(self.ROLES_FIRMANTES_P1) else None),
                    email=s.get('email') or None,
                    sign_url=s.get('sign_url') or None,
                    token_firmante=s.get('token') or None,
                    estado='pendiente',
                ))
            if firmantes:
                FraternaRondaFirmante.objects.bulk_create(firmantes)
        return ronda

    def _partes_p1_pendientes(self, info):
        """Candado de firmas del Paquete 2 del lado BE (espejo de la bitacora).

        Devuelve la lista de nombres de "partes" del Paquete 1 (excluye arrendador/
        prestador, que firman al final) que aun NO estan 'firmado', o None si el
        contrato no tiene bitacora utilizable (legacy sin ronda -> el gate queda
        como hasta hoy: solo el FE verifica contra ZapSign).

        Espejo-first: si el espejo dice que todos firmaron, no hay red. Si dice que
        falta alguien, se revalida contra ZapSign (verdad viva, emparejando por
        token de firmante) para no bloquear por un evento de webhook perdido; si
        ZapSign no responde, manda el espejo (conservador: bloquea).
        """
        ronda = info.rondas_firma.filter(estado='pendiente').first()
        if ronda is None or not ronda.token_1:
            return None
        partes = [f for f in ronda.firmantes.filter(paquete=1)
                  if f.rol not in self.ROLES_FINALES]
        if not partes:
            return None
        pendientes = [f for f in partes if f.estado != 'firmado']
        if not pendientes:
            return []
        try:
            url = f'{API_URL_ZAPSIGN}docs/{ronda.token_1}/'
            headers = {'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            vivos = {s.get('token'): s.get('status')
                     for s in (resp.json().get('signers') or []) if s.get('token')}
            pendientes = [f for f in pendientes
                          if vivos.get(f.token_firmante) != 'signed']
        except Exception as e:
            logger.warning(f"{datetime.now()} Candado P2: revalidacion ZapSign fallo "
                           f"(contrato {info.id}), manda el espejo: {e}")
        return [f.nombre for f in pendientes]

    def _cancelar_ronda_pendiente(self, info, motivo=None, usuario=None):
        """Enganche 'Cancelar firmas': cierra la ronda 'pendiente' como 'cancelado'.

        Cierre terminal: la ronda conserva tokens, snapshot y el estado de cada
        firmante tal como quedaron (auditoria completa del intento); el webhook ya
        no la revive (una 'cancelado' solo refresca su espejo, sin PDF ni rail).
        Una 'firmado' NUNCA se cancela: para cambiarla se genera otra ronda
        (renovacion). Devuelve la ronda cancelada o None si no habia 'pendiente'.
        """
        ronda = info.rondas_firma.filter(estado='pendiente').first()
        if ronda is None:
            return None
        ronda.estado = 'cancelado'
        if motivo:
            ronda.motivo = str(motivo)[:255]
        if usuario:
            ronda.usuario = usuario
        ronda.cerrado_en = timezone.now()
        ronda.save(update_fields=['estado', 'motivo', 'usuario', 'cerrado_en'])
        return ronda

    def _vigente_sellado(self, info):
        """Contrato con termino firmado ('actual' o 'expirado') sin renovacion en
        curso = SELLADO.

        Sus datos y firmas respaldan el termino (vigente o ya vencido): no se
        edita, no se (re)generan enlaces y no se retiran firmas. La UNICA salida
        es `iniciar_renovacion` (menu "Renovar contrato"), que abre la ronda de
        renovacion y pone el contrato en 'en_renovacion'; ahi vuelve a ser
        editable (aplican los candados por token de siempre). Un 'expirado' se
        sella igual que un 'actual': el contrato esta terminado, la unica accion
        posible es renovarlo. NULL (pendiente/legacy) NO se sella (flujo normal).
        """
        if getattr(info, 'estado_contrato', None) not in ('actual', 'expirado'):
            return False
        return not info.rondas_firma.filter(estado='pendiente').exists()

    def generar_urls_firma_paquete_1(self, request, *args, **kwargs):
        """Manda Paquete 1 a ZapSign. Persiste doc_token en info.token.
        Lee pagare_distinto/cantidad del modelo del contrato."""
        bloqueo_temporal = self._guard_firmas_deshabilitadas()
        if bloqueo_temporal:
            return bloqueo_temporal
        try:
            data = request.data
            if not isinstance(data, dict):
                return Response({'error': 'Se requiere id_contrato y residente_contrato'}, status=status.HTTP_400_BAD_REQUEST)
            id_paq = data["id_contrato"]
            bloqueo_demo = self._guard_demo(request, id_paq)
            if bloqueo_demo:
                return bloqueo_demo
            candado_rol = self._guard_solo_arrendify_o_aprobado(request, id_paq)
            if candado_rol:
                return candado_rol
            marca = marca_para(request.user)
            # Fix (A) consistencia: los firmantes se re-derivan de la BD (fuente de verdad),
            # NO del snapshot del FE (`residente_contrato`), que podia venir viejo/duplicado.
            info = self.queryset.filter(id=id_paq).first()
            if not info or not info.residente:
                return Response({'error': 'Contrato o residente no encontrado'}, status=status.HTTP_404_NOT_FOUND)

            # Contrato VIGENTE sin renovacion en curso: generar enlaces sueltos
            # abriria un intento nuevo por fuera del flujo. La renovacion se inicia
            # con "Renovar contrato" (abre la ronda y habilita esta generacion).
            if self._vigente_sellado(info):
                return Response(
                    {'error': 'El contrato esta sellado. Para emitir documentos '
                              'nuevos usa "Renovar contrato".'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            residente = ResidenteSerializers(info.residente).data

            nombre_archivo, pdf_bytes, total_paginas = self._generar_paquete_1_pdf(id_paq, marca=marca)
            base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')

            contrato_data = {
                "id": id_paq,
                "filename": nombre_archivo,
                "base64_pfd": base64_pdf,
                "residente": residente,
                "total_paginas": total_paginas,
            }
            # persistir_token=False PERMANENTE (decisión 2026-07-23): el doc_token vive
            # SOLO en la bitácora de rondas (token_1) — fraterna_contrato.token queda
            # jubilado como fuente (la UI y el webhook trabajan contra la ronda; los
            # contratos pre-bitácora se cubren con la migración de datos al deploy).
            resultado = self._subir_paquete_a_zapsign(contrato_data, self.armar_payload_firmas_paquete_1, persistir_token=False, marca=marca)

            # Enganche bitácora de rondas: abre/refresca la ronda 'pendiente' con el
            # snapshot + token_1 + firmantes P1. Best-effort: si el ledger falla NO
            # tumbamos la firma (el documento ZapSign ya se creó).
            if resultado:
                try:
                    usuario = (getattr(request.user, 'email', '') or
                               getattr(request.user, 'username', '') or '') or None
                    signers = (resultado.get('zapsign_new_doc') or {}).get('signers', [])
                    self._registrar_ronda_p1(info, resultado.get('doc_token'), signers, usuario)
                except Exception as e_ronda:
                    logger.error(f"{datetime.now()} No se pudo registrar la ronda P1 "
                                 f"(contrato {id_paq}): {e_ronda}")

            return Response({"respuestaZS": resultado, "paquete": "1"}, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en generar_urls_firma_paquete_1 línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def generar_urls_firma_paquete_2(self, request, *args, **kwargs):
        """Manda Paquete 2 a ZapSign y persiste el doc_token en `FraternaContratos.token_paquete_2`."""
        bloqueo_temporal = self._guard_firmas_deshabilitadas()
        if bloqueo_temporal:
            return bloqueo_temporal
        try:
            data = request.data
            if not isinstance(data, dict):
                return Response({'error': 'Se requiere id_contrato y residente_contrato'}, status=status.HTTP_400_BAD_REQUEST)
            id_paq = data["id_contrato"]
            bloqueo_demo = self._guard_demo(request, id_paq)
            if bloqueo_demo:
                return bloqueo_demo
            candado_rol = self._guard_solo_arrendify_o_aprobado(request, id_paq)
            if candado_rol:
                return candado_rol
            marca = marca_para(request.user)
            # Fix (A) consistencia: los firmantes se re-derivan de la BD (fuente de verdad),
            # NO del snapshot del FE (`residente_contrato`), que podia venir viejo/duplicado.
            info = self.queryset.filter(id=id_paq).first()
            if not info or not info.residente:
                return Response({'error': 'Contrato o residente no encontrado'}, status=status.HTTP_404_NOT_FOUND)
            # Mismo sellado que el Paquete 1: un contrato VIGENTE sin renovacion en
            # curso no emite documentos nuevos (la salida es "Renovar contrato").
            if self._vigente_sellado(info):
                return Response(
                    {'error': 'El contrato esta sellado. Para emitir documentos '
                              'nuevos usa "Renovar contrato".'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            residente = ResidenteSerializers(info.residente).data

            # El Anexo del Paquete 2 imprime departamento y cama; si faltan, el documento
            # sale con "None". Se bloquea la generacion hasta que el contrato los tenga.
            if not (info.no_depa and str(info.no_depa).strip()) or not (info.cama and str(info.cama).strip()):
                return Response(
                    {'error': 'Falta asignar departamento y/o cama al contrato. Asignalos antes de generar el Paquete 2.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Candado de firmas del P1 (lado BE, espejo de la bitacora): las "partes"
            # deben haber firmado antes de emitir el P2 (arrendador/prestador firman
            # al final). El FE ya lo verifica; esto lo hace inviolable ante llamadas
            # directas a la API. Contratos legacy sin ronda: sin cambio (devuelve None).
            pendientes_p1 = self._partes_p1_pendientes(info)
            if pendientes_p1:
                return Response(
                    {'error': 'Las partes del Paquete 1 aun no firman: '
                              f'{", ".join(pendientes_p1)}. El arrendador y el prestador '
                              'firman al final; genera el Paquete 2 cuando las partes hayan firmado.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            nombre_archivo, pdf_bytes, total_paginas = self._generar_paquete_2_pdf(id_paq, marca=marca)
            base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')

            contrato_data = {
                "id": id_paq,
                "filename": nombre_archivo,
                "base64_pfd": base64_pdf,
                "residente": residente,
                "total_paginas": total_paginas,
            }
            # persistir_token=False PERMANENTE (decisión 2026-07-23, espejo del P1): el
            # doc_token del P2 vive SOLO en la ronda (token_2); token_paquete_2 jubilado.
            resultado = self._subir_paquete_a_zapsign(contrato_data, self.armar_payload_firmas_paquete_2, persistir_token=False, campo_token='token_paquete_2', marca=marca)

            # Enganche bitacora de rondas: completa la ronda 'pendiente' con token_2,
            # firmantes P2 y RE-CONGELA snapshot/fechas (+_delta_p2). Best-effort: un
            # fallo del ledger NO tumba la firma (el documento ZapSign ya se creo).
            if resultado:
                try:
                    usuario = (getattr(request.user, 'email', '') or
                               getattr(request.user, 'username', '') or '') or None
                    signers = (resultado.get('zapsign_new_doc') or {}).get('signers', [])
                    self._registrar_ronda_p2(info, resultado.get('doc_token'), signers, usuario)
                except Exception as e_ronda:
                    logger.error(f"{datetime.now()} No se pudo registrar la ronda P2 "
                                 f"(contrato {id_paq}): {e_ronda}")

            return Response({"respuestaZS": resultado, "paquete": "2"}, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en generar_urls_firma_paquete_2 línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # FIN PAQUETE 1 / PAQUETE 2
    # =========================================================================

    def generar_reporte_contratos(self, request, *args, **kwargs):
        """Genera un PDF con el reporte de contratos Fraterna celebrados en un mes/anio.
        Recibe { "mes": 1-12, "anio": YYYY }; filtra por fecha_celebracion."""
        try:
            data = request.data
            mes = int(data.get('mes'))
            anio = int(data.get('anio'))
            if mes < 1 or mes > 12:
                return Response({'error': 'Mes invalido (1-12).'}, status=status.HTTP_400_BAD_REQUEST)

            contratos = self.queryset.filter(
                fecha_celebracion__year=anio,
                fecha_celebracion__month=mes,
            ).order_by('fecha_celebracion')

            meses_es = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

            filas = []
            suma_renta = 0.0
            total_aprobados = 0
            por_tipologia = {}
            pill_map = {
                'aprobado': 'pill-ok',
                'en revision': 'pill-rev', 'en revisión': 'pill-rev',
                'firmado': 'pill-firm',
            }
            for c in contratos:
                try:
                    renta_val = float(c.renta) if c.renta not in (None, '') else 0.0
                except (ValueError, TypeError):
                    renta_val = 0.0

                tipologia = (c.tipologia or '').strip() or 'Sin tipologia'
                por_tipologia[tipologia] = por_tipologia.get(tipologia, 0) + 1

                proceso = c.contrato.order_by('-id').first()
                estatus = proceso.status_proceso if (proceso and proceso.status_proceso) else '-'
                estatus_norm = estatus.strip().lower()

                # La suma de renta mensual solo considera contratos en estado Aprobado.
                if estatus_norm == 'aprobado':
                    total_aprobados += 1
                    suma_renta += renta_val

                if c.residente:
                    residente_nombre = c.residente.nombre_residente or c.residente.nombre_arrendatario or '-'
                else:
                    residente_nombre = '-'

                filas.append({
                    'no_depa': c.no_depa or '-',
                    'residente': residente_nombre,
                    'tipologia': tipologia,
                    'fecha_celebracion': c.fecha_celebracion.strftime('%d/%m/%Y') if c.fecha_celebracion else '-',
                    'fecha_vigencia': c.fecha_vigencia.strftime('%d/%m/%Y') if c.fecha_vigencia else '-',
                    'renta': f"${renta_val:,.2f}",
                    'estatus': estatus,
                    'pill': pill_map.get(estatus_norm, 'pill-other'),
                })

            desglose = [{'tipologia': t, 'cantidad': n} for t, n in sorted(por_tipologia.items())]

            context = {
                'mes_nombre': meses_es[mes],
                'anio': anio,
                'total': len(filas),
                'total_aprobados': total_aprobados,
                'suma_renta': f"${suma_renta:,.2f}",
                'desglose': desglose,
                'filas': filas,
                'generado': datetime.now().strftime('%d/%m/%Y %H:%M'),
            }

            html_string = render_to_string('home/reporte_contratos_fraterna.html', context)
            pdf_file = HTML(string=html_string).write_pdf()

            response = HttpResponse(pdf_file, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Reporte_Contratos_Fraterna_{anio}_{mes:02d}.pdf"'
            return response

        except (TypeError, ValueError):
            return Response({'error': 'Parametros invalidos: se requiere mes (1-12) y anio.'},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en generar_reporte_contratos linea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _generar_comodato_interno(self, info, marca=None):
        """Función interna para generar el PDF del comodato"""
        try:
            # Obtener la duración para pasarla a letra
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            duracion_texto = num2words(duracion_meses, lang='es')
            
            # Obtener renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            # Obtener la tipología
            opciones = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png"
            }
            
            inventario = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.png"
            }
            
            tipologia = info.tipologia
            plano = opciones.get(tipologia, "")
            tabla_inventario = inventario.get(tipologia, "")
            
            # Obtener la URL del plano que sube fraterna
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
            
            context = {
                'info': info,
                'duracion_meses': duracion_meses,
                'duracion_texto': duracion_texto,
                'renta_texto': renta_texto,
                'plano': plano,
                'plan_loc': plan_loc,
                'tabla_inventario': tabla_inventario,
                **(marca or {}),
            }

            template = 'home/comodato_fraterna.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando comodato interno: {e}")
            raise e
    
    def _generar_contrato_interno(self, info, marca=None):
        """Función interna para generar el PDF del contrato"""
        try:
            # Obtener la cantidad de habitantes para pasarla a letra
            habitantes = int(info.habitantes)
            habitantes_texto = num2words(habitantes, lang='es')
            
            # Obtener renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            # Obtener la tipología
            opciones = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png"
            }
            
            inventario = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.png"
            }
            
            tipologia = info.tipologia
            plano = opciones.get(tipologia, "")
            tabla_inventario = inventario.get(tipologia, "")
            
            # Obtener la URL del plano que sube fraterna
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
            
            context = {
                **{
                    'info': info,
                    'habitantes_texto': habitantes_texto,
                    'renta_texto': renta_texto,
                    'plano': plano,
                    'plan_loc': plan_loc,
                    'tabla_inventario': tabla_inventario,
                },
                **_contraprestacion_fraterna_context(info),
                **(marca or {}),
            }

            template = 'home/contrato_fraterna_v2.html' if settings.USE_NEW_FRATERNA_CONTRACT else 'home/contrato_fraterna.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando contrato interno: {e}")
            raise e
    
    def _generar_poliza_interno(self, info, marca=None):
        """Función interna para generar el PDF de la póliza"""
        try:
            # Generar el número de contrato
            arrendatario = info.residente.nombre_arrendatario
            primera_letra = arrendatario[0].upper()
            ultima_letra = arrendatario[-1].upper()
            
            year = info.fecha_celebracion.strftime("%g")
            month = info.fecha_celebracion.strftime("%m")
            
            nom_contrato = f"AFY{month}{year}CX51{info.id}CA{primera_letra}{ultima_letra}"
            
            # Obtener renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            context = {
                'info': info,
                'renta_texto': renta_texto,
                'nom_contrato': nom_contrato,
                **(marca or {}),
            }

            template = 'home/poliza_fraterna.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando póliza interna: {e}")
            raise e
    
    def _generar_pagare_interno(self, info, pagare_distinto=None, cantidad_pagare=None, marca=None):
        """Función interna para generar el PDF del pagaré.

        Args opcionales para compatibilidad con llamadas viejas. Si no vienen,
        se leen del propio modelo (`info.pagare_distinto` y `info.cantidad_primer_pagare`).
        `marca`: contexto de marca blanca (cuentas demo).
        """
        try:
            # Si no se pasaron explícitos, leer del modelo
            if pagare_distinto is None:
                pagare_distinto = (info.pagare_distinto or "No")
            if cantidad_pagare is None:
                cantidad_pagare = (info.cantidad_primer_pagare or "0")

            # Procesar cantidad del pagaré
            if pagare_distinto == "Si":
                if "." not in str(cantidad_pagare):
                    cantidad_pagare_num = cantidad_pagare
                    cantidad_decimal = "00"
                    cantidad_letra = num2words(cantidad_pagare_num, lang='es')
                else:
                    cantidad_completa = str(cantidad_pagare).split(".")
                    cantidad_pagare_num = cantidad_completa[0]
                    cantidad_decimal = cantidad_completa[1]
                    cantidad_letra = num2words(cantidad_pagare_num, lang='es')
            else:
                cantidad_pagare_num = 0
                cantidad_decimal = "00"
                cantidad_letra = num2words(cantidad_pagare_num, lang='es')
            
            # Definir la fecha inicial
            fecha_inicial = info.fecha_move_in
            dia = fecha_inicial.day

            # Un pagaré por mes de `duracion` — helper compartido con la cláusula
            # Vigésima Primera del contrato: misma fuente, el número impreso y los
            # documentos nunca difieren. (Fuente autoritativa para "X de N".)
            duracion_meses = _num_pagares_fraterna(info)

            # Generar 1 pagaré por cada mes según `duracion_meses`.
            # Para contratos cortos (< 1 mes) generamos exactamente 1 pagaré que cubre el periodo.
            # Día impreso: el 1er pagaré lleva el día real del move-in (mes de entrada,
            # prorrateable vía pagare_distinto); los siguientes vencen el `dia_pago` del
            # contrato (default 5), ajustado al último día real del mes si no alcanza
            # (p.ej. 31 -> 28/29 en febrero, 30 en abril).
            dia_pago = _dia_pago_fraterna(info)
            fechas_iteradas = []
            num_pagares = duracion_meses
            for offset in range(num_pagares):
                fecha_pagare = fecha_inicial + relativedelta(months=offset)
                nombre_mes = fecha_pagare.strftime("%B")
                if offset == 0:
                    dia_mes = fecha_inicial.day
                else:
                    dia_mes = min(dia_pago, monthrange(fecha_pagare.year, fecha_pagare.month)[1])
                fechas_iteradas.append((nombre_mes.capitalize(), fecha_pagare.year, dia_mes))

            # Obtener la renta para pasarla a letra
            if "." not in info.renta:
                number = int(info.renta)
                renta_decimal = "00"
                text_representation = num2words(number, lang='es').capitalize()
            else:
                renta_completa = info.renta.split(".")
                number = int(renta_completa[0])
                renta_decimal = renta_completa[1]
                text_representation = num2words(number, lang='es').capitalize()
            
            context = {
                'info': info,
                'dia': dia,
                'lista_fechas': fechas_iteradas,
                'text_representation': text_representation,
                'duracion_meses': duracion_meses,
                'pagare_distinto': pagare_distinto,
                'cantidad_pagare': cantidad_pagare_num,
                'cantidad_letra': cantidad_letra,
                'cantidad_decimal': cantidad_decimal,
                'renta_decimal': renta_decimal,
                **(marca or {}),
            }

            template = 'home/pagare_fraterna.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando pagaré interno: {e}")
            raise e
        
    def renovar_contrato_fraterna(self, request, *args, **kwargs):
        try:
            print("Renovar el contrato pa")
            print("Request",request.data)
            bloqueo_demo = self._guard_demo(request, request.data.get("id"))
            if bloqueo_demo:
                return bloqueo_demo
            instance = self.queryset.get(id = request.data["id"])
            print("mi id es: ",instance.id)
            print(instance.__dict__)
            #Mandar Whats con lo datos del contrato a Miri
            remitente = 'notificaciones@arrendify.com'
            destinatario = 'desarrolloarrendify@gmail.com'

            print(instance.residente.nombre_residente)
            asunto = f"Renovacion de Contrato del arrendatario {instance.residente.nombre_arrendatario}"
            
           
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Subject'] = asunto
            print("paso objeto mime")

            pdf_html = renovacion_aviso_fraterna(instance)

            msg.attach(MIMEText(pdf_html, 'html'))
            print("pase el msg attach 1")
        
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                server.sendmail(remitente, destinatario, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            # proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            # print("proceso",proceso.__dict__)
            # proceso.status_proceso = request.data["status"]
            # proceso.save()
            
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)


class DocumentosArrendamientosFraterna(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendamientosFraternaModel.objects.all()
    serializer_class = FraternaArrendamientosSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendamiento Fraterna....📄")
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list documentos arrendamientos es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Documentos Arrendamiento Fraterna....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            print("FILES ===>", request.FILES)
            
            # Verificar si viene contrato_id directamente (desde Admin Fraterna)
            contrato_id = data.get('contrato_id', None)
            sin_recibo = data.get('sin_recibo', 'false').lower() == 'true'
            numero_pago_manual = data.get('numero_pago', None)
            
            print(f"Contrato ID: {contrato_id}, Sin Recibo: {sin_recibo}, Número Pago Manual: {numero_pago_manual}")
            
            if contrato_id:
                # Flujo para usuario Admin Fraterna con contrato específico
                print(f"Flujo Admin Fraterna - Buscando contrato ID: {contrato_id}")
                try:
                    contrato = FraternaContratos.objects.get(id=contrato_id)
                    arrendatario = contrato.residente
                    print(f"Contrato y residente encontrados: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm}")
                except FraternaContratos.DoesNotExist:
                    return Response({'error': f'Contrato ID {contrato_id} no encontrado'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Flujo original para usuarios normales
                # Usar first_name del usuario autenticado para buscar arrendatario
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                # Intentar diferentes estrategias de búsqueda
                arrendatario = None
                
                # Estrategia 1: Buscar por nombre completo
                arrendatario = Residentes.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario)
                ).first()
                
                # Estrategia 2: Si no encuentra, buscar por primer nombre
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    print(f"Buscando por primer nombre: {primer_nombre}")
                    arrendatario = Residentes.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(nombre_empresa_pm__icontains=primer_nombre)
                    ).first()
                
                # Estrategia 3: Si aún no encuentra, buscar por palabras individuales
                if not arrendatario:
                    palabras = nombre_usuario.split()
                    for palabra in palabras:
                        if len(palabra) > 2:  # Solo palabras de más de 2 caracteres
                            print(f"Buscando por palabra: {palabra}")
                            arrendatario = Residentes.objects.filter(
                                Q(nombre_arrendatario__icontains=palabra) |
                                Q(nombre_empresa_pm__icontains=palabra)
                            ).first()
                            if arrendatario:
                                break
                
                # Estrategia 4: Buscar por relación directa con el usuario
                if not arrendatario:
                    print("Buscando arrendatario asociado directamente al usuario")
                    arrendatario = Residentes.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                print(f"Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm} (ID: {arrendatario.id})")
                
                # Buscar contrato relacionado
                try:
                    contrato = FraternaContratos.objects.get(residente=arrendatario)
                    print(f"Contrato encontrado: {contrato.id}")
                except FraternaContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Buscar proceso relacionado
            try:
                proceso = ProcesoContrato.objects.get(contrato=contrato)
                print(f"Proceso encontrado: {proceso.id}")
            except ProcesoContrato.DoesNotExist:
                return Response({'error': f'Proceso no encontrado para el contrato ID: {contrato.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            duracion_meses = self.extraer_duracion_meses(contrato.duracion)
            print(f"Duración extraída: {duracion_meses} meses")

            # Determinar número de pago
            if numero_pago_manual:
                # Usar número de pago manual si viene
                numero_pago_actual = int(numero_pago_manual)
                print(f"Usando número de pago manual: {numero_pago_actual}")
                
                # VALIDACIÓN: Verificar que no exista ya un pago con este número
                pago_existente = self.get_queryset().filter(
                    contrato=contrato,
                    proceso=proceso,
                    numero_pago=numero_pago_actual
                ).first()
                
                if pago_existente:
                    return Response({
                        'error': f'Ya existe un pago registrado con el número {numero_pago_actual} para este contrato',
                        'detalles': {
                            'numero_pago': numero_pago_actual,
                            'contrato_id': contrato.id,
                            'proceso_id': proceso.id,
                            'fecha_registro': pago_existente.dateTimeOfUpload.strftime('%Y-%m-%d %H:%M:%S') if pago_existente.dateTimeOfUpload else 'N/A'
                        }
                    }, status=status.HTTP_400_BAD_REQUEST)
                
            else:
                # Contar pagos existentes para este contrato
                pagos_existentes = DocumentosArrendamientosFraternaModel.objects.filter(contrato=contrato).count()
                numero_pago_actual = pagos_existentes + 1
                print(f"Número de pago calculado automáticamente: {numero_pago_actual}")

            # Calcular renta total
            renta_total = Decimal(str(contrato.renta)) * duracion_meses if contrato.renta else Decimal('0')

            # Calcular interés por retraso (12% anual) - SOLO si no es un pago sin recibo
            interes_aplicado = Decimal('0')
            fecha_vencimiento = datetime.now().date() + timedelta(days=30)  # 30 días para pagar

            if not sin_recibo:  # Solo calcular intereses si hay recibo físico
                # Verificar si hay retraso en pagos anteriores
                if numero_pago_actual > 1:
                    ultimo_pago = DocumentosArrendamientosFraternaModel.objects.filter(
                        contrato=contrato
                    ).order_by('-dateTimeOfUpload').first()
                    
                    if ultimo_pago and ultimo_pago.fecha_vencimiento:
                        dias_retraso = (datetime.now().date() - ultimo_pago.fecha_vencimiento).days
                        if dias_retraso > 0:
                            # Aplicar 12% anual = 1% mensual
                            interes_mensual = Decimal('0.01')
                            meses_retraso = Decimal(str(dias_retraso)) / Decimal('30')
                            interes_aplicado = Decimal(str(contrato.renta)) * interes_mensual * meses_retraso
            
            # Obtener archivo - puede ser None si sin_recibo=true
            comp_pago_file = request.FILES.get('comp_pago', None)
            
            # Validar que si no es sin_recibo, debe venir archivo
            if not sin_recibo and not comp_pago_file:
                return Response({
                    'error': 'Se requiere archivo de recibo para registrar el pago'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Obtener referencia de pago del request
            referencia_pago = data.get('referencia_pago', '')
            print(f"📝 Referencia de pago recibida: '{referencia_pago}'")
            
            # Crear documento
            documento_data = {
                "user": user_session.id,
                "arrendatario": arrendatario.id,
                "contrato": contrato.id,
                "proceso": proceso.id,
                "comp_pago": comp_pago_file,  # Puede ser None si sin_recibo=true
                "referencia_pago": referencia_pago,  
                "numero_pago": numero_pago_actual,
                "total_pagos": duracion_meses,
                "renta_total": renta_total,
                "interes_aplicado": interes_aplicado,
                "fecha_vencimiento": fecha_vencimiento,
            }
            
            tipo_registro = "SIN RECIBO" if sin_recibo else "CON RECIBO"
            print(f"Pago {numero_pago_actual} de {duracion_meses} ({tipo_registro}) - Renta total: ${renta_total} - Interés: ${interes_aplicado}")
            
            arrendamientos_serializer = self.get_serializer(data=documento_data)
            arrendamientos_serializer.is_valid(raise_exception=True)
            arrendamientos_serializer.save()
            
            print("Documento ligado correctamente....✅")
            return Response(arrendamientos_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def extraer_duracion_meses(self, duracion_texto):
        """
        Extrae la duración en meses de un texto.
        Ejemplos: "6 meses" -> 6, "12 meses" -> 12, "24 meses" -> 24
        """
        if not duracion_texto:
            return 1
        
        # Convertir a string y buscar números
        texto = str(duracion_texto).lower().strip()
        
        # Buscar números en el texto
        numeros = re.findall(r'\d+', texto)
        
        if numeros:
            duracion = int(numeros[0])
            # Validar que sea un número razonable (entre 1 y 60 meses)
            if 1 <= duracion <= 60:
                return duracion
            else:
                print(f"Advertencia: Duración inusual detectada: {duracion} meses")
                return duracion
        
        # Si no encuentra números, intentar palabras
        palabras_meses = {
            'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6,
            'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10, 'once': 11, 'doce': 12,
            'dieciocho': 18, 'veinticuatro': 24, 'treinta': 30, 'treinta y seis': 36
        }
        
        for palabra, valor in palabras_meses.items():
            if palabra in texto:
                return valor
        
        print(f"No se pudo extraer duración de: '{duracion_texto}', usando 1 mes por defecto")
        return 1
        
    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            print("Eliminando Documentos Arrendamiento Garza Sada....🗑️")
            documentos_arrendamiento = self.get_object()
            documento_arrendamiento_serializer = self.serializer_class(documentos_arrendamiento)
            if documentos_arrendamiento:
                comp_pago = documento_arrendamiento_serializer.data['comp_pago']
                print("Eliminando Comprobante de Pago....", comp_pago)
                
                documentos_arrendamiento.delete()
                print("Documentos Arrendamiento Garza Sada eliminados correctamente....✅")
                return Response({'message': 'Archivo eliminado correctamente'}, status=204) 
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:  
            print(f"el error es en documentos arrendamiento destroy es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando Documentos Arrendatario Garza Sada....🔄")
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print("Datos Actuales ====>",request.data)
            
            # Verificar si se proporciona un nuevo archivo adjunto
            keys = request.data.keys()
    
            # Convertir las llaves a una lista y obtener la primera
            first_key = list(keys)[0]
            #first_key = str(first_key)
            print(first_key)
            
            # Acceder dinámicamente al atributo de instance usando first_key
            if hasattr(instance, first_key):
                archivo_anterior = getattr(instance, first_key)
                print("Archivo anterior ====>", archivo_anterior)
                eliminar_archivo_s3(archivo_anterior)
                print("Archivo eliminado de S3 desde Fraterna....✅")
            else:
                print(f"El atributo '{first_key}' no existe en la instancia.")
            
            serializer.update(instance, serializer.validated_data)
            print("Se actualizó correctamente el documento del residente Fraterna....✅")
            return Response(serializer.data)

        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], url_path='reporte_completo_fraterna')
    def reporte_completo(self, request):
        """Genera reporte PDF completo de arrendamientos Fraterna"""
        try:
            from django.http import HttpResponse
            from django.template.loader import render_to_string
            from weasyprint import HTML
            from collections import defaultdict
            
            print("Generando reporte completo Fraterna....📊")
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            arrendatario_id = request.query_params.get('arrendatario_id', None)
            queryset = DocumentosArrendamientosFraternaModel.objects.select_related('arrendatario', 'contrato', 'proceso')
            if es_admin:
                if arrendatario_id:
                    queryset = queryset.filter(arrendatario_id=arrendatario_id)
            else:
                nombre_usuario = request.user.first_name.strip()
                arrendatario = Residentes.objects.filter(Q(nombre_arrendatario__icontains=nombre_usuario) | Q(nombre_residente__icontains=nombre_usuario) | Q(user=request.user)).first()
                if not arrendatario:
                    return Response({'error': 'No se encontró información'}, status=status.HTTP_404_NOT_FOUND)
                queryset = queryset.filter(arrendatario=arrendatario)
            
            recibos = queryset.order_by('arrendatario__nombre_arrendatario', 'numero_pago')
            arrendatarios_data = defaultdict(lambda: {'arrendatario': {}, 'contrato': {}, 'recibos': [], 'estadisticas': {'total_pagos': 0, 'pagos_realizados': 0, 'pagos_pendientes': 0, 'renta_mensual': 0, 'renta_total': 0, 'total_pagado': 0, 'total_pendiente': 0, 'interes_total': 0, 'porcentaje_completado': 0}})
            
            for recibo in recibos:
                if not recibo.arrendatario:
                    continue
                arr_id = recibo.arrendatario.id
                
                if not arrendatarios_data[arr_id]['arrendatario']:
                    nombre = recibo.arrendatario.nombre_arrendatario or recibo.arrendatario.nombre_residente or 'Sin nombre'
                    email = recibo.arrendatario.correo_arrendatario or recibo.arrendatario.correo_residente or 'No especificado'
                    telefono = recibo.arrendatario.celular_arrendatario or recibo.arrendatario.celular_residente or 'No especificado'
                    tipo = 'Persona Física' if recibo.arrendatario.nombre_arrendatario else 'Residente'
                    arrendatarios_data[arr_id]['arrendatario'] = {'nombre': nombre, 'email': email, 'telefono': telefono, 'tipo': tipo}
                
                if recibo.contrato and not arrendatarios_data[arr_id]['contrato']:
                    contrato = recibo.contrato
                    arrendatarios_data[arr_id]['contrato'] = {'no_depa': contrato.no_depa or 'N/A', 'duracion': contrato.duracion or 'No especificada', 'fecha_celebracion': contrato.fecha_celebracion.strftime('%d/%m/%Y') if contrato.fecha_celebracion else 'N/A', 'fecha_vigencia': contrato.fecha_vigencia.strftime('%d/%m/%Y') if contrato.fecha_vigencia else 'N/A', 'renta': float(contrato.renta) if contrato.renta else 0}
                
                estado = 'Sin fecha'
                dias_retraso = 0
                if recibo.fecha_vencimiento:
                    hoy = date.today()
                    dias_restantes = (recibo.fecha_vencimiento - hoy).days
                    if dias_restantes < 0:
                        estado = 'Vencido'
                        dias_retraso = abs(dias_restantes)
                    elif dias_restantes <= 7:
                        estado = 'Próximo a vencer'
                    else:
                        estado = 'Al día'
                
                renta_mensual = float(recibo.contrato.renta) if recibo.contrato and recibo.contrato.renta else 0
                interes_aplicado = float(recibo.interes_aplicado) if recibo.interes_aplicado else 0
                monto_pagado = renta_mensual if recibo.comp_pago else 0
                monto_pendiente = renta_mensual - monto_pagado
                usuario_subio = recibo.user.first_name or recibo.user.username if recibo.user else 'Sin usuario'
                referencia_pago = recibo.referencia_pago if recibo.referencia_pago else f"FR-{recibo.id:06d}" if recibo.id else 'N/A'
                
                recibo_data = {'numero_pago': recibo.numero_pago or 0, 'fecha_subida': recibo.dateTimeOfUpload.strftime('%d/%m/%Y %H:%M') if recibo.dateTimeOfUpload else 'N/A', 'fecha_vencimiento': recibo.fecha_vencimiento.strftime('%d/%m/%Y') if recibo.fecha_vencimiento else 'N/A', 'interes': interes_aplicado, 'estado': estado}
                
                if es_admin:
                    recibo_data.update({'departamento': recibo.contrato.no_depa if recibo.contrato else 'N/A', 'referencia_pago': referencia_pago, 'monto': renta_mensual, 'monto_pagado': monto_pagado, 'monto_pendiente': monto_pendiente, 'dias_retraso': dias_retraso, 'penalizacion': interes_aplicado, 'usuario': usuario_subio})
                
                arrendatarios_data[arr_id]['recibos'].append(recibo_data)
                stats = arrendatarios_data[arr_id]['estadisticas']
                stats['total_pagos'] = recibo.total_pagos or 0
                stats['pagos_realizados'] = len(arrendatarios_data[arr_id]['recibos'])
                stats['pagos_pendientes'] = stats['total_pagos'] - stats['pagos_realizados']
                stats['renta_total'] = float(recibo.renta_total) if recibo.renta_total else 0
                stats['interes_total'] += interes_aplicado
                if recibo.contrato and recibo.contrato.renta:
                    stats['renta_mensual'] = float(recibo.contrato.renta)
                    stats['total_pagado'] = stats['renta_mensual'] * stats['pagos_realizados']
                    stats['total_pendiente'] = stats['renta_mensual'] * stats['pagos_pendientes']
                if stats['total_pagos'] > 0:
                    stats['porcentaje_completado'] = round((stats['pagos_realizados'] / stats['total_pagos']) * 100, 1)
            
            pagos_atrasados = sum(1 for arr in arrendatarios_data.values() for r in arr['recibos'] if r.get('estado') == 'Vencido')
            totales_generales = {'total_arrendatarios': len(arrendatarios_data), 'total_recibos': recibos.count(), 'ingresos_totales': sum(arr['estadisticas']['total_pagado'] for arr in arrendatarios_data.values()), 'pendientes_totales': sum(arr['estadisticas']['total_pendiente'] for arr in arrendatarios_data.values()), 'intereses_totales': sum(arr['estadisticas']['interes_total'] for arr in arrendatarios_data.values()), 'contratos_por_vencer': 0, 'pagos_atrasados': pagos_atrasados}
            context = {'arrendatarios': list(arrendatarios_data.values()), 'totales': totales_generales, 'fecha_generacion': datetime.now().strftime('%d/%m/%Y %H:%M'), 'usuario_generador': request.user.first_name or request.user.username}
            template_name = 'home/reporte_arrendamientos_fraterna_admin.html' if es_admin else 'home/reporte_arrendamientos_fraterna.html'
            html_string = render_to_string(template_name, context)
            html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
            pdf = html.write_pdf()
            response = HttpResponse(pdf, content_type='application/pdf')
            filename_suffix = '_admin' if es_admin else ''
            response['Content-Disposition'] = f'attachment; filename="reporte_fraterna{filename_suffix}_{date.today().strftime("%Y%m%d")}.pdf"'
            print("Reporte Fraterna generado exitosamente....✅")
            return response
        except Exception as e:
            print(f"Error al generar reporte Fraterna: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en reporte Fraterna: {e}")
            return Response({'error': f'Error al generar el reporte: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='lista_arrendatarios_fraterna')
    def lista_arrendatarios(self, request):
        """Lista de residentes Fraterna con contratos"""
        try:
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            if not es_admin:
                return Response({'error': 'Sin permisos'}, status=status.HTTP_403_FORBIDDEN)
            
            arrendatarios = Residentes.objects.filter(residente_contrato__isnull=False).distinct().values('id', 'nombre_arrendatario', 'nombre_residente')
            lista = [{'id': arr['id'], 'nombre': arr['nombre_arrendatario'] or arr['nombre_residente']} for arr in arrendatarios if arr['nombre_arrendatario'] or arr['nombre_residente']]
            print(f"Residentes Fraterna: {len(lista)}")
            return Response(lista, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error lista Fraterna: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class IncidenciasFraterna(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = IncidenciasFraternaModel.objects.all()
    serializer_class = IncidenciasFraternaSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendamiento Garza Sada....📄")
            queryset = self.filter_queryset(self.get_queryset())
            IncidenciasSerializers = self.get_serializer(queryset, many=True)
            return Response(IncidenciasSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list documentos arrendamientos es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Solicitud de Incidencia....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            
            # Verificar si es usuario autorizado para incidencias Arrendify
            usuarios_autorizados = ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            es_usuario_autorizado = (
                user_session.is_staff or 
                user_session.is_superuser or 
                user_session.username in usuarios_autorizados or
                getattr(user_session, 'pertenece_a', None) in usuarios_autorizados
            )
            
            arrendatario = None
            contrato = None
            
            if es_usuario_autorizado:
                print(f"Usuario autorizado para incidencias Arrendify: {user_session.username}")
                # Para usuarios autorizados, usar arrendatario/contrato del request si se proporcionan
                arrendatario_id = data.get('arrendatario', None)
                contrato_id = data.get('contrato', None)
                
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": arrendatario_id,
                    "contrato": contrato_id,
                    "incidencia": data.get('incidencia', ''),
                    "tipo_incidencia": data.get('tipo_incidencia', ''),
                    "prioridad": data.get('prioridad', 'Media'),
                    "status": "Pendiente de Revisión",
                }
                print(f"Creando incidencia Arrendify - User={user_session.id}, Arrendatario={arrendatario_id}, Contrato={contrato_id}")
            else:
                # Lógica original para usuarios regulares
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                # Intentar diferentes estrategias de búsqueda
                arrendatario = None
                
                # Estrategia 1: Buscar por nombre completo
                arrendatario = Residentes.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario)
                ).first()
                
                # Estrategia 2: Si no encuentra, buscar por primer nombre
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    print(f"Buscando por primer nombre: {primer_nombre}")
                    arrendatario = Residentes.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(nombre_empresa_pm__icontains=primer_nombre)
                    ).first()
                
                # Estrategia 3: Si aún no encuentra, buscar por palabras individuales
                if not arrendatario:
                    palabras = nombre_usuario.split()
                    for palabra in palabras:
                        if len(palabra) > 2:  # Solo palabras de más de 2 caracteres
                            print(f"Buscando por palabra: {palabra}")
                            arrendatario = Residentes.objects.filter(
                                Q(nombre_arrendatario__icontains=palabra) |
                                Q(nombre_empresa_pm__icontains=palabra)
                            ).first()
                            if arrendatario:
                                break
                
                # Estrategia 4: Buscar por relación directa con el usuario
                if not arrendatario:
                    print("Buscando arrendatario asociado directamente al usuario")
                    arrendatario = Residentes.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                print(f"Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm} (ID: {arrendatario.id})")
                
                # Buscar contrato relacionado
                try:
                    contrato = FraternaContratos.objects.get(arrendatario=arrendatario)
                    print(f"Contrato encontrado: {contrato.id}")
                except FraternaContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Crear Incidencia para usuario regular
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": arrendatario.id,
                    "contrato": contrato.id,
                    "incidencia": data.get('incidencia', ''),
                    "status": "Pendiente de Revisión",
                }
                print(f"Creando incidencia regular con: User={user_session.id}, Arrendatario={arrendatario.id}, Contrato={contrato.id}")
            
            arrendamientos_serializer = self.get_serializer(data=incidencia_data)
            arrendamientos_serializer.is_valid(raise_exception=True)
            arrendamientos_serializer.save()
            
            print("Incidencia creada exitosamente....✅")
            return Response(arrendamientos_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST) 


    @action(detail=False, methods=['get'], url_path='pendientes')
    def pendientes(self, request):
        """GET -- cuantas incidencias siguen sin dictaminar. Nada mas.

        Existe aparte de list() porque lo pide el SIDEBAR en cada carga de
        pagina, y list() serializa el contrato y la ficha COMPLETOS de cada
        incidencia (con PII del residente). Aqui es un COUNT y ya.

        Sin estatus tambien cuenta: nadie la ha dictaminado, asi que sigue
        siendo trabajo pendiente — es el mismo criterio que usa la bandeja.

        Devuelve 0 en vez de 403 a quien no opera Fraterna: es una insignia del
        menu, no un dato; que reviente el sidebar entero por esto seria peor.
        """
        try:
            if not _puede_revisar_recibos(request.user):
                return Response({'pendientes': 0}, status=status.HTTP_200_OK)
            n = IncidenciasFraternaModel.objects.filter(
                Q(status='Pendiente de Revisión') | Q(status__isnull=True) | Q(status='')
            ).count()
            return Response({'pendientes': n}, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"error en pendientes de incidencias: {e}")
            return Response({'pendientes': 0}, status=status.HTTP_200_OK)


########################## F R A T E R N A ######################################        

########################## S E M I L L E R O  P U R I S I M A ######################################
class Arrendatarios_semilleroViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Arrendatarios_semillero.objects.all()
    serializer_class = Arrentarios_semilleroSerializers
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
                print("Esta entrando a listar Residentes")
                arrendatarios =  self.get_queryset().order_by('-id')
                serializer = self.get_serializer(arrendatarios, many=True)
                return Response(serializer.data, status= status.HTTP_200_OK)
            
           elif user_session.rol == "Inmobiliaria":
                #tengo que busca a los inquilinos que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de Residentes propios y registrados por mis agentes
                inquilinos_a_cargo = self.get_queryset().filter(user_id__in = agentes)
                inquilinos_mios = self.get_queryset().filter(user_id = user_session)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
                mios = mios.order_by('-id')
               
                serializer = self.get_serializer(mios, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                
                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['inmobiliaria'] = True
                    
                return Response(serialized_data)      
            
           elif user_session.rol == "Agente":  
                print("soy Agente", user_session.first_name)
                #obtengo mis inquilinos
                residentes_ag = self.get_queryset().filter(user_id = user_session).order_by('-id')
              
                #tengo que obtener a mis inquilinos vinculados
              
                serializer = self.get_serializer(residentes_ag, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)
         
           return Response(serializer.data, status= status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print("Llegando a create de arrendatarios semillero")
            print(request.data)
            arrendatarios_semillero_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            print(arrendatarios_semillero_serializer)
            if arrendatarios_semillero_serializer.is_valid(raise_exception=True):
                arrendatarios_semillero_serializer.save(user = user_session)
                print("Guardado arrendatarios_semillero")
                return Response({'arrendatarios_semilleros': arrendatarios_semillero_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion")
                return Response({'errors': arrendatarios_semillero_serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def update(self, request, *args, **kwargs):
        try:
            print("Esta entrando a actualizar Residentes")
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print(request.data)
            instance = self.get_object()
            print("instance",instance)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            print(serializer)
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("edito residente")
                # return redirect('myapp:my-url')
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            user_session = request.user
            print("Entrando a retrieve")
            modelos = Residentes.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            Residentes = modelos.filter(slug=slug)
            if Residentes:
                serializer_Residentes = ResidenteSerializers(Residentes, many=True)
                return Response(serializer_Residentes.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            print("LLegando a eliminar residente")
            Residentes = self.get_object()
            if Residentes:
                Residentes.delete()
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
  
    def mandar_aprobado(self, request, *args, **kwargs):  
        try:
            print("Aprobar al residente")
            info = request.data
            print("el id que llega", info )
            print("accediendo a informacion", info["estado_civil"])
            today = date.today().strftime('%d/%m/%Y')
            ingreso = int(info["ingreso"])
            ingreso_texto = num2words(ingreso, lang='es').capitalize()
            context = {'info': info, "fecha_consulta":today, 'ingreso':ingreso, 'ingreso_texto':ingreso_texto}
        
            # Renderiza el template HTML  
            template = 'home/aprobado_fraterna.html'
    
            html_string = render_to_string(template, context)# lo comvertimos a string
            pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
            print("pdf realizado")
            
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
            print("antes de enviar_archivo",context)
            self.enviar_archivo(archivo, info)
            print("PDF ENVIADO")
            return Response({'Mensaje': 'Todo Bien'},status= status.HTTP_200_OK)
        
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
                  
    def enviar_archivo(self, archivo, info, comentario="nada"):
        print("")
        print("entrando a enviar archivo")
        print("soy pdf content",archivo)
        print("soy comentario",comentario)
        arrendatario = info["nombre_arrendatario"]
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            # destinatario = 'jsepulvedaarrendify@gmail.com'
            destinatario = 'legal@fraterna.mx'
            # destinatario2 = 'juridico.arrendify1@gmail.com'
            destinatario2 = 'smosqueda@fraterna.mx'
            
            
            asunto = f"Resultado Investigación Arrendatario {arrendatario}"
            
            destinatarios = [destinatario,destinatario2]
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Cc'] = destinatario2
            msg['Subject'] = asunto
            print("paso objeto mime")
           
            # Estilo del mensaje
            #variable resultado_html_fraterna
            pdf_html = aprobado_fraterna(info)
          
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("pase el msg attach 1")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Resultado_investigación.pdf')
            msg.attach(pdf_part)
            print("pase el msg attach 2")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                server.sendmail(remitente, destinatarios, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})
        
class DocumentosArrendatario_semillero(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendatarios_semilleros.objects.all()
    serializer_class = DASSerializer
   
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def create (self, request, *args,**kwargs):
        try: 
            user_session = str(request.user.id)
            data = request.data
            data = {
                    "Ine_arrendatario": request.FILES.get('Ine_arrendatario', None),
                    "Ine_obligado": request.FILES.get('Ine_obligado', None),
                    "Comp_dom_arrendatario": request.FILES.get('Comp_dom_arrendatario', None),
                    "Comp_dom_obligado": request.FILES.get('Comp_dom_obligado', None),
                    "Rfc_arrendatario": request.FILES.get('Rfc_arrendatario', None),
                    "Ingresos_arrendatario": request.FILES.get('Ingresos_arrendatario', None),
                    "Ingresos2_arrendatario": request.FILES.get('Ingresos2_arrendatario', None),
                    "Ingresos3_arrendatario": request.FILES.get('Ingresos3_arrendatario', None),
                    "Ingresos_obligado": request.FILES.get('Ingresos_obligado', None),
                    "Ingresos2_obligado": request.FILES.get('Ingresos_obligado2', None),
                    "Ingresos3_obligado": request.FILES.get('Ingresos_obligado3', None),
                    "Extras": request.FILES.get('Extras', None),
                    "Recomendacion_laboral": request.FILES.get('Recomendacion_laboral', None),
                    "arrendatario":request.data['arrendatario'],
                    "user":user_session
                }
          
            if data:
                documentos_serializer = self.get_serializer(data=data)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save()
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            documentos_inquilinos = self.get_object()
            documento_inquilino_serializer = self.serializer_class(documentos_inquilinos)
            print("Soy ine", documento_inquilino_serializer.data['ine'])
            print("1")
            if documentos_inquilinos:
                ine = documento_inquilino_serializer.data['ine']
                print("Soy ine 2", ine)
                comp_dom= documento_inquilino_serializer.data['comp_dom']
                rfc= documento_inquilino_serializer.data['escrituras_titulo']
                print("Soy RFC", rfc)
                ruta_ine = 'apps/static'+ ine
                print("Ruta ine", ruta_ine)
                ruta_comprobante_domicilio = 'apps/static'+ comp_dom
                ruta_rfc = 'apps/static'+ rfc
                print("Ruta com", ruta_comprobante_domicilio)
                print("Ruta RFC", ruta_rfc)
            
                # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
                documentos_inquilinos.delete()
                return Response({'message': 'Archivo eliminado correctamente'}, status=204)
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
        
    def retrieve(self, request, pk=None):
        try:
            documentos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            inquilino = documentos.filter(id=pk)
            serializer_inquilino = DISerializer(inquilino, many=True)
            print(serializer_inquilino.data)
            ine = serializer_inquilino.data[0]['ine']
            print(ine)
            # documentos_arrendador = self.get_object()
            # print(documentos_arrendador)
            return Response(serializer_inquilino.data)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
   
    def update(self, request, *args, **kwargs):
        try:
            print("Entre en el update")
            instance = self.get_object()
            print("paso instance")
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print(request.data)
            
            # Verificar si se proporciona un nuevo archivo adjunto
            keys = request.data.keys()
    
            # Convertir las llaves a una lista y obtener la primera
            first_key = list(keys)[0]
            #first_key = str(first_key)
            print(first_key)
            
            # Acceder dinámicamente al atributo de instance usando first_key
            if hasattr(instance, first_key):
                archivo_anterior = getattr(instance, first_key)
                print("arc", archivo_anterior)
                eliminar_archivo_s3(archivo_anterior)
            else:
                print(f"El atributo '{first_key}' no existe en la instancia.")
            
            print("archivo",archivo_anterior)
            serializer.update(instance, serializer.validated_data)
            print("finalizado")
            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
#////////////////////////CONTRATOS SEMILLERO///////////////////////////////
class Contratos_semillero(viewsets.ModelViewSet):
    # authentication_classes = [TokenAuthentication, SessionAuthentication]
    # permission_classes = [IsAuthenticated]
    queryset = SemilleroContratos.objects.all()
    serializer_class = ContratoSemilleroSerializer
    
    def list(self, request, *args, **kwargs):
        try:
           user_session = request.user       
           if user_session.is_staff:
               print("Esta entrando a listar cotizacion")
               contratos =  SemilleroContratos.objects.all().order_by('-id')
               serializer = self.get_serializer(contratos, many=True)
               serialized_data = serializer.data
                
               # Agregar el campo 'is_staff'
               for item in serialized_data:
                 item['is_staff'] = True
                
               return Response(serialized_data)
           
           elif user_session.rol == "Inmobiliaria":
               #primero obtenemos mis agentes.
               print("soy inmobiliaria en listar contratos", user_session.name_inmobiliaria)
               agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
               #obtenemos los contratos
               contratos_mios = SemilleroContratos.objects.filter(user_id = user_session.id)
               contratos_agentes = SemilleroContratos.objects.filter(user_id__in = agentes.values("id"))
               contratos_all = contratos_mios.union(contratos_agentes)
               contratos_all = contratos_all.order_by('-id')
               
               print("es posible hacer esto:", contratos_all)
               
               serializer = self.get_serializer(contratos_all, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
               
           elif user_session.rol == "Agente":
               print(f"soy Agente: {user_session.first_name} en listar contrato")
               residentes_ag = SemilleroContratos.objects.filter(user_id = user_session).order_by('-id')
              
               serializer = self.get_serializer(residentes_ag, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print(user_session)
            print("RD",request.data)
            print("Request",request)
            print("Llegando a create de contrato para fraterna")
            
            fecha_actual = date.today()
            contrato_serializer = self.serializer_class(data = request.data) #Usa el serializer_class
            if contrato_serializer.is_valid():
                nuevo_proceso = ProcesoContrato_semillero.objects.create(usuario = user_session, fecha = fecha_actual, status_proceso = "En Revisión")
                if nuevo_proceso:
                    print("ya la armamos")
                    print(nuevo_proceso.id)
                    info = contrato_serializer.save(user = user_session)
                    nuevo_proceso.contrato = info
                    nuevo_proceso.save()
                    #send_noti_varios(FraternaContratos, request, title="Nueva solicitud de contrato en Fraterna", text=f"A nombre del Arrendatario {info.residente.nombre_arrendatario}", url = f"fraterna/contrato/#{info.residente.id}_{info.cama}_{info.no_depa}")
                    print("despues de metodo send_noti")
                    print("Se Guardado solicitud")
                    return Response({'Semillero': contrato_serializer.data}, status=status.HTTP_201_CREATED)
                else:
                    print("no se creo el proceso")
                    return Response({'msj':'no se creo el proceso'}, status=status.HTTP_204_NO_CONTENT) 
            
            else:
                print("serializer no valido")
                return Response({'msj':'no es valido el serializer'}, status=status.HTTP_204_NO_CONTENT)     
            
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try:
            #primero verificamos que tenga contadores activos
            print("Esta entrando a actualizar Contratos Semillero")
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
           
                        
            proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            print("el contador es: ",proceso.contador)
            if (proceso.contador > 0 ):
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                if serializer.is_valid(raise_exception=True):
                    self.perform_update(serializer)
                    #proceso.contador = proceso.contador - 1
                    #proceso.save()
                    print("edito proceso contrato")
                    #send_noti_varios(SemilleroContratos, request, title="Se a modificado el contrato de:", text=f"FRATERNA VS {instance.residente.nombre_arrendatario} - {instance.residente.nombre_residente}".upper(), url = f"fraterna/contrato/#{instance.residente.id}_{instance.cama}_{instance.no_depa}")
                    return Response(serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response({'errors': serializer.errors})
            else:
                return Response({'msj': 'LLegaste al limite de tus modificaciones en el proceso'}, status=status.HTTP_205_RESET_CONTENT)
      
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy(self,request, *args, **kwargs):
        try:
            residente = self.get_object()
            if residente:
                residente.delete()
                return Response({'message': 'residente eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def aprobar_contrato_semillero(self, request, *args, **kwargs):
        try:
            print("update status contrato")
            print("Request",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("mi id es: ",instance.id)
            print(instance.__dict__)
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def desaprobar_contrato_semillero(self, request, *args, **kwargs):
        try:
            print("desaprobar Contrato")
            instance = self.queryset.get(id = request.data["id"])
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = "En Revisión"
            # proceso.contador = 2 # en vista que me indiquen lo contrario lo dejamos asi
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a desaprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_pagare_semillero(self, request, *args, **kwargs):
        try:
            #activamos la libreri de locale para obtener el mes en español
            print("Generar Pagare Semillero")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            print("rd",request.data)
            id_paq = request.data["id"]
            pagare_distinto = request.data["pagare_distinto"]

            if pagare_distinto == "Si":
                if "." not in request.data["cantidad_pagare"]:
                    print("no hay yaya pagare")
                    cantidad_pagare = request.data["cantidad_pagare"]
                    cantidad_decimal = "00"
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
                
                else:
                    cantidad_completa = request.data["cantidad_pagare"].split(".")
                    cantidad_pagare = cantidad_completa[0]
                    cantidad_decimal = cantidad_completa[1]
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
            else:
                cantidad_pagare = 0
                cantidad_decimal = "00"
                cantidad_letra = num2words(cantidad_pagare, lang='es')
            print(pagare_distinto)
            print(cantidad_pagare)
            
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)
            # Definir la fecha inicial
            fecha_inicial = info.fecha_celebracion
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
            if "." not in info.renta:
                print("no hay yaya")
                number = int(info.renta)
                renta_decimal = "00"
                text_representation = num2words(number, lang='es').capitalize()
               
            else:
                print("tengo punto en renta")
                renta_completa = info.renta.split(".")
                info.renta = renta_completa[0]
                renta_decimal = renta_completa[1]
                text_representation = num2words(renta_completa[0], lang='es').capitalize()
           
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'pagare_distinto':pagare_distinto , 'cantidad_pagare':cantidad_pagare, 'cantidad_letra':cantidad_letra,'cantidad_decimal':cantidad_decimal, 'renta_decimal':renta_decimal}
            print("pasamos el context")
            
            template = 'home/pagare_semillero.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("generamos correctamente")
            return HttpResponse(response, content_type='application/pdf')
    
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_poliza_semillero(self, request, *args, **kwargs):
        try:
            print("Generar Poliza Semillero")
            print("Data ====>", request.data)
            id_paq = request.data["id"]
            testigo1 = request.data["testigo1"]
            testigo2 = request.data["testigo2"]
            print(testigo1)
            print(testigo2)
            print("el id que llega", id_paq)
            info = self.queryset.filter(id=id_paq).first()
            print(info.__dict__)

            print("vamos a generar el codigo")
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            if info.id < 9:
                info.id = f"0{info.id}"
                print("")
            print("fec", fec)

            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" + f"{info.id}" + "CA" + na
            print("paqueton", nom_paquete.upper())

            # ✅ Conversión correcta de renta
            renta = float(info.renta)
            print("la renta es:", renta)
            parte_entera = int(renta)
            centavos = round((renta - parte_entera) * 100)

            renta_texto = f"{num2words(parte_entera, lang='es')} pesos"
            if centavos > 0:
                renta_texto += f" con {num2words(centavos, lang='es')} centavos"
            renta_texto = renta_texto.capitalize()

            # ✅ Cálculo de la póliza
            if renta > 14999:
                resultado = renta * 0.17
                valor_poliza = int(round(resultado))  # Redondear y convertir a int si se quiere solo entero
                print("resultado esperado", valor_poliza)
            else:
                valor_poliza = 2500

            poliza_texto = num2words(valor_poliza, lang='es').capitalize()

            context = {
                'info': info,
                'renta_texto': renta_texto,
                'nom_paquete': nom_paquete,
                'valor_poliza': valor_poliza,
                'poliza_texto': poliza_texto,
                "testigo1": testigo1,
                "testigo2": testigo2
            }

            template = 'home/poliza_semillero.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO POLIZA")
            return HttpResponse(response, content_type='application/pdf')

        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def generar_contrato_semillero(self, request, *args, **kwargs):
        try:
            print("Generar contrato Semillero")
            print("Data Entrante ====>", request.data)
            id_paq = request.data["id"]
            testigo1 = request.data["testigo1"]
            testigo2 = request.data["testigo2"]
            print("Testigo 1 ====>",testigo1)
            print("Testigo 2 ====>",testigo2)
            print("ID ====>", id_paq)
            info = self.queryset.filter(id=id_paq).first()
            print("Diccionario ====>",info.__dict__)
            
            # 🧠 Convertir renta con centavos a texto
            renta = float(info.renta)
            parte_entera = int(renta)
            centavos = round((renta - parte_entera) * 100)
            renta_texto = f"{num2words(parte_entera, lang='es')} pesos"
            if centavos > 0:
                renta_texto += f" con {num2words(centavos, lang='es')} centavos"
            renta_texto = renta_texto.capitalize()
            
            # Obtener los datos de la vigencia
            vigencia = info.duracion.split(" ")
            num_vigencia = vigencia[0]
            print(num_vigencia)

            print("Generando Codigo de paquete...")
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            if info.id < 9:
                info.id = f"0{info.id}"
            print("Fecha Celebracion ====>", fec)

            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            print("Dia ====>", dia)
            print("Mes ====>", mes)
            print("Año ====>", anio)
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" + f"{info.id}" + "CA" + na
            print("Numero Paquete ====>", nom_paquete.upper())

            context = {
                'info': info,
                'renta_texto': renta_texto,
                'num_vigencia': num_vigencia,
                'nom_paquete': nom_paquete,
                "testigo1": testigo1,
                "testigo2": testigo2
            }
            # Para depurar el contexto
            print("Context ===> ",context)

            template = 'home/contrato_arr_frat.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("Generado con Exito")

            return HttpResponse(response, content_type='application/pdf')

        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST) 
        
    def renovar_contrato_semillero(self, request, *args, **kwargs):
        try:
            print("Renovacion de contrato Semillero")
            print("Data ====>",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("ID ====>",instance.id)
            print(instance.__dict__)
            #Mandar Whats con lo datos del contrato a Miri
            
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_semillero.objects.all().get(contrato_id = instance.id)
            print("Proceso ====>",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)


class InvestigacionSemillero(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Arrendatarios_semillero.objects.all()
    serializer_class = Arrentarios_semilleroSerializers
   
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        if user_session.username == "Arrendatario1" or user_session.username == "Legal" or  user_session.username == "Investigacion" or user_session.username == "AndresMtzO" or user_session.username == "MIRIAM" or user_session.username == "jon_admin" or user_session.username == "SUArrendify" or user_session.username == "Becarios":
            print("USUARIO STAFF")
            qs = request.GET.get('nombre')     
            try:
                if qs:
                    inquilino = Arrendatarios_semillero.objects.all().order_by('-id')
                    serializer = Arrentarios_semilleroSerializers(inquilino, many=True)                    
                    return Response(serializer.data)
                    
                else:
                        print("Listar Investigacion Semillero")
                        investigar = Arrendatario.objects.all().order_by('-id')
                        serializer = InquilinoSerializers(investigar, many=True)
                        return Response(serializer.data)
                
                #    return Response(serializer.data, status= status.HTTP_200_OK)
            except Exception as e:
                print(f"el error es: {e}")
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
                return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'No estas autorizado'}, status=status.HTTP_401_UNAUTHORIZED)
    
    def investigacion_francis(self, request, *args, **kwargs):
        user_session = request.user       
        if user_session.username == "Arrendatario1" or user_session.username == "Legal":
            print("Si eres el elegido")
            qs = request.GET.get('nombre')     
            try:
                if qs:
                    inquilino = Arrendatarios_semillero.objects.all().filter(nombre__icontains = qs)
                    id_inq = []
                    for inq in inquilino:
                        id_inq.append(inq.id)
                    investigar = Investigacion.objects.all().filter(inquilino__in = id_inq)
                    serializer = self.get_serializer(investigar, many=True)
                    return Response(serializer.data)
                    
                else:
                        print("Esta entrando a listar inquilino desde investigacion francis calete")
                        francis = User.objects.all().filter(name_inmobiliaria = "Francis Calete").first()
                        print(francis)
                        print(francis.id)
                        inquilino = Arrendatarios_semillero.objects.all().filter(user_id = francis.id)
                        print(inquilino)
                        id_inq = []
                        for inq in inquilino:
                            id_inq.append(inq.id)
                        investigar = Investigacion.objects.all().filter(inquilino__in = id_inq)
                        # investigar =  Investigacion.objects.filter(user_id = user_session)
                        serializer = self.get_serializer(investigar, many=True)
                        return Response(serializer.data)
                
                #    return Response(serializer.data, status= status.HTTP_200_OK)
            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'No estas autorizado'}, status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        pass
        # try:
        #     print("Esta entrando a actualizar inv")
        #     partial = kwargs.pop('partial', False)
        #     print("partials",partial)
        #     print("soy el request",request.data)
        #     print("soy el status que llega",request.data["status"])
        #     instance = self.get_object()
        #     print("instance",instance)
        #     print("id",instance.id)
            
        #     #Consulata para obtener el inquilino y establecemos fecha de hoy
        #     today = date.today().strftime('%d/%m/%Y')
        #     inquilino_mod =  Arrendatario.objects.all().filter(id = instance.id)
        #     primer_inquilino = inquilino_mod.first()
        #     print("soy nombre de inquilino",primer_inquilino.nombre)
        #     #Consulata para obtener el fiador confirme a la fk y releated name 
        #     fiador = primer_inquilino.aval.all().first()
        #     #primero comprobar si hay aval
        #     if fiador:
        #         print("si hay fiador")
        #         print("yo soy info de los fiadores",fiador.__dict__)
                
        #         #si hay fiador hacemos el proceso de aprobar           
        #         if request.data["status"] == "Aprobado":
        #             print("APROBADO")
        #             primer_inquilino.status = "1"
        #             print("status cambiado",primer_inquilino.status)
        #             primer_inquilino.save()
        #             print("fiador.fiador_obligado",fiador.fiador_obligado)
        #             #asignacion de variables dependiendo del Regimen fiscal del Fiador
        #             if primer_inquilino.p_fom == "Persona Moral":
        #                 print("Soy persona moral")
        #             else: 
                        
        #                 if fiador.fiador_obligado == "Obligado Solidario Persona Moral":
        #                     print("No agregamos nada")
        #                 else:
        #                     ingreso = request.data["roe_inquilino"]
        #                     ine_inquilino = request.data["ine_inquilino"]
        #                     ine_fiador = request.data["ine_fiador"]
                            
        #                     if fiador.recibos == "Si":
        #                         ingreso_obligado = "Recibo de nómina"   
        #                     else:
        #                         ingreso_obligado = "Estado de cuenta" 
        #                         #combierte el salario mensual a letra prospecto
                                
        #                     number = primer_inquilino.ingreso_men
        #                     number = int(number)
        #                     text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
        #                     text_representation = text_representation.capitalize()
        #                     #combierte el salario mensual de aval
        #                     number_2 = fiador.ingreso_men_fiador
        #                     number_2 = int(number_2)
        #                     text_representation2 = num2words(number_2, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
        #                     text_representation2 = text_representation2.capitalize()
        #             print("Pasamo el if de obligado ")
                
        #             #hacer el proceso de enviar archivo especial para persona moral
        #             if primer_inquilino.p_fom == "Persona Moral":
        #                 print("soy persona moral")
        #                 archivo = request.data["doc_rec"]                        
        #                 archivo = request.data["doc_rec"]
        #                 comentario = "nada"
        #                 self.enviar_archivo(archivo,primer_inquilino,comentario)
                           
        #             else:    
        #                 if fiador.fiador_obligado == "Fiador Solidario":
        #                     print("Hola soy Fiador Solidario")
        #                     context = {
        #                     'info':primer_inquilino,
        #                     'fiador':fiador,
        #                     'fecha_actual':today,
        #                     'ine_inquilino':ine_inquilino,
        #                     'ine_fiador':ine_fiador,
        #                     'number': number,
        #                     'number_2': number_2,
        #                     'text_representation': text_representation,
        #                     'text_representation2': text_representation2,
        #                     'ingreso':ingreso,
        #                     'ingreso_obligado':ingreso_obligado,
        #                     'template':"home/aprobado_fiador.html",
        #                     }
        #                     self.generar_archivo(context)  
                        
        #                 elif fiador.fiador_obligado == "Obligado Solidario Persona Fisica":
        #                     context = {
        #                     'info':primer_inquilino,
        #                     'fiador':fiador,
        #                     'fecha_actual':today,
        #                     'ine_inquilino':ine_inquilino,
        #                     'ine_fiador':ine_fiador,
        #                     'number': number,
        #                     'number_2': number_2,
        #                     'text_representation': text_representation,
        #                     'text_representation2': text_representation2,
        #                     'ingreso':ingreso,
        #                     'ingreso_obligado':ingreso_obligado,
        #                     'template':"home/aprobado_obligado.html",
        #                     }
        #                     self.generar_archivo(context)  
                        
        #                 else:
        #                     print("Obligado Solidario Persona Moral")
        #                     print("Otro proceso")
        #                     archivo = request.data["doc_rec"]
        #                     comentario = "nada"
        #                     self.enviar_archivo(archivo,primer_inquilino,comentario)      
                
        #         if request.data["status"] == "Rechazado":
        #             print("rechazado con aval")
        #             primer_inquilino.status = "0"
        #             print("status cambiado",primer_inquilino.status)
        #             primer_inquilino.save()
        #             comentario = request.data["comentario"]
        #             archivo =request.data["doc_rec"]
        #             self.enviar_archivo(archivo,primer_inquilino,comentario)   
                

        #         elif request.data["status"] == "En espera":
        #             primer_inquilino.status = "1"
        #             print("status cambiado",primer_inquilino.status)
        #             primer_inquilino.save()
        #             print("paso save")
        #     # S I N A V A L            
        #     else:
        #         print("no hay aval aprobado")
        #         if request.data["status"] == "Aprobado":
        #             print("APROBADO SIN AVAL")
        #             primer_inquilino.status = "1"
        #             primer_inquilino.fiador = "no hay"
        #             primer_inquilino.save()
        #             print("status cambiado",primer_inquilino.status)
        #             comentario = "nada"
        #             print(comentario)
                    
        #             if "doc_sa" in request.data:
        #                 print("si existo")
        #                 archivo_sa = request.data["doc_sa"]
        #                 print(archivo_sa)
        #             else:
        #                 print("no existo")
        #                 archivo_sa = request.data["doc_rec"] 
        #                 print(archivo_sa)
                    
        #             self.enviar_archivo(archivo_sa,primer_inquilino,comentario)  
                
        #         if request.data["status"] == "Rechazado":
        #                 print("Rechazado sin Aval")
        #                 primer_inquilino.status = "0"
        #                 primer_inquilino.fiador = "no hay"
        #                 print("status cambiado",primer_inquilino.status)
        #                 primer_inquilino.save()
        #                 comentario = request.data["comentario"]
        #                 archivo =request.data["doc_rec"]
        #                 self.enviar_archivo(archivo,primer_inquilino,comentario)    
            
        #         elif request.data["status"] == "En espera":
        #             primer_inquilino.status = "1"
        #             primer_inquilino.fiador = "no hay"
        #             print("status cambiado",primer_inquilino.status)
        #             primer_inquilino.save()
        #             print("paso save")  
            
        #     serializer = self.get_serializer(instance, data=request.data, partial=partial)
            
        #     if serializer.is_valid(raise_exception=True):
        #         self.perform_update(serializer)
        #         print("edite investigacion")
            
        #         return Response(serializer.data, status=status.HTTP_200_OK)
        #     else:
        #         return Response({'errors': serializer.errors})
        # except Exception as e:
        #     return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, pk=None, *args, **kwargs):
        user_session = request.user
        try:
            print("Entrando a retrieve")
            modelos = Investigacion.objects.all() #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            print(pk)
            inv = modelos.filter(id=pk)
            if inv:
                serializer_investigacion = InvestigacionSerializers(inv, many=True)
                return Response(serializer_investigacion.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay investigacion en estos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)             
        
    def enviar_archivo(self, archivo, info, estatus):
        #cuando francis este registrado regresar todo como estaba
        # francis = User.objects.all().filter(name_inmobiliaria = "Francis Calete").first()
        print("Enviar Investigacion Semillero")
        print("PDF ====>",archivo)
        print("Estatus Investigacion ====>",estatus)
        print("DATA ====>",info.__dict__)
        print("ID USUARIO ====>",info.user_id)
   
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            # if info.user_id == francis.id:
            #     print("Es el mismo usuaio, envialo a francis calete")
            #     # destinatario = 'el que meden @francis o algo asi'
            #     pdf_html = contenido_pdf_aprobado_francis(info,estatus)
            #     print("destinatario Francis", destinatario)
            # else:
            #destinatario = 'jsepulvedaarrendify@gmail.com'
            destinatario = info.email
            pdf_html = contenido_pdf_aprobado(info,estatus)
            print("Destinatario ====> ",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
            #Destino=['desarrolloarrendify@gmail.com']
            #Destino=['juridico.arrendify1@gmail.com']
            asunto = f"Resultado Investigación Prospecto {info.nombre_arrendatario}"
            
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = ','.join(Destino)
            msg['Subject'] = asunto
            print("paso objeto mime")
            
            #Evalua si tiene este atributo
            # if hasattr(info, 'fiador'):
            #     print("SOY info.fiador",info.fiador)
            
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("Creacion de Mail ====>")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("Mail Creado ====>")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("TLS ====>")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("LOGIN ====>")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("CORREO ENVIADO ====>")
            return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
    def enviar_archivo_semillero(self, archivo, info, estatus):
        #cuan(do francis este registrado regresar todo como estaba
        print("Enviar Archivo Investigacion Semillero ====>")
        print("PDF ====>",archivo)
        print("Estatus Investigacion ====>",estatus)
        print("INFO Investigacion ====>",info.__dict__)
        print("ID USUARIO ====>",info.user_id)
   
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            destinatario = info.correo_arrendatario
            pdf_html = contenido_pdf_aprobado_semillero(info,estatus)
            print("Destinatario ====>",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
            #Destino=['desarrolloarrendify@gmail.com']
            #Destino=['juridico.arrendify1@gmail.com']
            asunto = f"Resultado Investigación Prospecto {info.nombre_arrendatario}"
            
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = ','.join(Destino)
            msg['Subject'] = asunto
            print("paso objeto mime")
            
            #Evalua si tiene este atributo
            # if hasattr(info, 'fiador'):
            #     print("SOY info.fiador",info.fiador)
            
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("Creacion de Mail ====>")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("Mail Creado ====>")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("TLS ====>")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("LOGIN ====>")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("CORREO ENVIADO ====>")
            return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
        
    def aprobar_residente_semillero(self, request, *args, **kwargs):
        try:
            print("Aprobar Prospecto semillero")
            #Consulata para obtener el inquilino y establecemos fecha de hoy
            today = date.today().strftime('%d/%m/%Y')
            req_dat = request.data
            info = Arrendatarios_semillero.objects.filter(id = req_dat["id"]).first()
            print("DATA ====>",info.__dict__)   
                 
                 
            redes_negativo = req_dat.get("redes_negativo")
            print("DATA ====>",req_dat)
            print("ID DATA ====>", req_dat["id"])
            print("")
            print("Arrendatario ====>",info.nombre_arrendatario)       
            print("Diccionario ====>",info.__dict__)
            print("")                                                                 
            print("")
            print("Redes Negativas ====>", redes_negativo)            
            print("")
            
            requisitos = ['referencia1', 'referencia2', 'referencia3'] # una lista para verificar las referencias 1,2 y 3
            presentes = [req for req in requisitos if req in request.data and request.data[req]]
            print("Referencias presentes ====>",presentes)
            if len(presentes) == 3:
                referencias = "En consideración a lo referido por las referencias podemos constatar que la informacion brindada por el prospecto al inicio del tramite es verídica, lo cual nos permite estimar que cuenta con buenos comentarios hacia su persona."
            elif len(presentes) > 0:
                referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con alguna(s) referencias proporcionadas, por lo tanto, no podemos corroborar por completo la veracidad de la información proporcionada en la solicitud de arrendamiento. "
            else:
                referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con ninguna de las referencias proporcionadas, por lo tanto, no podemos corroborar la veracidad de la información proporcionada en la solicitud de arrendamiento. "
            
            #comentarios de redes para walden
            if redes_negativo:
                redes_negativo = dict(redes_negativo)
                #inicializamos la lista 
                redes_comentarios = []
                #establecemos las frases
                conductas = {
                'conducta_violenta': "Conducta violenta o agresiva: Publicaciones que muestran armas de fuego u otros objetos peligrosos.",
                'conducta_discriminatoria': "Conducta discriminatoria o racista: Comentarios, imágenes o memes que promueven el racismo, sexismo, homofobia, transfobia u otro tipo de discriminación.",
                'contenido_ofensivo_odio': "Contenido ofensivo o de odio: Publicaciones que contienen discursos de odio contra diversos grupos étnicos, religiosos, de orientación sexual, género, etc",
                'bullying_acoso': "Bullying o acoso: Participación en o incitación al acoso, ya sea ciberacoso o en la vida real.",
                'contenido_inapropiado': "Contenido inapropiado o explícito: Publicaciones de contenido sexual explícito o inapropiado.",
                'desinformacion_teoria': "Desinformación y teorías conspirativas: Difusión de información falsa o engañosa, así como la promoción de teorías conspirativas sin fundamento que puedan poner en peligro la tranquilidad y orden dentro de la comunidad.",
                'lenguaje_vulgar': "Lenguaje vulgar o inapropiado: Uso excesivo de lenguaje vulgar o soez en sus publicaciones.",
                'contenido_poco_profesional': "Conducta poco profesional: Publicaciones que muestran comportamientos inapropiados en contextos profesionales.",
                'falta_integridad': "Falta de integridad: Inconsistencias en la información compartida en diferentes plataformas, o indicios de comportamientos engañosos o fraudulentos.",
                'divulgacion_info': "Divulgación de información confidencial: Publicaciones que revelan información privada o confidencial de empresas, clientes o individuos.",
                'exceso_negatividad': "Exceso de negatividad: Publicaciones predominantemente negativas o quejumbrosas.",
                'falta_respeto_priv': "Falta de respeto hacia la privacidad: Compartir información privada de otras personas sin su consentimiento.",
                'ausencia_diversidad': "Ausencia de diversidad y tolerancia: Falta de representación de diversas perspectivas y falta de respeto por la diversidad en sus publicaciones."
                }
                # Bucle para generar las frases basadas en los valores de redes_negativo
                for clave, valor in redes_negativo.items(): #hacemos un for basado en la clave valor del dicciones redes_negativo en el .items al ser un diccionario
                    if valor == "Si" and clave in conductas:
                        frase = conductas[clave]
                        #lo agregamos a la lista redes_comentarios
                        redes_comentarios.append(frase)
                        print("Clave ====>", clave)
                        print("Frase ====>", frase)
                        print("Comentarios Redes ====>", redes_comentarios)
                    elif valor == "Si" and clave not in conductas:
                        print(f"No hay una frase definida para la clave: {clave}")
            else:
                redes_comentarios = "no tengo datos"
                print("Comentarios Redes ====>",redes_comentarios)
        
            #opciones para el score interno de nosotros
            opciones = {
                'Excelente': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_excelente.png",
                'Bueno': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_bueno.png",
                'Regular': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_regular.png",
                'Malo': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_malo.png"
            }
            
            tipo_score_ingreso = req_dat["tipo_score_ingreso"]
            tipo_score_pp = req_dat["tipo_score_pp"]
            tipo_score_credito = req_dat["tipo_score_credito"]
            
            if tipo_score_ingreso and tipo_score_pp and tipo_score_credito in opciones:
                tsi = opciones[tipo_score_ingreso]
                tspp = opciones[tipo_score_pp]
                tsc = opciones[tipo_score_credito]
                print(f"Tu Tipo de score ingresos es: {tipo_score_ingreso}, URL: {tsi}")
                print(f"Tu Tipo de score de pagos puntuales es: {tipo_score_pp}, URL: {tspp}")
                print(f"Tu Tipo de score de credito es: {tipo_score_credito}, URL: {tsc}")
            
               
            #Dar conclusion dinamica
            antecedentes = request.data.get('antecedentes') # Obtenemos todos los antecedentes del prospecto
            print("ANTECEDENTES ====>",antecedentes)
            if antecedentes:
                # del antecedentes["civil_mercantil_demandado"] 
                print("CIVIL O FAMILIAR ====>",antecedentes)
                if antecedentes.get("civil_mercantil_demandado") and len(antecedentes) == 1: #tiene antecedentes de civil o de familiar? los excentamos si no delincuente
                    print("Historial Crediticio ====>")
                    #evaluar el historial crediticio  
                    
                    if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                        print("Rechazado ====>")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                    
                    elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                        print("Aprobado ====>")
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                        status = "Aprobado"
                        motivo = "No hay motivo de rechazo"
                    
                    elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                        print("A Considerar ====>")
                        conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                        status = "Aprobado_pe"
                        motivo = "1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                        
                elif antecedentes.get("antecedentes_aval_si") and len(antecedentes) == 1: #tiene antecedentes de aval
                        print("AVAL CON ANTECEDENTES")
                        print("Solicitar cambio Aval")
                        
                        if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                            print("Rechazado ====>")
                            conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                            status = "Declinado"
                            motivo = f"1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                            print("Aprobado ====>")
                            conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                            status = "Aprobado"
                            motivo =  f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                            print("A Considerar ====>")
                            conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                            status = "Aprobado_pe"
                            motivo = f"1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse.\n3.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                    
                elif antecedentes and tipo_score_pp == "Malo" or antecedentes and tipo_score_ingreso == "Malo":
                        print("Rechazado ====>")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."    
                        
                else:
                    print("Antecedentes")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."
            else: #No tiene Antecedentes
                
                #evaluar el historial crediticio  
                if tipo_score_pp == "Malo":
                    print("Rechazado ====>")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Buro: Se cuenta con un buro con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                
                elif tipo_score_ingreso == "Malo":
                    print("Rechazado ====>")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Ingresos: Los ingresos comprobados no son suficientes para garantizar el cumplimiento de sus obligaciones financieras."
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                    print("Aprobado ====>")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = ""   
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente" and antecedentes.get("antecedentes_aval_si") and antecedentes != None :
                    print("Aprobado ====>")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos." 
                
                elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                    print("A Considerar ====>")
                    conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                    status = "Aprobado_pe"
                    motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                
                 
                    
            context = {'info': info, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                       "redes_comentarios":redes_comentarios, 'referencias':referencias, 'antecedentes':antecedentes,'status':status, 'conclusion':conclusion, 'motivo':motivo}
            
            template = 'home/report_semillero.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            print("Generando PDF")
            pdf_file = HTML(string=html_string).write_pdf()

            # #aqui hacia abajo es para enviar por email
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
        
            print("DATOS ARCHIVO ====>",context)
            correo = self.enviar_archivo_semillero(archivo, context["info"], context["status"])
            print("CORREO ====>",correo)
            if correo.status_code == 200:
                 # Aprobar o desaprobar
                if status == "Aprobado_pe" or status == "Aprobado":  
                     info.status = "Aprobado"
                     info.save()
                else:
                     info.status = "Rechazado"
                     info.save()
                
                print("Correo ENVIADO")
            
            else:
                print("Correo NO ENVIADO")
                Response({"Error":"no se envio el correo"},status = 409)
            
            return Response({'mensaje': "Todo salio bien, pdf enviado"}, status = 200)
           
            #de aqui hacia abajo Devuelve el PDF como respuesta
            # response = HttpResponse(content_type='application/pdf')
            # response['Content-Disposition'] = 'inline; filename="Pagare.pdf"'
            # response.write(pdf_file)
            # print("Finalizamos el proceso de aprobado") 
            # return response
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status = "404")  
        

########################## S E M I L L E R O  P U R I S I M A ######################################

class DocumentosArrendamiento_Semillero(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendamientos_semillero.objects.all()
    serializer_class = SemilleroArrendamientosSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendamiento Semillero....📄")
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list documentos arrendamientos semillero es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Documentos Arrendamiento Semillero....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            print("FILES ===>", request.FILES)
            
            contrato_id = data.get('contrato_id', None)
            sin_recibo = data.get('sin_recibo', 'false').lower() == 'true'
            numero_pago_manual = data.get('numero_pago', None)
            
            print(f"Contrato ID: {contrato_id}, Sin Recibo: {sin_recibo}, Número Pago Manual: {numero_pago_manual}")
            
            if contrato_id:
                print(f"Flujo Semillero - Buscando contrato ID: {contrato_id}")
                try:
                    contrato = SemilleroContratos.objects.get(id=contrato_id)
                    arrendatario = contrato.arrendatario
                except SemilleroContratos.DoesNotExist:
                    return Response({'error': f'Contrato ID {contrato_id} no encontrado'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                arrendatario = None
                arrendatario = Arrendatarios_semillero.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(arr_nombre_empresa__icontains=nombre_usuario)
                ).first()
                
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    print(f"Buscando por primer nombre: {primer_nombre}")
                    arrendatario = Arrendatarios_semillero.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(arr_nombre_empresa__icontains=primer_nombre)
                    ).first()
                
                if not arrendatario:
                    palabras = nombre_usuario.split()
                    for palabra in palabras:
                        if len(palabra) > 2:
                            print(f"Buscando por palabra: {palabra}")
                            arrendatario = Arrendatarios_semillero.objects.filter(
                                Q(nombre_arrendatario__icontains=palabra) |
                                Q(arr_nombre_empresa__icontains=palabra)
                            ).first()
                            if arrendatario:
                                break
                
                if not arrendatario:
                    print("Buscando arrendatario asociado directamente al usuario")
                    arrendatario = Arrendatarios_semillero.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                try:
                    contrato = SemilleroContratos.objects.get(arrendatario=arrendatario)
                except SemilleroContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                proceso = ProcesoContrato_semillero.objects.get(contrato=contrato)
                print(f"Proceso encontrado: {proceso.id}")
            except ProcesoContrato_semillero.DoesNotExist:
                return Response({'error': f'Proceso no encontrado para el contrato ID: {contrato.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            duracion_meses = self.extraer_duracion_meses(contrato.duracion)
            print(f"Duración extraída: {duracion_meses} meses")
            
            if numero_pago_manual:
                numero_pago_actual = int(numero_pago_manual)
                pago_existente = DocumentosArrendamientos_semillero.objects.filter(
                    contrato=contrato,
                    proceso=proceso,
                    numero_pago=numero_pago_actual
                ).first()
                if pago_existente:
                    return Response({
                        'error': f'Ya existe un pago registrado con el número {numero_pago_actual} para este contrato',
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                pagos_existentes = DocumentosArrendamientos_semillero.objects.filter(contrato=contrato).count()
                numero_pago_actual = pagos_existentes + 1
            
            renta_total = Decimal(str(contrato.renta)) * duracion_meses if contrato.renta else Decimal('0')
            interes_aplicado = Decimal('0')
            fecha_vencimiento = datetime.now().date() + timedelta(days=30)
            
            if not sin_recibo:
                if numero_pago_actual > 1:
                    ultimo_pago = DocumentosArrendamientos_semillero.objects.filter(
                        contrato=contrato
                    ).order_by('-dateTimeOfUpload').first()
                    
                    if ultimo_pago and ultimo_pago.fecha_vencimiento:
                        dias_retraso = (datetime.now().date() - ultimo_pago.fecha_vencimiento).days
                        if dias_retraso > 0:
                            interes_mensual = Decimal('0.01')
                            meses_retraso = Decimal(str(dias_retraso)) / Decimal('30')
                            interes_aplicado = Decimal(str(contrato.renta)) * interes_mensual * meses_retraso
            
            comp_pago_file = request.FILES.get('comp_pago', None)
            if not sin_recibo and not comp_pago_file:
                return Response({'error': 'Se requiere archivo de recibo para registrar el pago'}, status=status.HTTP_400_BAD_REQUEST)
            
            referencia_pago = data.get('referencia_pago', '')
            documento_data = {
                "user": user_session.id,
                "arrendatario": arrendatario.id,
                "contrato": contrato.id,
                "proceso": proceso.id,
                "comp_pago": comp_pago_file,
                "referencia_pago": referencia_pago,
                "numero_pago": numero_pago_actual,
                "total_pagos": duracion_meses,
                "renta_total": renta_total,
                "interes_aplicado": interes_aplicado,
                "fecha_vencimiento": fecha_vencimiento,
            }
            
            arrendamientos_serializer = self.get_serializer(data=documento_data)
            arrendamientos_serializer.is_valid(raise_exception=True)
            arrendamientos_serializer.save()
            
            print("Documento Semillero ligado correctamente....✅")
            return Response(arrendamientos_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def extraer_duracion_meses(self, duracion_texto):
        if not duracion_texto:
            return 1
        
        texto = str(duracion_texto).lower().strip()
        numeros = re.findall(r'\d+', texto)
        if numeros:
            duracion = int(numeros[0])
            return duracion
        
        palabras_meses = {
            'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6,
            'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10, 'once': 11, 'doce': 12,
            'dieciocho': 18, 'veinticuatro': 24, 'treinta': 30, 'treinta y seis': 36
        }
        for palabra, valor in palabras_meses.items():
            if palabra in texto:
                return valor
        return 1
        
    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            print("Eliminando Documentos Arrendamiento Semillero....🗑️")
            documentos_arrendamiento = self.get_object()
            documento_arrendamiento_serializer = self.serializer_class(documentos_arrendamiento)

            if documentos_arrendamiento:
                comp_pago = documento_arrendamiento_serializer.data['comp_pago']
                print("Eliminando Comprobante de Pago....", comp_pago)
                
                documentos_arrendamiento.delete()
                print("Documentos Arrendamiento Semillero eliminados correctamente....✅")
                return Response({'message': 'Archivo eliminado correctamente'}, status=204) 
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:  
            print(f"el error es en documentos arrendamiento destroy semillero es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='reporte_completo')
    def reporte_completo(self, request):
        """Genera reporte PDF completo de arrendamientos Semillero"""
        try:

            print("Generando reporte completo de arrendamientos Semillero....📊")
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            arrendatario_id = request.query_params.get('arrendatario_id', None)
            queryset = DocumentosArrendamientos_semillero.objects.select_related('arrendatario', 'contrato', 'proceso')

            if es_admin:
                if arrendatario_id:
                    queryset = queryset.filter(arrendatario_id=arrendatario_id)
            else:
                nombre_usuario = request.user.first_name.strip()
                arrendatario = Arrendatarios_semillero.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) | Q(arr_nombre_empresa__icontains=nombre_usuario) | Q(user=request.user)
                ).first()
                if not arrendatario:
                    return Response({'error': 'No se encontró información de arrendamiento para este usuario'}, status=status.HTTP_404_NOT_FOUND)
                queryset = queryset.filter(arrendatario=arrendatario)

            recibos = queryset.order_by('arrendatario_id', 'numero_pago')
            arrendatarios_data = defaultdict(lambda: {'arrendatario': {}, 'contrato': {}, 'recibos': [], 'estadisticas': {'total_pagos': 0, 'pagos_realizados': 0, 'pagos_pendientes': 0, 'renta_mensual': 0, 'renta_total': 0, 'total_pagado': 0, 'total_pendiente': 0, 'interes_total': 0, 'porcentaje_completado': 0}})

            for recibo in recibos:
                if not recibo.arrendatario:
                    continue
                arr_id = recibo.arrendatario.id
                if not arrendatarios_data[arr_id]['arrendatario']:
                    nombre = recibo.arrendatario.nombre_arrendatario or getattr(recibo.arrendatario, 'arr_nombre_empresa', None) or 'Sin nombre'
                    arrendatarios_data[arr_id]['arrendatario'] = {'nombre': nombre, 'email': getattr(recibo.arrendatario, 'correo', None) or 'No especificado', 'telefono': getattr(recibo.arrendatario, 'celular', None) or 'No especificado', 'tipo': 'Persona Física' if recibo.arrendatario.nombre_arrendatario else 'Persona Moral'}
                if recibo.contrato and not arrendatarios_data[arr_id]['contrato']:
                    contrato = recibo.contrato
                    arrendatarios_data[arr_id]['contrato'] = {'no_depa': getattr(contrato, 'no_depa', None) or 'N/A', 'duracion': getattr(contrato, 'duracion', None) or 'No especificada', 'fecha_celebracion': getattr(contrato, 'fecha_celebracion', None).strftime('%d/%m/%Y') if getattr(contrato, 'fecha_celebracion', None) else 'N/A', 'fecha_vigencia': getattr(contrato, 'fecha_terminacion', None).strftime('%d/%m/%Y') if getattr(contrato, 'fecha_terminacion', None) else 'N/A', 'renta': float(getattr(contrato, 'renta', None)) if getattr(contrato, 'renta', None) else 0}
                estado = 'Sin fecha'
                if getattr(recibo, 'fecha_vencimiento', None):
                    dias_restantes = (recibo.fecha_vencimiento - date.today()).days
                    estado = 'Vencido' if dias_restantes < 0 else ('Próximo a vencer' if dias_restantes <= 7 else 'Al día')
                renta_mensual = float(recibo.contrato.renta) if recibo.contrato and getattr(recibo.contrato, 'renta', None) else 0
                interes_aplicado = float(recibo.interes_aplicado) if getattr(recibo, 'interes_aplicado', None) else 0
                arrendatarios_data[arr_id]['recibos'].append({'numero_pago': recibo.numero_pago or 0, 'fecha_subida': recibo.dateTimeOfUpload.strftime('%d/%m/%Y %H:%M') if getattr(recibo, 'dateTimeOfUpload', None) else 'N/A', 'fecha_vencimiento': recibo.fecha_vencimiento.strftime('%d/%m/%Y') if getattr(recibo, 'fecha_vencimiento', None) else 'N/A', 'interes': interes_aplicado, 'estado': estado})
                stats = arrendatarios_data[arr_id]['estadisticas']
                stats['total_pagos'] = recibo.total_pagos or 0
                stats['pagos_realizados'] = len(arrendatarios_data[arr_id]['recibos'])
                stats['pagos_pendientes'] = stats['total_pagos'] - stats['pagos_realizados']
                stats['renta_total'] = float(recibo.renta_total) if getattr(recibo, 'renta_total', None) else 0
                stats['interes_total'] += interes_aplicado
                if recibo.contrato and getattr(recibo.contrato, 'renta', None):
                    stats['renta_mensual'] = float(recibo.contrato.renta)
                    stats['total_pagado'] = stats['renta_mensual'] * stats['pagos_realizados']
                    stats['total_pendiente'] = stats['renta_mensual'] * stats['pagos_pendientes']
                if stats['total_pagos'] > 0:
                    stats['porcentaje_completado'] = round((stats['pagos_realizados'] / stats['total_pagos']) * 100, 1)

            context = {'arrendatarios': list(arrendatarios_data.values()), 'totales': {'total_arrendatarios': len(arrendatarios_data), 'total_recibos': recibos.count(), 'ingresos_totales': sum(a['estadisticas']['total_pagado'] for a in arrendatarios_data.values()), 'pendientes_totales': sum(a['estadisticas']['total_pendiente'] for a in arrendatarios_data.values()), 'intereses_totales': sum(a['estadisticas']['interes_total'] for a in arrendatarios_data.values()), 'contratos_por_vencer': 0, 'pagos_atrasados': 0}, 'fecha_generacion': datetime.now().strftime('%d/%m/%Y %H:%M'), 'usuario_generador': request.user.first_name or request.user.username}
            template_name = 'home/reporte_arrendamientos_garzasada_admin.html' if es_admin else 'home/reporte_arrendamientos_garzasada_v2.html'
            html_string = render_to_string(template_name, context)
            pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="reporte_arrendamientos_semillero{"_admin" if es_admin else ""}_{date.today().strftime("%Y%m%d")}.pdf"'
            print("Reporte Semillero generado exitosamente....✅")
            return response
        except Exception as e:
            print(f"Error al generar reporte Semillero: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en reporte Semillero: {e}")
            return Response({'error': f'Error al generar el reporte: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='lista_arrendatarios')
    def lista_arrendatarios(self, request):
        """Lista de arrendatarios Semillero con contratos (solo admin)"""
        try:
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            if not es_admin:
                return Response({'error': 'Sin permisos'}, status=status.HTTP_403_FORBIDDEN)
            arrendatario_ids = SemilleroContratos.objects.values_list('arrendatario_id', flat=True).distinct()
            arrendatarios = Arrendatarios_semillero.objects.filter(id__in=arrendatario_ids).values('id', 'nombre_arrendatario', 'arr_nombre_empresa')
            lista = [{'id': arr['id'], 'nombre': arr.get('nombre_arrendatario') or arr.get('arr_nombre_empresa')} for arr in arrendatarios if arr.get('nombre_arrendatario') or arr.get('arr_nombre_empresa')]
            return Response(lista, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error lista Semillero: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class IncidenciasSemilleroViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = IncidenciasSemillero.objects.all()
    serializer_class = IncidenciasSemilleroSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Incidencias Semillero....📄")
            queryset = self.filter_queryset(self.get_queryset())
            IncidenciasSerializers = self.get_serializer(queryset, many=True)
            return Response(IncidenciasSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list incidencias semillero es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Solicitud de Incidencia Semillero....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            
            usuarios_autorizados = ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            es_usuario_autorizado = (
                user_session.is_staff or 
                user_session.is_superuser or 
                user_session.username in usuarios_autorizados or
                getattr(user_session, 'pertenece_a', None) in usuarios_autorizados
            )
            
            if es_usuario_autorizado:
                arrendatario_id = data.get('arrendatario', None)
                contrato_id = data.get('contrato', None)
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": arrendatario_id,
                    "contrato": contrato_id,
                    "incidencia": data.get('incidencia', ''),
                    "tipo_incidencia": data.get('tipo_incidencia', ''),
                    "prioridad": data.get('prioridad', 'Media'),
                    "status": "Pendiente de Revisión",
                }
            else:
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                arrendatario = Arrendatarios_semillero.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(arr_nombre_empresa__icontains=nombre_usuario)
                ).first()
                
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    arrendatario = Arrendatarios_semillero.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(arr_nombre_empresa__icontains=primer_nombre)
                    ).first()
                
                if not arrendatario:
                    arrendatario = Arrendatarios_semillero.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                try:
                    contrato = SemilleroContratos.objects.get(arrendatario=arrendatario)
                except SemilleroContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
                
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": arrendatario.id,
                    "contrato": contrato.id,
                    "incidencia": data.get('incidencia', ''),
                    "status": "Pendiente de Revisión",
                }
            
            incidencias_serializer = self.get_serializer(data=incidencia_data)
            incidencias_serializer.is_valid(raise_exception=True)
            incidencias_serializer.save()
            
            print("Incidencia Semillero creada exitosamente....✅")
            return Response(incidencias_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)


########################## G A R Z A  S A D A ######################################
class Arrendatarios_GarzaSadaViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Arrendatarios_garzasada.objects.all()
    serializer_class = Arrentarios_GarzaSadaSerializers
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
            if user_session.is_staff or user_session.username == "GarzaSada": #Muestra todos los arrendatarios
                print("Listar Residentes Garza Sada")
                arrendatarios =  self.get_queryset().order_by('-id')
                serializer = self.get_serializer(arrendatarios, many=True)
                return Response(serializer.data, status= status.HTTP_200_OK)
            
            # elif user_session.rol == "Inmobiliaria": #Muestra los arrendatarios de la inmobiliaria y los que hayan registrado los agentes
            #     print("Soy Inmobiliaria ====>", user_session.name_inmobiliaria)
            #     agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
            #     inquilinos_agentes = self.get_queryset().filter(user_id__in = agentes)#Buscamos inquilinos con base en los agentes que pertenecen a la inmobiliaria
            #     inquilinos_inmobiliaria = self.get_queryset().filter(user_id = user_session)
            #     all_inquilinos = inquilinos_agentes.union(inquilinos_inmobiliaria)#Une ambas consultas de agentes y la inmobiliaria
            #     all_inquilinos = all_inquilinos.order_by('-id') #ordena por id descendente
               
            #     serializer = self.get_serializer(all_inquilinos, many=True)
            #     serialized_data = serializer.data
                
            #     if not serialized_data:
            #         print("No hay datos disponibles")
            #         return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                
            #     # Agregar el campo 'is_staff'
            #     for item in serialized_data:
            #         item['inmobiliaria'] = True
                    
            #     return Response(serialized_data)      
            
            elif user_session.rol == "Agente":  
                print("Soy Agente ====>", user_session.first_name)
                residentes_agente = self.get_queryset().filter(user_id = user_session).order_by('-id')#Buscamos inquilinos del agente y los ordenamos por id descendente
              
                serializer = self.get_serializer(residentes_agente, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("No hay datos disponibles")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)
            
            elif user_session.rol == "Residente":
                print("Soy Residente ====>", user_session.first_name)
                nombre_busqueda = (user_session.first_name).strip()

                # Si no hay nombre para filtrar, retorna lista vacía por seguridad
                if not nombre_busqueda:
                    return Response([], status=status.HTTP_200_OK)

                residente = (
                    Arrendatarios_garzasada.objects
                    .filter(
                        Q(nombre_arrendatario__icontains=nombre_busqueda) |
                        Q(nombre_empresa_pm__icontains=nombre_busqueda)
                    )
                    .order_by('-id')
                )
                
                for arrendatario in residente:
                    arrendatario_dict = model_to_dict(arrendatario)
                    print(f"ARRENDATARIO COMPLETO ====> {arrendatario_dict}")
                
                print("Residente encontrado ====>", residente)

                serializer = self.get_serializer(residente, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)           
        
        except Exception as e:
            print(f"el error desde list arrendatarios garza sada es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print("Creando arrendatario Garza Sada....")
            print("Arrendatario ====>",request.data)
            arrendatarios_garzasada_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            print(arrendatarios_garzasada_serializer)
            if arrendatarios_garzasada_serializer.is_valid(raise_exception=True):
                arrendatarios_garzasada_serializer.save(user = user_session)
                print("Guardo arrendatario Garza Sada....✅")
                return Response({'arrendatarios_semilleros': arrendatarios_garzasada_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion...❌")
                return Response({'errors': arrendatarios_garzasada_serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando arrendatario Garza Sada....🔄")
            partial = kwargs.pop('partial', False)
            print("partials====>",partial)
            print(request.data)
            instance = self.get_object()
            print("instance ====>",instance)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            print(serializer)
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("Residente actualizado correctamente....✅")
                # return redirect('myapp:my-url')
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            user_session = request.user
            print("Entrando a retrieve")
            modelos = Residentes.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            Residentes = modelos.filter(slug=slug)
            if Residentes:
                serializer_Residentes = Arrentarios_GarzaSadaSerializers(Residentes, many=True)
                return Response(serializer_Residentes.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            print("Eliminando arrendatario Garza Sada....🗑 ️")
            Residentes = self.get_object()
            if Residentes:
                Residentes.delete()
                print("Residente eliminado correctamente....✅")
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
  
    def mandar_aprobado(self, request, *args, **kwargs):  
        try:
            print("Aprobar al residente Garza Sada....")
            info = request.data
            print("Residente a Aprobar ====>", info )
            today = date.today().strftime('%d/%m/%Y')
            ingreso = int(info["ingreso"])
            ingreso_texto = num2words(ingreso, lang='es').capitalize()
            context = {'info': info, "fecha_consulta":today, 'ingreso':ingreso, 'ingreso_texto':ingreso_texto}
        
            # Renderiza el template HTML  
            template = 'home/aprobado_fraterna.html'
    
            html_string = render_to_string(template, context)# lo comvertimos a string
            pdf_file = HTML(string=html_string).write_pdf(target=None) # Genera el PDF utilizando weasyprint para descargar del usuario
            print("PDF creado correctamente....✅")
            
            archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
            print("Contenido PDF....",context)
            self.enviar_archivo(archivo, info)
            print("PDF enviado por correo....✅")
            return Response({'Mensaje': 'Todo Bien'},status= status.HTTP_200_OK)
        
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
                  
    def enviar_archivo(self, archivo, info, comentario="nada"):
        print("Enviando archivo por correo electrónico Garza Sada....📫")
        print("Comentarios....💬",comentario)
        arrendatario = info["nombre_arrendatario"]
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            # destinatario = 'jsepulvedaarrendify@gmail.com'
            destinatario = 'legal@fraterna.mx'
            # destinatario2 = 'juridico.arrendify1@gmail.com'
            destinatario2 = 'smosqueda@fraterna.mx'
            
            
            asunto = f"Resultado Investigación Arrendatario {arrendatario}"
            
            destinatarios = [destinatario,destinatario2]
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = destinatario
            msg['Cc'] = destinatario2
            msg['Subject'] = asunto
            print("Cabecera de correo electrónico creada....✅")
           
            # Estilo del mensaje
            #variable resultado_html_fraterna
            pdf_html = aprobado_fraterna(info)
          
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("PDf adjuntado al mensaje....✅")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Resultado_investigación.pdf')
            msg.attach(pdf_part)
            print("Se creo el mail con el PDF adjunto....✅")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                server.sendmail(remitente, destinatarios, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
            print("Correo electrónico enviado correctamente....✅")
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})
        
class DocumentosArrendatario_GarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendatarios_garzasada.objects.all()
    serializer_class = DAGSSerializer
   
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendatarios Garza Sada....📄")
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def create (self, request, *args,**kwargs):
        try: 
            print("Creando Documentos Arrendatarios Garza Sada....📄")
            user_session = str(request.user.id)
            
            # Verificar si el arrendatario existe
            arrendatario_id = request.data.get('arrendatario')
            print(f"🔍 Verificando arrendatario con ID: {arrendatario_id} (tipo: {type(arrendatario_id)})")
            
            if not arrendatario_id:
                return Response({'error': 'El ID del arrendatario es requerido'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Convertir a entero
            try:
                arrendatario_id = int(arrendatario_id)
                print(f"✅ ID convertido a entero: {arrendatario_id}")
            except (ValueError, TypeError):
                return Response({'error': f'ID del arrendatario inválido: {arrendatario_id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Verificar si existe el arrendatario en la base de datos
            try:
                arrendatario = Arrendatarios_garzasada.objects.get(id=arrendatario_id)
                print(f"✅ Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm}")
            except Arrendatarios_garzasada.DoesNotExist:
                print(f"❌ El arrendatario con ID {arrendatario_id} NO EXISTE en la base de datos")
                # Listar arrendatarios disponibles
                arrendatarios_disponibles = Arrendatarios_garzasada.objects.all().values('id', 'nombre_arrendatario', 'nombre_empresa_pm')
                print(f"📋 Arrendatarios disponibles: {list(arrendatarios_disponibles)}")
                return Response({
                    'error': f'El arrendatario con ID {arrendatario_id} no existe',
                    'arrendatarios_disponibles': list(arrendatarios_disponibles)
                }, status=status.HTTP_400_BAD_REQUEST)
            
            data = {
                    "Ine_arrendatario": request.FILES.get('Ine_arrendatario', None),
                    "Ine_obligado": request.FILES.get('Ine_obligado', None),
                    "Comp_dom_arrendatario": request.FILES.get('Comp_dom_arrendatario', None),
                    "Comp_dom_obligado": request.FILES.get('Comp_dom_obligado', None),
                    "Rfc_arrendatario": request.FILES.get('Rfc_arrendatario', None),
                    "Ingresos_arrendatario": request.FILES.get('Ingresos_arrendatario', None),
                    "Ingresos2_arrendatario": request.FILES.get('Ingresos2_arrendatario', None),
                    "Ingresos3_arrendatario": request.FILES.get('Ingresos3_arrendatario', None),
                    "Ingresos_obligado": request.FILES.get('Ingresos_obligado', None),
                    "Ingresos2_obligado": request.FILES.get('Ingresos_obligado2', None),
                    "Ingresos3_obligado": request.FILES.get('Ingresos_obligado3', None),
                    "Extras": request.FILES.get('Extras', None),
                    "Recomendacion_laboral": request.FILES.get('Recomendacion_laboral', None),
                    "arrendatario":arrendatario_id,
                    "user":user_session
                }
          
            if data:
                documentos_serializer = self.get_serializer(data=data)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save()
                print("Documentos Arrendatarios Garza Sada guardados correctamente....✅")
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            print("Eliminando Documentos Arrendatario Garza Sada....🗑️")
            documentos_inquilinos = self.get_object()
            documento_inquilino_serializer = self.serializer_class(documentos_inquilinos)
            if documentos_inquilinos:
                ine = documento_inquilino_serializer.data['ine']
                print("Eliminando INE....", ine)
                comp_dom= documento_inquilino_serializer.data['comp_dom']
                rfc= documento_inquilino_serializer.data['escrituras_titulo']
                print("Eliminando RFC....", rfc)
                ruta_ine = 'apps/static'+ ine
                print("Ruta ine", ruta_ine)
                ruta_comprobante_domicilio = 'apps/static'+ comp_dom
                ruta_rfc = 'apps/static'+ rfc
                print("Ruta com", ruta_comprobante_domicilio)
                print("Ruta RFC", ruta_rfc)
            
                # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
                documentos_inquilinos.delete()
                print("Documentos Arrendatario Garza Sada eliminados correctamente....✅")
                return Response({'message': 'Archivo eliminado correctamente'}, status=204)
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
        
    def retrieve(self, request, pk=None):
        try:
            documentos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            inquilino = documentos.filter(id=pk)
            serializer_inquilino = DISerializer(inquilino, many=True)
            print(serializer_inquilino.data)
            ine = serializer_inquilino.data[0]['ine']
            print(ine)
            # documentos_arrendador = self.get_object()
            # print(documentos_arrendador)
            return Response(serializer_inquilino.data)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
   
    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando Documentos Arrendatario Garza Sada....🔄")
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print("Datos Actuales ====>",request.data)
            
            # Verificar si se proporciona un nuevo archivo adjunto
            keys = request.data.keys()
    
            # Convertir las llaves a una lista y obtener la primera
            first_key = list(keys)[0]
            #first_key = str(first_key)
            print(first_key)
            
            # Acceder dinámicamente al atributo de instance usando first_key
            if hasattr(instance, first_key):
                archivo_anterior = getattr(instance, first_key)
                print("Archivo anterior ====>", archivo_anterior)
                eliminar_archivo_s3(archivo_anterior)
            else:
                print(f"El atributo '{first_key}' no existe en la instancia.")
            
            serializer.update(instance, serializer.validated_data)
            print("Se actualizó correctamente el documento del arrendatario Garza Sada....✅")
            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
class DocumentosArrendamiento_GarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendamientos_garzasada.objects.all()
    serializer_class = GarzaSadaArrendamientosSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendamiento Garza Sada....📄")
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list documentos arrendamientos es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Documentos Arrendamiento Garza Sada....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            print("FILES ===>", request.FILES)
            
            # Verificar si viene contrato_id directamente (desde GarzaSada)
            contrato_id = data.get('contrato_id', None)
            sin_recibo = data.get('sin_recibo', 'false').lower() == 'true'
            numero_pago_manual = data.get('numero_pago', None)
            
            print(f"Contrato ID: {contrato_id}, Sin Recibo: {sin_recibo}, Número Pago Manual: {numero_pago_manual}")
            
            if contrato_id:
                # Flujo para usuario GarzaSada con contrato específico
                print(f"Flujo GarzaSada - Buscando contrato ID: {contrato_id}")
                try:
                    contrato = GarzaSadaContratos.objects.get(id=contrato_id)
                    arrendatario = contrato.arrendatario
                    print(f"Contrato y arrendatario encontrados: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm}")
                except GarzaSadaContratos.DoesNotExist:
                    return Response({'error': f'Contrato ID {contrato_id} no encontrado'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Flujo original para usuarios normales
                # Usar first_name del usuario autenticado para buscar arrendatario
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                # Intentar diferentes estrategias de búsqueda
                arrendatario = None
                
                # Estrategia 1: Buscar por nombre completo
                arrendatario = Arrendatarios_garzasada.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario)
                ).first()
                
                # Estrategia 2: Si no encuentra, buscar por primer nombre
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    print(f"Buscando por primer nombre: {primer_nombre}")
                    arrendatario = Arrendatarios_garzasada.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(nombre_empresa_pm__icontains=primer_nombre)
                    ).first()
                
                # Estrategia 3: Si aún no encuentra, buscar por palabras individuales
                if not arrendatario:
                    palabras = nombre_usuario.split()
                    for palabra in palabras:
                        if len(palabra) > 2:  # Solo palabras de más de 2 caracteres
                            print(f"Buscando por palabra: {palabra}")
                            arrendatario = Arrendatarios_garzasada.objects.filter(
                                Q(nombre_arrendatario__icontains=palabra) |
                                Q(nombre_empresa_pm__icontains=palabra)
                            ).first()
                            if arrendatario:
                                break
                
                # Estrategia 4: Buscar por relación directa con el usuario
                if not arrendatario:
                    print("Buscando arrendatario asociado directamente al usuario")
                    arrendatario = Arrendatarios_garzasada.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                print(f"Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm} (ID: {arrendatario.id})")
                
                # Buscar contrato relacionado
                try:
                    contrato = GarzaSadaContratos.objects.get(arrendatario=arrendatario)
                    print(f"Contrato encontrado: {contrato.id}")
                except GarzaSadaContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Buscar proceso relacionado
            try:
                proceso = ProcesoContrato_garzasada.objects.get(contrato=contrato)
                print(f"Proceso encontrado: {proceso.id}")
            except ProcesoContrato_garzasada.DoesNotExist:
                return Response({'error': f'Proceso no encontrado para el contrato ID: {contrato.id}'}, status=status.HTTP_400_BAD_REQUEST)
            
            duracion_meses = self.extraer_duracion_meses(contrato.duracion)
            print(f"Duración extraída: {duracion_meses} meses")

            # Determinar número de pago
            if numero_pago_manual:
                # Usar número de pago manual si viene
                numero_pago_actual = int(numero_pago_manual)
                print(f"Usando número de pago manual: {numero_pago_actual}")
                
                # ✅ VALIDACIÓN: Verificar que no exista ya un pago con este número
                pago_existente = DocumentosArrendamientos_garzasada.objects.filter(
                    contrato=contrato,
                    proceso=proceso,
                    numero_pago=numero_pago_actual
                ).first()
                
                if pago_existente:
                    return Response({
                        'error': f'Ya existe un pago registrado con el número {numero_pago_actual} para este contrato',
                        'detalles': {
                            'numero_pago': numero_pago_actual,
                            'contrato_id': contrato.id,
                            'proceso_id': proceso.id,
                            'fecha_registro': pago_existente.dateTimeOfUpload.strftime('%Y-%m-%d %H:%M:%S') if pago_existente.dateTimeOfUpload else 'N/A'
                        }
                    }, status=status.HTTP_400_BAD_REQUEST)
                
            else:
                # Contar pagos existentes para este contrato
                pagos_existentes = DocumentosArrendamientos_garzasada.objects.filter(contrato=contrato).count()
                numero_pago_actual = pagos_existentes + 1
                print(f"Número de pago calculado automáticamente: {numero_pago_actual}")

            # Calcular renta total
            renta_total = Decimal(str(contrato.renta)) * duracion_meses if contrato.renta else Decimal('0')

            # Calcular interés por retraso (12% anual) - SOLO si no es un pago sin recibo
            interes_aplicado = Decimal('0')
            fecha_vencimiento = datetime.now().date() + timedelta(days=30)  # 30 días para pagar

            if not sin_recibo:  # Solo calcular intereses si hay recibo físico
                # Verificar si hay retraso en pagos anteriores
                if numero_pago_actual > 1:
                    ultimo_pago = DocumentosArrendamientos_garzasada.objects.filter(
                        contrato=contrato
                    ).order_by('-dateTimeOfUpload').first()
                    
                    if ultimo_pago and ultimo_pago.fecha_vencimiento:
                        dias_retraso = (datetime.now().date() - ultimo_pago.fecha_vencimiento).days
                        if dias_retraso > 0:
                            # Aplicar 12% anual = 1% mensual
                            interes_mensual = Decimal('0.01')
                            meses_retraso = Decimal(str(dias_retraso)) / Decimal('30')
                            interes_aplicado = Decimal(str(contrato.renta)) * interes_mensual * meses_retraso
            
            # Obtener archivo - puede ser None si sin_recibo=true
            comp_pago_file = request.FILES.get('comp_pago', None)
            
            # Validar que si no es sin_recibo, debe venir archivo
            if not sin_recibo and not comp_pago_file:
                return Response({
                    'error': 'Se requiere archivo de recibo para registrar el pago'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Obtener referencia de pago del request
            referencia_pago = data.get('referencia_pago', '')
            print(f"📝 Referencia de pago recibida: '{referencia_pago}'")
            
            # Crear documento
            documento_data = {
                "user": user_session.id,
                "arrendatario": arrendatario.id,
                "contrato": contrato.id,
                "proceso": proceso.id,
                "comp_pago": comp_pago_file,  # Puede ser None si sin_recibo=true
                "referencia_pago": referencia_pago,  
                "numero_pago": numero_pago_actual,
                "total_pagos": duracion_meses,
                "renta_total": renta_total,
                "interes_aplicado": interes_aplicado,
                "fecha_vencimiento": fecha_vencimiento,
            }
            
            tipo_registro = "SIN RECIBO" if sin_recibo else "CON RECIBO"
            print(f"Pago {numero_pago_actual} de {duracion_meses} ({tipo_registro}) - Renta total: ${renta_total} - Interés: ${interes_aplicado}")
            
            arrendamientos_serializer = self.get_serializer(data=documento_data)
            arrendamientos_serializer.is_valid(raise_exception=True)
            arrendamientos_serializer.save()
            
            print("Documento ligado correctamente....✅")
            return Response(arrendamientos_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def extraer_duracion_meses(self, duracion_texto):
        """
        Extrae la duración en meses de un texto.
        Ejemplos: "6 meses" -> 6, "12 meses" -> 12, "24 meses" -> 24
        """
        if not duracion_texto:
            return 1
        
        # Convertir a string y buscar números
        texto = str(duracion_texto).lower().strip()
        
        # Buscar números en el texto
        numeros = re.findall(r'\d+', texto)
        
        if numeros:
            duracion = int(numeros[0])
            # Validar que sea un número razonable (entre 1 y 60 meses)
            if 1 <= duracion <= 60:
                return duracion
            else:
                print(f"Advertencia: Duración inusual detectada: {duracion} meses")
                return duracion
        
        # Si no encuentra números, intentar palabras
        palabras_meses = {
            'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6,
            'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10, 'once': 11, 'doce': 12,
            'dieciocho': 18, 'veinticuatro': 24, 'treinta': 30, 'treinta y seis': 36
        }
        
        for palabra, valor in palabras_meses.items():
            if palabra in texto:
                return valor
        
        print(f"No se pudo extraer duración de: '{duracion_texto}', usando 1 mes por defecto")
        return 1
        
    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            print("Eliminando Documentos Arrendamiento Garza Sada....🗑️")
            documentos_arrendamiento = self.get_object()
            documento_arrendamiento_serializer = self.serializer_class(documentos_arrendamiento)
            if documentos_arrendamiento:
                comp_pago = documento_arrendamiento_serializer.data['comp_pago']
                print("Eliminando Comprobante de Pago....", comp_pago)
                
                documentos_arrendamiento.delete()
                print("Documentos Arrendamiento Garza Sada eliminados correctamente....✅")
                return Response({'message': 'Archivo eliminado correctamente'}, status=204) 
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:  
            print(f"el error es en documentos arrendamiento destroy es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando Documentos Arrendatario Garza Sada....🔄")
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print("Datos Actuales ====>",request.data)
            
            # Verificar si se proporciona un nuevo archivo adjunto
            keys = request.data.keys()
    
            # Convertir las llaves a una lista y obtener la primera
            first_key = list(keys)[0]
            #first_key = str(first_key)
            print(first_key)
            
            # Acceder dinámicamente al atributo de instance usando first_key
            if hasattr(instance, first_key):
                archivo_anterior = getattr(instance, first_key)
                print("Archivo anterior ====>", archivo_anterior)
                eliminar_archivo_s3(archivo_anterior)
                print("Archivo eliminado de S3 desde GarzaSada....✅")
            else:
                print(f"El atributo '{first_key}' no existe en la instancia.")
            
            serializer.update(instance, serializer.validated_data)
            print("Se actualizó correctamente el documento del arrendatario Garza Sada....✅")
            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='reporte_completo')
    def reporte_completo(self, request):
        """
        Genera un reporte PDF completo con información detallada de arrendamientos
        
        Control de acceso:
        - Usuarios normales: Solo su información
        - Administradores: Todos los arrendamientos o filtrados por arrendatario_id
        
        Query params:
        - arrendatario_id (opcional): Filtrar por ID de arrendatario específico
        """
        try:
            from django.http import HttpResponse
            from django.template.loader import render_to_string
            from weasyprint import HTML
            from collections import defaultdict
            
            print("Generando reporte completo de arrendamientos Fraterna....📊")
            
            # Verificar si es administrador
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            
            # Obtener parámetro de filtro (solo para admin)
            arrendatario_id = request.query_params.get('arrendatario_id', None)
            
            # Construir queryset base
            queryset = DocumentosArrendamientosFraternaModel.objects.select_related(
                'arrendatario',
                'contrato',
                'proceso'
            )
            
            if es_admin:
                print(f"Usuario administrador: {request.user.username}")
                # Administrador puede ver todos o filtrar por arrendatario_id
                if arrendatario_id:
                    queryset = queryset.filter(arrendatario_id=arrendatario_id)
                    print(f"Filtrando por arrendatario ID: {arrendatario_id}")
            else:
                print(f"Usuario normal: {request.user.username}")
                # Usuario normal: solo sus propios datos
                # Buscar arrendatario asociado al usuario
                nombre_usuario = request.user.first_name.strip()
                arrendatario = Residentes.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario) |
                    Q(user=request.user)
                ).first()
                
                if not arrendatario:
                    return Response({
                        'error': 'No se encontró información de arrendamiento para este usuario'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                queryset = queryset.filter(arrendatario=arrendatario)
                print(f"Filtrando por arrendatario: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm}")
            
            # Ordenar resultados
            recibos = queryset.order_by('arrendatario__nombre_arrendatario', 'numero_pago')
            
            # Agrupar información por arrendatario
            arrendatarios_data = defaultdict(lambda: {
                'arrendatario': {},
                'contrato': {},
                'recibos': [],
                'estadisticas': {
                    'total_pagos': 0,
                    'pagos_realizados': 0,
                    'pagos_pendientes': 0,
                    'renta_mensual': 0,
                    'renta_total': 0,
                    'total_pagado': 0,
                    'total_pendiente': 0,
                    'interes_total': 0,
                    'porcentaje_completado': 0,
                }
            })
            
            for recibo in recibos:
                if not recibo.arrendatario:
                    continue
                
                arr_id = recibo.arrendatario.id
                
                # Información del arrendatario (solo la primera vez)
                if not arrendatarios_data[arr_id]['arrendatario']:
                    nombre = recibo.arrendatario.nombre_arrendatario or recibo.arrendatario.nombre_empresa_pm
                    
                    # Determinar email y teléfono según el tipo
                    if recibo.arrendatario.nombre_arrendatario:
                        # Persona Física
                        email = recibo.arrendatario.correo or 'No especificado'
                        telefono = recibo.arrendatario.celular or 'No especificado'
                        tipo = 'Persona Física'
                    else:
                        # Persona Moral
                        email = recibo.arrendatario.correo or 'No especificado'
                        telefono = recibo.arrendatario.telefono_empresa_pm or 'No especificado'
                        tipo = 'Persona Moral'
                    
                    arrendatarios_data[arr_id]['arrendatario'] = {
                        'nombre': nombre,
                        'email': email,
                        'telefono': telefono,
                        'tipo': tipo,
                    }
                
                # Información del contrato (solo la primera vez)
                if recibo.contrato and not arrendatarios_data[arr_id]['contrato']:
                    contrato = recibo.contrato
                    arrendatarios_data[arr_id]['contrato'] = {
                        'no_depa': contrato.no_depa or 'N/A',
                        'num_inq': contrato.num_inq or 'N/A',
                        'duracion': contrato.duracion or 'No especificada',
                        'fecha_celebracion': contrato.fecha_celebracion.strftime('%d/%m/%Y') if contrato.fecha_celebracion else 'N/A',
                        'fecha_vigencia': contrato.fecha_vigencia.strftime('%d/%m/%Y') if contrato.fecha_vigencia else 'N/A',
                        'renta': float(contrato.renta) if contrato.renta else 0,
                    }
                
                # Calcular estado del pago y días de retraso
                estado = 'Sin fecha'
                dias_retraso = 0
                if recibo.fecha_vencimiento:
                    hoy = date.today()
                    dias_restantes = (recibo.fecha_vencimiento - hoy).days
                    if dias_restantes < 0:
                        estado = 'Vencido'
                        dias_retraso = abs(dias_restantes)
                    elif dias_restantes <= 7:
                        estado = 'Próximo a vencer'
                    else:
                        estado = 'Al día'
                
                # Calcular montos y datos adicionales para admin
                renta_mensual = float(recibo.contrato.renta) if recibo.contrato and recibo.contrato.renta else 0
                interes_aplicado = float(recibo.interes_aplicado) if recibo.interes_aplicado else 0
                penalizacion = interes_aplicado
                monto_pagado = renta_mensual if recibo.comp_pago else 0
                monto_pendiente = renta_mensual - monto_pagado
                usuario_subio = 'Sin usuario'
                if recibo.user:
                    usuario_subio = recibo.user.first_name or recibo.user.username
                referencia_pago = f"GS-{recibo.id:06d}" if recibo.id else 'N/A'
                
                # Agregar recibo con campos básicos
                recibo_data = {
                    'numero_pago': recibo.numero_pago or 0,
                    'fecha_subida': recibo.dateTimeOfUpload.strftime('%d/%m/%Y %H:%M') if recibo.dateTimeOfUpload else 'N/A',
                    'fecha_vencimiento': recibo.fecha_vencimiento.strftime('%d/%m/%Y') if recibo.fecha_vencimiento else 'N/A',
                    'interes': interes_aplicado,
                    'estado': estado,
                }
                
                # Campos adicionales para administrador
                if es_admin:
                    recibo_data.update({
                        'departamento': recibo.contrato.no_depa if recibo.contrato else 'N/A',
                        'num_inq': recibo.contrato.num_inq if recibo.contrato else 'N/A',
                        'referencia_pago': referencia_pago,
                        'monto': renta_mensual,
                        'monto_pagado': monto_pagado,
                        'monto_pendiente': monto_pendiente,
                        'dias_retraso': dias_retraso,
                        'penalizacion': penalizacion,
                        'usuario': usuario_subio,
                    })
                
                arrendatarios_data[arr_id]['recibos'].append(recibo_data)
                
                # Actualizar estadísticas
                stats = arrendatarios_data[arr_id]['estadisticas']
                stats['total_pagos'] = recibo.total_pagos or 0
                stats['pagos_realizados'] = len(arrendatarios_data[arr_id]['recibos'])
                stats['pagos_pendientes'] = stats['total_pagos'] - stats['pagos_realizados']
                stats['renta_total'] = float(recibo.renta_total) if recibo.renta_total else 0
                stats['interes_total'] += interes_aplicado
                
                if recibo.contrato and recibo.contrato.renta:
                    stats['renta_mensual'] = float(recibo.contrato.renta)
                    stats['total_pagado'] = stats['renta_mensual'] * stats['pagos_realizados']
                    stats['total_pendiente'] = stats['renta_mensual'] * stats['pagos_pendientes']
                
                # Calcular porcentaje
                if stats['total_pagos'] > 0:
                    stats['porcentaje_completado'] = round((stats['pagos_realizados'] / stats['total_pagos']) * 100, 1)
            
            # Calcular contratos por vencer (próximos 30 días)
            hoy = date.today()
            fecha_limite = hoy + timedelta(days=30)
            contratos_por_vencer = 0
            pagos_atrasados = 0
            
            for arr_data in arrendatarios_data.values():
                # Contar contratos por vencer
                fecha_vigencia_str = arr_data['contrato'].get('fecha_vigencia', '')
                if fecha_vigencia_str and fecha_vigencia_str != 'N/A':
                    try:
                        fecha_vigencia = datetime.strptime(fecha_vigencia_str, '%d/%m/%Y').date()
                        if hoy <= fecha_vigencia <= fecha_limite:
                            contratos_por_vencer += 1
                    except:
                        pass
                
                # Contar pagos atrasados (solo los que ya pasaron su fecha de vencimiento)
                for recibo in arr_data['recibos']:
                    # Solo contar como atrasado si el estado es 'Vencido'
                    # Esto significa que la fecha de vencimiento ya pasó
                    if recibo.get('estado', '') == 'Vencido':
                        pagos_atrasados += 1
            
            # Calcular totales generales
            totales_generales = {
                'total_arrendatarios': len(arrendatarios_data),
                'total_recibos': recibos.count(),
                'ingresos_totales': sum(arr['estadisticas']['total_pagado'] for arr in arrendatarios_data.values()),
                'pendientes_totales': sum(arr['estadisticas']['total_pendiente'] for arr in arrendatarios_data.values()),
                'intereses_totales': sum(arr['estadisticas']['interes_total'] for arr in arrendatarios_data.values()),
                'contratos_por_vencer': contratos_por_vencer,
                'pagos_atrasados': pagos_atrasados,
            }
            
            # Contexto para el template
            context = {
                'arrendatarios': list(arrendatarios_data.values()),
                'totales': totales_generales,
                'fecha_generacion': datetime.now().strftime('%d/%m/%Y %H:%M'),
                'usuario_generador': request.user.first_name or request.user.username,
            }
            
            # Seleccionar template según tipo de usuario
            template_name = 'home/reporte_arrendamientos_garzasada_admin.html' if es_admin else 'home/reporte_arrendamientos_garzasada_v2.html'
            print(f"Usando template: {template_name}")
            
            # Renderizar HTML
            html_string = render_to_string(template_name, context)
            
            # Generar PDF
            html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
            pdf = html.write_pdf()
            
            # Crear respuesta HTTP
            response = HttpResponse(pdf, content_type='application/pdf')
            filename_suffix = '_admin' if es_admin else ''
            response['Content-Disposition'] = f'attachment; filename="reporte_arrendamientos_garzasada{filename_suffix}_{date.today().strftime("%Y%m%d")}.pdf"'
            
            print("Reporte generado exitosamente....✅")
            return response
            
        except Exception as e:
            print(f"Error al generar reporte: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': f'Error al generar el reporte: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='lista_arrendatarios')
    def lista_arrendatarios(self, request):
        """
        Obtiene la lista completa de arrendatarios con contratos activos.
        Solo disponible para administradores.
        Útil para filtros en el frontend.
        """
        try:
            # Verificar si es administrador
            es_admin = request.user.is_staff or request.user.is_superuser or request.user.username in ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            
            if not es_admin:
                return Response({
                    'error': 'No tienes permisos para acceder a esta información'
                }, status=status.HTTP_403_FORBIDDEN)
            
            print(f"Admin {request.user.username} solicitando lista de arrendatarios")
            
            # Obtener arrendatarios únicos con contratos
            arrendatarios = Arrendatarios_garzasada.objects.filter(
                contratos_garzasada__isnull=False
            ).distinct().values(
                'id',
                'nombre_arrendatario',
                'nombre_empresa_pm'
            )
            
            # Formatear respuesta
            lista = []
            for arr in arrendatarios:
                nombre = arr['nombre_arrendatario'] or arr['nombre_empresa_pm']
                if nombre:
                    lista.append({
                        'id': arr['id'],
                        'nombre': nombre
                    })
            
            print(f"Se encontraron {len(lista)} arrendatarios")
            return Response(lista, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error al obtener lista de arrendatarios: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class IncidenciasGarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = IncidenciasGarzaSada.objects.all()
    serializer_class = IncidenciasGarzaSadaSerializer
    
    def list(self, request, *args, **kwargs):
        try:
            print("Listando Documentos Arrendamiento Garza Sada....📄")
            queryset = self.filter_queryset(self.get_queryset())
            IncidenciasSerializers = self.get_serializer(queryset, many=True)
            return Response(IncidenciasSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error esta en list documentos arrendamientos es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try: 
            print("Creando Solicitud de Incidencia....📄")
            user_session = request.user
            data = request.data
            print("Data ===>", data)
            
            # Verificar si es usuario autorizado para incidencias Arrendify
            usuarios_autorizados = ['GarzaSada', 'Fraterna', 'SemilleroPurisima']
            es_usuario_autorizado = (
                user_session.is_staff or 
                user_session.is_superuser or 
                user_session.username in usuarios_autorizados or
                getattr(user_session, 'pertenece_a', None) in usuarios_autorizados
            )
            
            arrendatario = None
            contrato = None
            
            if es_usuario_autorizado:
                print(f"Usuario autorizado para incidencias Arrendify: {user_session.username}")
                # Para usuarios autorizados, crear incidencia sin arrendatario/contrato
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": None,
                    "contrato": None,
                    "incidencia": data.get('incidencia', ''),
                    "tipo_incidencia": data.get('tipo_incidencia', ''),
                    "prioridad": data.get('prioridad', 'Media'),
                    "status": "Pendiente de Revisión",
                }
                print(f"Creando incidencia Arrendify sin asociaciones: User={user_session.id}")
            else:
                # Lógica original para usuarios regulares
                nombre_usuario = user_session.first_name.strip()
                print(f"Nombre completo del usuario: {nombre_usuario}")
                
                # Intentar diferentes estrategias de búsqueda
                arrendatario = None
                
                # Estrategia 1: Buscar por nombre completo
                arrendatario = Arrendatarios_garzasada.objects.filter(
                    Q(nombre_arrendatario__icontains=nombre_usuario) |
                    Q(nombre_empresa_pm__icontains=nombre_usuario)
                ).first()
                
                # Estrategia 2: Si no encuentra, buscar por primer nombre
                if not arrendatario:
                    primer_nombre = nombre_usuario.split()[0] if nombre_usuario else ""
                    print(f"Buscando por primer nombre: {primer_nombre}")
                    arrendatario = Arrendatarios_garzasada.objects.filter(
                        Q(nombre_arrendatario__icontains=primer_nombre) |
                        Q(nombre_empresa_pm__icontains=primer_nombre)
                    ).first()
                
                # Estrategia 3: Si aún no encuentra, buscar por palabras individuales
                if not arrendatario:
                    palabras = nombre_usuario.split()
                    for palabra in palabras:
                        if len(palabra) > 2:  # Solo palabras de más de 2 caracteres
                            print(f"Buscando por palabra: {palabra}")
                            arrendatario = Arrendatarios_garzasada.objects.filter(
                                Q(nombre_arrendatario__icontains=palabra) |
                                Q(nombre_empresa_pm__icontains=palabra)
                            ).first()
                            if arrendatario:
                                break
                
                # Estrategia 4: Buscar por relación directa con el usuario
                if not arrendatario:
                    print("Buscando arrendatario asociado directamente al usuario")
                    arrendatario = Arrendatarios_garzasada.objects.filter(user=user_session).first()
                
                if not arrendatario:
                    return Response({
                        'error': f'No se encontró arrendatario para el usuario: {nombre_usuario}',
                        'debug_info': f'User ID: {user_session.id}, Username: {user_session.username}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                print(f"Arrendatario encontrado: {arrendatario.nombre_arrendatario or arrendatario.nombre_empresa_pm} (ID: {arrendatario.id})")
                
                # Buscar contrato relacionado
                try:
                    contrato = GarzaSadaContratos.objects.get(arrendatario=arrendatario)
                    print(f"Contrato encontrado: {contrato.id}")
                except GarzaSadaContratos.DoesNotExist:
                    return Response({'error': f'Contrato no encontrado para el arrendatario ID: {arrendatario.id}'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Crear Incidencia para usuario regular
                incidencia_data = {
                    "user": user_session.id,
                    "arrendatario": arrendatario.id,
                    "contrato": contrato.id,
                    "incidencia": data.get('incidencia', ''),
                    "status": "Pendiente de Revisión",
                }
                print(f"Creando incidencia regular con: User={user_session.id}, Arrendatario={arrendatario.id}, Contrato={contrato.id}")
            
            arrendamientos_serializer = self.get_serializer(data=incidencia_data)
            arrendamientos_serializer.is_valid(raise_exception=True)
            arrendamientos_serializer.save()
            
            print("Incidencia creada exitosamente....✅")
            return Response(arrendamientos_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)       
        
#////////////////////////CONTRATOS GARZA SADA///////////////////////////////
class Contratos_GarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = GarzaSadaContratos.objects.all()
    serializer_class = ContratoGarzaSadaSerializer
    
    def list(self, request, *args, **kwargs):
        try:
           user_session = request.user       
           if user_session.is_staff or user_session.username == "GarzaSada":
               print("Listar contratos Garza Sada....")
               # ✅ Incluir datos del arrendatario con select_related
               contratos =  GarzaSadaContratos.objects.select_related('arrendatario').all().order_by('-id')
               serializer = self.get_serializer(contratos, many=True)
               serialized_data = serializer.data
                
               # Agregar el campo 'is_staff'
               for item in serialized_data:
                 item['is_staff'] = True
                
               return Response(serialized_data)
           
           elif user_session.rol == "Inmobiliaria":#La inmobiliaria ve todos los contratos de sus agentes y los suyos
               print("Inmobiliaria ====>", user_session.name_inmobiliaria)
               agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) #primero obtenemos mis agentes.
               contratos_inmobiliaria = GarzaSadaContratos.objects.filter(user_id = user_session.id)#Obetenemos los contratos de la inmobiliaria
               contratos_agentes = GarzaSadaContratos.objects.filter(user_id__in = agentes.values("id"))#Obtenemos los contratos de los agentes que pertenecen a la inmobiliaria
               contratos_all = contratos_inmobiliaria.union(contratos_agentes)#Hacemos union de los contratos de la inmobiliaria y los agentes
               contratos_all = contratos_all.order_by('-id')#Ordenamos por id descendente
               
               serializer = self.get_serializer(contratos_all, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
               
           elif user_session.rol == "Agente":#El agente solo ve sus contratos
               print("Agente ====>", user_session.first_name)
               residentes_agente = GarzaSadaContratos.objects.filter(user_id = user_session).order_by('-id')#Obtenemos los contratos del agente y oredenamos por id descendente
               serializer = self.get_serializer(residentes_agente , many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
           
           elif user_session.rol == "Residente" and user_session.pertenece_a == "GarzaSada":#El residente ve sus contratos
                print("Residente ====>", user_session.first_name)
                nombre_busqueda = (user_session.first_name).strip()

                # Si no hay nombre para filtrar, retorna lista vacía por seguridad
                if not nombre_busqueda:
                    return Response([], status=status.HTTP_200_OK)

                contratos_residente = (
                    GarzaSadaContratos.objects
                    .filter(
                        Q(arrendatario__nombre_arrendatario__icontains=nombre_busqueda) |
                        Q(arrendatario__nombre_empresa_pm__icontains=nombre_busqueda)
                    )
                    .order_by('-id')
                )

                serializer = self.get_serializer(contratos_residente, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)

           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print("Datos a Guardar ====>",request.data)
            print("Creando contrato Garza Sada....📑")
            
            fecha_actual = date.today()
            contrato_serializer = self.serializer_class(data = request.data) #Usa el serializer_class
            if contrato_serializer.is_valid():
                nuevo_proceso = ProcesoContrato_garzasada.objects.create(usuario = user_session, fecha = fecha_actual, status_proceso = "En Revisión")
                if nuevo_proceso:
                    print("ID Contrato nuevo ====>",nuevo_proceso.id)
                    info = contrato_serializer.save(user = user_session)
                    nuevo_proceso.contrato = info
                    nuevo_proceso.save()
                    #send_noti_varios(FraternaContratos, request, title="Nueva solicitud de contrato en Fraterna", text=f"A nombre del Arrendatario {info.residente.nombre_arrendatario}", url = f"fraterna/contrato/#{info.residente.id}_{info.cama}_{info.no_depa}")
                    #print("despues de metodo send_noti")#descomentar para notificaciones
                    print("Se genero nueva solicitud de contrato Garza Sada....✅")
                    return Response({'Semillero': contrato_serializer.data}, status=status.HTTP_201_CREATED)
                else:
                    print("No se creo el proceso de contrato Garza Sada....❌")
                    return Response({'msj':'no se creo el proceso'}, status=status.HTTP_204_NO_CONTENT) 
            
            else:
                print("serializer no valido")
                return Response({'msj':'no es valido el serializer'}, status=status.HTTP_204_NO_CONTENT)     
            
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try:
            print("Actualizando contrato Garza Sada....🔄")
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
           
                        
            proceso = ProcesoContrato_garzasada.objects.all().get(contrato_id = instance.id)
            print("Contador ====> ",proceso.contador)
            if (proceso.contador > 0 ):
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                if serializer.is_valid(raise_exception=True):
                    self.perform_update(serializer)
                    proceso.contador = proceso.contador - 1
                    proceso.save()
                    print("Edito contrato Garza Sada correctamente....✅")
                    #send_noti_varios(SemilleroContratos, request, title="Se a modificado el contrato de:", text=f"FRATERNA VS {instance.residente.nombre_arrendatario} - {instance.residente.nombre_residente}".upper(), url = f"fraterna/contrato/#{instance.residente.id}_{instance.cama}_{instance.no_depa}")
                    return Response(serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response({'errors': serializer.errors})
            else:
                return Response({'msj': 'LLegaste al limite de tus modificaciones en el proceso'}, status=status.HTTP_205_RESET_CONTENT)
      
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy(self,request, *args, **kwargs):
        try:
            print("Eliminando contrato Garza Sada....🗑️")
            residente = self.get_object()
            if residente:
                residente.delete()
                print("Contrato eliminado correctamente....✅")
                return Response({'message': 'residente eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
    @action(detail=False, methods=['post'], url_path='subir_contrato_pdf')
    def subir_contrato_pdf(self, request, *args, **kwargs):
        """
        Sube un contrato PDF (modo 'subir').
        Body:
          - arrendatario: ID del arrendatario (FK)
          - filename: nombre del archivo (sugerido)
          - mimetype: application/pdf
          - size: tamaño bytes (informativo)
          - data_base64: PDF en base64 (sin encabezado data:)
          - no_depa: (opcional) para asociar
        """
        try:
            data = request.data
            arr_id = data.get('arrendatario')
            filename = data.get('filename') or 'contrato.pdf'
            b64 = data.get('data_base64')
            no_depa = data.get('no_depa')
            fecha_celebracion_raw = data.get('fecha_celebracion')

            if not arr_id or not b64:
                return Response({'error': 'arrendatario y data_base64 son requeridos'}, status=400)

            # decodificar
            try:
                file_bytes = base64.b64decode(b64)
            except Exception:
                return Response({'error': 'data_base64 inválido'}, status=400)

            # crear contrato mínimo
            arr = Arrendatarios_garzasada.objects.filter(pk=arr_id).first()
            if not arr:
                return Response({'error': 'Arrendatario no encontrado'}, status=404)

            fecha_celebracion = date.today()
            if fecha_celebracion_raw:
                try:
                    fecha_celebracion = datetime.strptime(str(fecha_celebracion_raw), "%Y-%m-%d").date()
                except Exception:
                    return Response({'error': 'fecha_celebracion inválida, usa formato YYYY-MM-DD'}, status=400)

            contrato = GarzaSadaContratos.objects.create(
                user=request.user if request.user.is_authenticated else None,
                arrendatario=arr,
                no_depa=no_depa or None,
                fecha_celebracion=fecha_celebracion,
            )

            # guardar archivo
            contrato.contrato_pdf.save(filename, ContentFile(file_bytes), save=True)

            # crear proceso “En Revisión”, igual que en create()
            fecha_actual = date.today()
            proceso = ProcesoContrato_garzasada.objects.create(
                usuario=request.user,
                fecha=fecha_actual,
                status_proceso="En Revisión",
                contrato=contrato
            )

            return Response({
                'id': contrato.id,
                'arrendatario': contrato.arrendatario_id,
                'no_depa': contrato.no_depa,
                'fecha_celebracion': str(contrato.fecha_celebracion) if getattr(contrato, 'fecha_celebracion', None) else None,
                'archivo': contrato.contrato_pdf.url if contrato.contrato_pdf else None,
                'proceso': proceso.status_proceso,
            }, status=201)

        except Exception as e:
            print(f"error subir_contrato_pdf: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en {exc_tb.tb_frame.f_code.co_name} línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=400)
    
    
    def aprobar_contrato_garzasada(self, request, *args, **kwargs):
        try:
            print("Aprobar Contrato Garza Sada")
            print("Contrato a Aprobar ====>",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("ID ====>",instance.id)
            print(instance.__dict__)
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_garzasada.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            print("Proceso aprobado correctamente....✅")
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def desaprobar_contrato_garzasada(self, request, *args, **kwargs):
        try:
            print("Desaprobar Contrato Garza Sada")
            instance = self.queryset.get(id = request.data["id"])
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_garzasada.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = "En Revisión"
            # proceso.contador = 2 # en vista que me indiquen lo contrario lo dejamos asi
            proceso.save()
            print("Proceso desaprobado correctamente....✅")
            return Response({'Exito': 'Se cambio el estatus a desaprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
   
    def generar_paquete_completo_garzasada(self, request, *args, **kwargs):
        """
        Devuelve el paquete combinado en formato PDF descargable para visualizar en el front.
        """
        try:
            print("Generando paquete completo Garza Sada...")
            data = request.data
            if isinstance(data, dict):
                id_paq = data["id"]
                pagare_distinto = data.get("pagare_distinto", "No")
                cantidad_pagare = data.get("cantidad_pagare", "0")
                testigo1 = data.get("testigo1", "")
                testigo2 = data.get("testigo2", "")
            else:
                id_paq = data
                pagare_distinto = "No"
                cantidad_pagare = "0"

            nombre_archivo, pdf_bytes, total_paginas = self.generar_paquete_garzasada_pdf(id_paq, pagare_distinto, cantidad_pagare, testigo1, testigo2)

            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Paquete Garza Sada {nombre_archivo}"'
            response.write(pdf_bytes)
            print("paginas totales ====>", total_paginas)

            print("Paquete completo generado exitosamente")
            return response

        except Exception as e:
            print(f"Error en generar_paquete_completo_garzasada: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                        f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def generar_paquete_garzasada_pdf(self, id_paq, pagare_distinto="No", cantidad_pagare="0", testigo1="", testigo2=""):
            total_paginas = {"arrendamiento": 0, "poliza": 0, "pagares": 0}
            
            print("Soy el self",self)

            info = self.queryset.filter(id=id_paq).first()
            if not info:
                raise ValueError("Contrato no encontrado")

            pdf_writer = PdfWriter()

            # ===== 1) CONTRATO =====
            # Prioridad: 1) base64, 2) FileField, 3) generar desde plantilla
            if info.contrato_pdf_b64:
                print("Usando contrato PDF desde base64 subido...")
                import base64
                contrato_bytes = base64.b64decode(info.contrato_pdf_b64)
                contrato_reader = PdfReader(io.BytesIO(contrato_bytes))
            else:
                print("Generando contrato desde plantilla...")
                contrato_pdf = self._generar_contrato_garzasada_interno(info, testigo1=testigo1, testigo2=testigo2)
                contrato_reader = PdfReader(io.BytesIO(contrato_pdf))

            total_paginas["arrendamiento"] = len(contrato_reader.pages)
            for page in contrato_reader.pages:
                pdf_writer.add_page(page)

            # ===== 2) POLIZA =====
            poliza_pdf = self._generar_poliza_garzasada_interno(info)
            poliza_reader = PdfReader(io.BytesIO(poliza_pdf))
            total_paginas["poliza"] = len(poliza_reader.pages)
            for page in poliza_reader.pages:
                pdf_writer.add_page(page)

            # ===== 3) PAGARÉS =====
            pagare_pdf = self._generar_pagare_garzasada_interno(info, pagare_distinto, cantidad_pagare)
            pagare_reader = PdfReader(io.BytesIO(pagare_pdf))
            total_paginas["pagares"] = len(pagare_reader.pages)
            for page in pagare_reader.pages:
                pdf_writer.add_page(page)

            output_pdf = io.BytesIO()
            pdf_writer.write(output_pdf)
            output_pdf.seek(0)

            fecha_actual = dt.now().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"Paquete_Completo_GarzaSada_{info.arrendatario.nombre_arrendatario}_{fecha_actual}.pdf"

            return nombre_archivo, output_pdf.getvalue(), total_paginas
        
    def generar_pagare_garzasada(self, request, *args, **kwargs):
        try:
            #activamos la libreri de locale para obtener el mes en español
            print("Generar Pagare Garza Sada")
            locale.setlocale(locale.LC_ALL,"es_MX.utf8")
            print("data pagare ====>",request.data)
            id_paq = request.data["id"]
            pagare_distinto = request.data["pagare_distinto"]

            if pagare_distinto == "Si":
                if "." not in request.data["cantidad_pagare"]:
                    print("No tiene decimales....")
                    cantidad_pagare = request.data["cantidad_pagare"]
                    cantidad_decimal = "00"
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
                
                else:
                    cantidad_completa = request.data["cantidad_pagare"].split(".")
                    cantidad_pagare = cantidad_completa[0]
                    cantidad_decimal = cantidad_completa[1]
                    cantidad_letra = num2words(cantidad_pagare, lang='es')
            else:
                cantidad_pagare = 0
                cantidad_decimal = "00"
                cantidad_letra = num2words(cantidad_pagare, lang='es')
            print(pagare_distinto)
            print(cantidad_pagare)
            
            print("ID ====>", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print("Datos Inquilino ====>",info.__dict__)
            # Definir la fecha inicial
            fecha_inicial = info.fecha_celebracion
            print("Fecha Celebracion ====>",fecha_inicial)
            #fecha_inicial = datetime(2024, 3, 20)
            #checar si cambiar el primer dia o algo asi
            # fecha inicial move in
            dia = fecha_inicial.day
            
            # Definir la duración en meses
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            print("MESES ====>",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_inicial < fecha_final:
                nombre_mes = fecha_inicial.strftime("%B")  # %B da el nombre completo del mes
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_inicial.year))      
                fecha_inicial += relativedelta(months=1)
            
            print("Fechas Iteradas ====>",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            for month, year in fechas_iteradas:
                print(f"Año: {year}, Mes: {month}")
            
            #obtenermos la renta para pasarla a letra
            if "." not in info.renta:
                print("No hay decimales en renta")
                number = int(info.renta)
                renta_decimal = "00"
                text_representation = num2words(number, lang='es').capitalize()
               
            else:
                print("Hay decimales en renta")
                renta_completa = info.renta.split(".")
                info.renta = renta_completa[0]
                renta_decimal = renta_completa[1]
                text_representation = num2words(renta_completa[0], lang='es').capitalize()
           
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses, 'pagare_distinto':pagare_distinto , 'cantidad_pagare':cantidad_pagare, 'cantidad_letra':cantidad_letra,'cantidad_decimal':cantidad_decimal, 'renta_decimal':renta_decimal}
            
            template = 'home/pagare_garzasada.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Se genero el pagare correctamente....✅")
            return HttpResponse(response, content_type='application/pdf')
    
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_poliza_garzasada(self, request, *args, **kwargs):
        try:
            print("Generar Poliza Garza Sada")
            id_paq = request.data
            print("ID ====>", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)
            
            #vamos a genenrar el numero de contrato
            arrendatario = info.arrendatario.nombre_arrendatario
            primera_letra = arrendatario[0].upper()  # Obtiene la primera letra
            ultima_letra = arrendatario[-1].upper()  # Obtiene la última letra

            year = info.fecha_celebracion.strftime("%g")
            month = info.fecha_celebracion.strftime("%m")
            
            nom_contrato = f"AFY{month}{year}CX51{info.id}CA{primera_letra}{ultima_letra}"  
            print("Nombre del contrato", nom_contrato)     
            #obtenemos renta y costo poliza para letra
            # Convertir primero a float para manejar valores decimales como '8400.00'
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
       
            context = {'info': info, 'renta_texto':renta_texto, 'nom_contrato':nom_contrato,}
            template = 'home/poliza_garzasada.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO POLIZA")
            return HttpResponse(response, content_type='application/pdf')
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_contrato_garzasada(self, request, *args, **kwargs):
        try:
            print("Generar contrato Garza Sada")
            print("Data Entrante ====>", request.data)
            id_paq = request.data["id"]
            testigo1 = request.data["testigo1"]
            testigo2 = request.data["testigo2"]
            print("Testigo 1 ====>",testigo1)
            print("Testigo 2 ====>",testigo2)
            print("ID ====>", id_paq)
            info = self.queryset.filter(id=id_paq).first()
            print("Diccionario ====>",info.__dict__)
            
            #convertir m2 a texto
            superficie = float(info.superficie)
            superficie_texto=f"{num2words(float(superficie), lang='es')}"
            
            # 🧠 Convertir renta con centavos a texto
            renta = float(info.renta)
            parte_entera = int(renta)
            centavos = round((renta - parte_entera) * 100)
            renta_texto = f"{num2words(parte_entera, lang='es')} pesos"
            if centavos > 0:
                renta_texto += f" con {num2words(centavos, lang='es')} centavos"
            renta_texto = renta_texto.capitalize()
            
            # 🧠 Convertir deposito con centavos a texto
            deposito = float(info.deposito)
            parte_entera_deposito = int(deposito)
            centavos_deposito = round((deposito - parte_entera_deposito) * 100)
            deposito_texto = f"{num2words(parte_entera_deposito, lang='es')} pesos"
            if centavos_deposito > 0:
                deposito_texto += f" con {num2words(centavos, lang='es')} centavos"
            deposito_texto = deposito_texto.capitalize()
            
            #Obtener rentas antiicipadas
            anticipadas = float(info.anticipadas)
            rentas_anticipadas = float(anticipadas * renta)
            anticipadas_texto = f"{num2words(float(rentas_anticipadas), lang='es')} pesos"
            
            # Obtener los datos de la vigencia
            vigencia = info.duracion.split(" ")
            num_vigencia = vigencia[0]
            print("Vigencia ====>",num_vigencia)

            print("Generando Codigo de paquete...")
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            if info.id < 9:
                info.id = f"0{info.id}"
            print("Fecha Celebracion ====>", fec)
            
            # Obtener mes correspondiente a pago de renta
            # Generar rango del mes siguiente basado en la fecha de celebración
            fecha_celebracion = info.fecha_celebracion

            # Obtener el primer día del mes siguiente
            primer_dia_siguiente = fecha_celebracion.replace(day=1) + relativedelta(months=1)

            # Obtener el último día del mes siguiente
            ultimo_dia_siguiente = primer_dia_siguiente + relativedelta(months=1) - relativedelta(days=1)

            # Diccionario de meses en español
            meses_espanol = {
                1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
                5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
                9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
            }

            # Formatear las fechas en español
            rango_mes_siguiente = f"{primer_dia_siguiente.day:02d} de {meses_espanol[primer_dia_siguiente.month]} {primer_dia_siguiente.year} al {ultimo_dia_siguiente.day:02d} de {meses_espanol[ultimo_dia_siguiente.month]} {ultimo_dia_siguiente.year}"

            print("Rango del mes siguiente ====>", rango_mes_siguiente)
            
            # Calcular 1 mes antes de la fecha de vigencia
            fecha_vigencia = info.fecha_terminacion
            if fecha_vigencia:
                # Obtener 1 mes antes de la fecha de vigencia
                fecha_un_mes_antes_vigencia = fecha_vigencia - relativedelta(months=1)
                
                # Formatear la fecha en español
                mes_antes_vigencia = f"{fecha_un_mes_antes_vigencia.day:02d} de {meses_espanol[fecha_un_mes_antes_vigencia.month]} {fecha_un_mes_antes_vigencia.year}"
                
                print("Un mes antes de vigencia ====>", mes_antes_vigencia)
            else:
                # Si no hay fecha de vigencia, calcular basándose en fecha de celebración + duración
                duracion_meses = int(num_vigencia)  # Ya tienes num_vigencia calculado
                fecha_fin_vigencia = fecha_celebracion + relativedelta(months=duracion_meses)
                fecha_un_mes_antes_vigencia = fecha_fin_vigencia - relativedelta(months=1)
                
                # Formatear la fecha en español
                mes_antes_vigencia = f"{fecha_un_mes_antes_vigencia.day:02d} de {meses_espanol[fecha_un_mes_antes_vigencia.month]} {fecha_un_mes_antes_vigencia.year}"
                
                print("Un mes antes de vigencia (calculado) ====>", mes_antes_vigencia)

            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" + f"{info.id}" + "CA" + na
            print("Numero Paquete ====>", nom_paquete.upper())

            context = {
                'info': info,
                'renta_texto': renta_texto,
                'deposito_texto': deposito_texto,
                'superficie_texto': superficie_texto,
                'rentas_anticipadas': rentas_anticipadas,
                'anticipadas_texto': anticipadas_texto,
                'num_vigencia': num_vigencia,
                'nom_paquete': nom_paquete,
                'rango_mes_siguiente': rango_mes_siguiente,
                'mes_antes_vigencia': mes_antes_vigencia,
                "testigo1": testigo1,
                "testigo2": testigo2
            }
            # Para depurar el contexto
            print("Context ===> ",context)

            template = 'home/contrato_ga_sa.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("Contrato generado correctamente....✅")

            return HttpResponse(response, content_type='application/pdf')

        except Exception as e:
            print(f"el error en generar_contrato_garzasada es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST) 
        
    @action(detail=False, methods=['post'], url_path='descargar_contrato_base64')
    def descargar_contrato_base64(self, request, *args, **kwargs):
        """Descarga el contrato subido (almacenado en base64) como PDF"""
        try:
            print("Descargar contrato desde base64")
            print("Data Entrante ====>", request.data)
            
            id_contrato = request.data.get("id")
            if not id_contrato:
                return Response({'error': 'ID de contrato requerido'}, status=status.HTTP_400_BAD_REQUEST)
            
            info = self.queryset.filter(id=id_contrato).first()
            if not info:
                return Response({'error': 'Contrato no encontrado'}, status=status.HTTP_404_NOT_FOUND)
            
            if not info.contrato_pdf_b64:
                return Response({'error': 'No hay contrato en base64 para este registro'}, status=status.HTTP_404_NOT_FOUND)
            
            # Decodificar base64 a bytes
            import base64
            pdf_bytes = base64.b64decode(info.contrato_pdf_b64)
            
            # Devolver como PDF
            response = HttpResponse(content_type=info.contrato_mimetype or 'application/pdf')
            filename = info.contrato_filename or f'contrato_{id_contrato}.pdf'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.write(pdf_bytes)
            
            print(f"Contrato base64 descargado correctamente: {filename} ✅")
            return response
            
        except Exception as e:
            print(f"Error en descargar_contrato_base64: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def _generar_contrato_garzasada_interno(self, info, testigo1="", testigo2=""):
        """Función interna para generar el PDF del contrato de Garza Sada"""
        try:
            print(" Generando contrato Garza Sada interno...")
            print(f"   - Arrendatario: {info.arrendatario.nombre_arrendatario if info.arrendatario else 'NONE'}")
            print(f"   - Testigo1: {testigo1}, Testigo2: {testigo2}")
            
            # Convertir m2 a texto
            superficie = float(info.superficie) if info.superficie else 0
            print(f"   - Superficie: {superficie} m2")
            superficie_texto = f"{num2words(float(superficie), lang='es')}"
            
            # Convertir renta con centavos a texto
            renta = float(info.renta) if info.renta else 0
            print(f"   - Renta: ${renta}")
            parte_entera = int(renta)
            centavos = round((renta - parte_entera) * 100)
            renta_texto = f"{num2words(parte_entera, lang='es')} pesos"
            if centavos > 0:
                renta_texto += f" con {num2words(centavos, lang='es')} centavos"
            renta_texto = renta_texto.capitalize()
            
            # Convertir deposito con centavos a texto
            deposito = float(info.deposito)
            parte_entera_deposito = int(deposito)
            centavos_deposito = round((deposito - parte_entera_deposito) * 100)
            deposito_texto = f"{num2words(parte_entera_deposito, lang='es')} pesos"
            if centavos_deposito > 0:
                deposito_texto += f" con {num2words(centavos_deposito, lang='es')} centavos"
            deposito_texto = deposito_texto.capitalize()
            
            # Obtener rentas anticipadas
            anticipadas = float(info.anticipadas)
            rentas_anticipadas = float(anticipadas * renta)
            anticipadas_texto = f"{num2words(float(rentas_anticipadas), lang='es')} pesos"
            
            # Obtener los datos de la vigencia
            vigencia = info.duracion.split(" ")
            num_vigencia = vigencia[0]
            
            # Generar código de paquete
            na = str(info.arrendatario.nombre_arrendatario)[0:1] + str(info.arrendatario.nombre_arrendatario)[-1]
            fec = str(info.fecha_celebracion).split("-")
            id_formatted = f"0{info.id}" if info.id < 9 else str(info.id)
            
            dia = fec[2]
            mes = fec[1]
            anio = fec[0][2:4]
            nom_paquete = "AFY" + dia + mes + anio + "CX" + "24" + id_formatted + "CA" + na
            
            # Generar rango del mes siguiente basado en la fecha de celebración
            fecha_celebracion = info.fecha_celebracion
            primer_dia_siguiente = fecha_celebracion.replace(day=1) + relativedelta(months=1)
            ultimo_dia_siguiente = primer_dia_siguiente + relativedelta(months=1) - relativedelta(days=1)
            
            # Diccionario de meses en español
            meses_espanol = {
                1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
                5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
                9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
            }
            
            rango_mes_siguiente = f"{primer_dia_siguiente.day:02d} de {meses_espanol[primer_dia_siguiente.month]} {primer_dia_siguiente.year} al {ultimo_dia_siguiente.day:02d} de {meses_espanol[ultimo_dia_siguiente.month]} {ultimo_dia_siguiente.year}"
            
            # Calcular 1 mes antes de la fecha de vigencia
            fecha_vigencia = info.fecha_terminacion
            if fecha_vigencia:
                fecha_un_mes_antes_vigencia = fecha_vigencia - relativedelta(months=1)
                mes_antes_vigencia = f"{fecha_un_mes_antes_vigencia.day:02d} de {meses_espanol[fecha_un_mes_antes_vigencia.month]} {fecha_un_mes_antes_vigencia.year}"
            else:
                duracion_meses = int(num_vigencia)
                fecha_fin_vigencia = fecha_celebracion + relativedelta(months=duracion_meses)
                fecha_un_mes_antes_vigencia = fecha_fin_vigencia - relativedelta(months=1)
                mes_antes_vigencia = f"{fecha_un_mes_antes_vigencia.day:02d} de {meses_espanol[fecha_un_mes_antes_vigencia.month]} {fecha_un_mes_antes_vigencia.year}"
            
            context = {
                'info': info,
                'renta_texto': renta_texto,
                'deposito_texto': deposito_texto,
                'superficie_texto': superficie_texto,
                'rentas_anticipadas': rentas_anticipadas,
                'anticipadas_texto': anticipadas_texto,
                'num_vigencia': num_vigencia,
                'nom_paquete': nom_paquete,
                'rango_mes_siguiente': rango_mes_siguiente,
                'mes_antes_vigencia': mes_antes_vigencia,
                "testigo1": testigo1,
                "testigo2": testigo2
            }
            
            template = 'home/contrato_ga_sa.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando contrato Garza Sada interno: {e}")
            raise e

    def _generar_poliza_garzasada_interno(self, info):
        """Función interna para generar el PDF de la póliza de Garza Sada"""
        try:
            print("Generando póliza Garza Sada interno...")
            
            # Generar el número de contrato
            arrendatario = info.arrendatario.nombre_arrendatario
            primera_letra = arrendatario[0].upper()
            ultima_letra = arrendatario[-1].upper()
            
            year = info.fecha_celebracion.strftime("%g")
            month = info.fecha_celebracion.strftime("%m")
            
            nom_contrato = f"AFY{month}{year}CX51{info.id}CA{primera_letra}{ultima_letra}"
            
            # Obtener renta y costo poliza para letra
            renta = int(float(info.renta))
            renta_texto = num2words(renta, lang='es').capitalize()
            
            context = {
                'info': info, 
                'renta_texto': renta_texto, 
                'nom_contrato': nom_contrato
            }
            
            template = 'home/poliza_garzasada.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando póliza Garza Sada interno: {e}")
            raise e

    def _generar_pagare_garzasada_interno(self, info, pagare_distinto="No", cantidad_pagare="0"):
        """Función interna para generar el PDF del pagaré de Garza Sada"""
        try:
            print("Generando pagaré Garza Sada interno...")
            locale.setlocale(locale.LC_ALL, "es_MX.utf8")
            
            # Procesar cantidad del pagaré
            if pagare_distinto == "Si":
                if "." not in str(cantidad_pagare):
                    cantidad_decimal = "00"
                    cantidad_letra = num2words(int(cantidad_pagare), lang='es')
                else:
                    cantidad_completa = str(cantidad_pagare).split(".")
                    cantidad_pagare = cantidad_completa[0]
                    cantidad_decimal = cantidad_completa[1]
                    cantidad_letra = num2words(int(cantidad_pagare), lang='es')
            else:
                cantidad_pagare = 0
                cantidad_decimal = "00"
                cantidad_letra = num2words(0, lang='es')
            
            # Definir la fecha inicial
            fecha_inicial = info.fecha_celebracion
            dia = fecha_inicial.day
            
            # Definir la duración en meses
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            
            # Calcular la fecha final
            fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
            
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            fecha_temp = fecha_inicial
            
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_temp < fecha_final:
                nombre_mes = fecha_temp.strftime("%B")
                fechas_iteradas.append((nombre_mes.capitalize(), fecha_temp.year))
                fecha_temp += relativedelta(months=1)
            
            # Obtener la renta para pasarla a letra
            if "." not in str(info.renta):
                number = int(info.renta)
                renta_decimal = "00"
                text_representation = num2words(number, lang='es').capitalize()
            else:
                renta_completa = str(info.renta).split(".")
                renta_valor = renta_completa[0]
                renta_decimal = renta_completa[1]
                text_representation = num2words(int(renta_valor), lang='es').capitalize()
            
            context = {
                'info': info, 
                'dia': dia,
                'lista_fechas': fechas_iteradas, 
                'text_representation': text_representation, 
                'duracion_meses': duracion_meses, 
                'pagare_distinto': pagare_distinto,
                'cantidad_pagare': cantidad_pagare, 
                'cantidad_letra': cantidad_letra,
                'cantidad_decimal': cantidad_decimal, 
                'renta_decimal': renta_decimal
            }
            
            template = 'home/pagare_garzasada.html'
            html_string = render_to_string(template, context)
            pdf_file = HTML(string=html_string).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            print(f"Error generando pagaré Garza Sada interno: {e}")
            raise e
        
#////////////////INICIO INTEGRACION ZAPSIGN/////////////////////    
    
    def _construir_firmantes_garzasada(self, singer):
        """Construye la lista de firmantes para contratos Garza Sada"""
        firmantes = []
        
        # Firmante 0: Fraterna (representa a Garza Sada)
        firmantes.append({
            "name": "FRATERNA ADMINISTRADORA DE PROYECTOS, S.A. DE C.V.'' REPRESENTADA POR ALMA GABRIELA GRANADOS CASTILLO",
            "phone_country": "52",
            # TODO: Agregar email y teléfono del representante de Garza Sada
        })
        
        # Firmante 1: Arrendatario
        firmantes.append({
            "name": singer["nombre_arrendatario"],
            "email": singer["correo_arrendatario"],
            "phone_country": "52",
            "phone_number": singer["celular_arrendatario"],
            "send_automatic_email": True,
            "send_automatic_whatsapp": False,
        })
        
        # Firmante 2: Obligado solidario (solo si existe)
        nombre_obligado = singer.get("nombre_obligado", "").strip()
        if nombre_obligado:
            firmantes.append({
                "name": nombre_obligado,
                "email": singer.get("correo_obligado", singer["correo_arrendatario"]),
                "phone_country": "52",
                "phone_number": singer.get("celular_obligado", singer["celular_arrendatario"]),
                "send_automatic_email": True,
                "send_automatic_whatsapp": False,
            })
        
        # Firmante final: Jonathan Guadarrama
        firmantes.append({
            "name": "JONATHAN GUADARRAMA SALGADO",
            "email": "genaro.guadarrama@arrendify.com",
            "phone_country": "52",
            "phone_number": "5531398629",
            "send_automatic_email": True,
        })
        
        return firmantes

    def build_payload_to_zapsign(self, contrato_data):
        """ Datos del contrado: contrato_data = {"id", "filename", "base64_pfd", "residente"}
            Aquí armamos el payload que se va enviar para la solicitud
            de creacion del documento 

        """
        data = contrato_data
        singer = data["arrendatario"]
        brand_logo = "https://pagosprueba.s3.us-east-1.amazonaws.com/ZapSign/logo-contratodearrendamiento.webp"

        payload = {
            "base64_pdf": data["base64_pdf"],
            "name": data["filename"],
            "signers": self._construir_firmantes_garzasada(singer),
            "lang": "es",
            "disable_signer_emails": False,
            "brand_logo": brand_logo,
            "brand_primary_color": "#672584",
            "brand_name": "Arrendify",
            "folder_path": "/GARZASADA",
            "created_by": "juridico.arrendify1@gmail.com",
            "signature_order_active": False,
            "reminder_every_n_days": 0,
            "allow_refuse_signature": True,
            "disable_signers_get_original_file": False
        }
        
        return payload
    
    def armar_payload_posiciones_firma(self, signer_tokens, total_paginas, arrendatario):
        rubricas = []

        # Calcular offsets por sección
        offsets = {}
        acumulador = 0
        for nombre, paginas in total_paginas.items():
            offsets[nombre] = acumulador
            acumulador += paginas

        # Definir posiciones por sección
        posiciones_por_seccion = {
            "comodato": [
                (0, 5.0, 5.0, 0),
                (0, 5.0, 75.0, 1),
                (1, 13.0, 18.0, 0),
                (1, 13.0, 65.0, 1),
                (2, 5.0, 75.0, 1),
                (3, 26.5, 18.0, 1)
            ],
            "arrendamiento": [],
            "manual": [],
            "poliza": [],
            "pagares": []
        }

        # ARRRENDAMIENTO: [0, 1, 2] en cada página (izq-centro-der)
        arr_total = total_paginas["arrendamiento"]
        for i in range(arr_total):
            posiciones_por_seccion["arrendamiento"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 2)
            ])

        # MANUAL: [1, 2] más separados en la parte baja derecha
        man_total = total_paginas["manual"]
        for i in range(man_total):
            posiciones_por_seccion["manual"].extend([
                (i, 5.0, 55.0, 1),
                (i, 5.0, 80.0, 2)
            ])

        # POLIZA: [0, 1, 3] (izq-centro-der)
        pol_total = total_paginas["poliza"]
        for i in range(pol_total):
            posiciones_por_seccion["poliza"].extend([
                (i, 5.0, 5.0, 0),
                (i, 5.0, 40.0, 1),
                (i, 5.0, 75.0, 3)
            ])

        # PAGARES: firmantes condicionales según residente.aval y edad
        pag_total = total_paginas["pagares"]

        aval = arrendatario.get("aval", "").strip()
        edad = int(arrendatario.get("edad", 0))

        for i in range(pag_total):
            # Firmante 2 (residente) siempre firma
            posiciones_por_seccion["pagares"].append((i, 16.0, 55.0, 2))

            # Si la condición se cumple, también firma el firmante 1 (arrendatario)
            if aval == "Si" and edad >= 18:
                posiciones_por_seccion["pagares"].append((i, 33.0, 55.0, 1))

        # Construcción final del payload con offset aplicado
        for seccion, posiciones in posiciones_por_seccion.items():
            offset = offsets[seccion]
            for page, bottom, left, signer_index in posiciones:
                if signer_index < len(signer_tokens):
                    rubricas.append({
                        "page": page + offset,
                        "relative_position_bottom": bottom,
                        "relative_position_left": left,
                        "relative_size_x": 19.55,
                        "relative_size_y": 9.42,
                        "type": "signature",
                        "signer_token": signer_tokens[signer_index]
                    })

        return {"rubricas": rubricas}


    def subir_documento_a_zapsign(self, contrato_data):
        # Armar payload para subir documento
        payload = self.build_payload_to_zapsign(contrato_data)

        headers = {
            'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}',
            'Content-Type': 'application/json'
        }
        print("Solicitando documento a Zapsign")

        url = f'{API_URL_ZAPSIGN}docs/'

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()

            try:
                response_data = response.json()
            except ValueError:
                print("⚠️ La respuesta no está en formato JSON.")
                response_data = {"raw_response": response.text}

            # Extraer token del documento
            doc_token = response_data.get("token")

            # Extraer tokens de firmantes
            signer_tokens = [s.get("token") for s in response_data.get("signers", []) if s.get("token")]

            if not doc_token:
                raise ValueError("No se pudo obtener el token del documento desde la respuesta.")

            print("Token del documento generado:", doc_token)
            print("ID del contrato que se va a actualizar:", contrato_data["id"])

            # Guardar token en la base de datos
            info = self.queryset.filter(id=contrato_data["id"]).first()
            if not info:
                raise ValueError("Contrato no encontrado en la base de datos.")

            info.token = doc_token
            info.save()
            print("Token guardado exitosamente en la base de datos.")            

            # Comportamiento configurable: si contrato_data incluye "_omit_place"=True,
            # NO se colocan rúbricas aquí (se hará después con posiciones visuales).
            do_place = not contrato_data.get("_omit_place", False)
            if do_place:
                # Armar y enviar payload de rúbricas (layout por defecto actual)
                rubricas_payload = self.armar_payload_posiciones_firma(signer_tokens, contrato_data["total_paginas"], contrato_data["arrendatario"])
                posicionar_url = f'{API_URL_ZAPSIGN}docs/{doc_token}/place-signatures/'
                print("📤 Enviando posiciones de firmas (layout por defecto)...")

                posicionar_response = requests.post(
                    posicionar_url,
                    headers=headers,
                    json=rubricas_payload,
                    timeout=60
                )

                posicionar_response.raise_for_status()
                print("Posiciones de firmas configuradas correctamente.")

                return {
                    "payload": payload,
                    "doc_token": doc_token,
                    "zapsign_new_doc": response_data,
                    "rubricas_payload": rubricas_payload,
                    "rubricas_response": posicionar_response.text or "Sin contenido"
                }

            # Si omitimos place-signatures, devolvemos solo datos del documento creado
            return {
                "payload": payload,
                "doc_token": doc_token,
                "zapsign_new_doc": response_data,
            }

        except requests.exceptions.Timeout:
            print("Error: Tiempo de espera agotado al comunicar con ZapSign.")
        except requests.exceptions.RequestException as e:
            print(f"Error en la solicitud a Zap-Sign: {e}")
        except Exception as e:
            print(f"Error inesperado en subir documento zapsign: {e}")

        return None

    def armar_payload_posiciones_custom(self, positions, signer_tokens):
        """Construye payload de rúbricas desde posiciones personalizadas del frontend."""
        rubricas = []
        if not isinstance(positions, list):
            return {"rubricas": rubricas}
        for pos in positions:
            try:
                page = int(pos.get("page", 0))
                bottom = float(pos.get("bottom", 0))
                left = float(pos.get("left", 0))
                size_x = float(pos.get("size_x", 19.55))
                size_y = float(pos.get("size_y", 9.42))
                signer_index = int(pos.get("signer_index", 0))
                if signer_index < 0 or signer_index >= len(signer_tokens):
                    continue
                rubricas.append({
                    "page": page,
                    "relative_position_bottom": bottom,
                    "relative_position_left": left,
                    "relative_size_x": size_x,
                    "relative_size_y": size_y,
                    "type": "signature",
                    "signer_token": signer_tokens[signer_index]
                })
            except Exception:
                continue
        return {"rubricas": rubricas}

    def posicionar_y_generar_urls_gs(self, request, *args, **kwargs):
        """Crea/obtiene doc ZapSign y aplica posiciones.
        - Si NO hay PDF cargado: usa posicionamiento automático (como Fraterna)
        - Si SÍ hay PDF cargado: usa posicionamiento visual del frontend
        Acceso: username == 'GarzaSada' o staff."""
        try:
            user_session = request.user
            if not (user_session.is_staff or getattr(user_session, "username", "") == "GarzaSada"):
                return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

            data = request.data or {}
            contrato_id = data.get("contrato_id")
            arr_cto = data.get("arrendatario_contrato")
            positions = data.get("positions", [])
            doc_tipo = data.get("doc_tipo", "contrato")
            print(f"📥 Datos recibidos: contrato_id={contrato_id}, doc_tipo={doc_tipo}, positions={len(positions)}")
            
            if not contrato_id:
                return Response({"error": "contrato_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

            info = self.queryset.filter(id=contrato_id).first()
            if not info:
                return Response({"error": "Contrato no encontrado"}, status=status.HTTP_404_NOT_FOUND)
            
            print(f"✅ Contrato encontrado: ID={info.id}, Arrendatario={info.arrendatario.nombre_arrendatario if info.arrendatario else 'None'}")

            # Verificar si hay PDF cargado
            tiene_pdf_cargado = bool(info.contrato_pdf_b64)
            print(f"{'✅ PDF cargado detectado' if tiene_pdf_cargado else '⚠️ No hay PDF cargado - usará generación automática'}")

            doc_token = getattr(info, "token", None)
            if not doc_token:
                print("📄 Creando documento en ZapSign...")
                
                # Preparar PDF
                if tiene_pdf_cargado:
                    print("📄 Usando PDF cargado por el usuario")
                    pdf_bytes = base64.b64decode(info.contrato_pdf_b64)
                    total_paginas = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
                else:
                    print("🔨 Generando PDF automáticamente")
                    if not info.arrendatario:
                        return Response({"error": "El contrato no tiene arrendatario asociado"}, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Generar según tipo de documento
                    if doc_tipo == "paquete":
                        testigo1 = data.get("testigo1", "Angelina Castillo González")
                        testigo2 = data.get("testigo2", "Marcelo André Trujillo Moncada")
                        pagare_distinto = data.get("pagare_distinto", "No")
                        cantidad_pagare = data.get("cantidad_pagare", "")
                        
                        # Generar paquete completo
                        pdf_contrato = self._generar_contrato_garzasada_interno(info, testigo1=testigo1, testigo2=testigo2)
                        pdf_poliza = self._generar_poliza_garzasada_interno(info)
                        pdf_pagare = self._generar_pagare_garzasada_interno(info, pagare_distinto=pagare_distinto, cantidad_pagare=cantidad_pagare)
                        
                        # Fusionar PDFs
                        from PyPDF2 import PdfMerger
                        merger = PdfMerger()
                        merger.append(io.BytesIO(pdf_contrato))
                        merger.append(io.BytesIO(pdf_poliza))
                        merger.append(io.BytesIO(pdf_pagare))
                        
                        output = io.BytesIO()
                        merger.write(output)
                        merger.close()
                        pdf_bytes = output.getvalue()
                        
                        # Calcular páginas por sección
                        total_paginas = {
                            "arrendamiento": len(PdfReader(io.BytesIO(pdf_contrato)).pages),
                            "poliza": len(PdfReader(io.BytesIO(pdf_poliza)).pages),
                            "pagares": len(PdfReader(io.BytesIO(pdf_pagare)).pages),
                            "manual": 0,
                            "comodato": 0
                        }
                    else:
                        testigo1 = data.get("testigo1", "Angelina Castillo González")
                        testigo2 = data.get("testigo2", "Marcelo André Trujillo Moncada")
                        pdf_bytes = self._generar_contrato_garzasada_interno(info, testigo1=testigo1, testigo2=testigo2)
                        total_paginas = {
                            "arrendamiento": len(PdfReader(io.BytesIO(pdf_bytes)).pages),
                            "poliza": 0,
                            "pagares": 0,
                            "manual": 0,
                            "comodato": 0
                        }
                    
                    print(f"✅ PDF generado: {len(pdf_bytes)} bytes")

                nombre_archivo = f"Contrato Garza Sada - {info.arrendatario.nombre_arrendatario}"
                base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                
                if not arr_cto:
                    return Response({"error": "arrendatario_contrato es requerido"}, status=status.HTTP_400_BAD_REQUEST)
                
                # Configurar contrato_data según si hay PDF cargado o no
                contrato_data = {
                    "id": contrato_id,
                    "filename": nombre_archivo,
                    "base64_pdf": base64_pdf,
                    "arrendatario": arr_cto,
                    "total_paginas": total_paginas if not tiene_pdf_cargado else len(PdfReader(io.BytesIO(pdf_bytes)).pages),
                    "_omit_place": tiene_pdf_cargado,  # Si hay PDF cargado, omitir posicionamiento automático
                }
                
                creado = self.subir_documento_a_zapsign(contrato_data)
                if not creado or not creado.get("doc_token"):
                    return Response({"error": "No fue posible crear el documento en ZapSign"}, status=status.HTTP_502_BAD_GATEWAY)
                doc_token = creado["doc_token"]
                info.refresh_from_db()
                
                # Si NO hay PDF cargado, las posiciones ya se aplicaron automáticamente
                if not tiene_pdf_cargado:
                    print("✅ Posiciones automáticas ya aplicadas")
                    return Response({
                        "doc_token": doc_token,
                        "message": "Documento creado con posicionamiento automático",
                        "signers": creado.get("zapsign_new_doc", {}).get("signers", [])
                    }, status=status.HTTP_200_OK)

            # Si llegamos aquí, hay PDF cargado y necesitamos aplicar posiciones del frontend
            print("🎯 Aplicando posiciones del frontend...")
            
            # Obtener tokens de firmantes del doc en ZapSign
            url_doc = f"{API_URL_ZAPSIGN}docs/{doc_token}/"
            headers = {'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'}
            resp = requests.get(url_doc, headers=headers, timeout=30)
            if resp.status_code != 200:
                return Response({"error": "Error al consultar documento ZapSign", "status_code": resp.status_code, "response": resp.text}, status=resp.status_code)
            try:
                doc_json = resp.json()
            except ValueError:
                return Response({"error": "Respuesta de ZapSign no es JSON"}, status=status.HTTP_502_BAD_GATEWAY)
            
            # Extraer información de los firmantes
            signers = doc_json.get("signers", [])
            signer_tokens = [s.get("token") for s in signers if s.get("token")]
            
            # Obtener nombres y emails de los firmantes
            signers_info = []
            for signer in signers:
                signers_info.append({
                    "token": signer.get("token"),
                    "name": signer.get("name"),
                    "email": signer.get("email"),
                    "status": signer.get("status"),
                    "sign_url": signer.get("sign_url")
                })
            
            print(f"👥 Firmantes encontrados: {[s['name'] for s in signers_info]}")
            
            # Aplicar posiciones del frontend
            rubricas_payload = self.armar_payload_posiciones_custom(positions, signer_tokens)

            posicionar_url = f"{API_URL_ZAPSIGN}docs/{doc_token}/place-signatures/"
            pos_resp = requests.post(posicionar_url, headers=headers, json=rubricas_payload, timeout=60)
            if pos_resp.status_code not in (200, 201, 204):
                return Response({"error": "Error al colocar firmas", "status_code": pos_resp.status_code, "response": pos_resp.text}, status=pos_resp.status_code)

            return Response({
                "doc_token": doc_token,
                "signers": signers_info,
                "rubricas_payload": rubricas_payload,
                "zapsign_place_response": pos_resp.text or "Sin contenido"
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Error en posicionar_y_generar_urls_gs línea {exc_tb.tb_lineno}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def posicionar_sobre_existente_gs(self, request, *args, **kwargs):
        """Aplica posiciones sobre documento existente en ZapSign.
        Acceso: username == 'GarzaSada' o staff."""
        try:
            user_session = request.user
            if not (user_session.is_staff or getattr(user_session, "username", "") == "GarzaSada"):
                return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

            data = request.data or {}
            contrato_id = data.get("contrato_id")
            positions = data.get("positions", [])
            if not contrato_id:
                return Response({"error": "contrato_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)

            info = self.queryset.filter(id=contrato_id).first()
            if not info or not getattr(info, "token", None):
                return Response({"error": "Contrato o token no encontrado"}, status=status.HTTP_404_NOT_FOUND)

            doc_token = info.token
            url_doc = f"{API_URL_ZAPSIGN}docs/{doc_token}/"
            headers = {'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'}
            resp = requests.get(url_doc, headers=headers, timeout=30)
            if resp.status_code != 200:
                return Response({"error": "Error al consultar documento ZapSign", "status_code": resp.status_code, "response": resp.text}, status=resp.status_code)
            try:
                doc_json = resp.json()
            except ValueError:
                return Response({"error": "Respuesta de ZapSign no es JSON"}, status=status.HTTP_502_BAD_GATEWAY)
            signer_tokens = [s.get("token") for s in doc_json.get("signers", []) if s.get("token")]
            rubricas_payload = self.armar_payload_posiciones_custom(positions, signer_tokens)

            posicionar_url = f"{API_URL_ZAPSIGN}docs/{doc_token}/place-signatures/"
            pos_resp = requests.post(posicionar_url, headers=headers, json=rubricas_payload, timeout=60)
            if pos_resp.status_code not in (200, 201, 204):
                return Response({"error": "Error al colocar firmas", "status_code": pos_resp.status_code, "response": pos_resp.text}, status=pos_resp.status_code)

            return Response({
                "doc_token": doc_token,
                "rubricas_payload": rubricas_payload,
                "zapsign_place_response": pos_resp.text or "Sin contenido"
            }, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{dt.now()} Error en posicionar_sobre_existente_gs línea {exc_tb.tb_lineno}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#////////////////FIN INTEGRACION ZAPSIGN/////////////////////        
        
        
    def renovar_contrato_garzasada(self, request, *args, **kwargs):
        try:
            print("Renovacion de contrato Garza Sada")
            print("Data ====>",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("ID ====>",instance.id)
            print(instance.__dict__)
            #Mandar Whats con lo datos del contrato a Miri
            
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato_garzasada.objects.all().get(contrato_id = instance.id)
            print("Proceso ====>",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            print("Contrato renovado correctamente....✅")
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)


class InvestigacionGarzaSada(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Arrendatarios_garzasada.objects.all()
    serializer_class = Arrentarios_GarzaSadaSerializers
   
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        if user_session.username == "Arrendatario1" or user_session.username == "Legal" or  user_session.username == "Investigacion" or user_session.username == "AndresMtzO" or user_session.username == "MIRIAM" or user_session.username == "jon_admin" or user_session.username == "SUArrendify" or user_session.username == "Becarios":
            print("USUARIO STAFF")
            qs = request.GET.get('nombre')     
            try:
                if qs:
                    inquilino = Arrendatarios_garzasada.objects.all().order_by('-id')
                    serializer = Arrentarios_GarzaSadaSerializers(inquilino, many=True)                    
                    return Response(serializer.data)
                    
                else:
                        print("Listar Investigacion Garza Sada")
                        investigar = Arrendatarios_garzasada.objects.all().order_by('-id')
                        serializer = Arrentarios_GarzaSadaSerializers(investigar, many=True)
                        return Response(serializer.data)
                
                #    return Response(serializer.data, status= status.HTTP_200_OK)
            except Exception as e:
                print(f"el error es: {e}")
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
                return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'No estas autorizado'}, status=status.HTTP_401_UNAUTHORIZED)
    

    def update(self, request, *args, **kwargs):
        pass
        
    def retrieve(self, request, pk=None, *args, **kwargs):
        user_session = request.user
        try:
            print("Entrando a retrieve")
            modelos = Investigacion.objects.all() #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            print(pk)
            inv = modelos.filter(id=pk)
            if inv:
                serializer_investigacion = InvestigacionSerializers(inv, many=True)
                return Response(serializer_investigacion.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay investigacion en estos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)             
        
    # def enviar_archivo(self, archivo, info, estatus):
    #     #cuando francis este registrado regresar todo como estaba
    #     # francis = User.objects.all().filter(name_inmobiliaria = "Francis Calete").first()
    #     print("Enviar Investigacion Garza Sada ====>")
    #     print("PDF ====>",archivo)
    #     print("Estatus Investigacion ====>",estatus)
    #     print("DATA ====>",info.__dict__)
    #     print("ID USUARIO ====>",info.user_id)
   
    #     # Configura los detalles del correo electrónico
    #     try:
    #         remitente = 'notificaciones@arrendify.com'
    #         # if info.user_id == francis.id:
    #         #     print("Es el mismo usuaio, envialo a francis calete")
    #         #     # destinatario = 'el que meden @francis o algo asi'
    #         #     pdf_html = contenido_pdf_aprobado_francis(info,estatus)
    #         #     print("destinatario Francis", destinatario)
    #         # else:
    #         #destinatario = 'jsepulvedaarrendify@gmail.com'
    #         destinatario = info.email
    #         pdf_html = contenido_pdf_aprobado(info,estatus)
    #         print("Destinatario ====> ",destinatario)
            
    #         #hacemos una lista destinatarios para enviar el correo
    #         Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
    #         #Destino=['desarrolloarrendify@gmail.com']
    #         #Destino=['juridico.arrendify1@gmail.com']
    #         asunto = f"Resultado Investigación Prospecto {info.nombre_arrendatario}"
            
    #         # Crea un objeto MIMEMultipart para el correo electrónico
    #         msg = MIMEMultipart()
    #         msg['From'] = remitente
    #         msg['To'] = ','.join(Destino)
    #         msg['Subject'] = asunto
    #         print("paso objeto mime")
            
    #         #Evalua si tiene este atributo
    #         # if hasattr(info, 'fiador'):
    #         #     print("SOY info.fiador",info.fiador)
            
    #         # Adjuntar el contenido HTML al mensaje
    #         msg.attach(MIMEText(pdf_html, 'html'))
    #         print("Creacion de Mail ====>")
    #         # Adjunta el PDF al correo electrónico
    #         pdf_part = MIMEBase('application', 'octet-stream')
    #         pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
    #         encoders.encode_base64(pdf_part)
    #         pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
    #         msg.attach(pdf_part)
    #         print("Mail Creado ====>")
            
    #         # Establece la conexión SMTP y envía el correo electrónico
    #         smtp_server = 'mail.arrendify.com'
    #         smtp_port = 587
    #         smtp_username = config('mine_smtp_u')
    #         smtp_password = config('mine_smtp_pw')
    #         with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
    #             server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
    #             print("TLS ====>")
    #             server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
    #             print("LOGIN ====>")
    #             server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
    #             print("CORREO ENVIADO ====>")
    #         return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
    #     except SMTPException as e:
    #         print("Error al enviar el correo electrónico:", str(e))
    #         exc_type, exc_obj, exc_tb = sys.exc_info()
    #         logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
    #         return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
    def enviar_archivo_garza_sada(self, archivo, info, estatus):
        # Función específica para enviar archivos de investigación Garza Sada
        print("Enviar Archivo Investigacion Garza Sada ====>")
        print("PDF ====>",archivo)
        print("Estatus Investigacion ====>",estatus)
        print("INFO Investigacion ====>",info.__dict__)
        print("ID USUARIO ====>",info.user_id)
   
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones@arrendify.com'
            destinatario = info.correo_arrendatario
            # Usar la función genérica contenido_pdf_aprobado para Garza Sada
            pdf_html = contenido_pdf_aprobado_GS(info,estatus)
            print("Destinatario ====>",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['juridico.arrendify1@gmail.com',f'{destinatario}','inmobiliarias.arrendify@gmail.com','desarrolloarrendify@gmail.com']
            #Destino=['desarrolloarrendify@gmail.com']
            #Destino=['juridico.arrendify1@gmail.com']
            asunto = f"Resultado Investigación Prospecto {info.nombre_arrendatario}"
            
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = ','.join(Destino)
            msg['Subject'] = asunto
            print("paso objeto mime")
            
            #Evalua si tiene este atributo
            # if hasattr(info, 'fiador'):
            #     print("SOY info.fiador",info.fiador)
            
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("Creacion de Mail ====>")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("Mail Creado ====>")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("TLS ====>")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("LOGIN ====>")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("CORREO ENVIADO ====>")
            return Response({'message': 'Correo electrónico enviado correctamente.'}, status = 200)
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'message': 'Error al enviar el correo electrónico.'}, status = 409)
    
        
    def aprobar_prospecto_garza_sada(self, request, *args, **kwargs):
        try:
            print("Aprobar Prospecto Garza Sada")
            #Consulata para obtener el inquilino y establecemos fecha de hoy
            today = date.today().strftime('%d/%m/%Y')
            req_dat = request.data
            # Usar modelo de Arrendatarios_garzasada en lugar de Semillero
            info = Arrendatarios_garzasada.objects.filter(id = req_dat["id"]).first()
            print("DATA ====>",info.__dict__)   
                 
                 
            redes_negativo = req_dat.get("redes_negativo")
            print("DATA ====>",req_dat)
            print("ID DATA ====>", req_dat["id"])
            print("")
            print("Arrendatario ====>",info.nombre_arrendatario)       
            print("Diccionario ====>",info.__dict__)
            print("")                                                                 
            print("")
            print("Redes Negativas ====>", redes_negativo)            
            print("")
            
            requisitos = ['referencia1', 'referencia2', 'referencia3'] # una lista para verificar las referencias 1,2 y 3
            presentes = [req for req in requisitos if req in request.data and request.data[req]]
            print("Referencias presentes ====>",presentes)
            if len(presentes) == 3:
                referencias = "En consideración a lo referido por las referencias podemos constatar que la informacion brindada por el prospecto al inicio del tramite es verídica, lo cual nos permite estimar que cuenta con buenos comentarios hacia su persona."
            elif len(presentes) > 0:
                referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con alguna(s) referencias proporcionadas, por lo tanto, no podemos corroborar por completo la veracidad de la información proporcionada en la solicitud de arrendamiento. "
            else:
                referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con ninguna de las referencias proporcionadas, por lo tanto, no podemos corroborar la veracidad de la información proporcionada en la solicitud de arrendamiento. "
            
            #comentarios de redes para walden
            if redes_negativo:
                redes_negativo = dict(redes_negativo)
                #inicializamos la lista 
                redes_comentarios = []
                #establecemos las frases
                conductas = {
                'conducta_violenta': "Conducta violenta o agresiva: Publicaciones que muestran armas de fuego u otros objetos peligrosos.",
                'conducta_discriminatoria': "Conducta discriminatoria o racista: Comentarios, imágenes o memes que promueven el racismo, sexismo, homofobia, transfobia u otro tipo de discriminación.",
                'contenido_ofensivo_odio': "Contenido ofensivo o de odio: Publicaciones que contienen discursos de odio contra diversos grupos étnicos, religiosos, de orientación sexual, género, etc",
                'bullying_acoso': "Bullying o acoso: Participación en o incitación al acoso, ya sea ciberacoso o en la vida real.",
                'contenido_inapropiado': "Contenido inapropiado o explícito: Publicaciones de contenido sexual explícito o inapropiado.",
                'desinformacion_teoria': "Desinformación y teorías conspirativas: Difusión de información falsa o engañosa, así como la promoción de teorías conspirativas sin fundamento que puedan poner en peligro la tranquilidad y orden dentro de la comunidad.",
                'lenguaje_vulgar': "Lenguaje vulgar o inapropiado: Uso excesivo de lenguaje vulgar o soez en sus publicaciones.",
                'contenido_poco_profesional': "Conducta poco profesional: Publicaciones que muestran comportamientos inapropiados en contextos profesionales.",
                'falta_integridad': "Falta de integridad: Inconsistencias en la información compartida en diferentes plataformas, o indicios de comportamientos engañosos o fraudulentos.",
                'divulgacion_info': "Divulgación de información confidencial: Publicaciones que revelan información privada o confidencial de empresas, clientes o individuos.",
                'exceso_negatividad': "Exceso de negatividad: Publicaciones predominantemente negativas o quejumbrosas.",
                'falta_respeto_priv': "Falta de respeto hacia la privacidad: Compartir información privada de otras personas sin su consentimiento.",
                'ausencia_diversidad': "Ausencia de diversidad y tolerancia: Falta de representación de diversas perspectivas y falta de respeto por la diversidad en sus publicaciones."
                }
                # Bucle para generar las frases basadas en los valores de redes_negativo
                for clave, valor in redes_negativo.items(): #hacemos un for basado en la clave valor del dicciones redes_negativo en el .items al ser un diccionario
                    if valor == "Si" and clave in conductas:
                        frase = conductas[clave]
                        #lo agregamos a la lista redes_comentarios
                        redes_comentarios.append(frase)
                        print("Clave ====>", clave)
                        print("Frase ====>", frase)
                        print("Comentarios Redes ====>", redes_comentarios)
                    elif valor == "Si" and clave not in conductas:
                        print(f"No hay una frase definida para la clave: {clave}")
            else:
                redes_comentarios = "no tengo datos"
                print("Comentarios Redes ====>",redes_comentarios)
        
            #opciones para el score interno de nosotros
            opciones = {
                'Excelente': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_excelente.png",
                'Bueno': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_bueno.png",
                'Regular': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_regular.png",
                'Malo': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_malo.png"
            }
            
            tipo_score_ingreso = req_dat["tipo_score_ingreso"]
            tipo_score_pp = req_dat["tipo_score_pp"]
            tipo_score_credito = req_dat["tipo_score_credito"]
            
            if tipo_score_ingreso and tipo_score_pp and tipo_score_credito in opciones:
                tsi = opciones[tipo_score_ingreso]
                tspp = opciones[tipo_score_pp]
                tsc = opciones[tipo_score_credito]
                print(f"Tu Tipo de score ingresos es: {tipo_score_ingreso}, URL: {tsi}")
                print(f"Tu Tipo de score de pagos puntuales es: {tipo_score_pp}, URL: {tspp}")
                print(f"Tu Tipo de score de credito es: {tipo_score_credito}, URL: {tsc}")
            
               
            #Dar conclusion dinamica
            antecedentes = request.data.get('antecedentes') # Obtenemos todos los antecedentes del prospecto
            print("ANTECEDENTES ====>",antecedentes)
            if antecedentes:
                # del antecedentes["civil_mercantil_demandado"] 
                print("CIVIL O FAMILIAR ====>",antecedentes)
                if antecedentes.get("civil_mercantil_demandado") and len(antecedentes) == 1: #tiene antecedentes de civil o de familiar? los excentamos si no delincuente
                    print("Historial Crediticio ====>")
                    #evaluar el historial crediticio  
                    
                    if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                        print("Rechazado ====>")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                    
                    elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                        print("Aprobado ====>")
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                        status = "Aprobado"
                        motivo = "No hay motivo de rechazo"
                    
                    elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                        print("A Considerar ====>")
                        conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                        status = "Aprobado_pe"
                        motivo = "1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                        
                elif antecedentes.get("antecedentes_aval_si") and len(antecedentes) == 1: #tiene antecedentes de aval
                        print("AVAL CON ANTECEDENTES")
                        print("Solicitar cambio Aval")
                        
                        if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                            print("Rechazado ====>")
                            conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                            status = "Declinado"
                            motivo = f"1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                            print("Aprobado ====>")
                            conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                            status = "Aprobado"
                            motivo =  f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                        
                        elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                            print("A Considerar ====>")
                            conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                            status = "Aprobado_pe"
                            motivo = f"1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse.\n3.-Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{aval}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos."
                    
                elif antecedentes and tipo_score_pp == "Malo" or antecedentes and tipo_score_ingreso == "Malo":
                        print("Rechazado ====>")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."    
                        
                else:
                    print("Antecedentes")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."
            else: #No tiene Antecedentes
                
                #evaluar el historial crediticio  
                if tipo_score_pp == "Malo":
                    print("Rechazado ====>")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Buro: Se cuenta con un buro con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                
                elif tipo_score_ingreso == "Malo":
                    print("Rechazado ====>")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Ingresos: Los ingresos comprobados no son suficientes para garantizar el cumplimiento de sus obligaciones financieras."
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                    print("Aprobado ====>")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = ""   
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente" and antecedentes.get("antecedentes_aval_si") and antecedentes != None :
                    print("Aprobado ====>")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_arrendatario} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = f"Derivado a lo anterior, a fin de concretar la relación contractual que se busca generar, es necesario buscar a una nueva figura de AVAL ya que el C.{info.nombre_obligado or info.obligado_nombre_empresa}, presenta diversos procedimientos en materia mercantil en su contra, lo cual nos imposibilita celebrar el contrato de arrendamiento ante tales supuestos." 
                
                elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                    print("A Considerar ====>")
                    conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                    status = "Aprobado_pe"
                    motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                
                 
                    
            context = {'info': info, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                       "redes_comentarios":redes_comentarios, 'referencias':referencias, 'antecedentes':antecedentes,'status':status, 'conclusion':conclusion, 'motivo':motivo}
            
            template = 'home/report_garzasada.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            print("Generando PDF")
            pdf_file = HTML(string=html_string).write_pdf()

            # #aqui hacia abajo es para enviar por email
            # archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
        
            # print("DATOS ARCHIVO ====>",context)
            # correo = self.enviar_archivo_garza_sada(archivo, context["info"], context["status"])
            # print("CORREO ====>",correo)
            # if correo.status_code == 200:
            #      # Aprobar o desaprobar
            #     if status == "Aprobado_pe" or status == "Aprobado":  
            #          info.status = "Aprobado"
            #          info.save()
            #     else:
            #          info.status = "Rechazado"
            #          info.save()
                
            #     print("Correo ENVIADO")
            
            # else:
            #     print("Correo NO ENVIADO")
            #     Response({"Error":"no se envio el correo"},status = 409)
            
            # return Response({'mensaje': "Todo salio bien, pdf enviado"}, status = 200)
           
            #de aqui hacia abajo Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'inline; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Finalizamos el proceso de aprobado")
            return response

        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status = "404")


class DepartamentosFraterna(viewsets.ViewSet):
    """Vista agregada de departamentos Fraterna, jerarquía Departamento → Camas → Contratos.

    list: cada depto con contadores de camas (ocupadas/reservadas/disponibles)
          y estado derivado (ocupado/parcial/reservado/disponible).
    retrieve: lista de camas del depto con su estado y contrato vigente.
    historial_cama: historial de contratos de una cama específica del depto.

    Regla de ocupación: status_proceso='Aprobado' con `fecha_celebracion ≤ hoy ≤ fecha_vigencia`.
    `fecha_move_in/move_out` se conservan informativos y no afectan el estado.
    Camas se comparan por `UPPER(TRIM(cama))` para tolerar inconsistencias de captura.
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    lookup_value_regex = '[^/]+'

    @staticmethod
    def _residente_nombre(residente):
        if not residente:
            return None
        return (
            getattr(residente, 'nombre_arrendatario', None)
            or getattr(residente, 'nombre_empresa_pm', None)
            or getattr(residente, 'nombre_residente', None)
            or None
        )

    @staticmethod
    def _residente_detalle(residente):
        if not residente:
            return {
                'arrendatario_nombre': None,
                'arrendatario_sexo': None,
                'residente_extra_nombre': None,
                'residente_extra_sexo': None,
            }
        return {
            'arrendatario_nombre': getattr(residente, 'nombre_arrendatario', None) or None,
            'arrendatario_sexo': getattr(residente, 'sexo_arrendatario', None) or None,
            'residente_extra_nombre': getattr(residente, 'nombre_residente', None) or None,
            'residente_extra_sexo': getattr(residente, 'sexo', None) or None,
        }

    @staticmethod
    def _normalize_cama(raw):
        if raw is None:
            return None
        s = str(raw).strip()
        return s.upper() if s else None

    @staticmethod
    def _status_por_contrato(contrato_ids):
        """Devuelve {contrato_id: status_str} con el último ProcesoContrato por contrato."""
        if not contrato_ids:
            return {}
        procesos = (
            ProcesoContrato.objects
            .filter(contrato_id__in=contrato_ids)
            .order_by('contrato_id', '-fecha', '-id')
            .values('contrato_id', 'status_proceso')
        )
        out = {}
        for p in procesos:
            cid = p['contrato_id']
            if cid not in out:
                out[cid] = (p['status_proceso'] or '').strip()
        return out

    @staticmethod
    def _estado_por_status(status_str):
        s_lower = (status_str or '').lower()
        if s_lower == 'aprobado':
            return 'ocupado'
        # 'en revisión' / 'en revision' / vacío / cualquier otro → reservado mientras esté en ventana
        return 'reservado'

    @staticmethod
    def _estado_depa(camas_info):
        """Dado un dict {cama: {estado}}, devuelve el estado agregado del depa."""
        if not camas_info:
            return 'disponible'
        estados = {info['estado'] for info in camas_info.values()}
        if estados == {'ocupado'}:
            return 'ocupado'
        if estados == {'disponible'}:
            return 'disponible'
        if estados == {'reservado'}:
            return 'reservado'
        if 'ocupado' in estados or 'reservado' in estados:
            if 'disponible' in estados:
                return 'parcial'
            # mezcla ocupado + reservado, sin disponibles → parcial también
            return 'parcial'
        return 'disponible'

    def _build_camas_de_depa(self, no_depa=None):
        """Construye la estructura de camas, agrupada por (no_depa, cama_norm).

        Para cada cama elige el contrato 'representativo' actual: primero un Aprobado vigente
        en `[fecha_celebracion, fecha_vigencia]`; si no, un En Revisión en ventana; si no, None.
        """
        today = date.today()
        qs = (
            FraternaContratos.objects
            .exclude(no_depa__isnull=True)
            .exclude(no_depa__exact='')
            .select_related('residente')
            .order_by('no_depa', '-fecha_celebracion', '-id')
        )
        if no_depa is not None:
            qs = qs.filter(no_depa=no_depa)

        contratos = list(qs)
        status_map = self._status_por_contrato([c.id for c in contratos])

        # camas[no_depa][cama_norm] = {'cama','estado','contrato','status'}
        camas = {}
        rank = {'ocupado': 2, 'reservado': 1, 'disponible': 0}

        for c in contratos:
            cama_norm = self._normalize_cama(c.cama)
            if cama_norm is None:
                continue

            depa_bucket = camas.setdefault(c.no_depa, {})
            existing = depa_bucket.get(cama_norm)

            in_window = (
                c.fecha_celebracion is not None
                and c.fecha_vigencia is not None
                and c.fecha_celebracion <= today <= c.fecha_vigencia
            )

            if in_window:
                status_str = status_map.get(c.id, '')
                nuevo_estado = self._estado_por_status(status_str)
                candidato = {
                    'cama': cama_norm,
                    'estado': nuevo_estado,
                    'contrato': c,
                    'status': status_str,
                }
            else:
                # Este contrato no vigente; solo sirve para asegurar existencia de la cama.
                candidato = {
                    'cama': cama_norm,
                    'estado': 'disponible',
                    'contrato': None,
                    'status': '',
                }

            if existing is None or rank[candidato['estado']] > rank[existing['estado']]:
                depa_bucket[cama_norm] = candidato

        return camas

    def list(self, request, *args, **kwargs):
        try:
            # Lee del INVENTARIO físico (FraternaDepartamento/FraternaCama), no de contratos.
            # 'reservados' y 'proxima_vigencia' provienen de contratos → fase posterior (0/None).
            result = []
            for d in FraternaDepartamento.objects.prefetch_related('camas').all():
                camas = list(d.camas.all())
                ocup = sum(1 for c in camas if c.status == 'ocupada')
                disp = sum(1 for c in camas if c.status == 'disponible')
                # Géneros presentes en las camas del depa (para el filtro por género del FE).
                generos = sorted({(c.genero or '').strip() for c in camas if (c.genero or '').strip()})
                result.append({
                    'no_depa': d.no_depa,
                    'estado': d.status,                 # ocupado / parcial / disponible
                    'nivel': d.nivel,
                    'tipologia': d.tipologia,
                    'es_residencial': d.es_residencial,
                    'camas_total': len(camas),
                    'camas_ocupadas': ocup,
                    'camas_reservadas': 0,              # contratos → fase posterior
                    'camas_disponibles': disp,
                    'generos': generos,
                    'proxima_vigencia': None,           # contratos → fase posterior
                    'actualizado': d.actualizado,
                })

            orden_estado = {'ocupado': 0, 'parcial': 1, 'reservado': 2, 'disponible': 3}
            result.sort(key=lambda x: (orden_estado.get(x['estado'], 9), x['no_depa']))

            resumen = {
                'total': len(result),
                'ocupados': sum(1 for r in result if r['estado'] == 'ocupado'),
                'parciales': sum(1 for r in result if r['estado'] == 'parcial'),
                'reservados': 0,
                'disponibles': sum(1 for r in result if r['estado'] == 'disponible'),
            }

            return Response({'resumen': resumen, 'departamentos': result}, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"error en DepartamentosFraterna.list: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk=None, *args, **kwargs):
        try:
            no_depa = pk
            # Lee las camas del INVENTARIO. Datos de contrato (arrendatario/sexo/vigencia/renta)
            # → fase posterior (null por ahora); se muestra el residente reportado en el Excel.
            depto = (FraternaDepartamento.objects
                     .filter(no_depa=no_depa)
                     .prefetch_related('camas')
                     .first())
            camas = sorted(depto.camas.all(), key=lambda c: c.cama) if depto else []

            # Contrato 'actual' por cama (a lo más 1 por el UniqueConstraint) -> lo usa el
            # botón "Liberar cama" del FE para un confirm contextual; al liberar, el backend
            # expira ese contrato.
            contratos_activos = {}
            if camas:
                for k in (FraternaContratos.objects
                          .filter(cama_ref_id__in=[c.id for c in camas], estado_contrato='actual')
                          .values('id', 'cama_ref_id', 'fecha_vigencia')):
                    contratos_activos[k['cama_ref_id']] = k

            camas_data = []
            contadores = {'ocupado': 0, 'reservado': 0, 'disponible': 0}
            for c in camas:
                estado = 'ocupado' if c.status == 'ocupada' else 'disponible'
                contadores[estado] += 1
                _act = contratos_activos.get(c.id)
                camas_data.append({
                    'id': c.id,
                    'cama': c.cama,
                    'nomenclatura': c.nomenclatura,
                    'estado': estado,
                    'residente_nombre': c.residente,
                    'residente_extra_nombre': c.residente,
                    'arrendatario_nombre': c.arrendatario,
                    'genero': c.genero,
                    'fecha_ocupacion_inicio': c.fecha_ocupacion_inicio,
                    'fecha_ocupacion_termino': c.fecha_ocupacion_termino,
                    'actualizado': c.actualizado,
                    'contrato_activo_id': _act['id'] if _act else None,
                    'contrato_activo_vigencia': _act['fecha_vigencia'] if _act else None,
                    # Detalle de contrato (sexo/fechas/renta) — fase posterior (null por ahora)
                    'status_proceso': None,
                    'residente_id': None,
                    'arrendatario_sexo': None,
                    'residente_extra_sexo': None,
                    'fecha_celebracion': None,
                    'fecha_vigencia': None,
                    'fecha_move_in': None,
                    'fecha_move_out': None,
                    'renta': None,
                    'contrato_id_vigente': None,
                })

            resumen = {
                'camas_total': len(camas),
                'camas_ocupadas': contadores['ocupado'],
                'camas_reservadas': contadores['reservado'],
                'camas_disponibles': contadores['disponible'],
                'estado_depa': depto.status if depto else 'disponible',
            }

            return Response({'no_depa': no_depa, 'resumen': resumen, 'camas': camas_data}, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"error en DepartamentosFraterna.retrieve: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path=r'camas/(?P<cama>[^/]+)')
    def historial_cama(self, request, pk=None, cama=None, *args, **kwargs):
        """Historial de contratos vinculados a una cama del inventario (vía cama_ref)."""
        try:
            no_depa = pk
            cama_in = (cama or '').strip().upper()
            depto = (FraternaDepartamento.objects
                     .filter(no_depa=no_depa)
                     .prefetch_related('camas')
                     .first())
            cama_obj = None
            if depto:
                cama_obj = next((c for c in depto.camas.all()
                                 if (c.cama or '').strip().upper() == cama_in), None)
            if not cama_obj:
                return Response({'no_depa': no_depa, 'cama': cama, 'contratos': []}, status=status.HTTP_200_OK)

            contratos = list(cama_obj.contratos.select_related('residente').order_by('-fecha_celebracion', '-id'))
            status_map = self._status_por_contrato([c.id for c in contratos])

            data = []
            for c in contratos:
                data.append({
                    'id': c.id,
                    'residente_nombre': self._residente_nombre(c.residente),
                    'residente_id': c.residente_id,
                    'fecha_celebracion': c.fecha_celebracion,
                    'fecha_vigencia': c.fecha_vigencia,
                    'fecha_move_in': c.fecha_move_in,
                    'fecha_move_out': c.fecha_move_out,
                    'duracion': c.duracion,
                    'renta': c.renta,
                    'cama_original': c.cama,
                    'status_proceso': status_map.get(c.id, '') or None,
                })

            return Response({'no_depa': no_depa, 'cama': cama_obj.cama,
                             'nomenclatura': cama_obj.nomenclatura, 'contratos': data},
                            status=status.HTTP_200_OK)

        except Exception as e:
            print(f"error en DepartamentosFraterna.historial_cama: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='liberar_cama')
    def liberar_cama(self, request):
        """Libera manualmente una cama del inventario (botón de UI).

        Pone la cama en 'disponible' y borra al ocupante (vía FraternaCama.liberar()).
        Si la cama tiene un contrato 'actual' (a lo más 1 por el UniqueConstraint), lo
        expira en la MISMA transacción para no dejar cama libre + contrato activo (estado
        inconsistente). NO toca fecha_move_out ni otra data del contrato. El status del
        depa se recalcula solo por el signal post_save de la cama.
        """
        try:
            cama_id = request.data.get('cama_id')
            if not cama_id:
                return Response({'error': 'Falta cama_id'}, status=status.HTTP_400_BAD_REQUEST)
            cama = (FraternaCama.objects
                    .select_related('departamento')
                    .filter(pk=cama_id)
                    .first())
            if cama is None:
                return Response({'error': 'Cama no encontrada'}, status=status.HTTP_404_NOT_FOUND)

            with transaction.atomic():
                expirados = (FraternaContratos.objects
                             .filter(cama_ref=cama, estado_contrato='actual')
                             .update(estado_contrato='expirado'))
                cama.liberar()   # -> signal post_save -> recalcula el status del depa

            cama.refresh_from_db()
            depa = cama.departamento
            depa.refresh_from_db()
            return Response({
                'ok': True,
                'cama_id': cama.id,
                'nomenclatura': cama.nomenclatura,
                'cama_status': cama.status,
                'contratos_expirados': expirados,
                'depa_no': depa.no_depa,
                'depa_status': depa.status,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"error en DepartamentosFraterna.liberar_cama: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en liberar_cama línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# --------------------------------------------------------------------------- #
# Bandeja de revision de recibos (lado Fraterna)                               #
# --------------------------------------------------------------------------- #
#
# El portal del residente ya deja subir el comprobante (2026-08-18); lo que
# faltaba era la otra mitad del ciclo: que Fraterna lo REVISE, capture el monto
# y lo apruebe. Aprobar existia desde antes, pero enterrado dentro de la ficha
# de cada residente (fraterna/detalles_documentos/<id>), o sea que habia que
# saber de antemano a quien buscar. Esto lo pone del derecho: una sola cola con
# lo que falta por dictaminar, lo mas viejo arriba.


def _puede_revisar_recibos(user):
    """Quien entra a la bandeja.

    Es el MISMO conjunto al que el sidebar le enciende la seccion Fraterna
    (`sidebar.js`: username "Fraterna", pertenece_a "Fraterna" o is_staff), mas
    los dos equipos internos por `rol_interno`.

    No se aprieta a `rol_interno` a secas aunque sea dinero: hay 17 cuentas
    activas que operan Fraterna todos los dias (leasingteam, utower2,
    FernandaSantiago, RentasU...) sin ese campo, y quedarian fuera. Tampoco se
    afloja a `IsAuthenticated`, que es lo unico que protege hoy al CRUD de
    recibos: la bandeja junta los pagos de TODOS los residentes en una pantalla
    y eso no tiene por que verlo cualquier cuenta con token.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    # El middleware del portal ya corta al residente antes de llegar aqui; esto
    # es el cinturon por si algun dia se mueve el orden de los middlewares.
    if getattr(user, 'rol', None) == 'Residente':
        return False
    return bool(
        getattr(user, 'is_staff', False)
        or getattr(user, 'pertenece_a', None) == 'Fraterna'
        or getattr(user, 'username', None) == 'Fraterna'
        or puede_ver_credenciales_residente(user)
    )


def _hora_local(valor):
    """ISO de un datetime en la zona del proyecto, no en UTC.

    Con USE_TZ=True la BD devuelve UTC y el front corta el ISO a pelo: sin esto,
    un recibo subido a las 9 de la manana se lee con la hora de Londres. Mismo
    gotcha que en el portal (_fecha_hora de portal_residente_views).
    """
    return timezone.localtime(valor).isoformat() if valor else ''


def _partes_de_la_ronda(ronda_id, ficha, firmantes):
    """Nombre y correo de arrendatario y residente, como quedaron CONGELADOS.

    Salen de `fraterna_ronda_firmante`, no de `datos_snapshot`: el snapshot solo
    guarda inmueble y dinero (y su unica clave de nombre, `residente_nombre`,
    contiene en realidad al ARRENDATARIO). Los firmantes en cambio son las
    personas tal como se mandaron a firmar. Medido en proddev: las 319 rondas
    firmadas tienen firmante arrendatario con nombre y correo, y 312 tienen
    residente — los 7 que faltan son fichas donde arrendatario y residente son
    la misma persona, y ahi entra el respaldo de la ficha.

    El CELULAR no viaja nunca por aqui: `fraterna_ronda_firmante` no tiene esa
    columna, asi que ese sale de la ficha por fuerza.
    """
    del_rol = firmantes.get(ronda_id) or {}
    if ronda_id and ronda_id not in firmantes:
        del_rol = {}
        for f in (FraternaRondaFirmante.objects
                  .filter(ronda_id=ronda_id, rol__in=('arrendatario', 'residente'))
                  .order_by('paquete', 'id')):
            del_rol.setdefault(f.rol, f)
        firmantes[ronda_id] = del_rol

    def parte(rol, nombre_ficha, correo_ficha, celular_ficha):
        f = del_rol.get(rol)
        return {
            'nombre': ((f.nombre if f else '') or nombre_ficha or '').strip(),
            'correo': ((f.email if f else '') or correo_ficha or '').strip(),
            # Unico dato que la ronda no congela: no existe la columna.
            'celular': str(celular_ficha or '').strip(),
            'fuente': 'ronda' if f else 'ficha',
        }

    return {
        'arrendatario': parte('arrendatario',
                              getattr(ficha, 'nombre_arrendatario', ''),
                              getattr(ficha, 'correo_arrendatario', ''),
                              getattr(ficha, 'celular_arrendatario', '')),
        'residente': parte('residente',
                           getattr(ficha, 'nombre_residente', ''),
                           getattr(ficha, 'correo_residente', ''),
                           getattr(ficha, 'celular_residente', '')),
    }


def _quien_subio_recibo(r):
    """(clave, nombre) de quien subio el comprobante, en terminos de la ficha.

    Desde el portal, `user` ya no es siempre un operador: puede ser la cuenta
    del arrendatario o la del residente (las dos FK que se agregaron a
    `residentes` el 2026-08-13). Al revisor le importa distinguirlos.
    """
    if not r.user_id:
        return 'administracion', 'La administración'
    ficha = r.residente
    if ficha:
        if r.user_id == ficha.arrendatario_cuenta_id:
            return 'arrendatario', (ficha.nombre_arrendatario or '').strip() or 'El arrendatario'
        if r.user_id == ficha.residente_cuenta_id:
            return 'residente', (ficha.nombre_residente or '').strip() or 'El residente'
    return 'operador', getattr(r.user, 'username', '') or 'La administración'


class RecibosPolizaResidenteViewSet(viewsets.ModelViewSet):
    """CRUD de recibos de pago de póliza por residente Fraterna.

    Soporta multi-archivo: cada fila = un recibo. Filtra por `?residente=<id>` y/o `?contrato=<id>`.
    DELETE limpia el archivo asociado en S3.
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = RecibosPolizaResidente.objects.all().order_by('-fecha_pago', '-fecha_subida')
    serializer_class = RecibosPolizaResidenteSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        residente_id = self.request.query_params.get('residente')
        contrato_id = self.request.query_params.get('contrato')
        if residente_id:
            qs = qs.filter(residente_id=residente_id)
        if contrato_id:
            qs = qs.filter(contrato_id=contrato_id)
        return qs

    def perform_create(self, serializer):
        # Auditoría: registra quién subió el recibo.
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            # Borra el archivo de S3 solo si es de la generacion por id (carpeta del
            # residente + nombre unico por fila = nadie mas referencia esa key). Los
            # paths viejos por nombre podian estar compartidos: esos no se tocan.
            prefijo_propio = f'Fraterna/residente/{instance.residente_id}/Recibos_poliza/'
            if instance.archivo and str(instance.archivo).startswith(prefijo_propio):
                eliminar_archivo_s3(instance.archivo)
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            print(f"error en RecibosPolizaResidenteViewSet.destroy: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='contratos_de_residente')
    def contratos_de_residente(self, request):
        """Devuelve solo `id, no_depa, fechas` de los contratos Fraterna del residente.

        Evita pedir el LIST completo de /contratos_fraterna/ (739 filas con anidados pesados)
        cuando solo se necesita poblar el dropdown del modal de recibos.
        """
        residente_id = request.query_params.get('residente')
        if not residente_id:
            return Response([], status=status.HTTP_200_OK)
        contratos = (
            FraternaContratos.objects
            .filter(residente_id=residente_id)
            .order_by('-fecha_celebracion', '-id')
            .values('id', 'no_depa', 'fecha_move_in', 'fecha_move_out')
        )
        return Response(list(contratos), status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        """Marca el recibo como aprobado. Registra quién y cuándo (auditoría)."""
        try:
            recibo = self.get_object()
            recibo.aprobado = True
            recibo.aprobado_por = request.user
            recibo.fecha_aprobacion = timezone.now()
            recibo.save(update_fields=['aprobado', 'aprobado_por', 'fecha_aprobacion'])
            ser = self.get_serializer(recibo)
            return Response(ser.data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"error en aprobar recibo: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def desaprobar(self, request, pk=None):
        """Revierte la aprobación del recibo, limpia metadatos de auditoría."""
        try:
            recibo = self.get_object()
            recibo.aprobado = False
            recibo.aprobado_por = None
            recibo.fecha_aprobacion = None
            recibo.save(update_fields=['aprobado', 'aprobado_por', 'fecha_aprobacion'])
            ser = self.get_serializer(recibo)
            return Response(ser.data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"error en desaprobar recibo: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------- #
    # Bandeja de revision                                                  #
    # ------------------------------------------------------------------- #

    def _fila_bandeja(self, r, calendarios, del_contrato, firmantes=None):
        """Un recibo con TODO lo que el revisor necesita para dictaminarlo."""
        contrato = r.contrato
        cuenta = None
        if contrato is not None:
            if contrato.id not in calendarios:
                # El estado de cuenta se calcula con TODOS los recibos del
                # contrato, no solo con este: el dinero se aplica en cascada y
                # un abono viejo cambia a que mes le toca al de hoy.
                calendarios[contrato.id] = estado_de_cuenta(
                    contrato, del_contrato.get(contrato.id, []))
            cuenta = calendarios[contrato.id]

        bloques = (cuenta or {}).get('periodos') or []
        # El tramo (periodo contractual firmado) del que cuelga este pago: el de
        # su ronda si la tiene, si no el que contiene el mes que se esta
        # cubriendo, y como ultimo recurso el mas reciente.
        tramo = None
        if bloques:
            if r.ronda_id:
                tramo = next((b for b in bloques if b['ronda_id'] == r.ronda_id), None)
            if tramo is None and (cuenta or {}).get('ronda_en_curso'):
                tramo = next((b for b in bloques
                              if b['ronda_id'] == cuenta['ronda_en_curso']), None)
            if tramo is None:
                tramo = bloques[-1]

        # EL MES QUE ANDA CUBRIENDO y lo que le falta. Ya no sale de una columna
        # del recibo (se dejo de guardar el 2026-08-18): se calcula al vuelo,
        # asi que un abono parcial sigue apuntando al mismo mes hasta saldarlo.
        en_curso = None
        vencidos = []
        if cuenta and cuenta.get('hay_calendario'):
            for m in cuenta['meses']:
                if en_curso is None and m['estado'] != 'pagado':
                    en_curso = m
                if m['vencido'] and m['estado'] != 'pagado':
                    vencidos.append({
                        'periodo_texto': m['periodo_texto'],
                        'monto': m['monto'],
                        'pagado': m['pagado'],
                        'falta': m['falta'],
                        'vence': m['vence'],
                    })

        # Lo que se espera que cubra este comprobante: lo que le falta al mes en
        # curso, no la renta completa (si ya hubo un abono, falta menos).
        esperado = en_curso['falta'] if en_curso else None

        depa = ((tramo['no_depa'] if tramo else '')
                or (getattr(contrato, 'no_depa', '') or ''))
        cama = ((tramo['cama'] if tramo else '')
                or (getattr(contrato, 'cama', '') or ''))

        # Quienes son las partes: de los FIRMANTES de la ronda a la que pertenece
        # el tramo (lo que se firmo), con respaldo en la ficha. Ver
        # `_partes_de_la_ronda`.
        ficha = r.residente
        partes = _partes_de_la_ronda(
            (tramo['ronda_id'] if tramo else None) or r.ronda_id,
            ficha, firmantes if firmantes is not None else {})
        subido_por, subido_por_nombre = _quien_subio_recibo(r)
        nombre_archivo = str(r.archivo).rsplit('/', 1)[-1] if r.archivo else ''
        ext = nombre_archivo.rsplit('.', 1)[-1].lower() if '.' in nombre_archivo else ''
        try:
            url = r.archivo.url if r.archivo else ''
        except Exception:
            url = ''

        return {
            'id': r.id,
            'residente_id': r.residente_id,
            'nombre_arrendatario': (getattr(ficha, 'nombre_arrendatario', '') or '').strip(),
            'nombre_residente': (getattr(ficha, 'nombre_residente', '') or '').strip(),
            'contrato_id': r.contrato_id,
            'depa': depa,
            'cama': cama,
            'ronda_id': r.ronda_id,
            'tramo_periodo': (tramo['periodo_texto'] if tramo else ''),
            'tramo_tipo': (tramo['tipo'] or '') if tramo else '',
            'vigencia_desde': (tramo['vigencia_desde'] if tramo else ''),
            'vigencia_hasta': (tramo['vigencia_hasta'] if tramo else ''),
            'partes': partes,
            'archivo_url': url,
            'nombre_archivo': nombre_archivo,
            'extension': ext,
            'es_imagen': ext in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic'),
            'monto': str(r.monto) if r.monto is not None else '',
            # Lo que el residente declaro al subirlo: QUE pago y POR DONDE. El
            # revisor lo necesita para saber si el comprobante que tiene enfrente
            # es una mensualidad o una multa antes de teclear el monto.
            'concepto': r.concepto or '',
            'concepto_texto': r.get_concepto_display() if r.concepto else '',
            'metodo_pago': r.metodo_pago or '',
            'metodo_pago_texto': r.get_metodo_pago_display() if r.metodo_pago else '',
            # Lo que le falta al mes que se esta cubriendo. Es la sugerencia para
            # el campo del monto; el revisor la confirma o la corrige contra el
            # comprobante que tiene enfrente.
            'monto_esperado': esperado,
            # Estado de cuenta VIVO del contrato: de que mes va, cuanto debe y
            # que otros meses ya se le vencieron. Puramente informativo — nada
            # de esto se guarda en el recibo.
            'cuenta': {
                'hay_calendario': bool(cuenta and cuenta.get('hay_calendario')),
                'motivo': (cuenta or {}).get('motivo') or '',
                'saldo': (cuenta or {}).get('saldo') or '0',
                'saldo_en_revision': (cuenta or {}).get('saldo_en_revision') or '0',
                'meses_vencidos': (cuenta or {}).get('meses_vencidos') or 0,
                'total': (cuenta or {}).get('total') or '0',
                'en_curso': en_curso,
                'vencidos': vencidos,
            },
            'referencia': r.referencia or '',
            'comentarios': r.comentarios or '',
            'fecha_subida': _hora_local(r.fecha_subida),
            'subido_por': subido_por,
            'subido_por_nombre': subido_por_nombre,
            'aprobado': r.aprobado,
            'fecha_aprobacion': _hora_local(r.fecha_aprobacion),
            'aprobado_por': getattr(r.aprobado_por, 'username', '') or '',
        }

    @action(detail=False, methods=['get'], url_path='bandeja')
    def bandeja(self, request):
        """GET /recibos_poliza_residente/bandeja/ -- la cola de revision.

        `?estado=pendientes|aprobados|todos` (por defecto pendientes) y `?q=`
        (nombre, depa, cama o referencia; insensible a acentos).

        Los PENDIENTES salen del mas viejo al mas nuevo a proposito: es una cola
        de trabajo y quien lleva mas tiempo esperando su dictamen va primero.
        Los aprobados, al reves -- lo ultimo dictaminado arriba, que es lo que se
        consulta cuando alguien reclama.
        """
        try:
            if not _puede_revisar_recibos(request.user):
                return Response({'error': 'No tienes permiso para revisar recibos de pago.'},
                                status=status.HTTP_403_FORBIDDEN)

            estado = (request.query_params.get('estado') or 'pendientes').lower()
            q = (request.query_params.get('q') or '').strip()

            qs = (RecibosPolizaResidente.objects
                  .select_related('residente', 'contrato', 'user', 'aprobado_por'))
            if q:
                # Insensible a acentos en los nombres (misma receta que la tabla
                # de contratos): unaccent() sobre la columna + termino sin
                # acentos. Depa, cama y referencia son ASCII, van tal cual.
                term = _sin_acentos(q)
                qs = qs.annotate(
                    _na_ua=Unaccent('residente__nombre_arrendatario'),
                    _nr_ua=Unaccent('residente__nombre_residente'),
                ).filter(
                    Q(_na_ua__icontains=term)
                    | Q(_nr_ua__icontains=term)
                    | Q(contrato__no_depa__icontains=q)
                    | Q(contrato__cama__icontains=q)
                    | Q(referencia__icontains=q)
                )

            # Los contadores se cuentan sobre el universo YA filtrado por la
            # busqueda: si no, las pestanas prometerian filas que el buscador de
            # arriba acaba de quitar.
            pendientes = qs.filter(aprobado=False).count()
            aprobados = qs.filter(aprobado=True).count()

            if estado == 'pendientes':
                filas = qs.filter(aprobado=False).order_by('fecha_subida', 'id')
            elif estado == 'aprobados':
                filas = qs.filter(aprobado=True).order_by('-fecha_aprobacion', '-id')
            else:
                filas = qs.order_by('aprobado', 'fecha_subida', 'id')

            total = (pendientes + aprobados if estado == 'todos'
                     else pendientes if estado == 'pendientes' else aprobados)
            filas = list(filas[:TOPE_BANDEJA_RECIBOS])

            # El estado de cuenta necesita TODOS los recibos del contrato, no
            # solo los de esta pagina: el dinero se aplica en cascada y un abono
            # que quedo fuera del filtro cambia de que mes va el de hoy.
            ids = {r.contrato_id for r in filas if r.contrato_id}
            del_contrato = {}
            if ids:
                for x in RecibosPolizaResidente.objects.filter(contrato_id__in=ids):
                    del_contrato.setdefault(x.contrato_id, []).append(x)

            # Firmantes de TODAS las rondas de esos contratos, en una sola
            # consulta: resolverlos recibo por recibo seria un N+1.
            firmantes = {}
            if ids:
                for f in (FraternaRondaFirmante.objects
                          .filter(ronda__contrato_id__in=ids,
                                  rol__in=('arrendatario', 'residente'))
                          .order_by('paquete', 'id')):
                    firmantes.setdefault(f.ronda_id, {}).setdefault(f.rol, f)

            # `tramos()` recorre las rondas de un contrato: se cachea por
            # contrato para no recalcular el mismo calendario en cada recibo.
            calendarios = {}
            datos = [self._fila_bandeja(r, calendarios, del_contrato, firmantes)
                     for r in filas]

            return Response({
                'recibos': datos,
                'pendientes': pendientes,
                'aprobados': aprobados,
                'total': total,
                # Se declara el corte en vez de truncar en silencio: una lista
                # cortada se lee como "ya no hay mas".
                'mostrados': len(datos),
                'truncado': total > len(datos),
                'tope': TOPE_BANDEJA_RECIBOS,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"error en bandeja de recibos: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en bandeja de recibos linea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='pendientes')
    def pendientes(self, request):
        """GET -- cuantos recibos esperan dictamen. Nada mas.

        Existe aparte de `bandeja/` porque lo pide el SIDEBAR en cada carga de
        pagina: `bandeja/` arma el calendario de cada contrato para poder decir
        el monto esperado, y eso no se puede pagar en cada navegacion. Aqui es
        un COUNT y ya.

        Devuelve 0 en vez de 403 a quien no puede revisar: es una insignia del
        menu, no un dato; que reviente el sidebar entero por esto seria peor.
        """
        try:
            if not _puede_revisar_recibos(request.user):
                return Response({'pendientes': 0}, status=status.HTTP_200_OK)
            n = RecibosPolizaResidente.objects.filter(aprobado=False).count()
            return Response({'pendientes': n}, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"error en pendientes de recibos: {e}")
            return Response({'pendientes': 0}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='revisar')
    def revisar(self, request, pk=None):
        """POST -- dictamina un recibo: captura lo que leyo el revisor y aprueba.

        Body: `{monto, periodo, fecha_pago, contrato, comentarios, aprobar}`.
        Todo opcional salvo `aprobar`, que decide si ademas se da por bueno.

        Va en UNA sola llamada a proposito: para quien revisa, capturar el monto
        y aprobar son el mismo acto, y partirlo en PATCH + POST deja un hueco
        donde el recibo queda aprobado con el monto viejo si la segunda falla.

        Aprobar EXIGE monto: sin cifra el mes queda en verde sin que nadie haya
        dicho cuanto se pago (el calendario presume que un comprobante aprobado
        sin monto cubre la mensualidad completa). El endpoint viejo `aprobar/` no
        cambia -- lo sigue usando el modal de la ficha del residente.
        """
        try:
            if not _puede_revisar_recibos(request.user):
                return Response({'error': 'No tienes permiso para revisar recibos de pago.'},
                                status=status.HTTP_403_FORBIDDEN)

            recibo = self.get_object()
            datos = request.data
            quiere_aprobar = str(datos.get('aprobar', '')).lower() in ('true', '1', 'si')
            campos = []

            # --- contrato: solo entre los de SU ficha ----------------------- #
            if 'contrato' in datos:
                crudo = datos.get('contrato')
                if crudo in (None, '', 'null'):
                    recibo.contrato = None
                    recibo.ronda = None
                    campos += ['contrato', 'ronda']
                else:
                    contrato = FraternaContratos.objects.filter(
                        id=crudo, residente_id=recibo.residente_id).first()
                    if not contrato:
                        return Response({'error': 'Ese contrato no es de este residente.'},
                                        status=status.HTTP_400_BAD_REQUEST)
                    recibo.contrato = contrato
                    campos.append('contrato')

            # --- monto ------------------------------------------------------ #
            if 'monto' in datos:
                crudo = str(datos.get('monto') or '').replace(',', '').replace('$', '').strip()
                if crudo == '':
                    recibo.monto = None
                else:
                    try:
                        monto = Decimal(crudo)
                    except (InvalidOperation, ValueError):
                        return Response({'error': 'El monto no es un numero valido.'},
                                        status=status.HTTP_400_BAD_REQUEST)
                    if monto < 0:
                        return Response({'error': 'El monto no puede ser negativo.'},
                                        status=status.HTTP_400_BAD_REQUEST)
                    recibo.monto = monto
                campos.append('monto')

            # EL MES YA NO SE GUARDA (2026-08-18): mandarlo se ignora. Se
            # intento y sale mal con los abonos — un pago de $1,000 contra una
            # renta de $16,000 daba el mes por cubierto y el siguiente
            # comprobante se iba al mes siguiente. Ahora el dinero se aplica en
            # cascada al calcular el estado de cuenta
            # (utils/calendario_pagos._repartir), asi que un abono parcial deja
            # su mes a medias y se sigue cobrando.

            # --- fecha de pago y comentarios -------------------------------- #
            if 'fecha_pago' in datos:
                crudo = str(datos.get('fecha_pago') or '').strip()
                if crudo == '':
                    recibo.fecha_pago = None
                else:
                    fecha = parse_date(crudo[:10])
                    if not fecha:
                        return Response({'error': 'La fecha de pago no tiene formato AAAA-MM-DD.'},
                                        status=status.HTTP_400_BAD_REQUEST)
                    recibo.fecha_pago = fecha
                campos.append('fecha_pago')

            if 'comentarios' in datos:
                recibo.comentarios = str(datos.get('comentarios') or '').strip() or None
                campos.append('comentarios')

            # --- aprobar ---------------------------------------------------- #
            if quiere_aprobar:
                if recibo.monto is None:
                    return Response(
                        {'error': 'Captura el monto del pago antes de aprobar el recibo.'},
                        status=status.HTTP_400_BAD_REQUEST)
                recibo.aprobado = True
                recibo.aprobado_por = request.user
                recibo.fecha_aprobacion = timezone.now()
                campos += ['aprobado', 'aprobado_por', 'fecha_aprobacion']

            if campos:
                # dedup conservando el orden: `ronda` puede entrar dos veces
                recibo.save(update_fields=list(dict.fromkeys(campos)))

            recibo = (RecibosPolizaResidente.objects
                      .select_related('residente', 'contrato', 'user', 'aprobado_por')
                      .get(pk=recibo.pk))
            todos = (list(RecibosPolizaResidente.objects.filter(contrato_id=recibo.contrato_id))
                     if recibo.contrato_id else [])
            return Response(self._fila_bandeja(recibo, {}, {recibo.contrato_id: todos}),
                            status=status.HTTP_200_OK)
        except Exception as e:
            print(f"error en revisar recibo: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Error en revisar recibo linea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

########################## G A R Z A  S A D A ######################################
