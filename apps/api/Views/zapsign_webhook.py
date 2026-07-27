"""Webhook receptor de eventos de ZapSign.

Recibe los eventos de ZapSign (push) y persiste el estado de firma de cada
paquete en `FraternaContratos`:
  - `token`           (Paquete 1) -> campo `estado_firma_paquete_1`
  - `token_paquete_2` (Paquete 2) -> campo `estado_firma_paquete_2`

El emparejamiento es por `token` del documento: ZapSign manda el mismo
`external_id` (= id del contrato) para ambos paquetes, asi que el token es lo
unico que distingue P1 de P2. El `status` del documento se guarda tal cual
("pending" -> "signed" / "refused").

La cuenta de ZapSign es compartida con otros tenants (Garza Sada, generico,
etc.); los eventos cuyos tokens no correspondan a un contrato Fraterna
simplemente se registran en el log y se ignoran.

Se sigue registrando el payload crudo para poder verificar el esquema real de
ZapSign ante cualquier cambio.

Ademas de FraternaContratos, cada evento se espeja en la bitacora de rondas de
firma (`fraterna_ronda_firma` / `fraterna_ronda_firmante`): estado del doc por
paquete, estado por firmante (la verdad se relee con GET docs/{token}/, el
evento solo dispara) y el PDF firmado se baja a NUESTRO S3.

CIERRE OPERATIVO (partes): la ronda se cierra 'firmado' cuando las PARTES
(arrendatario + residente) de AMBOS paquetes firman. Los finales (arrendador
Fraterna / prestador Jonathan) NO gatean: en prod practicamente nunca firman
al momento (auditoria 2026-07-16: 0/60 docs recientes con esas firmas), asi
que esperar el 'signed' a nivel documento dejaria la bitacora y el rail
inertes. El cierre dispara el rail estado_contrato/cama (misma logica que el
camino legacy doc-level, extraida a `_activar_vigencia`); las firmas de los
finales se registran despues en el espejo (una ronda 'firmado' se sigue
refrescando) y se cobran desde el "Historial de firmas" del FE. Todo el bloque
de rondas es best-effort: nunca altera la respuesta 200 ni el rail legacy del
contrato. Ver handoff "Fraterna - Renovacion de contratos + bitacora de rondas
de firma - 2026-07-07".

Registrar en ZapSign la URL:  https://<dominio-backend>/zapsign-webhook/
"""
import json
import logging
import threading
import time

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connections, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from core.settings import API_TOKEN_ZAPSIGN, API_URL_ZAPSIGN

from ...home.models import FraternaContratos, FraternaRondaFirma

logger = logging.getLogger(__name__)

# =============================================================================
# Bitacora de rondas de firma (fraterna_ronda_firma / fraterna_ronda_firmante).
# El webhook es dueno del "momento 2" del ledger: espejar el estado de firma
# por paquete y por firmante, bajar el PDF firmado a nuestro S3 y cerrar la
# ronda cuando las PARTES de ambos paquetes firman (los finales no gatean),
# disparando el rail estado_contrato/cama. El alta de rondas es de
# "Generar Paquete 1/2" y la cancelacion del boton de reset; aqui NO se crean
# ni se cancelan rondas.
# =============================================================================

# Prefijo en el bucket real (arrendifystorage, via default_storage) donde se
# guardan los PDF firmados de cada ronda: {prefijo}/ronda_{id}_paquete_{N}.pdf
# (la key lleva la PK de la ronda -> 1 ronda = 1 objeto propio, sin pisarse).
S3_PREFIX_RONDAS = 'fraterna/rondas'

# status de un signer de ZapSign -> estado del espejo local (fraterna_ronda_firmante).
ESTADOS_FIRMANTE_ZAPSIGN = {
    'signed': 'firmado',
    'refused': 'rechazado',
    'rejected': 'rechazado',
}

# Roles que firman al final y NO gatean el cierre de la ronda (espejo de
# Contratos_fraterna.ROLES_FINALES): arrendador = Fraterna, prestador = Jonathan.
ROLES_FINALES = ('arrendador', 'prestador')


