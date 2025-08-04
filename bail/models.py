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


class BailSpecificites(models.Model):
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

    def __str__(self):
        return f"Bail {self.bien} - ({self.date_debut})"


class BailSignatureRequest(models.Model):
    bail = models.ForeignKey(
        BailSpecificites, on_delete=models.CASCADE, related_name="signature_requests"
    )

    # Soit un signataire de bailleur, soit un locataire (un seul à la fois)
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
        related_name="signature_requests",
    )

    order = models.PositiveSmallIntegerField(
        help_text="Ordre de signature dans le processus"
    )
    otp = models.CharField(max_length=6, blank=True, default="")
    otp_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Horodatage de génération de l'OTP (pour vérifier l'expiration)",
    )
    signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)
    link_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        unique_together = [("bail", "bailleur_signataire"), ("bail", "locataire")]
        ordering = ["order"]

    def __str__(self):
        signataire = self.get_signataire_name()
        return f"Signature de {signataire} pour {self.bail}"

    def get_signataire_name(self):
        if self.bailleur_signataire:
            return self.bailleur_signataire.full_name
        elif self.locataire:
            return self.locataire.full_name
        return "Inconnu"

    def get_email(self):
        if self.bailleur_signataire:
            return self.bailleur_signataire.email
        elif self.locataire:
            return self.locataire.email
        return None

    def is_otp_valid(self, otp_value, expiry_minutes=10):
        """
        Vérifie si l'OTP fourni est valide (correct et non expiré).

        Args:
            otp_value (str): L'OTP à vérifier
            expiry_minutes (int): Durée de validité en minutes (défaut: 10)

        Returns:
            bool: True si l'OTP est valide, False sinon
        """
        # Vérifier que l'OTP correspond
        if self.otp != otp_value:
            return False

        # Vérifier que l'OTP n'est pas vide
        if not self.otp:
            return False

        # Vérifier que l'horodatage existe
        if not self.otp_generated_at:
            return False

        # Vérifier que l'OTP n'a pas expiré
        from datetime import timedelta

        from django.utils import timezone

        expiry_time = self.otp_generated_at + timedelta(minutes=expiry_minutes)
        return timezone.now() <= expiry_time

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


# ==============================
# MODÈLES POUR ÉTAT DES LIEUX
# ==============================


class EtatLieuxType(models.TextChoices):
    """Types d'état des lieux"""

    ENTREE = "entree", "État des lieux d'entrée"
    SORTIE = "sortie", "État des lieux de sortie"


class ElementState(models.TextChoices):
    """États possibles pour un élément"""

    MAUVAIS = "M", "Mauvais"
    PASSABLE = "P", "Passable"
    BON = "B", "Bon"
    TRES_BON = "TB", "Très bon"
    EMPTY = "", "Non renseigné"


class EtatLieux(models.Model):
    """Modèle principal pour l'état des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relations
    bail = models.ForeignKey(
        BailSpecificites, on_delete=models.CASCADE, related_name="etats_lieux"
    )

    # Type et dates
    type_etat_lieux = models.CharField(
        max_length=10, choices=EtatLieuxType.choices, help_text="Type d'état des lieux"
    )

    # PDF généré
    pdf = models.FileField(
        upload_to="etat_lieux_pdfs/",
        null=True,
        blank=True,
        help_text="PDF de l'état des lieux généré",
    )

    # Timestamps
    date_creation = models.DateTimeField(default=timezone.now)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bail_etat_lieux"
        verbose_name = "État des lieux"
        verbose_name_plural = "États des lieux"
        ordering = ["-date_creation"]

    def __str__(self):
        type_display = self.get_type_etat_lieux_display()
        return f"État des lieux {type_display} - {self.bail.bien.adresse}"


class EtatLieuxPiece(models.Model):
    """Pièce pour les états des lieux - rattachée directement au bien"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation directe avec le bien
    bien = models.ForeignKey(
        Bien, on_delete=models.CASCADE, related_name="pieces_etat_lieux"
    )

    # Informations de la pièce
    nom = models.CharField(max_length=100, help_text="Nom de la pièce")
    type_piece = models.CharField(max_length=50, help_text="Type de pièce")

    class Meta:
        db_table = "bail_etat_lieux_piece"
        verbose_name = "Pièce état des lieux"
        verbose_name_plural = "Pièces état des lieux"
        unique_together = [["bien", "nom"]]  # Une seule pièce par nom et par bien

    def __str__(self):
        return f"{self.nom} - {self.bien.adresse}"


