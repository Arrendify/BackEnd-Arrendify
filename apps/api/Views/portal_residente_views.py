# -*- coding: utf-8 -*-
"""Portal del residente Fraterna.

Lo que ve el humano que entra con la cuenta generada por
`utils/acceso_residente.py`: su ficha, sus documentos y sus contratos (con el
proceso de firma, su enlace y sus renovaciones). Casi todo es lectura; lo poco
escribible esta acotado a proposito: recibos de pago, incidencias y subir un
documento de su expediente. BORRAR no existe en ninguno de los tres.

REGLA DE ORO: el residente NUNCA manda un id. Todas las vistas resuelven el
universo visible desde `request.user` via las dos FK de la fase 1
(`residentes.arrendatario_cuenta` / `residentes.residente_cuenta`). Si el id no
viaja en el request, no hay IDOR que explotar: "dame el contrato 852" no es una
operacion que exista aqui. Los ids que SI se devuelven son de lectura, para que
el front pueda pintar y agrupar.

Un registro puede tener DOS cuentas (arrendatario y residente son personas
distintas en 727 de 846 casos) y una cuenta puede estar ligada a VARIOS
registros (misma persona con dos camas). Por eso todo devuelve una LISTA de
fichas y cada una declara `soy`: 'arrendatario', 'residente' o 'ambos'.

Que ve cada quien dentro de una ficha compartida:
  · Datos personales -> el bloque de TU rol completo; del otro, solo el nombre
    (saber con quien estas ligado sin heredarle CURP/RFC/telefono).
  · Documentos -> desde 2026-08-18 el expediente ENTERO lo comparten las dos
    cuentas de la ficha: lo ven completo (INE de la otra parte incluida) y
    cualquiera de las dos puede subir o reemplazar cualquier documento. No
    pueden borrar. OJO con la convencion real de prod: el campo `Ine` es la del
    ARRENDATARIO y `Ine_arr` la del RESIDENTE (el sufijo del campo miente).
  · Enlaces de firma -> solo el que te toca. El espejo `FraternaRondaFirmante`
    guarda `rol` por firmante, asi que se filtra por el rol que tienes EN ESA
    FICHA: el arrendatario no ve el enlace del residente ni al reves, y nadie ve
    el de Fraterna (arrendador) ni el del prestador.
"""
import io
import logging
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import validate_email
from django.db.models import EmailField, F, Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from pypdf import PdfReader, PdfWriter

from ...home.models import (
    DocumentosResidentes, FraternaContratos, FraternaRondaFirma,
    IncidenciasFraterna, RecibosPolizaResidente, Residentes,
)
from ..utils.calendario_pagos import (
    estado_de_cuenta, nombre_mes, renta_mensual, tramos,
)
from ..utils.demo_mode import marca_para
from .fraterna_views import eliminar_archivo_s3

logger = logging.getLogger(__name__)

SOY_ARRENDATARIO = 'arrendatario'
SOY_RESIDENTE = 'residente'
SOY_AMBOS = 'ambos'


# --------------------------------------------------------------------------- #
# Resolucion del universo visible                                             #
# --------------------------------------------------------------------------- #

def fichas_de(user):
    """Registros de `residentes` ligados a esta cuenta (por cualquiera de las 2 FK).

    Unica puerta de entrada a los datos del portal: todo lo demas parte de aqui.
    """
    if not getattr(user, 'is_authenticated', False):
        return Residentes.objects.none()
    return (
        Residentes.objects
        .filter(Q(arrendatario_cuenta=user) | Q(residente_cuenta=user))
        .distinct()
        .order_by('-id')
    )


def fichas_ids_de(user):
    """Solo los ids de sus fichas: el filtro que usan casi todas las consultas."""
    return list(fichas_de(user).values_list('id', flat=True))


def soy_en(ficha, user):
    """Rol de esta cuenta DENTRO de esta ficha: arrendatario, residente o ambos."""
    es_arr = ficha.arrendatario_cuenta_id == user.id
    es_res = ficha.residente_cuenta_id == user.id
    if es_arr and es_res:
        return SOY_AMBOS
    return SOY_ARRENDATARIO if es_arr else SOY_RESIDENTE


def _roles_de(soy):
    """`soy` -> roles de firmante que le corresponden (para filtrar sign_urls)."""
    if soy == SOY_AMBOS:
        return (SOY_ARRENDATARIO, SOY_RESIDENTE)
    return (soy,)


def _fecha(valor):
    return valor.isoformat() if valor else None


def _fecha_hora(valor):
    """Datetime en hora LOCAL.

    Con USE_TZ la BD devuelve UTC y el front corta el ISO a pelo (`iso.slice`),
    asi que sin localizar un recibo subido a las 9 de la manana se leeria con la
    hora de Londres.
    """
    return timezone.localtime(valor).isoformat() if valor else None


def _url_archivo(campo, version=None):
    """URL publica de un FileField + cache-buster.

    Las keys de documentos son FIJAS por campo (fix 2026-07-16), asi que resubir
    un archivo reusa la URL y el navegador puede servir el viejo de cache
    (Cache-Control 24h). El sufijo `?v=` lo resuelve del lado del servidor para
    que el front no tenga que acordarse.
    """
    if not campo:
        return None
    try:
        url = campo.url
    except Exception:
        return None
    if not url:
        return None
    if version:
        url = f"{url}{'&' if '?' in url else '?'}v={version}"
    return url


def _url_key(key):
    """URL publica de una S3 key suelta (los PDF firmados guardan key, no FileField)."""
    if not key:
        return None
    try:
        return default_storage.url(key)
    except Exception:
        return None


EXTENSIONES_IMAGEN = ('jpg', 'jpeg', 'png', 'webp', 'gif', 'heic', 'heif')
# Lo que un residente puede subir como recibo: su comprobante sale del banco (PDF)
# o de la camara del telefono. Nada ejecutable ni ofimatico.
EXTENSIONES_RECIBO = ('pdf',) + EXTENSIONES_IMAGEN
TAMANO_MAX_RECIBO = 10 * 1024 * 1024  # 10 MB
# Lo que puede subir a su expediente: la foto de la INE o el PDF del banco. Se
# declaran aparte de los recibos aunque hoy coincidan: son dos tramites y uno
# puede endurecerse sin arrastrar al otro.
EXTENSIONES_DOCUMENTO = ('pdf',) + EXTENSIONES_IMAGEN
TAMANO_MAX_DOCUMENTO = 10 * 1024 * 1024  # 10 MB


def _extension(nombre):
    return nombre.rsplit('.', 1)[-1].lower() if nombre and '.' in nombre else ''


# --------------------------------------------------------------------------- #
# Armado de payloads                                                          #
# --------------------------------------------------------------------------- #

def _bloque_arrendatario(f):
    return {
        'nombre': f.nombre_arrendatario or '',
        'nacionalidad': f.nacionalidad_arrendatario or '',
        'rfc': f.rfc_arrendatario or '',
        'curp': f.curp or '',
        'identificacion': f.identificacion_arrendatario or '',
        'no_identificacion': f.no_ide_arrendatario or '',
        'sexo': f.sexo_arrendatario or '',
        'estado_civil': f.estado_civil or '',
        'celular': f.celular_arrendatario or '',
        'correo': f.correo_arrendatario or '',
        'direccion': f.direccion_arrendatario or '',
        'empleo': f.empleo or '',
        'domicilio_empleo': f.domicilio_empleo or '',
    }


def _bloque_residente(f):
    return {
        'nombre': f.nombre_residente or '',
        'nacionalidad': f.nacionalidad_residente or '',
        'identificacion': f.identificacion_residente or '',
        'no_identificacion': f.no_ide_residente or '',
        'sexo': f.sexo or '',
        'fecha_nacimiento': _fecha(f.fecha_nacimiento),
        'edad': f.edad or '',
        'celular': f.celular_residente or '',
        'correo': f.correo_residente or '',
        'direccion': f.direccion_residente or '',
    }


def _referencias(f):
    """Las 3 referencias personales, incluidas las vacias.

    Van SIEMPRE las tres (con su `indice`) porque la pantalla ahora edita: sin
    el hueco no habria donde capturar una referencia que falta. Las vacias las
    esconde el front en modo lectura.
    """
    crudas = [
        (1, f.n_ref1, f.p_ref1, f.tel_ref1),
        (2, f.n_ref2, f.p_ref2, f.tel_ref2),
        (3, f.n_ref3, f.p_ref3, f.tel_ref3),
    ]
    return [
        {'indice': i, 'nombre': n or '', 'parentesco': p or '',
         'telefono': str(t) if t else ''}
        for i, n, p, t in crudas
    ]


def _ficha_publica(f, soy):
    """La ficha COMPLETA: los dos bloques y las referencias.

    Hasta 2026-08-18 cada cuenta veia solo su mitad (del otro, el nombre). Ahora
    las dos cuentas ligadas al mismo registro ven —y editan— la ficha entera:
    son las dos partes del mismo contrato y comparten el tramite, igual que ya
    comparten expediente, recibos e incidencias. `soy` se queda para la etiqueta
    y para saber cual bloque es el propio.
    """
    return {
        'ficha_id': f.id,
        'soy': soy,
        'arrendatario': _bloque_arrendatario(f),
        'residente': _bloque_residente(f),
        'referencias': _referencias(f),
    }


# --------------------------------------------------------------------------- #
# Candado de edicion de la ficha                                              #
# --------------------------------------------------------------------------- #
#
# Regla del usuario (2026-08-18): la ficha se edita SOLO mientras no haya nada
# emitido — contrato "Pendiente" o "En renovacion", y sin proceso de firma
# abierto. En cuanto el documento sale a firmar o queda sellado, los datos se
# congelan: lo que se cambie aqui NO cambia el PDF que ya se genero, asi que
# editar solo abriria un desfase entre lo que dice el portal y lo que dice el
# documento que la gente firmo.
#
# Basta con que UNO de sus contratos este en firma o sellado: la ficha es una
# sola y alimenta a todos.

def _texto_para(columna, valor, etiqueta):
    """(texto limpio, error) para una columna de texto de `residentes`.

    El tope de caracteres se lee del propio modelo en vez de repetirlo aqui: si
    manana crece una columna, esto se entera solo. Truncar en silencio seria
    peor que rechazar — la persona creeria que guardo su direccion completa.
    """
    v = ('' if valor is None else str(valor)).strip()
    campo = Residentes._meta.get_field(columna)
    tope = getattr(campo, 'max_length', None)
    if tope and len(v) > tope:
        return None, f'{etiqueta}: máximo {tope} caracteres.'
    if v and isinstance(campo, EmailField):
        try:
            validate_email(v)
        except ValidationError:
            return None, f'{etiqueta}: el correo no tiene un formato válido.'
    return v, None


