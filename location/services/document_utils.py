"""
Utilitaires pour la gestion des documents signables (Bail, EtatLieux).
"""
from typing import Any, Dict, Optional

from location.constants import UserRole


def determine_mandataire_doit_signer(
    user_role: Optional[str],
    form_data: Dict[str, Any],
) -> bool:
    """
    Détermine si le mandataire doit signer un document (Bail ou État des lieux).

    Logique :
    1. Si user_role == MANDATAIRE → mandataire_doit_signer = True (automatique)
    2. Si user_role == BAILLEUR → lire depuis form_data (question posée dans le formulaire)
    3. Autre cas → False par défaut

    Args:
        user_role: Rôle de l'utilisateur ("mandataire" ou "bailleur")
        form_data: Données du formulaire (validated_data pour Bail, form_data pour EDL)

    Returns:
        bool: True si le mandataire doit signer, False sinon

    Examples:
        >>> # Mandataire remplit le formulaire
        >>> determine_mandataire_doit_signer("mandataire", {})
        True

        >>> # Bailleur avec mandataire
        >>> determine_mandataire_doit_signer("bailleur", {"mandataire_doit_signer": True})
        True

        >>> # Bailleur sans mandataire
        >>> determine_mandataire_doit_signer("bailleur", {})
        False
    """
    if user_role == UserRole.MANDATAIRE:
        return True
    elif user_role == UserRole.BAILLEUR and form_data:
        return form_data.get("mandataire_doit_signer", False)
    return False
