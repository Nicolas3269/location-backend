"""
Utilitaires pour la vérification des droits d'accès aux locations et biens.
"""

from bail.models import Bail
from location.models import Bien, Location


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
    # Vérifier si l'utilisateur est mandataire pour cette location
    if location.mandataire and location.mandataire.signataire:
        if location.mandataire.signataire.email == user_email:
            return True

    # Vérifier si l'utilisateur est bailleur
    for bailleur in location.bien.bailleurs.all():
        if bailleur.email == user_email:
            return True

    # Vérifier si l'utilisateur est un des locataires
    for locataire in location.locataires.all():
        if locataire.email == user_email:
            return True

    return False


def user_has_bien_access(
    bien: Bien, user_email: str, check_locataires: bool = False
) -> bool:
    """
    Vérifie si un utilisateur a accès à un bien.

    Vérifie si l'utilisateur est un des bailleurs du bien.
    Si check_locataires=True, vérifie aussi si l'utilisateur est locataire
    d'un bail sur ce bien.

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

    # Vérifier si l'utilisateur est locataire d'un bail sur ce bien (optionnel)
    if check_locataires:
        user_bails = Bail.objects.filter(location__bien=bien)
        for bail in user_bails:
            if bail.location.locataires.filter(email=user_email).exists():
                return True

    return False
