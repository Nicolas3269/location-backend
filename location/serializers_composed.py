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
    """Caractéristiques physiques d'un bien"""

    superficie = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True
    )
    type_bien = serializers.ChoiceField(
        choices=["appartement", "maison"], default="appartement"
    )
    etage = serializers.CharField(required=False, allow_blank=True, default="")
    porte = serializers.CharField(required=False, allow_blank=True, default="")
    dernier_etage = serializers.BooleanField(default=False)
    meuble = serializers.BooleanField(required=True)
    pieces_info = serializers.JSONField(
        required=True,
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
        child=serializers.CharField(), required=False, default=list
    )
    annexes_collectives = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    information = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )


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
    identifiant_fiscal = serializers.CharField(required=False, allow_blank=True)
    periode_construction = serializers.CharField(required=True)


class ZoneReglementaireSerializer(serializers.Serializer):
    """Zone réglementaire et autorisations"""

    zone_tendue = serializers.BooleanField(default=False)
    permis_de_louer = serializers.BooleanField(default=False)


# ============================================
# SERIALIZERS POUR LES PERSONNES
# ============================================


class PersonneBaseSerializer(serializers.Serializer):
    """Serializer de base pour une personne"""

    lastName = serializers.CharField(max_length=100)
    firstName = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    date_naissance = serializers.DateField(required=False, allow_null=True)
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)


class PersonneCompleteSerializer(PersonneBaseSerializer):
    """Personne avec adresse et coordonnées bancaires"""

    adresse = serializers.CharField(required=True)
    iban = serializers.CharField(max_length=34, required=False, allow_blank=True)


class SocieteBaseSerializer(serializers.Serializer):
    """Serializer pour une société"""

    raison_sociale = serializers.CharField(max_length=200)
    siret = serializers.CharField(max_length=14, min_length=14)
    forme_juridique = serializers.CharField(max_length=100)
    adresse = serializers.CharField()
    telephone = serializers.CharField(max_length=20, required=False)
    email = serializers.EmailField(required=False)


class SignataireSerializer(PersonneBaseSerializer):
    """Serializer pour le signataire d'une société (sans adresse obligatoire)"""

    adresse = serializers.CharField(required=False, allow_blank=True)
    iban = serializers.CharField(max_length=34, required=False, allow_blank=True)


class BailleurInfoSerializer(serializers.Serializer):
    """Informations du bailleur (physique ou morale)"""

    bailleur_type = serializers.ChoiceField(
        choices=["physique", "morale"], default="physique"
    )
    # Si personne physique - utilise PersonneCompleteSerializer avec adresse obligatoire
    personne = PersonneCompleteSerializer(required=False)
    # Si personne morale
    societe = SocieteBaseSerializer(required=False)
    # Signataire pour société - utilise SignataireSerializer sans adresse obligatoire
    signataire = PersonneBaseSerializer(required=False)
    # Autres co-bailleurs
    co_bailleurs = serializers.ListField(
        child=PersonneBaseSerializer(), required=False, default=list
    )

    def validate(self, data):
        """Validation : soit personne, soit société requis"""
        bailleur_type = data.get("bailleur_type", "physique")

        if bailleur_type == "physique":
            if not data.get("personne"):
                raise serializers.ValidationError(
                    "Les informations de la personne sont requises pour un bailleur physique"
                )
            # Pour personne physique, on nettoie les champs société
            data.pop("societe", None)
            data.pop("signataire", None)

        elif bailleur_type == "morale":
            if not data.get("societe"):
                raise serializers.ValidationError(
                    "Les informations de la société sont requises pour un bailleur moral"
                )
            # Pour personne morale, on utilise personne comme signataire si présent
            # mais sans exiger l'adresse (elle est dans société)
            if data.get("personne"):
                # Transformer personne en signataire sans l'adresse obligatoire
                signataire_data = data.pop("personne")
                # Garder seulement les infos de base du signataire
                data["signataire"] = {
                    "lastName": signataire_data.get("lastName"),
                    "firstName": signataire_data.get("firstName"),
                    "email": signataire_data.get("email"),
                }
        return data


class LocataireInfoSerializer(PersonneBaseSerializer):
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

    premiere_mise_en_location = serializers.BooleanField(default=False)
    locataire_derniers_18_mois = serializers.BooleanField(default=False)
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

        return {
            "area_id": localisation_data.get("area_id"),
            "type_bien": caracteristiques.get("type_bien", "appartement"),
            "pieces_info": caracteristiques.get("pieces_info", {}),
            "periode_construction": regime.get("periode_construction", ""),
        }


class BienQuittanceSerializer(serializers.Serializer):
    """Serializer pour un bien dans une quittance (seulement adresse)"""

    localisation = AdresseSerializer()
    caracteristiques = serializers.DictField(required=False)


class CaracteristiquesEtatLieuxSerializer(serializers.Serializer):
    """Caractéristiques d'un bien pour état des lieux"""

    superficie = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    type_bien = serializers.ChoiceField(
        choices=[("appartement", "Appartement"), ("maison", "Maison")], required=False
    )
    etage = serializers.CharField(required=False, allow_blank=True, default="")
    porte = serializers.CharField(required=False, allow_blank=True, default="")
    dernier_etage = serializers.BooleanField(
        default=False, help_text="Le bien est-il au dernier étage ?"
    )
    meuble = serializers.BooleanField(default=False)
    pieces_info = serializers.JSONField(required=False)


