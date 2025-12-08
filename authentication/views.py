import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.utils import (
    create_email_verification,
    get_tokens_for_user,
    send_verification_email_with_otp,
    set_refresh_token_cookie,
    verify_google_token,
    verify_otp_only_and_generate_token,
)
from bail.models import Bail
from location.models import Bailleur, Bien, Locataire, Location, Mandataire
from location.services.access_utils import (
    get_user_mandataires,
    user_has_mandataire_role,
)
from location.services.serialization_utils import (
    serialize_bien_with_stats,
)
from signature.document_status import DocumentStatus

User = get_user_model()
logger = logging.getLogger(__name__)


# Décorateur pour limiter les requêtes (prévention contre les abus)
# Désactivé en mode DEBUG pour permettre les tests E2E parallèles
def rate_limit(view_func):
    if settings.DEBUG:
        return view_func  # Pas de rate limit en dev/test
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

        # Créer la réponse (plus d'access token - c'est le rôle de authStore)
        response = JsonResponse(
            {
                "success": True,
                "user": {"email": user.email},
            }
        )

        # Configurer le refresh token en cookie HttpOnly
        set_refresh_token_cookie(response, tokens["refresh"])

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

        # Créer la réponse (plus d'access token - c'est le rôle de authStore)
        response = JsonResponse(
            {
                "success": True,
                "message": "Authentification réussie",
                "email": email,
            }
        )

        # Configurer le refresh token en cookie HttpOnly
        set_refresh_token_cookie(response, tokens_dict["refresh"])

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


