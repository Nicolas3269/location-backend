"""
Services partagés pour la signature de documents
"""

import logging

from django.conf import settings

from core.email_service import EmailService
from core.email_subjects import get_subject
from core.url_builders import (
    get_bailleur_id_from_location,
    get_location_url,
)
from location.constants import UserRole
from location.models import Bien
from location.templatetags.french_grammar import avec_de
from signature.models import AbstractSignatureRequest

logger = logging.getLogger(__name__)


def _get_signataire_role(signature_request) -> UserRole:
    """Détermine le rôle du signataire (bailleur, mandataire, locataire)."""
    if (
        hasattr(signature_request, "bailleur_signataire")
        and signature_request.bailleur_signataire
    ):
        return UserRole.BAILLEUR
    elif hasattr(signature_request, "mandataire") and signature_request.mandataire:
        return UserRole.MANDATAIRE
    elif hasattr(signature_request, "locataire") and signature_request.locataire:
        return UserRole.LOCATAIRE
    return UserRole.BAILLEUR  # Fallback


def _get_document_config(document_type: str) -> dict:
    """Retourne la config pour un type de document."""
    configs = {
        "bail": {
            "display": "bail",
            "folder": "bail",
            "url_path": "bail",
            "signed_template": "bail_signe",
        },
        "etat_lieux": {
            "display": "état des lieux",
            "folder": "edl",
            "url_path": "etat-lieux",
            "signed_template": "signe",
        },
        "avenant": {
            "display": "avenant",
            "folder": "avenant",
            "url_path": "avenant",
            "signed_template": "signe",
        },
    }
    return configs.get(
        document_type,
        {
            "display": document_type,
            "folder": document_type,
            "url_path": document_type,
            "signed_template": "signe",
        },
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
        "prenom": signature_request.get_signataire_first_name(),
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
        "prenom": signature_request.get_signataire_first_name(),
        "otp": otp,
        "role": role,
        "document_type": config["display"],
    }

    # Sujet avec OTP visible (ex: "🔏 Code 123456 - Signature de votre bail")
    subject = f"🔏 Code {otp} - Signature de votre {config['display']}"

    success = EmailService.send(
        to=email,
        subject=subject,
        template="common/otp_signature",
        context=context,
    )

    if success:
        logger.info(f"Email OTP envoyé à {email}")
    else:
        logger.error(f"Erreur lors de l'envoi de l'email OTP à {email}")

    return success


def send_document_signed_emails(document, document_type="bail"):
    """
    Envoie un email à toutes les parties pour les informer que le document est signé.

    Args:
        document: Instance du document signable (Bail, EtatLieux, etc.)
        document_type: Type de document ("bail", "etat_lieux", "avenant")
    """
    config = _get_document_config(document_type)
    base_url = settings.FRONTEND_URL

    # Récupérer les IDs pour construire les liens
    location = document.location
    location_id = str(location.id) if location else None
    bien_id = str(location.bien.id) if location and location.bien else None
    bailleur_id = get_bailleur_id_from_location(location)

    # Récupérer toutes les demandes de signature pour ce document
    signature_requests = document.signature_requests.all()

    for sig_request in signature_requests:
        email = sig_request.get_signataire_email()
        if not email:
            continue

        role = _get_signataire_role(sig_request)

        # Template spécifique pour locataire/EDL (entrée vs sortie)
        if role == UserRole.LOCATAIRE and document_type == "etat_lieux":
            from etat_lieux.models import EtatLieuxType

            if document.type_etat_lieux == EtatLieuxType.ENTREE:
                template_name = "entree_signe"
            elif document.type_etat_lieux == EtatLieuxType.SORTIE:
                template_name = "sortie_signe"
            else:
                raise ValueError(f"Type EDL inconnu: {document.type_etat_lieux}")
        else:
            template_name = config["signed_template"]

        template = f"{role}/{config['folder']}/{template_name}"

        # Construire le lien vers l'espace selon le rôle
        lien_espace = get_location_url(role, location_id, bien_id, bailleur_id)

        context = {
            "prenom": sig_request.get_signataire_first_name(),
            "lien_espace": lien_espace,
        }

        # Contexte spécifique selon le rôle et le type de document
        if role in (UserRole.BAILLEUR, UserRole.MANDATAIRE):
            if document_type == "bail" and location_id:
                # Lien vers la page documents où le bouton EDL est disponible
                context["lien_edl"] = lien_espace
            elif role == UserRole.MANDATAIRE:
                # Lien vers la page services pour les mandataires
                context["lien_services"] = f"{base_url}/services"
            else:
                # Lien vers la page assurances pour les bailleurs
                context["lien_services"] = f"{base_url}/assurances"
        elif role == UserRole.LOCATAIRE:
            # Offres partenaires (déménagement, etc.) → page de notification
            context["lien_partenaires"] = (
                f"{base_url}/me-notifier?topic=demenagement&role={UserRole.LOCATAIRE}"
            )

        subject = get_subject(template)

        success = EmailService.send(
            to=email,
            subject=subject,
            template=template,
            context=context,
        )

        if success:
            logger.info(f"Email 'document signé' envoyé à {email} ({role})")
        else:
            logger.error(f"Erreur envoi email 'document signé' à {email}")


