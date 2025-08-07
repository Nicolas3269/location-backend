"""
Modèles abstraits et utilitaires pour la signature de documents
"""
import uuid
from abc import abstractmethod
from datetime import timedelta

from django.db import models
from django.utils import timezone


class AbstractSignatureRequest(models.Model):
    """Modèle abstrait pour les demandes de signature"""

    # Signataire (peut être bailleur ou locataire)
    bailleur_signataire = models.ForeignKey(
        "bail.Personne",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Signataire du bailleur (personne physique ou représentant de société)",
    )
    locataire = models.ForeignKey(
        "bail.Locataire",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Locataire signataire",
    )

    # Ordre de signature
    order = models.PositiveSmallIntegerField(
        help_text="Ordre de signature dans le processus"
    )

    # OTP et sécurité
    otp = models.CharField(max_length=6, blank=True, default="")
    otp_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Horodatage de génération de l'OTP (pour vérifier l'expiration)",
    )

    # Lien unique pour accéder à la signature
    link_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # État de la signature
    signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)

    # Image de la signature (optionnel)
    signature_image = models.ImageField(
        upload_to="signatures/", null=True, blank=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["order"]

    def __str__(self):
        signataire = self.get_signataire_name()
        document = self.get_document_name()
        return f"Signature de {signataire} pour {document}"

    def get_signataire_name(self):
        """Retourne le nom du signataire"""
        if self.bailleur_signataire:
            return self.bailleur_signataire.full_name
        elif self.locataire:
            return self.locataire.full_name
        return "Inconnu"

    def get_signataire_email(self):
        """Retourne l'email du signataire"""
        if self.bailleur_signataire:
            return self.bailleur_signataire.email
        elif self.locataire:
            return self.locataire.email
        return None

    def is_otp_valid(self, otp_value, expiry_minutes=10):
        """
        Vérifie si l'OTP fourni est valide (correct et non expiré).

        Args:
            otp_value (str): L'OTP à vérifier
            expiry_minutes (int): Durée de validité en minutes (défaut: 10)

        Returns:
            bool: True si l'OTP est valide, False sinon
        """
        if not self.otp or not self.otp_generated_at:
            return False

        # Vérifier si l'OTP correspond
        if self.otp != otp_value:
            return False

        # Vérifier l'expiration
        expiry_time = self.otp_generated_at + timedelta(minutes=expiry_minutes)
        if timezone.now() > expiry_time:
            return False

        return True

    def generate_otp(self):
        """Génère un nouvel OTP à 6 chiffres"""
        import random

        self.otp = str(random.randint(100000, 999999))
        self.otp_generated_at = timezone.now()
        self.save(update_fields=["otp", "otp_generated_at"])
        return self.otp

    def mark_as_signed(self):
        """Marque la demande comme signée"""
        self.signed = True
        self.signed_at = timezone.now()
        self.save(update_fields=["signed", "signed_at"])

    @abstractmethod
    def get_document_name(self):
        """Retourne le nom du document à signer"""
        pass

    @abstractmethod
    def get_document(self):
        """Retourne l'objet document associé"""
        pass

    @abstractmethod
    def get_next_signature_request(self):
        """Retourne la prochaine demande de signature dans l'ordre"""
        pass