"""
Serializers composables pour une meilleure architecture.
Chaque serializer représente un domaine métier atomique.
"""

from rest_framework import serializers

# ============================================
# SERIALIZERS ATOMIQUES DE BASE
# ============================================


class AdresseSerializer(serializers.Serializer):
    """Serializer pour une adresse avec géolocalisation"""

    adresse = serializers.CharField(required=True, max_length=255)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    area_id = serializers.IntegerField(required=False, allow_null=True)


class CaracteristiquesBienSerializer(serializers.Serializer):
    """Caractéristiques physiques d'un bien - Unifié pour tous les formulaires"""

    superficie = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    type_bien = serializers.ChoiceField(
        choices=["appartement", "maison"], required=False, default="appartement"
    )
    etage = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    porte = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    dernier_etage = serializers.BooleanField(required=False, allow_null=True, default=None)
    meuble = serializers.BooleanField(required=False, allow_null=True, default=None)
    pieces_info = serializers.JSONField(
        required=False,
        help_text="Détail des pièces: chambres, sallesDeBain, cuisines, etc.",
    )


class PerformanceEnergetiqueSerializer(serializers.Serializer):
    """Performance énergétique du bien"""

    classe_dpe = serializers.ChoiceField(
        choices=["A", "B", "C", "D", "E", "F", "G", "NA"], default="NA"
    )
    depenses_energetiques = serializers.CharField(
        required=False, allow_blank=True, default=""
    )


class EquipementsSerializer(serializers.Serializer):
    """Équipements et annexes du bien"""

    annexes_privatives = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    annexes_collectives = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    information = serializers.ListField(child=serializers.CharField(), required=False)


class SystemeEnergieSerializer(serializers.Serializer):
    """Système énergétique (chauffage ou eau chaude)"""

    type = serializers.CharField(required=False, allow_blank=True)
    energie = serializers.CharField(required=False, allow_blank=True)


class EnergieSerializer(serializers.Serializer):
    """Systèmes énergétiques du bien"""

    chauffage = SystemeEnergieSerializer(required=False)
    eau_chaude = SystemeEnergieSerializer(required=False)


class RegimeJuridiqueSerializer(serializers.Serializer):
    """Régime juridique et fiscal du bien"""

    regime_juridique = serializers.ChoiceField(
        choices=["monopropriete", "copropriete"], required=True
    )
    identifiant_fiscal = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    periode_construction = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ZoneReglementaireSerializer(serializers.Serializer):
    """Zone réglementaire et autorisations"""

    zone_tendue = serializers.BooleanField(required=False, allow_null=True)
    permis_de_louer = serializers.BooleanField(required=False, allow_null=True)


# ============================================
# SERIALIZERS POUR LES PERSONNES
# ============================================


class PersonneSerializer(serializers.Serializer):
    """Serializer pour une personne (bailleur, locataire, signataire)"""

    id = serializers.UUIDField(required=False, allow_null=True, help_text="UUID généré côté frontend")
    lastName = serializers.CharField(max_length=100)
    firstName = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    date_naissance = serializers.DateField(required=False, allow_null=True)
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    adresse = serializers.CharField(required=False, allow_blank=True)
    iban = serializers.CharField(max_length=34, required=False, allow_blank=True)


class SocieteSerializer(serializers.Serializer):
    """Serializer pour une société"""

    raison_sociale = serializers.CharField(max_length=200)
    siret = serializers.CharField(max_length=14, min_length=14)
    forme_juridique = serializers.CharField(max_length=100)
    adresse = serializers.CharField()
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)


