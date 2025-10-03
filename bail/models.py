"""
Nouveau modèle Bail refactorisé
À renommer en models.py après validation
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from location.models import BaseModel, Bien, Locataire, Location, Personne
from signature.document_status import DocumentStatus
from signature.models import AbstractSignatureRequest
from signature.models_base import SignableDocumentMixin

# Les modèles Personne, Societe, Mandataire, Bailleur, Bien, Locataire restent inchangés
# (on garde les existants)


class Bail(SignableDocumentMixin, BaseModel):
    """Contrat de bail (ex-Bail)"""

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="bails"
    )

    # Statut
    status = models.CharField(
        max_length=20, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT
    )

    # Annulation
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Durée
    duree_mois = models.IntegerField(default=12)

    # Documents et clauses
    justificatifs = models.JSONField(default=list)
    clauses_particulieres = models.TextField(blank=True)
    observations = models.TextField(blank=True)

    # PDFs spécifiques au bail
    notice_information_pdf = models.FileField(
        upload_to="bail_pdfs/", null=True, blank=True
    )
    dpe_pdf = models.FileField(
        upload_to="bail_pdfs/",
        null=True,
        blank=True,
        verbose_name="Diagnostic de Performance Énergétique PDF",
    )
    grille_vetuste_pdf = models.FileField(
        upload_to="bail_pdfs/",
        null=True,
        blank=True,
        verbose_name="Grille de vétusté PDF",
    )

    # Dates importantes
    date_signature = models.DateField(default=timezone.now)

    # Travaux et réparations
    travaux_bailleur = models.TextField(blank=True)
    travaux_locataire = models.TextField(blank=True)
    honoraires_ttc = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Historique automatique
    history = HistoricalRecords()

    # Méthodes héritées de l'ancien Bail
    def check_and_update_status(self):
        """Met à jour automatiquement le statut selon les signatures"""
        current_status = self.status

        # Ne pas passer automatiquement de DRAFT à SIGNING
        # Cela sera fait par send_signature_email quand on envoie vraiment l'email

        # Passer de SIGNING à SIGNED si toutes les signatures sont complètes
        if self.status == DocumentStatus.SIGNING:
            if (
                self.signature_requests.exists()
                and not self.signature_requests.filter(signed=False).exists()
            ):
                self.status = DocumentStatus.SIGNED

        if current_status != self.status:
            self.save(update_fields=["status"])

    # Méthodes de SignableDocumentMixin
    def get_document_name(self):
        return "Bail"

    def get_file_prefix(self):
        return "bail"

    def __str__(self):
        return f"Bail {self.location.bien} - ({self.location.date_debut})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["location"],
                condition=models.Q(status__in=["SIGNING", "SIGNED"]),
                name="unique_signing_or_signed_bail_per_location",
            )
        ]
        ordering = ["-created_at"]
        db_table = "bail_bail_new"
        verbose_name = "Bail"
        verbose_name_plural = "Bails"


class DocumentType(models.TextChoices):
    """Types de documents gérés dans le système."""

    BAIL = "bail", "Contrat de bail"
    GRILLE_VETUSTE = "grille_vetuste", "Grille de vétusté"
    NOTICE_INFORMATION = "notice_information", "Notice d'information"
    DIAGNOSTIC = "diagnostic", "Diagnostic"
    PERMIS_DE_LOUER = "permis_de_louer", "Permis de louer"
    AUTRE = "autre", "Autre document"


class Document(BaseModel):
    """Modèle pour gérer tous les documents liés aux baux et aux biens."""

    # Relations - un document peut être lié soit à un bail, soit à un bien
    bail = models.ForeignKey(
        Bail,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    bien = models.ForeignKey(
        Bien,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )

    type_document = models.CharField(max_length=50, choices=DocumentType.choices)
    nom_original = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/%Y/%m/")

    uploade_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_uploades",
    )

    class Meta:
        db_table = "bail_document"
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_type_document_display()} - {self.nom_original}"


class BailSignatureRequest(AbstractSignatureRequest):
    bail = models.ForeignKey(
        Bail, on_delete=models.CASCADE, related_name="signature_requests"
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
        return f"Contrat de bail - {self.bail.location.bien.adresse}"

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

    def mark_as_signed(self):
        """Marque la demande comme signée et met à jour le statut du document"""
        super().mark_as_signed()
        # Vérifier et mettre à jour le statut du bail
        if self.bail:
            self.bail.check_and_update_status()

    def save(self, *args, **kwargs):
        """Override save pour mettre à jour automatiquement le statut du bail"""
        super().save(*args, **kwargs)

        # Mettre à jour le statut du bail associé (pour compatibilité)
        if self.bail:
            self.bail.check_and_update_status()
