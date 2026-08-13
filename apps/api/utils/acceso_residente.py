# -*- coding: utf-8 -*-
"""Altas de acceso al portal para residentes Fraterna.

Un registro de `residentes` puede generar hasta DOS cuentas de login, porque
arrendatario y residente son personas distintas en 727 de 846 casos:

    residentes.arrendatario_cuenta  -> quien firma y paga
    residentes.residente_cuenta     -> quien habita

Cuando son la MISMA persona (mismo nombre y mismo correo; 66 casos medidos) los
dos campos apuntan a la MISMA cuenta: no se duplica al humano.

Reglas de correo (decision del usuario, 2026-08-13):
  - El correo NO es unique en `residentes` y no se le pone constraint: 49 grupos
    de correo repetido son legitimos (misma persona con 2 registros / 2 camas).
  - La unicidad se cuida en `accounts_customuser`: si el correo YA pertenece a
    otra cuenta, la cuenta nueva se crea SIN email y NO se le manda credencial
    (llegaria a otra persona). El operador la entrega a mano desde el modal.
  - Ese mismo cuidado evita romper la recuperacion de contrasena: la vista de
    RecuperarPassword hace User.objects.get(email=...) y con correos repetidos
    revienta con MultipleObjectsReturned (bug ya vivo en prod: 57 correos en 121
    cuentas). No le agregamos casos.

Permisos de la cuenta creada: rol='Residente', pertenece_a='Fraterna',
is_staff=False y rol_interno NULL — que es justo el nivel mas restrictivo de
los candados de contrato (no aprueba, no edita aprobados, no emite firmas).
"""
import logging
import re
import smtplib
import unicodedata
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from decouple import config
from django.contrib.auth.hashers import check_password  # noqa: F401  (lo usa el modelo)
from django.utils.crypto import get_random_string

from ...accounts.models import CustomUser
from ...authentication.variables import nuevo_usuario_zoho
from ...home.models import FraternaCredencialAcceso, Residentes

logger = logging.getLogger(__name__)

TIPO_ARRENDATARIO = FraternaCredencialAcceso.TIPO_ARRENDATARIO
TIPO_RESIDENTE = FraternaCredencialAcceso.TIPO_RESIDENTE

# Alfabeto sin caracteres ambiguos al dictar por telefono (nada de l/I/1, O/0).
_ALFABETO_CLAVE = 'abcdefghjkmnpqrstuvwxyz23456789'
_LARGO_MINIMO_SLUG = 4
_MAX_INTENTOS_USERNAME = 50


def _sin_acentos(texto):
    return unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()


def _tokens(nombre):
    """Palabras utiles del nombre: descarta iniciales y particulas de 1 letra."""
    return [t for t in re.split(r'\s+', (nombre or '').strip()) if len(t) > 1]


def base_username(nombre):
    """Primer nombre + primer apellido, normalizado. '' si el nombre no da.

    Heuristica por cantidad de palabras (nombres mexicanos suelen traer dos
    apellidos): con 4+ palabras el apellido paterno es la 3a. Medido sobre los
    846 registros reales: 7.4% de colision, contra 14.8% de tomar las dos
    primeras palabras (que en 'Nadia Janeth Molina Romero' da 'nadiajaneth').
    """
    t = _tokens(nombre)
    if not t:
        return ''
    if len(t) >= 4:
        crudo = t[0] + t[2]
    elif len(t) == 3:
        crudo = t[0] + t[1]
    else:
        crudo = ''.join(t[:2])
    return re.sub(r'[^a-z]', '', _sin_acentos(crudo).lower())


def generar_username(nombre, residente_id):
    """Username libre: 'albertojuarez', luego 'albertojuarez.2', '.3'...

    El '#' que se propuso primero no sirve: el validador de Django solo admite
    letras, digitos y @ . + - _ . Todo en minusculas porque el login es
    case-sensitive y dictar mayusculas garantiza tickets de soporte.
    """
    base = base_username(nombre)
    if len(base) < _LARGO_MINIMO_SLUG:
        # Nombres inservibles ('Papa de Chopin' -> 'papade') o vacios.
        base = 'fraterna{}'.format(residente_id)
    if not CustomUser.objects.filter(username__iexact=base).exists():
        return base
    for n in range(2, _MAX_INTENTOS_USERNAME):
        candidato = '{}.{}'.format(base, n)
        if not CustomUser.objects.filter(username__iexact=candidato).exists():
            return candidato
    # Salida de emergencia: el id del residente + ruido, unico por construccion.
    return '{}.{}{}'.format(base, residente_id, get_random_string(3, 'abcdefghjkmnpqrstuvwxyz'))


def generar_password():
    """Clave dictable: 3 grupos de 4, sin caracteres que se confundan al hablar."""
    return '-'.join(get_random_string(4, _ALFABETO_CLAVE) for _ in range(3))


def correo_disponible(correo):
    """True si ningun usuario tiene ya ese correo (case-insensitive)."""
    correo = (correo or '').strip()
    if not correo:
        return False
    return not CustomUser.objects.filter(email__iexact=correo).exists()


def _nombres_equivalentes(a, b):
    na = ' '.join(_sin_acentos(a or '').lower().split())
    nb = ' '.join(_sin_acentos(b or '').lower().split())
    return bool(na) and na == nb


