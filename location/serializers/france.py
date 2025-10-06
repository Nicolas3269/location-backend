"""
Serializers spécifiques pour la France.
Définit les règles métier et validations pour les formulaires français.
"""

from rest_framework import serializers

from location.models import Bien, Location, RentTerms

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

# ========================================
# STEPS CONFIGURATION
# Organisation par domaine fonctionnel
# ========================================

# --- BIEN - Localisation ---
ADRESSE_STEPS = [
    {
        "id": "bien.localisation.adresse",
        "required_fields": ["bien.localisation.adresse"],
        "fields": {
            "bien.localisation.adresse": Bien.adresse,
            "bien.localisation.latitude": Bien.latitude,
            "bien.localisation.longitude": Bien.longitude,
            "bien.localisation.area_id": RentTerms.rent_price_id,
        },
    },
]

# --- BIEN - Caractéristiques de base ---
TYPE_BIEN_STEPS = [
    {
        "id": "bien.caracteristiques.type_bien",
        "required_fields": ["bien.caracteristiques.type_bien"],
        "fields": {
            "bien.caracteristiques.type_bien": Bien.type_bien,
            "bien.caracteristiques.etage": Bien.etage,
            "bien.caracteristiques.porte": Bien.porte,
            "bien.caracteristiques.dernier_etage": Bien.dernier_etage,
        },
    },
]
SUPERFICIE_STEPS = [
    {
        "id": "bien.caracteristiques.superficie",
        "required_fields": ["bien.caracteristiques.superficie"],
        "fields": {
            "bien.caracteristiques.superficie": Bien.superficie,
        },
    },
]
PIECES_INFO_STEPS = [
    {
        "id": "bien.caracteristiques.pieces_info",
        "required_fields": [],  # Validation par business rule uniquement
        "fields": {
            "bien.caracteristiques.pieces_info": Bien.pieces_info,
        },
        "business_rules": ["atLeastOneRoom"],  # Au moins 1 chambre ou séjour
    },
]
MEUBLE_STEPS = [
    {
        "id": "bien.caracteristiques.meuble",
        "required_fields": ["bien.caracteristiques.meuble"],
        "fields": {
            "bien.caracteristiques.meuble": Bien.meuble,
        },
    },
]

# --- BIEN - Régime juridique ---
REGIME_JURIDIQUE_STEPS = [
    {
        "id": "bien.regime.regime_juridique",
        "required_fields": ["bien.regime.regime_juridique"],
        "fields": {
            "bien.regime.regime_juridique": Bien.regime_juridique,
        },
    },
]
PERIODE_CONSTRUCTION_STEPS = [
    {
        "id": "bien.regime.periode_construction",
        "required_fields": ["bien.regime.periode_construction"],
        "fields": {
            "bien.regime.periode_construction": Bien.periode_construction,
        },
    },
]

# --- BIEN - Équipements (partagés) ---
EQUIPEMENTS_PRIVATIVES_STEPS = [
    {
        "id": "bien.equipements.annexes_privatives",
        "default": [],
        "required_fields": [],  # Optionnel
        "fields": {
            "bien.equipements.annexes_privatives": Bien.annexes_privatives,
        },
    },
]
EQUIPEMENTS_COLLECTIVES_STEPS = [
    {
        "id": "bien.equipements.annexes_collectives",
        "default": [],
        "required_fields": [],  # Optionnel
        "fields": {
            "bien.equipements.annexes_collectives": Bien.annexes_collectives,
        },
    },
]
EQUIPEMENTS_INFORMATION_STEPS = [
    {
        "id": "bien.equipements.information",
        "default": [],
        "required_fields": [],  # Optionnel
        "fields": {
            "bien.equipements.information": Bien.information,
        },
    },
]

# --- BIEN - Énergie (partagés) ---
ENERGIE_CHAUFFAGE_STEPS = [
    {
        "id": "bien.energie.chauffage",
        "required_fields": [],  # Validation par business rule
        "fields": {
            "bien.energie.chauffage.type": Bien.chauffage_type,
            "bien.energie.chauffage.energie": Bien.chauffage_energie,
        },
        "business_rules": ["chauffageValidation"],  # Validation complète du chauffage
    },
]
ENERGIE_EAU_CHAUDE_STEPS = [
    {
        "id": "bien.energie.eau_chaude",
        "required_fields": [],  # Validation par business rule
        "fields": {
            "bien.energie.eau_chaude.type": Bien.eau_chaude_type,
            "bien.energie.eau_chaude.energie": Bien.eau_chaude_energie,
        },
        "business_rules": [
            "eauChaudeValidation"
        ],  # Validation complète de l'eau chaude
    },
]