class BailleurInfoSerializer(serializers.Serializer):
    """Informations du bailleur (physique ou morale)"""

    bailleur_type = serializers.ChoiceField(
        choices=["physique", "morale"], default="physique"
    )
    personne = PersonneSerializer(required=False, allow_null=True)
    societe = SocieteSerializer(required=False, allow_null=True)
    signataire = PersonneSerializer(required=False, allow_null=True)
    co_bailleurs = serializers.ListField(child=PersonneSerializer(), required=False)

    def to_internal_value(self, data):
        """Nettoyer les données avant la validation"""
        # Récupérer le type de bailleur
        bailleur_type = data.get("bailleur_type", "physique")
        
        # Créer une copie des données pour ne pas modifier l'original
        cleaned_data = dict(data)
        
        # Nettoyer les champs non pertinents selon le type
        if bailleur_type == "physique":
            # Pour personne physique, supprimer les champs société
            cleaned_data.pop("societe", None)
            cleaned_data.pop("signataire", None)
        elif bailleur_type == "morale":
            # Pour personne morale, supprimer le champ personne s'il n'est pas utilisé comme signataire
            if "personne" in cleaned_data and "signataire" not in cleaned_data:
                # Conserver personne pour transformation en signataire
                pass
            elif "personne" in cleaned_data:
                cleaned_data.pop("personne", None)
        
        return super().to_internal_value(cleaned_data)

    def validate(self, data):
        """Validation : physique avec personne (adresse obligatoire), morale avec société et signataire"""
        bailleur_type = data.get("bailleur_type", "physique")

        if bailleur_type == "physique":
            if not data.get("personne"):
                raise serializers.ValidationError(
                    "Les informations de la personne sont requises pour un bailleur physique"
                )
            # Vérifier que l'adresse est fournie pour personne physique
            personne = data.get("personne", {})
            if not personne.get("adresse"):
                raise serializers.ValidationError(
                    {"personne": {"adresse": "L'adresse est requise pour un bailleur personne physique"}}
                )
            # Nettoyer les champs non pertinents
            data.pop("societe", None)
            data.pop("signataire", None)

        elif bailleur_type == "morale":
            if not data.get("societe"):
                raise serializers.ValidationError(
                    "Les informations de la société sont requises pour un bailleur moral"
                )
            if not data.get("signataire"):
                raise serializers.ValidationError(
                    "Les informations du signataire sont requises pour un bailleur moral"
                )
            # Nettoyer le champ personne
            data.pop("personne", None)
            
        return data


class LocataireInfoSerializer(PersonneSerializer):
    """Informations d'un locataire"""

    profession = serializers.CharField(required=False, allow_blank=True)
    revenus_mensuels = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )


# ============================================
# SERIALIZERS POUR LES MODALITÉS
# ============================================


class ModalitesFinancieresSerializer(serializers.Serializer):
    """Modalités financières de la location"""

    loyer_hors_charges = serializers.DecimalField(max_digits=10, decimal_places=2)
    charges = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    type_charges = serializers.ChoiceField(
        choices=["provisionnelles", "forfaitaires"], default="provisionnelles"
    )
    depot_garantie = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    jour_paiement = serializers.IntegerField(min_value=1, max_value=31, default=1)


class ModalitesZoneTendueSerializer(serializers.Serializer):
    """Modalités spécifiques zone tendue"""

    premiere_mise_en_location = serializers.BooleanField(required=False, allow_null=True)
    locataire_derniers_18_mois = serializers.BooleanField(required=False, allow_null=True)
    dernier_montant_loyer = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    justificatif_complement_loyer = serializers.CharField(
        required=False, allow_blank=True
    )


class DatesLocationSerializer(serializers.Serializer):
    """Dates de la location"""

    date_debut = serializers.DateField()
    date_fin = serializers.DateField(required=False, allow_null=True)
    duree_bail = serializers.IntegerField(default=3, min_value=1, max_value=99)


# ============================================
# SERIALIZERS COMPOSÉS PRINCIPAUX
# ============================================


