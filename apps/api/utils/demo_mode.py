# -*- coding: utf-8 -*-
"""Modo demostraciones (usuarios con rol="Demo").

Un usuario Demo entra al flujo de contratos Fraterna con la tabla completa a la
vista, pero:
  - Los nombres y datos personales de residentes/arrendatarios ajenos se
    enmascaran SERVER-SIDE (la protección real vive aquí, no en el front).
  - Solo puede operar (aprobar, editar, generar documentos, mandar a firma)
    contratos creados por él mismo.
  - Los documentos que genera salen con la marca blanca (Vivenda) en lugar de
    Fraterna, vía variables de contexto que los templates resuelven con
    |default a los valores Fraterna reales (usuarios normales: salida idéntica).
  - Sus solicitudes de firma van a ZapSign en sandbox, a carpeta propia y con
    los correos apuntando al propio usuario demo (nadie real recibe nada).

NOTA 2026-07-22 (decisión del usuario): los puntos 1 y 2 ya no aplican tal
cual — la cuenta demo ahora ve las listas completas y puede editar, aprobar y
descargar en cualquier registro. _guard_demo quedó solo en firmas, renovación
y borrado, y aprobar residentes sigue bloqueado. Las funciones enmascarar_*
de abajo quedaron sin llamadores; se conservan por si se revierte.
"""

ROL_DEMO = "Demo"

