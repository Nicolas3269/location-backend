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
    Envoie un email avec le lien de signature (sans OTP - généré à l'accès)
    Le statut du document sera mis à jour vers SIGNING lors de l'envoi de l'OTP.

    Args:
        signature_request: Instance de AbstractSignatureRequest
        document_type: Type de document ("bail" ou "etat_lieux")
    """
    # Plus besoin de générer l'OTP ici - il sera généré lors de l'accès à la page

    # Récupérer l'email du signataire
    email = signature_request.get_signataire_email()
    if not email:
        logger.error(f"Pas d'email pour {signature_request}")
        return False

    # Convertir le document_type technique vers un nom lisible
    document_display_name = {
        "bail": "bail",
        "etat_lieux": "état des lieux",
    }.get(document_type, document_type)

    # Déterminer le type de document pour l'email
    if document_type == "bail":
        subject = "Signature électronique de votre bail de location"
        template = "bail/email_signature.html"
    elif document_type == "etat_lieux":
        subject = "Signature électronique de votre état des lieux"
        template = "etat_lieux/email_signature.html"
    else:
        subject = f"Signature électronique de votre {document_display_name}"
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
        "document_type": document_display_name,
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

    Vous êtes invité(e) à signer électroniquement votre {document_display_name}.

    Pour accéder au document et le signer, cliquez sur le lien suivant :
    {signature_url}

    Un code de vérification (OTP) vous sera envoyé par email lors de l'accès à la page.

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


def send_otp_email(signature_request, document_type="document"):
    """
    Envoie un email avec le code OTP pour la signature.
    Met à jour le statut du document vers SIGNING si c'est le premier signataire.

    Args:
        signature_request: Instance de AbstractSignatureRequest
        document_type: Type de document ("bail" ou "etat_lieux")
    """
    # Récupérer l'email du signataire
    email = signature_request.get_signataire_email()
    if not email:
        logger.error(f"Pas d'email pour {signature_request}")
        return False
    
    # Récupérer le document et mettre à jour son statut si c'est le premier signataire
    document = signature_request.get_document()
    if hasattr(document, 'status'):
        from signature.document_status import DocumentStatus
        # Si c'est le premier signataire (order = 1), passer en SIGNING
        if signature_request.order == 1 and document.status == DocumentStatus.DRAFT.value:
            document.status = DocumentStatus.SIGNING.value
            document.save()
            logger.info(f"Document {type(document).__name__} {document.id} passé en status SIGNING lors de l'envoi de l'OTP")

    # Convertir le document_type technique vers un nom lisible
    document_display_name = {
        "bail": "bail",
        "etat_lieux": "état des lieux",
    }.get(document_type, document_type)

    # Récupérer l'OTP généré
    otp = signature_request.otp
    if not otp:
        logger.error("Aucun OTP généré pour cette demande de signature")
        return False

    # Sujet et message spécifiques à l'OTP
    subject = f"🔏 Code {otp} - Signature de votre {document_display_name}"

    text_message = f"""
    Bonjour {signature_request.get_signataire_name()},

    Voici votre code de vérification (OTP) pour signer votre {document_display_name} :

    {otp}

    Ce code est valable pendant 10 minutes.

    Si vous n'avez pas demandé ce code, ignorez cet email.

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
            html_message=None,
            fail_silently=False,
        )
        logger.info(f"Email OTP envoyé à {email}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email OTP à {email}: {e}")
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


def create_signature_requests_generic(document, signature_request_model):
    """
    Fonction générique pour créer des demandes de signature pour un document.
    Fonctionne avec bail et état des lieux.

    Args:
        document: Instance du document signable (Bail, EtatLieux, etc.)
        signature_request_model: Modèle de demande de signature
    """
    # Déterminer le champ de relation vers le document
    document_field_name = None
    for field in signature_request_model._meta.get_fields():
        if field.is_relation and not field.many_to_many and not field.one_to_many:
            if hasattr(
                field.related_model, "_meta"
            ) and field.related_model._meta.model is type(document):
                document_field_name = field.name
                break

    if not document_field_name:
        raise ValueError(
            f"Impossible de trouver le champ de relation vers "
            f"{type(document)} dans {signature_request_model}"
        )

    # Supprimer les anciennes demandes de signature
    signature_request_model.objects.filter(**{document_field_name: document}).delete()

    # Déduire la location depuis le document

    location = document.location

    bailleurs = location.bien.bailleurs.all()
    bailleur_signataires = [
        bailleur.signataire for bailleur in bailleurs if bailleur.signataire
    ]
    locataires = list(location.locataires.all())

    order = 1

    # Créer les demandes pour les bailleurs signataires
    for signataire in bailleur_signataires:
        if signataire:
            signature_request_model.objects.create(
                **{
                    document_field_name: document,
                    "bailleur_signataire": signataire,
                    "order": order,
                    "otp": "",
                }
            )
            order += 1

    # Créer les demandes pour les locataires
    for locataire in locataires:
        signature_request_model.objects.create(
            **{
                document_field_name: document,
                "locataire": locataire,
                "order": order,
                "otp": "",
            }
        )
        order += 1

    logger.info(
        f"Créé {order - 1} demandes de signature pour "
        f"{type(document).__name__} {document.id}"
    )