# --- BIEN - Performance énergétique (DPE) ---
DPE_STEPS = [
    {
        "id": "bien.performance_energetique.classe_dpe",
        "required_fields": ["bien.performance_energetique.classe_dpe"],
        "fields": {
            "bien.performance_energetique.classe_dpe": Bien.classe_dpe,
        },
    },
    {
        "id": "bien.performance_energetique.depenses_energetiques",
        "condition": "dpe_not_na",
        "required_fields": ["bien.performance_energetique.depenses_energetiques"],
        "fields": {
            "bien.performance_energetique.depenses_energetiques": Bien.depenses_energetiques,
        },
    },
    {
        "id": "bien.regime.identifiant_fiscal",
        "required_fields": [
            "bien.regime.fill_identifiant_fiscal"
        ],  # Choix de remplir ou non
        "fields": {
            "bien.regime.identifiant_fiscal": Bien.identifiant_fiscal,
        },
        "business_rules": [
            "identifiantFiscalValidation"
        ],  # Validation du choix de remplissage
    },
]

# --- PERSONNES (Bailleur et Locataires) ---
PERSON_STEPS = [
    # Bailleur
    {
        "id": "bailleur.bailleur_type",
        "required_fields": ["bailleur.bailleur_type"],
        "fields": {},  # Pas de mapping direct, c'est un choix UI
    },
    {
        "id": "bailleur.personne",
        "condition": "bailleur_is_physique",
        "required_fields": [],  # Validation par business rule
        "fields": {},  # Géré par le serializer BailleurInfoSerializer
        "business_rules": [
            "bailleurPersonneValidation"
        ],  # Validation personne physique
    },
    {
        "id": "bailleur.signataire",
        "condition": "bailleur_is_morale",
        "required_fields": [],  # Géré par serializer
        "fields": {},  # Géré par le serializer
    },
    {
        "id": "bailleur.societe",
        "condition": "bailleur_is_morale",
        "required_fields": [],  # Validation par business rule
        "fields": {},  # Géré par le serializer
        "business_rules": ["societeValidation"],  # Validation complète société
    },
    {
        "id": "bailleur.co_bailleurs",
        "required_fields": [],  # Optionnel
        "fields": {},  # Relation many-to-many
    },
    # Locataires
    {
        "id": "locataires",
        "required_fields": [],  # Validation par business rule
        "fields": {},  # Relation many-to-many
        "business_rules": ["locatairesRequired"],
    },
]

PERSON_STEPS_SOLIDAIRES = [
    {
        "id": "solidaires",
        "condition": "has_multiple_tenants",
        "required_fields": ["solidaires"],
        "fields": {
            "solidaires": Location.solidaires,
        },
    },
]

# --- MODALITÉS FINANCIÈRES ---
MODALITES_FINANCIERES_STEPS = [
    {
        "id": "modalites_financieres.loyer_hors_charges",
        "required_fields": ["modalites_financieres.loyer_hors_charges"],
        "fields": {
            "modalites_financieres.loyer_hors_charges": RentTerms.montant_loyer,
        },
    },
    {
        "id": "modalites_financieres.charges_mensuelles",
        "required_fields": [
            "modalites_financieres.type_charges",
            "modalites_financieres.charges",
        ],
        "fields": {
            "modalites_financieres.charges": RentTerms.montant_charges,
            "modalites_financieres.type_charges": RentTerms.type_charges,
        },
    },
]

# --- ZONE TENDUE ---
ZONE_TENDUE_STEPS = [
    {
        "id": "modalites_zone_tendue.premiere_mise_en_location",
        "condition": "zone_tendue",
        "required_fields": ["modalites_zone_tendue.premiere_mise_en_location"],
        "fields": {
            "modalites_zone_tendue.premiere_mise_en_location": RentTerms.premiere_mise_en_location,
        },
    },
    {
        "id": "modalites_zone_tendue.locataire_derniers_18_mois",
        "condition": "zone_tendue_not_first_rental",
        "required_fields": ["modalites_zone_tendue.locataire_derniers_18_mois"],
        "fields": {
            "modalites_zone_tendue.locataire_derniers_18_mois": RentTerms.locataire_derniers_18_mois,
        },
    },
    {
        "id": "modalites_zone_tendue.dernier_montant_loyer",
        "condition": "zone_tendue_has_previous_tenant",
        "required_fields": ["modalites_zone_tendue.dernier_montant_loyer"],
        "fields": {
            "modalites_zone_tendue.dernier_montant_loyer": RentTerms.dernier_montant_loyer,
        },
    },
]