def _consultar_doc_zapsign(doc_token):
    """GET docs/{token}/ a ZapSign (la fuente de verdad). None si falla."""
    try:
        url = f'{API_URL_ZAPSIGN}docs/{doc_token}/'
        headers = {'Authorization': f'Bearer {API_TOKEN_ZAPSIGN}'}
        respuesta = requests.get(url, headers=headers, timeout=10)
        if respuesta.status_code != 200:
            logger.warning(
                "[ZapSign webhook] GET doc %s respondio %s",
                doc_token, respuesta.status_code,
            )
            return None
        return respuesta.json()
    except Exception as e:
        logger.warning("[ZapSign webhook] GET doc %s fallo: %s", doc_token, e)
        return None


def _fecha_firma(signer):
    """`signed_at` del signer de ZapSign -> datetime aware (o None)."""
    try:
        fecha = parse_datetime(signer.get('signed_at') or '')
        if fecha is not None and timezone.is_naive(fecha):
            fecha = timezone.make_aware(fecha)
        return fecha
    except Exception:
        return None


def _sync_firmantes(ronda, paquete, signers):
    """Alinea estado/firmado_en de los firmantes del paquete con `signers[]`.

    Empareja por token de firmante y, como respaldo, por nombre (el email puede
    repetirse entre firmantes). Solo toca estado y fecha: nombre/rol/sign_url
    quedan como se capturaron al generar el paquete.
    """
    if not signers:
        return
    locales = list(ronda.firmantes.filter(paquete=paquete))
    por_token = {f.token_firmante: f for f in locales if f.token_firmante}
    por_nombre = {f.nombre: f for f in locales}
    for s in signers:
        firmante = (por_token.get(s.get('token'))
                    or por_nombre.get((s.get('name') or '')[:200]))
        if firmante is None:
            logger.warning(
                "[ZapSign webhook] signer %s sin espejo en ronda %s P%s",
                s.get('token') or s.get('name'), ronda.pk, paquete,
            )
            continue
        estado = ESTADOS_FIRMANTE_ZAPSIGN.get((s.get('status') or '').lower(), 'pendiente')
        firmado_en = firmante.firmado_en
        if estado == 'firmado':
            firmado_en = _fecha_firma(s) or firmado_en or timezone.now()
        elif estado == 'pendiente':
            firmado_en = None
        if estado != firmante.estado or firmado_en != firmante.firmado_en:
            firmante.estado = estado
            firmante.firmado_en = firmado_en
            firmante.save(update_fields=['estado', 'firmado_en'])


def _descargar_pdf_firmado(ronda_id, paquete, doc_token, intentos=6, espera=20):
    """Baja el `signed_file` de ZapSign y lo sube a NUESTRO S3 (pdf_firmado_N).

    Corre en un hilo daemon: el signed_file tarda unos segundos en generarse
    tras el evento 'signed', asi que se reintenta con pausa. Si se agotan los
    intentos solo queda el log; cualquier evento posterior del doc lo vuelve a
    intentar (el campo sigue vacio).
    """
    campo = f'pdf_firmado_{paquete}'
    try:
        for intento in range(1, intentos + 1):
            if intento > 1:
                time.sleep(espera)
            doc = _consultar_doc_zapsign(doc_token)
            url_pdf = (doc or {}).get('signed_file')
            if not url_pdf:
                continue
            try:
                respuesta = requests.get(url_pdf, timeout=60)
                if respuesta.status_code != 200 or not respuesta.content:
                    continue
                key = default_storage.save(
                    f'{S3_PREFIX_RONDAS}/ronda_{ronda_id}_paquete_{paquete}.pdf',
                    ContentFile(respuesta.content),
                )
                FraternaRondaFirma.objects.filter(pk=ronda_id).update(**{campo: key})
                logger.warning(
                    "[ZapSign webhook] ronda %s %s guardado en S3: %s",
                    ronda_id, campo, key,
                )
                return
            except Exception as e:
                logger.warning(
                    "[ZapSign webhook] intento %s de bajar PDF (ronda %s P%s): %s",
                    intento, ronda_id, paquete, e,
                )
        logger.error(
            "[ZapSign webhook] agotados %s intentos de bajar el PDF firmado "
            "(ronda %s P%s, token %s)", intentos, ronda_id, paquete, doc_token,
        )
    finally:
        # El hilo abre su propia conexion a la BD; cerrarla al salir.
        connections.close_all()


