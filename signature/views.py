"""
Vues génériques pour la signature de documents
"""

import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from authentication.utils import get_tokens_for_user, set_refresh_token_cookie
from bail.models import Avenant
from location.models import Location
from location.services.access_utils import get_user_role_for_location
from location.services.bailleur_utils import get_primary_bailleur_for_user
from signature.document_status import DocumentStatus
from signature.models import AbstractSignatureRequest
from signature.models_base import SignableDocumentMixin

from .document_list_service import get_etat_lieux_documents_list
from .pdf_processing import process_signature_generic

# Envoyer l'OTP par email
from .services import (
    cancel_document_signature,
    get_next_signer,
    send_otp_email,
    send_signature_cancelled_emails,
    send_signature_email,
    verify_signature_order,
)

logger = logging.getLogger(__name__)


def get_signature_request_generic(request, token, model_class):
    """
    Vue générique pour récupérer les informations d'une demande de signature

    Args:
        request: HttpRequest
        token: Token de signature
        model_class: Classe du modèle de signature
    """
    # Chercher avec all_objects (inclut les annulés) pour distinguer les cas
    sig_req: AbstractSignatureRequest | None = model_class.all_objects.filter(
        link_token=token
    ).first()

    if sig_req is None:
        # Token vraiment inexistant
        return JsonResponse(
            {
                "error": "Ce lien de signature n'est plus valide.",
                "token_not_found": True,
            },
            status=404,
        )

    if sig_req.is_cancelled:
        # Demande annulée (soft deleted)
        contact_info = sig_req.get_contact_info()
        return JsonResponse(
            {
                "error": "Cette demande de signature a été annulée.",
                "cancelled": True,
                "contact": contact_info,
            },
            status=410,  # 410 Gone - ressource n'existe plus
        )

    # À partir d'ici, sig_req existe - les erreurs sont de vraies erreurs techniques
    try:
        if sig_req.signed:
            return JsonResponse(
                {
                    "error": "Ce document a déjà été signé",
                    "already_signed": True,
                },
                status=400,
            )

        # Vérifier que c'est bien son tour
        if not verify_signature_order(sig_req):
            return JsonResponse(
                {
                    "error": "Ce n'est pas encore votre tour de signer",
                    "not_your_turn": True,
                },
                status=403,
            )

        # Récupérer le document
        document = sig_req.get_document()

        # Préparer les données de réponse
        # Fallback pour page_title si non implémenté
        try:
            page_title = sig_req.get_page_title()
        except (NotImplementedError, AttributeError):
            page_title = "Signature du document"

        response_data = {
            "success": True,
            "signataire": sig_req.get_signataire_name(),
            "document_name": sig_req.get_document_name(),
            "page_title": page_title,
            "order": sig_req.order,
        }

        # Ajouter l'URL du PDF si disponible
        if hasattr(document, "pdf") and document.pdf:
            response_data["pdfUrl"] = document.pdf.url

        # Générer et envoyer un OTP seulement si demandé explicitement
        # (via query param send_otp=true)
        # Ne PAS envoyer automatiquement si l'OTP est vide
        send_otp_param = request.GET.get("send_otp", "false").lower() == "true"
        should_send_otp = send_otp_param

        if should_send_otp:
            sig_req.generate_otp()

            document_type = sig_req.get_document_type()
            send_otp_email(sig_req, document_type)

        # Préparer les données du signataire (utilise la propriété signer qui gère mandataire)
        person = sig_req.signer
        signer_email = sig_req.get_signataire_email()

        # Préparer la réponse dans le nouveau format unifié
        # Note: On utilise is_locataire (français) pour cohérence avec is_mandataire et is_bailleur
        response_data.update(
            {
                "success": True,
                "person": {
                    "email": signer_email,
                    "first_name": person.firstName if person else "",
                    "last_name": person.lastName if person else "",
                },
                "otp_sent": should_send_otp,
                "is_locataire": bool(sig_req.locataire),
                "is_mandataire": bool(sig_req.mandataire),
                "is_bailleur": bool(sig_req.bailleur_signataire),
            }
        )

        # Si c'est un locataire, vérifier le statut des documents via Document model
        if sig_req.locataire:
            from bail.models import Document, DocumentType

            locataire = sig_req.locataire
            response_data["locataire_id"] = str(locataire.id)

            # Récupérer les documents MRH et Caution via le modèle Document
            mrh_docs = Document.objects.filter(
                locataire=locataire, type_document=DocumentType.ATTESTATION_MRH
            )
            caution_docs = Document.objects.filter(
                locataire=locataire, type_document=DocumentType.CAUTION_SOLIDAIRE
            )

            # Format liste pour les fichiers MRH
            mrh_files = [
                {
                    "id": str(doc.id),
                    "name": doc.nom_original,
                    "url": doc.file.url,
                    "type": "Attestation MRH",
                }
                for doc in mrh_docs
            ]

            # Format liste pour les fichiers Caution
            caution_files = [
                {
                    "id": str(doc.id),
                    "name": doc.nom_original,
                    "url": doc.file.url,
                    "type": "Caution solidaire",
                }
                for doc in caution_docs
            ]

            response_data["documents_required"] = {
                "mrh_required": True,
                "caution_required": locataire.caution_requise,
                "mrh_files": mrh_files,
                "caution_files": caution_files,
                # Garder pour rétrocompatibilité
                "mrh_uploaded": len(mrh_files) > 0,
                "caution_uploaded": len(caution_files) > 0,
            }

        # Ajouter l'ID du document selon le type et le location_id
        if hasattr(sig_req, "bail"):
            bail = sig_req.bail
            response_data["bail_id"] = bail.id
            response_data["location_id"] = str(bail.location_id)

            # Ajouter le régime juridique du bien pour les assurances
            if bail.location and bail.location.bien:
                response_data["regime_juridique"] = bail.location.bien.regime_juridique

            # Ajouter la liste des documents du dossier de location
            from .document_list_service import get_bail_documents_list

            response_data["documents_list"] = get_bail_documents_list(bail, request)

        elif hasattr(sig_req, "etat_lieux"):
            etat_lieux = sig_req.etat_lieux
            response_data["etat_lieux_id"] = etat_lieux.id
            response_data["location_id"] = str(etat_lieux.location_id)

            # Ajouter le régime juridique du bien pour les assurances
            if etat_lieux.location and etat_lieux.location.bien:
                response_data["regime_juridique"] = (
                    etat_lieux.location.bien.regime_juridique
                )

            # Ajouter la liste des documents de l'état des lieux

            response_data["documents_list"] = get_etat_lieux_documents_list(
                etat_lieux, request
            )

        elif hasattr(sig_req, "avenant"):
            avenant: Avenant = sig_req.avenant
            response_data["avenant_id"] = str(avenant.id)
            response_data["location_id"] = str(avenant.bail.location_id)

            # Ajouter le régime juridique du bien pour les assurances
            if avenant.bail.location and avenant.bail.location.bien:
                response_data["regime_juridique"] = (
                    avenant.bail.location.bien.regime_juridique
                )

            # Ajouter la liste des documents de l'avenant
            from .document_list_service import get_avenant_documents_list

            response_data["documents_list"] = get_avenant_documents_list(
                avenant, request
            )

        elif hasattr(sig_req, "quotation"):
            quotation = sig_req.quotation
            response_data["quotation_id"] = str(quotation.id)
            response_data["location_id"] = str(quotation.location_id)

        # Tenter d'authentifier automatiquement l'utilisateur
        User = get_user_model()
        try:
            user = User.objects.get(email=signer_email)
            tokens = get_tokens_for_user(user)

            # Ajouter les infos utilisateur
            response_data["user"] = {"email": user.email}

            # Créer la réponse avec le refresh token en cookie
            response = JsonResponse(response_data)
            set_refresh_token_cookie(response, tokens["refresh"])

            logger.info(f"Auto-authentication successful for {signer_email}")
            return response

        except User.DoesNotExist:
            logger.info(f"No user account found for {signer_email}")
            # L'utilisateur n'a pas de compte, retourner sans authentification
            return JsonResponse(response_data)

    except Exception as e:
        logger.exception(
            f"Erreur lors de la récupération de la demande de signature: {e}"
        )
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=500,
        )


