# -*- coding: utf-8 -*-
"""Cuentas de acceso limitado (accounts_customuser.accesos).

Una cuenta normal de operador entra a TODO el sistema: el gating historico es
por `is_staff` / `pertenece_a`, que son de tenant, no de pantalla. Cuando el
cliente pide una cuenta que solo atienda una bandeja (2026-08-18: tres cuentas
de Fraterna, dos solo para Incidencias y una para Incidencias + Recibos) no hay
donde escribirlo.

`accesos` es esa lista blanca, en una columna de texto:

    NULL / ''               -> sin restriccion. Es el caso de las ~1490 cuentas
                               que ya existian: la columna nace nula y nadie
                               cambia de comportamiento.
    'incidencias'           -> solo la bandeja de incidencias.
    'incidencias,recibos'   -> las dos bandejas.

Se administra SOLO por SQL directo, igual que `rol_interno`: ningun serializer
lo escribe, y los candados leen `request.user` de la BD, asi que editar el
localStorage del navegador no concede nada. Se expone READ-ONLY en el payload
del login para que el front pueda esconder lo que la cuenta no puede usar (eso
es cosmetica; el candado de verdad es apps/api/middleware_accesos.py).

Anadir un modulo = una entrada aqui, otra en el middleware y otra en el
sidebar del front. Un valor desconocido no abre nada: si no esta en el mapa de
rutas del middleware, no hay ruta que permita.
"""

MODULO_INCIDENCIAS = 'incidencias'
MODULO_RECIBOS = 'recibos'

MODULOS_CONOCIDOS = (MODULO_INCIDENCIAS, MODULO_RECIBOS)


def modulos_de(user):
    """Los modulos de la cuenta. Conjunto vacio = cuenta SIN restriccion."""
    crudo = (getattr(user, 'accesos', None) or '').strip()
    if not crudo:
        return frozenset()
    return frozenset(p.strip().lower() for p in crudo.split(',') if p.strip())


def tiene_acceso_limitado(user):
    """True si la cuenta esta acotada a una lista de modulos."""
    return bool(modulos_de(user))


def puede_usar(user, modulo):
    """True si la cuenta puede usar `modulo`.

    Las cuentas sin restriccion pueden todo — este helper NO sustituye a los
    permisos que ya existen (is_staff, rol_interno, etc.), solo los recorta.
    """
    modulos = modulos_de(user)
    return (not modulos) or (modulo in modulos)
