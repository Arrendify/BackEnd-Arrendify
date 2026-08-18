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
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta

# Centinela para ordenar recibos sin `fecha_subida` (filas viejas).
_EPOCA = datetime(1970, 1, 1, tzinfo=timezone.utc)

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
        # Donde vive, POR SEPARADO ademas de dentro de `etiqueta`. Sale del
        # snapshot congelado de la ronda, que es lo que dice el documento
        # firmado: la fila del contrato puede venir vacia (una renovacion la
        # edita, y hay contratos capturados antes de asignar depa). Medido en
        # proddev: 318 de 319 rondas firmadas traen depa y cama.
        'no_depa': terminos.no_depa or '',
        'cama': terminos.cama or '',
        # Vigencia REAL del periodo firmado (move-in -> fin), que no es lo mismo
        # que `desde`/`hasta`: esos son el primer y el ultimo MES cobrable (dia
        # 1), y un contrato que arranca el 18 de agosto termina el 18, no el 1.
        'vigencia_desde': terminos.fecha_move_in,
        'vigencia_hasta': terminos.fecha_vigencia,
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


def _repartir(meses, recibos):
    """Aplica lo entregado a las mensualidades, de la MAS VIEJA a la mas nueva.

    Es la regla de cualquier cobranza: el dinero salda primero lo mas atrasado.
    El mes NO viene escrito en el recibo — desde 2026-08-18 ya no se guarda — y
    por eso un abono parcial deja el mes A MEDIAS en vez de darlo por cubierto:
    antes, un comprobante de $1,000 contra una renta de $16,000 marcaba el mes
    como ocupado y el siguiente pago se iba al mes siguiente, con el viejo
    debiendo $15,000 y nadie reclamandolo.

    Van DOS pasadas, no una sola mezclada por fecha, para no perder la distincion
    de las "dos varas" (ver el encabezado del modulo):
      1. lo APROBADO por Fraterna, que es lo unico que pinta un mes de verde;
      2. lo que sigue EN REVISION, que apaga la alerta pero no valida el pago.
    Si se mezclaran, un comprobante sin dictaminar podria quedarse el mes viejo y
    empujar el dinero ya validado al mes siguiente.

    Un comprobante SIN monto capturado se presume que cubre la mensualidad que se
    estaba esperando (regla del usuario, 2026-08-18): consume lo que le falte al
    primer mes sin saldar.

    Devuelve, en el mismo orden que `meses`, un dict por mes con lo aplicado.
    """
    reparto = [{'aprobado': Decimal('0'), 'revision': Decimal('0'),
                'ids': [], 'sin_monto': False} for _ in meses]

    def falta_en(i, hasta_revision):
        """Lo que le falta al mes i, o None si esa mensualidad no trae cifra."""
        monto = meses[i]['monto']
        if monto is None:
            return None
        usado = reparto[i]['aprobado']
        if hasta_revision:
            usado += reparto[i]['revision']
        return max(monto - usado, Decimal('0'))

    def pasada(lista, clave):
        hasta_revision = (clave == 'revision')
        i = 0
        for r in lista:
            # Avanzar al primer mes que todavia deba algo. Los meses sin cifra
            # (falta None) se saltan: no hay contra que repartir.
            while i < len(meses) and falta_en(i, hasta_revision) in (Decimal('0'), None):
                i += 1
            if i >= len(meses):
                break                        # pago adelantado o de mas: saldo a favor

            if r.monto is None:
                reparto[i][clave] += falta_en(i, hasta_revision)
                reparto[i]['ids'].append(r.id)
                reparto[i]['sin_monto'] = True
                continue

            resto = r.monto
            while resto > Decimal('0') and i < len(meses):
                falta = falta_en(i, hasta_revision)
                if falta is None or falta == Decimal('0'):
                    i += 1
                    continue
                toma = min(resto, falta)
                reparto[i][clave] += toma
                if r.id not in reparto[i]['ids']:
                    reparto[i]['ids'].append(r.id)
                resto -= toma
                if toma >= falta:
                    i += 1

    # Orden estable (lo mas viejo primero) para que el mismo comprobante caiga
    # siempre en el mismo mes entre una carga y otra.
    orden = sorted(recibos, key=lambda r: (r.fecha_subida or _EPOCA, r.id))
    pasada([r for r in orden if r.aprobado], 'aprobado')
    pasada([r for r in orden if not r.aprobado], 'revision')
    return reparto


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
            'mes_en_curso': None, 'mes_en_curso_texto': '', 'ronda_en_curso': None,
            'total_meses': 0,
            'fuente': None,
        }

    # El reparto es en cascada sobre TODOS los meses del contrato seguidos (los
    # tramos van en orden), no mes por mes contra el recibo que lo nombre: el
    # recibo ya no guarda mes. Ver `_repartir`.
    planos = [m for t in lista for m in t['meses']]
    reparto = _repartir(planos, recibos)

    periodos, todos, saldo, en_revision_total, vencidos = [], [], Decimal('0'), Decimal('0'), 0
    total_contrato = Decimal('0')
    mes_a_pagar = ronda_a_pagar = None
    mes_en_curso = ronda_en_curso = None
    k = 0

    for t in lista:
        meses_salida = []
        for m in t['meses']:
            aplicado = reparto[k]
            k += 1
            aprobado = aplicado['aprobado']
            en_revision = aplicado['revision']
            monto = m['monto']

            if monto is None:
                # Mensualidad sin cifra (ronda sin renta): no se puede medir.
                cubierto = aprobado > 0 or aplicado['sin_monto']
                entregado = cubierto or bool(aplicado['ids'])
                falta = Decimal('0')
            else:
                cubierto = aprobado >= monto
                entregado = (aprobado + en_revision) >= monto
                falta = max(monto - aprobado, Decimal('0'))

            vencido = m['vence'] <= hoy

            if cubierto:
                estado = PAGADO
            elif aprobado > 0:
                estado = PARCIAL
            elif aplicado['ids']:
                estado = EN_REVISION
            else:
                estado = VENCIDO if vencido else POR_VENCER

            # EL MES QUE ANDA CUBRIENDO: el primero que no esta saldado del todo
            # por Fraterna, este entregado o no. Es lo que contesta "de que mes
            # es este pago" ahora que el recibo no lo guarda, y sigue siendo el
            # mismo mes mientras quede un peso pendiente (el caso del abono
            # parcial que motivo todo esto).
            if mes_en_curso is None and not cubierto:
                mes_en_curso, ronda_en_curso = m['periodo'], t['ronda_id']

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
            if monto is not None:
                total_contrato += monto

            fila = {
                'numero': m['numero'],
                'periodo': m['periodo'].isoformat(),
                'periodo_texto': nombre_mes(m['periodo']),
                'vence': m['vence'].isoformat(),
                'monto': str(monto) if monto is not None else None,
                'pagado': str(aprobado),
                'en_revision': str(en_revision),
                'falta': str(falta),
                'vencido': vencido,
                'estado': estado,
                'ronda_id': t['ronda_id'],
                'recibos': aplicado['ids'],
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
            # Donde vive y vigencia real, del snapshot congelado de la ronda.
            'no_depa': t['no_depa'],
            'cama': t['cama'],
            'vigencia_desde': t['vigencia_desde'].isoformat() if t['vigencia_desde'] else '',
            'vigencia_hasta': t['vigencia_hasta'].isoformat() if t['vigencia_hasta'] else '',
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
        # El mes que ANDA CUBRIENDO: el primero sin saldar del todo, aunque ya
        # haya subido comprobante. `mes_a_pagar` es otra cosa — el primero que
        # ni siquiera tiene comprobante — y es el que dispara la alerta del
        # portal, que no debe regañar a quien ya entrego el suyo.
        'mes_en_curso': mes_en_curso.isoformat() if mes_en_curso else None,
        'mes_en_curso_texto': nombre_mes(mes_en_curso),
        'ronda_en_curso': ronda_en_curso,
        'renta_mensual': (str(ultimo['renta_mensual'])
                          if ultimo['renta_mensual'] is not None else None),
        # Lo que costara el contrato completo: la suma de TODAS sus
        # mensualidades, no solo las vencidas.
        'total': str(total_contrato),
        'total_meses': len(todos),
        'fuente': ultimo['fuente'],
    }
