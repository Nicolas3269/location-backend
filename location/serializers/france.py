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
    PersonneSerializer,
)


class FranceBailSerializer(serializers.Serializer):
    """
    Serializer pour un bail en France.
    Définit les champs obligatoires et conditionnels selon la réglementation française.
    """

    # Champ pour tracer l'origine du document
    source = serializers.CharField(default="bail")

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
        L'ordre est défini par la position dans la liste.
        Les IDs correspondent directement aux clés du FORM_COMPONENTS_CATALOG du frontend.
        """
        return [
            # BIEN - Localisation
            {"id": "bien.localisation.adresse"},
            # BIEN - Type et surface et etage
            {"id": "bien.caracteristiques.type_bien"},
            {"id": "bien.regime.regime_juridique"},
            {"id": "bien.regime.periode_construction"},
            {"id": "bien.caracteristiques.superficie"},
            {"id": "bien.caracteristiques.pieces_info"},
            # BIEN - Détails
            {"id": "bien.caracteristiques.meuble"},
            # BIEN - Équipements
            {"id": "bien.equipements.annexes_privatives"},
            {"id": "bien.equipements.annexes_collectives"},
            {"id": "bien.equipements.information"},
            # BIEN - Énergie
            {"id": "bien.energie.chauffage"},
            {"id": "bien.energie.eau_chaude"},
            # BIEN - Performance
            {"id": "bien.performance_energetique.classe_dpe"},
            {
                "id": "bien.performance_energetique.depenses_energetiques",
                "condition": "dpe_not_na",
            },
            {"id": "bien.regime.identifiant_fiscal"},
            # BAILLEUR
            {"id": "bailleur.bailleur_type"},
            {"id": "bailleur.personne", "condition": "bailleur_is_physique"},
            {"id": "bailleur.signataire", "condition": "bailleur_is_morale"},
            {"id": "bailleur.societe", "condition": "bailleur_is_morale"},
            {"id": "bailleur.co_bailleurs"},
            # LOCATAIRES
            {"id": "locataires"},
            {"id": "solidaires", "condition": "has_multiple_tenants"},
            # DATES
            {"id": "dates.date_debut"},
            # ZONE TENDUE (conditionnel - déterminé automatiquement par l'adresse)
            {
                "id": "modalites_zone_tendue.premiere_mise_en_location",
                "condition": "zone_tendue",
            },
            {
                "id": "modalites_zone_tendue.locataire_derniers_18_mois",
                "condition": "zone_tendue_not_first_rental",
            },
            {
                "id": "modalites_zone_tendue.dernier_montant_loyer",
                "condition": "zone_tendue_has_previous_tenant",
            },
            # MODALITÉS FINANCIÈRES
            {"id": "modalites_financieres.loyer_hors_charges"},
            {"id": "modalites_financieres.charges_mensuelles"},
        ]


class FranceQuittanceSerializer(serializers.Serializer):
    """
    Serializer pour une quittance en France.
    """

    # Champ pour tracer l'origine du document
    source = serializers.CharField(default="quittance")

    # Champs obligatoires pour une quittance
    bien = BienQuittanceSerializer(required=True)  # Juste l'adresse
    bailleur = BailleurInfoSerializer(required=True)
    locataires = serializers.ListField(
        child=PersonneSerializer(), min_length=1, required=True
    )
    modalites_financieres = ModalitesFinancieresSerializer(required=True)

    # Options de location
    solidaires = serializers.BooleanField(
        default=False, help_text="Les locataires sont-ils solidaires ?"
    )

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
        L'ordre est défini par la position dans la liste.
        """
        return [
            # BIEN - Juste l'essentiel pour une quittance
            {"id": "bien.localisation.adresse"},
            {"id": "bien.caracteristiques.type_bien"},
            {"id": "bien.caracteristiques.superficie"},
            {"id": "bien.caracteristiques.pieces_info"},
            {"id": "bien.caracteristiques.meuble"},
            # BAILLEUR
            {"id": "bailleur.bailleur_type"},
            {"id": "bailleur.personne", "condition": "bailleur_is_physique"},
            {"id": "bailleur.signataire", "condition": "bailleur_is_morale"},
            {"id": "bailleur.societe", "condition": "bailleur_is_morale"},
            {"id": "bailleur.co_bailleurs"},
            # LOCATAIRES
            {"id": "locataires"},
            {"id": "solidaires", "condition": "has_multiple_tenants"},
            # Modalités financières
            {"id": "modalites_financieres.loyer_hors_charges"},
            {"id": "modalites_financieres.charges_mensuelles"},
            # La période est toujours demandée
            {"id": "periode_quittance"},
        ]


class FranceEtatLieuxSerializer(serializers.Serializer):
    """
    Serializer pour un état des lieux en France.
    """

    # Champ pour tracer l'origine du document
    source = serializers.CharField(default="etat_lieux")

    # Champs obligatoires
    bien = BienEtatLieuxSerializer(required=True)
    bailleur = BailleurInfoSerializer(required=True)
    locataires = serializers.ListField(
        child=PersonneSerializer(), min_length=1, required=True
    )

    # Dates et modalités optionnelles pour état des lieux
    dates = DatesLocationSerializer(required=False)
    modalites_financieres = ModalitesFinancieresSerializer(required=False)

    # Options de location
    solidaires = serializers.BooleanField(
        default=False, help_text="Les locataires sont-ils solidaires ?"
    )

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
        L'ordre est défini par la position dans la liste.
        """
        return [
            # BIEN - Localisation
            {"id": "bien.localisation.adresse"},
            # BIEN - Type et surface et etage
            {"id": "bien.caracteristiques.type_bien"},
            {"id": "bien.regime.regime_juridique"},
            {"id": "bien.regime.periode_construction"},
            {"id": "bien.caracteristiques.superficie"},
            {"id": "bien.caracteristiques.pieces_info"},
            # BIEN - Détails
            {"id": "bien.caracteristiques.meuble"},
            # BIEN - Équipements
            {"id": "bien.equipements.annexes_privatives"},
            {"id": "bien.equipements.annexes_collectives"},
            {"id": "bien.equipements.information"},
            # BIEN - Énergie
            {"id": "bien.energie.chauffage"},
            {"id": "bien.energie.eau_chaude"},
            # BAILLEUR
            {"id": "bailleur.bailleur_type"},
            {"id": "bailleur.personne", "condition": "bailleur_is_physique"},
            {"id": "bailleur.signataire", "condition": "bailleur_is_morale"},
            {"id": "bailleur.societe", "condition": "bailleur_is_morale"},
            {"id": "bailleur.co_bailleurs"},
            # LOCATAIRES
            {"id": "locataires"},
            {"id": "solidaires", "condition": "has_multiple_tenants"},
            # MODALITÉS ÉTAT DES LIEUX
            {"id": "type_etat_lieux"},
            {"id": "date_etat_lieux"},
            # ÉTAT DES LIEUX
            {"id": "description_pieces"},
            {"id": "nombre_cles"},
            {"id": "equipements_chauffage"},
            {"id": "releve_compteurs"},
        ]
