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

ADRESSE_STEPS = [
    {"id": "bien.localisation.adresse"},
]
TYPE_BIEN_STEPS = [
    {"id": "bien.caracteristiques.type_bien"},
]
REGIME_JURIDIQUE_STEPS = [{"id": "bien.regime.regime_juridique"}]
PERIODE_CONSTRUCTION_STEPS = [{"id": "bien.regime.periode_construction"}]
SUPERFICIE_STEPS = [{"id": "bien.caracteristiques.superficie"}]
PIECES_INFO_STEPS = [{"id": "bien.caracteristiques.pieces_info"}]
# # BIEN - Détails
MEUBLE_STEPS = [{"id": "bien.caracteristiques.meuble"}]


PERSON_STEPS = [
    # BAILLEUR
    {"id": "bailleur.bailleur_type"},
    {"id": "bailleur.personne", "condition": "bailleur_is_physique"},
    {"id": "bailleur.signataire", "condition": "bailleur_is_morale"},
    {"id": "bailleur.societe", "condition": "bailleur_is_morale"},
    {"id": "bailleur.co_bailleurs"},
    # LOCATAIRES
    {"id": "locataires"},
    {"id": "solidaires", "condition": "has_multiple_tenants"},
]
EQUIPEMENTS_AND_ENERGY_STEPS = [
    # BIEN - Équipements
    {"id": "bien.equipements.annexes_privatives", "default": []},
    {"id": "bien.equipements.annexes_collectives", "default": []},
    {"id": "bien.equipements.information", "default": []},
    # BIEN - Énergie
    {"id": "bien.energie.chauffage"},
    {"id": "bien.energie.eau_chaude"},
]

EQUIPEMENTS_ETAT_LIEUX_STEPS = [
    # BIEN - Équipements
    {"id": "bien.equipements.annexes_privatives", "default": []},
]
ETAT_LIEUX_ENERGY_STEPS = [
    # BIEN - Énergie
    {"id": "bien.energie.chauffage"},
    {"id": "bien.energie.eau_chaude"},
]
DPE_STEPS = [
    # BIEN - DPE
    {"id": "bien.performance_energetique.classe_dpe"},
    {
        "id": "bien.performance_energetique.depenses_energetiques",
        "condition": "dpe_not_na",
    },
    {"id": "bien.regime.identifiant_fiscal"},
]

BAIL_DATE = [{"id": "dates.date_debut"}]

MODALITES_FINANCIERES_STEPS = [
    # Modalités financières
    {"id": "modalites_financieres.loyer_hors_charges"},
    {"id": "modalites_financieres.charges_mensuelles"},
]

ZONE_TENDUE_STEPS = [
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
]
PERIODE_QUITTANCE_STEPS = [
    {"id": "periode_quittance"},
]
DETAIL_ETAT_LIEUX_EQUIPEMENT_STEPS = [
    {"id": "equipements_chauffage"},
    {"id": "releve_compteurs"},
]
ETAT_LIEUX_CLES_STEPS = [
    {"id": "nombre_cles"},
]
ETAT_LIEUX_DEFINITION_STEPS = [
    {"id": "type_etat_lieux"},
    {"id": "date_etat_lieux"},
]
DETAIL_ETAT_LIEUX_STEPS = [
    # ÉTAT DES LIEUX
    {"id": "description_pieces"},
]


class BaseLocationSerializer(serializers.Serializer):
    """
    Serializer de base pour tous les documents de location.
    Contient les champs communs à tous les documents.
    """

    # Identifiant de la location existante (pour mise à jour)
    location_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    # Type de document source
    source = serializers.CharField(required=True)


