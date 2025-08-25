"""
Modèles pour la gestion des locations
Location est l'entité pivot centrale
"""

import uuid

from django.db import models

from rent_control.choices import (
    ChargeType,
    ConstructionPeriod,
    PropertyType,
    RegimeJuridique,
    SystemType,
)


class BaseModel(models.Model):
    """Modèle de base avec timestamps"""

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


# ==============================
# NOUVEAUX MODÈLES POUR BAILLEUR
# ==============================


class Personne(models.Model):
    """Personne physique (propriétaire, signataire, etc.)"""

    lastName = models.CharField(max_length=100, db_column='nom')
    firstName = models.CharField(max_length=100, db_column='prenom')
    date_naissance = models.DateField(
        null=True, blank=True
    )  # Optionnel pour certains cas
    email = models.EmailField()
    adresse = models.TextField()

    # Informations bancaires (pour les propriétaires)
    iban = models.CharField(max_length=34, blank=True, null=True)

    class Meta:
        verbose_name = "Personne"
        verbose_name_plural = "Personnes"

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.firstName} {self.lastName}"


class Societe(models.Model):
    """Société (propriétaire, mandataire, etc.)"""

    siret = models.CharField(max_length=14)
    raison_sociale = models.CharField(max_length=200)
    forme_juridique = models.CharField(max_length=100)
    adresse = models.TextField()
    email = models.EmailField()

    # Informations bancaires (pour les sociétés propriétaires)
    iban = models.CharField(max_length=34, blank=True, null=True)

    class Meta:
        verbose_name = "Société"
        verbose_name_plural = "Sociétés"

    def __str__(self):
        return self.raison_sociale

    @property
    def full_name(self):
        return f"{self.forme_juridique} {self.raison_sociale}"


class Mandataire(models.Model):
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
    date_debut_mandat = models.DateField()
    date_fin_mandat = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Mandataire"
        verbose_name_plural = "Mandataires"

    def __str__(self):
        return f"{self.societe.raison_sociale} (Mandataire)"


