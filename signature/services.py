"""
Services partagés pour la signature de documents
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_signature_email(signature_request, document_type="document"):
    """
    Envoie un email avec le lien de signature et l'OTP

    Args:
        signature_request: Instance de AbstractSignatureRequest
        document_type: Type de document ("bail" ou "etat_lieux")
    """
    # Générer un nouvel OTP
    otp = signature_request.generate_otp()

    # Récupérer l'email du signataire
    email = signature_request.get_signataire_email()
    if not email:
        logger.error(f"Pas d'email pour {signature_request}")
        return False

    # Déterminer le type de document pour l'email
    if document_type == "bail":
        subject = "Signature électronique de votre bail de location"
        template = "bail/email_signature.html"
    elif document_type == "etat_lieux":
        subject = "Signature électronique de votre état des lieux"
        template = "etat_lieux/email_signature.html"
    else:
        subject = f"Signature électronique de votre {document_type}"
        template = None

    # Construire l'URL de signature selon le type de document
    base_url = settings.FRONTEND_URL
    if document_type == "bail":
        signature_url = f"{base_url}/bail/signing/{signature_request.link_token}"
    elif document_type == "etat_lieux":
        signature_url = f"{base_url}/etat-lieux/signing/{signature_request.link_token}"
    else:
        signature_url = (
            f"{base_url}/{document_type}/signing/{signature_request.link_token}"
        )

    # Préparer le contexte de l'email
    context = {
        "signataire_name": signature_request.get_signataire_name(),
        "signature_url": signature_url,
        "otp": otp,
        "document_type": document_type,
    }

    # Générer le contenu de l'email
    if template:
        try:
            html_message = render_to_string(template, context)
        except Exception:
            # Si le template n'existe pas, utiliser un message par défaut
            html_message = None
    else:
        html_message = None

    # Message texte par défaut
    text_message = f"""
    Bonjour {signature_request.get_signataire_name()},

    Vous êtes invité(e) à signer électroniquement votre {document_type}.

    Pour accéder au document et le signer, cliquez sur le lien suivant :
    {signature_url}

    Votre code de vérification (OTP) est : {otp}

    Ce code est valable pendant 10 minutes.

    Cordialement,
    L'équipe Hestia
    """

    # Envoyer l'email
    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Email de signature envoyé à {email}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email à {email}: {e}")
        return False


def verify_signature_order(signature_request):
    """
    Vérifie que c'est bien le tour de ce signataire

    Args:
        signature_request: Instance de AbstractSignatureRequest

    Returns:
        bool: True si c'est son tour, False sinon
    """
    # Récupérer le document
    document = signature_request.get_document()

    # Déterminer le nom du champ de relation vers le document
    if hasattr(signature_request, "etat_lieux"):
        document_field = "etat_lieux"
    elif hasattr(signature_request, "bail"):
        document_field = "bail"
    else:
        # Fallback - essayer de deviner le champ
        for field in signature_request._meta.get_fields():
            if field.is_relation and not field.many_to_many and not field.one_to_many:
                if field.name not in [
                    "bailleur_signataire",
                    "locataire",
                    "signature_image",
                ]:
                    document_field = field.name
                    break
        else:
            raise ValueError("Impossible de déterminer le champ document")

    # Récupérer la première demande non signée
    next_request = (
        type(signature_request)
        .objects.filter(
            **{document_field: document},
            signed=False,
        )
        .order_by("order")
        .first()
    )

    return next_request == signature_request


def get_next_signer(signature_request):
    """
    Récupère le prochain signataire après la signature actuelle

    Args:
        signature_request: Instance de AbstractSignatureRequest

    Returns:
        AbstractSignatureRequest ou None
    """
    return signature_request.get_next_signature_request()
