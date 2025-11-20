"""
Modèles pour la gestion des locations
Location est l'entité pivot centrale
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import models
from simple_history.models import HistoricalRecords

from rent_control.choices import (
    ChargeType,
    ConstructionPeriod,
    PropertyType,
    RegimeJuridique,
    SystemType,
)
from rent_control.views import get_rent_control_info

User = get_user_model()


class BaseModel(models.Model):
    """
    Modèle de base pour tous les modèles Hestia.

    Fournit :
    - UUID comme clé primaire (compatibilité frontend, sécurité, distribution)
    - Timestamps automatiques (created_at, updated_at) pour l'audit
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DPEClass(models.TextChoices):
    A = "A", "A (≤ 70 kWh/m²/an)"
    B = "B", "B (71 à 110 kWh/m²/an)"
    C = "C", "C (111 à 180 kWh/m²/an)"
    D = "D", "D (181 à 250 kWh/m²/an)"
    E = "E", "E (251 à 330 kWh/m²/an)"
    F = "F", "F (331 à 420 kWh/m²/an)"
    G = "G", "G (> 420 kWh/m²/an)"
    NA = "NA", "Non soumis à DPE"


class BailleurType(models.TextChoices):
    """Types de bailleur"""
    PHYSIQUE = "physique", "Personne physique"
    MORALE = "morale", "Personne morale"


# ==============================
# NOUVEAUX MODÈLES POUR BAILLEUR
# ==============================


class Personne(BaseModel):
    """Personne physique (propriétaire, signataire, etc.)"""

    # Lien vers le compte utilisateur (créé automatiquement via email)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personnes",
        help_text="Compte utilisateur associé (créé automatiquement via email)",
    )

    lastName = models.CharField(max_length=100, db_column="nom")
    firstName = models.CharField(max_length=100, db_column="prenom")
    date_naissance = models.DateField(
        null=True, blank=True, default=None
    )  # Optionnel pour certains cas
    email = models.EmailField()
    adresse = models.TextField(blank=True, null=True, default=None)

    # Informations bancaires (pour les propriétaires)
    iban = models.CharField(max_length=34, blank=True, null=True, default=None)

    # Historique automatique
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Personne"
        verbose_name_plural = "Personnes"

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.firstName} {self.lastName}"

    def save(self, *args, **kwargs):
        """
        Crée ou associe automatiquement un User lors de la sauvegarde.
        Si un User existe avec cet email, il est réutilisé.
        Sinon, un nouveau User est créé.
        """
        # Créer/récupérer le User basé sur l'email
        if self.email and not self.user:
            user, created = User.objects.get_or_create(
                email=self.email,
                defaults={
                    "username": self.email,  # Email comme username
                    "first_name": self.firstName,
                    "last_name": self.lastName,
                },
            )
            self.user = user

            # Ne PAS update le nom si le user existe déjà
            # (évite d'écraser avec une faute de frappe)

        super().save(*args, **kwargs)


class Societe(BaseModel):
    """Société (propriétaire, mandataire, etc.)"""

    siret = models.CharField(max_length=14)
    raison_sociale = models.CharField(max_length=200)
    forme_juridique = models.CharField(max_length=100)
    adresse = models.TextField()
    email = models.EmailField()

    # Informations bancaires (pour les sociétés propriétaires)
    iban = models.CharField(max_length=34, blank=True, null=True, default=None)

    # Historique automatique
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Société"
        verbose_name_plural = "Sociétés"

    def __str__(self):
        return self.raison_sociale

    @property
    def full_name(self):
        return f"{self.forme_juridique} {self.raison_sociale}"


class Mandataire(BaseModel):
    """Mandataire/Agence qui gère pour le compte du propriétaire"""

    # Un mandataire est toujours une société dans la pratique
    societe = models.ForeignKey(
        Societe, on_delete=models.CASCADE, related_name="mandats"
    )

    # Signataire du mandataire (personne physique qui signe)
    signataire = models.ForeignKey(
        Personne,
        on_delete=models.CASCADE,
        related_name="mandats_signes",
        help_text="Personne physique qui signe pour le mandataire",
    )

    # Infos du mandat
    numero_carte_professionnelle = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = "Mandataire"
        verbose_name_plural = "Mandataires"

    def __str__(self):
        return f"{self.societe.raison_sociale} (Mandataire)"