def send_signature_cancelled_emails(signature_requests, document, document_type="bail"):
    """
    Envoie un email à toutes les parties pour les informer que la signature a été annulée.
    IMPORTANT: Appeler AVANT de supprimer les signature_requests.

    N'envoie qu'aux personnes qui ont déjà signé OU qui sont en train de signer
    (pas à ceux qui n'ont jamais reçu de lien de signature).

    Args:
        signature_requests: QuerySet des signature requests (avant suppression)
        document: Instance du document signable (Bail, EtatLieux, etc.)
        document_type: Type de document ("bail", "etat_lieux", "avenant")
    """
    config = _get_document_config(document_type)
    adresse = _get_adresse_logement(document)

    # Récupérer les IDs pour construire les liens
    location = document.location
    location_id = str(location.id) if location else None
    bien_id = str(location.bien.id) if location and location.bien else None
    bailleur_id = get_bailleur_id_from_location(location)

    # Trouver le prochain signataire en attente (celui qui a reçu le lien)
    next_signer = signature_requests.filter(signed=False).order_by("order").first()
    next_order = next_signer.order if next_signer else float("inf")

    # Filtrer: ceux qui ont signé OU le signataire actuel
    signataires_a_notifier = [
        sig for sig in signature_requests if sig.signed or sig.order == next_order
    ]

    for sig_request in signataires_a_notifier:
        email = sig_request.get_signataire_email()
        if not email:
            continue

        role = _get_signataire_role(sig_request)

        # Construire le lien vers l'espace selon le rôle
        lien_espace = get_location_url(role, location_id, bien_id, bailleur_id)

        context = {
            "prenom": sig_request.get_signataire_first_name(),
            "document_type": config["display"],
            "adresse": adresse,
            "lien_espace": lien_espace,
        }

        subject = get_subject(
            "common/annulation_signature",
            document_type=avec_de(config["display"]),
        )

        success = EmailService.send(
            to=email,
            subject=subject,
            template="common/annulation_signature",
            context=context,
        )

        if success:
            logger.info(f"Email 'signature annulée' envoyé à {email}")
        else:
            logger.error(f"Erreur envoi email 'signature annulée' à {email}")


def send_signature_confirmation_email(
    signature_request, document, document_type="bail"
):
    """
    Envoie un email de confirmation après signature.
    NE PAS appeler pour le dernier signataire (il recevra l'email "document signé").

    Args:
        signature_request: Instance de SignatureRequest qui vient de signer
        document: Instance du document signable (Bail, EtatLieux, etc.)
        document_type: Type de document ("bail", "etat_lieux", "avenant")
    """
    email = signature_request.get_signataire_email()
    if not email:
        return

    config = _get_document_config(document_type)
    role = _get_signataire_role(signature_request)

    # Récupérer les IDs pour construire les liens
    location = document.location
    location_id = str(location.id) if location else None
    bien_id = str(location.bien.id) if location and location.bien else None
    bailleur_id = get_bailleur_id_from_location(location)

    # Récupérer toutes les signature requests du document
    sig_requests: list[AbstractSignatureRequest] = (
        document.signature_requests.all().order_by("order")
    )

    # Construire la liste des signataires ayant signé
    signataires_signes = []
    for sig in sig_requests.filter(signed=True):
        signataire_info = {
            "nom": sig.get_signataire_name(),
        }
        if sig.signed_at:
            signataire_info["date"] = sig.signed_at.strftime("%d/%m/%Y à %H:%M")
        signataires_signes.append(signataire_info)

    # Construire la liste des signataires restants
    signataires_restants = []
    prochain_signataire = None
    for sig in sig_requests.filter(signed=False).order_by("order"):
        signataire_info = {
            "nom": sig.get_signataire_name(),
        }
        signataires_restants.append(signataire_info)
        if prochain_signataire is None:
            prochain_signataire = signataire_info

    # Construire le lien vers l'espace selon le rôle
    lien_espace = get_location_url(role, location_id, bien_id, bailleur_id)

    context = {
        "prenom": signature_request.get_signataire_first_name(),
        "role": role,
        "document_type": config["display"],
        "signataires_signes": signataires_signes,
        "signataires_restants": signataires_restants,
        "prochain_signataire": prochain_signataire,
        "lien_espace": lien_espace,
    }

    subject = get_subject(
        "common/post_signature",
        document_type=avec_de(config["display"]),
    )

    success = EmailService.send(
        to=email,
        subject=subject,
        template="common/post_signature",
        context=context,
    )

    if success:
        logger.info(f"Email 'confirmation signature' envoyé à {email}")
    else:
        logger.error(f"Erreur envoi email 'confirmation signature' à {email}")


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
