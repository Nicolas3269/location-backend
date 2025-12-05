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
    AVENANT = "avenant", "Avenant au bail"
    GRILLE_VETUSTE = "grille_vetuste", "Grille de vétusté"
    NOTICE_INFORMATION = "notice_information", "Notice d'information"
    DIAGNOSTIC = "diagnostic", "Diagnostics techniques"
    PERMIS_DE_LOUER = "permis_de_louer", "Permis de louer"
    ATTESTATION_MRH = "attestation_mrh", "Attestation MRH"
    CAUTION_SOLIDAIRE = "caution_solidaire", "Caution solidaire"
    AUTRE = "autre", "Autre document"


class Document(BaseModel):
    """Modèle pour gérer tous les documents liés aux baux, biens, locataires ou avenants."""

    # Relations - un document peut être lié à un bail, bien, locataire ou avenant
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
    avenant = models.ForeignKey(
        "Avenant",
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
        # Contraintes uniques PARTIELLES : seulement pour les non-annulées
        # Permet de garder les anciennes signature requests annulées (soft delete)
        # tout en créant de nouvelles pour le même bail/signataire
        constraints = [
            models.UniqueConstraint(
                fields=["bail", "bailleur_signataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_bail_bailleur_signataire_active"
            ),
            models.UniqueConstraint(
                fields=["bail", "locataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_bail_locataire_active"
            ),
            models.UniqueConstraint(
                fields=["bail", "mandataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_bail_mandataire_active"
            ),
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

    # NOTE: mark_as_signed() n'est PAS surchargé ici.
    # Le statut du document (SIGNING → SIGNED) est géré par
    # process_signature_generic dans pdf_processing.py qui vérifie
    # si TOUTES les signatures sont complètes avant de passer à SIGNED.


class AvenantMotif(models.TextChoices):
    """Motifs possibles pour un avenant au bail."""

    IDENTIFIANT_FISCAL = "identifiant_fiscal", "Numéro d'identifiant fiscal"
    DIAGNOSTICS_DDT = "diagnostics_ddt", "Diagnostics techniques obligatoires"
    PERMIS_DE_LOUER = "permis_de_louer", "Autorisation préalable de mise en location"


class Avenant(SignableDocumentMixin, BaseModel):
    """
    Avenant au contrat de bail.
    Permet de compléter un bail signé avec des informations manquantes.
    Un bail peut avoir plusieurs avenants.
    """

    bail = models.ForeignKey(
        Bail,
        on_delete=models.CASCADE,
        related_name="avenants",
        help_text="Bail auquel cet avenant est rattaché",
    )

    # Numéro d'avenant (auto-incrémenté par bail)
    numero = models.PositiveIntegerField(
        verbose_name="Numéro d'avenant",
        help_text="Numéro séquentiel de l'avenant pour ce bail",
    )

    # Motifs de l'avenant (peut en avoir plusieurs)
    motifs = models.JSONField(
        default=list,
        verbose_name="Motifs de l'avenant",
        help_text="Liste des motifs : identifiant_fiscal, diagnostics_ddt, permis_de_louer",
    )

    # Données ajoutées via cet avenant
    identifiant_fiscal = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default=None,
        verbose_name="Identifiant fiscal ajouté",
        help_text="Numéro d'identifiant fiscal du logement (si ajouté via cet avenant)",
    )

    # Les documents (DDT, permis de louer) sont liés via le modèle Document existant
    # avec une référence au bail

    # Historique automatique
    history = HistoricalRecords()

    class Meta:
        db_table = "bail_avenant"
        verbose_name = "Avenant"
        verbose_name_plural = "Avenants"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["bail", "numero"],
                name="unique_avenant_numero_per_bail",
            )
        ]

    def save(self, *args, **kwargs):
        """Auto-incrémente le numéro d'avenant si non défini."""
        if not self.numero:
            # Trouver le dernier numéro pour ce bail
            last_avenant = Avenant.objects.filter(bail=self.bail).order_by(
                "-numero"
            ).first()
            self.numero = (last_avenant.numero + 1) if last_avenant else 1
        super().save(*args, **kwargs)

    def get_document_name(self):
        return f"Avenant n°{self.numero}"

    def get_file_prefix(self):
        return f"avenant_{self.numero}"

    def __str__(self):
        return f"Avenant n°{self.numero} - Bail {self.bail.location.bien.adresse}"

    @property
    def location(self):
        """Accès direct à la location via le bail."""
        return self.bail.location

    @property
    def has_identifiant_fiscal(self):
        return AvenantMotif.IDENTIFIANT_FISCAL in self.motifs

    @property
    def has_diagnostics_ddt(self):
        return AvenantMotif.DIAGNOSTICS_DDT in self.motifs

    @property
    def has_permis_de_louer(self):
        return AvenantMotif.PERMIS_DE_LOUER in self.motifs

    @property
    def mandataire_doit_signer(self):
        """
        Hérite du paramètre du bail parent.
        L'avenant doit être signé par les mêmes parties que le bail.
        """
        return self.bail.mandataire_doit_signer


class AvenantSignatureRequest(AbstractSignatureRequest):
    """Demande de signature pour un avenant."""

    avenant = models.ForeignKey(
        Avenant,
        on_delete=models.CASCADE,
        related_name="signature_requests",
    )

    # Signataires (mêmes que le bail original)
    mandataire = models.ForeignKey(
        Mandataire,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="avenant_signature_requests",
    )
    bailleur_signataire = models.ForeignKey(
        Personne,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="avenant_bailleur_signature_requests",
    )
    locataire = models.ForeignKey(
        Locataire,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="avenant_signature_requests",
    )

    class Meta:
        db_table = "bail_avenant_signature_request"
        # Contraintes uniques PARTIELLES : seulement pour les non-annulées
        constraints = [
            models.UniqueConstraint(
                fields=["avenant", "bailleur_signataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_avenant_bailleur_signataire_active"
            ),
            models.UniqueConstraint(
                fields=["avenant", "locataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_avenant_locataire_active"
            ),
            models.UniqueConstraint(
                fields=["avenant", "mandataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_avenant_mandataire_active"
            ),
        ]
        ordering = ["order"]

    def get_document_name(self):
        return f"Avenant n°{self.avenant.numero} - {self.avenant.bail.location.bien.adresse}"

    def get_document(self):
        return self.avenant

    def get_next_signature_request(self):
        return (
            AvenantSignatureRequest.objects.filter(
                avenant=self.avenant,
                signed=False,
                order__gt=self.order,
            )
            .order_by("order")
            .first()
        )

    def get_document_type(self):
        return SignableDocumentType.AVENANT.value

    # NOTE: mark_as_signed() n'est PAS surchargé ici.
    # Le statut du document (SIGNING → SIGNED) est géré par
    # process_signature_generic dans pdf_processing.py qui vérifie
    # si TOUTES les signatures sont complètes avant de passer à SIGNED.
