"""
Statuts communs pour tous les documents signables.
"""

from django.db import models


class DocumentStatus(models.TextChoices):
    """Statuts possibles pour les documents (bail, état des lieux, quittance)"""

    DRAFT = "draft", "Brouillon"
    SIGNING = "signing", "En cours de signature"
    SIGNED = "signed", "Signé et finalisé"
    CANCELLED = "cancelled", "Annulé"