"""
Utilitaires pour l'authentification.
"""

import logging
import random
import string
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.models import EmailVerification

User = get_user_model()
logger = logging.getLogger(__name__)


def get_tokens_for_user(user) -> Dict[str, str]:
    """
    Génère les tokens JWT pour un utilisateur.
    """
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def generate_otp(length: int = 6) -> str:
    """
    Génère un code OTP numérique aléatoire de la longueur spécifiée.
    """
    return "".join(random.choices(string.digits, k=length))


def verify_google_token(token: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Vérifie un token Google et retourne (success, email, error_message)
    """
    try:
        # Configuration Google Client ID à définir dans settings.py
        GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
        if not GOOGLE_CLIENT_ID:
            return False, None, "GOOGLE_CLIENT_ID non configuré"

        # Vérifier le token Google
        id_info = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )

        # Vérifier que le token est valide
        if id_info["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
            return False, None, "Émetteur de token invalide"

        # Récupérer l'email
        email = id_info.get("email")
        if not email:
            return False, None, "Email manquant dans le token Google"

        # Vérifier que l'email est vérifié par Google
        if not id_info.get("email_verified", False):
            return False, None, "Email non vérifié par Google"

        return True, id_info, None

    except ValueError as e:
        logger.error(f"Erreur de vérification du token Google: {str(e)}")
        return False, None, f"Token Google invalide: {str(e)}"


def create_email_verification(email: str) -> EmailVerification:
    """
    Crée une nouvelle demande de vérification d'email et renvoie l'objet créé.
    """
    # Supprime les anciennes vérifications non validées pour cet email
    EmailVerification.objects.filter(email=email, verified=False).delete()

    # Crée une nouvelle vérification
    otp = generate_otp()
    verification = EmailVerification.objects.create(email=email, otp=otp)

    return verification


def send_verification_email_with_otp(verification: EmailVerification) -> None:
    """
    Envoie un email de vérification avec OTP.
    """
    verification_url = f"{settings.FRONTEND_URL}/verify-email/{verification.token}/"

    message = f"""
Bonjour,

Merci d'avoir fourni votre adresse email. Pour continuer, veuillez vérifier
votre adresse email.

Votre code de vérification est : {verification.otp}

Ce code est valable pour une durée de 24 heures.

Si vous n'avez pas demandé cette vérification, vous pouvez ignorer cet email.

Cordialement,
L'équipe HESTIA
"""

    # Inclure l'OTP dans l'objet pour faciliter l'auto-complétion sur mobile
    # Format standard reconnu par iOS et Android
    send_mail(
        subject=f"{verification.otp} - Vérifiez votre adresse email",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[verification.email],
    )


def verify_otp_only_and_generate_token(
    email: str, otp: str
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Vérifie un email avec un OTP sans nécessiter le token et génère un JWT si valide.
    Retourne (success, tokens_dict, error_message)
    Cette fonction est utilisée lorsque l'utilisateur est en cours de formulaire
    et doit vérifier son email avec un code OTP reçu, sans avoir à manipuler le token.
    """
    try:
        # Rechercher la vérification la plus récente pour cet email
        verification = (
            EmailVerification.objects.filter(email=email, verified=False)
            .order_by("-created_at")
            .first()
        )

        if not verification:
            return False, None, "Aucune vérification en attente pour cet email."

        if verification.is_expired():
            return (
                False,
                None,
                "La vérification a expiré. Veuillez demander un nouveau code.",
            )

        if verification.otp != otp:
            return False, None, "Code incorrect. Veuillez réessayer."

        # Si tout est bon, marquer comme vérifié
        verification.verified = True
        verification.verified_at = timezone.now()
        verification.save()

        # Créer ou récupérer l'utilisateur
        user, created = User.objects.get_or_create(
            email=email, defaults={"username": email, "is_active": True}
        )

        # Générer le JWT avec SimpleJWT
        tokens = get_tokens_for_user(user)

        return True, tokens, None

    except Exception as e:
        logger.error(f"Erreur lors de la vérification de l'OTP: {str(e)}")
        return False, None, f"Erreur lors de la vérification: {str(e)}"


def set_refresh_token_cookie(response, refresh_token):
    """
    Configure le refresh token en cookie HttpOnly de manière centralisée.
    """
    refresh_token_lifetime = settings.SIMPLE_JWT.get("REFRESH_TOKEN_LIFETIME")
    cookie_max_age = (
        int(refresh_token_lifetime.total_seconds())
        if refresh_token_lifetime
        else 14 * 24 * 60 * 60  # 14 jours par défaut
    )

    response.set_cookie(
        "jwt_refresh",
        refresh_token,
        max_age=cookie_max_age,
        httponly=True,
        secure=not settings.DEBUG,  # HTTPS en production seulement
        samesite="Lax",
    )