def _bloqueo_de_edicion(contratos):
    """(clave, mensaje) del motivo que congela la ficha, o (None, None)."""
    en_firma = vigente = firmado = terminado = None

    for c in contratos:
        rondas = list(c.rondas_firma.all())
        pendiente = next((r for r in rondas if r.estado == 'pendiente'), None)
        if pendiente is not None:
            paquete = _paquete_en_proceso(pendiente)
            que = 'la renovación' if pendiente.tipo == 'renovacion' else 'tu contrato'
            en_firma = en_firma or ('en_firma', (
                f'El Paquete {paquete} de {que} está en proceso de firma. '
                f'Ese documento ya se envió a firmar y no cambia con lo que se '
                f'edite aquí; si algo está mal, avísale a la administración de '
                f'Fraterna antes de firmar.'))
            continue

        # 'en_renovacion' es justo el hueco donde SI se puede corregir: la
        # renovacion se esta preparando y todavia no hay documento emitido.
        if c.estado_contrato == 'en_renovacion':
            continue

        if c.estado_contrato == 'actual':
            vigente = vigente or ('vigente', (
                'Tu contrato está vigente. Tus datos son los que quedaron en el '
                'documento firmado, así que ya no se pueden cambiar desde aquí: '
                'para corregir algo, escríbele a la administración de Fraterna.'))
            continue

        if c.estado_contrato == 'expirado':
            terminado = terminado or ('terminado', (
                'Tu contrato ya terminó. Los datos quedan como se firmaron, de '
                'registro; para cualquier corrección, escríbele a la '
                'administración de Fraterna.'))
            continue

        # `estado_contrato` esta en NULL en 579 de 900 contratos (nunca se
        # backfilleo), asi que el campo por si solo no distingue un borrador de
        # un contrato ya firmado. La bitacora de rondas si: una ronda 'firmado'
        # es un termino EN PIE, con su PDF, y esos datos tampoco se tocan.
        if any(r.estado == 'firmado' for r in rondas):
            firmado = firmado or ('firmado', (
                'Ya hay un contrato firmado con estos datos, así que quedaron '
                'sellados. Para corregir algo, escríbele a la administración de '
                'Fraterna.'))

    return en_firma or vigente or firmado or terminado or (None, None)


# Documentos del expediente. `propio_de` = de quien es el archivo
# ('arrendatario' / 'residente' / None = del expediente).
#
# Desde 2026-08-18 `propio_de` YA NO FILTRA: las dos cuentas de una ficha ven el
# expediente entero y cualquiera de las dos puede subir o reemplazar cualquier
# documento (regla del usuario, la misma que en recibos e incidencias). Se
# conserva para etiquetar de quien es cada cosa en la pantalla.
#
# Convencion real de prod: `Ine` es la INE del ARRENDATARIO y `Ine_arr` la del
# RESIDENTE. El nombre del campo miente; no invertir estas etiquetas.
DOCUMENTOS = [
    ('Ine', 'INE / Identificación del arrendatario', SOY_ARRENDATARIO, 'comentarios_ine'),
    ('Ine_arr', 'INE / Identificación del residente', SOY_RESIDENTE, 'comentarios_ine'),
    ('Comp_dom', 'Comprobante de domicilio', None, 'comentarios_comp'),
    ('Rfc', 'Constancia de situación fiscal', None, 'comentarios_rfc'),
    ('Ingresos', 'Comprobante de ingresos', None, 'comentarios_ingresos'),
    ('Recomendacion_laboral', 'Recomendación laboral', None, 'comentarios_rl'),
    ('Extras', 'Documentos extra', None, 'comentarios_extra'),
]

# El mismo catalogo por campo, para validar lo que llega del formulario: subir a
# un campo que no este aqui no es una operacion que exista.
CAMPOS_DOCUMENTO = {
    campo: (etiqueta, propio_de, comentario)
    for campo, etiqueta, propio_de, comentario in DOCUMENTOS
}


def _documento_publico(expediente, campo):
    """Un documento del expediente, o None si ese campo esta vacio."""
    etiqueta, propio_de, campo_comentario = CAMPOS_DOCUMENTO[campo]
    version = None
    if expediente.dateTimeOfUpload:
        version = int(expediente.dateTimeOfUpload.timestamp())
    archivo = getattr(expediente, campo, None)
    url = _url_archivo(archivo, version)
    if not url:
        return None
    nombre = str(archivo).rsplit('/', 1)[-1]
    return {
        'campo': campo,
        'etiqueta': etiqueta,
        'propio_de': propio_de,
        'tiene_archivo': True,
        'nombre_archivo': nombre,
        'url': url,
        # El front decide con esto si pinta un <img> o un <iframe>: adivinar
        # por la URL es fragil cuando lleva cache-buster.
        'extension': _extension(nombre),
        'es_imagen': _extension(nombre) in EXTENSIONES_IMAGEN,
        'comentario': getattr(expediente, campo_comentario, None) or '',
    }


def _documentos_publicos(expediente):
    """Los documentos que este expediente TIENE cargados (los vacios, no).

    Los huecos se rellenan mas arriba, despues de juntar todas las filas: si un
    campo vacio saliera de aqui, en el dedup de `mis_documentos` le ganaria a la
    fila vieja que si tiene el archivo y el documento desapareceria.
    """
    salida = []
    for campo, _etiqueta, _propio_de, _comentario in DOCUMENTOS:
        doc = _documento_publico(expediente, campo)
        if doc:
            salida.append(doc)
    return salida


def _documento_vacio(campo):
    """Hueco de un documento que todavia no se sube: la tarjeta con el boton."""
    etiqueta, propio_de, _comentario = CAMPOS_DOCUMENTO[campo]
    return {
        'campo': campo,
        'etiqueta': etiqueta,
        'propio_de': propio_de,
        'tiene_archivo': False,
        'nombre_archivo': '',
        'url': None,
        'extension': '',
        'es_imagen': False,
        'comentario': '',
    }


# Las partes que se le muestran al residente. Fraterna (arrendador) y el
# prestador de servicios TAMBIEN firman el documento, pero son firmas internas
# que se resuelven al final del proceso: al residente no le dicen nada sobre lo
# que el tiene que hacer, y verlas "pendientes" solo confunde. Se ven las dos
# partes que importan de este lado del contrato.
ROLES_VISIBLES = ('arrendatario', 'residente')
ORDEN_ROLES = {'arrendatario': 0, 'residente': 1}

ETIQUETA_ROL = {
    'arrendatario': 'Arrendatario',
    'residente': 'Residente',
}


def _firmantes_del_paquete(ronda, paquete):
    """Los firmantes de UN paquete. Con el P2 generado, la ronda tiene los dos
    juegos (4 + 4) y mezclarlos pinta a la misma persona dos veces con estados
    distintos, sin nada que diga cual es cual."""
    return [f for f in ronda.firmantes.all() if f.paquete == paquete]


def _firmantes_publicos(ronda, roles):
    """TODAS las partes de la ronda con su estado; el enlace, solo el propio.

    El residente necesita ver como va el proceso completo — a quien le falta
    firmar — asi que el estado de las demas partes si viaja. Lo que NO viaja es
    el `sign_url` de nadie mas (firmaria por otro) ni su correo (no le hace
    falta para saber si ya firmaron).

    El `sign_url` propio se calla en dos casos, y los dos importan: si la persona
    YA firmo (el enlace lleva a un documento cerrado) y si la ronda no esta
    'pendiente' (un intento cancelado o expirado conserva su enlace de ZapSign,
    y mandar ahi al residente seria hacerlo firmar algo que el sistema desecho).
    """
    ronda_viva = ronda.estado == 'pendiente'
    en_proceso = _paquete_en_proceso(ronda)
    salida = []
    for f in _firmantes_del_paquete(ronda, en_proceso):
        rol = (f.rol or '').lower()
        if rol not in ROLES_VISIBLES:
            continue
        es_mio = rol in roles
        puede_firmar = es_mio and ronda_viva and f.estado != 'firmado'
        salida.append({
            'paquete': f.paquete,
            'nombre': f.nombre,
            'rol': rol,
            'rol_etiqueta': ETIQUETA_ROL.get(rol, (f.rol or '').capitalize()),
            'estado': f.estado,
            'firmado_en': f.firmado_en.isoformat() if f.firmado_en else None,
            'es_mio': es_mio,
            'sign_url': f.sign_url if puede_firmar else None,
        })
    return sorted(salida, key=lambda s: (s['paquete'], ORDEN_ROLES.get(s['rol'], 9)))


def _paquete_en_proceso(ronda):
    """1 o 2: en que mitad del expediente esta parada la ronda.

    El Paquete 2 se genera DESPUES de que el 1 queda listo, asi que su sola
    existencia (token_2, o firmantes de paquete 2) ya dice que el proceso avanzo.
    """
    if ronda.token_2 or any(f.paquete == 2 for f in ronda.firmantes.all()):
        return 2
    return 1


def _ronda_publica(ronda, roles):
    """Una ronda/proceso de firma vista por una de las partes."""
    return {
        'id': ronda.id,
        'uuid': str(ronda.uuid) if ronda.uuid else None,
        'numero': ronda.numero,
        'tipo': ronda.tipo,               # 'inicial' | 'renovacion'
        'estado': ronda.estado,           # pendiente | firmado | expirado | cancelado
        'mono_paquete': ronda.mono_paquete,
        'estado_firma_1': ronda.estado_firma_1,
        'estado_firma_2': ronda.estado_firma_2,
        'generado_en': ronda.generado_en.isoformat() if ronda.generado_en else None,
        'cerrado_en': ronda.cerrado_en.isoformat() if ronda.cerrado_en else None,
        'fecha_celebracion': _fecha(ronda.fecha_celebracion),
        'fecha_vigencia': _fecha(ronda.fecha_vigencia),
        'fecha_move_in': _fecha(ronda.fecha_move_in),
        'fecha_move_out': _fecha(ronda.fecha_move_out),
        # PDF firmado en NUESTRO S3: existe solo cuando el documento junto todas
        # las firmas. Es el contrato final que el residente se puede descargar.
        'pdf_firmado_1_url': _url_key(ronda.pdf_firmado_1),
        'pdf_firmado_2_url': _url_key(ronda.pdf_firmado_2),
        'paquete_en_proceso': _paquete_en_proceso(ronda),
        'firmantes': _firmantes_publicos(ronda, roles),
        # Firmas que faltan de las partes que NO se muestran (Fraterna y el
        # prestador). Sin este dato el front contaria solo las visibles y diria
        # "proceso completo" cuando todavia falta la firma interna.
        'pendientes_internas': sum(
            1 for f in _firmantes_del_paquete(ronda, _paquete_en_proceso(ronda))
            if (f.rol or '').lower() not in ROLES_VISIBLES and f.estado != 'firmado'
        ),
    }


# Las dos mitades del expediente que se manda a firmar. Su contenido lo define
# Contratos_fraterna (fraterna_views): P1 = contrato + manual UTO + pagares;
# P2 = comodato + anexos + poliza. Aqui no se replica nada de eso, se llama.
PAQUETE_1 = 'paquete_1'
PAQUETE_2 = 'paquete_2'
TODO = 'todo'

ETIQUETA_PAQUETE = {
    PAQUETE_1: 'Contrato, manual y pagarés',
    PAQUETE_2: 'Comodato, anexos y póliza',
    TODO: 'Expediente completo',
}


def _leer_de_s3(key):
    """Bytes de un objeto de S3, o None si no se puede leer."""
    if not key:
        return None
    try:
        with default_storage.open(key, 'rb') as f:
            return f.read()
    except Exception as e:
        logger.warning("Portal: no se pudo leer %s de S3 (%s)", key, e)
        return None


def _unir_pdfs(pdfs):
    """Concatena varios PDF en uno (para la opcion 'todo')."""
    escritor = PdfWriter()
    for datos in pdfs:
        for pagina in PdfReader(io.BytesIO(datos)).pages:
            escritor.add_page(pagina)
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


# De donde salio el PDF que se esta mostrando. Ordenados de mas real a menos:
# el residente tiene que poder distinguir el documento definitivo del borrador.
ORIGEN_FIRMADO = 'firmado'            # cerrado, con todas las firmas (nuestro S3)
ORIGEN_PARCIAL = 'firmas_parciales'   # en ZapSign, ya con algunas firmas puestas
ORIGEN_ENVIADO = 'enviado_a_firmar'   # en ZapSign, tal cual se envio, sin firmas
ORIGEN_PREVIA = 'previa'              # no hay proceso: se rinde la plantilla