# Marca blanca para documentos generados por el usuario demo. Las claves marca_*
# (y representante_fraterna, que los templates ya usaban) alimentan los
# |default de los templates de contrato/pagaré/póliza/comodato/anexos.
# TODO dato aquí es FICTICIO: razón social, personas, direcciones, cuentas.
MARCA_DEMO = {
    'es_demo': True,
    'marca_nombre_corto': 'Vivenda',
    'marca_slug': 'Vivenda',

    # Arrendador (sustituye a Fraterna Administradora de Proyectos)
    'marca_razon_social': 'Vivenda Administradora de Proyectos, S.A. de C.V.',
    'marca_razon_social_mayus': 'VIVENDA ADMINISTRADORA DE PROYECTOS, S.A. DE C.V.',
    'marca_razon_social_l1': 'Vivenda Administradora de Proyectos,',
    'representante_fraterna': 'Mariana Solís Herrera',
    'marca_representante_mayus': 'MARIANA SOLÍS HERRERA',
    'marca_correo_legal': 'legal@vivenda.mx',
    'marca_correo_admin': 'administracion@vivenda.mx',
    'marca_celular_arrendador': '8100000000',
    'marca_domicilio_arrendador': 'Av. Alfonso Reyes 1000, Col. Del Valle, San Pedro Garza García, Nuevo León',
    'marca_declaracion_constitucion': (
        'Es una sociedad mercantil legalmente constituida y existente de conformidad con las '
        'leyes mexicanas vigentes, con plenas facultades para la celebración del presente Contrato.'
    ),

    # Inmueble (sustituye a "U TOWER" y su dirección)
    'marca_nombre_inmueble': 'TORRE VIVENDA',
    'marca_inmueble_caratula': '"TORRE VIVENDA", el cual se encuentra ubicado en Av. Alfonso Reyes 1000, Col. Del Valle, San Pedro Garza García, N.L.',
    'marca_inmueble_poliza': '"TORRE VIVENDA", EL CUAL SE ENCUENTRA UBICADO EN AV. ALFONSO REYES 1000, COL. DEL VALLE, SAN PEDRO GARZA GARCÍA, N.L.',
    'marca_direccion_inmueble_mayus': 'AV. ALFONSO REYES 1000, COL. DEL VALLE, SAN PEDRO GARZA GARCÍA, N.L.',
    'marca_direccion_arrendador_poliza': 'AV. ALFONSO REYES 1000, COL. DEL VALLE, SAN PEDRO GARZA GARCÍA, N.L.',

    # Datos de pago (ficticios)
    'marca_banco': 'BBVA',
    'marca_cuenta_bancaria': '0123456789',
    'marca_clabe': '012580001234567895',

    # Pagaré (beneficiario)
    'marca_beneficiario_pagare': "''VIVENDA ADMINISTRADORA DE PROYECTOS, S.A. DE C.V.'' REPRESENTADA POR MARIANA SOLÍS HERRERA",

    # Póliza jurídica — cliente-arrendador (lado Vivenda)
    'marca_poliza_arrendador': '“VIVENDA ADMINISTRADORA DE PROYECTOS, S.A. de C.V.” REPRESENTADA POR MARIANA SOLÍS HERRERA',
    'marca_poliza_razon_social': '“VIVENDA ADMINISTRADORA DE PROYECTOS, S.A. de C.V.”',

    # Póliza jurídica — PRESTADOR ficticio (sustituye a Arrendify S.A.P.I. y a
    # su apoderado; el representante coincide con el testigo del flujo de firma
    # para que el documento y los firmantes de ZapSign cuadren)
    'marca_prestador_corto': 'Blinda Legal',
    'marca_prestador_razon': 'BLINDA LEGAL, S.A.P.I. DE C.V.',
    'marca_prestador_representante': 'Andrés Palacios Vega',
    'marca_prestador_representante_mayus': 'ANDRÉS PALACIOS VEGA',
    'marca_prestador_domicilio_decl': 'Av. Insurgentes Sur 800, Int. 301, Col. Del Valle, C.P. 03100, Benito Juárez, Ciudad de México.',
    'marca_prestador_direccion': 'Av. Insurgentes Sur 800, Int. 301, Col. Del Valle, C.P. 03100, Benito Juárez, Ciudad de México.',
    'marca_prestador_correo': 'contacto@blindalegal.mx',
    'marca_prestador_oficina': '5550000000',

    # Comodato (sustituye a Patrimonio Torre Verde)
    'marca_comodante': 'Mobiliaria Vivenda, S.A. de C.V.',
    'marca_comodante_mayus': 'MOBILIARIA VIVENDA, S.A. DE C.V.',
    'marca_ubicacion_comodato': 'Torre Vivenda ubicado en la Av. Alfonso Reyes 1000, Col. Del Valle, CP 66220, San Pedro Garza García, Nuevo León, México',
    'marca_domicilio_comodato': 'la Av. Alfonso Reyes 1000, Col. Del Valle, CP 66220, San Pedro Garza García, Nuevo León, México',
    'marca_cuenta_comodato': '012-34567-890-12',
    'marca_clabe_comodato': '012580009876543210',
    'marca_comodato_decl_constitucion': (
        'Que es una sociedad anónima de capital variable debidamente constituida conforme a las '
        'leyes mexicanas, con plenas facultades para la celebración del presente instrumento.'
    ),
    'marca_comodato_decl_denominacion': (
        'Que su denominación social vigente es Mobiliaria Vivenda, S.A. de C.V., conforme a sus '
        'estatutos sociales vigentes.'
    ),
    'marca_comodato_rfc': 'MVI200210AB1',
}

# ZapSign en modo demo: documentos NORMALES (sandbox=False por decisión del
# usuario 2026-07-22: el flujo de firma se ve/comporta idéntico al real;
# consumen créditos ZapSign como cualquier doc). Carpeta propia /DEMOSTRACIONES.
ZAPSIGN_DEMO_SANDBOX = False
ZAPSIGN_DEMO_FOLDER = '/DEMOSTRACIONES'
ZAPSIGN_DEMO_TESTIGO = 'ANDRÉS PALACIOS VEGA'
ZAPSIGN_DEMO_BRAND_NAME = 'Contrato.Pro'
ZAPSIGN_DEMO_TELEFONO = '5500000000'


def es_usuario_demo(user):
    """True solo para usuarios autenticados con rol Demo y sin is_staff."""
    return (
        bool(getattr(user, 'is_authenticated', False))
        and getattr(user, 'rol', '') == ROL_DEMO
        and not getattr(user, 'is_staff', False)
    )


