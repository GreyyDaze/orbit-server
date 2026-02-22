import stripe
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from identity.models import AnonymousProfile
import logging

logger = logging.getLogger(__name__)

class CreateCheckoutSessionView(APIView):
    def post(self, request):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        if not request.ghost:
            return Response({"error": "Ghost ID required"}, status=status.HTTP_400_BAD_REQUEST)

        print(f"DEBUG: Creating checkout for Ghost {request.ghost.ghost_id}")

        try:
            # We use metadata to link the payment back to the Ghost ID
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[
                    {
                        'price_data': {
                            'currency': 'usd',
                            'product_data': {
                                'name': 'Orbit Pro - Unlimited Boards & Lifetime Data',
                            },
                            'unit_amount': 2900, # $29.00
                        },
                        'quantity': 1,
                    },
                ],
                mode='payment',
                success_url=settings.FRONTEND_URL + '/payment/success?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=settings.FRONTEND_URL + '/pricing',
                metadata={
                    'ghost_id': str(request.ghost.ghost_id)
                }
            )
            return Response({'url': checkout_session.url})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': f"Stripe error: {repr(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        event = None

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # Handle the checkout.session.completed event
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            ghost_id = session.get('metadata', {}).get('ghost_id')
            customer_id = session.get('customer')

            if ghost_id:
                try:
                    profile = AnonymousProfile.objects.get(ghost_id=ghost_id)
                    profile.is_pro = True
                    profile.stripe_customer_id = customer_id
                    profile.save()
                    logger.info(f"Ghost {ghost_id} upgraded to PRO")
                except AnonymousProfile.DoesNotExist:
                    logger.error(f"Ghost {ghost_id} not found after successful payment")

        return Response(status=status.HTTP_200_OK)
