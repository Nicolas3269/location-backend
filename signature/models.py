"""
Modèles abstraits et utilitaires pour la signature de documents
"""

import uuid
from abc import abstractmethod
from datetime import timedelta

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from location.models import BaseModel, Locataire, Mandataire, Personne


class AbstractSignatureRequest(BaseModel):
    """Modèle abstrait pour les demandes de signature"""

    # Signataire (peut être mandataire, bailleur ou locataire)
    mandataire = models.ForeignKey(
        Mandataire,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Mandataire qui signe pour le compte du bailleur",
    )
    bailleur_signataire = models.ForeignKey(
        Personne,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Signataire du bailleur (personne physique ou représentant de société)",
    )
    locataire = models.ForeignKey(
        Locataire,
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
    signature_image = models.ImageField(upload_to="signatures/", null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["order"]

    def __str__(self):
        signataire = self.get_signataire_name()
        document = self.get_document_name()
        return f"Signature de {signataire} pour {document}"

    @property
    def signer(self):
        """
        Retourne le signataire (Personne ou Mandataire).

        Returns:
            Personne|Mandataire: L'instance qui doit signer
        """
        # Ordre de priorité: mandataire > bailleur_signataire > locataire
        if self.mandataire:
            return self.mandataire.signataire if self.mandataire.signataire else None
        return self.bailleur_signataire or self.locataire

    def get_signataire_name(self):
        """Retourne le nom du signataire"""
        return self.signer.full_name if self.signer else "Inconnu"

    def get_signataire_email(self):
        """Retourne l'email du signataire"""
        return self.signer.email if self.signer else None

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

    @abstractmethod
    def get_document_type(self):
        """
        Retourne le type de document pour le système de signature.

        Returns:
            str: Type de document ('bail', 'etat_lieux', 'quittance', etc.)
        """
        pass


class SignatureMetadata(BaseModel):
    """
    Journal de preuves forensique pour chaque signature utilisateur.

    Stocke toutes les métadonnées nécessaires pour prouver l'authenticité
    d'une signature en cas de litige (conformité eIDAS AES).

    Architecture "Forensic Complete" (Option 2) :
    - Métadonnées OTP/IP/HTTP complètes
    - Certificat X.509 extrait du PDF (accès rapide)
    - Hash PDF avant/après signature
    - Timestamps serveur NTP-sync
    """

    # Relation polymorphe vers document (Bail/EtatLieux/Quittance)
    document_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="signature_metadata_documents",
        help_text="Type de document signé",
    )
    document_object_id = models.UUIDField(help_text="ID du document signé")
    document = GenericForeignKey("document_content_type", "document_object_id")

    # Référence au SignatureRequest (source de vérité)
    # Le signer découle de SignatureRequest.signer
    signature_request_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="signature_metadata_requests",
        help_text="Type de SignatureRequest (Bail, EtatLieux, etc.)",
    )
    signature_request_object_id = models.UUIDField(help_text="ID du SignatureRequest")
    signature_request = GenericForeignKey(
        "signature_request_content_type", "signature_request_object_id"
    )

    # Champ de signature PDF (contient UUID Personne/signer)
    signature_field_name = models.CharField(
        max_length=255,
        help_text="Nom du champ PDF (format: {signer_uuid}-{name} slugifié)",
    )

    # Métadonnées OTP (copie immuable pour audit forensique)
    otp_code = models.CharField(
        max_length=6,
        help_text="Code OTP validé (copie immuable depuis SignatureRequest)",
    )
    otp_generated_at = models.DateTimeField(
        help_text="Date/heure génération OTP (copie immuable)"
    )
    otp_validated_at = models.DateTimeField(
        help_text="Date/heure validation OTP (copie immuable)"
    )
    otp_validated = models.BooleanField(help_text="OTP validé avec succès")

    # Métadonnées HTTP (preuve origine)
    ip_address = models.GenericIPAddressField(help_text="Adresse IP du signataire")
    user_agent = models.TextField(help_text="User-Agent navigateur")
    referer = models.URLField(blank=True, help_text="Referer HTTP")

    # Métadonnées cryptographiques
    signature_timestamp = models.DateTimeField(
        help_text="Date/heure signature (serveur NTP-sync)"
    )
    pdf_hash_before = models.CharField(
        max_length=64, help_text="Hash SHA-256 du PDF AVANT signature"
    )
    pdf_hash_after = models.CharField(
        max_length=64, help_text="Hash SHA-256 du PDF APRÈS signature"
    )

    # Certificat X.509 (extraction depuis PDF pour accès rapide)
    certificate_pem = models.TextField(
        help_text="Certificat X.509 complet (format PEM)"
    )
    certificate_fingerprint = models.CharField(
        max_length=64, help_text="Empreinte SHA-256 du certificat"
    )
    certificate_subject_dn = models.CharField(
        max_length=255, help_text="Subject DN (CN, O, Email)"
    )
    certificate_issuer_dn = models.CharField(
        max_length=255, help_text="Issuer DN (CA Hestia)"
    )
    certificate_valid_from = models.DateTimeField(help_text="Début validité certificat")
    certificate_valid_until = models.DateTimeField(help_text="Fin validité certificat")

    # TSA (optionnel - vide si architecture sans TSA intermédiaires)
    tsa_timestamp = models.CharField(
        max_length=128, blank=True, help_text="Token TSA (si utilisé)"
    )
    tsa_response = models.BinaryField(
        blank=True, null=True, help_text="Réponse complète TSA RFC 3161"
    )

    class Meta:
        ordering = ["signature_timestamp"]
        verbose_name = "Métadonnées de signature"
        verbose_name_plural = "Métadonnées de signatures"
        indexes = [
            models.Index(fields=["document_content_type", "document_object_id"]),
            models.Index(
                fields=["signature_request_content_type", "signature_request_object_id"]
            ),
            models.Index(fields=["signature_timestamp"]),
        ]

    @property
    def signer(self):
        """
        Retourne le signataire depuis le SignatureRequest.

        Returns:
            Personne: L'instance de Personne qui a signé
        """
        # SignatureRequest hérite de AbstractSignatureRequest qui a .signer
        return self.signature_request.signer if self.signature_request else None

    def __str__(self):
        signer_name = self.signer.full_name if self.signer else "Inconnu"
        return f"Signature de {signer_name} - {self.signature_timestamp}"

    def to_proof_dict(self):
        """Export pour journal de preuves JSON"""
        return {
            "signer_email": self.signer.email if self.signer else None,
            "signer_name": self.signer.full_name if self.signer else "Inconnu",
            "signature_timestamp": self.signature_timestamp.isoformat(),
            "otp": {
                "otp_code": self.otp_code,
                "otp_generated_at": self.otp_generated_at.isoformat(),
                "otp_validated_at": self.otp_validated_at.isoformat(),
                "otp_validated": self.otp_validated,
            },
            "http": {
                "ip_address": str(self.ip_address),
                "user_agent": self.user_agent,
                "referer": self.referer,
            },
            "cryptographic": {
                "pdf_hash_before": self.pdf_hash_before,
                "pdf_hash_after": self.pdf_hash_after,
                "certificate_fingerprint": self.certificate_fingerprint,
                "certificate_subject": self.certificate_subject_dn,
                "certificate_issuer": self.certificate_issuer_dn,
            },
            "tsa_timestamp": self.tsa_timestamp if self.tsa_timestamp else None,
        }