def marca_para(user):
    """Contexto de marca para renders de documentos.

    None para usuarios normales (los templates caen a sus |default Fraterna);
    dict MARCA_DEMO + correo del usuario para cuentas demo.
    """
    if not es_usuario_demo(user):
        return None
    marca = dict(MARCA_DEMO)
    marca['demo_email'] = getattr(user, 'email', '') or 'demostraciones@arrendify.com'
    return marca


def contrato_es_del_usuario(user, contrato):
    return contrato is not None and contrato.user_id == getattr(user, 'id', None)


# Campos PII del residente serializado que se vacían en filas ajenas.
_CAMPOS_RESIDENTE_A_VACIAR = (
    'rfc_arrendatario', 'identificacion_arrendatario', 'no_ide_arrendatario',
    'sexo_arrendatario', 'celular_arrendatario', 'correo_arrendatario',
    'empleo', 'domicilio_empleo', 'direccion_arrendatario', 'curp',
    'estado_civil', 'nacionalidad_arrendatario',
    'identificacion_residente', 'no_ide_residente', 'sexo',
    'fecha_nacimiento', 'edad', 'celular_residente', 'correo_residente',
    'direccion_residente', 'aval', 'nacionalidad_residente',
)


def enmascarar_contrato_serializado(item):
    """Muta un dict serializado de FraternaContratos: vacía la PII de contacto
    e identidad del residente (correos, celulares, RFC, CURP, direcciones,
    archivos). Los NOMBRES y los tokens/estados de firma quedan visibles a
    propósito (decisión del usuario 2026-07-22: la tabla del demo muestra
    arrendatario/residente reales y la columna Firmas carga igual que para
    cualquier admin)."""
    rc = item.get('residente_contrato')
    if isinstance(rc, dict):
        for campo in _CAMPOS_RESIDENTE_A_VACIAR:
            if campo in rc:
                rc[campo] = None
        if 'archivos' in rc:
            rc['archivos'] = []
        if 'user' in rc:
            rc['user'] = None
    return item


def enmascarar_lista_contratos(user, data):
    """Enmascara IN PLACE las filas ajenas de una lista serializada de
    contratos. No-op para usuarios que no son demo."""
    if not es_usuario_demo(user):
        return data
    uid = getattr(user, 'id', None)
    for item in data:
        if item.get('user') != uid:
            enmascarar_contrato_serializado(item)
    return data


def aplicar_demo_a_payload_zapsign(payload, marca):
    """Muta el payload de creación de documento ZapSign para una cuenta demo:
    sandbox, carpeta propia y marca blanca SOLO en los firmantes
    institucionales — firmante 1 (arrendador → Vivenda) y último (testigo →
    ficticio), que llevan el correo/teléfono de prueba de la cuenta demo con
    envío automático apagado (firman desde la UI). El arrendatario y el
    residente van SIN cambios: su correo/celular del expediente y el envío
    normal — quien da la demo elige residentes cuyos datos controla."""
    if not (marca and marca.get('es_demo')):
        return payload

    demo_email = marca.get('demo_email', 'demostraciones@arrendify.com')

    payload['sandbox'] = ZAPSIGN_DEMO_SANDBOX
    payload['folder_path'] = ZAPSIGN_DEMO_FOLDER
    payload['brand_name'] = ZAPSIGN_DEMO_BRAND_NAME

    signers = payload.get('signers') or []
    if signers:
        arrendador = signers[0]
        arrendador['name'] = (
            f"''{marca['marca_razon_social_mayus']}'' "
            f"REPRESENTADA POR {marca['marca_representante_mayus']}"
        )
        arrendador['email'] = demo_email
        arrendador['phone_number'] = ZAPSIGN_DEMO_TELEFONO
        arrendador['send_automatic_email'] = False
        arrendador['send_automatic_whatsapp'] = False
    if len(signers) > 1:
        testigo = signers[-1]
        testigo['name'] = ZAPSIGN_DEMO_TESTIGO
        testigo['email'] = demo_email
        testigo['phone_number'] = ZAPSIGN_DEMO_TELEFONO
        testigo['send_automatic_email'] = False
        testigo['send_automatic_whatsapp'] = False
    return payload
