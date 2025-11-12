"""
Utilitaires pour la serialization des données de Bailleur et Mandataire.
"""
from typing import Any, Dict

from rest_framework import serializers

from location.models import Bailleur, BailleurType, Mandataire, Personne, Societe


# ============================================
# MODEL SERIALIZERS POUR LECTURE (PREFILL)
# ============================================


class PersonneReadSerializer(serializers.ModelSerializer):
    """Serializer en lecture seule pour Personne"""

    class Meta:
        model = Personne
        fields = ["lastName", "firstName", "email", "adresse"]


class SocieteReadSerializer(serializers.ModelSerializer):
    """Serializer en lecture seule pour Société"""

    class Meta:
        model = Societe
        fields = ["raison_sociale", "siret", "forme_juridique", "adresse", "email"]


class MandataireReadSerializer(serializers.ModelSerializer):
    """Serializer en lecture seule pour Mandataire"""

    signataire = PersonneReadSerializer()
    agence = SocieteReadSerializer(source="societe")

    class Meta:
        model = Mandataire
        fields = ["signataire", "agence", "numero_carte_professionnelle"]


class BailleurReadSerializer(serializers.ModelSerializer):
    """Serializer en lecture seule pour Bailleur"""

    bailleur_type = serializers.CharField(source="bailleur_type.value")
    personne = PersonneReadSerializer(required=False, allow_null=True)
    societe = SocieteReadSerializer(required=False, allow_null=True)
    signataire = PersonneReadSerializer(required=False, allow_null=True)

    class Meta:
        model = Bailleur
        fields = ["bailleur_type", "personne", "societe", "signataire"]


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
