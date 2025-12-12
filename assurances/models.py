"""
Modèles Assurances - MRH, PNO, GLI.

Ce module contient les modèles pour gérer les devis et polices d'assurance
souscrits via le partenaire Mila.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from location.models import BaseModel, Locataire
from signature.models import AbstractSignatureRequest
from signature.models_base import SignableDocumentMixin


class InsuranceProduct(models.TextChoices):
    """Types de produits d'assurance."""

    MRH = "MRH", "Multirisque Habitation (Locataire)"
    PNO = "PNO", "Propriétaire Non Occupant"
    GLI = "GLI", "Garantie Loyers Impayés"


# Préfixes pour les numéros de police par produit
POLICY_NUMBER_PREFIXES = {
    InsuranceProduct.MRH: "PO-MRHIND-67",
    InsuranceProduct.PNO: "PO-PNOIND-67",
    InsuranceProduct.GLI: "PO-GLIIND-67",
}


class InsuranceQuotation(BaseModel, SignableDocumentMixin):
    """
    Devis d'assurance demandé via API Mila.

    Hérite de:
    - BaseModel: id (UUID), created_at, updated_at
    - SignableDocumentMixin: status, pdf, latest_pdf, est_signe, etc.

    Pour la signature, on utilise le champ `pdf` (hérité de SignableDocumentMixin)
    (les CP sont le document légal à signer, pas le devis ni les CGV).
    """

    # Utilisateur qui a demandé le devis
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="insurance_quotations",
        help_text="Utilisateur ayant demandé le devis",
    )

    # Type de produit
    product = models.CharField(
        max_length=10,
        choices=InsuranceProduct.choices,
        default=InsuranceProduct.MRH,
    )

    # Location associée (nullable pour assurance standalone)
    location = models.ForeignKey(
        "location.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="insurance_quotations",
    )

    # Paramètres de tarification
    deductible = models.IntegerField(default=170)
    effective_date = models.DateField()

    # Réponse API Mila (JSON des formules)
    formulas_data = models.JSONField()

    # Formule sélectionnée
    selected_formula_code = models.CharField(max_length=50, blank=True, default="")

    # Document devis (optionnel, pour archive)
    devis_document = models.FileField(
        upload_to="assurances/devis/",
        null=True,
        blank=True,
        default=None,
    )
    # Note: Le PDF des CP utilise `pdf` hérité de SignableDocumentMixin
    # Le PDF signé est stocké dans `latest_pdf`

    # Expiration
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "Devis assurance"
        verbose_name_plural = "Devis assurances"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "product", "status"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"Devis {self.product} {self.id}"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    # ===== Implémentation SignableDocumentMixin =====

    def get_document_name(self) -> str:
        return f"Devis {self.get_product_label()}"

    def get_file_prefix(self) -> str:
        return f"devis_{self.product.lower()}"

    # ===== Properties =====

    @property
    def is_valid(self) -> bool:
        return timezone.now() < self.expires_at

    @property
    def formulas_count(self) -> int:
        return len(self.formulas_data) if self.formulas_data else 0

    @property
    def selected_formula(self) -> dict | None:
        if not self.selected_formula_code or not self.formulas_data:
            return None
        for formula in self.formulas_data:
            if formula.get("code") == self.selected_formula_code:
                return formula
        return None

    def get_product_label(self) -> str:
        return InsuranceProduct(self.product).label


