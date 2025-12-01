"""
Services partagés pour la signature de documents
"""

import logging

from django.conf import settings

from core.email_service import EmailService
from core.email_subjects import get_subject
from location.models import Bien

logger = logging.getLogger(__name__)


def _get_signataire_role(signature_request) -> str:
    """Détermine le rôle du signataire (bailleur, mandataire, locataire)."""
    if (
        hasattr(signature_request, "bailleur_signataire")
        and signature_request.bailleur_signataire
    ):
        return "bailleur"
    elif hasattr(signature_request, "mandataire") and signature_request.mandataire:
        return "mandataire"
    elif hasattr(signature_request, "locataire") and signature_request.locataire:
        return "locataire"
    return "bailleur"  # Fallback


def _get_document_config(document_type: str) -> dict:
    """Retourne la config pour un type de document."""
    configs = {
        "bail": {"display": "bail", "folder": "bail", "url_path": "bail"},
        "etat_lieux": {
            "display": "état des lieux",
            "folder": "edl",
            "url_path": "etat-lieux",
        },
    }
    return configs.get(
        document_type,
        {"display": document_type, "folder": document_type, "url_path": document_type},
    )


def _get_adresse_logement(document) -> str:
    """Récupère l'adresse du logement depuis le document."""
    if hasattr(document, "location") and document.location:
        bien: Bien = document.location.bien
        if bien and bien.adresse:
            return bien.adresse
    return ""


def send_signature_email(signature_request, document_type="document"):
    """
    Envoie un email avec le lien de signature (sans OTP - généré à l'accès)
    Le statut du document sera mis à jour vers SIGNING lors de l'envoi de l'OTP.

    Args:
        signature_request: Instance de AbstractSignatureRequest
        document_type: Type de document ("bail" ou "etat_lieux")
    """
    email = signature_request.get_signataire_email()
    if not email:
        logger.error(f"Pas d'email pour {signature_request}")
        return False

    role = _get_signataire_role(signature_request)
    config = _get_document_config(document_type)
    document = signature_request.get_document()

    # Construire l'URL de signature
    base_url = settings.FRONTEND_URL
    signature_url = (
        f"{base_url}/{config['url_path']}/signing/{signature_request.link_token}"
    )

    # Template et contexte
    template = f"{role}/{config['folder']}/demande_signature"
    context = {
        "prenom": signature_request.get_signataire_name(),
        "signature_url": signature_url,
        "document_type": config["display"],
        "adresse_logement": _get_adresse_logement(document),
        "lien_espace": f"{base_url}/mon-compte",
    }

    # Sujet depuis le mapping EMAIL_SUBJECTS
    subject = get_subject(template)

    success = EmailService.send(
        to=email,
        subject=subject,
        template=template,
        context=context,
    )

    if success:
        logger.info(f"Email de signature envoyé à {email}")
    else:
        logger.error(f"Erreur lors de l'envoi de l'email à {email}")

    return success


def send_otp_email(signature_request, document_type="document"):
    """
    Envoie un email avec le code OTP pour la signature.
    Met à jour le statut du document vers SIGNING si c'est le premier signataire.

    Args:
        signature_request: Instance de AbstractSignatureRequest
        document_type: Type de document ("bail" ou "etat_lieux")
    """
    email = signature_request.get_signataire_email()
    if not email:
        logger.error(f"Pas d'email pour {signature_request}")
        return False

    # Récupérer le document et mettre à jour son statut si c'est le premier signataire
    document = signature_request.get_document()
    if hasattr(document, "status"):
        from signature.document_status import DocumentStatus

        if (
            signature_request.order == 1
            and document.status == DocumentStatus.DRAFT.value
        ):
            document.status = DocumentStatus.SIGNING.value
            document.save()
            logger.info(
                f"Document {type(document).__name__} {document.id} passé en status SIGNING"
            )

    otp = signature_request.otp
    if not otp:
        logger.error("Aucun OTP généré pour cette demande de signature")
        return False

    role = _get_signataire_role(signature_request)
    config = _get_document_config(document_type)

    # Utiliser le template OTP commun
    context = {
        "prenom": signature_request.get_signataire_name(),
        "otp": otp,
        "role": role,
        "document_type": config["display"],
    }

    success = EmailService.send(
        to=email,
        subject=f"🔏 Code {otp} - Signature de votre {config['display']}",
        template="common/otp_signature",
        context=context,
    )

    if success:
        logger.info(f"Email OTP envoyé à {email}")
    else:
        logger.error(f"Erreur lors de l'envoi de l'email OTP à {email}")

    return success


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


