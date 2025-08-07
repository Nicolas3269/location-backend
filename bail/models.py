# models.py
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from rent_control.choices import (
    ChargeType,
    ConstructionPeriod,
    PropertyType,
    RegimeJuridique,
    SystemType,
)
from signature.models import AbstractSignatureRequest
from signature.models_base import SignableDocumentMixin


class BailStatus(models.TextChoices):
    """Statuts possibles pour un bail"""

    DRAFT = "draft", "Brouillon"
    SIGNING_IN_PROGRESS = "signing_in_progress", "En cours de signature"
    SIGNED = "signed", "Signé et finalisé"


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

    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
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
        return f"{self.prenom} {self.nom}"


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

    @property
    def nombre_pieces_principales(self):
        """
        Calcule le nombre de pièces principales (chambres + salons).
        Utilisé pour le matching avec RentPrice.
        """
        if not self.pieces_info:
            return 0

        chambres = self.pieces_info.get("chambres", 0)
        salons = self.pieces_info.get("salons", 0)
        return chambres + salons

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
        return f"{self.prenom} {self.nom} (Locataire)"


class BailSpecificites(SignableDocumentMixin):
    """Model representing the lease specifics."""

    bien = models.ForeignKey(Bien, on_delete=models.CASCADE, related_name="bails")

    # Mandataire optionnel au niveau du bail
    mandataire = models.ForeignKey(
        Mandataire,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="baux_geres",
        help_text="Mandataire qui gère ce bail",
    )
    locataires = models.ManyToManyField(Locataire, related_name="bails")
    solidaires = models.BooleanField(
        default=False,
        help_text="Indique si les locataires sont solidaires pour le paiement du loyer",
    )

    # Durée du bail
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)

    # Loyer et charges
    montant_loyer = models.DecimalField(max_digits=10, decimal_places=2)
    type_charges = models.CharField(
        max_length=20,
        choices=ChargeType.choices,
        default=ChargeType.FORFAITAIRES,
        verbose_name="Type de charges",
    )
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
        help_text="Justification du complément de loyer en cas de dépassement "
        "du plafond d'encadrement",
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

    # Statut du bail
    status = models.CharField(
        max_length=20,
        choices=BailStatus.choices,
        default=BailStatus.DRAFT,
        verbose_name="Statut",
        help_text="Statut actuel du bail dans son cycle de vie",
    )

    def check_and_update_status(self):
        """
        Vérifie et met à jour automatiquement le statut du bail selon les signatures
        """
        current_status = self.status

        if self.status == BailStatus.DRAFT:
            # Si des signatures existent, passer en "signing_in_progress"
            if self.signature_requests.exists():
                self.status = BailStatus.SIGNING_IN_PROGRESS

        if self.status == BailStatus.SIGNING_IN_PROGRESS:
            # Si toutes les signatures sont complètes, passer en "signed"
            if (
                self.signature_requests.exists()
                and not self.signature_requests.filter(signed=False).exists()
            ):
                self.status = BailStatus.SIGNED

        # Sauvegarder seulement si le statut a effectivement changé
        if current_status != self.status:
            self.save(update_fields=["status"])

    def get_rent_price(self):
        """
        Récupère le RentPrice associé à ce bail.
        Retourne None si pas de rent_price_id ou si le RentPrice n'existe pas.
        """
        if not self.rent_price_id:
            return None

        try:
            from rent_control.models import RentPrice

            return RentPrice.objects.get(id=self.rent_price_id)
        except RentPrice.DoesNotExist:
            return None

    # Interface SignableDocument
    def get_document_name(self):
        """Retourne le nom du type de document"""
        return "Bail"

    def get_file_prefix(self):
        """Retourne le préfixe pour les noms de fichiers"""
        return "bail"

    def __str__(self):
        return f"Bail {self.bien} - ({self.date_debut})"


class BailSignatureRequest(AbstractSignatureRequest):
    bail = models.ForeignKey(
        BailSpecificites, on_delete=models.CASCADE, related_name="signature_requests"
    )

    # Override les champs pour spécifier les related_name différents d'EtatLieux
    bailleur_signataire = models.ForeignKey(
        Personne,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="bailleur_signature_requests",
        help_text=(
            "Signataire du bailleur (personne physique ou représentant de société)"
        ),
    )
    locataire = models.ForeignKey(
        Locataire,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="bail_signature_requests",
    )

    class Meta:
        unique_together = [("bail", "bailleur_signataire"), ("bail", "locataire")]
        ordering = ["order"]

    def get_document_name(self):
        """Retourne le nom du document à signer"""
        return f"Contrat de bail - {self.bail.bien.adresse}"

    def get_document(self):
        """Retourne l'objet document associé"""
        return self.bail

    def get_next_signature_request(self):
        """Retourne la prochaine demande de signature dans l'ordre"""
        return (
            BailSignatureRequest.objects.filter(
                bail=self.bail,
                signed=False,
                order__gt=self.order,
            )
            .order_by("order")
            .first()
        )

    def save(self, *args, **kwargs):
        """Override save pour mettre à jour automatiquement le statut du bail"""
        super().save(*args, **kwargs)

        # Mettre à jour le statut du bail associé
        if self.bail:
            self.bail.check_and_update_status()


class DocumentType(models.TextChoices):
    """Types de documents gérés dans le système."""

    BAIL = "bail", "Contrat de bail"
    GRILLE_VETUSTE = "grille_vetuste", "Grille de vétusté"
    NOTICE_INFORMATION = "notice_information", "Notice d'information"
    DIAGNOSTIC = "diagnostic", "Diagnostic"
    PERMIS_DE_LOUER = "permis_de_louer", "Permis de louer"
    AUTRE = "autre", "Autre document"


class Document(models.Model):
    """Modèle pour gérer tous les documents liés aux baux et aux biens."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relations - un document peut être lié soit à un bail, soit à un bien
    bail = models.ForeignKey(
        "BailSpecificites",
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
        help_text="Bail auquel ce document est rattaché",
    )
    bien = models.ForeignKey(
        "Bien",
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
        help_text="Bien auquel ce document est rattaché",
    )

    # Métadonnées du document
    type_document = models.CharField(
        max_length=50, choices=DocumentType.choices, help_text="Type de document"
    )
    nom_original = models.CharField(
        max_length=255, help_text="Nom original du fichier uploadé"
    )
    file = models.FileField(
        upload_to="documents/%Y/%m/", help_text="Fichier du document"
    )

    # Timestamps
    date_creation = models.DateTimeField(default=timezone.now)
    date_modification = models.DateTimeField(auto_now=True)

    # Utilisateur qui a uploadé le document
    uploade_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_uploades",
        help_text="Utilisateur qui a uploadé ce document",
    )

    class Meta:
        db_table = "bail_document"
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.get_type_document_display()} - {self.nom_original}"

    @property
    def url(self):
        """Retourne l'URL du fichier."""
        if self.file:
            return self.file.url
        return None

    @property
    def est_diagnostic(self):
        """Indique si ce document est un diagnostic."""
        return self.type_document == DocumentType.DIAGNOSTIC
