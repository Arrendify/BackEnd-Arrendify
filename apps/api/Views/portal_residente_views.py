# -*- coding: utf-8 -*-
"""Portal del residente Fraterna — SOLO LECTURA.

Lo que ve el humano que entra con la cuenta generada por
`utils/acceso_residente.py`: su ficha, sus documentos y sus contratos (con el
proceso de firma, su enlace y sus renovaciones). Nada mas, y nada escribible:
en este archivo no hay POST/PUT/DELETE a proposito.

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
  · Documentos -> tu INE es tuya; el resto del expediente (comprobante de
    domicilio, RFC, ingresos, recomendacion, extras) es del expediente y lo ven
    ambos. OJO con la convencion real de prod: el campo `Ine` es la del
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

from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpResponse
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
from ..middleware_portal import ROL_PORTAL
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
    """Las 3 referencias personales, sin las vacias."""
    crudas = [
        (f.n_ref1, f.p_ref1, f.tel_ref1),
        (f.n_ref2, f.p_ref2, f.tel_ref2),
        (f.n_ref3, f.p_ref3, f.tel_ref3),
    ]
    return [
        {'nombre': n or '', 'parentesco': p or '', 'telefono': str(t) if t else ''}
        for n, p, t in crudas
        if n or p or t
    ]


def _ficha_publica(f, soy):
    """Ficha vista por su dueno: su bloque completo, del otro solo el nombre."""
    datos = {
        'ficha_id': f.id,
        'soy': soy,
        'referencias': _referencias(f),
    }
    if soy in (SOY_ARRENDATARIO, SOY_AMBOS):
        datos['arrendatario'] = _bloque_arrendatario(f)
    else:
        datos['arrendatario'] = {'nombre': f.nombre_arrendatario or ''}
    if soy in (SOY_RESIDENTE, SOY_AMBOS):
        datos['residente'] = _bloque_residente(f)
    else:
        datos['residente'] = {'nombre': f.nombre_residente or ''}
    return datos


# Documentos del expediente. `propio_de` = a quien pertenece el archivo:
#   'arrendatario' / 'residente' -> solo lo ve esa persona
#   None                         -> del expediente, lo ven los dos
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


def _documentos_publicos(expediente, soy):
    """Documentos que esta persona puede ver de este expediente."""
    version = None
    if expediente.dateTimeOfUpload:
        version = int(expediente.dateTimeOfUpload.timestamp())

    salida = []
    for campo, etiqueta, propio_de, campo_comentario in DOCUMENTOS:
        if propio_de and soy != SOY_AMBOS and propio_de != soy:
            continue
        archivo = getattr(expediente, campo, None)
        url = _url_archivo(archivo, version)
        if not url:
            continue
        nombre = str(archivo).rsplit('/', 1)[-1]
        salida.append({
            'campo': campo,
            'etiqueta': etiqueta,
            'nombre_archivo': nombre,
            'url': url,
            # El front decide con esto si pinta un <img> o un <iframe>: adivinar
            # por la URL es fragil cuando lleva cache-buster.
            'extension': _extension(nombre),
            'es_imagen': _extension(nombre) in EXTENSIONES_IMAGEN,
            'comentario': getattr(expediente, campo_comentario, None) or '',
        })
    return salida


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
    """Endpoints de lectura del portal. Solo GET, siempre acotados a request.user."""

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def _fallo(self, e, donde):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logger.error(
            f"{datetime.now()} Portal residente ({donde}) fallo en la linea "
            f"{exc_tb.tb_lineno}: {e}"
        )
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def mi_informacion(self, request):
        """GET /portal/mi_informacion/ -> fichas ligadas a esta cuenta."""
        try:
            fichas = [
                _ficha_publica(f, soy_en(f, request.user))
                for f in fichas_de(request.user)
            ]
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

    def mis_documentos(self, request):
        """GET /portal/mis_documentos/ -> expediente visible por ficha."""
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
                soy = por_ficha[exp.residente_id]
                for doc in _documentos_publicos(exp, soy):
                    acumulado[exp.residente_id].setdefault(doc['campo'], doc)

            salida = []
            for f in fichas:
                salida.append({
                    'ficha_id': f.id,
                    'soy': por_ficha[f.id],
                    'nombre_arrendatario': f.nombre_arrendatario or '',
                    'nombre_residente': f.nombre_residente or '',
                    'documentos': list(acumulado[f.id].values()),
                })
            return Response({'fichas': salida}, status=status.HTTP_200_OK)
        except Exception as e:
            return self._fallo(e, 'mis_documentos')

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


# --------------------------------------------------------------------------- #
# Recibos de pago — LO UNICO que el residente puede escribir                  #
# --------------------------------------------------------------------------- #

def _recibo_publico(r, cuenta_id):
    """Un recibo visto por el residente. `mio` decide si puede editarlo/borrarlo."""
    mio = r.user_id == cuenta_id
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
        'fecha_pago': _fecha(r.fecha_pago),
        'referencia': r.referencia or '',
        'comentarios': r.comentarios or '',
        'fecha_subida': r.fecha_subida.isoformat() if r.fecha_subida else None,
        'aprobado': r.aprobado,
        'fecha_aprobacion': r.fecha_aprobacion.isoformat() if r.fecha_aprobacion else None,
        # Quien lo subio, en terminos del portal: 'yo' o 'la administracion'.
        'lo_subi_yo': mio,
        # Un recibo aprobado queda congelado: cambiarle el archivo despues de que
        # Fraterna lo dio por bueno seria cambiar la evidencia de un pago ya
        # validado. El backend lo vuelve a comprobar en cada PATCH/DELETE.
        'puedo_editarlo': mio and not r.aprobado,
    }


class PortalRecibos(viewsets.ViewSet):
    """Recibos de pago del portal: el UNICO punto de escritura que tiene el residente.

    Que puede hacer y que no:
      · VE los recibos de sus fichas que subio EL, mas los que cargo la
        administracion a esa ficha. Los que subio la OTRA parte del contrato
        (arrendatario vs residente) no los ve — es la misma separacion que en
        documentos.
      · SUBE recibos nuevos. `residente`, `contrato` y `user` los pone el
        servidor desde el token; mandar otra ficha en el body no sirve de nada.
      · EDITA / BORRA solo los suyos y solo mientras no esten aprobados.
      · NUNCA toca `aprobado`, `fecha_aprobacion` ni `aprobado_por`: la revision
        es de Fraterna. No estan en la lista de campos escribibles.
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    # Lo unico que el residente puede escribir de un recibo.
    CAMPOS_EDITABLES = ('monto', 'fecha_pago', 'referencia', 'comentarios')

    def _fallo(self, e, donde):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logger.error(
            f"{datetime.now()} Portal recibos ({donde}) fallo en la linea "
            f"{exc_tb.tb_lineno}: {e}"
        )
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _visibles(self, user):
        """Recibos que esta cuenta puede ver.

        Los suyos, mas los que subio la administracion a sus fichas (`user` es
        una cuenta que NO es del portal, o quedo en NULL). Sin esta segunda
        mitad, un recibo que Fraterna cargue por el residente le seria invisible
        y acabaria subiendo un duplicado.
        """
        fichas = fichas_ids_de(user)
        if not fichas:
            return RecibosPolizaResidente.objects.none()
        de_la_administracion = (
            Q(user__isnull=True) | ~Q(user__rol=ROL_PORTAL)
        )
        return (
            RecibosPolizaResidente.objects
            .filter(residente_id__in=fichas)
            .filter(Q(user=user) | de_la_administracion)
            .select_related('user')
            .order_by('-fecha_pago', '-fecha_subida')
        )

    def _mio_editable(self, user, pk):
        """El recibo `pk` si es suyo Y todavia se puede tocar. Si no, (None, motivo)."""
        recibo = (
            RecibosPolizaResidente.objects
            .filter(pk=pk, residente_id__in=fichas_ids_de(user))
            .first()
        )
        if not recibo:
            return None, 'Ese recibo no existe o no es tuyo.'
        if recibo.user_id != user.id:
            return None, 'Solo puedes modificar los recibos que tú subiste.'
        if recibo.aprobado:
            return None, 'Este recibo ya fue aprobado por la administración y no se puede modificar.'
        return recibo, None

    @staticmethod
    def _limpiar_campos(datos):
        """Normaliza lo que llega del formulario. Devuelve (valores, error)."""
        valores = {}
        monto = (datos.get('monto') or '').strip()
        if monto:
            try:
                valores['monto'] = Decimal(monto.replace(',', '').replace('$', ''))
            except (InvalidOperation, AttributeError):
                return None, 'El monto no es un número válido.'
        fecha_pago = (datos.get('fecha_pago') or '').strip()
        if fecha_pago:
            # Parsear aqui, no dejarselo al save(): Django acepta el string y lo
            # convierte al escribir, pero el objeto en memoria se queda con el
            # str y revienta al serializarlo de vuelta (.isoformat sobre un str).
            fecha = parse_date(fecha_pago)
            if not fecha:
                return None, 'La fecha de pago no es válida (formato AAAA-MM-DD).'
            valores['fecha_pago'] = fecha
        for campo in ('referencia', 'comentarios'):
            if campo in datos:
                valores[campo] = (datos.get(campo) or '').strip()
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
                {'recibos': recibos, 'fichas': fichas, 'total': len(recibos)},
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

            # La ficha llega del formulario solo para elegir ENTRE LAS SUYAS; si
            # manda una ajena (o ninguna) cae en la primera propia.
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

            # El contrato tampoco se acepta del cliente: se toma el vigente de esa
            # ficha (o el mas reciente), para que el recibo quede en su contexto.
            de_la_ficha = FraternaContratos.objects.filter(residente_id=ficha_id)
            contrato = (
                de_la_ficha.filter(estado_contrato='actual').order_by('-id').first()
                or de_la_ficha.order_by('-id').first()
            )

            recibo = RecibosPolizaResidente.objects.create(
                user=request.user,
                residente_id=ficha_id,
                contrato=contrato,
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
        """Sus contratos, para que el form ofrezca a cual ligar la incidencia."""
        contratos = (
            FraternaContratos.objects
            .filter(residente_id__in=fichas_ids_de(user))
            .order_by('-id')
        )
        return [
            {
                'contrato_id': c.id,
                'ficha_id': c.residente_id,
                'departamento': c.no_depa or '',
                'cama': c.cama or '',
                'vigente': (c.estado_contrato or '') == 'actual',
            }
            for c in contratos
        ]

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