# --- DATES ---
BAIL_DATE_STEPS = [
    {
        "id": "dates.date_debut",
        "required_fields": ["dates.date_debut"],  # date_fin est optionnelle
        "fields": {
            "dates.date_debut": Location.date_debut,
            "dates.date_fin": Location.date_fin,
        },
    },
]

# ========================================
# STEPS SPÉCIFIQUES QUITTANCE
# ========================================
QUITTANCE_LOCATAIRE_SELECTION_STEPS = [
    {
        "id": "quittance.locataire_selection",
        "condition": "has_multiple_tenants",
        "always_unlocked": True,
        "required_fields": ["locataire_ids"],
        "fields": {},  # Liste d'IDs de locataires
        "question": "Pour quel(s) locataire(s) souhaitez-vous générer cette quittance ?",
    },
]

QUITTANCE_MONTANT_STEPS = [
    {
        "id": "quittance.montant",
        "always_unlocked": True,
        "required_fields": [
            "loyer_hors_charges",
            "charges",
        ],
        "fields": {},  # Montants pré-remplis depuis modalites_financieres
        "question": "Quel est le montant de cette quittance ?",
    },
]

PERIODE_QUITTANCE_STEPS = [
    {
        "id": "periode_quittance",
        "always_unlocked": True,  # Toujours éditable pour créer de nouvelles quittances
        "required_fields": [
            "periode_quittance.mois",
            "periode_quittance.annee",
            "periode_quittance.date_paiement",
        ],
        "fields": {},  # Géré directement par le serializer Quittance
    },
]

# ========================================
# STEPS SPÉCIFIQUES ÉTAT DES LIEUX
# ========================================

# --- Définition de l'état des lieux ---
ETAT_LIEUX_DEFINITION_STEPS = [
    {
        "id": "type_etat_lieux",
        "always_unlocked": True,
        "required_fields": ["type_etat_lieux"],
        "fields": {},  # Champ direct dans EtatLieux
    },
    {
        "id": "date_etat_lieux",
        "always_unlocked": True,
        "required_fields": ["date_etat_lieux"],
        "fields": {},  # Champ direct dans EtatLieux
    },
]

# --- Détails techniques état des lieux ---
DETAIL_ETAT_LIEUX_EQUIPEMENT_STEPS = [
    {
        "id": "equipements_chauffage",
        "always_unlocked": True,
        "required_fields": [],  # Optionnel
        "fields": {},  # Stocké en JSON dans EtatLieux
    },
    {
        "id": "compteurs",
        "always_unlocked": True,
        "required_fields": [],  # Validation par business rule
        "fields": {},  # Stocké en JSON dans EtatLieux
        "business_rules": ["compteursConditionnels"],
    },
]

# --- Équipements des annexes privatives état des lieux ---
ANNEXES_PRIVATIVES_EQUIPEMENTS_STEPS = [
    {
        "id": "bien.equipements.annexes_privatives_equipements",
        "condition": "at_least_one_annexes_privatives_selected",
        "required_fields": [],  # Optionnel
        "fields": {},  # Stocké en JSON dans EtatLieux
    },
]


# --- Clés ---
ETAT_LIEUX_CLES_STEPS = [
    {
        "id": "nombre_cles",
        "required_fields": [],  # Optionnel
        "always_unlocked": True,
        "fields": {},  # Stocké en JSON dans EtatLieux
    },
]

# --- Commentaires généraux ---
COMMENTAIRES_GENERAUX_STEPS = [
    {
        "id": "commentaires_generaux",
        "required_fields": [],  # Optionnel
        "always_unlocked": True,
        "fields": {},  # Stocké en TextField dans EtatLieux
    },
]

# --- Description des pièces ---
DETAIL_ETAT_LIEUX_STEPS = [
    {
        "id": "description_pieces",
        "required_fields": [],  # Optionnel
        "always_unlocked": True,
        "fields": {},  # Stocké en JSON (rooms) dans EtatLieux
    },
]

# --- DOCUMENTS LOCATAIRES (Pré-signature) ---
TENANT_DOCUMENT_MRH_STEPS = [
    {
        "id": "tenant_documents.mrh",
        "required_fields": ["tenant_documents.attestation_mrh"],
        "always_unlocked": True,
    },
]

TENANT_DOCUMENT_CAUTION_STEPS = [
    {
        "id": "tenant_documents.caution",
        "required_fields": ["tenant_documents.caution_solidaire"],
        "always_unlocked": True,
    },
]