# Que tan definitivo es cada origen. Sirve para el caso 'todo', donde se pegan
# dos mitades que pueden venir de fuentes distintas: gana la menos definitiva.
RANGO_ORIGEN = {
    ORIGEN_PREVIA: 0,
    ORIGEN_ENVIADO: 1,
    ORIGEN_PARCIAL: 2,
    ORIGEN_FIRMADO: 3,
}


def _bajar(url, que):
    """Bytes de una URL, o None. Con timeout corto: esto va en la ruta de una
    pantalla, y mas vale caer al plan B que dejarla colgada."""
    import requests  # tardio: solo hace falta cuando hay proceso de firma vivo
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.warning("Portal: no se pudo bajar %s (%s)", que, e)
        return None


def _consultar_zapsign(token):
    """GET docs/{token}/ a ZapSign — la fuente de verdad. None si falla.

    Falla en silencio a proposito: esto va en la ruta de una pantalla, y si
    ZapSign no contesta es mejor mostrar lo que hay en la BD que romperla.
    """
    import requests  # tardio: solo hace falta cuando hay proceso de firma vivo
    from decouple import config
    try:
        base = config('API_URL_ZAPSIGN')
        api_token = config('API_TOKEN_ZAPSIGN')
        r = requests.get(
            f'{base}docs/{token}/',
            headers={'Authorization': f'Bearer {api_token}'},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("Portal: ZapSign no respondio por el doc %s (%s)", token, e)
        return None


def _doc_en_zapsign(token):
    """(bytes, origen) del documento vivo en ZapSign, o (None, None).

    ZapSign publica DOS archivos del mismo documento y la diferencia importa:
      · `signed_file`  -> el PDF con las firmas puestas HASTA AHORA. Aparece en
        cuanto firma el primero, aunque el documento siga 'pending'.
      · `original_file`-> el PDF tal cual se envio, sin firma ninguna.
    Se prefiere el primero: si alguien ya firmo, el residente debe ver esa firma.
    """
    doc = _consultar_zapsign(token)
    if not doc:
        return None, None

    if doc.get('signed_file'):
        datos = _bajar(doc['signed_file'], f'signed_file de {token}')
        if datos:
            return datos, ORIGEN_PARCIAL
    if doc.get('original_file'):
        datos = _bajar(doc['original_file'], f'original_file de {token}')
        if datos:
            return datos, ORIGEN_ENVIADO
    return None, None


def conciliar_con_zapsign(ronda):
    """Pone al dia el espejo local de firmas preguntandole a ZapSign.

    El estado de firma llega normalmente por webhook. Dos motivos para no
    confiar solo en el:
      · En local no hay webhook (ZapSign no puede llamar a 127.0.0.1), asi que
        el residente firma y la pantalla se queda diciendo "aun no firma".
      · En prod el webhook YA perdio eventos aislados (caso documentado del
        contrato 919) y no habia nada que reconciliara despues. El residente se
        quedaria viendo su firma como pendiente para siempre.

    Preguntar al abrir la pantalla cierra las dos. Es barato: un GET por paquete
    vivo, y solo cuando hay una ronda pendiente.

    LIMITE DELIBERADO: esto sincroniza el ESPEJO DE FIRMANTES y el estado por
    paquete. NO cierra rondas, no marca `estado_contrato`, no baja PDF a S3 ni
    ocupa/libera camas — todo eso sigue siendo del webhook, que es quien tiene
    el orden correcto. Aqui solo se refleja un hecho que ya ocurrio.

    Devuelve True si algo cambio.
    """
    from .zapsign_webhook import _sync_firmantes  # mismo criterio que el webhook

    if ronda.estado != 'pendiente':
        return False

    cambio = False
    for paquete, token in ((1, ronda.token_1), (2, ronda.token_2)):
        if not token:
            continue
        doc = _consultar_zapsign(token)
        if not doc:
            continue
        try:
            _sync_firmantes(ronda, paquete, doc.get('signers') or [])
        except Exception as e:
            logger.warning("Portal: no se pudo sincronizar la ronda %s P%s (%s)",
                           ronda.pk, paquete, e)
            continue
        campo = f'estado_firma_{paquete}'
        status = doc.get('status')
        if status and getattr(ronda, campo) != status:
            setattr(ronda, campo, status)
            ronda.save(update_fields=[campo])
            cambio = True
    return cambio


def conciliar_rondas(rondas):
    """Concilia varias rondas contra ZapSign a la vez.

    Cada consulta tarda ~4s, asi que en fila una cuenta con varios contratos
    hacia esperar 16s a que cargara la pantalla. Como es I/O puro, van en
    paralelo: el peor caso pasa a ser lo que tarde la mas lenta.

    Cada hilo abre su propia conexion a la BD (son thread-local) y tiene que
    cerrarla al terminar, o quedan colgadas.
    """
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connection

    rondas = list(rondas)
    if not rondas:
        return
    if len(rondas) == 1:
        conciliar_con_zapsign(rondas[0])
        return

    def tarea(ronda):
        try:
            conciliar_con_zapsign(ronda)
        except Exception as e:
            logger.warning("Portal: fallo conciliando la ronda %s (%s)", ronda.pk, e)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(tarea, rondas))


def _pdf_de_paquete(contrato, parte, user):
    """(bytes, origen) del paquete pedido. (None, None) si no se pudo armar.

    Se busca el documento MAS REAL que exista, en este orden:
      1. El PDF firmado que dejo el webhook en nuestro S3 (proceso cerrado).
      2. El documento vivo en ZapSign, si hay una ronda pendiente: lo que de
         verdad se mando a firmar, con las firmas que ya lleve. Esto es lo que
         el residente necesita ver mientras el proceso corre — la plantilla
         rendida en vivo puede haber cambiado desde que se envio.
      3. Como ultimo recurso, la plantilla rendida con los mismos metodos del
         viewset de operador: una vista previa de lo que se firmara.

    Se instancia `Contratos_fraterna` a proposito en vez de copiar su logica:
    los generadores son metodos suyos y no necesitan request (leen del queryset
    de clase). Copiarlos aqui seria condenarlos a divergir.
    """
    from .fraterna_views import Contratos_fraterna  # tardio: evita import circular

    rondas = contrato.rondas_firma.all()
    firmada = next((r for r in rondas if r.estado == 'firmado'), None)
    pendiente = next((r for r in rondas if r.estado == 'pendiente'), None)
    # La ronda que manda: si el contrato ya esta en pie, la firmada; si se esta
    # firmando ahora, la pendiente.
    ronda = firmada or pendiente

    # 1. El definitivo que bajo el webhook a NUESTRO S3.
    if firmada:
        # Las rondas migradas del esquema viejo traen TODO en un solo documento
        # (mono_paquete): ese PDF es el expediente completo, no solo el P1.
        key = (firmada.pdf_firmado_1 if (parte == PAQUETE_1 or firmada.mono_paquete)
               else firmada.pdf_firmado_2)
        datos = _leer_de_s3(key)
        if datos:
            return datos, ORIGEN_FIRMADO

    # 2. ZapSign. Vale tanto para la ronda en curso como para una YA firmada
    #    cuyo PDF no llego al bucket: el webhook baja el `signed_file` en un hilo
    #    con reintentos, y si esos se agotan (o el evento se perdio) la key queda
    #    vacia. Antes se caia a la vista previa y el residente veia un borrador
    #    de un contrato que ya habia firmado; ZapSign si tiene el documento real.
    if ronda:
        token = ronda.token_1 if parte == PAQUETE_1 else ronda.token_2
        if token:
            datos, origen = _doc_en_zapsign(token)
            if datos:
                # Si la ronda esta cerrada, lo que sirve ZapSign ya es el
                # documento final aunque venga por la via del `signed_file`.
                return datos, (ORIGEN_FIRMADO if firmada else origen)

    # 3. Vista previa.
    marca = marca_para(user)
    generador = Contratos_fraterna()
    try:
        if parte == PAQUETE_1:
            _, datos, _ = generador._generar_paquete_1_pdf(contrato.id, marca=marca)
        else:
            _, datos, _ = generador._generar_paquete_2_pdf(contrato.id, marca=marca)
        return datos, ORIGEN_PREVIA
    except Exception as e:
        logger.warning(
            "Portal: no se pudo generar el %s del contrato %s (%s)",
            parte, contrato.id, e,
        )
        return None, None


def _partes_disponibles(c):
    """Que opciones tiene sentido ofrecerle al residente para ESTE contrato.

    Con un proceso de firma VIVO hay un solo documento que importa: el que esta
    en la mesa de firma. Ofrecer ahi las tres opciones mezclaria ese documento
    real con borradores generados al vuelo — el residente veria "Paquete 2" y no
    sabria que eso todavia no existe, o pediria "expediente completo" y se le
    pegaria una vista previa debajo de lo que si mando a firmar.

    Un contrato firmado con el esquema viejo (mono_paquete) es tambien un unico
    documento: su "Paquete 2" nunca se genero por separado.
    """
    pendiente = next((r for r in c.rondas_firma.all() if r.estado == 'pendiente'), None)
    if pendiente:
        return [PAQUETE_1 if _paquete_en_proceso(pendiente) == 1 else PAQUETE_2]

    firmada = next((r for r in c.rondas_firma.all() if r.estado == 'firmado'), None)
    if firmada and firmada.mono_paquete:
        return [PAQUETE_1]
    return [PAQUETE_1, PAQUETE_2, TODO]


def _estado_visible(c, pendiente, firmada):
    """Como se le nombra el estado del contrato al residente.

    `estado_contrato` esta en NULL en casi todos los contratos (nunca se
    backfilleo), y "Sin estado" no le dice nada a quien esta esperando firmar.
    Cuando el campo no ayuda, el estado se deduce de la bitacora de rondas, que
    si sabe donde esta parado el proceso.

    Devuelve (texto, tono) — el tono lo usa el front para el color.
    """
    if c.estado_contrato == 'actual':
        return 'Vigente', 'ok'
    if c.estado_contrato == 'expirado':
        return 'Terminado', 'neutro'

    if pendiente:
        paquete = _paquete_en_proceso(pendiente)
        # Cuando arrendatario y residente ya firmaron, para ellos el tramite se
        # acabo: lo que falta (Fraterna y el prestador) se resuelve internamente
        # y no depende de nadie de este lado. Seguir diciendo "en proceso" los
        # deja esperando algo que ya hicieron. El detalle fino —cuantas firmas
        # faltan de verdad— lo da el bloque de firma, que no promete de mas.
        visibles = [f for f in _firmantes_del_paquete(pendiente, paquete)
                    if (f.rol or '').lower() in ROLES_VISIBLES]
        if visibles and all(f.estado == 'firmado' for f in visibles):
            return f'Firma del Paquete {paquete} completada', 'ok'

        que = 'Renovación' if pendiente.tipo == 'renovacion' else 'Contrato'
        return f'{que} en proceso de firma · Paquete {paquete}', 'proceso'

    if c.estado_contrato == 'en_renovacion':
        return 'En renovación', 'proceso'
    if firmada:
        return 'Firmado', 'ok'
    return 'Sin proceso de firma', 'neutro'


