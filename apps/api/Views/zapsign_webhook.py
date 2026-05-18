"""Webhook receptor de eventos de ZapSign.

Esta primera versión RECIBE y REGISTRA en log el payload de cada evento.
ZapSign no garantiza un esquema fijo y estable, así que registramos el payload
crudo para construir la persistencia del estado de firma sobre datos reales.

Siguiente paso (una vez registrado un payload real de ZapSign):
  - Campo en FraternaContratos para el estado de firma + migración.
  - Lógica de marcado: ubicar el contrato por `token` / `token_paquete_2`
    y marcarlo firmado cuando el documento quede completamente firmado.

Para usarlo: registrar en ZapSign la URL  https://<dominio-backend>/zapsign-webhook/
"""
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


@csrf_exempt
def zapsign_webhook(request):
    """Endpoint para registrar como webhook en ZapSign.

    GET  -> responde 200 (útil para validar que la URL está viva).
    POST -> registra el evento de ZapSign y responde 200.

    Siempre responde 200 ante un POST procesable para que ZapSign no reintente
    en bucle; cualquier error queda en el log para diagnóstico.
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

    # Se registra el payload crudo a nivel WARNING para garantizar que sea
    # visible en el log mientras observamos el formato real de ZapSign.
    logger.warning("[ZapSign webhook] payload crudo: %s", raw)

    payload = None
    try:
        payload = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        logger.warning("[ZapSign webhook] el cuerpo no es JSON valido")

    if isinstance(payload, dict):
        # Extracción defensiva de los campos típicos (evento / token / status).
        doc = payload.get('doc') if isinstance(payload.get('doc'), dict) else {}
        doc_token = payload.get('token') or payload.get('doc_token') or doc.get('token')
        doc_status = payload.get('status') or doc.get('status')
        evento = (payload.get('event_type') or payload.get('event')
                  or payload.get('type') or 'desconocido')
        logger.warning(
            "[ZapSign webhook] evento=%s token=%s status=%s",
            evento, doc_token, doc_status,
        )
        # TODO (persistencia): cuando exista el campo de estado de firma en
        # FraternaContratos, ubicar el contrato por token / token_paquete_2 y
        # marcarlo firmado si `doc_status` indica documento completo.

    return JsonResponse({'received': True}, status=200)
