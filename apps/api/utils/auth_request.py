# -*- coding: utf-8 -*-
"""Resolver el usuario de una peticion desde un middleware.

Los middlewares corren ANTES que la autenticacion de DRF, asi que con un token
`request.user` todavia es AnonymousUser: hay que resolverlo a mano con el mismo
TokenAuthentication que usaran las vistas.

Esto vive aparte porque ya son dos los candados que lo necesitan (el del portal
del residente y el de las cuentas de acceso limitado) y cada uno resolviendolo
por su cuenta significaba DOS consultas por peticion para lo mismo. El resultado
se memoriza en el propio `request`, que muere con la peticion.
"""
from rest_framework.authentication import TokenAuthentication

_MEMORIA = '_usuario_resuelto'


def usuario_de_la_peticion(request):
    """El usuario de la peticion (venga por sesion o por token DRF) o None.

    Un token invalido no es asunto de quien llama: devuelve None y que la vista
    responda su propio 401.
    """
    if hasattr(request, _MEMORIA):
        return getattr(request, _MEMORIA)

    usuario = getattr(request, 'user', None)
    if usuario is not None and usuario.is_authenticated:
        setattr(request, _MEMORIA, usuario)
        return usuario

    try:
        resultado = TokenAuthentication().authenticate(request)
    except Exception:
        resultado = None

    usuario = resultado[0] if resultado else None
    setattr(request, _MEMORIA, usuario)
    return usuario
