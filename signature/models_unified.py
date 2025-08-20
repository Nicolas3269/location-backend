"""
Modèle SignatureRequest unifié utilisant GenericForeignKey
Pour gérer les signatures de tous les documents signables
"""

import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from signature.models import AbstractSignatureRequest


class SignatureRequest(AbstractSignatureRequest):
    """Demande de signature unifiée pour tous les documents signables"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation générique vers n'importe quel document signable
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to={
            "model__in": ["bail", "etatlieux"]  # Extensible à d'autres modèles
        },
    )
    object_id = models.UUIDField()
    document = GenericForeignKey("content_type", "object_id")

    # Signataires
    bailleur_signataire = models.ForeignKey(
        "bail.Personne",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="signature_requests_bailleur",
    )
    locataire = models.ForeignKey(
        "bail.Locataire",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="signature_requests_locataire",
    )

    def get_document(self):
        """Retourne le document associé"""
        return self.document

    def get_document_name(self):
        """Retourne le nom du document à signer"""
        if hasattr(self.document, "get_document_name"):
            return self.document.get_document_name()
        return str(self.document)

    def get_next_signature_request(self):
        """Retourne la prochaine demande de signature dans l'ordre"""
        return (
            SignatureRequest.objects.filter(
                content_type=self.content_type,
                object_id=self.object_id,
                signed=False,
                order__gt=self.order,
            )
            .order_by("order")
            .first()
        )

    def save(self, *args, **kwargs):
        """Override save pour mettre à jour automatiquement le statut du document"""
        super().save(*args, **kwargs)

        # Mettre à jour le statut du document associé s'il a une méthode check_and_update_status
        if self.document and hasattr(self.document, "check_and_update_status"):
            self.document.check_and_update_status()

    class Meta:
        ordering = ["order"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]
        db_table = "signature_request"
        verbose_name = "Demande de signature"
        verbose_name_plural = "Demandes de signature"

    def __str__(self):
        return f"Signature {self.get_document_name()} - {'Signé' if self.signed else 'En attente'}"
