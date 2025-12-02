"""
Utilitaires pour construire les URLs frontend selon le rôle utilisateur.

Les routes frontend sont différentes selon le rôle :
- Bailleur : /mon-compte/mes-biens/{bien_id}/locations/{location_id}/documents
- Mandataire : /mon-compte/mes-mandats/{bailleur_id}/biens/{bien_id}/locations/{location_id}/documents
- Locataire : /mon-compte/mes-locations/{location_id}
"""

from django.conf import settings

from location.constants import UserRole

# Routes de base par rôle
USER_SPACE_PATHS = {
    UserRole.BAILLEUR: "/mon-compte/mes-biens",
    UserRole.MANDATAIRE: "/mon-compte/mes-mandats",
    UserRole.LOCATAIRE: "/mon-compte/mes-locations",
}


def get_user_space_url(role: UserRole | str) -> str:
    """
    Retourne l'URL de l'espace utilisateur (page d'accueil) selon le rôle.

    Args:
        role: UserRole ou string

    Returns:
        URL complète vers l'espace utilisateur
    """
    base_url = settings.FRONTEND_URL
    path = USER_SPACE_PATHS.get(role, "/mon-compte")
    return f"{base_url}{path}"


def get_location_url(
    role: UserRole | str,
    location_id: str | None = None,
    bien_id: str | None = None,
    bailleur_id: str | None = None,
) -> str:
    """
    Construit l'URL vers la page de location selon le rôle.

    Args:
        role: UserRole ou string ("bailleur", "mandataire", "locataire")
        location_id: UUID de la location
        bien_id: UUID du bien (requis pour bailleur/mandataire)
        bailleur_id: UUID du bailleur (requis pour mandataire)

    Returns:
        URL complète vers la page de location
    """
    base = get_user_space_url(role)

    if role == UserRole.MANDATAIRE and bailleur_id and bien_id and location_id:
        return f"{base}/{bailleur_id}/biens/{bien_id}/locations/{location_id}/documents"
    elif role == UserRole.BAILLEUR and bien_id and location_id:
        return f"{base}/{bien_id}/locations/{location_id}/documents"
    elif role == UserRole.LOCATAIRE and location_id:
        return f"{base}/{location_id}"
    else:
        return base


def get_bailleur_id_from_location(location) -> str | None:
    """
    Récupère l'ID du premier bailleur depuis une location.
    Utilisé pour construire les URLs mandataire.

    Args:
        location: Instance de Location

    Returns:
        UUID du bailleur ou None
    """
    if location and location.bien:
        first_bailleur = location.bien.bailleurs.order_by("created_at").first()
        if first_bailleur:
            return str(first_bailleur.id)
    return None