class BienRentPriceSerializer(serializers.Serializer):
    """Serializer minimal pour calculer les prix de référence des loyers"""

    localisation = AdresseSerializer()
    # Utiliser des serializers imbriqués pour une validation correcte
    caracteristiques = serializers.DictField(required=False)
    regime = serializers.DictField(required=False)

    def to_internal_value(self, data):
        """Extraction des champs nécessaires pour le calcul du loyer de référence"""
        # Ne pas utiliser super() pour éviter la validation stricte des DictField
        localisation_serializer = AdresseSerializer(data=data.get("localisation", {}))
        localisation_serializer.is_valid(raise_exception=True)
        localisation_data = localisation_serializer.validated_data

        # Extraire les champs minimaux nécessaires
        caracteristiques = data.get("caracteristiques", {})
        regime = data.get("regime", {})

        result = {}

        # Ajouter seulement les champs présents
        if "area_id" in localisation_data:
            result["area_id"] = localisation_data["area_id"]
        if "type_bien" in caracteristiques:
            result["type_bien"] = caracteristiques["type_bien"]
        if "pieces_info" in caracteristiques:
            result["pieces_info"] = caracteristiques["pieces_info"]
        if "periode_construction" in regime:
            result["periode_construction"] = regime["periode_construction"]
        if "meuble" in caracteristiques:
            result["meuble"] = caracteristiques["meuble"]

        return result

    def create_bien_instance(self, validated_data):
        """Créer une instance Bien à partir des données validées"""
        from location.models import Bien

        bien = Bien()

        # Assigner seulement les champs présents dans validated_data
        if "type_bien" in validated_data:
            bien.type_bien = validated_data["type_bien"]
        if "pieces_info" in validated_data:
            bien.pieces_info = validated_data["pieces_info"]
        if "periode_construction" in validated_data:
            bien.periode_construction = validated_data["periode_construction"]
        if "meuble" in validated_data:
            bien.meuble = validated_data["meuble"]

        return bien


class BienQuittanceSerializer(serializers.Serializer):
    """Serializer minimal pour un bien dans une quittance"""

    localisation = AdresseSerializer(required=True)
    caracteristiques = CaracteristiquesBienSerializer(required=True)
    regime = RegimeJuridiqueSerializer(required=False)


class BienEtatLieuxSerializer(serializers.Serializer):
    """Serializer pour un bien dans un état des lieux"""

    localisation = AdresseSerializer()
    caracteristiques = CaracteristiquesBienSerializer()
    performance_energetique = PerformanceEnergetiqueSerializer(required=False)
    equipements = EquipementsSerializer()  # Décommenté pour accepter les équipements
    energie = EnergieSerializer()
    regime = RegimeJuridiqueSerializer(required=False)  # Ajouté pour sauvegarder regime_juridique et periode_construction
    zone_reglementaire = ZoneReglementaireSerializer(required=False)


class BienBailSerializer(serializers.Serializer):
    """Serializer complet pour un bien dans un bail"""

    localisation = AdresseSerializer()
    caracteristiques = CaracteristiquesBienSerializer()
    performance_energetique = PerformanceEnergetiqueSerializer()
    equipements = EquipementsSerializer()
    energie = EnergieSerializer()
    regime = RegimeJuridiqueSerializer()
    zone_reglementaire = ZoneReglementaireSerializer(required=False)

    class Meta:
        # Pour la génération, on indique qu'il s'agit d'une composition
        is_composite = True
        components = [
            "localisation",
            "caracteristiques",
            "performance_energetique",
            "equipements",
            "energie",
            "regime",
            "zone_reglementaire",
        ]


# ============================================
# SERIALIZERS POUR CRÉATION VIA /location/create-or-update/
# ============================================

# Import des serializers spécifiques par pays
from location.serializers.france import (
    FranceBailSerializer,
    FranceQuittanceSerializer,
    FranceEtatLieuxSerializer,
)

# Alias pour utilisation dans views.py
CreateBailSerializer = FranceBailSerializer
CreateQuittanceSerializer = FranceQuittanceSerializer
CreateEtatLieuxSerializer = FranceEtatLieuxSerializer


