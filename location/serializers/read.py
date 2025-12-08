"""
Serializers READ pour lire les données existantes.
Optimisés pour la lecture avec relations et métadonnées calculées.
"""

from typing import Any, Dict

from rest_framework import serializers

from location.models import (
    Adresse,
    Bailleur,
    Bien,
    Location,
    Mandataire,
    RentTerms,
)
from location.serializers.base import LocationBaseSerializer
from location.serializers.helpers import (
    extract_bailleurs_with_priority,
    restructure_bien_to_nested_format,
    serialize_bailleur_to_dict,
    serialize_locataire_to_dict,
    serialize_mandataire_to_dict,
)


class AdresseReadSerializer(serializers.ModelSerializer):
    """
    Serializer READ pour Adresse.
    Retourne uniquement les champs structurés (frontend construit le formaté).
    """

    class Meta:
        model = Adresse
        fields = [
            "id",
            "numero",
            "voie",
            "complement",
            "code_postal",
            "ville",
            "pays",
            "latitude",
            "longitude",
        ]


class BienReadSerializer(serializers.ModelSerializer):
    """
    Serializer READ pour Bien.
    Retourne tous les champs nécessaires pour pré-remplir un formulaire.
    """

    # Adresse FK (required) - typé pour génération Zod
    adresse = AdresseReadSerializer(read_only=True)

    class Meta:
        model = Bien
        fields = [
            "id",
            "adresse",  # Contient latitude/longitude via AdresseReadSerializer
            "type_bien",
            "superficie",
            "meuble",
            "etage",
            "porte",
            "dernier_etage",
            "classe_dpe",
            "depenses_energetiques",
            "pieces_info",
            "annexes_privatives",
            "annexes_collectives",
            "regime_juridique",
            "periode_construction",
            "identifiant_fiscal",
            "chauffage_type",
            "chauffage_energie",
            "eau_chaude_type",
            "eau_chaude_energie",
            "information",
        ]


class BailleurReadSerializer(serializers.ModelSerializer):
    """
    Serializer READ pour Bailleur.
    Flatten la structure selon le type (PHYSIQUE ou MORALE).
    Ne pas définir de sous-serializers pour éviter l'import circulaire.
    """

    class Meta:
        model = Bailleur
        fields = ["id", "bailleur_type", "personne", "societe", "signataire"]

    def to_representation(self, instance: Bailleur) -> Dict[str, Any]:
        """
        Retourne la structure nested attendue par le serializer WRITE.
        Format aligné avec BailleurInfoSerializer.
        Délègue à serialize_bailleur_to_dict() pour éviter la duplication.
        """

        return serialize_bailleur_to_dict(instance)


class RentTermsReadSerializer(serializers.ModelSerializer):
    """Serializer READ pour RentTerms."""

    class Meta:
        model = RentTerms
        fields = [
            "montant_loyer",
            "montant_charges",
            "type_charges",
            "depot_garantie",
            "zone_tendue",
            "zone_tres_tendue",
            "zone_tendue_touristique",
            "premiere_mise_en_location",
            "locataire_derniers_18_mois",
            "dernier_montant_loyer",
            "dernier_loyer_periode",
            "justificatif_complement_loyer",
        ]


class MandataireReadSerializer(serializers.ModelSerializer):
    """
    Serializer READ pour Mandataire.
    Ne pas définir de sous-serializers pour éviter l'import circulaire.
    """

    class Meta:
        model = Mandataire
        fields = ["id", "signataire", "societe", "numero_carte_professionnelle"]

    def to_representation(self, instance: Mandataire) -> Dict[str, Any]:
        """
        Flatten la structure pour le frontend.
        Délègue à serialize_mandataire_to_dict() pour éviter la duplication.
        """

        return serialize_mandataire_to_dict(instance)


