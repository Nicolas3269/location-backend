"""
Service de souscription assurance.

Gère le processus complet de souscription:
- Création de la police
- Validation du paiement
- Génération des documents
- Envoi des emails
"""

import logging
import re
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

import mrml
from django.template.loader import render_to_string

from .documents import InsuranceDocumentService

if TYPE_CHECKING:
    from assurances.models import InsurancePolicy, InsuranceQuotation
    from location.models import User

logger = logging.getLogger(__name__)


class InsuranceSubscriptionService:
    """
    Service pour gérer les souscriptions d'assurance.

    Responsabilités:
    - Créer une police à partir d'un devis et d'une formule
    - Activer une police après paiement
    - Envoyer les documents par email
    """

    def create_policy(
        self,
        quotation: "InsuranceQuotation",
        formula_code: str,
        subscriber: "User",
    ) -> "InsurancePolicy":
        """
        Crée une nouvelle police d'assurance en attente de paiement.

        Args:
            quotation: Devis valide
            formula_code: Code de la formule choisie
            subscriber: Utilisateur souscripteur

        Returns:
            InsurancePolicy créée avec statut PENDING

        Raises:
            ValueError: Si la formule n'existe pas dans le devis
            ValueError: Si le devis est expiré
        """
        from assurances.models import InsurancePolicy

        # Vérifier la validité du devis
        if not quotation.is_valid:
            raise ValueError("Le devis a expiré, veuillez en demander un nouveau")

        # Vérifier que la formule existe dans le devis
        formula = None
        for f in quotation.formulas_data:
            if f["code"] == formula_code:
                formula = f
                break

        if not formula:
            raise ValueError(f"Formule {formula_code} non trouvée dans le devis")

        # S'assurer que la formule est sélectionnée sur le devis
        if quotation.selected_formula_code != formula_code:
            quotation.selected_formula_code = formula_code
            quotation.save(update_fields=["selected_formula_code"])

        # Créer la police (les autres champs sont accessibles via quotation)
        policy = InsurancePolicy.objects.create(
            quotation=quotation,
            subscriber=subscriber,
            status=InsurancePolicy.Status.PENDING,
        )

        logger.info(
            f"Created {quotation.product} policy {policy.policy_number} for user {subscriber.email}"
        )
        return policy

    def activate_policy(self, policy: "InsurancePolicy") -> None:
        """
        Active une police après confirmation du paiement.

        - Génère les documents (AVANT d'activer - pour rollback si échec)
        - Met à jour le statut
        - Attache l'attestation aux documents locataire
        - Envoie les emails

        Args:
            policy: Police à activer
        """

        if policy.status != policy.Status.PENDING:
            logger.warning(f"Policy {policy.policy_number} is not PENDING, skipping")
            return

        logger.info(
            f"🚀 Starting activation for {policy.quotation.product} policy {policy.policy_number}"
        )

        # 1. Générer les documents EN PREMIER (avant de changer le statut)
        # Si la génération échoue, la police reste PENDING
        doc_service = InsuranceDocumentService()
        try:
            doc_service.generate_all_documents(policy)
            logger.info(f"✅ Documents generated for policy {policy.policy_number}")
        except Exception as e:
            logger.exception(
                f"❌ Failed to generate documents for policy {policy.policy_number}: {e}"
            )
            raise  # Ne pas activer la police si les documents ne sont pas générés

        # 2. Maintenant activer la police (documents générés avec succès)
        policy.status = policy.Status.ACTIVE
        policy.activated_at = timezone.now()
        policy.save(update_fields=["status", "activated_at", "updated_at"])

        logger.info(
            f"✅ Activated {policy.quotation.product} policy {policy.policy_number}"
        )

        # 3. Attacher l'attestation aux documents du locataire (pour le flow tenant)
        if policy.attestation_document:
            self._attach_attestation_to_locataire(policy)
        else:
            logger.warning(
                f"⚠️ No attestation_document found for policy {policy.policy_number} "
                f"even after generation"
            )

        # 4. Envoyer les documents par email
        self.send_policy_documents_email(policy)

    def _attach_attestation_to_locataire(self, policy: "InsurancePolicy") -> None:
        """
        Attache l'attestation générée aux documents du locataire.

        Cela permet au locataire de voir son attestation dans le flow de signature
        sans avoir à la re-uploader.

        Args:
            policy: Police avec attestation générée
        """
        from bail.models import Document, DocumentType

        logger.info(
            f"🔍 _attach_attestation_to_locataire called for policy {policy.policy_number}"
        )

        # Trouver le locataire correspondant au souscripteur
        location = policy.quotation.location
        if not location:
            logger.warning(f"No location for policy {policy.policy_number}")
            return

        logger.info(
            f"📍 Location {location.id} has {location.locataires.count()} locataires"
        )

        # Debug: afficher tous les emails des locataires
        all_locataire_emails = list(location.locataires.values_list("email", flat=True))
        logger.info(
            f"📧 Locataires emails: {all_locataire_emails}, "
            f"looking for: {policy.subscriber.email}"
        )

        locataire = location.locataires.filter(email=policy.subscriber.email).first()

        if not locataire:
            logger.warning(
                f"No locataire found for subscriber {policy.subscriber.email} "
                f"in location {policy.quotation.location_id}"
            )
            return

        # Supprimer l'ancienne attestation si elle existe
        Document.objects.filter(
            locataire=locataire,
            type_document=DocumentType.ATTESTATION_MRH,
        ).delete()

        # Créer le nouveau document
        Document.objects.create(
            locataire=locataire,
            type_document=DocumentType.ATTESTATION_MRH,
            nom_original=f"Attestation MRH - {policy.policy_number}.pdf",
            file=policy.attestation_document,
            uploade_par=policy.subscriber,
        )

        logger.info(
            f"Attached attestation to locataire {locataire.email} "
            f"for policy {policy.policy_number}"
        )

    def send_policy_documents_email(self, policy: "InsurancePolicy") -> None:
        """
        Envoie les documents de police par email au souscripteur.

        Args:
            policy: Police avec documents générés
        """
        subscriber = policy.subscriber
        location = policy.quotation.location
        bien = location.bien if location else None

        # Préparer le contexte pour le template
        context = {
            "subscriber": subscriber,
            "policy": policy,
            "bien": bien,
            "adresse": bien.adresse if bien else None,
            "frontend_url": settings.FRONTEND_URL,
            "logo_url": "https://hestia.software/icons/logo-hestia-whatsapp.png",
            "current_year": "2025",
        }

        # Rendre le contenu MJML et compiler en HTML
        product = policy.quotation.product
        subject = f"Votre attestation d'assurance {product} - {policy.policy_number}"

        mjml_content = render_to_string(
            "emails/assurances/policy_documents.mjml", context
        )
        html_content = mrml.to_html(mjml_content).content

        # Générer version texte depuis HTML
        text_content = self._html_to_text(html_content)

        # Créer l'email
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[subscriber.email],
        )
        email.attach_alternative(html_content, "text/html")

        # Joindre les documents
        if policy.attestation_document:
            email.attach_file(policy.attestation_document.path)

        if policy.cp_document:
            email.attach_file(policy.cp_document.path)

        # Envoyer
        try:
            email.send()
            logger.info(f"Sent policy documents email to {subscriber.email}")
        except Exception as e:
            logger.error(f"Failed to send policy documents email: {e}")
            raise

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convertit HTML en texte brut simple (fallback)."""
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\s+", " ", text)
        text = "\n".join(line.strip() for line in text.split("\n") if line.strip())
        return text

    def cancel_policy(
        self,
        policy: "InsurancePolicy",
        reason: str = "",
    ) -> None:
        """
        Résilie une police d'assurance.

        Args:
            policy: Police à résilier
            reason: Motif de résiliation (optionnel)
        """
        if not policy.can_be_cancelled:
            raise ValueError(
                f"La police {policy.policy_number} ne peut pas être résiliée"
            )

        policy.status = policy.Status.CANCELLED
        policy.end_date = timezone.now().date()
        policy.save(update_fields=["status", "end_date", "updated_at"])

        logger.info(
            f"Cancelled {policy.quotation.product} policy {policy.policy_number}: {reason}"
        )

        # TODO: Envoyer email de confirmation de résiliation
        # TODO: Notifier Mila si nécessaire