class EtatLieuxPieceDetail(models.Model):
    """Détails d'une pièce pour un état des lieux spécifique"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    etat_lieux = models.ForeignKey(
        EtatLieux, on_delete=models.CASCADE, related_name="pieces_details"
    )
    piece = models.ForeignKey(
        EtatLieuxPiece, on_delete=models.CASCADE, related_name="details_etat_lieux"
    )

    # États des éléments (JSONField pour flexibilité)
    elements = models.JSONField(
        default=dict, help_text="États des différents éléments de la pièce"
    )

    # Équipements et mobilier
    equipments = models.JSONField(
        default=list, help_text="Liste des équipements de la pièce"
    )
    mobilier = models.JSONField(default=list, help_text="Liste du mobilier de la pièce")

    class Meta:
        db_table = "bail_etat_lieux_piece_detail"
        verbose_name = "Détail pièce état des lieux"
        verbose_name_plural = "Détails pièces état des lieux"
        unique_together = [["etat_lieux", "piece"]]

    def __str__(self):
        return f"{self.piece.nom} - {self.etat_lieux}"


class EtatLieuxSignatureRequest(models.Model):
    """Demande de signature pour un état des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    etat_lieux = models.ForeignKey(
        EtatLieux, on_delete=models.CASCADE, related_name="signature_requests"
    )

    # Signataire (peut être bailleur ou locataire)
    bailleur_signataire = models.ForeignKey(
        "Personne",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="etat_lieux_signatures_bailleur",
    )
    locataire = models.ForeignKey(
        "Locataire",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="etat_lieux_signatures_locataire",
    )

    # Ordre de signature
    order = models.IntegerField(help_text="Ordre de signature")

    # Token et OTP
    link_token = models.UUIDField(default=uuid.uuid4, unique=True)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_generated_at = models.DateTimeField(null=True, blank=True)

    # Signature
    signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)
    signature_image = models.ImageField(
        upload_to="etat_lieux_signatures/", null=True, blank=True
    )

    # Timestamps
    date_creation = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "bail_etat_lieux_signature_request"
        verbose_name = "Demande signature état des lieux"
        verbose_name_plural = "Demandes signature état des lieux"
        ordering = ["order"]

    def __str__(self):
        signer = self.bailleur_signataire or self.locataire
        return f"Signature {self.etat_lieux} - {signer}"

    def is_otp_valid(self, otp_input):
        """Vérifie si l'OTP est valide et non expiré"""
        if not self.otp or not self.otp_generated_at:
            return False

        if self.otp != otp_input:
            return False

        # Vérifier l'expiration (10 minutes)
        expiry_time = timezone.timedelta(minutes=10)
        if timezone.now() - self.otp_generated_at > expiry_time:
            return False

        return True


class EtatLieuxPhoto(models.Model):
    """Photos associées aux éléments d'état des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation avec la pièce (qui contient déjà la relation vers l'état des lieux)
    piece = models.ForeignKey(
        EtatLieuxPiece,
        on_delete=models.CASCADE,
        related_name="photos",
        help_text="Pièce à laquelle cette photo est associée",
    )

    # Localisation de la photo dans le formulaire
    element_key = models.CharField(
        max_length=50, help_text="Clé de l'élément (sol, murs, etc.)"
    )
    photo_index = models.IntegerField(help_text="Index de la photo pour cet élément")

    # Fichier photo
    image = models.ImageField(
        upload_to="etat_lieux_photos/",
        help_text="Photo de l'élément",
    )

    # Métadonnées
    nom_original = models.CharField(max_length=255, help_text="Nom original du fichier")
    date_upload = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "bail_etat_lieux_photo"
        verbose_name = "Photo état des lieux"
        verbose_name_plural = "Photos état des lieux"
        ordering = ["piece", "element_key", "photo_index"]

    def __str__(self):
        return f"Photo {self.piece.nom}/{self.element_key} - {self.piece.bien}"