def es_la_misma_persona(residente):
    """True si arrendatario y residente del registro son el mismo humano.

    Exige nombre equivalente Y correo compatible (el del residente vacio o igual
    al del arrendatario). Con nombre igual pero correos distintos se prefiere
    pecar de conservador y crear dos cuentas: puede ser un junior.
    """
    if not _nombres_equivalentes(residente.nombre_arrendatario, residente.nombre_residente):
        return False
    c_arr = (residente.correo_arrendatario or '').strip().lower()
    c_res = (residente.correo_residente or '').strip().lower()
    return not c_res or c_res == c_arr


def enviar_credenciales(email, username, password):
    """Manda usuario+clave al correo. True si salio; False si SMTP fallo.

    Reusa la plantilla `nuevo_usuario_zoho`, que pinta su primer argumento como
    'Usuario:' — por eso recibe el username y no el correo.
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = 'notificaciones@arrendify.com'
        msg['To'] = email
        msg['Subject'] = 'Tu acceso al portal de Contrato.pro'
        msg.attach(MIMEText(nuevo_usuario_zoho(username, password), 'html'))

        with smtplib.SMTP('mail.arrendify.com', 587) as server:
            server.starttls()
            server.login(config('mine_smtp_u'), config('mine_smtp_pw'))
            server.sendmail(config('mine_smtp_u'), email, msg.as_string())
        return True
    except Exception as e:
        # Que no se caiga el alta del residente porque el SMTP tuvo un mal dia:
        # la credencial queda guardada y el operador la dicta desde el modal.
        logger.error('No se pudo enviar credencial a %s: %s', email, e)
        return False


def crear_cuenta(residente, tipo, operador=None):
    """Crea la cuenta de login de un residente y devuelve (cuenta, credencial).

    No decide a que campo se liga: eso lo hace `asegurar_accesos`.
    """
    if tipo == TIPO_ARRENDATARIO:
        nombre = residente.nombre_arrendatario
        correo = (residente.correo_arrendatario or '').strip()
    else:
        nombre = residente.nombre_residente
        correo = (residente.correo_residente or '').strip()

    username = generar_username(nombre, residente.id)
    password = generar_password()
    # Correo ocupado por otra cuenta -> la cuenta nace sin email (ver docstring).
    email = correo if correo_disponible(correo) else ''

    cuenta = CustomUser.objects.create(
        username=username,
        email=email,
        first_name=(nombre or '').strip()[:150],
        rol='Residente',
        pertenece_a='Fraterna',
        is_staff=False,
        is_active=True,
    )
    cuenta.set_password(password)
    cuenta.save(update_fields=['password'])

    enviada = bool(email) and enviar_credenciales(email, username, password)

    credencial = FraternaCredencialAcceso.objects.create(
        cuenta=cuenta,
        residente=residente,
        tipo=tipo,
        password_generada=password,
        generada_por=operador if getattr(operador, 'is_authenticated', False) else None,
        enviada_por_correo=enviada,
    )
    return cuenta, credencial


def asegurar_accesos(residente, operador=None):
    """Crea las cuentas que le falten al registro. Idempotente.

    Devuelve un resumen para que la view lo pueda reportar sin volver a leer.
    """
    # `pendientes_envio` lista los tipos cuya credencial NO salio por correo: el
    # front los usa para avisar al operador que le toca entregarlas a mano.
    resumen = {'arrendatario': None, 'residente': None, 'misma_persona': False,
               'creadas': 0, 'pendientes_envio': []}
    campos = []

    if not residente.arrendatario_cuenta_id and _tokens(residente.nombre_arrendatario):
        cuenta, credencial = crear_cuenta(residente, TIPO_ARRENDATARIO, operador)
        residente.arrendatario_cuenta = cuenta
        campos.append('arrendatario_cuenta')
        resumen['creadas'] += 1
        if not credencial.enviada_por_correo:
            resumen['pendientes_envio'].append(TIPO_ARRENDATARIO)
    resumen['arrendatario'] = residente.arrendatario_cuenta

    if not residente.residente_cuenta_id:
        if es_la_misma_persona(residente) and residente.arrendatario_cuenta_id:
            # Mismo humano: los dos FK apuntan a la misma cuenta.
            residente.residente_cuenta_id = residente.arrendatario_cuenta_id
            campos.append('residente_cuenta')
            resumen['misma_persona'] = True
        elif _tokens(residente.nombre_residente):
            cuenta, credencial = crear_cuenta(residente, TIPO_RESIDENTE, operador)
            residente.residente_cuenta = cuenta
            campos.append('residente_cuenta')
            resumen['creadas'] += 1
            if not credencial.enviada_por_correo:
                resumen['pendientes_envio'].append(TIPO_RESIDENTE)
    resumen['residente'] = residente.residente_cuenta

    if campos:
        residente.save(update_fields=campos)
    return resumen


def regenerar_credencial(cuenta, operador=None):
    """Nueva clave para una cuenta ya creada. Devuelve (password, enviada)."""
    credencial = FraternaCredencialAcceso.objects.filter(cuenta=cuenta).first()
    if credencial is None:
        return None, False

    password = generar_password()
    cuenta.set_password(password)
    cuenta.save(update_fields=['password'])

    enviada = bool(cuenta.email) and enviar_credenciales(cuenta.email, cuenta.username, password)

    credencial.password_generada = password
    credencial.generada_por = operador if getattr(operador, 'is_authenticated', False) else None
    credencial.enviada_por_correo = enviada
    credencial.save(update_fields=['password_generada', 'generada_por', 'enviada_por_correo', 'generada_en'])
    return password, enviada
