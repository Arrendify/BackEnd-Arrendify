# -*- coding: utf-8 -*-
"""Candado de las cuentas del portal del residente.

Una cuenta de residente SOLO existe dentro de /portal/. Fuera de ahi recibe 403,
aunque el endpoint en cuestion no sepa nada del portal.

Por que un middleware y no un permiso por viewset: los endpoints de operador se
escribieron cuando el unico humano con cuenta era un operador, asi que casi
todos se conforman con `IsAuthenticated` y devuelven el universo entero. Medido
con un token de residente antes de poner esto:

    GET /documentos_residentes/  -> 200 con 841 expedientes (INEs, constancias
                                    fiscales y comprobantes de TODAS las personas)
    GET /incidencias_fraterna/   -> 200 con las incidencias de todos
    GET /departamentos_fraterna/ -> 200 con el inventario completo

Ir viewset por viewset dejaria fuera al que alguien escriba mañana. Al invertir
la regla —todo cerrado salvo la lista blanca de abajo— un endpoint nuevo nace
cerrado para el residente, que es el default correcto.

Ojo: esto NO cambia nada para operadores, clientes ni cuentas legacy; solo mira
las cuentas con rol 'Residente', que antes de esta feature no existian (0 en
prod). Las paginas HTML las sirve el otro Django (el front): ahi el guard es de
UX, la seguridad de verdad es esta, porque aqui vive el dato.
"""
import logging

from django.http import JsonResponse
from rest_framework.authentication import TokenAuthentication

logger = logging.getLogger(__name__)

ROL_PORTAL = 'Residente'

# Lo unico que una cuenta de portal puede tocar. Prefijos, comparados sobre la
# ruta completa. Todo lo demas responde 403.
RUTAS_PERMITIDAS = (
    '/portal/',            # sus tres pantallas
    '/login_api/',         # entrar
    '/logout',             # salir
    '/user_unico/',        # el check de sesion que hace loader.js en cada pagina
    '/user_info/',         # su propio perfil (pantalla de ajustes)
    '/change_password/',   # cambiar su clave: es lo que espera fue_cambiada()
    '/RecuperarPassword/', # recuperar contrasena
    '/nuevo-password',     # cambiarla
    '/admin/',             # Django admin trae su propio candado (is_staff)
)


class CandadoPortalResidente:
    """Deja a las cuentas de residente dentro de /portal/ y nada mas."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = self._usuario(request)
        if usuario is not None and getattr(usuario, 'rol', None) == ROL_PORTAL:
            ruta = request.path
            if not ruta.startswith(RUTAS_PERMITIDAS):
                logger.warning(
                    "Portal: la cuenta %s (residente) intento %s %s",
                    usuario.username, request.method, ruta,
                )
                return JsonResponse(
                    {'error': 'Esta sección no está disponible para tu cuenta.'},
                    status=403,
                )
        return self.get_response(request)

    @staticmethod
    def _usuario(request):
        """El usuario de la peticion, venga por sesion o por token DRF.

        El middleware corre antes que la autenticacion de DRF, asi que con un
        token `request.user` todavia es AnonymousUser: hay que resolverlo a mano
        con el mismo TokenAuthentication que usaran las vistas (una consulta por
        PK indexada). Un token invalido no es asunto de este candado — deja
        pasar y que la vista responda su 401.
        """
        usuario = getattr(request, 'user', None)
        if usuario is not None and usuario.is_authenticated:
            return usuario
        try:
            resultado = TokenAuthentication().authenticate(request)
        except Exception:
            return None
        return resultado[0] if resultado else None
