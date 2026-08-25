# -*- coding: utf-8 -*-
"""Cargos de Fraterna: lo que se debe y NO es mensualidad.

Multas, servicios, moras, penas, deposito y poliza. La mensualidad la deriva al
vuelo `utils/calendario_pagos` del calendario congelado de la ronda; TODO lo
demas es una fila explicita de `FraternaCargo`, y el estado de cuenta suma dos
bolsas. El motor de renta jamas calcula una mora.

MIENTRAS EL CRON NO EXISTA, ESTA ES LA UNICA VIA DE ALTA. El detector
automatico esta bloqueado por respuestas que Fraterna/Legal todavia no dan (si
el 10% es unico o mensual, y sobre todo la FECHA DE CORTE: sin ella la primera
corrida le pondria mora a medio edificio por pagos que si se hicieron, fuera del
sistema). Aqui `origen` queda siempre en 'staff' y el cargo lo tecleo un humano
que ya miro el caso.

Lo que a proposito NO existe:
  · DELETE -- un cargo se RETIRA (cambio de estado a 'cancelado', con quien,
    cuando y por que). Borrarlo dejaria el historial mintiendo, que es justo lo
    que la tabla evita: el residente pudo haberlo visto en su portal.

El flujo del front es de dos pasos, y no por capricho: `buscar` tiene que ser
barato (se dispara mientras el operador teclea) asi que NO calcula calendarios;
el calendario se arma en `contexto`, ya para un solo contrato elegido.
"""
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ...home.models import FraternaCargo, FraternaContratos, Residentes
from ..utils.calendario_pagos import (
    _mes_corto, bolsa_cargos, estado_de_cuenta, renta_mensual, ronda_cobrable,
    tramos,
)
from .fraterna_views import Unaccent, _puede_revisar_recibos, _sin_acentos

# Tope de fichas que devuelve el buscador. Es un buscador de escritorio: quien
# teclea "garcia" no quiere 200 filas, quiere afinar el termino.
TOPE_BUSQUEDA = 25


def _catalogo_conceptos():
    return [{'valor': v, 'texto': t} for v, t in FraternaCargo.CONCEPTOS]


def _cargo_publico(c):
    return {
        'id': c.id,
        'ronda_id': c.ronda_id,
        'concepto': c.concepto,
        'concepto_texto': c.get_concepto_display(),
        'periodo': c.periodo.isoformat() if c.periodo else '',
        'periodo_texto': _mes_corto(c.periodo) if c.periodo else '',
        'monto': str(c.monto),
        'iva_incluido': c.iva_incluido,
        'estado': c.estado,
        'estado_texto': c.get_estado_display(),
        'origen': c.origen,
        'notas': c.notas or '',
        'creado_por': getattr(c.creado_por, 'username', '') or '',
        'creado_en': c.creado_en.isoformat() if c.creado_en else '',
        'motivo': c.motivo or '',
        'es_cobrable': c.es_cobrable(),
    }


def _lugar_de(ronda, contrato):
    """Depto y cama del SNAPSHOT firmado, con la fila del contrato de respaldo.

    El snapshot es lo que dice el documento; la fila la reescribe una renovacion
    y hay contratos capturados antes de asignar depa.
    """
    snap = (getattr(ronda, 'datos_snapshot', None) or {}) if ronda else {}
    return (snap.get('no_depa') or contrato.no_depa or '',
            snap.get('cama') or contrato.cama or '')