class BienEtatLieuxSerializer(serializers.Serializer):
    """Serializer pour un bien dans un état des lieux"""

    localisation = AdresseSerializer()
    caracteristiques = CaracteristiquesEtatLieuxSerializer()
    # equipements = EquipementsSerializer()
    energie = EnergieSerializer()
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


class CreateLocationComposedSerializer(serializers.Serializer):
    """
    Serializer pour créer une location (version composée).
    Utilise la composition pour une meilleure organisation.
    """

    # Métadonnées
    source = serializers.ChoiceField(
        choices=["bail", "quittance", "etat_lieux", "manual"], default="manual"
    )

    # Composition des domaines métier
    bien = BienBailSerializer()
    bailleur = BailleurInfoSerializer()
    locataires = serializers.ListField(child=LocataireInfoSerializer(), min_length=1)
    modalites_financieres = ModalitesFinancieresSerializer()
    modalites_zone_tendue = ModalitesZoneTendueSerializer(required=False)
    dates = DatesLocationSerializer()

    # Options de location
    solidaires = serializers.BooleanField(
        default=False, help_text="Les locataires sont-ils solidaires ?"
    )

    # IDs pour update
    location_id = serializers.UUIDField(required=False, allow_null=True)
    bien_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, data):
        """Validations métier inter-domaines"""
        # Si zone tendue, modalités zone tendue requises
        if data.get("bien", {}).get("zone_reglementaire", {}).get("zone_tendue"):
            if not data.get("modalites_zone_tendue"):
                raise serializers.ValidationError(
                    "Les modalités zone tendue sont requises en zone tendue"
                )

        # Validation cohérence dates
        dates = data.get("dates", {})
        if dates.get("date_fin") and dates.get("date_debut"):
            if dates["date_fin"] <= dates["date_debut"]:
                raise serializers.ValidationError(
                    "La date de fin doit être après la date de début"
                )

        return data

    class Meta:
        # Métadonnées pour la génération
        is_composite = True
        components = [
            "bien",
            "bailleur",
            "locataires",
            "modalites_financieres",
            "modalites_zone_tendue",
            "dates",
        ]


# ============================================
# SERIALIZERS POUR DIFFÉRENTS CONTEXTES
# ============================================


class CreateBailSerializer(CreateLocationComposedSerializer):
    """Serializer spécifique pour créer un bail"""

    source = serializers.HiddenField(default="bail")

    # Modalités zone tendue - requis pour un bail complet
    # Note: Quand un bail est créé depuis un état des lieux,
    # le frontend doit s'assurer de collecter ces informations manquantes
    modalites_zone_tendue = ModalitesZoneTendueSerializer(required=True)


class CreateQuittanceSerializer(serializers.Serializer):
    """Serializer simplifié pour une quittance"""

    source = serializers.HiddenField(default="quittance")

    # Seulement les infos nécessaires - on utilise BienQuittanceSerializer pour l'adresse
    bien = BienQuittanceSerializer()  # Juste l'adresse
    bailleur = BailleurInfoSerializer()
    locataires = serializers.ListField(
        child=PersonneBaseSerializer()  # Version simplifiée
    )
    modalites_financieres = ModalitesFinancieresSerializer()

    # Spécifique quittance
    periode_quittance = serializers.DictField(
        child=serializers.CharField(), help_text="Mois et année de la quittance"
    )
    date_paiement = serializers.DateField()


class CreateEtatLieuxSerializer(serializers.Serializer):
    """Serializer pour un état des lieux"""

    source = serializers.HiddenField(default="etat_lieux")

    # Infos de base - on utilise BienEtatLieuxSerializer
    bien = BienEtatLieuxSerializer()
    bailleur = BailleurInfoSerializer()
    locataires = serializers.ListField(child=PersonneBaseSerializer())

    # Dates de location (optionnelles pour état des lieux)
    dates = DatesLocationSerializer(required=False)
    modalites_financieres = ModalitesFinancieresSerializer(required=False)

    # Options
    solidaires = serializers.BooleanField(default=False, required=False)

    # Spécifique état des lieux - rendre optionnels car remplis progressivement
    type_etat_lieux = serializers.ChoiceField(
        choices=["entree", "sortie"], required=False
    )
    date_etat_lieux = serializers.DateField(required=False)

    # État détaillé des pièces (correspond aux "rooms" dans le frontend)
    # Note: Ce champ contient l'état de chaque pièce (murs, sols, etc.),
    # différent de pieces_info qui contient le nombre de pièces
    pieces = serializers.ListField(
        child=serializers.DictField(),
        help_text="État détaillé de chaque pièce pour l'état des lieux (rooms dans le frontend)",
        required=False,
        default=list,
    )

    # IDs pour update
    location_id = serializers.UUIDField(required=False, allow_null=True)
    bien_id = serializers.UUIDField(required=False, allow_null=True)
