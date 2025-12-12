"""
Handlers pour les webhooks Stripe Assurances.

Endpoints pour recevoir et traiter les événements Stripe.
"""

import logging

import stripe
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services.stripe_service import InsuranceStripeService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    """
    Endpoint pour les webhooks Stripe.

    Vérifie la signature et dispatch vers le handler approprié.

    URL: POST /api/assurances/webhooks/stripe/

    Événements gérés:
    - checkout.session.completed: Checkout terminé → active la police immédiatement
    - checkout.session.async_payment_succeeded: Paiement SEPA confirmé (3-5j après)
    - checkout.session.async_payment_failed: Paiement SEPA échoué → suspend police
    - checkout.session.expired: Session expirée sans paiement
    - payment_intent.payment_failed: Échec de paiement CB
    - invoice.upcoming: Facture à venir → ajoute taxe attentat si anniversaire
    - customer.subscription.deleted: Subscription résiliée → annule la police
    - charge.refunded: Remboursement effectué
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        return HttpResponse(status=500)

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            webhook_secret,
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        return HttpResponse(status=400)

    # Logger l'événement avec détails
    event_type = event["type"]
    session = event.get("data", {}).get("object", {})
    metadata = session.get("metadata", {})
    logger.info(
        f"📨 Received Stripe webhook: {event_type} | "
        f"session_id={session.get('id')} | "
        f"payment_status={session.get('payment_status')} | "
        f"metadata={metadata}"
    )

    # Dispatcher vers le handler approprié
    stripe_service = InsuranceStripeService()

    try:
        if event_type == "checkout.session.completed":
            # Checkout complété - activer immédiatement pour une meilleure UX
            # Pour CB: payment_status="paid" → paiement instantané
            # Pour SEPA: payment_status="unpaid" → paiement en attente
            # On active dans les deux cas car la couverture doit prendre effet immédiatement
            stripe_service.handle_checkout_completed(event)

        elif event_type == "checkout.session.async_payment_succeeded":
            # Paiement SEPA confirmé (3-5 jours après)
            # Si pas déjà activé par checkout.session.completed, activer maintenant
            stripe_service.handle_checkout_completed(event)

        elif event_type == "checkout.session.async_payment_failed":
            # Paiement SEPA échoué (rejet bancaire, fonds insuffisants, etc.)
            stripe_service.handle_async_payment_failed(event)

        elif event_type == "checkout.session.expired":
            # Session expirée (24h sans paiement)
            stripe_service.handle_checkout_expired(event)

        elif event_type == "payment_intent.payment_failed":
            # Échec de paiement
            stripe_service.handle_payment_failed(event)

        elif event_type == "invoice.upcoming":
            # Facture à venir - ajouter taxe attentat si anniversaire
            stripe_service.handle_invoice_upcoming(event)

        elif event_type == "customer.subscription.deleted":
            # Subscription résiliée
            stripe_service.handle_subscription_deleted(event)

        elif event_type == "charge.refunded":
            # Remboursement
            charge = event["data"]["object"]
            logger.info(
                f"Charge refunded: {charge['id']} - "
                f"Amount: {charge['amount_refunded']/100}€"
            )

        else:
            logger.debug(f"Unhandled event type: {event_type}")

    except Exception as e:
        logger.exception(f"Error processing webhook {event_type}: {e}")
        # Retourner 200 pour éviter les retries inutiles
        # L'erreur est loggée et peut être investiguée

    return HttpResponse(status=200)
