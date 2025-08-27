"""
Serializers spécifiques pour la France.
Définit les règles métier et validations pour les formulaires français.
"""

from rest_framework import serializers
from ..serializers_composed import (
    BienBailSerializer,
    BailleurInfoSerializer,
    LocataireInfoSerializer,
    PersonneBaseSerializer,
    ModalitesFinancieresSerializer,
    ModalitesZoneTendueSerializer,
    DatesLocationSerializer,
    BienQuittanceSerializer,
    BienEtatLieuxSerializer,
)


class FranceBailSerializer(serializers.Serializer):
    """
    Serializer pour un bail en France.
    Définit les champs obligatoires et conditionnels selon la réglementation française.
    """

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

    def validate(self, data):
        """
        Validation conditionnelle pour la France.
        """
        # Si zone tendue, les modalités zone tendue deviennent obligatoires
        zone_tendue = (
            data.get("bien", {})
            .get("zone_reglementaire", {})
            .get("zone_tendue", False)
        )

        if zone_tendue:
            if not data.get("modalites_zone_tendue"):
                raise serializers.ValidationError(
                    {
                        "modalites_zone_tendue": "Les informations de zone tendue sont obligatoires en zone réglementée"
                    }
                )

            # Valider les champs conditionnels dans modalites_zone_tendue
            modalites_zt = data.get("modalites_zone_tendue", {})

            # Si ce n'est pas la première mise en location
            if modalites_zt.get("premiere_mise_en_location") is False:
                # Vérifier si un locataire dans les 18 derniers mois
                if modalites_zt.get("locataire_derniers_18_mois") is None:
                    raise serializers.ValidationError(
                        {
                            "modalites_zone_tendue.locataire_derniers_18_mois": "Cette information est requise si ce n'est pas la première mise en location"
                        }
                    )

                # Si oui, le dernier montant du loyer est requis
                if modalites_zt.get("locataire_derniers_18_mois") is True:
                    if not modalites_zt.get("dernier_montant_loyer"):
                        raise serializers.ValidationError(
                            {
                                "modalites_zone_tendue.dernier_montant_loyer": "Le dernier montant du loyer est requis s'il y a eu un locataire dans les 18 derniers mois"
                            }
                        )

        # Validation des dates
        dates = data.get("dates", {})
        if dates.get("date_fin") and dates.get("date_debut"):
            if dates["date_fin"] <= dates["date_debut"]:
                raise serializers.ValidationError(
                    {"dates": "La date de fin doit être après la date de début"}
                )

        # Validation de solidarité si plusieurs locataires
        if len(data.get("locataires", [])) > 1 and "solidaires" not in data:
            # En France, par défaut les colocataires sont solidaires
            data["solidaires"] = True

        return data

    def get_conditional_fields(self):
        """
        Retourne la liste des champs conditionnels avec leurs conditions.
        Les conditions sont des clés référençant des fonctions dans le frontend.
        """
        return [
            # Bailleur - conditionnel selon le type
            {
                "field": "bailleur.personne",
                "condition": "bailleur_is_person",
                "depends_on": ["bailleur.bailleur_type"],
            },
            {
                "field": "bailleur.societe",
                "condition": "bailleur_is_company",
                "depends_on": ["bailleur.bailleur_type"],
            },
            # Solidaires - conditionnel si plusieurs locataires
            {
                "field": "solidaires",
                "condition": "has_multiple_tenants",
                "depends_on": ["locataires"],
            },
            # Performance énergétique
            {
                "field": "bien.performance_energetique.depenses_energetiques",
                "condition": "dpe_not_na",  # Clé de condition définie dans conditions.ts
                "depends_on": ["bien.performance_energetique.classe_dpe"],
            },
            # Zone tendue
            {
                "field": "modalites_zone_tendue.premiere_mise_en_location",
                "condition": "zone_tendue",
                "depends_on": [],  # zone_tendue est calculé automatiquement depuis l'adresse
            },
            {
                "field": "modalites_zone_tendue.locataire_derniers_18_mois",
                "condition": "zone_tendue_not_first_rental",
                "depends_on": [
                    "modalites_zone_tendue.premiere_mise_en_location",
                ],
            },
            {
                "field": "modalites_zone_tendue.dernier_montant_loyer",
                "condition": "zone_tendue_has_previous_tenant",
                "depends_on": [
                    "modalites_zone_tendue.premiere_mise_en_location",
                    "modalites_zone_tendue.locataire_derniers_18_mois",
                ],
            },
        ]


class FranceQuittanceSerializer(serializers.Serializer):
    """
    Serializer pour une quittance en France.
    """

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


class FranceEtatLieuxSerializer(serializers.Serializer):
    """
    Serializer pour un état des lieux en France.
    """

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