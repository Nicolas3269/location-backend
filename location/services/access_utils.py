"""
Utilitaires pour la vérification des droits d'accès aux locations et biens.
"""
from typing import TYPE_CHECKING

from bail.models import Bail
from location.models import Bailleur, Bien, Locataire, Location, Mandataire

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from location.models import Personne


class UserLocationInfo:
    """Informations sur le rôle et la personne d'un utilisateur pour une location."""

    def __init__(
        self,
        is_mandataire: bool = False,
        is_bailleur: bool = False,
        is_locataire: bool = False,
        personne: "Personne | None" = None,
        locataire: "Locataire | None" = None,
    ):
        self.is_mandataire = is_mandataire
        self.is_bailleur = is_bailleur
        self.is_locataire = is_locataire
        self.personne = personne
        self.locataire = locataire

    def to_dict(self) -> dict[str, bool]:
        """Retourne les rôles sous forme de dict (rétrocompatibilité)."""
        return {
            "is_mandataire": self.is_mandataire,
            "is_bailleur": self.is_bailleur,
            "is_locataire": self.is_locataire,
        }


def get_user_info_for_location(
    location: Location, user_email: str
) -> UserLocationInfo:
    """
    Retourne les rôles et la Personne d'un utilisateur pour une location.

    Args:
        location: Instance de Location
        user_email: Email de l'utilisateur à vérifier

    Returns:
        UserLocationInfo avec is_mandataire, is_bailleur, is_locataire, personne
    """
    user_email_lower = user_email.lower()
    personne: "Personne | None" = None

    # Vérifier si l'utilisateur est mandataire pour cette location
    is_mandataire = False
    if location.mandataire and location.mandataire.signataire:
        if location.mandataire.signataire.email.lower() == user_email_lower:
            is_mandataire = True
            personne = location.mandataire.signataire

    # Vérifier si l'utilisateur est bailleur (utilise la property email du modèle)
    is_bailleur = False
    if not personne:  # Si pas déjà trouvé comme mandataire
        for bailleur in location.bien.bailleurs.all():
            try:
                if bailleur.email.lower() == user_email_lower:
                    is_bailleur = True
                    personne = bailleur.personne or bailleur.signataire
                    break
            except ValueError:
                # Bailleur invalide (pas de personne ni signataire)
                continue

    # Vérifier si l'utilisateur est un des locataires
    is_locataire = False
    locataire_found: Locataire | None = None
    for loc in location.locataires.all():
        if loc.email.lower() == user_email_lower:
            is_locataire = True
            locataire_found = loc
            break

    return UserLocationInfo(
        is_mandataire=is_mandataire,
        is_bailleur=is_bailleur,
        is_locataire=is_locataire,
        personne=personne,
        locataire=locataire_found,
    )


def get_user_role_for_location(location: Location, user_email: str) -> dict[str, bool]:
    """
    Retourne les rôles d'un utilisateur pour une location donnée.

    Args:
        location: Instance de Location
        user_email: Email de l'utilisateur à vérifier

    Returns:
        Dict avec is_mandataire, is_bailleur, is_locataire
    """
    return get_user_info_for_location(location, user_email).to_dict()


def get_personne_for_user_on_location(
    location: Location, user_email: str
) -> "Personne | None":
    """
    Retourne la Personne associée à un utilisateur pour une location donnée.

    Cherche dans l'ordre : mandataire, bailleur.
    (Les locataires ne sont pas des Personne mais des Locataire)

    Args:
        location: Instance de Location
        user_email: Email de l'utilisateur

    Returns:
        Personne ou None si non trouvé
    """
    return get_user_info_for_location(location, user_email).personne


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
