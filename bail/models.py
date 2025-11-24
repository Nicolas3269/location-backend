"""
Nouveau modèle Bail refactorisé
À renommer en models.py après validation
"""

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from backend.pdf_utils import get_static_pdf_iframe_url
from location.models import (
    BaseModel,
    Bien,
    DocumentAvecMandataireMixin,
    Locataire,
    Location,
    Mandataire,
    Personne,
)
from signature.document_types import SignableDocumentType
from signature.models import AbstractSignatureRequest
from signature.models_base import SignableDocumentMixin

# Les modèles Personne, Societe, Mandataire, Bailleur, Bien, Locataire restent inchangés
# (on garde les existants)


class Bail(DocumentAvecMandataireMixin, SignableDocumentMixin, BaseModel):
    """Contrat de bail (ex-Bail)"""

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="bails"
    )

    # Annulation
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Durée
    duree_mois = models.IntegerField(default=12)

    # Documents et clauses
    justificatifs = models.JSONField(default=list)
    clauses_particulieres = models.TextField(blank=True)
    observations = models.TextField(blank=True)

    # Confirmation DPE G (logement non décent depuis 1er janvier 2025)
    signature_dpe_g_acknowledgment = models.BooleanField(
        default=False,
        verbose_name="Confirmation responsabilité DPE G",
        help_text=(
            "Confirmation du bailleur qu'il assume la responsabilité de louer "
            "un logement classé G, non décent depuis le 1er janvier 2025"
        ),
    )

    # PDFs spécifiques au bail
    # Note: notice_information et grille_vetuste sont des documents statiques
    # accessibles via get_notice_information_url() - pas de champ FileField
    # Note: Les diagnostics (DPE, etc.) sont gérés via le modèle Document

    # Travaux et réparations
    travaux_bailleur = models.TextField(blank=True)
    travaux_locataire = models.TextField(blank=True)
    honoraires_ttc = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Historique automatique
    history = HistoricalRecords()

    # Méthodes de SignableDocumentMixin
    def get_document_name(self):
        return "Bail"

    def get_file_prefix(self):
        return "bail"

    # Méthode de DocumentAvecMandataireMixin
    def get_reference_date_for_honoraires(self):
        """
        Date de référence pour les honoraires (fallback si pas encore signé).
        Pour un bail : date de création du brouillon.
        """
        return self.created_at.date()

    def get_notice_information_url(self, request):
        """
        Retourne l'URL de la notice d'information (document statique).
        Factorise la logique au lieu d'utiliser le champ notice_information_pdf.

        Args:
            request: L'objet request Django pour construire l'URL absolue

        Returns:
            str: URL complète de la notice d'information statique
        """

        return get_static_pdf_iframe_url(request, "bails/notice_information.pdf")

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
    DIAGNOSTIC = "diagnostic", "Diagnostics techniques"
    PERMIS_DE_LOUER = "permis_de_louer", "Permis de louer"
    ATTESTATION_MRH = "attestation_mrh", "Attestation MRH"
    CAUTION_SOLIDAIRE = "caution_solidaire", "Caution solidaire"
    AUTRE = "autre", "Autre document"


class Document(BaseModel):
    """Modèle pour gérer tous les documents liés aux baux, biens et locataires."""

    # Relations - un document peut être lié soit à un bail, soit à un bien, soit à un locataire
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
    locataire = models.ForeignKey(
        "location.Locataire",
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
    mandataire = models.ForeignKey(
        Mandataire,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="bail_signature_requests",
        help_text="Mandataire qui signe pour le compte du bailleur",
    )
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
        unique_together = [
            ("bail", "bailleur_signataire"),
            ("bail", "locataire"),
            ("bail", "mandataire"),
        ]
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

    def get_document_type(self):
        """Retourne le type de document"""
        return SignableDocumentType.BAIL.value

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
