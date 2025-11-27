"""
Service d'envoi d'emails pour les quittances.
"""

from django.conf import settings
from django.core.mail import EmailMessage

from location.models import Locataire
from quittance.models import Quittance


def send_quittance_email(quittance: Quittance, pdf_url: str, sender_email: str):
    """
    Envoie la quittance par email à tous les locataires.
    """
    locataires: list[Locataire] = list(quittance.location.locataires.all())
    if not locataires:
        return False

    recipients = [loc.email for loc in locataires]

    message = f"""Bonjour,

Votre quittance de loyer pour {quittance.mois} {quittance.annee} est disponible.

Montant payé : {quittance.montant_total}€
- Loyer HC : {quittance.montant_loyer}€
- Charges : {quittance.montant_charges}€

Tous vos documents et quittances sont disponibles sur votre espace locataire :
{settings.FRONTEND_URL}/mon-compte/mes-locations

Vous pouvez également télécharger votre quittance (lien valable 7 jours) : {pdf_url}

Cordialement,
Hestia"""

    try:
        mois = quittance.mois.capitalize()
        subject = f"Quittance de loyer - {mois} {quittance.annee}"
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
            cc=[sender_email],
        )
        email.send()
        return True
    except Exception as e:
        print(f"Erreur envoi email quittance : {e}")
        return False