def _orden_de_vigencia(c):
    """Clave para ordenar contratos de "el que le importa hoy" hacia atras.

    Lo natural seria `estado_contrato == 'actual'`, pero ese campo esta en NULL
    en casi todos los contratos historicos (nunca se backfilleo), asi que por si
    solo no distingue nada. Se completa con la bitacora de rondas, que si es
    fiable: un contrato con firma en curso o con termino en pie esta mas vivo
    que uno sin rastro de firma.
    """
    rondas = list(c.rondas_firma.all())
    peso_estado = {'actual': 3, 'en_renovacion': 2, None: 1, '': 1, 'expirado': 0}
    return (
        peso_estado.get(c.estado_contrato, 1),
        any(r.estado == 'pendiente' for r in rondas),
        any(r.estado == 'firmado' for r in rondas),
        c.id,
    )


def _terminos_publicos(c, ronda):
    """Los terminos que se le muestran al residente: (inmueble, terminos, fuente).

    La fila `fraterna_contrato` NO es la verdad de lo que se firmo. Es la copia
    de trabajo del SIGUIENTE intento: una renovacion en curso la edita, y hay
    contratos en prod "renovados por edicion" donde la fila dice 2027 y el
    documento firmado dice otra cosa. Mostrarle esa fila al residente le
    ensenaria numeros que su contrato no dice.

    Asi que manda lo que quedo CONGELADO en la ronda — la pendiente si esta
    firmando, o la firmada si ya esta vigente — que es exactamente lo que
    imprimio el documento que tiene enfrente. La fila del contrato queda de
    respaldo para los campos que el snapshot no traiga (los migrados del
    esquema viejo son parciales) y para los contratos sin ninguna ronda.
    """
    snap = (ronda.datos_snapshot or {}) if ronda else {}

    def dato(clave, atributo=None):
        """Del snapshot si lo trae; si no, de la fila del contrato."""
        valor = snap.get(clave)
        if valor in (None, ''):
            valor = getattr(c, atributo or clave, None)
        return '' if valor is None else str(valor)

    def fecha_de(campo):
        if ronda is not None and getattr(ronda, campo, None):
            return getattr(ronda, campo)
        return getattr(c, campo, None)

    inmueble = {
        'departamento': dato('no_depa'),
        'cama': dato('cama'),
        'piso': dato('piso'),
        'tipologia': dato('tipologia'),
        'medidas': dato('medidas'),
        'habitantes': dato('habitantes'),
        'estacionamiento': dato('estacionamiento'),
        'precio_estacionamiento': dato('precio_estacionamiento_mxn'),
        'kilowatts_incluidos': dato('kilowatts_incluidos'),
    }

    dia_pago = snap.get('dia_pago') or c.dia_pago
    terminos = {
        'renta': dato('renta'),
        'duracion': dato('duracion'),
        # NULL = dia 5, que es el comportamiento historico del contrato.
        'dia_pago': dia_pago if dia_pago else 5,
        'fecha_celebracion': _fecha(fecha_de('fecha_celebracion')),
        'fecha_move_in': _fecha(fecha_de('fecha_move_in')),
        'fecha_move_out': _fecha(fecha_de('fecha_move_out')),
        'fecha_vigencia': _fecha(fecha_de('fecha_vigencia')),
    }
    return inmueble, terminos, ('ronda' if ronda is not None else 'contrato')


def _contrato_publico(c, soy):
    """Terminos del contrato + sus procesos de firma, para una de las partes."""
    roles = _roles_de(soy)
    # Los intentos 'cancelado' (desechados antes de completarse: se regeneraron
    # los enlaces, se corrigio un dato) son ruido de operacion. El residente ve
    # su historia real: lo pendiente, lo firmado y lo que un dia estuvo en pie.
    rondas = sorted(
        (r for r in c.rondas_firma.all() if r.estado != 'cancelado'),
        key=lambda r: r.numero,
    )

    vigencia, fuente_vigencia = c.vigencia_efectiva()

    # El proceso "vivo": el que tiene enlaces por firmar. Solo puede haber uno
    # (UniqueConstraint uniq_ronda_pendiente_por_contrato).
    pendiente = next((r for r in rondas if r.estado == 'pendiente'), None)
    firmada = next((r for r in rondas if r.estado == 'firmado'), None)

    estado_texto, estado_tono = _estado_visible(c, pendiente, firmada)

    # Los terminos salen de la ronda que corresponde: la que se esta firmando
    # ahora, o la que quedo en pie. Ver _terminos_publicos.
    inmueble, terminos, fuente_datos = _terminos_publicos(c, pendiente or firmada)

    return {
        'contrato_id': c.id,
        'ficha_id': c.residente_id,
        'soy': soy,
        'estado_contrato': c.estado_contrato,
        # Lo que se le muestra al residente: el campo crudo casi siempre es NULL,
        # asi que cuando no dice nada el estado sale de la bitacora de rondas.
        'estado_texto': estado_texto,
        'estado_tono': estado_tono,
        # Que puede pedir el visor para ESTE contrato (ver y descargar).
        'partes': [
            {'valor': p, 'etiqueta': ETIQUETA_PAQUETE[p]} for p in _partes_disponibles(c)
        ],
        'inmueble': inmueble,
        'terminos': terminos,
        # De donde salieron esos numeros: 'ronda' = congelados en el documento
        # que se firmo/esta firmando; 'contrato' = la fila (solo si no hay ronda).
        'fuente_datos': fuente_datos,
        # El proceso de firma activo, si lo hay: aqui vive SU enlace.
        'firma_en_curso': _ronda_publica(pendiente, roles) if pendiente else None,
        # El termino en pie hoy (contrato firmado vigente).
        'firma_vigente': _ronda_publica(firmada, roles) if firmada else None,
        # Renovaciones: historia completa de intentos, del mas viejo al mas nuevo.
        'procesos': [_ronda_publica(r, roles) for r in rondas],
        'renovaciones': [
            _ronda_publica(r, roles) for r in rondas if r.tipo == 'renovacion'
        ],
    }


# --------------------------------------------------------------------------- #
# Vistas                                                                      #
# --------------------------------------------------------------------------- #

