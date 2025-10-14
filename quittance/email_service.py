"""
Service d'envoi d'emails pour les quittances.
Utilise MJML pour des emails responsive.
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template
from mjml.tools import mjml_render


def send_quittance_email(quittance, pdf_url: str):
    """
    Envoie la quittance par email au locataire.

    Args:
        quittance: Instance de Quittance
        pdf_url: URL absolue du PDF généré

    Returns:
        bool: True si envoi réussi
    """
    # Récupérer le premier locataire (principal)
    locataire = quittance.location.locataires.first()
    if not locataire or not locataire.email:
        return False

    # Contexte pour le template
    context = {
        'period': f"{quittance.mois.capitalize()} {quittance.annee}",
        'tenant_name': locataire.full_name,
        'start_date': quittance.start_date.strftime('%d/%m/%Y') if hasattr(quittance, 'start_date') else f"01/{quittance.mois}/{quittance.annee}",
        'end_date': quittance.end_date.strftime('%d/%m/%Y') if hasattr(quittance, 'end_date') else f"30/{quittance.mois}/{quittance.annee}",
        'amount': quittance.montant_total,
        'base_rent': quittance.montant_loyer_hc,
        'charges': quittance.montant_charges,
        'pdf_url': pdf_url,
    }

    # Compiler MJML → HTML
    mjml_template = get_template('email/quittance_email.mjml')
    mjml_content = mjml_template.render(context)
    html_content = mjml_render(mjml_content)

    # Fallback texte brut
    text_content = f"""
Bonjour {locataire.full_name},

Votre quittance de loyer pour {quittance.mois} {quittance.annee} est disponible.

Montant payé : {quittance.montant_total}€
- Loyer HC : {quittance.montant_loyer_hc}€
- Charges : {quittance.montant_charges}€

Téléchargez votre quittance : {pdf_url}

Cordialement,
Hestia
    """

    # Créer et envoyer l'email
    email = EmailMultiAlternatives(
        subject=f"Quittance de loyer - {quittance.mois.capitalize()} {quittance.annee}",
        body=text_content,
        from_email="HESTIA <noreply@hestia.software>",
        to=[locataire.email],
    )
    email.attach_alternative(html_content, "text/html")

    try:
        email.send()
        return True
    except Exception as e:
        print(f"Erreur envoi email quittance : {e}")
        return False