class FranceBailSerializer(BaseLocationSerializer):
    """
    Serializer pour un bail en France.
    Définit les champs obligatoires et conditionnels selon la réglementation française.
    """

    # Override source avec valeur par défaut
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
        BAIL_STEPS = []
        BAIL_STEPS.extend(ADRESSE_STEPS)
        BAIL_STEPS.extend(TYPE_BIEN_STEPS)
        BAIL_STEPS.extend(REGIME_JURIDIQUE_STEPS)
        BAIL_STEPS.extend(PERIODE_CONSTRUCTION_STEPS)
        BAIL_STEPS.extend(SUPERFICIE_STEPS)
        BAIL_STEPS.extend(PIECES_INFO_STEPS)
        BAIL_STEPS.extend(MEUBLE_STEPS)

        BAIL_STEPS.extend(EQUIPEMENTS_AND_ENERGY_STEPS)
        BAIL_STEPS.extend(DPE_STEPS)
        BAIL_STEPS.extend(PERSON_STEPS)
        BAIL_STEPS.extend(ZONE_TENDUE_STEPS)
        BAIL_STEPS.extend(BAIL_DATE)

        BAIL_STEPS.extend(MODALITES_FINANCIERES_STEPS)

        return BAIL_STEPS


class FranceQuittanceSerializer(BaseLocationSerializer):
    """
    Serializer pour une quittance en France.
    """

    # Override source avec valeur par défaut
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
    date_paiement = serializers.DateField(
        required=True,
        help_text="Date du paiement du loyer",
    )

    @classmethod
    def get_step_config(cls):
        """
        Configuration des steps du formulaire quittance France.
        Plus simple car la plupart des données viennent du bail existant.
        L'ordre est défini par la position dans la liste.
        """
        QUITTANCE_STEPS = []
        QUITTANCE_STEPS.extend(ADRESSE_STEPS)
        QUITTANCE_STEPS.extend(TYPE_BIEN_STEPS)
        QUITTANCE_STEPS.extend(SUPERFICIE_STEPS)
        QUITTANCE_STEPS.extend(PERSON_STEPS)
        QUITTANCE_STEPS.extend(MODALITES_FINANCIERES_STEPS)
        QUITTANCE_STEPS.extend(PERIODE_QUITTANCE_STEPS)
        return QUITTANCE_STEPS


class FranceEtatLieuxSerializer(BaseLocationSerializer):
    """
    Serializer pour un état des lieux en France.
    """

    # Override source avec valeur par défaut
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

    releve_compteurs = serializers.JSONField(
        required=False, help_text="Relevés des compteurs (eau, gaz, électricité)"
    )
    nombre_cles = serializers.JSONField(
        required=False, default=dict, help_text="Nombre de clés remises"
    )
    equipements_chauffage = serializers.JSONField(
        required=False, default=dict, help_text="État des équipements de chauffage"
    )

    # Rooms avec leur état (pour l'état des lieux)
    rooms = serializers.JSONField(
        required=False, default=list, help_text="Détails des pièces avec leur état"
    )

    # Références des photos pour le multipart
    photo_references = serializers.JSONField(
        required=False, default=list, help_text="Références des photos uploadées"
    )

    @classmethod
    def get_step_config(cls):
        """
        Configuration des steps du formulaire état des lieux France.
        L'ordre est défini par la position dans la liste.
        """
        ETAT_LIEUX_STEPS = []
        ETAT_LIEUX_STEPS.extend(ETAT_LIEUX_DEFINITION_STEPS)
        ETAT_LIEUX_STEPS.extend(MEUBLE_STEPS)
        ETAT_LIEUX_STEPS.extend(PERSON_STEPS)
        ETAT_LIEUX_STEPS.extend(ADRESSE_STEPS)
        ETAT_LIEUX_STEPS.extend(TYPE_BIEN_STEPS)
        ETAT_LIEUX_STEPS.extend(EQUIPEMENTS_ETAT_LIEUX_STEPS)
        ETAT_LIEUX_STEPS.extend(ETAT_LIEUX_CLES_STEPS)
        ETAT_LIEUX_STEPS.extend(ETAT_LIEUX_ENERGY_STEPS)
        ETAT_LIEUX_STEPS.extend(DETAIL_ETAT_LIEUX_EQUIPEMENT_STEPS)
        ETAT_LIEUX_STEPS.extend(PIECES_INFO_STEPS)
        ETAT_LIEUX_STEPS.extend(DETAIL_ETAT_LIEUX_STEPS)
        return ETAT_LIEUX_STEPS
