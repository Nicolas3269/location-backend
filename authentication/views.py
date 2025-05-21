import json
import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

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

        return JsonResponse(
            {
                "success": True,
                "tokens": tokens,
                "user": {"email": user.email},
            }
        )

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

        return JsonResponse(
            {
                "success": True,
                "message": "Authentification réussie",
                "tokens": tokens_dict,
                "email": email,
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la vérification de l'OTP")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
