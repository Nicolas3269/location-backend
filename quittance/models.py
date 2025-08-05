import uuid

from django.db import models
from django.utils import timezone

from bail.models import BailSpecificites


class Quittance(models.Model):
    """Modèle pour stocker les quittances générées"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation avec le bail
    bail = models.ForeignKey(
        BailSpecificites, on_delete=models.CASCADE, related_name="quittances"
    )

    # Période de la quittance
    mois = models.CharField(
        max_length=20, help_text="Mois en français (janvier, février, etc.)"
    )
    annee = models.PositiveIntegerField(help_text="Année de la quittance")

    # Date de paiement
    date_paiement = models.DateField(help_text="Date à laquelle le loyer a été payé")

    # Montant
    montant_loyer = models.DecimalField(max_digits=10, decimal_places=2)

    # PDF généré
    pdf = models.FileField(
        upload_to="quittances_pdfs/",
        null=True,
        blank=True,
        help_text="PDF de la quittance généré",
    )

    # Timestamps
    date_creation = models.DateTimeField(default=timezone.now)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quittance"
        verbose_name_plural = "Quittances"
        ordering = ["-date_creation"]
        # Une seule quittance par mois/année/bail
        unique_together = [["bail", "mois", "annee"]]

    def __str__(self):
        return f"Quittance {self.mois} {self.annee} - {self.bail.bien.adresse}"