def _partes_paquete_completas(firmantes, paquete):
    """True si el paquete tiene espejo de "partes" y TODAS ya firmaron.

    Las partes son todo firmante que NO es final (arrendador/prestador); un rol
    desconocido cuenta como parte (conservador: debe firmar para cerrar). Un
    'rechazado' NO es 'firmado', asi que tambien bloquea el cierre.
    """
    partes = [f for f in firmantes
              if f.paquete == paquete and (f.rol or '') not in ROLES_FINALES]
    return bool(partes) and all(f.estado == 'firmado' for f in partes)


def _activar_vigencia(contrato):
    """Rail estado_contrato/cama: expira el 'actual' previo de ESA cama y activa
    este contrato, ocupando la cama del inventario. El orden expirar->activar
    importa (UniqueConstraint parcial inmediato/no-diferible). Idempotente: sin
    cama_ref o ya 'actual' no hace nada. NO toca la liberacion de otras camas.
    Devuelve True si activo el contrato en esta llamada.
    """
    if (contrato is None or not contrato.cama_ref_id
            or contrato.estado_contrato == 'actual'):
        return False
    with transaction.atomic():
        FraternaContratos.objects.filter(
            cama_ref_id=contrato.cama_ref_id, estado_contrato='actual',
        ).exclude(id=contrato.id).update(estado_contrato='expirado')
        contrato.estado_contrato = 'actual'
        contrato.save(update_fields=['estado_contrato'])
        # Al activarse, la cama del inventario pasa a 'ocupada' con el ocupante de
        # este contrato (residente/arrendatario/genero/fecha). El status del depa se
        # recalcula solo via el signal post_save de FraternaCama. Va dentro de la
        # misma transaccion: si la ocupacion falla, se revierte tambien la activacion.
        cama = contrato.cama_ref
        if cama is not None:
            cama.ocupar_desde_contrato(contrato)
    logger.warning(
        "[ZapSign webhook] contrato id=%s -> estado_contrato=actual (cama_ref_id=%s)",
        contrato.id, contrato.cama_ref_id,
    )
    return True


def _cerrar_ronda_si_completa(ronda, paquete_evento):
    """Cierre operativo de la ronda: las PARTES de ambos paquetes firmaron.

    Los finales (arrendador/prestador) NO gatean — en prod no firman al momento
    (0/60 docs recientes con esas firmas, auditoria 2026-07-16): el termino se
    compromete cuando las partes completan P1+P2, y las firmas de Fraterna/
    Jonathan se registran despues en el espejo (el historial del FE presta sus
    enlaces). Fallback: 'signed' a nivel documento en ambos paquetes tambien
    cierra (cubre rondas sin espejo de partes utilizable).

    Auto-reparacion: si las partes del paquete del evento ya estan completas y
    las del OTRO paquete no, se relee ESE doc de ZapSign antes de decidir (un
    evento perdido tipico: el webhook scoped del doc se registro tarde).

    El cierre y el rail (`_activar_vigencia`) van en la MISMA transaccion: si
    la activacion truena, la ronda sigue 'pendiente' y el siguiente evento del
    doc reintenta ambos (no queda cerrada sin rail).

    Devuelve True si la ronda quedo 'firmado' en esta llamada.
    """
    if ronda.estado != 'pendiente':
        return False

    firmantes = list(ronda.firmantes.all())
    otro = 2 if paquete_evento == 1 else 1
    token_otro = ronda.token_2 if otro == 2 else ronda.token_1
    if (token_otro
            and _partes_paquete_completas(firmantes, paquete_evento)
            and not _partes_paquete_completas(firmantes, otro)):
        doc_otro = _consultar_doc_zapsign(token_otro)
        if doc_otro:
            status_otro = doc_otro.get('status')
            if status_otro:
                setattr(ronda, f'estado_firma_{otro}', status_otro)
                ronda.save(update_fields=[f'estado_firma_{otro}'])
            _sync_firmantes(ronda, otro, doc_otro.get('signers') or [])
            firmantes = list(ronda.firmantes.all())

    partes_ok = (bool(ronda.token_1) and bool(ronda.token_2)
                 and _partes_paquete_completas(firmantes, 1)
                 and _partes_paquete_completas(firmantes, 2))
    doc_level_ok = (ronda.estado_firma_1 == 'signed'
                    and ronda.estado_firma_2 == 'signed')
    if not (partes_ok or doc_level_ok):
        return False

    with transaction.atomic():
        # Solo UNA ronda 'firmado' por contrato (el termino en pie): la anterior
        # pasa a 'expirado' (queda como historial de renovaciones en el modal)
        # ANTES de marcar esta — el indice unico parcial es inmediato, mismo
        # orden expirar->activar que el rail de la cama.
        (FraternaRondaFirma.objects
         .filter(contrato_id=ronda.contrato_id, estado='firmado')
         .exclude(pk=ronda.pk)
         .update(estado='expirado',
                 motivo=f'termino reemplazado por el proceso #{ronda.numero}'))
        ronda.estado = 'firmado'
        ronda.cerrado_en = timezone.now()
        ronda.save(update_fields=['estado', 'cerrado_en'])
        _activar_vigencia(ronda.contrato)
    logger.warning(
        "[ZapSign webhook] ronda %s (contrato %s) CERRADA 'firmado' "
        "(partes_ok=%s, doc_level=%s)",
        ronda.pk, ronda.contrato_id, partes_ok, doc_level_ok,
    )
    return True