class DocumentAvecMandataireMixin(models.Model):
    """
    Mixin pour les documents pouvant être signés par un mandataire.
    Fournit :
    - Champ mandataire_doit_signer
    - Properties pour accéder aux honoraires mandataire (honoraires_mandataire, honoraires_*)
    - Méthode abstraite get_reference_date_for_honoraires() (à implémenter)

    Note: Properties est_signe, date_signature, latest_signature_timestamp
    sont fournies par SignableDocumentMixin (base pour tous documents signables).

    Usage:
        class Bail(DocumentAvecMandataireMixin, SignableDocumentMixin, BaseModel):
            def get_reference_date_for_honoraires(self):
                return self.created_at.date()
    """

    # Champ de base : le mandataire doit-il signer ce document ?
    mandataire_doit_signer = models.BooleanField(
        default=False,
        verbose_name="Le mandataire signe ce document",
        help_text=(
            "Si True : le mandataire est signataire juridique du document "
            "et sera inclus dans les demandes de signature"
        ),
    )

    class Meta:
        abstract = True

    def get_reference_date_for_honoraires(self):
        """
        Retourne la date de référence pour récupérer les honoraires.
        À implémenter dans chaque document concret.

        Exemples:
        - Bail: self.created_at.date()
        - EtatLieux: self.date_etat_lieux
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_reference_date_for_honoraires()"
        )

    @property
    def honoraires_mandataire(self):
        """
        Récupère les honoraires mandataire en vigueur.
        Utilise date_signature si disponible (document signé),
        sinon fallback sur get_reference_date_for_honoraires().
        """
        # Utiliser date_signature si disponible (document signé)
        if self.date_signature:
            reference_date = self.date_signature.date()
        else:
            # Fallback sur date de référence spécifique au document
            reference_date = self.get_reference_date_for_honoraires()

        return HonoraireMandataire.get_at_date(self.location, reference_date)

    @property
    def a_honoraires_mandataire(self):
        """Y a-t-il des honoraires mandataire pour ce document ?"""
        return self.honoraires_mandataire is not None

    def _get_honoraire_field(self, field_name):
        """Helper pour récupérer un champ des honoraires mandataire."""
        if not self.a_honoraires_mandataire:
            return None
        return getattr(self.honoraires_mandataire, field_name, None)

    @property
    def honoraires_bail_par_m2(self):
        """Tarif honoraires bail au m²"""
        return self._get_honoraire_field("honoraires_bail_par_m2")

    @property
    def honoraires_bail_part_bailleur_pct(self):
        """Part bailleur des honoraires bail (%)"""
        return self._get_honoraire_field("honoraires_bail_part_bailleur_pct")

    @property
    def honoraires_edl_par_m2(self):
        """Tarif honoraires EDL au m²"""
        return self._get_honoraire_field("honoraires_edl_par_m2")

    @property
    def honoraires_edl_part_bailleur_pct(self):
        """Part bailleur des honoraires EDL (%)"""
        return self._get_honoraire_field("honoraires_edl_part_bailleur_pct")


class HonoraireMandataire(BaseModel):
    """
    Tarifs du mandataire pour une location donnée.
    Permet de gérer l'historique des changements de tarifs.

    IMMUTABLE : Ne jamais modifier un enregistrement existant.
    Pour changer les tarifs, créer un nouvel enregistrement avec une nouvelle date_debut
    et fermer l'ancien en mettant date_fin.
    """
    location = models.ForeignKey(
        'Location',  # Forward reference car Location défini après
        on_delete=models.CASCADE,
        related_name="honoraires_mandataire_history"
    )

    # Période de validité
    date_debut = models.DateField(
        db_index=True,
        verbose_name="Date de début de validité",
        help_text="Date à partir de laquelle ces tarifs s'appliquent"
    )
    date_fin = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Date de fin de validité",
        help_text="Laissez vide si tarifs actuellement en vigueur"
    )

    # Honoraires BAIL
    honoraires_bail_par_m2 = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        verbose_name="Honoraires bail par m²",
        help_text=(
            "Tarif des honoraires de bail au m² (€/m²). "
            "Plafonds légaux : 12€/m² (zone très tendue), "
            "10€/m² (zone tendue), 8€/m² (zone normale)."
        )
    )
    honoraires_bail_part_bailleur_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        verbose_name="Part bailleur bail (%)",
        help_text=(
            "Pourcentage des honoraires de bail à la charge du bailleur "
            "(0-100%). La part locataire ne peut excéder 50%."
        )
    )

    # Honoraires ÉTAT DES LIEUX
    mandataire_fait_edl = models.BooleanField(
        default=False,
        verbose_name="Le mandataire fait les EDL",
        help_text="Indique si le mandataire réalise les états des lieux"
    )
    honoraires_edl_par_m2 = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        verbose_name="Honoraires EDL par m²",
        help_text=(
            "Tarif des honoraires d'état des lieux au m² (€/m²). "
            "Maximum 3€/m²."
        )
    )
    honoraires_edl_part_bailleur_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        verbose_name="Part bailleur EDL (%)",
        help_text=(
            "Pourcentage des honoraires EDL à la charge du bailleur "
            "(0-100%). Répartition libre entre bailleur et locataire."
        )
    )

    # Métadonnées
    raison_changement = models.TextField(
        blank=True,
        verbose_name="Raison du changement",
        help_text="Pourquoi ces tarifs ont changé (optionnel)"
    )

    class Meta:
        db_table = "location_honoraires_mandataire"
        ordering = ["-date_debut"]
        verbose_name = "Honoraires mandataire"
        verbose_name_plural = "Honoraires mandataire"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(date_fin__isnull=True) |
                    models.Q(date_fin__gte=models.F('date_debut'))
                ),
                name="date_fin_after_date_debut"
            )
        ]
        indexes = [
            models.Index(
                fields=['location', 'date_debut', 'date_fin'],
                name='honoraires_location_dates_idx'
            ),
        ]

    def __str__(self):
        debut = self.date_debut
        return f"Honoraires mandataire pour {self.location} - À partir du {debut}"

    def delete(self, *args, **kwargs):
        """
        Empêche la suppression si cet enregistrement est utilisé par
        des documents. Utilise une approche plus performante que count().
        """
        from django.core.exceptions import ProtectedError

        # Vérifier si utilisé (existe() plus rapide que count())
        if hasattr(self, 'bails') and self.bails.exists():
            msg = (
                f"Cannot delete HonoraireMandataire {self.id}: "
                f"used by bail documents"
            )
            raise ProtectedError(msg, [self])

        if hasattr(self, 'etats_lieux') and self.etats_lieux.exists():
            msg = (
                f"Cannot delete HonoraireMandataire {self.id}: "
                f"used by etat des lieux documents"
            )
            raise ProtectedError(msg, [self])

        super().delete(*args, **kwargs)

    @classmethod
    def get_at_date(cls, location, target_date):
        """
        Récupère les honoraires en vigueur à une date donnée.

        Args:
            location: Instance de Location
            target_date: date ou datetime

        Returns:
            HonoraireMandataire ou None
        """
        from datetime import datetime

        # Convertir datetime en date si nécessaire
        if isinstance(target_date, datetime):
            target_date = target_date.date()

        return cls.objects.filter(
            location=location,
            date_debut__lte=target_date
        ).filter(
            models.Q(date_fin__isnull=True) | models.Q(date_fin__gte=target_date)
        ).order_by('-date_debut').first()

    @classmethod
    def get_current(cls, location):
        """Récupère les honoraires actuellement en vigueur"""
        from datetime import date
        return cls.get_at_date(location, date.today())


class Bailleur(BaseModel):
    """Bailleur (propriétaire ou société propriétaire)"""

    # Un bailleur peut être soit une personne physique, soit une société
    personne = models.ForeignKey(
        Personne,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        default=None,
        related_name="bailleurs",
        help_text="Personne physique bailleur",
    )
    societe = models.ForeignKey(
        Societe,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        default=None,
        related_name="bailleurs",
        help_text="Société bailleur",
    )

    signataire = models.ForeignKey(
        Personne,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        default=None,
        related_name="bailleurs_signes",
        help_text="Personne physique qui signe pour le bailleur",
    )

    class Meta:
        verbose_name = "Bailleur"
        verbose_name_plural = "Bailleurs"
        constraints = [
            # S'assurer qu'exactement un des deux champs est rempli
            models.CheckConstraint(
                check=(
                    models.Q(personne__isnull=False, societe__isnull=True)
                    | models.Q(personne__isnull=True, societe__isnull=False)
                ),
                name="bailleur_exactly_one_type",
            )
        ]

    @property
    def bailleur_type(self):
        """Retourne le type de bailleur (physique ou morale)"""
        if self.personne:
            return BailleurType.PHYSIQUE
        elif self.societe:
            return BailleurType.MORALE
        raise ValueError(f"Bailleur {self.id} invalide: doit avoir personne ou société")

    @property
    def full_name(self):
        """Retourne le nom complet du bailleur."""
        if self.personne:
            return self.personne.full_name
        elif self.societe:
            return self.societe.full_name
        raise ValueError(f"Bailleur {self.id} invalide: doit avoir personne ou société")

    @property
    def adresse(self):
        """Retourne l'adresse du bailleur."""
        if self.personne:
            return self.personne.adresse
        elif self.societe:
            return self.societe.adresse
        return "Adresse inconnue"

    @property
    def email(self):
        """Retourne l'email du bailleur (personne ou signataire)."""
        if self.personne:
            return self.personne.email
        elif self.societe and self.signataire:
            return self.signataire.email
        raise ValueError(
            f"Bailleur {self.id} invalide: doit avoir personne ou signataire"
        )

    def save(self, *args, **kwargs):
        """Automatiser la logique du signataire selon le type de bailleur."""
        # Si c'est une personne physique, elle doit être son propre signataire
        if self.personne and not self.signataire:
            self.signataire = self.personne

        super().save(*args, **kwargs)

    def clean(self):
        """Validation supplémentaire du modèle."""
        from django.core.exceptions import ValidationError

        # Vérifier qu'on a exactement un type de bailleur
        if not self.personne and not self.societe:
            raise ValidationError(
                "Un bailleur doit être soit une personne, soit une société."
            )

        if self.personne and self.societe:
            raise ValidationError(
                "Un bailleur ne peut pas être à la fois une personne et une société."
            )

        # Si c'est une personne physique, le signataire doit être cette personne
        if self.personne and self.signataire and self.signataire != self.personne:
            raise ValidationError(
                "Pour une personne physique, le signataire doit être "
                "la personne elle-même."
            )

        # Si c'est une société, un signataire est obligatoire
        if self.societe and not self.signataire:
            raise ValidationError(
                "Une société doit avoir un signataire (personne physique)."
            )

    def __str__(self):
        if self.personne:
            return f"{self.personne.full_name} (Bailleur)"
        elif self.societe:
            return f"{self.societe.full_name} (Bailleur)"
        return "Bailleur inconnu"


