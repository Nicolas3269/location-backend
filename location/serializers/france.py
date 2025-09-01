"""
Serializers spécifiques pour la France.
Définit les règles métier et validations pour les formulaires français.
"""

from rest_framework import serializers

from ..serializers_composed import (
    BailleurInfoSerializer,
    BienBailSerializer,
    BienEtatLieuxSerializer,
    BienQuittanceSerializer,
    DatesLocationSerializer,
    LocataireInfoSerializer,
    ModalitesFinancieresSerializer,
    ModalitesZoneTendueSerializer,
    PersonneBaseSerializer,
)


class FranceBailSerializer(serializers.Serializer):
    """
    Serializer pour un bail en France.
    Définit les champs obligatoires et conditionnels selon la réglementation française.
    """

    # Champ pour tracer l'origine du document
    source = serializers.CharField(default="bail", read_only=True)

    # Champs toujours obligatoires
    bien = BienBailSerializer(required=True)
    bailleur = BailleurInfoSerializer(required=True)
    locataires = serializers.ListField(
        child=LocataireInfoSerializer(), min_length=1, required=True
    )
    modalites_financieres = ModalitesFinancieresSerializer(required=True)
    dates = DatesLocationSerializer(required=True)

    # Champ conditionnel (obligatoire si zone tendue)
    modalites_zone_tendue = ModalitesZoneTendueSerializer(required=False)

    # Options
    solidaires = serializers.BooleanField(
        default=False, help_text="Les locataires sont-ils solidaires ?"
    )

    @classmethod
    def get_step_config(cls):
        """
        Configuration des steps du formulaire bail France.
        Définit l'ordre et les champs de chaque step.
        Les IDs correspondent directement aux clés du FORM_COMPONENTS_CATALOG du frontend.
        """
        return {
            # BIEN - Localisation
            "bien.localisation.adresse": {
                "order": 10,
            },
            # BIEN - Type et surface et etage
            "bien.caracteristiques.type_bien": {
                "order": 20,
            },
            "bien.regime.regime_juridique": {
                "order": 30,
            },
            "bien.regime.periode_construction": {
                "order": 40,
            },
            "bien.caracteristiques.superficie": {
                "order": 50,
            },
            "bien.caracteristiques.pieces_info": {
                "order": 60,
            },
            # BIEN - Détails
            "bien.caracteristiques.meuble": {
                "order": 70,
            },
            # BIEN - Équipements
            "bien.equipements.annexes_privatives": {
                "order": 80,
            },
            "bien.equipements.annexes_collectives": {
                "order": 90,
            },
            "bien.equipements.information": {
                "order": 100,
            },
            # BIEN - Énergie
            "bien.energie.chauffage": {
                "order": 110,
            },
            "bien.energie.eau_chaude": {
                "order": 120,
            },
            # BIEN - Performance
            "bien.performance_energetique.classe_dpe": {
                "order": 130,
            },
            "bien.performance_energetique.depenses_energetiques": {
                "order": 140,
                "condition": "dpe_not_na",
            },
            "bien.regime.identifiant_fiscal": {
                "order": 160,
            },
            # BAILLEUR
            "bailleur.bailleur_type": {
                "order": 170,
            },
            "bailleur.personne": {
                "order": 180,
                "condition": "bailleur_is_person",
            },
            "bailleur.societe": {
                "order": 190,
                "condition": "bailleur_is_company",
            },
            "bailleur.co_bailleurs": {
                "order": 200,
            },
            # LOCATAIRES
            "locataires": {"order": 210},
            "solidaires": {
                "order": 220,
                "condition": "has_multiple_tenants",
            },
            # DATES
            "dates.date_debut": {
                "order": 230,
            },
            # ZONE TENDUE (conditionnel - déterminé automatiquement par l'adresse)
            "modalites_zone_tendue.premiere_mise_en_location": {
                "order": 240,
                "condition": "zone_tendue",
            },
            "modalites_zone_tendue.locataire_derniers_18_mois": {
                "order": 250,
                "condition": "zone_tendue_not_first_rental",
            },
            "modalites_zone_tendue.dernier_montant_loyer": {
                "order": 260,
                "condition": "zone_tendue_has_previous_tenant",
            },
            # MODALITÉS FINANCIÈRES
            "modalites_financieres.loyer_hors_charges": {
                "order": 270,
            },
            "modalites_financieres.charges_mensuelles": {
                "order": 280,
            },
        }


