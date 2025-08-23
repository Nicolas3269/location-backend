from rest_framework import serializers

from .models import (
    Bailleur,
    Bien,
    Locataire,
    Location,
    Personne,
    RentTerms,
    Societe,
)


class PersonneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Personne
        fields = "__all__"


class SocieteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Societe
        fields = "__all__"


class BailleurSerializer(serializers.ModelSerializer):
    personne = PersonneSerializer(required=False)
    societe = SocieteSerializer(required=False)
    signataire = PersonneSerializer(required=False)

    class Meta:
        model = Bailleur
        fields = "__all__"


class LocataireSerializer(serializers.ModelSerializer):
    class Meta:
        model = Locataire
        fields = "__all__"


class BienSerializer(serializers.ModelSerializer):
    bailleurs = BailleurSerializer(many=True, required=False)

    # Override les champs booléens pour gérer proprement la conversion
    dernier_etage = serializers.BooleanField(default=False)
    meuble = serializers.BooleanField(default=False)

    class Meta:
        model = Bien
        fields = "__all__"


class RentTermsSerializer(serializers.ModelSerializer):
    zone_tendue = serializers.BooleanField(default=False)
    permis_de_louer = serializers.BooleanField(default=False)

    class Meta:
        model = RentTerms
        fields = "__all__"


class LocationSerializer(serializers.ModelSerializer):
    bien = BienSerializer(required=False)
    locataires = LocataireSerializer(many=True, required=False)
    rent_terms = RentTermsSerializer(required=False)

    # Override le champ booléen
    solidaires = serializers.BooleanField(default=False)

    class Meta:
        model = Location
        fields = "__all__"


class CreateLocationSerializer(serializers.Serializer):
    """
    Serializer pour créer/mettre à jour une location avec toutes ses dépendances
    """

    # Source
    source = serializers.ChoiceField(
        choices=["bail", "quittance", "etat_lieux", "manual"], default="manual"
    )

    # Bien - Champs requis
    adresse = serializers.CharField(required=True)
    superficie = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True
    )
    type_bien = serializers.CharField(default="appartement", required=False)
    regime_juridique = serializers.CharField(default="monopropriete", required=False)

    # Bien - Champs booléens
    dernier_etage = serializers.BooleanField(default=False, required=False)
    meuble = serializers.CharField(
        default=False, required=False
    )  # CharField pour accepter "meuble"/"vide"
    permis_de_louer = serializers.BooleanField(default=False, required=False)
    zone_tendue = serializers.BooleanField(default=False, required=False)

    # Bien - Champs optionnels
    classe_dpe = serializers.CharField(default="NA", required=False, allow_blank=True)
    depenses_energetiques = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    periode_construction = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    etage = serializers.CharField(required=False, allow_blank=True, default="")
    porte = serializers.CharField(required=False, allow_blank=True, default="")

    # Localisation
    latitude = serializers.DecimalField(
        max_digits=10, decimal_places=7, required=False, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=10, decimal_places=7, required=False, allow_null=True
    )
    area_id = serializers.IntegerField(required=False, allow_null=True)

    # Équipements et annexes
    annexes = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    annexes_collectives = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    chauffage = serializers.DictField(required=False, default=dict)
    eau_chaude = serializers.DictField(required=False, default=dict)
    information = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    pieces_info = serializers.DictField(required=False, default=dict)

    # Bailleur
    bailleur_type = serializers.ChoiceField(
        choices=["physique", "morale"], default="physique"
    )
    landlord = serializers.DictField(required=True)
    siret = serializers.CharField(required=False, allow_blank=True, default="")
    societe = serializers.DictField(required=False, default=dict)
    other_landlords = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )

    # Locataires
    locataires = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )

    # Location
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)
    solidaires = serializers.BooleanField(default=False)

    # Modalités
    modalites = serializers.DictField(required=False, default=dict)

    # IDs existants (pour update)
    location_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_meuble(self, value):
        """Convertit meuble (peut être 'meuble'/'vide') en booléen"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            # Gestion spécifique pour meuble/vide
            if value.lower() == "meuble":
                return True
            elif value.lower() in ["vide", ""]:
                return False
            # Gestion générique pour true/false
            elif value.lower() in ["true", "1", "yes", "oui"]:
                return True
            else:
                return False
        return bool(value)

    def validate_solidaires(self, value):
        """S'assure que solidaires est un booléen"""
        if isinstance(value, str):
            if value.lower() in ["true", "1", "yes", "oui"]:
                return True
            elif value.lower() in ["false", "0", "no", "non", "vide", ""]:
                return False
        return bool(value)