class Bien(BaseModel):
    """Model representing the rental property."""

    bailleurs = models.ManyToManyField(
        Bailleur,
        related_name="biens",
        help_text="Un ou plusieurs bailleurs pour ce bien",
    )

    adresse = models.CharField(max_length=255)
    latitude = models.FloatField(null=True, blank=True, default=None)
    longitude = models.FloatField(null=True, blank=True, default=None)
    identifiant_fiscal = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default=None,
        verbose_name="Identifiant fiscal",
    )
    regime_juridique = models.CharField(
        max_length=20,
        choices=RegimeJuridique.choices,
        null=True,
        blank=True,
        default=None,
        verbose_name="Régime juridique",
    )

    type_bien = models.CharField(
        max_length=20,
        choices=PropertyType.choices,
        verbose_name="Type de bien",
        null=True,
        blank=True,
        default=None,
    )
    etage = models.CharField(max_length=10, blank=True)
    porte = models.CharField(max_length=10, blank=True)
    # To do : le mettre a terme pour les assurances
    dernier_etage = models.BooleanField(null=True, blank=True, default=None)

    periode_construction = models.CharField(
        max_length=20,
        choices=ConstructionPeriod.choices,
        blank=True,
        null=True,
        default=None,
        verbose_name="Période de construction",
    )

    superficie = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="En m²",
        null=True,
        blank=True,
        default=None,
    )

    meuble = models.BooleanField(
        null=True, blank=True, default=None, verbose_name="Meublé"
    )

    # Informations DPE (Diagnostic de Performance Énergétique)
    classe_dpe = models.CharField(
        max_length=2,
        choices=DPEClass.choices,
        null=True,
        blank=True,
        default=None,
        verbose_name="Classe énergétique DPE",
    )
    depenses_energetiques = models.CharField(
        max_length=400,
        blank=True,
        null=True,
        default=None,
        verbose_name="Dépenses énergétiques théoriques (€/an)",
    )
    # date_dpe = models.DateField(
    #     null=True, blank=True, verbose_name="Date de réalisation du DPE"
    # )

    # # Caractéristiques supplémentaires
    # annexes = models.TextField(blank=True)
    # additionnal_description = models.TextField(blank=True)

    # Annexes séparées (stockage JSON pour compatibilité frontend)
    annexes_privatives = models.JSONField(null=True, blank=True, default=None)
    annexes_collectives = models.JSONField(null=True, blank=True, default=None)
    information = models.JSONField(null=True, blank=True, default=None)

    # Détail des pièces (stockage JSON pour compatibilité frontend)
    pieces_info = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text="Détail des pièces: chambres, sallesDeBain, cuisines, etc.",
    )

    # Systèmes de chauffage et eau chaude
    chauffage_type = models.CharField(
        max_length=20,
        choices=SystemType.choices,
        blank=True,
        null=True,
        default=None,
    )
    chauffage_energie = models.CharField(
        max_length=50, blank=True, null=True, default=None
    )
    eau_chaude_type = models.CharField(
        max_length=20,
        choices=SystemType.choices,
        blank=True,
        null=True,
        default=None,
    )
    eau_chaude_energie = models.CharField(
        max_length=50, blank=True, null=True, default=None
    )

    # Historique automatique
    history = HistoricalRecords()

    @property
    def nombre_pieces_principales(self):
        """
        Calcule le nombre de pièces principales (chambres + sejours).
        Utilisé pour le matching avec RentPrice.
        """
        if not self.pieces_info:
            return 0

        chambres = self.pieces_info.get("chambres", 0)
        sejours = self.pieces_info.get("sejours", 0)
        return chambres + sejours

    def __str__(self):
        return f"{self.type_bien} - {self.adresse}"


