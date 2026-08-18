# -*- coding: utf-8 -*-
"""Calendario de pagos de un contrato Fraterna, calculado al vuelo.

No hay tabla de mensualidades y no hace falta: el calendario se deduce con
EXACTAMENTE la misma regla que imprime los pagares que el arrendatario firmo
(`_generar_pagare_interno` en fraterna_views), asi que el estado de cuenta del
portal no puede contradecir al papel que tiene en la mano. Si un dia cambia la
regla del pagare, cambia aqui tambien: la fuente es una.

    N       = un pago por mes de `duracion`  (_num_pagares_fraterna)
    base    = fecha_move_in
    mes k   = base + k meses
    vence   = el dia del move-in en el primer mes; el `dia_pago` (NULL -> 5) en
              los demas, recortado al ultimo dia real del mes (31 -> 28/29/30)
    monto   = renta + estacionamiento, salvo el primero si va prorrateado
              (`pagare_distinto` = "Si" -> `cantidad_primer_pagare`)

DE DONDE SALEN LOS TERMINOS — un TRAMO por ronda firmada
--------------------------------------------------------
La fila `fraterna_contrato` NO es lo que se firmo: es la copia de trabajo del
SIGUIENTE intento, y una renovacion en curso la edita. Cobrar de ahi significaria
pasarle al residente los meses viejos a la renta nueva. Los terminos de verdad
estan congelados en `FraternaRondaFirma` (4 fechas en columnas + el resto en
`datos_snapshot`), asi que el calendario se arma con **un tramo por ronda
firmada**: la inicial cobra su periodo a su renta, la renovacion el suyo a la
suya. Medido en proddev: los 255 contratos vigentes tienen ronda firmada (255 de
255) y las 318 rondas firmadas traen renta, duracion y move-in completos.

La fila del contrato queda de RESPALDO para los 582 historicos que nunca
firmaron por el sistema. Cada tramo declara su `fuente`: 'ronda' o 'contrato'.

QUE CUENTA COMO PAGADO (decisiones del usuario, 2026-08-18)
------------------------------------------------------------
Dos varas, a proposito:
  · El mes se pinta VERDE ("pagado") solo cuando Fraterna aprueba el
    comprobante. Subir una foto no valida un pago.
  · Pero el SALDO y la ALERTA cuentan lo entregado: un mes con su comprobante
    arriba deja de reclamarse aunque siga en revision — el residente ya hizo su
    parte y no tiene por que seguir leyendo "te falta el recibo de agosto". Lo
    que falta validar viaja aparte en `saldo_en_revision`. Si Fraterna acaba
    rechazando el comprobante (borrandolo), el mes vuelve a aparecer solo.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta

# Estados de un mes del calendario, de mejor a peor.
PAGADO = 'pagado'
PARCIAL = 'parcial'
EN_REVISION = 'en_revision'
VENCIDO = 'vencido'
POR_VENCER = 'por_vencer'

MESES_ES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
            'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
MESES_CORTOS = ('ene', 'feb', 'mar', 'abr', 'may', 'jun',
                'jul', 'ago', 'sep', 'oct', 'nov', 'dic')


def nombre_mes(periodo):
    """date(2026, 9, 1) -> 'Septiembre 2026'."""
    if not periodo:
        return ''
    return f'{MESES_ES[periodo.month - 1].capitalize()} {periodo.year}'


def _mes_corto(f):
    return f'{MESES_CORTOS[f.month - 1]} {f.year}' if f else ''


def _a_decimal(valor):
    """Numero de un campo que puede venir como texto ('8500', '8,500.00') o vacio."""
    if valor is None or valor == '':
        return None
    try:
        return Decimal(str(valor).replace(',', '').replace('$', '').strip())
    except (InvalidOperation, AttributeError, ValueError):
        return None


class Terminos(object):
    """Los terminos con los que se cobra un tramo, vengan de donde vengan.

    Existe para que `_num_pagares_fraterna` y `_dia_pago_fraterna` — que son la
    fuente autoritativa y esperan un objeto con `.duracion` y `.dia_pago` —
    funcionen igual con una ronda que con la fila del contrato, sin duplicar sus
    reglas ni tocarlas.
    """

    __slots__ = ('renta', 'precio_estacionamiento_mxn', 'duracion', 'dia_pago',
                 'pagare_distinto', 'cantidad_primer_pagare', 'fecha_move_in',
                 'fecha_vigencia', 'no_depa', 'cama', 'fuente')

    def __init__(self, **kw):
        for campo in self.__slots__:
            setattr(self, campo, kw.get(campo))


def _terminos_de_ronda(ronda):
    """Terminos congelados de una ronda: snapshot + las 4 fechas en columnas."""
    snap = ronda.datos_snapshot or {}
    if not isinstance(snap, dict):
        snap = {}
    dia = snap.get('dia_pago')
    return Terminos(
        renta=snap.get('renta'),
        precio_estacionamiento_mxn=_a_decimal(snap.get('precio_estacionamiento_mxn')),
        duracion=snap.get('duracion'),
        # El snapshot guarda '' cuando el contrato no tenia dia_pago; que llegue
        # como None para que caiga en el default 5 igual que la fila.
        dia_pago=int(dia) if str(dia or '').strip().isdigit() else None,
        pagare_distinto=snap.get('pagare_distinto'),
        cantidad_primer_pagare=snap.get('cantidad_primer_pagare'),
        fecha_move_in=ronda.fecha_move_in,
        fecha_vigencia=ronda.fecha_vigencia,
        no_depa=snap.get('no_depa'),
        cama=snap.get('cama'),
        fuente='ronda',
    )


def _terminos_de_contrato(contrato):
    """Respaldo: la fila del contrato, para los que nunca firmaron por el sistema."""
    return Terminos(
        renta=contrato.renta,
        precio_estacionamiento_mxn=contrato.precio_estacionamiento_mxn,
        duracion=contrato.duracion,
        dia_pago=contrato.dia_pago,
        pagare_distinto=contrato.pagare_distinto,
        cantidad_primer_pagare=contrato.cantidad_primer_pagare,
        fecha_move_in=contrato.fecha_move_in,
        fecha_vigencia=contrato.fecha_vigencia,
        no_depa=contrato.no_depa,
        cama=contrato.cama,
        fuente='contrato',
    )


def renta_mensual(fuente):
    """Lo que se paga cada mes: renta + estacionamiento (la "renta integral" de
    la clausula Cuarta). Acepta un contrato, una ronda o unos Terminos."""
    if hasattr(fuente, 'datos_snapshot'):
        fuente = _terminos_de_ronda(fuente)
    renta = _a_decimal(getattr(fuente, 'renta', None))
    if renta is None:
        return None
    estacionamiento = getattr(fuente, 'precio_estacionamiento_mxn', None)
    return renta + (estacionamiento or Decimal('0'))


def _meses_de(terminos):
    """Las mensualidades que obligan esos terminos, del primer mes al ultimo."""
    base = terminos.fecha_move_in
    if not base:
        return []
    # Import diferido: `fraterna_views` es la fuente autoritativa de estas dos
    # reglas, pero importarla arriba haria ciclo (ella importa medio proyecto).
    from ..Views.fraterna_views import _dia_pago_fraterna, _num_pagares_fraterna

    total = _num_pagares_fraterna(terminos)
    dia_pago = _dia_pago_fraterna(terminos)
    mensual = renta_mensual(terminos)
    primero = mensual
    if (terminos.pagare_distinto or 'No') == 'Si':
        prorrateo = _a_decimal(terminos.cantidad_primer_pagare)
        if prorrateo is not None:
            primero = prorrateo

    meses = []
    for k in range(total):
        f = base + relativedelta(months=k)
        dia = base.day if k == 0 else min(dia_pago, monthrange(f.year, f.month)[1])
        meses.append({
            'numero': k + 1,
            'periodo': date(f.year, f.month, 1),
            'vence': date(f.year, f.month, dia),
            'monto': primero if k == 0 else mensual,
        })
    return meses


def _rondas_cobrables(contrato):
    """Rondas FIRMADAS del contrato, en orden cronologico.

    Solo las firmadas: una ronda pendiente es un documento en la mesa, todavia
    no obliga a pagar nada, y las canceladas (135 en prod) no obligan nunca.
    """
    rondas = [r for r in contrato.rondas_firma.all()
              if r.estado == 'firmado' and r.fecha_move_in]
    return sorted(rondas, key=lambda r: (r.fecha_move_in, r.numero or 0))


def tramos(contrato):
    """Los periodos contractuales que hay que pagar, del mas viejo al mas nuevo.

    Uno por ronda firmada. Si dos se traslapan (una renovacion firmada antes de
    que se acabara el periodo anterior), el tramo viejo se CORTA donde arranca
    el nuevo: el mes se cobra una vez, con los terminos vigentes ese mes.
    """
    # SIN RONDA FIRMADA NO SE COBRA NADA (regla del usuario, 2026-08-18). La
    # fila del contrato no basta: es la copia de trabajo del siguiente intento y
    # existe desde antes de que nadie firme, asi que cobrar de ahi le pasaria
    # mensualidades a quien todavia no tiene contrato en pie — se vio en
    # pantalla, con una ficha "sin proceso de firma" a la que ya le decia
    # "debes $5,000". No se pierde ningun contrato vivo: los 255 vigentes tienen
    # ronda firmada (255 de 255). Los 582 sin ronda firmada son historicos que
    # se firmaron fuera del sistema y de los que no sabemos que se pacto.
    rondas = _rondas_cobrables(contrato)
    if not rondas:
        return []

    salida = []
    for i, ronda in enumerate(rondas):
        terminos = _terminos_de_ronda(ronda)
        meses = _meses_de(terminos)
        if not meses:
            continue
        if i + 1 < len(rondas):
            corte = rondas[i + 1].fecha_move_in
            meses = [m for m in meses if m['periodo'] < date(corte.year, corte.month, 1)]
        if meses:
            salida.append(_tramo(ronda, terminos, meses))
    return salida


def _tramo(ronda, terminos, meses):
    desde, hasta = meses[0]['periodo'], meses[-1]['periodo']
    lugar = ' · '.join(x for x in (
        f'Depto {terminos.no_depa}' if terminos.no_depa else '',
        f'Cama {terminos.cama}' if terminos.cama else '',
    ) if x)
    periodo_txt = f'{_mes_corto(desde)} – {_mes_corto(hasta)}'
    return {
        'ronda_id': ronda.id if ronda else None,
        'numero': ronda.numero if ronda else None,
        'tipo': (ronda.tipo if ronda else None),
        'fuente': terminos.fuente,
        # Lo que se lee en el selector del formulario: donde vive y que periodo
        # cubre. La ronda no se nombra: al residente no le dice nada.
        'etiqueta': f'{lugar} · {periodo_txt}' if lugar else periodo_txt,
        'periodo_texto': periodo_txt,
        'desde': desde,
        'hasta': hasta,
        'renta_mensual': renta_mensual(terminos),
        'meses': meses,
    }


def mensualidades(contrato):
    """Todas las mensualidades del contrato, de todos sus tramos, en orden."""
    return [m for t in tramos(contrato) for m in t['meses']]


def _cubierto(monto_mes, recibos):
    """(cubierto, aprobado, en_revision, entregado) de un mes.

    Dos varas distintas, a proposito:
      · `cubierto`  -> solo lo APROBADO. Es lo que pinta el mes en verde: el
        pago esta validado por Fraterna.
      · `entregado` -> aprobado + lo que espera revision. Es lo que apaga la
        ALERTA y el saldo (regla del usuario, 2026-08-18): si ya subio el
        comprobante del mes, el residente hizo su parte y no tiene por que
        seguir viendo "te falta el recibo de agosto". Si Fraterna acaba
        rechazandolo, el mes vuelve a aparecer en rojo solo.

    Un recibo SIN monto capturado se toma como que cubre el mes completo: el
    monto es opcional en el formulario y no vamos a dejar debiendo a alguien
    cuyo comprobante existe solo porque no escribio la cifra.
    """
    aprobado = Decimal('0')
    en_revision = Decimal('0')
    aprobado_sin_monto = False
    sin_monto = False
    for r in recibos:
        if r.aprobado:
            if r.monto is None:
                aprobado_sin_monto = True
                sin_monto = True
            else:
                aprobado += r.monto
        elif r.monto is None:
            sin_monto = True
        else:
            en_revision += r.monto

    if monto_mes is None:
        cubierto = aprobado_sin_monto or aprobado > 0
        entregado = cubierto or sin_monto or en_revision > 0
        return cubierto, aprobado, en_revision, entregado

    cubierto = aprobado_sin_monto or aprobado >= monto_mes
    entregado = cubierto or sin_monto or (aprobado + en_revision) >= monto_mes
    if aprobado_sin_monto:
        aprobado = aprobado or monto_mes
    # El residente ya no captura el monto (lo hace Fraterna al revisar), asi que
    # casi todos los comprobantes nuevos llegan sin cifra. Para que la pantalla
    # no diga siempre "en revision: $0" se presume que el comprobante cubre lo
    # que falta de ese mes — es la mensualidad que se estaba esperando. Cuando
    # Fraterna capture el monto real, esta cifra se sustituye por el de verdad.
    if sin_monto and not cubierto:
        en_revision = max(monto_mes - aprobado, Decimal('0'))
    return cubierto, aprobado, en_revision, entregado


def estado_de_cuenta(contrato, recibos, hoy=None):
    """El calendario del contrato con lo pagado encima, tramo por tramo.

    `recibos` son los de ESE contrato (ya filtrados por quien llama). Devuelve
    los periodos con sus meses, el saldo vencido y cual es el mes que toca.
    """
    hoy = hoy or date.today()
    lista = tramos(contrato)
    if not lista:
        if any(r.estado == 'pendiente' for r in contrato.rondas_firma.all()):
            motivo = ('Tu contrato todavía está en proceso de firma. Cuando quede '
                      'firmado aparecerán aquí tus mensualidades.')
        else:
            motivo = ('Todavía no hay un contrato firmado del que calcular tus '
                      'mensualidades.')
        return {
            'contrato_id': contrato.id,
            'hay_calendario': False,
            'motivo': motivo,
            'periodos': [], 'meses': [], 'saldo': '0', 'saldo_en_revision': '0',
            'meses_vencidos': 0, 'mes_a_pagar': None, 'mes_a_pagar_texto': '',
            'ronda_a_pagar': None, 'renta_mensual': None, 'total': '0',
            'total_meses': 0,
            'fuente': None,
        }

    # Un recibo se casa con su mes por (ronda, periodo). Los que traen periodo
    # pero no ronda (subidos antes de esto, o de un contrato sin firma) caen al
    # tramo que cubra ese mes: la clave laxa solo se consulta si la estricta no
    # encontro nada.
    por_ronda, por_periodo = {}, {}
    for r in recibos:
        if not r.periodo:
            continue
        por_ronda.setdefault((r.ronda_id, r.periodo), []).append(r)
        por_periodo.setdefault(r.periodo, []).append(r)

    periodos, todos, saldo, en_revision_total, vencidos = [], [], Decimal('0'), Decimal('0'), 0
    total_contrato = Decimal('0')
    mes_a_pagar = ronda_a_pagar = None

    for t in lista:
        meses_salida = []
        for m in t['meses']:
            del_mes = por_ronda.get((t['ronda_id'], m['periodo']))
            if del_mes is None:
                del_mes = [r for r in por_periodo.get(m['periodo'], []) if r.ronda_id is None]
            cubierto, aprobado, en_revision, entregado = _cubierto(m['monto'], del_mes)
            vencido = m['vence'] <= hoy

            if cubierto:
                estado = PAGADO
            elif aprobado > 0:
                estado = PARCIAL
            elif del_mes:
                estado = EN_REVISION
            else:
                estado = VENCIDO if vencido else POR_VENCER

            falta = Decimal('0')
            if m['monto'] is not None and not cubierto:
                falta = max(Decimal('0'), m['monto'] - aprobado)
            # El saldo y la alerta cuentan lo ENTREGADO, no lo aprobado: un mes
            # con su comprobante arriba deja de reclamarse aunque siga en
            # revision. Lo que aun no valida Fraterna viaja aparte, en
            # `saldo_en_revision`, para que la pantalla lo pueda decir.
            if vencido and not entregado:
                saldo += max(falta - en_revision, Decimal('0'))
                vencidos += 1
                if mes_a_pagar is None:
                    mes_a_pagar, ronda_a_pagar = m['periodo'], t['ronda_id']
            en_revision_total += en_revision
            if m['monto'] is not None:
                total_contrato += m['monto']

            fila = {
                'numero': m['numero'],
                'periodo': m['periodo'].isoformat(),
                'periodo_texto': nombre_mes(m['periodo']),
                'vence': m['vence'].isoformat(),
                'monto': str(m['monto']) if m['monto'] is not None else None,
                'pagado': str(aprobado),
                'falta': str(falta),
                'estado': estado,
                'ronda_id': t['ronda_id'],
                'recibos': [r.id for r in del_mes],
            }
            meses_salida.append(fila)
            todos.append(fila)

        periodos.append({
            'ronda_id': t['ronda_id'],
            'numero': t['numero'],
            'tipo': t['tipo'],
            'fuente': t['fuente'],
            'etiqueta': t['etiqueta'],
            'periodo_texto': t['periodo_texto'],
            'desde': t['desde'].isoformat(),
            'hasta': t['hasta'].isoformat(),
            'renta_mensual': str(t['renta_mensual']) if t['renta_mensual'] is not None else None,
            'meses': meses_salida,
        })

    ultimo = lista[-1]
    return {
        'contrato_id': contrato.id,
        'hay_calendario': True,
        'motivo': None,
        # Un bloque por periodo contractual (ronda). `meses` los trae todos
        # seguidos, para quien solo quiera la lista plana.
        'periodos': periodos,
        'meses': todos,
        # Lo que debe HOY: mensualidades ya vencidas que no estan aprobadas.
        'saldo': str(saldo),
        # Lo que se le descontaria en cuanto Fraterna apruebe lo que ya subio.
        'saldo_en_revision': str(en_revision_total),
        'meses_vencidos': vencidos,
        'mes_a_pagar': mes_a_pagar.isoformat() if mes_a_pagar else None,
        'mes_a_pagar_texto': nombre_mes(mes_a_pagar),
        'ronda_a_pagar': ronda_a_pagar,
        'renta_mensual': (str(ultimo['renta_mensual'])
                          if ultimo['renta_mensual'] is not None else None),
        # Lo que costara el contrato completo: la suma de TODAS sus
        # mensualidades, no solo las vencidas.
        'total': str(total_contrato),
        'total_meses': len(todos),
        'fuente': ultimo['fuente'],
    }


def periodo_a_imputar(contrato, recibos, hoy=None, ronda_id=None):
    """(ronda_id, periodo) al que se aplica un comprobante recien subido.

    El residente NO elige el mes (decision del usuario, 2026-08-18): se toma del
    mes en que sube. Pero tomarlo tal cual rompe el caso mas comun — subir el
    recibo de septiembre el 2 de octubre, porque el dia de pago es el 5 — y
    dejaria septiembre debiendo para siempre y octubre saldado sin haberse
    pagado. Asi que el comprobante se aplica **al mes vencido mas viejo que siga
    sin ningun recibo**, que es como salda cualquier cobranza: primero lo mas
    atrasado. Si no debe nada, cae en el primer mes libre (pago adelantado) y,
    si el calendario ya no da, en el mes en que lo subio.

    `ronda_id` acota la busqueda a ese periodo contractual cuando el formulario
    ya eligio uno; si no viene, se recorren todos los tramos del contrato.
    """
    hoy = hoy or date.today()
    del_mes = date(hoy.year, hoy.month, 1)
    if not contrato:
        return None, del_mes
    lista = tramos(contrato)
    if ronda_id is not None:
        lista = [t for t in lista if t['ronda_id'] == ronda_id] or lista
    if not lista:
        return None, del_mes

    ocupados = {(r.ronda_id, r.periodo) for r in recibos if r.periodo}
    libres = [(t, m) for t in lista for m in t['meses']
              if (t['ronda_id'], m['periodo']) not in ocupados]
    if not libres:
        return lista[-1]['ronda_id'], del_mes
    vencidos = [x for x in libres if x[1]['vence'] <= hoy]
    tramo, mes = (vencidos[0] if vencidos else libres[0])
    return tramo['ronda_id'], mes['periodo']