class PortalResidente(viewsets.ViewSet):
    """Pantallas del portal, siempre acotadas a request.user.

    Todo es GET salvo `subir_documento`: la unica escritura de aqui es dejar un
    archivo en un campo del expediente. Ni borrar documentos ni tocar los
    comentarios de la administracion son operaciones que existan.
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def _fallo(self, e, donde):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logger.error(
            f"{datetime.now()} Portal residente ({donde}) fallo en la linea "
            f"{exc_tb.tb_lineno}: {e}"
        )
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Lo unico editable de la ficha, y a que columna va cada cosa. Lo que no
    # este en estos dos mapas NO es escribible desde el portal: las cuentas
    # ligadas, el capturista, los ids y el estado del contrato quedan fuera por
    # construccion, no por una lista de prohibidos que haya que mantener.
    CAMPOS_ARRENDATARIO = {
        'nombre': 'nombre_arrendatario',
        'nacionalidad': 'nacionalidad_arrendatario',
        'rfc': 'rfc_arrendatario',
        'curp': 'curp',
        'identificacion': 'identificacion_arrendatario',
        'no_identificacion': 'no_ide_arrendatario',
        'sexo': 'sexo_arrendatario',
        'estado_civil': 'estado_civil',
        'celular': 'celular_arrendatario',
        'correo': 'correo_arrendatario',
        'direccion': 'direccion_arrendatario',
        'empleo': 'empleo',
        'domicilio_empleo': 'domicilio_empleo',
    }
    CAMPOS_RESIDENTE = {
        'nombre': 'nombre_residente',
        'nacionalidad': 'nacionalidad_residente',
        'identificacion': 'identificacion_residente',
        'no_identificacion': 'no_ide_residente',
        'sexo': 'sexo',
        'fecha_nacimiento': 'fecha_nacimiento',
        'edad': 'edad',
        'celular': 'celular_residente',
        'correo': 'correo_residente',
        'direccion': 'direccion_residente',
    }
    # Van a columnas NOT NULL y son la identidad de las partes en el contrato:
    # se pueden corregir, no vaciar.
    NOMBRES_OBLIGATORIOS = ('nombre_arrendatario', 'nombre_residente')

    def _bloqueos_por_ficha(self, fichas):
        """{ficha_id: (clave, mensaje)} — el candado de cada ficha.

        Una sola consulta para todas: `_paquete_en_proceso` mira los firmantes y
        sin el prefetch serian tres viajes a la BD por contrato.
        """
        ids = [f.id for f in fichas]
        por_ficha = {fid: [] for fid in ids}
        for c in (FraternaContratos.objects
                  .filter(residente_id__in=ids)
                  .prefetch_related('rondas_firma__firmantes')):
            por_ficha[c.residente_id].append(c)
        return {fid: _bloqueo_de_edicion(cs) for fid, cs in por_ficha.items()}

    def mi_informacion(self, request):
        """GET /portal/mi_informacion/ -> fichas ligadas a esta cuenta.

        Cada ficha viaja completa (las dos partes) y declara si se puede editar
        y, si no, por que: el front pinta con eso el boton o el aviso.
        """
        try:
            registros = list(fichas_de(request.user))
            bloqueos = self._bloqueos_por_ficha(registros)
            fichas = []
            for f in registros:
                clave, mensaje = bloqueos.get(f.id, (None, None))
                datos = _ficha_publica(f, soy_en(f, request.user))
                datos['puede_editar'] = clave is None
                datos['bloqueo'] = (None if clave is None
                                    else {'motivo': clave, 'mensaje': mensaje})
                fichas.append(datos)
            return Response({
                'cuenta': {
                    'username': request.user.username,
                    'nombre': request.user.first_name or '',
                    'correo': request.user.email or '',
                },
                'fichas': fichas,
                'total': len(fichas),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'mi_informacion')

    def _cambios_de_ficha(self, datos):
        """({columna: valor}, None) listo para escribir, o (None, error).

        Lo que no este en los mapas se IGNORA en vez de reventar: el front manda
        de vuelta el payload que recibio, y un campo de solo lectura colandose no
        deberia tumbar el guardado. Lo que si se rechaza es un valor invalido.
        """
        cambios = {}

        for bloque, mapa, quien in (
            ('arrendatario', self.CAMPOS_ARRENDATARIO, 'Arrendatario'),
            ('residente', self.CAMPOS_RESIDENTE, 'Residente'),
        ):
            enviado = datos.get(bloque)
            if enviado is None:
                continue
            if not isinstance(enviado, dict):
                return None, 'Los datos del %s tienen que venir en un objeto.' % bloque

            for clave, valor in enviado.items():
                columna = mapa.get(clave)
                if not columna:
                    continue

                if columna == 'fecha_nacimiento':
                    texto = ('' if valor is None else str(valor)).strip()
                    if not texto:
                        cambios[columna] = None
                        continue
                    fecha = parse_date(texto)
                    if not fecha:
                        return None, 'La fecha de nacimiento no es válida (formato AAAA-MM-DD).'
                    cambios[columna] = fecha
                    continue

                etiqueta = '%s: %s' % (quien, clave.replace('_', ' '))
                limpio, problema = _texto_para(columna, valor, etiqueta)
                if problema:
                    return None, problema
                if columna in self.NOMBRES_OBLIGATORIOS and not limpio:
                    return None, 'El nombre del %s no puede quedar vacío.' % bloque
                cambios[columna] = limpio

        # Referencias personales: siempre son tres y cada una dice cual es
        # (`indice`), asi que corregir la 2 no arrastra a la 1 ni a la 3.
        referencias = datos.get('referencias')
        if referencias is not None:
            if not isinstance(referencias, list):
                return None, 'Las referencias tienen que venir en una lista.'
            for posicion, ref in enumerate(referencias, start=1):
                if not isinstance(ref, dict):
                    return None, 'Cada referencia tiene que venir en un objeto.'
                try:
                    indice = int(ref.get('indice') or posicion)
                except (TypeError, ValueError):
                    return None, 'La referencia trae un índice que no es un número.'
                if indice not in (1, 2, 3):
                    return None, 'Solo hay tres referencias personales.'

                for clave, columna in (('nombre', 'n_ref%d' % indice),
                                       ('parentesco', 'p_ref%d' % indice)):
                    if clave in ref:
                        limpio, problema = _texto_para(
                            columna, ref.get(clave),
                            'Referencia %d: %s' % (indice, clave))
                        if problema:
                            return None, problema
                        cambios[columna] = limpio

                if 'telefono' in ref:
                    crudo = '' if ref.get('telefono') is None else str(ref['telefono'])
                    digitos = ''.join(c for c in crudo if c.isdigit())
                    if crudo.strip() and not digitos:
                        return None, ('El teléfono de la referencia %d no trae números.'
                                      % indice)
                    if len(digitos) > 15:
                        return None, ('El teléfono de la referencia %d tiene demasiados '
                                      'dígitos.' % indice)
                    # La columna es BigInteger: se guarda solo el numero, sin
                    # espacios ni guiones, y vacio es NULL (no cero).
                    cambios['tel_ref%d' % indice] = int(digitos) if digitos else None

        return cambios, None

    def actualizar_informacion(self, request):
        """PATCH /portal/mi_informacion/ -> corrige los datos de la ficha.

        Las dos cuentas ligadas al registro editan LO MISMO: el bloque del
        arrendatario, el del residente y las tres referencias. Quien puede
        escribir no lo decide el rol sino el estado del contrato
        (`_bloqueo_de_edicion`): con firma en curso o con documento sellado se
        responde 403 con el motivo, para que la pantalla lo pueda explicar.

        El correo que se edita aqui es el DEL CONTRATO. No es el de la cuenta
        del portal: cambiarlo no cambia por donde entra ni a donde le llegan sus
        credenciales.
        """
        try:
            fichas = list(fichas_de(request.user))
            if not fichas:
                return Response({'error': 'Tu cuenta no está ligada a ningún registro.'},
                                status=status.HTTP_403_FORBIDDEN)

            # Misma regla anti-IDOR de siempre: la ficha que manda el front solo
            # sirve para elegir ENTRE LAS SUYAS.
            pedida = request.data.get('ficha_id')
            try:
                ficha_id = int(pedida) if pedida else fichas[0].id
            except (TypeError, ValueError):
                ficha_id = fichas[0].id
            ficha = next((f for f in fichas if f.id == ficha_id), fichas[0])

            # El candado se comprueba AQUI. Que el front esconda el boton es
            # comodidad; esto es lo que de verdad cierra la puerta.
            clave, mensaje = self._bloqueos_por_ficha([ficha]).get(ficha.id, (None, None))
            if clave:
                return Response({'error': mensaje, 'motivo': clave},
                                status=status.HTTP_403_FORBIDDEN)

            cambios, problema = self._cambios_de_ficha(request.data)
            if problema:
                return Response({'error': problema}, status=status.HTTP_400_BAD_REQUEST)
            if not cambios:
                return Response({'error': 'No llegó ningún dato que cambiar.'},
                                status=status.HTTP_400_BAD_REQUEST)

            for columna, valor in cambios.items():
                setattr(ficha, columna, valor)
            ficha.save(update_fields=list(cambios.keys()))

            datos = _ficha_publica(ficha, soy_en(ficha, request.user))
            datos['puede_editar'] = True
            datos['bloqueo'] = None
            return Response(datos, status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'actualizar_informacion')

    def mis_documentos(self, request):
        """GET /portal/mis_documentos/ -> expediente COMPLETO por ficha.

        Las dos cuentas de una ficha ven lo mismo. Los documentos que faltan
        viajan vacios (`tiene_archivo: False`) para que la pantalla ofrezca
        subirlos: sin el hueco no habria donde colgar el boton.
        """
        try:
            fichas = list(fichas_de(request.user))
            por_ficha = {f.id: soy_en(f, request.user) for f in fichas}

            expedientes = DocumentosResidentes.objects.filter(
                residente_id__in=por_ficha.keys()
            ).order_by('residente_id', '-id')

            # Un registro puede tener mas de una fila de documentos (altas
            # repetidas): se juntan todas y se deduplica por campo, quedandose
            # con la mas reciente (el order_by de arriba la pone primero).
            acumulado = {fid: {} for fid in por_ficha}
            for exp in expedientes:
                for doc in _documentos_publicos(exp):
                    acumulado[exp.residente_id].setdefault(doc['campo'], doc)

            salida = []
            for f in fichas:
                cargados = acumulado[f.id]
                salida.append({
                    'ficha_id': f.id,
                    # `soy` ya no decide QUE se ve (el expediente se comparte
                    # entero): sirve para la etiqueta de la pantalla.
                    'soy': por_ficha[f.id],
                    'nombre_arrendatario': f.nombre_arrendatario or '',
                    'nombre_residente': f.nombre_residente or '',
                    'documentos': [cargados.get(campo) or _documento_vacio(campo)
                                   for campo, _e, _p, _c in DOCUMENTOS],
                })
            return Response({'fichas': salida}, status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'mis_documentos')

    def subir_documento(self, request):
        """POST /portal/mis_documentos/ -> sube o reemplaza UN documento.

        Subir y reemplazar son la misma operacion: dejar el archivo en su campo.
        BORRAR no existe a proposito (regla del usuario, 2026-08-18): el
        expediente es la prueba de lo que se entrego y el portal no puede
        vaciarlo — eso sigue siendo de la administracion.

        Cualquiera de las dos cuentas de la ficha puede subir cualquier
        documento, la INE de la otra parte incluida: son las dos caras del mismo
        tramite y ya comparten el resto del expediente.

        Misma regla anti-IDOR que en recibos: `ficha_id` solo sirve para elegir
        ENTRE LAS SUYAS; una ajena cae en la primera propia, no en un 404 que
        confirme que existe.
        """
        try:
            campo = (request.data.get('campo') or '').strip()
            if campo not in CAMPOS_DOCUMENTO:
                return Response({'error': 'Ese documento no existe en el expediente.'},
                                status=status.HTTP_400_BAD_REQUEST)

            fichas = fichas_ids_de(request.user)
            if not fichas:
                return Response({'error': 'Tu cuenta no está ligada a ningún registro.'},
                                status=status.HTTP_403_FORBIDDEN)
            pedida = request.data.get('ficha_id')
            try:
                ficha_id = int(pedida) if pedida else fichas[0]
            except (TypeError, ValueError):
                ficha_id = fichas[0]
            if ficha_id not in fichas:
                ficha_id = fichas[0]

            archivo = request.FILES.get('archivo')
            if not archivo:
                return Response({'error': 'Falta el archivo.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if archivo.size > TAMANO_MAX_DOCUMENTO:
                return Response(
                    {'error': f'El archivo pesa más de {TAMANO_MAX_DOCUMENTO // (1024 * 1024)} MB.'},
                    status=status.HTTP_400_BAD_REQUEST)
            if _extension(archivo.name) not in EXTENSIONES_DOCUMENTO:
                return Response({'error': 'Formato no permitido. Sube un PDF o una foto (JPG, PNG).'},
                                status=status.HTTP_400_BAD_REQUEST)

            # Se escribe SIEMPRE en la fila mas reciente de la ficha, que es la
            # que gana el dedup de `mis_documentos`: asi lo que se acaba de subir
            # es lo que se ve. Si la ficha no tiene expediente todavia, se crea.
            expediente = (DocumentosResidentes.objects
                          .filter(residente_id=ficha_id).order_by('-id').first())
            if expediente is None:
                expediente = DocumentosResidentes(residente_id=ficha_id, user=request.user)

            # El archivo anterior NO se borra de S3 aunque cambie de extension:
            # las keys viejas (esquema por nombre de residente) pueden estar
            # COMPARTIDAS entre registros, y borrar una dejaria sin documento a
            # un expediente ajeno. Con el esquema nuevo la key es fija por campo,
            # asi que reemplazar sobrescribe y no queda residuo. El save() ademas
            # mueve `dateTimeOfUpload`, que es el cache-buster de las URLs.
            setattr(expediente, campo, archivo)
            expediente.save()

            return Response({
                'ficha_id': ficha_id,
                'documento': _documento_publico(expediente, campo),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'subir_documento')

    def mis_contratos(self, request):
        """GET /portal/mis_contratos/ -> contratos, firma en curso y renovaciones."""
        try:
            fichas = list(fichas_de(request.user))
            por_ficha = {f.id: soy_en(f, request.user) for f in fichas}
            if not por_ficha:
                return Response({'contratos': [], 'total': 0}, status=status.HTTP_200_OK)

            # Con `?refrescar=1` se le pregunta a ZapSign como van las firmas
            # antes de responder. NO se hace en la carga normal a proposito:
            # ZapSign tarda entre 1 y 10 segundos, y eso serian 10 segundos de
            # pantalla en blanco cada vez. El front pinta primero con lo que hay
            # en la BD y pide el refresco despues (ver mis_contratos.html).
            #
            # Va ANTES de cargar los contratos: el prefetch de mas abajo cachea
            # los firmantes, y conciliar despues devolveria los estados viejos
            # que se acaban de corregir.
            if request.query_params.get('refrescar') == '1':
                conciliar_rondas(FraternaRondaFirma.objects.filter(
                    contrato__residente_id__in=por_ficha.keys(), estado='pendiente',
                ))

            contratos = list(
                FraternaContratos.objects
                .filter(residente_id__in=por_ficha.keys())
                .prefetch_related('rondas_firma__firmantes')
                .order_by('-id')
            )

            # `vigencia_efectiva()` respeta el atributo `rondas_firmadas` si viene
            # puesto (y consulta si no). Se llena aqui desde las rondas ya
            # prefetcheadas, con el mismo orden que espera (-numero), para no
            # disparar una consulta extra por contrato.
            for c in contratos:
                c.rondas_firmadas = sorted(
                    (r for r in c.rondas_firma.all() if r.estado == 'firmado'),
                    key=lambda r: r.numero, reverse=True,
                )

            # De mas vigente a menos: el portal abre en el que le importa hoy.
            contratos.sort(key=_orden_de_vigencia, reverse=True)

            salida = [
                _contrato_publico(c, por_ficha[c.residente_id]) for c in contratos
            ]
            return Response({
                'contratos': salida,
                'vigente_id': salida[0]['contrato_id'] if salida else None,
                'total': len(salida),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'mis_contratos')

    def contrato_pdf(self, request):
        """GET /portal/mi_contrato_pdf/ -> el documento del contrato, para verlo.

        `parte`: 'paquete_1' (default), 'paquete_2' o 'todo'.
        `contrato_id`: solo para elegir entre los suyos; uno ajeno cae al vigente.

        Cada paquete sale de la mejor fuente que haya, en este orden:
          1. El PDF FIRMADO en nuestro S3, si esa ronda ya cerro. Es el documento
             real, con las firmas: siempre gana.
          2. Si no, se arma en vivo con los MISMOS generadores que usa el
             operador para mandar a firmar. Asi el residente ve exactamente lo
             que va a firmar, no una aproximacion.

        En 'todo' cada mitad se resuelve por separado, asi que un contrato con el
        P1 ya firmado y el P2 todavia sin generar sale firmado arriba y en vista
        previa abajo.
        """
        try:
            contrato, error = self._contrato_pedido(request)
            if error:
                return error

            # Solo se sirve lo que este contrato ofrece hoy: con una firma en
            # curso, esa lista trae un unico elemento (el documento en la mesa),
            # asi que pedir 'todo' por URL no puede colar un borrador al lado
            # del documento real.
            disponibles = _partes_disponibles(contrato)
            parte = request.query_params.get('parte')
            if parte not in disponibles:
                parte = disponibles[0]

            partes = [PAQUETE_1, PAQUETE_2] if parte == TODO else [parte]
            pdfs, origenes = [], []
            for p in partes:
                datos, origen = _pdf_de_paquete(contrato, p, request.user)
                if datos:
                    pdfs.append(datos)
                    origenes.append(origen)

            if not pdfs:
                return Response(
                    {'error': 'Ese documento todavía no está disponible.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

            pdf = pdfs[0] if len(pdfs) == 1 else _unir_pdfs(pdfs)
            respuesta = HttpResponse(pdf, content_type='application/pdf')
            # inline: se ve dentro de la pagina, no se descarga.
            respuesta['Content-Disposition'] = (
                f'inline; filename="contrato_{contrato.id}_{parte}.pdf"'
            )
            respuesta['X-Contrato-Id'] = str(contrato.id)
            respuesta['X-Contrato-Parte'] = parte
            # En 'todo' se juntan dos mitades que pueden venir de fuentes
            # distintas (el P1 firmado y el P2 todavia en vista previa). Manda la
            # MENOS definitiva: el aviso no puede prometer mas de lo que hay.
            respuesta['X-Contrato-Origen'] = min(origenes, key=RANGO_ORIGEN.get)
            return respuesta
        except Exception as e:
            return self._fallo(e, 'contrato_pdf')

    def _contrato_pedido(self, request):
        """(contrato, None) o (None, Response de error). Nunca sale de sus fichas."""
        fichas = fichas_ids_de(request.user)
        if not fichas:
            return None, Response({'error': 'Tu cuenta no está ligada a ningún registro.'},
                                  status=status.HTTP_403_FORBIDDEN)
        contratos = list(
            FraternaContratos.objects
            .filter(residente_id__in=fichas)
            .prefetch_related('rondas_firma')
        )
        if not contratos:
            return None, Response({'error': 'No tienes contratos registrados.'},
                                  status=status.HTTP_404_NOT_FOUND)

        pedido = request.query_params.get('contrato_id')
        contrato = None
        if pedido:
            contrato = next((c for c in contratos if str(c.id) == str(pedido)), None)
        return (contrato or max(contratos, key=_orden_de_vigencia)), None


def _mis_contratos(user):
    return (
        FraternaContratos.objects
        .filter(residente_id__in=fichas_ids_de(user))
        .prefetch_related('rondas_firma')
        .order_by('-id')
    )


def contratos_para_select(user):
    """Sus contratos, para que un formulario del portal ofrezca a cual ligarse.

    Sale de sus fichas, nunca de un id del cliente: elegir uno ajeno no es
    una operacion que exista. Lo usan incidencias (a que contrato se refiere
    el reporte) y recibos, que ademas necesita el detalle de `periodos`.
    """
    salida = []
    for c in _mis_contratos(user):
        mensual = renta_mensual(c)
        salida.append({
            'contrato_id': c.id,
            'ficha_id': c.residente_id,
            'departamento': c.no_depa or '',
            'cama': c.cama or '',
            'vigente': (c.estado_contrato or '') == 'actual',
            'renta_mensual': str(mensual) if mensual is not None else '',
            'desde': _fecha(c.fecha_move_in),
            'hasta': _fecha(c.fecha_vigencia),
        })
    return salida


def periodos_para_select(user):
    """Las opciones del selector al subir un recibo: un PERIODO CONTRACTUAL.

    No es la fila del contrato sino cada tramo firmado —"Depto 612 · Cama A ·
    sep 2025 – ago 2026"— porque es lo que el residente reconoce y lo que
    define con que renta se cobra. Cada opcion carga las DOS ligas
    (`contrato_id` y `ronda_id`), asi el recibo queda pegado a su periodo sin
    que el residente tenga que saber que existe una ronda de firma.
    """
    opciones = []
    for c in _mis_contratos(user):
        vigente = (c.estado_contrato or '') == 'actual'
        # Solo lo COBRABLE: un contrato sin ronda firmada no tiene meses a los
        # cuales aplicar el pago, y el POST lo rechaza (regla del usuario,
        # 2026-08-18). Ofrecerlo en el selector seria ofrecer un error.
        for t in tramos(c):
            opciones.append({
                'contrato_id': c.id,
                'ronda_id': t['ronda_id'],
                'ficha_id': c.residente_id,
                'etiqueta': t['etiqueta'],
                'periodo_texto': t['periodo_texto'],
                'tipo': t['tipo'] or 'inicial',
                'fuente': t['fuente'],
                'vigente': vigente,
                'renta_mensual': (str(t['renta_mensual'])
                                  if t['renta_mensual'] is not None else ''),
                'desde': t['desde'].isoformat(),
                'hasta': t['hasta'].isoformat(),
                'meses': len(t['meses']),
            })
    # El periodo mas reciente primero: es el que casi siempre va a pagar.
    opciones.sort(key=lambda o: (o['vigente'], o['desde']), reverse=True)
    return opciones


def contrato_de_los_suyos(user, contrato_id):
    """El contrato `contrato_id` solo si es de una de sus fichas. Si no, None."""
    try:
        cid = int(contrato_id)
    except (TypeError, ValueError):
        return None
    return (
        FraternaContratos.objects
        .filter(id=cid, residente_id__in=fichas_ids_de(user))
        .first()
    )


# --------------------------------------------------------------------------- #
# Recibos de pago — LO UNICO que el residente puede escribir                  #
# --------------------------------------------------------------------------- #

def _quien_subio(r, cuenta_id):
    """(clave, nombre) de quien subio el recibo, en terminos del portal.

    Desde que las dos cuentas de una ficha comparten la lista (ver `_visibles`),
    "no es mio" ya no significa "lo cargo la administracion": puede ser de la otra
    parte del contrato, y la tarjeta tiene que poder decir de quien es.
    """
    if r.user_id and r.user_id == cuenta_id:
        return 'yo', 'Tú'
    ficha = r.residente
    if r.user_id and ficha:
        if r.user_id == ficha.arrendatario_cuenta_id:
            return SOY_ARRENDATARIO, (ficha.nombre_arrendatario or '').strip() or 'El arrendatario'
        if r.user_id == ficha.residente_cuenta_id:
            return SOY_RESIDENTE, (ficha.nombre_residente or '').strip() or 'El residente'
    return 'administracion', 'La administración'


def _recibo_publico(r, cuenta_id):
    """Un recibo visto por el residente. `mio` decide si puede editarlo/borrarlo."""
    mio = r.user_id == cuenta_id
    subido_por, subido_por_nombre = _quien_subio(r, cuenta_id)
    nombre = str(r.archivo).rsplit('/', 1)[-1] if r.archivo else ''
    ext = _extension(nombre)
    return {
        'id': r.id,
        'ficha_id': r.residente_id,
        'contrato_id': r.contrato_id,
        'archivo_url': _url_archivo(r.archivo),
        'nombre_archivo': nombre,
        'extension': ext,
        'es_imagen': ext in EXTENSIONES_IMAGEN,
        'monto': str(r.monto) if r.monto is not None else '',
        # Que se pago y por que medio: lo dice el residente al subirlo. Viajan
        # la clave (para el <select> al editar) y el texto ya resuelto (para
        # pintarlo), asi el front no repite el catalogo.
        'concepto': r.concepto or '',
        'concepto_texto': r.get_concepto_display() if r.concepto else '',
        'metodo_pago': r.metodo_pago or '',
        'metodo_pago_texto': r.get_metodo_pago_display() if r.metodo_pago else '',
        'fecha_pago': _fecha(r.fecha_pago),
        'referencia': r.referencia or '',
        'comentarios': r.comentarios or '',
        # Mes que cubre el comprobante. Lo pone el servidor al subir; el
        # residente no lo elige (ver `periodo_a_imputar`).
        'periodo': _fecha(r.periodo),
        'periodo_texto': nombre_mes(r.periodo),
        # Periodo contractual (ronda firmada) al que pertenece el pago: de ahi
        # salen la renta y la vigencia con las que se cobra ese mes.
        'ronda_id': r.ronda_id,
        # Sello automatico: cuando entro el comprobante al sistema. Lo pone la
        # BD (auto_now_add), no el formulario, asi que no se puede maquillar.
        'fecha_subida': _fecha_hora(r.fecha_subida),
        'aprobado': r.aprobado,
        'fecha_aprobacion': _fecha_hora(r.fecha_aprobacion),
        # Quien lo subio: 'yo' | 'arrendatario' | 'residente' | 'administracion'.
        'lo_subi_yo': mio,
        'subido_por': subido_por,
        'subido_por_nombre': subido_por_nombre,
        # 'aprobado' | 'en_revision': lo que pinta el badge de la tarjeta. Solo
        # lo aprobado por Fraterna baja el adeudo del estado de cuenta.
        'estado': 'aprobado' if r.aprobado else 'en_revision',
        # Un recibo aprobado queda congelado: cambiarle el archivo despues de que
        # Fraterna lo dio por bueno seria cambiar la evidencia de un pago ya
        # validado. El backend lo vuelve a comprobar en cada PATCH/DELETE.
        'puedo_editarlo': not r.aprobado,
    }


class PortalRecibos(viewsets.ViewSet):
    """Recibos de pago del portal: el UNICO punto de escritura que tiene el residente.

    Que puede hacer y que no:
      · VE todos los recibos de sus fichas: los suyos, los de la OTRA parte del
        contrato y los de la administracion (regla del usuario, 2026-08-18, la
        misma que en incidencias). Quien lo subio viaja en `subido_por`.
      · SUBE recibos nuevos. Aporta el ARCHIVO, a que contrato pertenece (y
        solo entre los suyos; uno ajeno cae al que le toca en silencio) y
        QUE pago + POR DONDE (concepto y metodo, obligatorios desde el
        2026-08-18). `residente`, `user`, `ronda` y `periodo` los resuelve el
        servidor, y el `monto` lo captura Fraterna al revisar.
      · NO puede subir nada si no tiene un contrato FIRMADO (409): sin
        mensualidades a las cuales aplicarlo, el comprobante quedaria colgado.
      · EDITA / BORRA cualquiera de su ficha mientras Fraterna no lo apruebe
        (regla del usuario, 2026-08-18): las dos cuentas comparten el tramite,
        igual que en documentos e incidencias. Aprobado = congelado.
      · NUNCA toca `aprobado`, `fecha_aprobacion` ni `aprobado_por`: la revision
        es de Fraterna. No estan en la lista de campos escribibles.
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    # Lo UNICO que el residente escribe: que concepto paga y por que medio
    # (2026-08-18). Son dos catalogos cerrados, no texto libre — se validan
    # contra los choices del modelo en `_limpiar_campos`, asi que aunque el
    # front mande otra cosa no entra.
    #
    # Lo que sigue SIN poder escribir y por que: el `monto` lo captura Fraterna
    # al revisar (es su lectura del documento, no lo que el residente diga que
    # pago); la fecha la sustituye el sello `fecha_subida`, que no se puede
    # maquillar; el mes que cubre lo calcula el servidor en cascada; y
    # referencia/comentarios se quitaron por no usarse. Esas columnas siguen
    # existiendo para el modulo del operador.
    CAMPOS_EDITABLES = ('concepto', 'metodo_pago')

    # Catalogos permitidos, tomados del modelo para que no se puedan separar.
    CONCEPTOS_VALIDOS = {c for c, _ in RecibosPolizaResidente.CONCEPTOS_PAGO}
    METODOS_VALIDOS = {m for m, _ in RecibosPolizaResidente.METODOS_PAGO}

    def _fallo(self, e, donde):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logger.error(
            f"{datetime.now()} Portal recibos ({donde}) fallo en la linea "
            f"{exc_tb.tb_lineno}: {e}"
        )
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _visibles(self, user):
        """Recibos que esta cuenta puede ver: TODOS los de sus fichas.

        Arrendatario y residente de una misma ficha ven los mismos recibos, los
        haya subido cualquiera de los dos o la administracion: es el pago del
        mismo contrato, y esconderle a uno el comprobante del otro solo provoca
        duplicados. Verlo no es poder tocarlo — editar y borrar siguen siendo
        solo lo propio (`_mio_editable`, sin cambios).
        """
        fichas = fichas_ids_de(user)
        if not fichas:
            return RecibosPolizaResidente.objects.none()
        return (
            RecibosPolizaResidente.objects
            .filter(residente_id__in=fichas)
            .select_related('user', 'residente')
            # Por mes cubierto, del mas reciente al mas viejo. `nulls_last`
            # porque los recibos que cargo la administracion no traen periodo
            # y en un DESC de Postgres los NULL se irian hasta arriba.
            .order_by(F('periodo').desc(nulls_last=True), '-fecha_subida')
        )

    def _mio_editable(self, user, pk):
        """El recibo `pk` si se puede tocar. Si no, (None, motivo).

        El candado es la FICHA y la APROBACION, no quien lo subio: arrendatario
        y residente son las dos caras del mismo tramite y ya comparten
        documentos e incidencias. Lo que protege la evidencia es `aprobado`:
        una vez que Fraterna lo dio por bueno, queda congelado para todos.
        """
        recibo = (
            RecibosPolizaResidente.objects
            .filter(pk=pk, residente_id__in=fichas_ids_de(user))
            .first()
        )
        if not recibo:
            return None, 'Ese recibo no existe o no es de tu registro.'
        if recibo.aprobado:
            return None, 'Este recibo ya fue aprobado por la administración y no se puede modificar.'
        return recibo, None

    @staticmethod
    def _limpiar_campos(datos):
        """Lo que el formulario puede escribir: concepto y metodo de pago.

        Unico lugar por el que pasa todo el body, para que agregar un campo
        escribible manana sea una linea aqui y no un `setattr` suelto. Lo que
        llegue y no este declarado se ignora en vez de reventar: el front
        reenvia el payload completo que recibio.

        Los dos son CATALOGOS: un valor fuera de la lista se rechaza (400) en
        vez de guardarse. Guardar basura ahi seria peor que no tener el campo —
        el dia que el concepto decida si el pago baja el adeudo, un valor
        inventado rompe la cuenta en silencio.
        """
        # Un campo que llega VACIO se ignora, no se guarda como vacio: asi un
        # PATCH que reenvia el payload completo no puede borrar un concepto ya
        # capturado. Que sean obligatorios AL DAR DE ALTA se comprueba en
        # `create`, que es donde se sabe que es un recibo nuevo.
        valores = {}
        for campo in PortalRecibos.CAMPOS_EDITABLES:
            limpio = (datos.get(campo) or '').strip()
            if limpio:
                valores[campo] = limpio

        concepto = valores.get('concepto')
        if concepto and concepto not in PortalRecibos.CONCEPTOS_VALIDOS:
            return {}, 'El concepto de pago no es válido.'
        metodo = valores.get('metodo_pago')
        if metodo and metodo not in PortalRecibos.METODOS_VALIDOS:
            return {}, 'El método de pago no es válido.'
        return valores, None

    @staticmethod
    def _validar_archivo(archivo):
        if archivo.size > TAMANO_MAX_RECIBO:
            return f'El archivo pesa más de {TAMANO_MAX_RECIBO // (1024 * 1024)} MB.'
        if _extension(archivo.name) not in EXTENSIONES_RECIBO:
            return 'Formato no permitido. Sube un PDF o una foto (JPG, PNG).'
        return None

    def list(self, request):
        """GET /portal/mis_recibos/"""
        try:
            recibos = [
                _recibo_publico(r, request.user.id) for r in self._visibles(request.user)
            ]
            # Para el selector cuando la cuenta tiene mas de una ficha.
            fichas = [
                {
                    'ficha_id': f.id,
                    'soy': soy_en(f, request.user),
                    'nombre_arrendatario': f.nombre_arrendatario or '',
                    'nombre_residente': f.nombre_residente or '',
                }
                for f in fichas_de(request.user)
            ]
            return Response(
                {
                    'recibos': recibos,
                    'fichas': fichas,
                    # A que PERIODO ligar el pago (contrato + ronda). Sustituyo
                    # al campo libre de 'referencia', que nadie llenaba.
                    'periodos': periodos_para_select(request.user),
                    # Los dos catalogos del formulario, servidos desde el modelo:
                    # agregar un concepto manana es una linea en models.py y no
                    # hay que acordarse de tocar tambien el HTML.
                    'catalogos': {
                        'conceptos': [{'valor': v, 'etiqueta': t}
                                      for v, t in RecibosPolizaResidente.CONCEPTOS_PAGO],
                        'metodos': [{'valor': v, 'etiqueta': t}
                                    for v, t in RecibosPolizaResidente.METODOS_PAGO],
                    },
                    'total': len(recibos),
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return self._fallo(e, 'list')

    def create(self, request):
        """POST /portal/mis_recibos/ — subir un recibo."""
        try:
            fichas = fichas_ids_de(request.user)
            if not fichas:
                return Response(
                    {'error': 'Tu cuenta no está ligada a ningún registro.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # El periodo lo elige el residente en el formulario, pero SOLO
            # entre los suyos: uno ajeno se descarta y cae al que le toca.
            # Del contrato sale tambien la ficha (un contrato pertenece a una),
            # asi que ya no hay dos selects que puedan contradecirse.
            contrato = contrato_de_los_suyos(request.user, request.data.get('contrato_id'))
            if contrato:
                ficha_id = contrato.residente_id
            else:
                pedida = request.data.get('ficha_id')
                try:
                    ficha_id = int(pedida) if pedida else fichas[0]
                except (TypeError, ValueError):
                    ficha_id = fichas[0]
                if ficha_id not in fichas:
                    ficha_id = fichas[0]

            archivo = request.FILES.get('archivo')
            if not archivo:
                return Response({'error': 'Falta el archivo del recibo.'},
                                status=status.HTTP_400_BAD_REQUEST)
            problema = self._validar_archivo(archivo)
            if problema:
                return Response({'error': problema}, status=status.HTTP_400_BAD_REQUEST)

            valores, problema = self._limpiar_campos(request.data)
            if problema:
                return Response({'error': problema}, status=status.HTTP_400_BAD_REQUEST)

            # Concepto y metodo son OBLIGATORIOS al dar de alta (no al editar:
            # un recibo viejo puede no traerlos). Se exigen aqui y no en el
            # modelo porque la columna tiene que seguir aceptando NULL para los
            # recibos que ya existian y para los que carga la administracion.
            for campo, etiqueta in (('concepto', 'concepto de pago'),
                                    ('metodo_pago', 'método de pago')):
                if not valores.get(campo):
                    return Response({'error': f'Elige el {etiqueta}.'},
                                    status=status.HTTP_400_BAD_REQUEST)

            # Sin contrato elegido (o con uno ajeno, que se descarta): el primero
            # COBRABLE de TODAS sus fichas — el que el selector habria puesto
            # hasta arriba. Buscarlo solo en `ficha_id` dejaba fuera al residente
            # cuyo unico contrato firmado cuelga de su otra ficha.
            if contrato is None:
                cobrables = [
                    c for c in FraternaContratos.objects
                    .filter(residente_id__in=fichas).prefetch_related('rondas_firma')
                    if tramos(c)
                ]
                contrato = (max(cobrables, key=_orden_de_vigencia)
                            if cobrables else None)
                if contrato is not None:
                    ficha_id = contrato.residente_id

            # SIN CONTRATO FIRMADO NO SE SUBEN RECIBOS (regla del usuario,
            # 2026-08-18). Antes se aceptaba y el comprobante quedaba colgado:
            # sin mensualidades a las cuales aplicarse, nadie lo revisaba y el
            # residente creia haber pagado. El boton del portal tambien se
            # apaga, pero eso es comodidad — el candado es este.
            if contrato is None or not tramos(contrato):
                return Response(
                    {'error': 'No tienes contratos vigentes donde subir recibos '
                              'de pago. En cuanto tu contrato quede firmado podrás '
                              'subir tus comprobantes.',
                     'motivo': 'sin_contrato_firmado'},
                    status=status.HTTP_409_CONFLICT,
                )

            # La ronda que eligio (el periodo del select), validada contra ESE
            # contrato: una ronda de otro no se acepta ni aunque exista.
            ronda_id = None
            pedida = request.data.get('ronda_id')
            if contrato and pedida:
                try:
                    candidata = int(pedida)
                except (TypeError, ValueError):
                    candidata = None
                if candidata and contrato.rondas_firma.filter(id=candidata).exists():
                    ronda_id = candidata

            # EL COMPROBANTE YA NO GUARDA A QUE MES PERTENECE (2026-08-18).
            # Se intento y sale mal con los abonos: un pago de $1,000 contra una
            # renta de $16,000 marcaba el mes como cubierto y el siguiente
            # comprobante se iba al mes siguiente, dejando el viejo debiendo
            # $15,000 sin que nadie lo reclamara. Ahora el dinero se aplica en
            # cascada, del mes mas viejo al mas nuevo, al calcular el estado de
            # cuenta (utils/calendario_pagos._repartir), asi que un abono parcial
            # deja su mes A MEDIAS y se sigue cobrando.
            #
            # `ronda` si se guarda: es el periodo contractual bajo el que se
            # pago, y de ahi salen la renta y la vigencia.
            recibo = RecibosPolizaResidente.objects.create(
                user=request.user,
                residente_id=ficha_id,
                contrato=contrato,
                ronda_id=ronda_id,
                archivo=archivo,
                **valores,
            )
            return Response(_recibo_publico(recibo, request.user.id),
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            return self._fallo(e, 'create')

    def partial_update(self, request, pk=None):
        """PATCH /portal/mis_recibos/<id>/ — corregir datos o reemplazar el archivo."""
        try:
            recibo, problema = self._mio_editable(request.user, pk)
            if problema:
                return Response({'error': problema}, status=status.HTTP_403_FORBIDDEN)

            valores, problema = self._limpiar_campos(request.data)
            if problema:
                return Response({'error': problema}, status=status.HTTP_400_BAD_REQUEST)
            for campo, valor in valores.items():
                setattr(recibo, campo, valor)

            archivo = request.FILES.get('archivo')
            if archivo:
                problema = self._validar_archivo(archivo)
                if problema:
                    return Response({'error': problema}, status=status.HTTP_400_BAD_REQUEST)
                anterior = str(recibo.archivo) if recibo.archivo else ''
                recibo.archivo = archivo
                recibo.save()
                # El nombre lleva uuid, asi que la key vieja no la referencia
                # nadie mas: se borra para no dejar basura en S3.
                if anterior and anterior != str(recibo.archivo):
                    eliminar_archivo_s3(anterior)
            else:
                recibo.save()

            return Response(_recibo_publico(recibo, request.user.id),
                            status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'partial_update')

    def estado_cuenta(self, request):
        """GET /portal/mi_estado_cuenta/ — cuanto debe, de que meses y que sigue.

        Un bloque por contrato: una ficha puede tener varios (53 tienen dos,
        y hasta cinco en un caso), y cada uno corre su propio calendario.
        Nada de esto vive en una tabla: se calcula al vuelo con la misma
        regla que imprime sus pagares (ver utils/calendario_pagos.py).
        """
        try:
            fichas = fichas_ids_de(request.user)
            if not fichas:
                return Response(
                    {'error': 'Tu cuenta no está ligada a ningún registro.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            recibos = list(self._visibles(request.user))
            por_contrato = {}
            for r in recibos:
                por_contrato.setdefault(r.contrato_id, []).append(r)

            contratos = sorted(_mis_contratos(request.user),
                               key=_orden_de_vigencia, reverse=True)

            bloques = []
            saldo_total = en_revision_total = total_general = Decimal('0')
            for c in contratos:
                # A la cascada solo entran los recibos de renta: un depósito en
                # garantía o una multa no deben "pagar" una mensualidad.
                bloque = estado_de_cuenta(c, [
                    r for r in por_contrato.get(c.id, []) if r.cuenta_para_renta()
                ])
                bloque.update({
                    'ficha_id': c.residente_id,
                    'departamento': c.no_depa or '',
                    'cama': c.cama or '',
                    'vigente': (c.estado_contrato or '') == 'actual',
                    'desde': _fecha(c.fecha_move_in),
                    'hasta': _fecha(c.fecha_vigencia),
                })
                saldo_total += Decimal(bloque['saldo'])
                en_revision_total += Decimal(bloque['saldo_en_revision'])
                total_general += Decimal(bloque.get('total') or '0')
                bloques.append(bloque)

            # Los comprobantes que cargo la administracion sin contrato no caen
            # en ningun calendario. Se declaran para que la pantalla pueda
            # decirlo en vez de dejarlos desaparecer de la cuenta.
            sueltos = len(por_contrato.get(None, []))

            return Response({
                'contratos': bloques,
                'saldo_total': str(saldo_total),
                'saldo_en_revision_total': str(en_revision_total),
                # Lo que costaran sus contratos completos, sumadas todas las
                # mensualidades (no solo las vencidas).
                'total_a_pagar': str(total_general),
                'recibos_sin_contrato': sueltos,
                'aviso': self._aviso(bloques, saldo_total, en_revision_total),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'estado_cuenta')

    @staticmethod
    def _aviso(bloques, saldo, en_revision):
        """El mensaje de arriba de la pantalla, en un solo criterio.

        Se arma en el backend a proposito: el front pinta lo que reciba, y asi
        el dia que cambie la regla no hay dos versiones del mismo texto.
        """
        cobrables = [b for b in bloques if b['hay_calendario']]
        if not cobrables:
            # Ningun contrato firmado: no hay nada que cobrar y decir "estas al
            # corriente" seria afirmar algo que no sabemos.
            return {'tipo': 'sin_calendario',
                    'texto': (bloques[0]['motivo'] if bloques else
                              'Todavía no hay un contrato firmado del que calcular '
                              'tus mensualidades.')}
        pendientes = [b for b in bloques if b['mes_a_pagar']]
        if pendientes:
            b = pendientes[0]
            meses = sum(x['meses_vencidos'] for x in pendientes)
            if meses == 1:
                texto = f"Te falta el recibo de {b['mes_a_pagar_texto'].lower()}."
            else:
                texto = (f"Tienes {meses} mensualidades sin comprobante "
                         f"aprobado, la más antigua es {b['mes_a_pagar_texto'].lower()}.")
            return {'tipo': 'debe', 'texto': texto}
        if en_revision > 0:
            return {'tipo': 'en_revision',
                    'texto': 'Ya subiste tus comprobantes; Fraterna los está revisando.'}
        return {'tipo': 'al_corriente', 'texto': 'Estás al corriente con tus pagos.'}

    def destroy(self, request, pk=None):
        """DELETE /portal/mis_recibos/<id>/"""
        try:
            recibo, problema = self._mio_editable(request.user, pk)
            if problema:
                return Response({'error': problema}, status=status.HTTP_403_FORBIDDEN)
            archivo = str(recibo.archivo) if recibo.archivo else ''
            recibo.delete()
            if archivo:
                eliminar_archivo_s3(archivo)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return self._fallo(e, 'destroy')


# --------------------------------------------------------------------------- #
# Incidencias                                                                 #
# --------------------------------------------------------------------------- #

def _cuentas_de_mis_fichas(user):
    """Ids de las cuentas de TODAS sus fichas: la propia y la de la otra parte.

    Es el universo de visibilidad de incidencias (regla del usuario,
    2026-08-13): arrendatario y residente de la misma ficha VEN las incidencias
    del otro, pero cada quien solo puede modificar las que creo el mismo.
    """
    cuentas = set()
    for f in fichas_de(user):
        if f.arrendatario_cuenta_id:
            cuentas.add(f.arrendatario_cuenta_id)
        if f.residente_cuenta_id:
            cuentas.add(f.residente_cuenta_id)
    return cuentas


def _incidencia_publica(i, cuenta_id):
    """Una incidencia vista desde el portal. `mia` decide si puede editarla."""
    mia = i.user_id == cuenta_id
    return {
        'id': i.id,
        'ficha_id': i.arrendatario_id,
        'contrato_id': i.contrato_id,
        'tipo_incidencia': i.tipo_incidencia or '',
        'incidencia': i.incidencia or '',
        'status': i.status or '',
        'solucion': i.solucion or '',
        # Fecha real de creacion; las incidencias de antes de `creada_en` caen a
        # dateTimeOfUpload, que es lo mas cercano que tienen.
        'creada_en': _fecha(i.creada_en or i.dateTimeOfUpload),
        'actualizada_en': _fecha(i.dateTimeOfUpload),
        'quien': (i.user.first_name or i.user.username) if i.user_id else '',
        'la_cree_yo': mia,
        # Una incidencia ya dictaminada (Aceptado / No Procedente) se congela:
        # editar el reporte despues del dictamen dejaria la solucion respondiendo
        # a un texto que ya no existe.
        'puedo_editarla': mia and (i.status or '') == PortalIncidencias.ESTATUS_INICIAL,
    }


class PortalIncidencias(viewsets.ViewSet):
    """Incidencias del portal del residente.

    Reglas (acordadas con el usuario, 2026-08-13):
      · CREA con tipo + descripcion; queda ligada a SU cuenta (`user`) y a su
        ficha. El contrato es OPCIONAL y solo puede ser uno de sus fichas: un
        contrato ajeno se descarta en silencio (misma politica que el resto del
        portal: los ids del cliente solo eligen entre lo suyo).
      · VE las suyas y las de la otra parte de su ficha (arrendatario <->
        residente se ven entre si).
      · EDITA solo las que creo el mismo, y solo mientras Fraterna no la
        dictamine (status distinto de 'Pendiente de Revisión' la congela).
      · `status`, `solucion` y `prioridad` son de Fraterna: no estan en la lista
        de campos escribibles.
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    ESTATUS_INICIAL = 'Pendiente de Revisión'

    def _fallo(self, e, donde):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logger.error(
            f"{datetime.now()} Portal incidencias ({donde}) fallo en la linea "
            f"{exc_tb.tb_lineno}: {e}"
        )
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _visibles(self, user):
        cuentas = _cuentas_de_mis_fichas(user)
        if not cuentas:
            return IncidenciasFraterna.objects.none()
        return (
            IncidenciasFraterna.objects
            .filter(user_id__in=cuentas)
            .select_related('user')
            .order_by('-id')
        )

    def _contrato_propio(self, user, contrato_id):
        """El contrato pedido SOLO si es de una de sus fichas; si no, None."""
        try:
            cid = int(contrato_id)
        except (TypeError, ValueError):
            return None
        return (
            FraternaContratos.objects
            .filter(id=cid, residente_id__in=fichas_ids_de(user))
            .first()
        )

    def _contratos_para_el_select(self, user):
        """Sus contratos, para que el form ofrezca a cual ligar la incidencia.

        Mismo helper que usan los recibos: una sola definicion de "cuales son
        sus contratos" para los dos formularios del portal.
        """
        return contratos_para_select(user)

    def list(self, request):
        """GET /portal/mis_incidencias/"""
        try:
            incidencias = [
                _incidencia_publica(i, request.user.id)
                for i in self._visibles(request.user)
            ]
            return Response({
                'incidencias': incidencias,
                'contratos': self._contratos_para_el_select(request.user),
                'total': len(incidencias),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'list')

    def create(self, request):
        """POST /portal/mis_incidencias/ — reportar una incidencia."""
        try:
            fichas = fichas_ids_de(request.user)
            if not fichas:
                return Response(
                    {'error': 'Tu cuenta no está ligada a ningún registro.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            descripcion = (request.data.get('incidencia') or '').strip()
            tipo = (request.data.get('tipo_incidencia') or '').strip()[:100]
            if not tipo:
                return Response({'error': 'Falta el tipo de incidencia.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not descripcion:
                return Response({'error': 'Describe la incidencia.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # Contrato opcional; si viene, la ficha de la incidencia es la del
            # contrato (una cuenta puede tener varias fichas).
            contrato = self._contrato_propio(request.user, request.data.get('contrato_id'))
            ficha_id = contrato.residente_id if contrato else fichas[0]

            incidencia = IncidenciasFraterna.objects.create(
                user=request.user,
                arrendatario_id=ficha_id,
                contrato=contrato,
                incidencia=descripcion,
                tipo_incidencia=tipo,
                status=self.ESTATUS_INICIAL,
                prioridad='Media',
            )
            return Response(_incidencia_publica(incidencia, request.user.id),
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            return self._fallo(e, 'create')

    def partial_update(self, request, pk=None):
        """PATCH /portal/mis_incidencias/<id>/ — corregir tipo/descripcion/contrato."""
        try:
            incidencia = self._visibles(request.user).filter(pk=pk).first()
            if not incidencia:
                return Response({'error': 'Esa incidencia no existe o no es tuya.'},
                                status=status.HTTP_403_FORBIDDEN)
            if incidencia.user_id != request.user.id:
                return Response(
                    {'error': 'Solo puedes modificar las incidencias que tú creaste.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if (incidencia.status or '') != self.ESTATUS_INICIAL:
                return Response(
                    {'error': 'Esta incidencia ya fue revisada por la administración '
                              'y no se puede modificar.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if 'tipo_incidencia' in request.data:
                tipo = (request.data.get('tipo_incidencia') or '').strip()[:100]
                if not tipo:
                    return Response({'error': 'Falta el tipo de incidencia.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                incidencia.tipo_incidencia = tipo
            if 'incidencia' in request.data:
                descripcion = (request.data.get('incidencia') or '').strip()
                if not descripcion:
                    return Response({'error': 'Describe la incidencia.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                incidencia.incidencia = descripcion
            if 'contrato_id' in request.data:
                # Mandarlo vacio la desliga; un contrato ajeno tambien cae a None.
                contrato = self._contrato_propio(request.user, request.data.get('contrato_id'))
                incidencia.contrato = contrato
                if contrato:
                    incidencia.arrendatario_id = contrato.residente_id

            incidencia.save()
            return Response(_incidencia_publica(incidencia, request.user.id),
                            status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'partial_update')
