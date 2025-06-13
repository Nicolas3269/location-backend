# models.py
import uuid

from django.db import models
from django.utils import timezone

from rent_control.choices import (
    ConstructionPeriod,
    PropertyType,
    RegimeJuridique,
    RoomCount,
    SystemType,
)


class DPEClass(models.TextChoices):
    A = "A", "A (≤ 70 kWh/m²/an)"
    B = "B", "B (71 à 110 kWh/m²/an)"
    C = "C", "C (111 à 180 kWh/m²/an)"
    D = "D", "D (181 à 250 kWh/m²/an)"
    E = "E", "E (251 à 330 kWh/m²/an)"
    F = "F", "F (331 à 420 kWh/m²/an)"
    G = "G", "G (> 420 kWh/m²/an)"
    NA = "NA", "Non soumis à DPE"


class Proprietaire(models.Model):
    """Model representing the property owner."""

    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    adresse = models.CharField(max_length=255)
    telephone = models.CharField(max_length=20)
    email = models.EmailField()

    # Informations bancaires
    iban = models.CharField(max_length=34, blank=True, null=True)

    def __str__(self):
        return f"{self.prenom} {self.nom}"

    def get_full_name(self):
        """Return the full name of the owner."""
        return f"{self.prenom} {self.nom}"


class Bien(models.Model):
    """Model representing the rental property."""

    proprietaires = models.ManyToManyField(Proprietaire, related_name="biens")

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
    etage = models.PositiveSmallIntegerField(null=True, blank=True)
    porte = models.CharField(max_length=10, blank=True)
    dernier_etage = models.BooleanField(default=False)

    periode_construction = models.CharField(
        max_length=20,
        choices=ConstructionPeriod.choices,
        blank=True,
        null=True,
        verbose_name="Période de construction",
    )

    superficie = models.DecimalField(max_digits=8, decimal_places=2, help_text="En m²")
    nb_pieces = models.CharField(
        max_length=10, choices=RoomCount.choices, verbose_name="Nombre de pièces"
    )

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

    # Caractéristiques supplémentaires
    annexes = models.TextField(blank=True)
    additionnal_description = models.TextField(blank=True)

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

    def __str__(self):
        return f"{self.type_bien} - {self.adresse}"


class Locataire(models.Model):
    """Model representing the tenant."""

    # Données d'identité obligatoires
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)

    # Données d'identité importantes mais techniquement optionnelles
    date_naissance = models.DateField(null=True, blank=True)
    lieu_naissance = models.CharField(max_length=100, blank=True)

    # Coordonnées (au moins une nécessaire en pratique)
    adresse_actuelle = models.CharField(max_length=255, blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    # Données supplémentaires
    profession = models.CharField(max_length=100, blank=True)
    employeur = models.CharField(max_length=100, blank=True)
    revenu_mensuel = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    num_carte_identite = models.CharField(max_length=30, blank=True)
    date_emission_ci = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.prenom} {self.nom}"

    def get_full_name(self):
        """Return the full name of the owner."""
        return f"{self.prenom} {self.nom}"


class BailSpecificites(models.Model):
    """Model representing the lease specifics."""

    bien = models.ForeignKey(Bien, on_delete=models.CASCADE, related_name="bails")
    locataires = models.ManyToManyField(Locataire, related_name="bails")

    # Durée du bail
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)

    # Loyer et charges
    montant_loyer = models.DecimalField(max_digits=10, decimal_places=2)
    montant_charges = models.DecimalField(max_digits=10, decimal_places=2)
    jour_paiement = models.PositiveSmallIntegerField(
        default=5, help_text="Jour du mois"
    )
    depot_garantie = models.DecimalField(max_digits=10, decimal_places=2)

    # Compteurs
    releve_eau_entree = models.CharField(max_length=20, blank=True)
    releve_elec_entree = models.CharField(max_length=20, blank=True)
    releve_gaz_entree = models.CharField(max_length=20, blank=True)

    # Dates importantes
    date_signature = models.DateField(default=timezone.now)
    date_etat_lieux_entree = models.DateField(null=True, blank=True)

    # Commentaires
    observations = models.TextField(blank=True)

    # Informations d'encadrement des loyers
    zone_tendue = models.BooleanField(
        default=False, help_text="Situé en zone d'encadrement des loyers"
    )
    prix_reference = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    complement_loyer = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    pdf = models.FileField(
        upload_to="bail_pdfs/", null=True, blank=True, verbose_name="Bail PDF"
    )

    latest_pdf = models.FileField(
        upload_to="bail_pdfs/",
        null=True,
        blank=True,
        verbose_name="Dernière version signée",
    )

    # Annexes du bail
    grille_vetuste_pdf = models.FileField(
        upload_to="bail_pdfs/",
        null=True,
        blank=True,
        verbose_name="Grille de vétusté PDF",
    )
    notice_information_pdf = models.FileField(
        upload_to="bail_pdfs/",
        null=True,
        blank=True,
        verbose_name="Notice d'information PDF",
    )
    dpe_pdf = models.FileField(
        upload_to="bail_pdfs/",
        null=True,
        blank=True,
        verbose_name="Diagnostic de Performance Énergétique PDF",
    )

    # Statut du brouillon
    is_draft = models.BooleanField(
        default=True,
        verbose_name="Brouillon",
        help_text="Indique si le bail est encore en mode brouillon",
    )

    def __str__(self):
        return f"Bail {self.bien} - ({self.date_debut})"


class BailSignatureRequest(models.Model):
    bail = models.ForeignKey(
        BailSpecificites, on_delete=models.CASCADE, related_name="signature_requests"
    )

    # Soit un propriétaire, soit un locataire (un seul à la fois)
    proprietaire = models.ForeignKey(
        Proprietaire,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="signature_requests",
    )
    locataire = models.ForeignKey(
        Locataire,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="signature_requests",
    )

    order = models.PositiveSmallIntegerField(
        help_text="Ordre de signature dans le processus"
    )
    otp = models.CharField(max_length=6)
    signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)
    link_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        unique_together = [("bail", "proprietaire"), ("bail", "locataire")]
        ordering = ["order"]

    def __str__(self):
        signataire = self.get_signataire_name()
        return f"Signature de {signataire} pour {self.bail}"

    def get_signataire_name(self):
        if self.proprietaire:
            return self.proprietaire.get_full_name()
        elif self.locataire:
            return self.locataire.get_full_name()
        return "Inconnu"

    def get_email(self):
        if self.proprietaire:
            return self.proprietaire.email
        elif self.locataire:
            return self.locataire.email
        return None