class Bailleur(models.Model):
    """Bailleur (propriétaire ou société propriétaire)"""

    # Un bailleur peut être soit une personne physique, soit une société
    personne = models.ForeignKey(
        Personne,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bailleurs",
        help_text="Personne physique bailleur",
    )
    societe = models.ForeignKey(
        Societe,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bailleurs",
        help_text="Société bailleur",
    )

    signataire = models.ForeignKey(
        Personne,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
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
        """Retourne le type de bailleur (personne ou société)"""
        if self.personne:
            return "personne"
        elif self.societe:
            return "societe"
        return "inconnu"

    @property
    def full_name(self):
        """Retourne le nom complet du bailleur."""
        if self.personne:
            return self.personne.full_name
        elif self.societe:
            return self.societe.full_name
        return "Bailleur inconnu"

    @property
    def adresse(self):
        """Retourne l'adresse du bailleur."""
        if self.personne:
            return self.personne.adresse
        elif self.societe:
            return self.societe.adresse
        return "Adresse inconnue"

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


class Bien(models.Model):
    """Model representing the rental property."""

    bailleurs = models.ManyToManyField(
        Bailleur,
        related_name="biens",
        help_text="Un ou plusieurs bailleurs pour ce bien",
    )

    adresse = models.CharField(max_length=255)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    identifiant_fiscal = models.CharField(
        max_length=50, blank=True, verbose_name="Identifiant fiscal"
    )
    regime_juridique = models.CharField(
        max_length=20,
        choices=RegimeJuridique.choices,
        default=RegimeJuridique.MONOPROPRIETE,
        verbose_name="Régime juridique",
    )

    type_bien = models.CharField(
        max_length=20, choices=PropertyType.choices, verbose_name="Type de bien"
    )
    etage = models.CharField(max_length=10, blank=True)
    porte = models.CharField(max_length=10, blank=True)
    # To do : le mettre a terme pour les assurances
    dernier_etage = models.BooleanField(default=False)

    periode_construction = models.CharField(
        max_length=20,
        choices=ConstructionPeriod.choices,
        blank=True,
        null=True,
        verbose_name="Période de construction",
    )

    superficie = models.DecimalField(max_digits=8, decimal_places=2, help_text="En m²")

    meuble = models.BooleanField(default=False, verbose_name="Meublé")

    # Informations DPE (Diagnostic de Performance Énergétique)
    classe_dpe = models.CharField(
        max_length=2,
        choices=DPEClass.choices,
        default=DPEClass.NA,
        verbose_name="Classe énergétique DPE",
    )
    depenses_energetiques = models.CharField(
        max_length=400,
        blank=True,
        default="non renseigné",
        verbose_name="Dépenses énergétiques théoriques (€/an)",
    )
    # date_dpe = models.DateField(
    #     null=True, blank=True, verbose_name="Date de réalisation du DPE"
    # )

    # # Caractéristiques supplémentaires
    # annexes = models.TextField(blank=True)
    # additionnal_description = models.TextField(blank=True)

    # Annexes séparées (stockage JSON pour compatibilité frontend)
    annexes_privatives = models.JSONField(default=list, blank=True)
    annexes_collectives = models.JSONField(default=list, blank=True)
    information = models.JSONField(default=list, blank=True)

    # Détail des pièces (stockage JSON pour compatibilité frontend)
    pieces_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="Détail des pièces: chambres, sallesDeBain, cuisines, etc.",
    )

    # Systèmes de chauffage et eau chaude
    chauffage_type = models.CharField(
        max_length=20,
        choices=SystemType.choices,
        blank=True,
        null=True,
    )
    chauffage_energie = models.CharField(max_length=50, blank=True)
    eau_chaude_type = models.CharField(
        max_length=20,
        choices=SystemType.choices,
        blank=True,
        null=True,
    )
    eau_chaude_energie = models.CharField(max_length=50, blank=True)

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
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    num_carte_identite = models.CharField(max_length=30, blank=True)
    date_emission_ci = models.DateField(null=True, blank=True)
    caution_requise = models.BooleanField(
        default=False,
        help_text="Indique si une caution est requise pour ce locataire",
    )

    class Meta:
        verbose_name = "Locataire"
        verbose_name_plural = "Locataires"

    def __str__(self):
        return f"{self.firstName} {self.lastName} (Locataire)"


class Location(BaseModel):
    """Location = relation entre un bien et des locataires"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    # Relations essentielles
    bien = models.ForeignKey(Bien, on_delete=models.PROTECT, related_name="locations")
    mandataire = models.ForeignKey(
        Mandataire, null=True, blank=True, on_delete=models.SET_NULL
    )
    locataires = models.ManyToManyField(Locataire, related_name="locations")
    solidaires = models.BooleanField(default=False)

    garants = models.ManyToManyField(
        Personne, related_name="bails_garantis", blank=True
    )

    # Dates
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)

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
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    type_charges = models.CharField(
        max_length=20,
        choices=ChargeType.choices,
        null=True,
        blank=True,
        verbose_name="Type de charges",
    )
    montant_charges = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    jour_paiement = models.PositiveSmallIntegerField(null=True, blank=True, default=5)
    depot_garantie = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Informations d'encadrement des loyers
    zone_tendue = models.BooleanField(
        default=False, help_text="Situé en zone d'encadrement des loyers"
    )
    permis_de_louer = models.BooleanField(
        default=False,
        verbose_name="Permis de louer",
        help_text="Indique si un permis de louer est requis pour ce bien",
    )
    rent_price_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID du RentPrice de référence (base rent_control)",
    )
    justificatif_complement_loyer = models.TextField(
        blank=True,
        verbose_name="Justification du complément de loyer",
        help_text="Justification du complément de loyer en cas de dépassement du plafond d'encadrement",
    )

    def get_rent_price(self):
        """Récupère le RentPrice associé à cette location."""
        if not self.rent_price_id:
            return None

        try:
            from rent_control.models import RentPrice

            return RentPrice.objects.get(id=self.rent_price_id)
        except RentPrice.DoesNotExist:
            return None

    def __str__(self):
        return f"RentTerms pour {self.location}"

    class Meta:
        db_table = "location_rentterms"
        verbose_name = "Conditions financières"
        verbose_name_plural = "Conditions financières"
