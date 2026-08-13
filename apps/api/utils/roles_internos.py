# -*- coding: utf-8 -*-
"""Permisos por equipo interno (accounts_customuser.rol_interno).

Valores:
  'arrendify' -> equipo interno Arrendify: aprueba/desaprueba contratos, edita
                 contratos aprobados y emite/resetea firmas sin candado de estatus.
  'fraterna'  -> operadores del cliente Fraterna: operan con los candados de
                 estatus (solo editan contratos NO aprobados; solo generan
                 enlaces de firma con el contrato Aprobado).
  NULL        -> todos los demas (clientes, residentes, cuentas legacy): mismos
                 candados que 'fraterna'.

El campo se administra SOLO por SQL directo a la BD (ningun serializer lo
escribe) y los guards leen request.user desde la BD — falsificar el payload de
localStorage en el navegador no concede nada.
"""

ROL_INTERNO_ARRENDIFY = 'arrendify'
ROL_INTERNO_FRATERNA = 'fraterna'


def es_operador_arrendify(user):
    """True solo para cuentas autenticadas del equipo interno Arrendify."""
    return (
        bool(getattr(user, 'is_authenticated', False))
        and getattr(user, 'rol_interno', None) == ROL_INTERNO_ARRENDIFY
    )


def puede_ver_credenciales_residente(user):
    """True para quien puede LEER la contrasena generada de un residente Fraterna.

    Portal del residente (2026-08-13): la clave se guarda en claro para que el
    operador se la pueda dictar, asi que leerla queda limitado a los dos equipos
    que operan Fraterna. Todo lo demas (incluido el propio residente) ve 403.
    """
    return (
        bool(getattr(user, 'is_authenticated', False))
        and getattr(user, 'rol_interno', None) in (ROL_INTERNO_ARRENDIFY, ROL_INTERNO_FRATERNA)
    )
