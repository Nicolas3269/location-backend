# serializers.py
from rest_framework import serializers

from .models import BailSpecificites, Bien, Locataire, Proprietaire


class ProprietaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proprietaire
        fields = ["id", "nom", "prenom", "adresse", "telephone", "email", "iban"]
        read_only_fields = ["id"]


class BienSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bien
        fields = [
            "id",
            "adresse",
            "latitude",
            "longitude",
            "type_bien",
            "etage",
            "porte",
            "dernier_etage",
            "periode_construction",
            "superficie",
            "nb_pieces",
            "meuble",
            "classe_dpe",
            "depenses_energetiques",
            "annexes",
            "additionnal_description",
            "annexes_privatives",
            "annexes_collectives",
            "equipements",
            "chauffage_type",
            "chauffage_energie",
            "eau_chaude_type",
            "eau_chaude_energie",
        ]
        read_only_fields = ["id"]


class LocataireSerializer(serializers.ModelSerializer):
    class Meta:
        model = Locataire
        fields = [
            "id",
            "nom",
            "prenom",
            "date_naissance",
            "lieu_naissance",
            "adresse_actuelle",
            "telephone",
            "email",
            "profession",
            "employeur",
            "revenu_mensuel",
            "num_carte_identite",
            "date_emission_ci",
        ]
        read_only_fields = ["id"]


class BailSpecificitesSerializer(serializers.ModelSerializer):
    class Meta:
        model = BailSpecificites
        fields = [
            "id",
            "bien",
            "date_debut",
            "date_fin",
            "montant_loyer",
            "montant_charges",
            "jour_paiement",
            "depot_garantie",
            "releve_eau_entree",
            "releve_elec_entree",
            "releve_gaz_entree",
            "date_signature",
            "date_etat_lieux_entree",
            "observations",
            "zone_tendue",
            "prix_reference",
            "complement_loyer",
            "is_draft",
        ]
        read_only_fields = ["id"]


class BailCreationProgressSerializer(serializers.Serializer):
    """Serializer pour suivre la progression de création du bail"""

    proprietaire_id = serializers.IntegerField(required=False)
    bien_id = serializers.IntegerField(required=False)
    locataires_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )
    current_step = serializers.CharField(max_length=50)
