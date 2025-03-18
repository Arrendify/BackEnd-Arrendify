import stripe
from django.conf import settings
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)
from datetime import datetime

stripe.api_key = settings.STRIPE_SECRET_KEY  # Configurar clave secreta

class CreateStripeCheckoutSession(viewsets.ModelViewSet):
    def create(self, request, *args, **kwargs):
        try:
            print("entrando en sesion check out prospecto")
            info = request.data
            print("soy info", info)
            costo = info['costo']
            producto = info['tipo_contrato']
            
            # Crear una sesión de pago
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],  # Métodos de pago aceptados
                line_items=[
                    {
                        'price_data': {
                            'currency': 'mxn', # Moneda
                            'product_data': {
                                'name': str(producto),  # Nombre del producto/servicio
                            },
                            'unit_amount': int(costo) * 100,  # Precio en centavos (3920 MXN)
                        },
                        'quantity': 1,
                    },
                ],
                mode='payment',  # Puede ser 'subscription' si es un pago recurrente
                success_url="http://192.168.2.24:8000/success?session_id={CHECKOUT_SESSION_ID}",
                cancel_url="http://192.168.2.24:8000/cancel",
            )
            print("")
            # print("soy session", session)
            print("retorno la url")
            print("quiero ver la url", session.url)
            return Response({"session_id": session.id, "url": session.url}, status=status.HTTP_200_OK)
            # return Response({"url": session.url}, status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
#Web Hook
import json
@csrf_exempt
def stripe_webhook(request):
    print("entro a stripe_webhook")
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    print("sig header",sig_header)
    # endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    endpoint_secret = "whsec_47566d0c657e8811e44dfaf10aa402d9037cb6cf5e2331471d03ace9d48f4324"

    try:
        print("entro a try")
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        print("soy event", event)

    except ValueError:
        print("entro a ValueError",ValueError)
        return JsonResponse({"error": "Invalid payload"}, status=400)
    except stripe.error.SignatureVerificationError:
        print("otro error",)
        return JsonResponse({"error": "Invalid signature"}, status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print("soy session", session)
        print(f"✅ Pago aprobado session complete: {session['id']}")
        # Procesar el pago en la base de datos
     # 🔹 Detectar si el pago fue aprobado
    
    if event["type"] == "charge.updated":
        session = event["data"]["object"]
        print(f"✅ Pago aprobado charge update: {session['id']}")
        # Aquí puedes actualizar la base de datos y notificar al usuario
    

    return JsonResponse({"status": "success"}, status=200)


class CheckPaymentStatus(APIView):
    def get(self, request):
        print("Entró a CheckPaymentStatus")
        session_id = request.query_params.get("session_id")  # Mejor práctica en DRF

        if not session_id:
            return Response({"error": "session_id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = stripe.checkout.Session.retrieve(session_id)
            print("Sesión obtenida:", session)
            return Response({"status": session.payment_status})  # paid, open, etc.
        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

   