def confirm_signature_generic(request, model_class, document_type):
    """
    Vue générique pour confirmer une signature

    Args:
        request: HttpRequest
        model_class: Classe du modèle de signature
        document_type: Type de document ("bail" ou "etat_lieux")
    """
    try:
        data = request.data
        token = data.get("token")
        otp = data.get("otp")
        signature_data_url = data.get("signatureImage")

        if not token or not otp:
            return JsonResponse(
                {"error": "Données manquantes (token ou OTP)"},
                status=400,
            )

        sig_req: AbstractSignatureRequest = get_object_or_404(
            model_class, link_token=token
        )

        if sig_req.signed:
            return JsonResponse({"error": "Déjà signé"}, status=400)

        # Vérifier que l'OTP est valide
        if not sig_req.is_otp_valid(otp):
            return JsonResponse(
                {"error": "Code OTP invalide ou expiré"},
                status=403,
            )

        # Vérifier que c'est bien son tour
        if not verify_signature_order(sig_req):
            return JsonResponse(
                {"error": "Ce n'est pas encore votre tour"},
                status=403,
            )

        # La signature manuscrite est OBLIGATOIRE pour :
        # 1. Créer les métadonnées forensiques (SignatureMetadata)
        # 2. Signer le PDF avec le tampon visuel
        # 3. Garantir la validité juridique (eIDAS AES)
        if not signature_data_url:
            return JsonResponse(
                {"error": "Image de signature manuscrite requise"},
                status=400,
            )

        # Mettre à jour le statut vers SIGNING si c'est le premier signataire
        # Note: Fait ici (pas dans send_otp_email) pour permettre à l'utilisateur
        # de revenir en arrière et éditer après avoir cliqué "Signer"
        document = sig_req.get_document()
        if hasattr(document, "status"):
            if (
                sig_req.order == 1
                and document.status == DocumentStatus.DRAFT.value
            ):
                document.status = DocumentStatus.SIGNING.value
                document.save()
                logger.info(
                    f"Document {type(document).__name__} {document.id} passé en status SIGNING"
                )

        # process_signature_generic s'occupera de mark_as_signed()
        # Passer la request pour capturer métadonnées HTTP (IP, user-agent)
        process_signature_generic(sig_req, signature_data_url, request=request)

        # Récupérer le document
        document: SignableDocumentMixin = sig_req.get_document()

        # Envoi au suivant - utiliser la fonction générique pour tous les types
        next_req = get_next_signer(sig_req)
        if next_req:
            send_signature_email(next_req, document_type)

        # Préparer la réponse
        response_data = {
            "success": True,
            "message": "Document signé avec succès",
        }

        # Ajouter l'URL du PDF signé (latest_pdf si disponible, sinon PDF original)
        if hasattr(document, "latest_pdf") and document.latest_pdf:
            response_data["pdfUrl"] = document.latest_pdf.url
        elif hasattr(document, "pdf") and document.pdf:
            response_data["pdfUrl"] = document.pdf.url

        # Ajouter le bienId et location_id pour la redirection et le nettoyage localStorage
        if hasattr(document, "location") and document.location:
            response_data["location_id"] = str(document.location.id)
            if hasattr(document.location, "bien"):
                response_data["bienId"] = document.location.bien.id

                # Pour le mandataire : ajouter le bailleurId pour la redirection
                # vers /mon-compte/mes-mandats/{bailleurId}/biens/{bienId}
                # Priorité au bailleur du user authentifié (request.user)
                bailleur = get_primary_bailleur_for_user(
                    document.location.bien.bailleurs, request.user
                )
                if bailleur:
                    response_data["bailleurId"] = str(bailleur.id)

        return JsonResponse(response_data)

    except Exception as e:
        logger.exception("Erreur lors de la signature du document")
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
            },
            status=500,
        )


