import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.utils import (
    create_email_verification,
    get_tokens_for_user,
    send_verification_email_with_otp,
    verify_google_token,
    verify_otp_only_and_generate_token,
)

User = get_user_model()
logger = logging.getLogger(__name__)


# Décorateur pour limiter les requêtes (prévention contre les abus)
def rate_limit(view_func):
    return ratelimit(key="ip", rate="5/m", method="POST", block=True)(view_func)


@csrf_exempt
@require_POST
@rate_limit
def login_with_google(request):
    """Vue pour authentifier un utilisateur avec Google"""
    try:
        data = json.loads(request.body)
        google_token = data.get("id_token")

        if not google_token:
            return JsonResponse({"error": "Token Google requis"}, status=400)

        # Vérifier le token Google
        success, id_info, error_message = verify_google_token(google_token)

        if not success:
            return JsonResponse({"error": error_message}, status=400)

        # Créer ou récupérer l'utilisateur
        email = id_info.get("email")
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": id_info.get("given_name"),
                "last_name": id_info.get("family_name"),
                "is_active": True,
            },
        )

        # Générer des tokens JWT
        tokens = get_tokens_for_user(user)

        # Créer la réponse avec seulement l'access token
        response = JsonResponse(
            {
                "success": True,
                "tokens": {"access": tokens["access"]},  # Seulement l'access token
                "user": {"email": user.email},
            }
        )

        # Configurer le refresh token en cookie HttpOnly
        response.set_cookie(
            "jwt_refresh",
            tokens["refresh"],
            max_age=7 * 24 * 60 * 60,  # 7 jours
            httponly=True,
            secure=not settings.DEBUG,  # HTTPS en production seulement
            samesite="Lax",
        )

        return response

    except Exception as e:
        logger.exception("Erreur lors de la connexion avec Google")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@require_POST
@rate_limit
def request_otp_login(request):
    """Vue pour demander un OTP de connexion par email"""
    try:
        data = json.loads(request.body)
        email = data.get("email")

        if not email:
            return JsonResponse({"error": "Email requis"}, status=400)

        # Créer une vérification d'email avec OTP
        verification = create_email_verification(email)

        # Envoyer l'email avec OTP
        send_verification_email_with_otp(verification)

        return JsonResponse(
            {
                "success": True,
                "message": "Code de vérification envoyé par email",
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la demande d'OTP")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@require_POST
@rate_limit
def verify_otp_login(request):
    """Vue pour vérifier un OTP et générer un token"""
    try:
        data = json.loads(request.body)
        email = data.get("email")
        otp = data.get("otp")

        if not email or not otp:
            return JsonResponse({"error": "Email et OTP requis"}, status=400)

        # Vérifier l'OTP avec email uniquement et générer token
        success, tokens_dict, error_message = verify_otp_only_and_generate_token(
            email, otp
        )

        if not success:
            return JsonResponse({"error": error_message}, status=400)

        # Créer la réponse avec seulement l'access token
        response = JsonResponse(
            {
                "success": True,
                "message": "Authentification réussie",
                "tokens": {"access": tokens_dict["access"]},  # Seulement l'access token
                "email": email,
            }
        )

        # Configurer le refresh token en cookie HttpOnly
        response.set_cookie(
            "jwt_refresh",
            tokens_dict["refresh"],
            max_age=7 * 24 * 60 * 60,  # 7 jours
            httponly=True,
            secure=not settings.DEBUG,  # HTTPS en production seulement
            samesite="Lax",
        )

        return response

    except Exception:
        logger.exception("Erreur lors de la vérification de l'OTP")
        return JsonResponse({"success": False, "error": "Erreur interne"}, status=500)


@csrf_exempt
@require_POST
def refresh_token_view(request):
    """Vue personnalisée pour rafraîchir les tokens via cookies"""
    try:
        # Récupérer le refresh token depuis les cookies
        refresh_token = request.COOKIES.get("jwt_refresh")

        if not refresh_token:
            return JsonResponse({"error": "Refresh token manquant"}, status=401)

        try:
            # Valider et rafraîchir le token
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            return JsonResponse({"access": access_token})

        except (TokenError, InvalidToken):
            # Token invalide ou expiré : purger le cookie automatiquement
            response = JsonResponse(
                {"error": "Token de rafraîchissement invalide"}, status=401
            )

            # Supprimer le cookie refresh token périmé
            response.set_cookie(
                "jwt_refresh",
                "",  # Valeur vide
                max_age=0,  # Expiration immédiate
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
            )

            return response

    except Exception:
        logger.exception("Erreur lors du rafraîchissement du token")
        return JsonResponse({"error": "Erreur interne du serveur"}, status=500)


@csrf_exempt
@require_POST
def logout_view(request):
    """Vue pour déconnecter un utilisateur en supprimant le refresh token des cookies"""
    try:
        # Créer la réponse
        response = JsonResponse({"success": True, "message": "Déconnexion réussie"})

        # Supprimer le cookie refresh token en le définissant avec
        # une date d'expiration passée
        response.set_cookie(
            "jwt_refresh",
            "",  # Valeur vide
            max_age=0,  # Expiration immédiate
            httponly=True,
            secure=not settings.DEBUG,  # HTTPS en production seulement
            samesite="Lax",
        )

        return response

    except Exception:
        logger.exception("Erreur lors de la déconnexion")
        return JsonResponse({"error": "Erreur interne du serveur"}, status=500)
