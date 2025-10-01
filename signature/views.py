"""
Vues génériques pour la signature de documents
"""

import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from authentication.utils import get_tokens_for_user, set_refresh_token_cookie

from .services import (
    get_next_signer,
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
    try:
        sig_req = get_object_or_404(model_class, link_token=token)

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
        response_data = {
            "success": True,
            "signataire": sig_req.get_signataire_name(),
            "document_name": sig_req.get_document_name(),
            "order": sig_req.order,
        }

        # Ajouter l'URL du PDF si disponible
        if hasattr(document, "pdf") and document.pdf:
            response_data["pdfUrl"] = request.build_absolute_uri(document.pdf.url)

        # Générer un OTP à chaque accès et l'envoyer par email
        sig_req.generate_otp()

        # Préparer les données de réponse
        person = sig_req.bailleur_signataire or sig_req.locataire
        signer_email = sig_req.get_signataire_email()

        # Envoyer l'OTP par email
        from .services import send_otp_email

        document_type = "bail" if hasattr(sig_req, "bail") else "etat_lieux"
        send_otp_email(sig_req, document_type)

        # Préparer la réponse dans le nouveau format unifié
        response_data.update(
            {
                "success": True,
                "person": {
                    "email": signer_email,
                    "first_name": person.firstName if person else "",
                    "last_name": person.lastName if person else "",
                },
                "otp_sent": True,
            }
        )

        # Ajouter l'ID du document selon le type
        if hasattr(sig_req, "bail"):
            response_data["bail_id"] = sig_req.bail.id
        elif hasattr(sig_req, "etat_lieux"):
            response_data["etat_lieux_id"] = sig_req.etat_lieux.id

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

        sig_req = get_object_or_404(model_class, link_token=token)

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

        # Traiter la signature si fournie - utiliser la fonction générique
        if signature_data_url:
            from .pdf_processing import process_signature_generic

            process_signature_generic(sig_req, signature_data_url)

        # Marquer comme signé
        sig_req.mark_as_signed()

        # Récupérer le document
        document = sig_req.get_document()

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
            response_data["pdfUrl"] = request.build_absolute_uri(
                document.latest_pdf.url
            )
        elif hasattr(document, "pdf") and document.pdf:
            response_data["pdfUrl"] = request.build_absolute_uri(document.pdf.url)

        # Ajouter le bienId pour la redirection
        if hasattr(document, "location") and document.location and hasattr(document.location, "bien"):
            response_data["bienId"] = document.location.bien.id

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
