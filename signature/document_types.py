"""
Types de documents signables dans le système de signature électronique
"""

from django.db import models


class SignableDocumentType(models.TextChoices):
    """
    Enum des types de documents qui peuvent être signés électroniquement.

    Utilisé pour :
    - Identifier le type de document dans les services de signature
    - Construire les URLs de signature (/bail/signing/, /etat-des-lieux/signing/, etc.)
    - Envoyer les emails de signature avec le bon template
    - Logger les actions de signature
    """

    BAIL = "bail", "Contrat de bail"
    ETAT_LIEUX = "etat_lieux", "État des lieux"
    QUITTANCE = "quittance", "Quittance de loyer"
    AVENANT = "avenant", "Avenant au bail"
    ASSURANCE = "assurance", "Assurance"