def resend_otp_generic(request, model_class, document_type):
    """
    Vue générique pour renvoyer un OTP

    Args:
        request: DRF Request object
        model_class: Classe du modèle de signature
        document_type: Type de document
    """
    try:
        data = request.data
        token = data.get("token")

        if not token:
            return JsonResponse(
                {"error": "Token manquant"},
                status=400,
            )

        sig_req = get_object_or_404(model_class, link_token=token)

        if sig_req.signed:
            return JsonResponse(
                {"error": "Ce document a déjà été signé"},
                status=400,
            )

        # Générer un nouvel OTP et l'envoyer par email
        sig_req.generate_otp()
        from .services import send_otp_email

        success = send_otp_email(sig_req, document_type)

        if success:
            return JsonResponse(
                {
                    "success": True,
                    "message": "Un nouveau code OTP a été envoyé par email",
                }
            )
        else:
            return JsonResponse(
                {"error": "Erreur lors de l'envoi de l'email"},
                status=500,
            )

    except Exception as e:
        logger.exception("Erreur lors du renvoi de l'OTP")
        return JsonResponse(
            {"error": str(e)},
            status=500,
        )


# Les documents locataire (MRH, Caution) sont maintenant gérés via:
# - Le modèle Document avec type_document
# - Les vues upload_document et delete_document existantes
# - L'endpoint standard /location/forms/tenant_documents/requirements/?token=xxx
#   géré par FormOrchestrator._get_tenant_documents_requirements()


