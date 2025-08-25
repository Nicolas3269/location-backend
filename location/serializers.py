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


# Les serializers de création complexes sont dans serializers_composed.py
# pour une meilleure organisation avec l'architecture composée