def _sync_ronda_desde_evento(doc_token, doc_status):
    """Espeja un evento de ZapSign en la ronda cuyo token_1/token_2 coincida.

    El evento solo dispara: la verdad (status del doc + signers[]) se relee con
    GET docs/{token}/, lo que hace el sync idempotente y auto-reparable (un
    evento perdido o fuera de orden se corrige con el siguiente). Si ZapSign no
    responde, se usa el status del propio evento como respaldo.

    Tras refrescar el espejo intenta el cierre operativo (partes de ambos
    paquetes firmadas -> ronda 'firmado' + rail; ver `_cerrar_ronda_si_completa`).
    Una 'cancelado' nunca revive (p. ej. alguien firma un enlace viejo); una
    'firmado' ya es terminal (solo se refresca el espejo).

    Devuelve un dict informativo, o None si el token no corresponde a ninguna
    ronda (p. ej. documento de otro tenant de la cuenta compartida).
    """
    ronda = (FraternaRondaFirma.objects
             .filter(Q(token_1=doc_token) | Q(token_2=doc_token))
             .order_by('-generado_en')
             .first())
    if ronda is None:
        return None

    paquete = 1 if ronda.token_1 == doc_token else 2
    campo_estado = f'estado_firma_{paquete}'

    doc = _consultar_doc_zapsign(doc_token)
    status_doc = (doc or {}).get('status') or doc_status

    setattr(ronda, campo_estado, status_doc)
    ronda.save(update_fields=[campo_estado])

    _sync_firmantes(ronda, paquete, (doc or {}).get('signers') or [])

    _cerrar_ronda_si_completa(ronda, paquete)

    # PDF firmado -> nuestro S3, en hilo aparte (el webhook responde 200 sin
    # esperar; el signed_file tarda unos segundos en existir).
    if (status_doc == 'signed' and ronda.estado != 'cancelado'
            and not getattr(ronda, f'pdf_firmado_{paquete}')):
        threading.Thread(
            target=_descargar_pdf_firmado,
            args=(ronda.pk, paquete, doc_token),
            daemon=True,
        ).start()

    logger.warning(
        "[ZapSign webhook] ronda %s (contrato %s) P%s: %s=%s estado=%s",
        ronda.pk, ronda.contrato_id, paquete, campo_estado, status_doc, ronda.estado,
    )
    return {
        'ronda_id': ronda.pk,
        'numero': ronda.numero,
        'paquete': paquete,
        'estado_firma': status_doc,
        'estado': ronda.estado,
    }


