"""
Utilitaires pour la gestion des documents signables (Bail, EtatLieux).
"""

from typing import Any, Dict, Optional

from location.constants import UserRole
from signature.document_types import SignableDocumentType


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


def determine_mandataire_fait_edl(
    user_role: Optional[str],
    form_data: Dict[str, Any],
    document_type: str,
) -> bool:
    """
    Détermine si le mandataire réalise les états des lieux.

    Logique selon le type de document :

    **EDL (État des lieux)** :
    - Si user_role == MANDATAIRE → True (automatique)
    - Sinon → False (pas de lecture depuis form_data,
      le mandataire n'est pas en train de faire l'EDL)

    **BAIL** :
    - Si user_role == MANDATAIRE → True (automatique)
    - Si user_role == BAILLEUR → lire depuis form_data
      (question posée dans le formulaire)
    - Sinon → False

    Args:
        user_role: Rôle de l'utilisateur ("mandataire" ou "bailleur")
        form_data: Données du formulaire (validated_data)
        document_type: Type de document (SignableDocumentType)

    Returns:
        bool: True si le mandataire fait les EDL, False sinon

    Examples:
        >>> # Mandataire remplit un EDL
        >>> determine_mandataire_fait_edl("mandataire", {}, SignableDocumentType.ETAT_LIEUX)
        True

        >>> # Bailleur remplit un EDL (mandataire ne fait pas l'EDL)
        >>> determine_mandataire_fait_edl("bailleur", {}, SignableDocumentType.ETAT_LIEUX)
        False

        >>> # Mandataire remplit un Bail
        >>> determine_mandataire_fait_edl("mandataire", {}, SignableDocumentType.BAIL)
        True

        >>> # Bailleur indique que le mandataire fait les EDL (dans le Bail)
        >>> determine_mandataire_fait_edl("bailleur", {
        ...     "honoraires_mandataire": {"edl": {"mandataire_fait_edl": True}}
        ... }, SignableDocumentType.BAIL)
        True

        >>> # Bailleur sans mandataire faisant les EDL
        >>> determine_mandataire_fait_edl("bailleur", {}, SignableDocumentType.BAIL)
        False
    """
    # Cas EDL : seul le mandataire peut avoir fait_edl = True
    if document_type == SignableDocumentType.ETAT_LIEUX:
        return user_role == UserRole.MANDATAIRE

    # Cas BAIL : toujours lire depuis form_data
    # (question posée au mandataire ET au bailleur)
    elif document_type == SignableDocumentType.BAIL and form_data:
        honoraires = form_data.get("honoraires_mandataire", {})
        edl = honoraires.get("edl", {}) if isinstance(honoraires, dict) else {}
        return edl.get("mandataire_fait_edl", False)

    return False
