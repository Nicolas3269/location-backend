"""
Utilitaires pour construire les URLs frontend selon le rôle utilisateur.

Les routes frontend sont différentes selon le rôle :
- Bailleur : /mon-compte/mes-biens/{bien_id}/locations/{location_id}/documents
- Mandataire : /mon-compte/mes-mandats/{bailleur_id}/biens/{bien_id}/locations/{location_id}/documents
- Locataire : /mon-compte/mes-locations/{location_id}
"""

from django.conf import settings

from location.constants import UserRole


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
    base_url = settings.FRONTEND_URL

    if role == UserRole.MANDATAIRE and bailleur_id and bien_id and location_id:
        return (
            f"{base_url}/mon-compte/mes-mandats/{bailleur_id}"
            f"/biens/{bien_id}/locations/{location_id}/documents"
        )
    elif role == UserRole.BAILLEUR and bien_id and location_id:
        return f"{base_url}/mon-compte/mes-biens/{bien_id}/locations/{location_id}/documents"
    elif role == UserRole.LOCATAIRE and location_id:
        return f"{base_url}/mon-compte/mes-locations/{location_id}"
    else:
        return f"{base_url}/mon-compte"


def get_location_path(
    role: UserRole | str,
    location_id: str | None = None,
    bien_id: str | None = None,
    bailleur_id: str | None = None,
) -> str:
    """
    Construit le path (sans base_url) vers la page de location selon le rôle.
    Utile pour les returnUrl.

    Args:
        role: UserRole ou string ("bailleur", "mandataire", "locataire")
        location_id: UUID de la location
        bien_id: UUID du bien (requis pour bailleur/mandataire)
        bailleur_id: UUID du bailleur (requis pour mandataire)

    Returns:
        Path vers la page de location (ex: /mon-compte/mes-biens/...)
    """
    if role == UserRole.MANDATAIRE and bailleur_id and bien_id and location_id:
        return (
            f"/mon-compte/mes-mandats/{bailleur_id}"
            f"/biens/{bien_id}/locations/{location_id}/documents"
        )
    elif role == UserRole.BAILLEUR and bien_id and location_id:
        return f"/mon-compte/mes-biens/{bien_id}/locations/{location_id}/documents"
    elif role == UserRole.LOCATAIRE and location_id:
        return f"/mon-compte/mes-locations/{location_id}"
    else:
        return "/mon-compte"


def get_edl_creation_url(
    role: UserRole | str,
    location_id: str,
    bien_id: str | None = None,
    bailleur_id: str | None = None,
) -> str:
    """
    Construit l'URL pour créer un état des lieux depuis une location.

    Args:
        role: UserRole (BAILLEUR ou MANDATAIRE)
        location_id: UUID de la location source
        bien_id: UUID du bien
        bailleur_id: UUID du bailleur (pour mandataire)

    Returns:
        URL complète vers /etat-lieux avec les paramètres de contexte
    """
    base_url = settings.FRONTEND_URL
    return_url = get_location_path(role, location_id, bien_id, bailleur_id)

    return (
        f"{base_url}/etat-lieux?mode=location_actuelle"
        f"&sourceId={location_id}&returnUrl={return_url}"
    )


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
