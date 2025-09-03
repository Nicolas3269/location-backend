"""
Nouveau modèle Quittance refactorisé
À renommer en models.py après validation
"""

import uuid

from django.db import models

from location.models import BaseModel, Location
from signature.document_status import DocumentStatus


class Quittance(BaseModel):
    """Quittance de loyer"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="quittances"
    )
    
    # Statut du document
    status = models.CharField(
        max_length=20, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT
    )

    # Période
    mois = models.CharField(
        max_length=20, help_text="Mois en français (janvier, février, etc.)"
    )
    annee = models.PositiveIntegerField(help_text="Année de la quittance")

    # Date de paiement
    date_paiement = models.DateField(help_text="Date à laquelle le loyer a été payé")

    # Document
    pdf = models.FileField(
        upload_to="quittances_pdfs/",
        null=True,
        blank=True,
        help_text="PDF de la quittance généré",
    )

    @property
    def montant_loyer(self):
        """Récupère le montant du loyer depuis RentTerms"""
        if hasattr(self.location, "rent_terms"):
            return self.location.rent_terms.montant_loyer
        return None

    @property
    def montant_charges(self):
        """Récupère le montant des charges depuis RentTerms"""
        if hasattr(self.location, "rent_terms"):
            return self.location.rent_terms.montant_charges
        return None

    @property
    def montant_total(self):
        """Calcule le montant total (loyer + charges)"""
        loyer = self.montant_loyer or 0
        charges = self.montant_charges or 0
        return loyer + charges

    class Meta:
        verbose_name = "Quittance"
        verbose_name_plural = "Quittances"
        ordering = ["-created_at"]
        unique_together = [["location", "mois", "annee"]]
        db_table = "quittance_quittance"

    def __str__(self):
        return f"Quittance {self.mois} {self.annee} - {self.location.bien.adresse}"
    
    def check_and_update_status(self):
        """Met à jour automatiquement le statut selon les signatures"""
        # Pour les quittances, on pourrait avoir une logique différente
        # car elles ne nécessitent pas forcément de signature
        # Mais si on veut implémenter la signature :
        from signature.document_status import DocumentStatus
        current_status = self.status
        
        # Si des signatures sont requises (optionnel pour quittances)
        if hasattr(self, 'signature_requests'):
            if self.status == DocumentStatus.DRAFT:
                if self.signature_requests.exists():
                    self.status = DocumentStatus.SIGNING

            if self.status == DocumentStatus.SIGNING:
                if (
                    self.signature_requests.exists()
                    and not self.signature_requests.filter(signed=False).exists()
                ):
                    self.status = DocumentStatus.SIGNED
        else:
            # Si pas de signature requise, passer directement en SIGNED après génération
            if self.status == DocumentStatus.DRAFT and self.pdf:
                self.status = DocumentStatus.SIGNED

        if current_status != self.status:
            self.save(update_fields=["status"])
