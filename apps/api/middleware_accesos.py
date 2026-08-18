# -*- coding: utf-8 -*-
"""Candado de las cuentas de acceso limitado (campo `accesos`).

Una cuenta con `accesos` puesto solo puede tocar los endpoints de SUS modulos.
Todo lo demas responde 403, aunque el endpoint no sepa nada de este candado.

Por que un middleware y no un permiso por viewset: los endpoints de operador se
escribieron cuando toda cuenta con token era un operador con acceso total, asi
que casi todos se conforman con `IsAuthenticated` y devuelven el universo
entero. Ir viewset por viewset dejaria fuera al que alguien escriba manana; al
invertir la regla —todo cerrado salvo la lista blanca— un endpoint nuevo nace
cerrado para estas cuentas, que es el default correcto. Es el mismo
razonamiento (y la misma forma) que apps/api/middleware_portal.py.

Ojo con el alcance: esto NO cambia nada para las cuentas de siempre. Solo mira
las que tienen `accesos` con valor, que antes de esta feature eran cero.

El front esconde ademas los botones que la cuenta no puede usar (sidebar.js),
pero eso es comodidad: sin este middleware bastaria con teclear la URL de otra
pantalla para operarla entera.
"""
import logging

from django.http import JsonResponse

from .utils.accesos import MODULO_INCIDENCIAS, MODULO_RECIBOS, modulos_de
from .utils.auth_request import usuario_de_la_peticion

logger = logging.getLogger(__name__)

# Metodos permitidos por regla. None = cualquiera.
TODOS = None
LECTURA = ('GET', 'HEAD', 'OPTIONS')

# Lo que necesita CUALQUIER pantalla del front para funcionar: entrar, salir, el
# chequeo de sesion que hace loader.js en cada carga, los ajustes de la propia
# cuenta y la campana de notificaciones (que es personal: cada quien ve las
# suyas).
COMUNES = (
    ('/login_api/', TODOS),
    ('/logout', TODOS),            # cubre /logout/ y /logout_api/
    ('/user_unico/', TODOS),       # el check de sesion de loader.js
    ('/user_info/', TODOS),        # su propio perfil (pantalla de ajustes)
    ('/change_password/', TODOS),
    ('/RecuperarPassword/', TODOS),
    ('/nuevo-password', TODOS),
    ('/notificaciones/', TODOS),   # la campana; crear_comunicado sale por EXCLUSIVAS
)

# Lo que abre cada modulo. Las rutas salen de lo que REALMENTE pide su pantalla
# del front: si manana la pantalla llama a un endpoint nuevo, hay que anadirlo
# aqui o se vera vacia.
MODULOS = {
    # /fraterna/incidencias/ — la bandeja, mas los dos botones de su cabecera
    # ("Reservar Asador" y "Comunicados") y el modal de levantar una incidencia
    # a nombre de un residente, que necesita la lista de contratos para el
    # buscador (solo lectura: desde aqui nadie edita un contrato).
    MODULO_INCIDENCIAS: (
        ('/incidencias_fraterna/', TODOS),
        ('/reservas_asador_fraterna/', TODOS),
        ('/notificaciones/crear_comunicado/', TODOS),
        ('/contratos_fraterna/', LECTURA),
    ),
    # /fraterna/recibos/ — la bandeja de comprobantes: listar, aprobar con monto,
    # desaprobar y borrar.
    MODULO_RECIBOS: (
        ('/recibos_poliza_residente/', TODOS),
    ),
}

# Rutas que cuelgan de un prefijo COMUN pero pertenecen a un modulo. Se revisan
# antes que nada: sin esto, "/notificaciones/" le abriria el envio de
# comunicados masivos a una cuenta que solo revisa recibos.
EXCLUSIVAS = (
    ('/notificaciones/crear_comunicado/', MODULO_INCIDENCIAS),
)


def _metodo_permitido(metodo, metodos):
    return metodos is None or metodo in metodos


def _puede(ruta, metodo, modulos):
    """True si una cuenta con `modulos` puede hacer `metodo` sobre `ruta`."""
    for prefijo, modulo in EXCLUSIVAS:
        if ruta.startswith(prefijo):
            return modulo in modulos

    reglas = list(COMUNES)
    for modulo in modulos:
        reglas.extend(MODULOS.get(modulo, ()))

    return any(
        ruta.startswith(prefijo) and _metodo_permitido(metodo, metodos)
        for prefijo, metodos in reglas
    )


class CandadoAccesoLimitado:
    """Deja a una cuenta con `accesos` dentro de sus modulos y nada mas."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = usuario_de_la_peticion(request)
        modulos = modulos_de(usuario) if usuario is not None else frozenset()

        # Sin `accesos` no hay nada que recortar: la peticion sigue su curso
        # exactamente como antes de esta feature.
        if modulos and not _puede(request.path, request.method, modulos):
            logger.warning(
                "Accesos: la cuenta %s (%s) intento %s %s",
                usuario.username, ','.join(sorted(modulos)), request.method, request.path,
            )
            return JsonResponse(
                {'error': 'Esta sección no está disponible para tu cuenta.'},
                status=403,
            )

        return self.get_response(request)
