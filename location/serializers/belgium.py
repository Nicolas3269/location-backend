"""
Serializers spécifiques pour la Belgique.
Définit les règles métier et validations pour les formulaires belges.
"""

from rest_framework import serializers
from ..serializers_composed import (
    BienBailSerializer,
    BailleurInfoSerializer,
    LocataireInfoSerializer,
    PersonneBaseSerializer,
    ModalitesFinancieresSerializer,
    DatesLocationSerializer,
    BienQuittanceSerializer,
    BienEtatLieuxSerializer,
)


class BelgiumBailSerializer(serializers.Serializer):
    """
    Serializer pour un bail en Belgique.
    Définit les champs obligatoires et conditionnels selon la réglementation belge.
    """

    # Champs toujours obligatoires
    bien = BienBailSerializer(required=True)
    bailleur = BailleurInfoSerializer(required=True)
    locataires = serializers.ListField(
        child=LocataireInfoSerializer(), min_length=1, required=True
    )
    modalites_financieres = ModalitesFinancieresSerializer(required=True)
    dates = DatesLocationSerializer(required=True)

    # Champs spécifiques à la Belgique
    region = serializers.ChoiceField(
        choices=["bruxelles", "wallonie", "flandre"],
        required=True,
        help_text="Région où se situe le bien",
    )

    # Garantie locative (obligatoire en Belgique)
    garantie_locative = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        help_text="Montant de la garantie locative (max 2 mois de loyer)",
    )

    # Certificat PEB (conditionnel selon la région)
    certificat_peb = serializers.CharField(
        required=False, help_text="Certificat de performance énergétique du bâtiment"
    )

    # Enregistrement du bail (obligatoire)
    enregistrement_bail = serializers.BooleanField(
        help_text="Le bail doit être enregistré dans les 2 mois",
        required=True,
    )

    # État des lieux d'entrée (obligatoire)
    etat_lieux_entree_effectue = serializers.BooleanField(
        required=True, help_text="Un état des lieux d'entrée a-t-il été effectué ?"
    )

    # Options
    solidaires = serializers.BooleanField(
        default=False, help_text="Les locataires sont-ils solidaires ?"
    )

    def validate(self, data):
        """
        Validation conditionnelle pour la Belgique.
        """
        # Validation selon la région
        region = data.get("region")

        # À Bruxelles, le certificat PEB est obligatoire
        if region == "bruxelles":
            if not data.get("certificat_peb"):
                raise serializers.ValidationError(
                    {
                        "certificat_peb": "Le certificat PEB est obligatoire à Bruxelles"
                    }
                )

        # En Wallonie, règles spécifiques
        if region == "wallonie":
            # Validation spécifique Wallonie si nécessaire
            pass

        # En Flandre, règles spécifiques
        if region == "flandre":
            # Le bail doit être en néerlandais ou bilingue
            pass

        # Validation de la garantie locative (max 2 mois en Belgique)
        garantie = data.get("garantie_locative")
        loyer = data.get("modalites_financieres", {}).get("loyer_mensuel")

        if garantie and loyer:
            if garantie > (loyer * 2):
                raise serializers.ValidationError(
                    {
                        "garantie_locative": "La garantie locative ne peut excéder 2 mois de loyer en Belgique"
                    }
                )

        # Validation des dates (durée standard 3-6-9 ans en Belgique)
        dates = data.get("dates", {})
        if dates.get("date_fin") and dates.get("date_debut"):
            if dates["date_fin"] <= dates["date_debut"]:
                raise serializers.ValidationError(
                    {"dates": "La date de fin doit être après la date de début"}
                )

        return data

    def get_conditional_fields(self):
        """
        Retourne la liste des champs conditionnels avec leurs conditions.
        """
        return [
            {
                "field": "certificat_peb",
                "condition": 'region === "bruxelles"',
                "depends_on": ["region"],
            },
        ]


class BelgiumQuittanceSerializer(serializers.Serializer):
    """
    Serializer pour une quittance en Belgique.
    """

    # Champs obligatoires pour une quittance
    bien = BienQuittanceSerializer(required=True)
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

    # En Belgique, mention obligatoire de l'indexation
    indexation_appliquee = serializers.BooleanField(
        default=False, help_text="Une indexation a-t-elle été appliquée ?"
    )


class BelgiumEtatLieuxSerializer(serializers.Serializer):
    """
    Serializer pour un état des lieux en Belgique.
    """

    # Champs obligatoires
    bien = BienEtatLieuxSerializer(required=True)
    bailleur = BailleurInfoSerializer(required=True)
    locataires = serializers.ListField(
        child=PersonneBaseSerializer(), min_length=1, required=True
    )

    # Dates et modalités
    dates = DatesLocationSerializer(required=True)  # Obligatoire en Belgique
    modalites_financieres = ModalitesFinancieresSerializer(required=False)

    # Champs spécifiques état des lieux
    type_etat_lieux = serializers.ChoiceField(
        choices=["entree", "sortie"], required=True
    )
    date_etat_lieux = serializers.DateField(required=True)

    # Expert agréé (recommandé en Belgique)
    expert_agree = serializers.CharField(
        required=False, help_text="Nom de l'expert agréé si applicable"
    )

    # Description détaillée
    description_pieces = serializers.JSONField(
        required=True, help_text="Description détaillée de l'état de chaque pièce"
    )
    releve_compteurs = serializers.JSONField(
        required=True,  # Obligatoire en Belgique
        help_text="Relevés des compteurs (eau, gaz, électricité)",
    )
    nombre_cles = serializers.IntegerField(
        required=True, help_text="Nombre de clés remises"
    )

    # Photos obligatoires en Belgique
    photos_pieces = serializers.ListField(
        child=serializers.URLField(),
        required=False,
        help_text="URLs des photos de chaque pièce",
    )