class Locataire(Personne):
    """Model representing the tenant (inherits from Personne)."""

    # Données d'identité supplémentaires spécifiques au locataire
    lieu_naissance = models.CharField(max_length=100, blank=True)

    # Adresse actuelle (différente de l'adresse générale de Personne
    # qui peut être l'adresse du bien loué)
    adresse_actuelle = models.CharField(
        max_length=255,
        blank=True,
        help_text="Adresse actuelle du locataire avant emménagement",
    )

    # Données supplémentaires spécifiques au locataire
    profession = models.CharField(max_length=100, blank=True)
    employeur = models.CharField(max_length=100, blank=True)
    revenu_mensuel = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, default=None
    )
    num_carte_identite = models.CharField(max_length=30, blank=True)
    date_emission_ci = models.DateField(null=True, blank=True, default=None)
    caution_requise = models.BooleanField(
        default=False,
        help_text="Indique si une caution est requise pour ce locataire",
    )

    # Documents pour la signature du bail : maintenant gérés via Document model
    # avec type_document = ATTESTATION_MRH ou CAUTION_SOLIDAIRE
    # Voir: locataire.documents.filter(type_document='attestation_mrh')

    class Meta:
        verbose_name = "Locataire"
        verbose_name_plural = "Locataires"

    def __str__(self):
        return f"{self.firstName} {self.lastName} (Locataire)"


