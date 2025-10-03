"""
Nouveau modèle Quittance refactorisé
À renommer en models.py après validation
"""

import uuid

from django.db import models
from simple_history.models import HistoricalRecords

from location.models import BaseModel, Locataire, Location
from signature.document_status import DocumentStatus


class Quittance(BaseModel):
    """Quittance de loyer"""

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="quittances"
    )

    # Locataires concernés par cette quittance (permet de gérer les quittances partielles)
    # Si vide, on considère que la quittance concerne tous les locataires de la location
    locataires = models.ManyToManyField(
        Locataire,
        related_name="quittances",
        blank=True,
        help_text="Locataire(s) concerné(s) par cette quittance. Si vide, tous les locataires de la location sont concernés.",
    )

    # Statut du document
    status = models.CharField(
        max_length=20, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT
    )

    # Annulation
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Période
    mois = models.CharField(
        max_length=20, help_text="Mois en français (janvier, février, etc.)"
    )
    annee = models.PositiveIntegerField(help_text="Année de la quittance")

    # Date de paiement
    date_paiement = models.DateField(help_text="Date à laquelle le loyer a été payé")

    # Montants spécifiques à cette quittance (peuvent différer du bail en cas d'évolution)
    montant_loyer = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Montant du loyer hors charges pour cette quittance",
    )
    montant_charges = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Montant des charges pour cette quittance",
    )

    # Document
    pdf = models.FileField(
        upload_to="quittances_pdfs/",
        null=True,
        blank=True,
        help_text="PDF de la quittance généré",
    )

    # Historique automatique
    history = HistoricalRecords()

    @property
    def montant_total(self):
        """Calcule le montant total (loyer + charges)"""
        return (self.montant_loyer or 0) + (self.montant_charges or 0)

    class Meta:
        verbose_name = "Quittance"
        verbose_name_plural = "Quittances"
        ordering = ["-created_at"]
        db_table = "quittance_quittance"

    def __str__(self):
        return f"Quittance {self.mois} {self.annee} - {self.location.bien.adresse}"

    def check_and_update_status(self):
        """Met à jour automatiquement le statut selon les signatures"""
        # Pour les quittances, le statut est géré différemment :
        # - DRAFT lors de la création
        # - SIGNED dès que le PDF est généré (fait dans generate_quittance_pdf)
        # Cette méthode est là pour compatibilité mais ne fait rien pour les quittances
        # car elles n'ont pas de processus de signature
        pass