class FranceQuittanceSerializer(serializers.Serializer):
    """
    Serializer pour une quittance en France.
    """

    # Champ pour tracer l'origine du document
    source = serializers.CharField(default="quittance", read_only=True)

    # Champs obligatoires pour une quittance
    bien = BienQuittanceSerializer(required=True)  # Juste l'adresse
    bailleur = BailleurInfoSerializer(required=True)
    locataires = serializers.ListField(
        child=PersonneBaseSerializer(), min_length=1, required=True
    )
    modalites_financieres = ModalitesFinancieresSerializer(required=True)

    # Spécifique quittance
    periode_quittance = serializers.DictField(
        child=serializers.CharField(),
        required=True,
        help_text="Mois et année de la quittance",
    )

    @classmethod
    def get_step_config(cls):
        """
        Configuration des steps du formulaire quittance France.
        Plus simple car la plupart des données viennent du bail existant.
        """
        return {
            # BIEN - Localisation
            "bien.localisation.adresse": {
                "order": 10,
            },
            # BIEN - Type et surface et etage
            "bien.caracteristiques.type_bien": {
                "order": 20,
            },
            "bien.regime.regime_juridique": {
                "order": 30,
            },
            "bien.regime.periode_construction": {
                "order": 40,
            },
            "bien.caracteristiques.superficie": {
                "order": 50,
            },
            "bien.caracteristiques.pieces_info": {
                "order": 60,
            },
            # BIEN - Détails
            "bien.caracteristiques.meuble": {
                "order": 70,
            },
            # BAILLEUR
            "bailleur.bailleur_type": {
                "order": 170,
            },
            "bailleur.personne": {
                "order": 180,
                "condition": "bailleur_is_person",
            },
            "bailleur.societe": {
                "order": 190,
                "condition": "bailleur_is_company",
            },
            "bailleur.co_bailleurs": {
                "order": 200,
            },
            # LOCATAIRES
            "locataires": {"order": 210},
            "solidaires": {
                "order": 220,
                "condition": "has_multiple_tenants",
            },
            # Modalités financières
            "modalites_financieres.loyer_hors_charges": {
                "order": 300,
            },
            "modalites_financieres.charges_mensuelles": {
                "order": 310,
            },
            # La période est toujours demandée
            "periode_quittance": {
                "order": 400,
            },
        }


class FranceEtatLieuxSerializer(serializers.Serializer):
    """
    Serializer pour un état des lieux en France.
    """

    # Champ pour tracer l'origine du document
    source = serializers.CharField(default="etat_lieux", read_only=True)

    # Champs obligatoires
    bien = BienEtatLieuxSerializer(required=True)
    bailleur = BailleurInfoSerializer(required=True)
    locataires = serializers.ListField(
        child=PersonneBaseSerializer(), min_length=1, required=True
    )

    # Dates et modalités optionnelles pour état des lieux
    dates = DatesLocationSerializer(required=False)
    modalites_financieres = ModalitesFinancieresSerializer(required=False)

    # Champs spécifiques état des lieux
    type_etat_lieux = serializers.ChoiceField(
        choices=["entree", "sortie"], required=True
    )
    date_etat_lieux = serializers.DateField(required=True)

    # Description détaillée
    description_pieces = serializers.JSONField(
        required=True, help_text="Description détaillée de l'état de chaque pièce"
    )
    releve_compteurs = serializers.JSONField(
        required=False, help_text="Relevés des compteurs (eau, gaz, électricité)"
    )
    nombre_cles = serializers.IntegerField(
        required=False, default=1, help_text="Nombre de clés remises"
    )
    equipements_chauffage = serializers.JSONField(
        required=False, default=dict, help_text="État des équipements de chauffage"
    )

    @classmethod
    def get_step_config(cls):
        """
        Configuration des steps du formulaire état des lieux France.
        """
        return {
            # BIEN - Localisation
            "bien.localisation.adresse": {
                "order": 10,
            },
            # BIEN - Type et surface et etage
            "bien.caracteristiques.type_bien": {
                "order": 20,
            },
            "bien.regime.regime_juridique": {
                "order": 30,
            },
            "bien.regime.periode_construction": {
                "order": 40,
            },
            "bien.caracteristiques.superficie": {
                "order": 50,
            },
            "bien.caracteristiques.pieces_info": {
                "order": 60,
            },
            # BIEN - Détails
            "bien.caracteristiques.meuble": {
                "order": 70,
            },
            # BIEN - Équipements
            "bien.equipements.annexes_privatives": {
                "order": 80,
            },
            "bien.equipements.annexes_collectives": {
                "order": 90,
            },
            "bien.equipements.information": {
                "order": 100,
            },
            # BIEN - Énergie
            "bien.energie.chauffage": {
                "order": 110,
            },
            "bien.energie.eau_chaude": {
                "order": 120,
            },
            # BAILLEUR
            "bailleur.bailleur_type": {
                "order": 170,
            },
            "bailleur.personne": {
                "order": 180,
                "condition": "bailleur_is_person",
            },
            "bailleur.societe": {
                "order": 190,
                "condition": "bailleur_is_company",
            },
            "bailleur.co_bailleurs": {
                "order": 200,
            },
            # LOCATAIRES
            "locataires": {"order": 210},
            "solidaires": {
                "order": 220,
                "condition": "has_multiple_tenants",
            },
            # MODALITÉS ÉTAT DES LIEUX
            "type_etat_lieux": {
                "order": 330,
            },
            "date_etat_lieux": {
                "order": 330,
            },
            # ÉTAT DES LIEUX
            "description_pieces": {
                "order": 400,
            },
            "nombre_cles": {
                "order": 410,
            },
            "equipements_chauffage": {
                "order": 420,
            },
            "releve_compteurs": {
                "order": 430,
            },
        }