class InsurancePolicy(BaseModel):
    """
    Police d'assurance souscrite.

    Représente une souscription effective à une assurance.
    Le numéro de police suit le format: PO-{PRODUCT}IND-67XXXXXXX

    Hérite de BaseModel: id (UUID), created_at, updated_at

    Les données du produit/formule/tarif sont accessibles via la FK quotation.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente de paiement"
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspendue (impayé)"
        CANCELLED = "CANCELLED", "Résiliée"
        EXPIRED = "EXPIRED", "Expirée"

    # Numéro de police: PO-MRHIND-670000001, PO-PNOIND-670000001, etc.
    policy_number = models.CharField(
        max_length=25,
        unique=True,
        blank=True,
        help_text="Format: PO-{PRODUCT}IND-67XXXXXXX",
    )

    # Relations
    quotation = models.ForeignKey(
        InsuranceQuotation,
        on_delete=models.PROTECT,
        related_name="policies",
        help_text="Devis source (contient product, location, formule, tarifs)",
    )
    subscriber = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="insurance_policies",
        help_text="Souscripteur (locataire ou bailleur)",
    )

    # Statut et dates
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        default=None,
        help_text="Date de fin (null = en cours)",
    )
    activated_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        help_text="Date d'activation après paiement",
    )

    # Stripe
    stripe_checkout_session_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="ID de la Checkout Session Stripe",
    )
    stripe_payment_intent_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="ID du PaymentIntent Stripe (paiement unique)",
    )
    stripe_subscription_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="ID de la Subscription Stripe (paiement mensuel)",
    )
    stripe_customer_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="ID du Customer Stripe",
    )

    # Documents générés
    # Note: cp_document est une property vers quotation.latest_pdf (CP signées)
    attestation_document = models.FileField(
        upload_to="assurances/attestation/",
        null=True,
        blank=True,
        default=None,
        help_text="Attestation d'assurance PDF",
    )

    class Meta:
        verbose_name = "Police assurance"
        verbose_name_plural = "Polices assurances"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["policy_number"]),
            models.Index(fields=["subscriber", "status"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.policy_number} - {self.quotation.product} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.policy_number:
            from .services.policy_number import generate_policy_number

            self.policy_number = generate_policy_number(self.quotation.product)
        super().save(*args, **kwargs)

    # ===== Properties =====
    # Note: product, location, effective_date, deductible, formula_* sont
    # accessibles via policy.quotation.xxx (utiliser select_related)

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def can_be_cancelled(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def cp_document(self):
        """
        Accès aux Conditions Particulières signées.

        Les CP sont stockées dans quotation.latest_pdf après signature.
        """
        return self.quotation.latest_pdf if self.quotation else None


class InsuranceQuotationSignatureRequest(AbstractSignatureRequest):
    """
    Demande de signature pour un devis d'assurance.

    Suit le même pattern que BailSignatureRequest/EtatLieuxSignatureRequest.
    Pour l'assurance MRH, il n'y a qu'un seul signataire : le locataire souscripteur.
    """

    quotation = models.ForeignKey(
        InsuranceQuotation,
        on_delete=models.CASCADE,
        related_name="signature_requests",
    )

    # Override le champ locataire pour spécifier le related_name
    locataire = models.ForeignKey(
        Locataire,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="insurance_signature_requests",
        help_text="Locataire souscripteur",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["quotation", "locataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_quotation_locataire_active",
            ),
        ]
        verbose_name = "Demande signature assurance"
        verbose_name_plural = "Demandes signatures assurances"

    def get_document_name(self) -> str:
        """Retourne le nom du document à signer."""
        return f"Devis {self.quotation.get_product_label()}"

    def get_document(self):
        """Retourne l'objet document associé (le devis)."""
        return self.quotation

    def get_next_signature_request(self):
        """
        Retourne la prochaine demande de signature.
        Pour l'assurance, il n'y a qu'un signataire donc retourne None.
        """
        return None

    def get_document_type(self) -> str:
        """Retourne le type de document pour le système de signature."""
        return "assurance"


class StaticDocument(BaseModel):
    """
    Documents statiques générés une seule fois et stockés en media storage.

    Utilisé pour les documents réglementaires qui ne changent pas par utilisateur :
    - DER (Document d'Entrée en Relation)
    - CGV (Conditions Générales de Vente) par produit
    """

    class DocumentType(models.TextChoices):
        DER = "DER", "Document d'Entrée en Relation"
        CGV_MRH = "CGV_MRH", "Conditions Générales MRH"
        CGV_PNO = "CGV_PNO", "Conditions Générales PNO"
        CGV_GLI = "CGV_GLI", "Conditions Générales GLI"

    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        unique=True,
        help_text="Type de document statique",
    )

    file = models.FileField(
        upload_to="assurances/static_documents/",
        help_text="Fichier PDF généré",
    )

    version = models.CharField(
        max_length=20,
        default="1.0",
        help_text="Version du document (ex: 2024.1)",
    )

    class Meta:
        verbose_name = "Document statique"
        verbose_name_plural = "Documents statiques"

    def __str__(self):
        return f"{self.get_document_type_display()} v{self.version}"

    @property
    def url(self) -> str | None:
        """Retourne l'URL publique du fichier."""
        if self.file:
            return self.file.url
        return None

    @classmethod
    def get_or_generate(cls, document_type: str, force_regenerate: bool = False):
        """
        Récupère le document existant ou le génère s'il n'existe pas.

        Args:
            document_type: Type de document (DER, CGV_MRH, etc.)
            force_regenerate: Force la régénération même si le document existe

        Returns:
            Instance de StaticDocument avec le fichier généré
        """
        from django.core.files.base import ContentFile

        from .services.documents import InsuranceDocumentService

        doc, created = cls.objects.get_or_create(
            document_type=document_type,
            defaults={"version": "2024.1"},
        )

        # Générer si nouveau ou forcé ou pas de fichier
        if created or force_regenerate or not doc.file:
            service = InsuranceDocumentService()
            pdf_bytes = service.generate_static_document(document_type)

            filename = f"{document_type.lower()}.pdf"
            doc.file.save(filename, ContentFile(pdf_bytes), save=True)

        return doc
