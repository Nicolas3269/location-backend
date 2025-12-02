from django.core.validators import EmailValidator
from django.db import models


class NotificationRequest(models.Model):
    """
    Modèle pour stocker les demandes de notification des utilisateurs
    pour les nouvelles fonctionnalités
    """

    FEATURE_CHOICES = [
        ("assurance", "Comparateur d'assurances"),
        ("demenagement", "Service déménagement"),
        ("stockage", "Box de stockage"),
        ("energie", "Énergie (électricité/gaz)"),
        ("eau", "Fournisseur d'eau"),
        ("internet", "Internet/Box"),
    ]

    ROLE_CHOICES = [
        ("proprietaire", "Propriétaire"),
        ("mandataire", "Mandataire immobilier"),
        ("locataire", "Locataire"),
        ("comptable", "Comptable"),
        ("autre", "Autre"),
    ]

    email = models.EmailField(
        validators=[EmailValidator()], help_text="Adresse email pour la notification"
    )

    feature = models.CharField(
        max_length=20, choices=FEATURE_CHOICES, help_text="Fonctionnalité demandée"
    )

    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, help_text="Rôle de l'utilisateur"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    notified = models.BooleanField(default=False, help_text="Notification envoyée")
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification_requests"
        unique_together = ["email", "feature"]  # Éviter les doublons
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} - {self.get_feature_display()}"