@csrf_exempt
def zapsign_webhook(request):
    """Endpoint para registrar como webhook en ZapSign.

    GET  -> responde 200 (util para validar que la URL esta viva).
    POST -> persiste el estado de firma del paquete y responde 200.

    Siempre responde 200 ante un POST procesable para que ZapSign no reintente
    en bucle; cualquier error queda en el log para diagnostico.
    """
    if request.method == 'GET':
        return JsonResponse({'status': 'ZapSign webhook activo'}, status=200)

    if request.method != 'POST':
        return JsonResponse({'error': 'Metodo no permitido'}, status=405)

    raw = ''
    try:
        raw = request.body.decode('utf-8', errors='replace') if request.body else ''
    except Exception as e:
        logger.error("[ZapSign webhook] no se pudo leer el cuerpo: %s", e)

    # Se registra el payload crudo para poder verificar el esquema real de ZapSign.
    logger.warning("[ZapSign webhook] payload crudo: %s", raw)

    payload = None
    try:
        payload = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        logger.warning("[ZapSign webhook] el cuerpo no es JSON valido")

    if not isinstance(payload, dict):
        return JsonResponse({'received': True, 'persisted': False}, status=200)

    # Extraccion defensiva: ZapSign manda token/status a nivel raiz; se cubren
    # tambien variantes anidadas bajo `doc`.
    doc = payload.get('doc') if isinstance(payload.get('doc'), dict) else {}
    doc_token = payload.get('token') or payload.get('doc_token') or doc.get('token')
    doc_status = payload.get('status') or doc.get('status')
    evento = (payload.get('event_type') or payload.get('event')
              or payload.get('type') or 'desconocido')
    logger.warning(
        "[ZapSign webhook] evento=%s token=%s status=%s",
        evento, doc_token, doc_status,
    )

    if not doc_token or not doc_status:
        return JsonResponse({'received': True, 'persisted': False}, status=200)

    # --- Bitacora de rondas: espejo del intento de firma (aditivo) ---
    # Corre ANTES e independiente del contrato: durante pruebas el token puede
    # vivir solo en la ronda (persistir_token=False) y, en prod, ambos caminos
    # deben actualizarse con el mismo evento. Best-effort: un fallo del ledger
    # no tumba el webhook.
    info_ronda = None
    try:
        info_ronda = _sync_ronda_desde_evento(doc_token, doc_status)
    except Exception as e:
        logger.error(
            "[ZapSign webhook] fallo el sync de ronda para token %s: %s",
            doc_token, e,
        )

    # Emparejar por token: `token` = Paquete 1, `token_paquete_2` = Paquete 2.
    contrato = FraternaContratos.objects.filter(token=doc_token).first()
    campo = 'estado_firma_paquete_1'
    if contrato is None:
        contrato = FraternaContratos.objects.filter(token_paquete_2=doc_token).first()
        campo = 'estado_firma_paquete_2'

    if contrato is None:
        if info_ronda is None:
            logger.warning(
                "[ZapSign webhook] token %s sin contrato ni ronda Fraterna (otro tenant?)",
                doc_token,
            )
        return JsonResponse(
            {'received': True, 'persisted': info_ronda is not None, 'ronda': info_ronda},
            status=200,
        )

    setattr(contrato, campo, doc_status)
    contrato.save(update_fields=[campo])
    logger.warning(
        "[ZapSign webhook] contrato id=%s %s=%s", contrato.id, campo, doc_status,
    )

    # --- Ciclo de vida del contrato vs la cama (estado_contrato), camino LEGACY ---
    # Para contratos SIN bitacora (sin ronda): cuando AMBOS paquetes quedan
    # 'signed' a nivel documento se activa la vigencia. Los contratos CON ronda
    # se activan antes, al cerrar la ronda por partes (`_cerrar_ronda_si_completa`);
    # este bloque queda como respaldo idempotente (si la ronda ya activo el
    # contrato, `_activar_vigencia` no hace nada).
    if (contrato.estado_firma_paquete_1 == 'signed'
            and contrato.estado_firma_paquete_2 == 'signed'):
        _activar_vigencia(contrato)

    return JsonResponse(
        {'received': True, 'persisted': True, 'contrato_id': contrato.id,
         'campo': campo, 'status': doc_status,
         'estado_contrato': contrato.estado_contrato, 'ronda': info_ronda},
        status=200,
    )