class FraternaCargoViewSet(viewsets.ViewSet):
    """POST /fraterna_cargos/ + GET /fraterna_cargos/buscar/ y /contexto/."""
    permission_classes = [IsAuthenticated]

    def _guardia(self, request):
        """Mismo conjunto que la bandeja de recibos: esto tambien es dinero."""
        if not _puede_revisar_recibos(request.user):
            return Response({'error': 'No tienes permiso para crear cargos.'},
                            status=status.HTTP_403_FORBIDDEN)
        return None

    # --- la pestana "Cargos generados" de la bandeja ------------------------
    def list(self, request):
        """GET /fraterna_cargos/?q= -- todos los cargos, del mas nuevo al viejo.

        El estado que se muestra es el CALCULADO con la misma bolsa del portal
        (`bolsa_cargos`): un cargo cubierto por recibos aprobados no puede decir
        'activo' aqui mientras el residente lo ve pagado alla. Los retirados y
        condonados salen con su etiqueta en vez de esconderse: esta pestana es
        el registro.
        """
        negado = self._guardia(request)
        if negado:
            return negado

        q = _sin_acentos((request.query_params.get('q') or '').strip()).lower()
        cargos = (FraternaCargo.objects
                  .select_related('ronda__contrato__residente', 'creado_por')
                  .order_by('-creado_en', '-id'))

        filas = []
        bolsas = {}          # una bolsa por contrato, no por cargo
        for c in cargos:
            contrato = c.ronda.contrato
            ficha = contrato.residente if contrato else None
            nombre_a = (ficha.nombre_arrendatario or '').strip() if ficha else ''
            nombre_r = (ficha.nombre_residente or '').strip() if ficha else ''
            if q and (q not in _sin_acentos(nombre_a).lower()
                      and q not in _sin_acentos(nombre_r).lower()):
                continue

            calc = None
            if contrato:
                if contrato.id not in bolsas:
                    bolsas[contrato.id] = {
                        f['id']: f
                        for f in bolsa_cargos(
                            contrato, list(contrato.recibos_poliza.all()))['cargos']
                    }
                calc = bolsas[contrato.id].get(c.id)

            fila = _cargo_publico(c)
            depa, cama = _lugar_de(c.ronda, contrato) if contrato else ('', '')
            fila.update({
                'contrato_id': contrato.id if contrato else None,
                'ficha_id': contrato.residente_id if contrato else None,
                'nombre_arrendatario': nombre_a,
                'nombre_residente': nombre_r,
                'depa': depa,
                'cama': cama,
                # 'pendiente'/'en_revision'/'parcial'/'pagado' para los vivos;
                # 'condonado'/'cancelado' del propio estado; 'periodo_cerrado'
                # para un activo cuya ronda ya no esta 'firmado' (se conserva
                # pero no cobra -- la regla del boton Renovar).
                'estado_calculado': (calc['estado'] if calc
                                     else ('periodo_cerrado' if c.estado == 'activo'
                                           else c.estado)),
                'pagado': calc['pagado'] if calc else '0',
                'falta': calc['falta'] if calc else str(c.monto),
                'retirable': c.estado == 'activo',
            })
            filas.append(fila)

        return Response({
            'cargos': filas,
            'total': len(filas),
            # Total SIN el filtro de busqueda, para el contador del chip: una
            # busqueda que deja 0 filas no debe apagar el numero del tab.
            'total_generados': len(cargos),
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='retirar')
    def retirar(self, request, pk=None):
        """POST /fraterna_cargos/<id>/retirar/ -- lo saca de la cuenta SIN borrar.

        `estado` pasa a 'cancelado' con quien, cuando y el motivo si lo dieron.
        El portal y la bolsa lo dejan de contar en ese instante; la fila se
        queda como registro (el residente pudo haberlo visto, y "desaparecio"
        no es una respuesta).
        """
        negado = self._guardia(request)
        if negado:
            return negado
        try:
            cargo = FraternaCargo.objects.get(pk=pk)
        except (FraternaCargo.DoesNotExist, ValueError, TypeError):
            return Response({'error': 'Cargo no encontrado.'},
                            status=status.HTTP_404_NOT_FOUND)
        if cargo.estado != 'activo':
            return Response({'error': 'Este cargo ya está '
                                      f'{cargo.get_estado_display().lower()}.'},
                            status=status.HTTP_409_CONFLICT)
        cargo.estado = 'cancelado'
        cargo.motivo = (request.data.get('motivo') or '').strip() or None
        cargo.cerrado_por = request.user
        cargo.cerrado_en = timezone.now()
        cargo.save(update_fields=['estado', 'motivo', 'cerrado_por', 'cerrado_en'])
        return Response(_cargo_publico(cargo), status=status.HTTP_200_OK)

    # --- paso 1: encontrar a la persona -------------------------------------
    @action(detail=False, methods=['get'], url_path='buscar')
    def buscar(self, request):
        """GET /fraterna_cargos/buscar/?q= -- fichas y sus contratos cobrables.

        Busca por nombre de arrendatario o de residente, insensible a acentos
        (misma receta que la bandeja: unaccent() sobre la columna y el termino
        normalizado del lado Python).

        Devuelve TAMBIEN los contratos a los que no se les puede cargar nada,
        con su motivo. Esconderlos haria que el operador buscara a la persona
        una y otra vez creyendo que no existe, cuando el problema es que su
        contrato nunca se firmo.
        """
        negado = self._guardia(request)
        if negado:
            return negado

        q = (request.query_params.get('q') or '').strip()
        if len(q) < 2:
            return Response({'resultados': [], 'truncado': False,
                             'aviso': 'Escribe al menos 2 letras del nombre.'},
                            status=status.HTTP_200_OK)

        term = _sin_acentos(q)
        fichas = (Residentes.objects
                  .annotate(_na=Unaccent('nombre_arrendatario'),
                            _nr=Unaccent('nombre_residente'))
                  .filter(Q(_na__icontains=term) | Q(_nr__icontains=term))
                  .prefetch_related('residente_contrato__rondas_firma')
                  .order_by('nombre_arrendatario', 'id'))
        total = fichas.count()
        fichas = list(fichas[:TOPE_BUSQUEDA])

        resultados = []
        for f in fichas:
            contratos = []
            for c in f.residente_contrato.all():
                ronda = ronda_cobrable(c)
                depa, cama = _lugar_de(ronda, c)
                contratos.append({
                    'contrato_id': c.id,
                    'depa': depa,
                    'cama': cama,
                    'estado_contrato': c.estado_contrato or '',
                    'ronda_id': ronda.id if ronda else None,
                    'puede_cargar': ronda is not None,
                    # Sin ronda firmada no hay a que colgar el cargo: la FK es
                    # NOT NULL a proposito (el cargo tiene que saber bajo que
                    # terminos nacio) y el calendario tampoco cobraria nada.
                    'motivo': '' if ronda else 'Sin ronda de firma firmada.',
                    'vigencia_desde': (ronda.fecha_move_in.isoformat()
                                       if ronda and ronda.fecha_move_in else ''),
                    'vigencia_hasta': (ronda.fecha_vigencia.isoformat()
                                       if ronda and ronda.fecha_vigencia else ''),
                    'periodo_texto': (
                        '{} - {}'.format(_mes_corto(ronda.fecha_move_in),
                                         _mes_corto(ronda.fecha_vigencia))
                        if ronda and ronda.fecha_move_in and ronda.fecha_vigencia else ''),
                    'tipo_ronda': (ronda.tipo or '') if ronda else '',
                })
            # Primero los cobrables: es lo que el operador viene a hacer.
            contratos.sort(key=lambda x: (not x['puede_cargar'], x['depa'], x['cama']))
            resultados.append({
                'ficha_id': f.id,
                'nombre_arrendatario': (f.nombre_arrendatario or '').strip(),
                'nombre_residente': (f.nombre_residente or '').strip(),
                'contratos': contratos,
            })

        return Response({
            'resultados': resultados,
            'mostrados': len(resultados),
            'total': total,
            # Se declara el corte en vez de truncar en silencio.
            'truncado': total > len(resultados),
        }, status=status.HTTP_200_OK)

    # --- paso 2: el contrato elegido ----------------------------------------
    @action(detail=False, methods=['get'], url_path='contexto')
    def contexto(self, request):
        """GET /fraterna_cargos/contexto/?contrato_id= -- todo para llenar el alta.

        Los meses salen del MISMO calendario que cobra la renta, no de uno
        nuevo: si se liga un cargo a su mensualidad, tiene que ser al mes que el
        residente ve en su estado de cuenta, o las dos pantallas dirian cosas
        distintas.
        """
        negado = self._guardia(request)
        if negado:
            return negado

        try:
            contrato = FraternaContratos.objects.get(
                pk=request.query_params.get('contrato_id'))
        except (FraternaContratos.DoesNotExist, ValueError, TypeError):
            return Response({'error': 'Contrato no encontrado.'},
                            status=status.HTTP_404_NOT_FOUND)

        ronda = ronda_cobrable(contrato)
        if ronda is None:
            return Response({'error': 'Este contrato no tiene una ronda de firma '
                                      'firmada, asi que no hay periodo al cual '
                                      'cargarle nada.',
                             'motivo': 'sin_contrato_firmado'},
                            status=status.HTTP_409_CONFLICT)

        # Los meses salen del ESTADO DE CUENTA, no del calendario pelon: para
        # decidir de que mes es una mora hay que ver cual quedo sin pagar, y eso
        # solo lo sabe la cascada. Se filtra con `cuenta_para_renta` -- el mismo
        # criterio del portal y de la bandeja -- para que las tres pantallas
        # cuenten igual.
        recibos = [x for x in contrato.recibos_poliza.all() if x.cuenta_para_renta()]
        cuenta = estado_de_cuenta(contrato, recibos)
        meses = [{'periodo': m['periodo'],
                  'periodo_texto': m['periodo_texto'],
                  'vence': m['vence'],
                  'monto': m['monto'],
                  'falta': m['falta'],
                  'vencido': m['vencido'],
                  'estado': m['estado']}
                 for m in (cuenta.get('meses') or [])
                 if m['ronda_id'] == ronda.id]

        depa, cama = _lugar_de(ronda, contrato)
        cargos = (FraternaCargo.objects.filter(ronda=ronda)
                  .exclude(estado='cancelado').select_related('creado_por'))

        renta = renta_mensual(ronda)
        return Response({
            'contrato_id': contrato.id,
            'ronda_id': ronda.id,
            'depa': depa,
            'cama': cama,
            'tipo_ronda': ronda.tipo or '',
            'vigencia_desde': (ronda.fecha_move_in.isoformat()
                               if ronda.fecha_move_in else ''),
            'vigencia_hasta': (ronda.fecha_vigencia.isoformat()
                               if ronda.fecha_vigencia else ''),
            'renta_mensual': str(renta) if renta is not None else '',
            'meses': meses,
            # Lo que ya trae encima, para no cobrarle dos veces lo mismo.
            'cargos': [_cargo_publico(x) for x in cargos],
            'catalogos': {'conceptos': _catalogo_conceptos()},
        }, status=status.HTTP_200_OK)

    # --- paso 3: darlo de alta ----------------------------------------------
    def create(self, request):
        """POST /fraterna_cargos/ -- alta manual.

        La RONDA no la manda el cliente: se deduce del contrato con
        `ronda_cobrable`, la misma funcion que ancla los recibos. Que el front
        pudiera elegirla abriria la puerta a colgar un cargo de un periodo ya
        cerrado.
        """
        negado = self._guardia(request)
        if negado:
            return negado

        datos = request.data or {}
        try:
            contrato = FraternaContratos.objects.get(pk=datos.get('contrato_id'))
        except (FraternaContratos.DoesNotExist, ValueError, TypeError):
            return Response({'error': 'Contrato no encontrado.'},
                            status=status.HTTP_404_NOT_FOUND)

        ronda = ronda_cobrable(contrato)
        if ronda is None:
            return Response({'error': 'Este contrato no tiene una ronda de firma firmada.',
                             'motivo': 'sin_contrato_firmado'},
                            status=status.HTTP_409_CONFLICT)

        concepto = (datos.get('concepto') or '').strip()
        if concepto not in dict(FraternaCargo.CONCEPTOS):
            return Response({'error': 'Elige un tipo de cargo valido.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # El monto se RECHAZA, no se corrige: un cargo con la cifra mal es una
        # reclamacion con la cifra mal.
        try:
            monto = Decimal(str(datos.get('monto', '')).replace(',', '').strip())
        except (InvalidOperation, AttributeError):
            return Response({'error': 'Captura un monto valido.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if monto <= 0:
            return Response({'error': 'El monto tiene que ser mayor que cero.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # El mes es OPCIONAL (una multa por ruido no refiere a ninguno), pero si
        # viene tiene que ser un mes real del calendario de ESE periodo: un mes
        # inventado dejaria el cargo colgado de una mensualidad que no existe.
        #
        # Se parsea a `date` ANTES de asignarlo, no se pasa el string. Django lo
        # acepta al escribir pero el objeto en memoria se queda con el texto, y
        # al serializar de vuelta truena con `.isoformat() sobre un str`. Es
        # exactamente el mismo tropiezo que ya costo un rato con `fecha_pago`
        # del recibo.
        crudo = (datos.get('periodo') or '').strip() or None
        periodo = None
        if crudo:
            periodo = parse_date(crudo)
            if periodo is None:
                return Response({'error': 'El mes tiene que venir como AAAA-MM-DD.'},
                                status=status.HTTP_400_BAD_REQUEST)
            tramo = next((t for t in tramos(contrato) if t['ronda_id'] == ronda.id), None)
            validos = {m['periodo'] for m in (tramo['meses'] if tramo else [])}
            if periodo not in validos:
                return Response({'error': 'Ese mes no pertenece al periodo firmado '
                                          'del contrato.'},
                                status=status.HTTP_400_BAD_REQUEST)

        try:
            cargo = FraternaCargo.objects.create(
                ronda=ronda,
                concepto=concepto,
                periodo=periodo,
                monto=monto,
                iva_incluido=bool(datos.get('iva_incluido')),
                estado='activo',
                origen='staff',
                creado_por=request.user,
                notas=(datos.get('notas') or '').strip() or None,
            )
        except IntegrityError:
            # El UNIQUE (ronda, periodo, concepto). Con `periodo` vacio no salta:
            # varias multas sueltas conviven a proposito.
            return Response({'error': 'Ese contrato ya tiene un cargo de ese tipo para '
                                      'ese mes. Revisa los cargos de abajo antes de '
                                      'crear otro.'},
                            status=status.HTTP_409_CONFLICT)

        return Response(_cargo_publico(cargo), status=status.HTTP_201_CREATED)
