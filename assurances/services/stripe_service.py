"""
Service Stripe pour les paiements assurance.

Utilise Stripe Checkout (redirect) pour:
- Meilleure confiance (logo Stripe)
- Support Apple Pay / Google Pay natif
- Gestion SEPA automatique
- PCI compliance simplifiée

Gestion de la taxe attentat:
- Ajoutée au premier prélèvement via invoice_item
- Renouvelée chaque année via webhook invoice.upcoming
"""

import logging
from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import stripe
from django.conf import settings
from django.utils import timezone

from assurances.models import InsuranceProduct
from location.models import Bien

if TYPE_CHECKING:
    from assurances.models import InsurancePolicy
    from location.models import User

logger = logging.getLogger(__name__)

# Configurer Stripe
stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")

# Labels pour les produits
PRODUCT_LABELS = {
    InsuranceProduct.MRH: "Assurance MRH",
    InsuranceProduct.PNO: "Assurance PNO",
    InsuranceProduct.GLI: "Garantie Loyers Impayés",
}

# Taxe attentat annuelle en centimes
TAXE_ATTENTAT_CENTS = 650  # 6.50€


class InsuranceStripeService:
    """
    Service pour gérer les paiements Stripe assurance via Checkout Sessions.

    Flow:
    1. create_checkout_session() → retourne checkout_url
    2. Frontend redirige vers checkout_url
    3. User paie sur Stripe
    4. Stripe redirige vers success_url
    5. Webhook checkout.session.completed → active la police

    Gestion taxe attentat:
    - Premier prélèvement: cotisation + taxe attentat (via add_invoice_items)
    - Renouvellement annuel: taxe ajoutée via webhook invoice.upcoming
    """

    def create_checkout_session(
        self,
        policy: "InsurancePolicy",
        context: str = "standalone",
        return_token: str = "",
        subscriber_name: str | None = None,
    ) -> dict:
        """
        Crée une Checkout Session Stripe pour le paiement assurance.

        La taxe attentat (6.50€) est automatiquement ajoutée au premier prélèvement.

        Args:
            policy: Police à payer
            context: Contexte d'origine ("standalone" ou "tenant_documents")
            return_token: Token de signature pour le retour (si context=tenant_documents)
            subscriber_name: Nom du souscripteur pour pré-remplir le formulaire SEPA

        Returns:
            {
                'checkout_url': 'https://checkout.stripe.com/...',
                'session_id': 'cs_xxx'
            }
        """
        # Accéder aux données via quotation
        quotation = policy.quotation
        location = quotation.location
        product = quotation.product
        formula = quotation.selected_formula or {}
        formula_label = formula.get("label", "")
        pricing_monthly = formula.get("pricing_monthly", 0)

        # Récupérer l'adresse du bien pour pré-remplir le formulaire SEPA
        billing_address = None
        if location:
            try:
                bien: Bien = getattr(location, "bien", None)
                if bien and bien.adresse:
                    addr = bien.adresse
                    # Construire line1 depuis les champs structurés
                    line1_parts = []
                    if addr.numero:
                        line1_parts.append(addr.numero)
                    if addr.voie:
                        line1_parts.append(addr.voie)
                    line1 = " ".join(line1_parts)

                    billing_address = {
                        "line1": line1,
                        "line2": addr.complement or "",
                        "postal_code": addr.code_postal or "",
                        "city": addr.ville or "",
                        "country": addr.pays or "FR",
                    }
            except Exception as e:
                logger.warning(f"Could not get billing address from location: {e}")

        # Créer ou récupérer le customer Stripe
        customer = self.get_or_create_customer(
            policy.subscriber, address=billing_address, name=subscriber_name
        )

        # URLs de redirection selon le contexte
        base_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        product_path = product.lower()  # mrh, pno, gli
        location_id = str(quotation.location_id) if location else ""

        if context == "tenant_documents" and return_token:
            success_url = f"{base_url}/bail/signing/{return_token}?insurance=success&session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = f"{base_url}/bail/signing/{return_token}?insurance=cancelled"
        else:
            success_url = f"{base_url}/assurances/{product_path}/success?session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = (
                f"{base_url}/assurances/{product_path}/cancel?location_id={location_id}"
            )

        # Label du produit
        product_label = PRODUCT_LABELS.get(product, "Assurance")

        # Montant mensuel en centimes
        amount_monthly = int(Decimal(str(pricing_monthly)) * 100)

        # Créer la session Checkout en mode subscription (paiement mensuel)
        # La taxe attentat est ajoutée comme line_item one-time (sans recurring)
        session = stripe.checkout.Session.create(
            customer=customer.id,
            mode="subscription",
            payment_method_types=["sepa_debit"],
            line_items=[
                # Cotisation mensuelle récurrente
                {
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": amount_monthly,
                        "recurring": {"interval": "month"},
                        "product_data": {
                            "name": f"{product_label} - {formula_label}",
                            "description": "Cotisation mensuelle prélevée chaque mois",
                        },
                    },
                    "quantity": 1,
                },
                # Taxe attentat - one-time (renouvelée via webhook invoice.upcoming)
                {
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": TAXE_ATTENTAT_CENTS,
                        "product_data": {
                            "name": "Taxe attentat (annuelle)",
                            "description": "Renouvelée à chaque date anniversaire",
                        },
                    },
                    "quantity": 1,
                },
            ],
            subscription_data={
                "description": (
                    f"{product_label} - {formula_label} - {policy.policy_number}"
                ),
                "metadata": {
                    "policy_id": str(policy.id),
                    "policy_number": policy.policy_number,
                    "product": product,
                    "subscription_start_date": quotation.effective_date.isoformat(),
                },
            },
            metadata={
                "policy_id": str(policy.id),
                "policy_number": policy.policy_number,
                "product": product,
                "type": "insurance_subscription",
                "location_id": location_id,
            },
            success_url=success_url,
            cancel_url=cancel_url,
            locale="fr",
            customer_email=policy.subscriber.email if not customer else None,
            # Note: custom_text non supporté pour subscription + SEPA
            # L'info sur la taxe attentat est affichée côté frontend
        )

        # Sauvegarder l'ID de session
        policy.stripe_checkout_session_id = session.id
        policy.stripe_customer_id = customer.id
        policy.save(update_fields=["stripe_checkout_session_id", "stripe_customer_id"])

        logger.info(
            f"Created Checkout Session {session.id} for {product} policy {policy.policy_number} "
            f"(monthly: {pricing_monthly}€ + taxe attentat: 6.50€ on first invoice)"
        )

        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }

    def get_or_create_customer(
        self, user: "User", address: dict | None = None, name: str | None = None
    ) -> stripe.Customer:
        """
        Récupère ou crée un customer Stripe pour l'utilisateur.

        Args:
            user: Utilisateur Django
            address: Adresse de facturation optionnelle (line1, line2, postal_code, city, country)
            name: Nom du titulaire (pré-remplissage SEPA)

        Returns:
            Customer Stripe
        """
        # Vérifier si l'utilisateur a déjà un customer_id
        stripe_customer_id = getattr(user, "stripe_customer_id", None)

        if stripe_customer_id:
            try:
                customer = stripe.Customer.retrieve(stripe_customer_id)
                # Mettre à jour l'adresse, le nom et la locale si nécessaire
                updates = {}
                if address and not customer.address:
                    updates["address"] = {
                        "line1": address.get("line1", ""),
                        "line2": address.get("line2", ""),
                        "postal_code": address.get("postal_code", ""),
                        "city": address.get("city", ""),
                        "country": address.get("country", "FR"),
                    }
                if name and (not customer.name or customer.name == user.email):
                    updates["name"] = name
                # Toujours s'assurer que la locale est en français
                locales = customer.preferred_locales or []
                if "fr" not in locales:
                    updates["preferred_locales"] = ["fr"]
                if updates:
                    stripe.Customer.modify(stripe_customer_id, **updates)
                return customer
            except stripe.error.InvalidRequestError:
                logger.warning(
                    f"Stripe customer {stripe_customer_id} not found, creating new"
                )

        # Déterminer le nom à utiliser (priorité: nom fourni > nom utilisateur > email)
        customer_name = (
            name or f"{user.first_name} {user.last_name}".strip() or user.email
        )

        # Préparer les données du customer
        customer_data = {
            "email": user.email,
            "name": customer_name,
            "metadata": {"user_id": str(user.id)},
            "preferred_locales": ["fr"],  # Factures en français
        }

        # Ajouter l'adresse de facturation si disponible (pré-remplissage SEPA)
        if address:
            customer_data["address"] = {
                "line1": address.get("line1", ""),
                "line2": address.get("line2", ""),
                "postal_code": address.get("postal_code", ""),
                "city": address.get("city", ""),
                "country": address.get("country", "FR"),
            }

        # Créer un nouveau customer
        customer = stripe.Customer.create(**customer_data)

        # Sauvegarder l'ID si le modèle User le supporte
        if hasattr(user, "stripe_customer_id"):
            user.stripe_customer_id = customer.id
            user.save(update_fields=["stripe_customer_id"])

        logger.info(f"Created Stripe customer {customer.id} for user {user.email}")
        return customer

    def handle_checkout_completed(self, event: dict) -> None:
        """
        Traite l'événement checkout.session.completed.

        Active la police et génère les documents.

        Args:
            event: Événement Stripe
        """
        from assurances.models import InsurancePolicy
        from assurances.services.subscription import InsuranceSubscriptionService

        session = event["data"]["object"]
        policy_id = session.get("metadata", {}).get("policy_id")

        if not policy_id:
            logger.debug("Checkout session without policy_id, skipping")
            return

        # Vérifier le type de paiement
        if session.get("metadata", {}).get("type") != "insurance_subscription":
            logger.debug("Checkout session is not insurance subscription, skipping")
            return

        # Pour SEPA, payment_status="unpaid" au moment du checkout.session.completed
        # Le paiement sera confirmé plus tard (checkout.session.async_payment_succeeded)
        # On active quand même la police pour que la couverture prenne effet
        payment_status = session.get("payment_status")
        if payment_status not in ("paid", "unpaid", "no_payment_required"):
            logger.warning(
                f"Checkout session {session['id']} unexpected status: {payment_status}"
            )
            return

        logger.info(
            f"Processing checkout with payment_status={payment_status} "
            f"(SEPA payments start as 'unpaid')"
        )

        try:
            policy = InsurancePolicy.objects.get(id=policy_id)
        except InsurancePolicy.DoesNotExist:
            logger.error(f"Policy {policy_id} not found for session {session['id']}")
            return

        # Sauvegarder le subscription_id
        subscription_id = session.get("subscription")
        if subscription_id:
            policy.stripe_subscription_id = subscription_id
            policy.save(update_fields=["stripe_subscription_id"])
        else:
            # Fallback pour mode payment (si jamais utilisé)
            payment_intent_id = session.get("payment_intent")
            if payment_intent_id:
                policy.stripe_payment_intent_id = payment_intent_id
                policy.save(update_fields=["stripe_payment_intent_id"])

        logger.info(
            f"Checkout completed for {policy.quotation.product} policy {policy.policy_number}"
        )

        # Activer la police
        subscription_service = InsuranceSubscriptionService()
        subscription_service.activate_policy(policy)

    def handle_invoice_upcoming(self, event: dict) -> None:
        """
        Traite l'événement invoice.upcoming.

        Ajoute la taxe attentat si c'est un anniversaire de contrat.
        Cet événement est déclenché ~3 jours avant la création de la facture.

        Args:
            event: Événement Stripe
        """
        invoice = event["data"]["object"]
        subscription_id = invoice.get("subscription")

        if not subscription_id:
            return

        # Récupérer la subscription pour vérifier si c'est une assurance
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
        except stripe.error.InvalidRequestError:
            logger.warning(f"Subscription {subscription_id} not found")
            return

        # Vérifier que c'est une assurance
        product = subscription.metadata.get("product")
        if product not in ["MRH", "PNO", "GLI"]:
            return

        policy_number = subscription.metadata.get("policy_number")
        subscription_start = subscription.metadata.get("subscription_start_date")

        if not subscription_start:
            logger.warning(
                f"No subscription_start_date in metadata for {policy_number}"
            )
            return

        # Parser la date de début
        try:
            start_date = datetime.fromisoformat(subscription_start).date()
        except ValueError:
            logger.error(f"Invalid subscription_start_date: {subscription_start}")
            return

        # Calculer si on est à un anniversaire (12 mois, 24 mois, etc.)
        invoice_date = datetime.fromtimestamp(
            invoice.get("period_end", 0), tz=dt_timezone.utc
        ).date()
        months_since_start = (
            (invoice_date.year - start_date.year) * 12
            + invoice_date.month
            - start_date.month
        )

        # La taxe attentat est due chaque année (mois 12, 24, 36, etc.)
        # Note: le premier prélèvement (mois 0) a déjà la taxe via add_invoice_items
        if months_since_start > 0 and months_since_start % 12 == 0:
            logger.info(
                f"🎂 Anniversary #{months_since_start // 12} for policy {policy_number} - "
                f"Adding taxe attentat"
            )

            # Ajouter la taxe attentat à la prochaine facture
            stripe.InvoiceItem.create(
                customer=invoice.get("customer"),
                subscription=subscription_id,
                amount=TAXE_ATTENTAT_CENTS,
                currency="eur",
                description=f"Taxe attentat - Année {months_since_start // 12 + 1}",
            )

            logger.info(
                f"✅ Added taxe attentat (6.50€) to upcoming invoice for {policy_number}"
            )

    def handle_checkout_expired(self, event: dict) -> None:
        """
        Traite l'événement checkout.session.expired.

        La session a expiré sans paiement (24h par défaut).

        Args:
            event: Événement Stripe
        """
        from assurances.models import InsurancePolicy

        session = event["data"]["object"]
        policy_id = session.get("metadata", {}).get("policy_id")

        if not policy_id:
            return

        try:
            policy = InsurancePolicy.objects.get(id=policy_id)
        except InsurancePolicy.DoesNotExist:
            return

        logger.info(f"Checkout session expired for policy {policy.policy_number}")

        # La police reste en PENDING, l'user peut réessayer
        # On pourrait envoyer un email de relance ici

    def handle_payment_failed(self, event: dict) -> None:
        """
        Traite l'événement payment_intent.payment_failed.

        Args:
            event: Événement Stripe
        """
        from assurances.models import InsurancePolicy

        payment_intent = event["data"]["object"]
        policy_id = payment_intent.get("metadata", {}).get("policy_id")

        if not policy_id:
            return

        try:
            policy = InsurancePolicy.objects.get(id=policy_id)
        except InsurancePolicy.DoesNotExist:
            return

        error = payment_intent.get("last_payment_error", {})
        error_message = error.get("message", "Unknown error")

        logger.warning(
            f"Payment failed for policy {policy.policy_number}: {error_message}"
        )

        # TODO: Envoyer email de notification d'échec

    def handle_async_payment_failed(self, event: dict) -> None:
        """
        Traite l'événement checkout.session.async_payment_failed.

        Le paiement SEPA a échoué (rejet bancaire, fonds insuffisants, etc.)
        La police doit être suspendue/annulée.

        Args:
            event: Événement Stripe
        """
        from assurances.models import InsurancePolicy

        session = event["data"]["object"]
        policy_id = session.get("metadata", {}).get("policy_id")

        if not policy_id:
            logger.debug("Async payment failed without policy_id, skipping")
            return

        try:
            policy = InsurancePolicy.objects.get(id=policy_id)
        except InsurancePolicy.DoesNotExist:
            logger.error(f"Policy {policy_id} not found for failed payment")
            return

        logger.warning(
            f"⚠️ SEPA payment failed for policy {policy.policy_number} - "
            f"suspending policy"
        )

        # Suspendre la police
        policy.status = InsurancePolicy.Status.SUSPENDED
        policy.save(update_fields=["status", "updated_at"])

        # TODO: Envoyer email de notification au client
        # TODO: Supprimer l'attestation du dossier locataire

    def handle_subscription_deleted(self, event: dict) -> None:
        """
        Traite l'événement customer.subscription.deleted.

        La subscription a été annulée/résiliée.

        Args:
            event: Événement Stripe
        """
        from assurances.models import InsurancePolicy

        subscription = event["data"]["object"]
        policy_number = subscription.get("metadata", {}).get("policy_number")

        if not policy_number:
            return

        try:
            policy = InsurancePolicy.objects.get(policy_number=policy_number)
        except InsurancePolicy.DoesNotExist:
            logger.warning(
                f"Policy {policy_number} not found for subscription deletion"
            )
            return

        logger.info(f"Subscription deleted for policy {policy_number}")

        # Résilier la police
        policy.status = InsurancePolicy.Status.CANCELLED
        policy.end_date = timezone.now().date()
        policy.save(update_fields=["status", "end_date", "updated_at"])

    def refund_payment(
        self, policy: "InsurancePolicy", reason: str = ""
    ) -> stripe.Refund:
        """
        Rembourse le paiement d'une police.

        Args:
            policy: Police à rembourser
            reason: Motif du remboursement

        Returns:
            Refund Stripe

        Raises:
            ValueError: Si pas de payment_intent_id
        """
        if not policy.stripe_payment_intent_id:
            raise ValueError("No payment intent found for this policy")

        refund = stripe.Refund.create(
            payment_intent=policy.stripe_payment_intent_id,
            reason="requested_by_customer",
            metadata={
                "policy_id": str(policy.id),
                "policy_number": policy.policy_number,
                "product": policy.quotation.product,
                "refund_reason": reason,
            },
        )

        logger.info(f"Created refund {refund.id} for policy {policy.policy_number}")
        return refund

    def cancel_subscription(self, policy: "InsurancePolicy") -> None:
        """
        Résilie la subscription Stripe d'une police.

        Args:
            policy: Police à résilier
        """
        if not policy.stripe_subscription_id:
            logger.warning(f"No subscription ID for policy {policy.policy_number}")
            return

        try:
            stripe.Subscription.cancel(policy.stripe_subscription_id)
            logger.info(
                f"Cancelled Stripe subscription {policy.stripe_subscription_id} "
                f"for policy {policy.policy_number}"
            )
        except stripe.error.InvalidRequestError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            raise

    def get_session_status(self, session_id: str) -> dict:
        """
        Récupère le statut d'une session Checkout.

        Utile pour la page success pour confirmer le paiement.

        Args:
            session_id: ID de la session Checkout

        Returns:
            {
                'status': 'complete' | 'expired' | 'open',
                'payment_status': 'paid' | 'unpaid' | 'no_payment_required',
                'policy_number': 'PO-...',
                'product': 'MRH' | 'PNO' | 'GLI'
            }
        """
        session = stripe.checkout.Session.retrieve(session_id)

        return {
            "status": session.status,
            "payment_status": session.payment_status,
            "policy_number": session.metadata.get("policy_number"),
            "product": session.metadata.get("product"),
            "customer_email": session.customer_details.email
            if session.customer_details
            else None,
        }