class LocationReadSerializer(LocationBaseSerializer):
    """
    Serializer READ pour Location.
    Hérite de LocationBaseSerializer + ajoute relations et métadonnées.
    Structure la sortie pour matcher le format attendu par le frontend.
    """

    # Relations (read_only)
    bien = BienReadSerializer(read_only=True)
    bailleur = serializers.SerializerMethodField()
    co_bailleurs = serializers.SerializerMethodField()  # ✅ Ajouté au même niveau
    locataires = serializers.SerializerMethodField()  # Géré manuellement
    mandataire = MandataireReadSerializer(read_only=True)
    rent_terms = RentTermsReadSerializer(read_only=True)

    # Métadonnées
    id = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta(LocationBaseSerializer.Meta):
        fields = LocationBaseSerializer.Meta.fields + [
            "id",
            "bien",
            "bailleur",
            "co_bailleurs",  # ✅ Ajouté
            "locataires",
            "mandataire",
            "rent_terms",
            "created_at",
            "updated_at",
        ]

    def get_bailleur(self, obj: Location) -> Dict[str, Any]:
        """
        Retourne le bailleur principal (user connecté prioritaire).
        """
        user = self.context.get("user")
        data = extract_bailleurs_with_priority(obj.bien.bailleurs.all(), user)
        return data.get("bailleur", {})  # ✅ Retourne seulement le principal

    def get_co_bailleurs(self, obj: Location) -> list[Dict[str, Any]]:
        """
        Retourne les co-bailleurs (tous sauf le principal).
        """
        user = self.context.get("user")
        data = extract_bailleurs_with_priority(obj.bien.bailleurs.all(), user)
        return data.get("co_bailleurs", [])  # ✅ Retourne la liste des co-bailleurs

    def get_locataires(self, obj: Location) -> list[Dict[str, Any]]:
        """
        Sérialise les locataires avec serialize_locataire_to_dict().
        """

        if not obj.locataires.exists():
            return []

        return [serialize_locataire_to_dict(loc) for loc in obj.locataires.all()]

    def to_representation(self, instance: Location) -> Dict[str, Any]:
        """
        Transforme la sortie pour matcher le format PREFILL = format WRITE des formulaires.
        Structure nested identique aux serializers WRITE (FranceBailSerializer, etc.).
        Cette structure est la SOURCE DE VÉRITÉ pour tous les formulaires.
        """
        data = super().to_representation(instance)

        # Nettoyer mandataire : ne pas inclure si vide ou None
        if "mandataire" in data and (
            not data["mandataire"] or data["mandataire"] == {}
        ):
            del data["mandataire"]

        # Restructurer "bien" en structure nested
        if "bien" in data and data["bien"]:
            # Préparer zone_reglementaire depuis rent_terms (si disponible)
            zone_override = None
            if "rent_terms" in data and data["rent_terms"]:
                rt = data["rent_terms"]
                zone_override = {
                    "zone_tendue": rt.get("zone_tendue"),
                    "zone_tres_tendue": rt.get("zone_tres_tendue"),
                    "zone_tendue_touristique": rt.get("zone_tendue_touristique"),
                }

            data["bien"] = restructure_bien_to_nested_format(
                data["bien"],
                calculate_zone_from_gps=False,
                zone_reglementaire_override=zone_override,
            )

        # Restructurer "rent_terms" en "modalites_financieres" (format WRITE)
        if "rent_terms" in data and data["rent_terms"]:
            rt = data["rent_terms"]

            # Modalités financières
            data["modalites_financieres"] = {
                "loyer_hors_charges": (
                    float(rt["montant_loyer"]) if rt.get("montant_loyer") else None
                ),
                "charges": float(rt["montant_charges"])
                if rt.get("montant_charges")
                else None,
                "type_charges": rt.get("type_charges"),
                "depot_garantie": (
                    float(rt["depot_garantie"]) if rt.get("depot_garantie") else None
                ),
            }

            # Zone tendue - modalités spécifiques
            if rt.get("zone_tendue"):
                data["modalites_zone_tendue"] = {
                    "premiere_mise_en_location": rt.get("premiere_mise_en_location"),
                    "locataire_derniers_18_mois": rt.get("locataire_derniers_18_mois"),
                    "dernier_montant_loyer": (
                        float(rt["dernier_montant_loyer"])
                        if rt.get("dernier_montant_loyer")
                        else None
                    ),
                    "dernier_loyer_periode": rt.get("dernier_loyer_periode"),
                    "justificatif_complement_loyer": rt.get(
                        "justificatif_complement_loyer"
                    ),
                }

            # Supprimer rent_terms de la racine (format DB, pas format WRITE)
            del data["rent_terms"]

        # Dates - regrouper dans un objet "dates" (format WRITE)
        if data.get("date_debut") or data.get("date_fin"):
            data["dates"] = {}
            if data.get("date_debut"):
                data["dates"]["date_debut"] = data["date_debut"]
                del data["date_debut"]
            if data.get("date_fin"):
                data["dates"]["date_fin"] = data["date_fin"]
                del data["date_fin"]

        return data
