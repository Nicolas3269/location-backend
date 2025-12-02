"""
Service d'envoi d'emails pour les quittances.
"""

import logging

from django.conf import settings

from core.email_service import EmailService
from core.url_builders import get_user_space_url
from location.constants import UserRole
from location.models import Bien, Locataire
from quittance.models import Quittance

logger = logging.getLogger(__name__)


def send_quittance_email(quittance: Quittance, pdf_url: str, sender_email: str):
    """
    Envoie la quittance par email à tous les locataires.
    """
    locataires: list[Locataire] = list(quittance.location.locataires.all())
    if not locataires:
        return False

    recipients = [loc.email for loc in locataires]

    # Récupérer l'adresse du logement
    bien: Bien = quittance.location.bien

    # Premier prénom pour la salutation
    prenom = locataires[0].firstName if locataires else ""

    mois = quittance.mois.capitalize()
    subject = f"Quittance de loyer - {mois} {quittance.annee}"

    context = {
        "prenom": prenom,
        "mois": mois,
        "annee": quittance.annee,
        "montant_total": quittance.montant_total,
        "montant_loyer": quittance.montant_loyer,
        "montant_charges": quittance.montant_charges,
        "adresse": bien.adresse,
        "pdf_url": pdf_url,
        "lien_espace": get_user_space_url(UserRole.LOCATAIRE),
        "lien_services": f"{settings.FRONTEND_URL}/me-notifier?role=locataire",
    }

    success = EmailService.send(
        to=recipients,
        subject=subject,
        template="locataire/quittance/nouvelle",
        context=context,
        cc=[sender_email],
    )

    if success:
        logger.info(f"Email quittance envoyé à {recipients}")
    else:
        logger.error(f"Erreur envoi email quittance à {recipients}")

    return success