@csrf_exempt
@require_POST
def google_redirect_callback(request):
    """Vue pour gérer le callback redirect de Google et rediriger vers le frontend"""
    try:
        # En mode redirect, Google envoie le credential via POST FormData
        google_token = request.POST.get("credential")

        if not google_token:
            logger.error("Aucun identifiant reçu de Google dans les données POST")
            # Rediriger vers le frontend avec erreur
            base_url = settings.FRONTEND_URL
            error_url = f"{base_url}/auth/google/callback?error=no_credential"
            return redirect(error_url)

        # Vérifier le token Google
        success, id_info, error_message = verify_google_token(google_token)

        if not success:
            logger.error(f"Échec de la vérification du token Google : {error_message}")
            base_url = settings.FRONTEND_URL
            error_url = f"{base_url}/auth/google/callback?error=invalid_token"
            return redirect(error_url)

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

        # Créer une réponse de redirection vers une route frontend dédiée
        # qui gère la récupération de pre_auth_url depuis sessionStorage
        redirect_url = f"{settings.FRONTEND_URL}/auth/google/callback"
        response = redirect(redirect_url)

        # Configurer le refresh token en cookie HttpOnly
        set_refresh_token_cookie(response, tokens["refresh"])

        logger.info(f"Google auth successful for user {email}, redirecting to frontend")
        return response

    except Exception as e:
        logger.error(f"Erreur dans le callback de redirection Google : {str(e)}")
        base_url = settings.FRONTEND_URL
        error_url = f"{base_url}/auth/google/callback?error=callback_error"
        return redirect(error_url)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    """
    Vue pour récupérer le profil utilisateur de base avec les rôles.

    Endpoint rapide sans comptage lourd de statistiques.
    Pour les données détaillées (biens, locations), utiliser /auth/profile/stats/
    """
    user = request.user

    # Informations utilisateur de base
    profile_data = {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "roles": {
            "is_mandataire": False,
            "is_bailleur": False,
            "is_locataire": False,
        },
    }

    # Vérifier si l'utilisateur est un mandataire
    mandataires = Mandataire.objects.filter(signataire__email=user.email).select_related('signataire')
    profile_data["roles"]["is_mandataire"] = mandataires.exists()

    # Si mandataire et User.first_name vide, utiliser données du signataire
    if mandataires.exists() and not user.first_name:
        mandataire = mandataires.first()
        if mandataire.signataire:
            profile_data["first_name"] = mandataire.signataire.firstName
            profile_data["last_name"] = mandataire.signataire.lastName

    # Vérifier si l'utilisateur est un bailleur
    bailleurs = Bailleur.objects.filter(
        models.Q(personne__email=user.email) | models.Q(signataire__email=user.email)
    ).select_related('personne', 'signataire').distinct()

    profile_data["roles"]["is_bailleur"] = bailleurs.exists()

    # Si bailleur et User.first_name vide, utiliser données bailleur
    if bailleurs.exists() and not user.first_name:
        from location.models import BailleurType

        bailleur = bailleurs.first()
        if bailleur.bailleur_type == BailleurType.PHYSIQUE and bailleur.personne:
            # Bailleur personne physique
            profile_data["first_name"] = bailleur.personne.firstName
            profile_data["last_name"] = bailleur.personne.lastName
        elif bailleur.bailleur_type == BailleurType.MORALE and bailleur.signataire:
            # Bailleur société → utiliser le signataire
            profile_data["first_name"] = bailleur.signataire.firstName
            profile_data["last_name"] = bailleur.signataire.lastName

    # Vérifier si l'utilisateur est un locataire
    locataires = Locataire.objects.filter(email=user.email)
    profile_data["roles"]["is_locataire"] = locataires.exists()

    # Si locataire et User.first_name vide, utiliser données locataire
    if locataires.exists() and not user.first_name:
        locataire = locataires.first()
        profile_data["first_name"] = locataire.firstName
        profile_data["last_name"] = locataire.lastName

    return JsonResponse({"success": True, **profile_data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_profile_stats(request):
    """
    Vue pour récupérer les statistiques et données détaillées du profil.

    Endpoint plus lourd avec comptage de biens, locations, et statistiques mandataire.
    À appeler après get_user_profile pour lazy-loading.
    """
    user = request.user
    stats_data = {}

    # Statistiques Bailleur : Liste des biens avec comptages
    try:
        bailleurs = Bailleur.objects.filter(
            models.Q(personne__email=user.email)
            | models.Q(signataire__email=user.email)
        ).distinct()

        if bailleurs.exists():
            biens = []
            for bailleur in bailleurs:
                for bien in Bien.objects.filter(bailleurs=bailleur):
                    # Utiliser le helper de sérialisation
                    bien_data = serialize_bien_with_stats(bien)
                    # Ajouter compatibilité avec ancien format
                    bien_data["nombre_baux"] = bien_data["nombre_baux"]
                    # Éviter les doublons
                    if not any(b["id"] == bien_data["id"] for b in biens):
                        biens.append(bien_data)

            stats_data["biens"] = biens

    except Exception as e:
        error_msg = f"Erreur récupération biens pour {user.email}: {e}"
        logger.error(error_msg)
        stats_data["biens"] = []

    # Statistiques Locataire : Liste des locations avec bails
    try:
        locataires = Locataire.objects.filter(email=user.email)

        if locataires.exists():
            locations = []
            for locataire in locataires:
                for location in Location.objects.filter(locataires=locataire):
                    # Récupérer le bail actif (SIGNING ou SIGNED)
                    bail = (
                        Bail.objects.filter(
                            location=location,
                            status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED],
                        )
                        .order_by("-created_at")
                        .first()
                    )

                    date_fin = (
                        location.date_fin.isoformat() if location.date_fin else None
                    )

                    # Si un bail existe, récupérer ses infos
                    signatures_completes = True
                    pdf_url = None
                    latest_pdf_url = None
                    status = "draft"

                    if bail:
                        signatures_completes = not bail.signature_requests.filter(
                            signed=False
                        ).exists()
                        pdf_url = bail.pdf.url if bail.pdf else None
                        latest_pdf_url = (
                            bail.latest_pdf.url if bail.latest_pdf else None
                        )
                        status = bail.status

                    # Récupérer les montants depuis RentTerms
                    montant_loyer = 0
                    montant_charges = 0
                    if hasattr(location, "rent_terms"):
                        montant_loyer = float(location.rent_terms.montant_loyer or 0)
                        montant_charges = float(
                            location.rent_terms.montant_charges or 0
                        )

                    location_data = {
                        "id": str(location.id),
                        "bien_adresse": location.bien.adresse,
                        "bien_type": location.bien.get_type_bien_display(),
                        "date_debut": location.date_debut.isoformat()
                        if location.date_debut
                        else None,
                        "date_fin": date_fin,
                        "montant_loyer": montant_loyer,
                        "montant_charges": montant_charges,
                        "status": status,
                        "signatures_completes": signatures_completes,
                        "pdf_url": pdf_url,
                        "latest_pdf_url": latest_pdf_url,
                        "created_at": (
                            bail.date_signature.isoformat()
                            if bail and bail.date_signature
                            else None
                        ),
                    }
                    # Éviter les doublons
                    if not any(loc["id"] == location_data["id"] for loc in locations):
                        locations.append(location_data)

            stats_data["locations"] = locations

    except Exception as e:
        error_msg = f"Erreur récupération locations pour {user.email}: {e}"
        logger.error(error_msg)
        stats_data["locations"] = []

    # Statistiques Mandataire : Nombre de biens/bailleurs gérés
    try:
        mandataires = get_user_mandataires(user.email)

        if mandataires.exists():
            # Compter les biens gérés via les locations
            nombre_biens_geres = (
                Bien.objects.filter(locations__mandataire__in=mandataires)
                .distinct()
                .count()
            )

            # Compter les bailleurs uniques gérés
            nombre_bailleurs_geres = (
                Bailleur.objects.filter(bien__locations__mandataire__in=mandataires)
                .distinct()
                .count()
            )

            stats_data["mandataire_stats"] = {
                "nombre_biens_geres": nombre_biens_geres,
                "nombre_bailleurs_geres": nombre_bailleurs_geres,
            }

    except Exception as e:
        error_msg = f"Erreur stats mandataire pour {user.email}: {e}"
        logger.error(error_msg)

    return JsonResponse({"success": True, **stats_data})