class Location(BaseModel):
    """Location = relation entre un bien et des locataires"""

    # Relations essentielles
    bien = models.ForeignKey(Bien, on_delete=models.PROTECT, related_name="locations")
    mandataire = models.ForeignKey(
        Mandataire, null=True, blank=True, on_delete=models.SET_NULL, default=None
    )
    locataires = models.ManyToManyField(Locataire, related_name="locations")
    solidaires = models.BooleanField(default=False)

    garants = models.ManyToManyField(
        Personne, related_name="bails_garantis", blank=True
    )

    # Dates
    date_debut = models.DateField(null=True, blank=True, default=None)
    date_fin = models.DateField(null=True, blank=True, default=None)

    # Source de création
    created_from = models.CharField(
        max_length=20,
        choices=[
            ("bail", "Bail"),
            ("quittance", "Quittance"),
            ("etat_lieux", "État des lieux"),
            ("manual", "Manuel"),
        ],
        default="manual",
    )

    # Historique automatique
    history = HistoricalRecords()

    def __str__(self):
        return f"Location {self.bien} - {self.date_debut or 'Sans date'}"

    class Meta:
        db_table = "location_location"
        verbose_name = "Location"
        verbose_name_plural = "Locations"
        ordering = ["-created_at"]


class RentTerms(BaseModel):
    """Conditions financières de la location"""

    location = models.OneToOneField(
        Location, on_delete=models.CASCADE, related_name="rent_terms"
    )

    # Montants
    montant_loyer = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, default=None
    )
    type_charges = models.CharField(
        max_length=20,
        choices=ChargeType.choices,
        null=True,
        blank=True,
        default=None,
        verbose_name="Type de charges",
    )
    montant_charges = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, default=None
    )
    jour_paiement = models.PositiveSmallIntegerField(null=True, blank=True, default=5)
    depot_garantie_override = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Override manuel du dépôt de garantie (si None, calculé automatiquement)",
    )

    # Informations réglementaires
    zone_tendue = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text="Situé en zone tendue (déséquilibre offre/demande de logements)",
    )
    zone_tres_tendue = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text="Situé en zone très tendue (Zone A bis - arrêté du 1er août 2014)",
    )
    zone_tendue_touristique = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text="Situé en zone tendue touristique (réglementation meublés de tourisme - 120 jours maximum)",
    )
    premiere_mise_en_location = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text="Première mise en location du bien",
    )
    locataire_derniers_18_mois = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text="Le bien a-t-il eu un locataire dans les 18 derniers mois",
    )
    dernier_montant_loyer = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Montant du dernier loyer si locataire dans les 18 derniers mois",
    )
    dernier_loyer_periode = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        default=None,
        help_text="Mois et année du dernier loyer perçu (format YYYY-MM, ex: 2024-03)",
    )
    permis_de_louer = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name="Permis de louer",
        help_text="Indique si un permis de louer est requis pour ce bien",
    )
    # Information encadrement des loyers
    rent_price_id = models.IntegerField(
        null=True,
        blank=True,
        default=None,
        help_text="ID du RentPrice de référence (base rent_control)",
    )
    justificatif_complement_loyer = models.TextField(
        blank=True,
        null=True,
        default=None,
        verbose_name="Justification du complément de loyer",
        help_text="Justification du complément de loyer en cas de dépassement du plafond d'encadrement",
    )

    @property
    def depot_garantie(self):
        """
        Calcule automatiquement le dépôt de garantie selon la loi française :
        - Non meublé : Maximum 1 mois de loyer HC
        - Meublé : Maximum 2 mois de loyer HC

        Retourne l'override manuel si défini, sinon calcule automatiquement.
        """
        # Si un override manuel est défini, le retourner
        if self.depot_garantie_override is not None:
            return self.depot_garantie_override

        # Sinon, calculer automatiquement
        if not self.montant_loyer:
            return None

        # Vérifier si le bien est meublé
        try:
            meuble = self.location.bien.meuble if self.location and self.location.bien else False
        except Exception:
            meuble = False

        # Calcul selon la réglementation : 1 mois si non meublé, 2 mois si meublé
        multiplier = 2 if meuble else 1
        return self.montant_loyer * multiplier

    def get_rent_price(self):
        """
        Récupère le RentPrice correspondant aux caractéristiques du bien.
        Utilise rent_price_id comme area_id si disponible.
        """
        from rent_control.utils import get_rent_price_for_bien

        if not self.rent_price_id:
            bien: Bien = self.location.bien
            _, area = get_rent_control_info(bien.latitude, bien.longitude)
            if not area:
                return None
            self.rent_price_id = area.id
            self.save(update_fields=["rent_price_id"])

        # rent_price_id stocke en fait l'area_id
        return get_rent_price_for_bien(self.location.bien, self.rent_price_id)

    def __str__(self):
        return f"RentTerms pour {self.location}"

    class Meta:
        db_table = "location_rentterms"
        verbose_name = "Conditions financières"
        verbose_name_plural = "Conditions financières"
