"""
Utilitaires pour la serialization des données de Bailleur et Mandataire.
"""
from typing import Any, Dict

from location.models import Bailleur, Mandataire
from location.serializers.read import BailleurReadSerializer, MandataireReadSerializer


def serialize_bailleur(bailleur: Bailleur) -> Dict[str, Any]:
    """
    Sérialise les données d'un Bailleur pour les formulaires.

    Utilise BailleurReadSerializer (ModelSerializer) pour garantir
    la cohérence avec le modèle.
    """
    if not bailleur:
        return {}

    serializer = BailleurReadSerializer(bailleur)
    return serializer.data


def serialize_mandataire(mandataire: Mandataire) -> Dict[str, Any]:
    """
    Sérialise les données d'un Mandataire pour les formulaires.

    Utilise MandataireReadSerializer (ModelSerializer) pour garantir
    la cohérence avec le modèle.
    """
    if not mandataire:
        return {}

    serializer = MandataireReadSerializer(mandataire)
    return serializer.data