def cancel_signature_generic(request, document_id, document_model):
    """
    Vue générique pour annuler une signature en cours.

    Permissions: Bailleur ou Mandataire uniquement.

    Actions:
    - Supprime toutes les signature requests liées au document
    - Supprime le latest_pdf
    - Passe le statut du document à DRAFT

    Args:
        request: HttpRequest
        document_id: UUID du document
        document_model: Classe du modèle de document (Bail ou EtatLieux)
    """
    try:
        # Récupérer le document
        document: SignableDocumentMixin = get_object_or_404(
            document_model, id=document_id
        )

        # Vérifier que le document est bien en cours de signature
        if document.status != DocumentStatus.SIGNING:
            return JsonResponse(
                {
                    "error": f"Ce document n'est pas en cours de signature (statut actuel: {document.status})"
                },
                status=400,
            )

        # Vérifier les permissions: le user doit être bailleur ou mandataire
        user = request.user
        if not user.is_authenticated:
            return JsonResponse(
                {"error": "Authentification requise"},
                status=401,
            )

        # Vérifier que l'utilisateur est bien le bailleur ou le mandataire

        location: Location = document.location
        user_roles = get_user_role_for_location(location, user.email)

        is_bailleur = user_roles.get("is_bailleur", False)
        is_mandataire = user_roles.get("is_mandataire", False)

        if not (is_bailleur or is_mandataire):
            return JsonResponse(
                {"error": "Vous n'avez pas les droits pour annuler cette signature"},
                status=403,
            )

        # Récupérer les signature requests pour envoyer les emails AVANT cancel
        signature_requests = document.signature_requests.all()
        sig_count = signature_requests.count()

        # Envoyer les emails d'annulation AVANT le soft delete
        if sig_count > 0:
            first_sig = signature_requests.first()
            document_type = first_sig.get_document_type()
            try:
                send_signature_cancelled_emails(
                    signature_requests, document, document_type
                )
                logger.info(f"📧 Emails d'annulation envoyés pour {document_type}")
            except Exception as email_error:
                logger.warning(f"⚠️ Erreur envoi emails d'annulation: {email_error}")

        # Utiliser le helper commun pour le reste
        cancelled_count = cancel_document_signature(document, user=user)

        logger.info(f"Signature annulée par {user.email}")

        return JsonResponse(
            {
                "success": True,
                "message": "La signature a été annulée avec succès",
                "document_id": str(document_id),
                "cancelled_signature_requests": cancelled_count,
            }
        )

    except Exception as e:
        logger.exception(f"Erreur lors de l'annulation de la signature: {e}")
        return JsonResponse(
            {"error": str(e)},
            status=500,
        )
