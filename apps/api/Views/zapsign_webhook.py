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

Registrar en ZapSign la URL:  https://<dominio-backend>/zapsign-webhook/
"""
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from ...home.models import FraternaContratos

logger = logging.getLogger(__name__)


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

    # Emparejar por token: `token` = Paquete 1, `token_paquete_2` = Paquete 2.
    contrato = FraternaContratos.objects.filter(token=doc_token).first()
    campo = 'estado_firma_paquete_1'
    if contrato is None:
        contrato = FraternaContratos.objects.filter(token_paquete_2=doc_token).first()
        campo = 'estado_firma_paquete_2'

    if contrato is None:
        logger.warning(
            "[ZapSign webhook] token %s sin contrato Fraterna (otro tenant?)",
            doc_token,
        )
        return JsonResponse({'received': True, 'persisted': False}, status=200)

    setattr(contrato, campo, doc_status)
    contrato.save(update_fields=[campo])
    logger.warning(
        "[ZapSign webhook] contrato id=%s %s=%s", contrato.id, campo, doc_status,
    )

    return JsonResponse(
        {'received': True, 'persisted': True, 'contrato_id': contrato.id,
         'campo': campo, 'status': doc_status},
        status=200,
    )
