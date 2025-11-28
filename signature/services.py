"""
Services partagés pour la signature de documents
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_signature_email(signature_request, document_type="document"):
    """
    Envoie un email avec le lien de signature (sans OTP - généré à l'accès)
    Le statut du document sera mis à jour vers SIGNING lors de l'envoi de l'OTP.

    Args:
        signature_request: Instance de AbstractSignatureRequest
        document_type: Type de document ("bail" ou "etat_lieux")
    """
    # Récupérer l'email du signataire
    email = signature_request.get_signataire_email()
    if not email:
        logger.error(f"Pas d'email pour {signature_request}")
        return False

    # Récupérer le prénom du signataire
    signer = signature_request.signer
    prenom = signer.firstName if signer else "Signataire"

    # Récupérer le document et l'adresse du bien
    document = signature_request.get_document()
    adresse_logement = ""
    if hasattr(document, "location") and document.location:
        bien = document.location.bien
        if bien:
            adresse_logement = bien.adresse or ""

    # Convertir le document_type technique vers un nom lisible
    document_display_name = {
        "bail": "bail de location",
        "etat_lieux": "état des lieux",
        "avenant": "avenant au bail",
    }.get(document_type, document_type)

    # Construire les URLs
    base_url = settings.FRONTEND_URL
    espace_personnel_url = f"{base_url}/mon-compte"

    if document_type == "bail":
        signature_url = f"{base_url}/bail/signing/{signature_request.link_token}"
        subject = "Votre signature est requise pour le bail ✍️"
    elif document_type == "etat_lieux":
        signature_url = f"{base_url}/etat-lieux/signing/{signature_request.link_token}"
        subject = "Votre signature est requise pour l'état des lieux ✍️"
    elif document_type == "avenant":
        signature_url = f"{base_url}/avenant/signing/{signature_request.link_token}"
        subject = "Votre signature est requise pour l'avenant ✍️"
    else:
        signature_url = (
            f"{base_url}/{document_type}/signing/{signature_request.link_token}"
        )
        subject = f"Votre signature est requise pour le {document_display_name} ✍️"

    # Construire le message avec l'adresse si disponible
    if adresse_logement:
        intro_logement = (
            f"Vous êtes invité(e) à signer le {document_display_name} "
            f"concernant le logement situé au {adresse_logement}."
        )
    else:
        intro_logement = f"Vous êtes invité(e) à signer le {document_display_name}."

    text_message = f"""
Bonjour {prenom},

{intro_logement}

👉 Signer le document : {signature_url}

La signature est sécurisée, personnelle et ne prend que 2 minutes.

Une fois votre signature apposée :
- le document sera transmis au signataire suivant (s'il y en a) ;
- vous recevrez un email de confirmation ;
- le document complet sera disponible dans votre espace personnel.

👉 Accéder à votre espace : {espace_personnel_url}

Si vous avez des questions, nous sommes là pour vous aider.

L'équipe Hestia 🏡
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

    # Récupérer le prénom du signataire
    signer = signature_request.signer
    prenom = signer.firstName if signer else "Signataire"

    # Récupérer le document et mettre à jour son statut si c'est le premier signataire
    document = signature_request.get_document()
    if hasattr(document, "status"):
        from signature.document_status import DocumentStatus

        # Si c'est le premier signataire (order = 1), passer en SIGNING
        if (
            signature_request.order == 1
            and document.status == DocumentStatus.DRAFT.value
        ):
            document.status = DocumentStatus.SIGNING.value
            document.save()
            logger.info(
                f"Document {type(document).__name__} {document.id} passé en status SIGNING lors de l'envoi de l'OTP"
            )

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
    Bonjour {prenom},

    Voici votre code de vérification (OTP) pour signer votre {document_display_name} :

    {otp}

    ⏱️ Ce code est personnel et valable 10 minutes.

    Il garantit la sécurité de votre signature électronique, conforme à la réglementation en vigueur. 

    Saisissez-le dans l’interface de signature pour valider votre engagement.

    👉 Si vous n’avez pas fait cette demande, vous pouvez ignorer ce message.

    À très vite,
    L’équipe Hestia 🏡
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


def send_signature_success_email(
    signature_request, document_type="document", next_signer=None
):
    """
    Envoie un email de confirmation au signataire après une signature réussie.

    Inclut:
    - Liste des personnes ayant déjà signé
    - Liste des personnes devant encore signer
    - Indication du prochain signataire
    - Lien vers l'espace personnel

    Args:
        signature_request: Instance de AbstractSignatureRequest (vient de signer)
        document_type: Type de document ("bail", "etat_lieux", "avenant")
        next_signer: Prochaine signature request (optionnel, récupéré si non fourni)
    """
    # Récupérer l'email du signataire
    email = signature_request.get_signataire_email()
    if not email:
        logger.error(f"Pas d'email pour {signature_request}")
        return False

    # Récupérer le prénom du signataire
    signer = signature_request.signer
    prenom = signer.firstName if signer else "Signataire"

    # Récupérer le document
    document = signature_request.get_document()

    # Récupérer toutes les signature requests pour ce document
    all_signature_requests = list(document.signature_requests.all().order_by("order"))

    # Séparer ceux qui ont signé et ceux qui doivent encore signer
    signed_requests = [sr for sr in all_signature_requests if sr.signed]
    pending_requests = [sr for sr in all_signature_requests if not sr.signed]

    # Formater les listes
    signed_list = [sr.get_signataire_name() for sr in signed_requests]
    pending_list = [sr.get_signataire_name() for sr in pending_requests]

    # Prochain signataire
    if next_signer is None:
        next_signer = signature_request.get_next_signature_request()

    next_signer_name = next_signer.get_signataire_name() if next_signer else None

    # Convertir le document_type technique vers un nom lisible
    document_display_name = {
        "bail": "bail",
        "etat_lieux": "état des lieux",
        "avenant": "avenant",
    }.get(document_type, document_type)

    # Construire l'URL de l'espace personnel
    base_url = settings.FRONTEND_URL
    espace_personnel_url = f"{base_url}/mon-compte"

    # Déterminer le sujet selon le type de document
    subject = "Votre signature est bien enregistrée ✔️"

    # Construire les listes formatées pour l'email
    if signed_list:
        signed_list_text = "\n".join([f"- {name}" for name in signed_list])
    else:
        signed_list_text = "- (aucun)"

    if pending_list:
        pending_list_text = "\n".join([f"- {name}" for name in pending_list])
    else:
        pending_list_text = "- (aucun - toutes les signatures sont complètes !)"

    # Message texte
    if pending_requests and next_signer_name:
        # Il reste des signataires
        text_message = f"""
Bonjour {prenom},

Bravo 🎉

Vous venez de signer électroniquement votre {document_display_name} — merci pour votre réactivité !

Voici un point complet sur l'avancement des signatures :

✅ Ont déjà signé :
{signed_list_text}

✍️ Doivent encore signer :
{pending_list_text}

👉 Le prochain à signer sera :
{next_signer_name}

Le signataire vient de recevoir automatiquement son lien sécurisé de signature.

---

Pour votre information, vous pouvez à tout moment :

📄 Télécharger le document actuel (version provisoire)
👀 Suivre l'avancement des signatures en temps réel
🗂️ Retrouver tous vos documents ({document_display_name}, annexes, pièces justificatives)

En accédant à votre espace personnel : {espace_personnel_url}

⚠️ Rappel important : le {document_display_name} ne sera juridiquement valable qu'une fois l'ensemble des signataires passés.

Nous vous enverrons un email dès que toutes les signatures seront terminées.

Merci pour votre confiance,

L'équipe Hestia 🏡
"""
    else:
        # Toutes les signatures sont complètes !
        text_message = f"""
Bonjour {prenom},

Bravo 🎉

Vous venez de signer électroniquement votre {document_display_name} — merci pour votre réactivité !

🎊 Excellente nouvelle : toutes les signatures sont désormais complètes !

✅ Ont signé :
{signed_list_text}

Votre {document_display_name} est maintenant juridiquement valable.

---

Vous pouvez à tout moment :

📄 Télécharger le document final signé
🗂️ Retrouver tous vos documents ({document_display_name}, annexes, pièces justificatives)

En accédant à votre espace personnel : {espace_personnel_url}

Merci pour votre confiance,

L'équipe Hestia 🏡
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
        logger.info(f"Email de confirmation de signature envoyé à {email}")
        return True
    except Exception as e:
        logger.error(
            f"Erreur lors de l'envoi de l'email de confirmation à {email}: {e}"
        )
        return False


def send_all_signed_notification(document, document_type="document"):
    """
    Envoie un email à TOUS les signataires quand le document est complètement signé.

    Args:
        document: Le document signable (Bail, EtatLieux, etc.)
        document_type: Type de document ("bail", "etat_lieux", "avenant")
    """
    # Récupérer toutes les signature requests
    all_signature_requests = list(document.signature_requests.all().order_by("order"))

    if not all_signature_requests:
        logger.warning(f"Aucune signature request pour {document}")
        return False

    # Vérifier que toutes les signatures sont complètes
    if not all(sr.signed for sr in all_signature_requests):
        logger.warning(
            f"Document {document} n'est pas complètement signé, "
            "notification non envoyée"
        )
        return False

    # Convertir le document_type technique vers un nom lisible
    document_display_name = {
        "bail": "bail",
        "etat_lieux": "état des lieux",
        "avenant": "avenant",
    }.get(document_type, document_type)

    # Construire les URLs
    base_url = settings.FRONTEND_URL
    espace_personnel_url = f"{base_url}/mon-compte"

    # Liste des signataires formatée
    signers_list = [sr.get_signataire_name() for sr in all_signature_requests]
    signers_list_text = "\n".join([f"- {name}" for name in signers_list])

    # Sujet de l'email
    subject = (
        f"Votre {document_display_name} est maintenant signé par toutes les parties ✅"
    )

    success_count = 0

    # Envoyer à chaque signataire
    for sig_req in all_signature_requests:
        email = sig_req.get_signataire_email()
        if not email:
            continue

        signer = sig_req.signer
        prenom = signer.firstName if signer else "Signataire"

        # Déterminer le rôle du signataire
        is_locataire = sig_req.locataire is not None
        is_bailleur_or_mandataire = (
            sig_req.bailleur_signataire is not None or sig_req.mandataire is not None
        )

        # Message différent selon le type de document
        if document_type == "bail":
            # Base du message commune à tous
            base_message = f"""
Bonjour {prenom},

Bonne nouvelle : toutes les parties viennent de signer électroniquement le bail.

👉 Le contrat est désormais valable juridiquement.

✅ Ont signé :
{signers_list_text}

Vous trouverez le bail signé par toutes les parties dans votre espace Hestia :
{espace_personnel_url}
"""
            # Section "Et maintenant" uniquement pour bailleur/mandataire
            if is_bailleur_or_mandataire:
                next_step_section = """
Et maintenant ?

La prochaine étape consiste à réaliser l'état des lieux d'entrée.
Celui-ci est obligatoire et permet de comparer l'état du logement à l'entrée et à la sortie du locataire.

Avec Hestia, vous pouvez générer votre état des lieux en quelques clics depuis votre location dans votre espace personnel.
"""
            elif is_locataire:
                next_step_section = """
Et maintenant ?

La prochaine étape sera la réalisation de l'état des lieux d'entrée avec votre bailleur ou mandataire. Celui-ci est obligatoire et permet de comparer l'état du logement à l'entrée et à la sortie.
"""
            else:
                next_step_section = ""

            text_message = (
                base_message
                + next_step_section
                + """
Nous restons à vos côtés pour simplifier chaque étape de la gestion locative.

Bien cordialement,

L'équipe Hestia 🏡
"""
            )
        elif document_type == "etat_lieux":
            text_message = f"""
Bonjour {prenom},

Bonne nouvelle : toutes les parties viennent de signer électroniquement l'état des lieux.

👉 Le document est désormais valable juridiquement.

✅ Ont signé :
{signers_list_text}

Vous trouverez l'état des lieux signé par toutes les parties dans votre espace Hestia :
{espace_personnel_url}

Nous restons à vos côtés pour simplifier chaque étape de la gestion locative.

Bien cordialement,

L'équipe Hestia 🏡
"""
        else:
            text_message = f"""
Bonjour {prenom},

Bonne nouvelle : toutes les parties viennent de signer électroniquement le {document_display_name}.

👉 Le document est désormais valable juridiquement.

✅ Ont signé :
{signers_list_text}

Vous trouverez le document signé par toutes les parties dans votre espace Hestia :
{espace_personnel_url}

Nous restons à vos côtés pour simplifier chaque étape de la gestion locative.

Bien cordialement,

L'équipe Hestia 🏡
"""

        try:
            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=None,
                fail_silently=False,
            )
            logger.info(f"Email de notification 'tout signé' envoyé à {email}")
            success_count += 1
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de la notification à {email}: {e}")

    total = len(all_signature_requests)
    logger.info(f"Notifications 'tout signé' envoyées: {success_count}/{total}")
    return success_count > 0