TENANT_DOCUMENT_SIGNATURE_STEPS = [
    {
        "id": "tenant_documents.signature",
        "required_fields": [],
        "always_unlocked": True,
    },
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

    @classmethod
    def get_all_field_mappings(cls):
        """
        Collecte tous les mappings depuis toutes les STEPS.

        Returns: Dict[str, Field] mapping field_path -> Django Field object
        """
        mappings = {}

        # Utiliser get_step_config() du serializer
        all_steps = cls.get_step_config()

        for step in all_steps:
            fields = step.get("fields", {})
            for field_path, field_obj in fields.items():
                mappings[field_path] = field_obj

        return mappings

    @classmethod
    def get_field_to_step_mapping(cls, model_class):
        """
        Retourne le mapping inverse : field_name -> step_id pour un modèle.
        Args:
            model_class: Classe du modèle (Bien, RentTerms, Location)
        Returns: Dict[str, str] mapping field_name -> field_path
        """
        mappings = cls.get_all_field_mappings()
        result = {}

        for field_path, field_obj in mappings.items():
            if field_obj and hasattr(field_obj, "field"):
                if field_obj.field.model == model_class:
                    field_name = field_obj.field.name
                    result[field_name] = field_path

        return result

    @classmethod
    def extract_model_data(cls, model_class, form_data):
        """
        Extrait automatiquement les données pour un modèle depuis form_data.
        Args:
            model_class: Classe du modèle
            form_data: Données du formulaire
        Returns: Dict avec les champs du modèle
        """
        mappings = cls.get_all_field_mappings()
        result = {}

        for field_path, field_obj in mappings.items():
            if field_obj and hasattr(field_obj, "field"):
                if field_obj.field.model == model_class:
                    # Utiliser field_path pour extraire la valeur
                    value = cls._get_nested_value(form_data, field_path)
                    if value is not None:
                        field_name = field_obj.field.name
                        result[field_name] = value

        return result

    @classmethod
    def _get_nested_value(cls, data, path):
        """
        Extrait une valeur imbriquée depuis un dictionnaire.
        Ex: _get_nested_value({"a": {"b": "c"}}, "a.b") -> "c"
        """
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return None
            else:
                return None
        return current

    @classmethod
    def get_step_config_by_id(cls, step_id):
        """
        Trouve la configuration d'une step par son ID.

        Args:
            step_id: L'ID de la step à rechercher

        Returns: La configuration de la step ou None si non trouvée
        """
        # Utiliser get_step_config() du serializer
        all_steps = cls.get_step_config()

        for step in all_steps:
            if step.get("id") == step_id:
                return step

        return None


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

        # Équipements complets pour bail
        BAIL_STEPS.extend(EQUIPEMENTS_PRIVATIVES_STEPS)
        BAIL_STEPS.extend(EQUIPEMENTS_COLLECTIVES_STEPS)
        BAIL_STEPS.extend(EQUIPEMENTS_INFORMATION_STEPS)

        # Énergie
        BAIL_STEPS.extend(ENERGIE_CHAUFFAGE_STEPS)
        BAIL_STEPS.extend(ENERGIE_EAU_CHAUDE_STEPS)

        BAIL_STEPS.extend(DPE_STEPS)
        BAIL_STEPS.extend(PERSON_STEPS)
        BAIL_STEPS.extend(PERSON_STEPS_SOLIDAIRES)
        BAIL_STEPS.extend(ZONE_TENDUE_STEPS)
        BAIL_STEPS.extend(BAIL_DATE_STEPS)
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

    # Options de location
    solidaires = serializers.BooleanField(
        default=False, help_text="Les locataires sont-ils solidaires ?"
    )

    # Spécifique quittance - sélection des locataires pour cette quittance
    locataire_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True,
        help_text="IDs des locataires pour cette quittance (si plusieurs locataires)",
    )

    # Montants (peuvent être ajustés par rapport au bail)
    loyer_hors_charges = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        help_text="Montant du loyer hors charges pour cette quittance",
    )
    charges = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        help_text="Montant des charges pour cette quittance",
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
        QUITTANCE_STEPS.extend(PERSON_STEPS)
        QUITTANCE_STEPS.extend(QUITTANCE_LOCATAIRE_SELECTION_STEPS)
        QUITTANCE_STEPS.extend(QUITTANCE_MONTANT_STEPS)
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

    compteurs = serializers.JSONField(
        required=False,
        default=None,
        allow_null=True,
        help_text="Relevés des compteurs (eau, gaz, électricité)",
    )
    nombre_cles = serializers.JSONField(
        required=False, default=dict, help_text="Nombre de clés remises"
    )
    equipements_chauffage = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Équipements de chauffage avec type, état et date d'entretien",
    )

    annexes_privatives_equipements = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Équipements des annexes privatives avec leur état",
    )

    # Rooms avec leur état (pour l'état des lieux)
    rooms = serializers.JSONField(
        required=False, default=list, help_text="Détails des pièces avec leur état"
    )

    # Commentaires généraux sur l'état des lieux
    commentaires_generaux = serializers.CharField(
        required=False,
        default=None,
        allow_null=True,
        allow_blank=True,
        help_text="Commentaires généraux sur l'état des lieux",
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
        ETAT_LIEUX_STEPS.extend(PERSON_STEPS)
        ETAT_LIEUX_STEPS.extend(ADRESSE_STEPS)
        ETAT_LIEUX_STEPS.extend(TYPE_BIEN_STEPS)

        # Équipements - seulement privatives pour état des lieux
        ETAT_LIEUX_STEPS.extend(EQUIPEMENTS_PRIVATIVES_STEPS)

        # Annexes privatives - leurs équipements
        ETAT_LIEUX_STEPS.extend(ANNEXES_PRIVATIVES_EQUIPEMENTS_STEPS)

        ETAT_LIEUX_STEPS.extend(ETAT_LIEUX_CLES_STEPS)

        # Énergie - réutilisation des steps atomiques
        ETAT_LIEUX_STEPS.extend(ENERGIE_CHAUFFAGE_STEPS)
        ETAT_LIEUX_STEPS.extend(ENERGIE_EAU_CHAUDE_STEPS)
        ETAT_LIEUX_STEPS.extend(DETAIL_ETAT_LIEUX_EQUIPEMENT_STEPS)

        ETAT_LIEUX_STEPS.extend(MEUBLE_STEPS)
        ETAT_LIEUX_STEPS.extend(PIECES_INFO_STEPS)
        ETAT_LIEUX_STEPS.extend(DETAIL_ETAT_LIEUX_STEPS)
        ETAT_LIEUX_STEPS.extend(COMMENTAIRES_GENERAUX_STEPS)
        return ETAT_LIEUX_STEPS

    def to_internal_value(self, data):
        """
        Convertir les objets vides en None pour les compteurs
        """
        validated_data = super().to_internal_value(data)

        # Si compteurs est un objet vide ou ne contient que des objets vides, le convertir en None
        if "compteurs" in validated_data:
            compteurs = validated_data["compteurs"]
            if compteurs is not None:
                # V\u00e9rifier si c'est un dictionnaire vide ou avec seulement des sous-dictionnaires vides
                if isinstance(compteurs, dict):
                    has_data = False
                    for key, value in compteurs.items():
                        if (
                            isinstance(value, dict) and value
                        ):  # Si le sous-dict a du contenu
                            # V\u00e9rifier si le sous-dict a des valeurs non vides
                            for sub_val in value.values():
                                if sub_val not in [None, "", {}]:
                                    has_data = True
                                    break
                        if has_data:
                            break

                    if not has_data:
                        validated_data["compteurs"] = None

        return validated_data

    @classmethod
    def get_equipment_config(cls):
        """
        Configuration des équipements pour les états des lieux.
        Retourne la configuration complète des équipements disponibles.
        """
        from location.equipment_config import get_all_equipements_config

        return get_all_equipements_config()


class FranceTenantDocumentsSerializer(BaseLocationSerializer):
    """
    Serializer pour les documents locataires (pré-signature).
    Utilisé pour collecter les documents MRH, caution, etc. avant la signature finale.
    """

    # Override source avec valeur par défaut
    source = serializers.CharField(default="tenant_documents")

    # Locataire ID (fourni via le token de signature)
    locataire_id = serializers.IntegerField(required=False, allow_null=True)

    @classmethod
    def get_steps(cls):
        """
        Steps pour la collecte des documents locataires.
        """
        TENANT_DOCS_STEPS = []
        TENANT_DOCS_STEPS.extend(TENANT_DOCUMENT_MRH_STEPS)
        TENANT_DOCS_STEPS.extend(TENANT_DOCUMENT_CAUTION_STEPS)
        TENANT_DOCS_STEPS.extend(TENANT_DOCUMENT_SIGNATURE_STEPS)
        return TENANT_DOCS_STEPS


# Les helper functions sont maintenant des méthodes de BaseLocationSerializer