def create_signature_requests_generic(document, signature_request_model, user=None):
    """
    Fonction générique pour créer des demandes de signature pour un document.
    Fonctionne avec bail et état des lieux.

    Ordre de signature:
    1. User créateur (celui qui a généré le document) - order=1
    2. Mandataire (si existe et différent du user)
    3. Bailleurs signataires (si différents du user)
    4. Locataires (si différents du user)

    Args:
        document: Instance du document signable (Bail, EtatLieux, etc.)
        signature_request_model: Modèle de demande de signature
        user: User qui a créé le document (sera le premier signataire)
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

    # IMPORTANT: Ordre déterministe (premier créé = principal)
    bailleurs = location.bien.bailleurs.order_by("created_at")
    bailleur_signataires = [
        bailleur.signataire for bailleur in bailleurs if bailleur.signataire
    ]
    locataires = list(location.locataires.all())

    order = 1
    user_email = user.email.lower() if user else None

    # Vérifier si le mandataire doit signer ce document
    mandataire_doit_signer = (
        hasattr(document, "mandataire_doit_signer")
        and document.mandataire_doit_signer
        and location.mandataire
    )

    # ÉTAPE 1: Le user créateur signe en premier (si fourni)
    if user and user_email:
        # Identifier le type de signataire du user
        # Vérifier si c'est le mandataire
        if (
            mandataire_doit_signer
            and location.mandataire.signataire.email.lower() == user_email
        ):
            signature_request_model.objects.create(
                **{
                    document_field_name: document,
                    "mandataire": location.mandataire,
                    "order": order,
                    "otp": "",
                }
            )
            order += 1
            logger.info(
                f"User créateur (mandataire) ajouté en premier signataire (order={order - 1}) "
                f"pour {type(document).__name__} {document.id}"
            )
        # Vérifier si c'est un bailleur
        elif any(
            sig and sig.email.lower() == user_email for sig in bailleur_signataires
        ):
            signataire = next(
                sig
                for sig in bailleur_signataires
                if sig and sig.email.lower() == user_email
            )
            signature_request_model.objects.create(
                **{
                    document_field_name: document,
                    "bailleur_signataire": signataire,
                    "order": order,
                    "otp": "",
                }
            )
            order += 1
            logger.info(
                f"User créateur (bailleur) ajouté en premier signataire (order={order - 1}) "
                f"pour {type(document).__name__} {document.id}"
            )
        # Vérifier si c'est un locataire
        elif any(loc.email.lower() == user_email for loc in locataires):
            locataire = next(
                loc for loc in locataires if loc.email.lower() == user_email
            )
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
                f"User créateur (locataire) ajouté en premier signataire (order={order - 1}) "
                f"pour {type(document).__name__} {document.id}"
            )

    # ÉTAPE 2: Mandataire (si pas déjà ajouté comme user créateur)
    if mandataire_doit_signer:
        mandataire_email = location.mandataire.signataire.email.lower()
        if not (user_email and mandataire_email == user_email):
            signature_request_model.objects.create(
                **{
                    document_field_name: document,
                    "mandataire": location.mandataire,
                    "order": order,
                    "otp": "",
                }
            )
            order += 1
            logger.info(
                f"Mandataire ajouté comme signataire (order={order - 1}) "
                f"pour {type(document).__name__} {document.id}"
            )

    # ÉTAPE 3: Bailleurs signataires (si pas déjà ajouté comme user créateur)
    for signataire in bailleur_signataires:
        if signataire:
            signataire_email = signataire.email.lower()
            if not (user_email and signataire_email == user_email):
                signature_request_model.objects.create(
                    **{
                        document_field_name: document,
                        "bailleur_signataire": signataire,
                        "order": order,
                        "otp": "",
                    }
                )
                order += 1

    # ÉTAPE 4: Locataires (si pas déjà ajouté comme user créateur)
    for locataire in locataires:
        locataire_email = locataire.email.lower()
        if not (user_email and locataire_email == user_email):
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
