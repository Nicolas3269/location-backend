"""
Utilitaires pour la vérification des droits d'accès aux locations et biens.
"""
from typing import TYPE_CHECKING

from bail.models import Bail
from location.models import Bailleur, Bien, Location, Mandataire

if TYPE_CHECKING:
    from django.db.models import QuerySet


def get_user_role_for_location(location: Location, user_email: str) -> dict[str, bool]:
    """
    Retourne les rôles d'un utilisateur pour une location donnée.

    Args:
        location: Instance de Location
        user_email: Email de l'utilisateur à vérifier

    Returns:
        Dict avec is_mandataire, is_bailleur, is_locataire
    """
    user_email_lower = user_email.lower()

    # Vérifier si l'utilisateur est mandataire pour cette location
    is_mandataire = (
        location.mandataire
        and location.mandataire.signataire
        and location.mandataire.signataire.email.lower() == user_email_lower
    )

    # Vérifier si l'utilisateur est bailleur
    is_bailleur = any(
        bailleur.signataire and bailleur.signataire.email.lower() == user_email_lower
        for bailleur in location.bien.bailleurs.all()
    )

    # Vérifier si l'utilisateur est un des locataires
    is_locataire = any(
        locataire.email.lower() == user_email_lower
        for locataire in location.locataires.all()
    )

    return {
        "is_mandataire": is_mandataire,
        "is_bailleur": is_bailleur,
        "is_locataire": is_locataire,
    }


def user_has_location_access(location: Location, user_email: str) -> bool:
    """
    Vérifie si un utilisateur a accès à une location.

    Vérifie dans l'ordre :
    1. Si l'utilisateur est le mandataire de cette location
    2. Si l'utilisateur est un des bailleurs du bien
    3. Si l'utilisateur est un des locataires

    Args:
        location: Instance de Location
        user_email: Email de l'utilisateur à vérifier

    Returns:
        True si l'utilisateur a accès, False sinon
    """
    roles = get_user_role_for_location(location, user_email)
    return any(roles.values())


def user_has_bien_access(
    bien: Bien, user_email: str, check_locataires: bool = False
) -> bool:
    """
    Vérifie si un utilisateur a accès à un bien.

    Vérifie dans l'ordre :
    1. Si l'utilisateur est un des bailleurs du bien
    2. Si l'utilisateur est mandataire d'une location de ce bien
    3. Si check_locataires=True, si l'utilisateur est locataire d'un bail sur ce bien

    Args:
        bien: Instance de Bien
        user_email: Email de l'utilisateur à vérifier
        check_locataires: Si True, vérifie aussi l'accès via les baux comme locataire

    Returns:
        True si l'utilisateur a accès, False sinon
    """
    # Vérifier si l'utilisateur est bailleur
    for bailleur in bien.bailleurs.all():
        try:
            if bailleur.email == user_email:
                return True
        except ValueError:
            # Bailleur invalide (pas de personne ni signataire), ignorer
            continue

    # Vérifier si l'utilisateur est mandataire d'une location de ce bien
    mandataires = Mandataire.objects.filter(signataire__email=user_email)
    if mandataires.exists():
        if Location.objects.filter(bien=bien, mandataire__in=mandataires).exists():
            return True

    # Vérifier si l'utilisateur est locataire d'un bail sur ce bien (optionnel)
    if check_locataires:
        user_bails = Bail.objects.filter(location__bien=bien)
        for bail in user_bails:
            if bail.location.locataires.filter(email=user_email).exists():
                return True

    return False


# =====================================================
# Helpers pour les mandataires
# =====================================================


def get_user_mandataires(user_email: str) -> "QuerySet[Mandataire]":
    """
    Retourne tous les mandataires d'un utilisateur.

    Un signataire peut gérer plusieurs agences/mandataires.

    Args:
        user_email: Email de l'utilisateur

    Returns:
        QuerySet de Mandataire
    """
    return Mandataire.objects.filter(signataire__email=user_email)


def user_has_mandataire_role(user_email: str) -> bool:
    """
    Vérifie si un utilisateur a le rôle mandataire.

    Args:
        user_email: Email de l'utilisateur

    Returns:
        True si l'utilisateur est mandataire, False sinon
    """
    return get_user_mandataires(user_email).exists()


def user_has_bailleur_access_via_mandataire(
    bailleur: Bailleur, user_email: str
) -> bool:
    """
    Vérifie si un mandataire a accès à un bailleur spécifique.

    Un mandataire a accès à un bailleur s'il gère au moins une location
    pour un bien appartenant à ce bailleur.

    Args:
        bailleur: Instance de Bailleur
        user_email: Email de l'utilisateur mandataire

    Returns:
        True si le mandataire gère ce bailleur, False sinon
    """
    mandataires = get_user_mandataires(user_email)

    if not mandataires.exists():
        return False

    # Vérifier qu'il existe au moins une location gérée par ce mandataire
    # pour un bien appartenant à ce bailleur
    return Location.objects.filter(
        mandataire__in=mandataires,
        bien__bailleurs=bailleur
    ).exists()


def user_has_bien_access_via_mandataire(bien: Bien, user_email: str) -> bool:
    """
    Vérifie si un mandataire a accès à un bien spécifique.

    Un mandataire a accès à un bien s'il gère au moins une location de ce bien.

    Args:
        bien: Instance de Bien
        user_email: Email de l'utilisateur mandataire

    Returns:
        True si le mandataire gère ce bien, False sinon
    """
    mandataires = get_user_mandataires(user_email)

    if not mandataires.exists():
        return False

    # Vérifier que ces mandataires gèrent ce bien (via une location)
    return Location.objects.filter(bien=bien, mandataire__in=mandataires).exists()
