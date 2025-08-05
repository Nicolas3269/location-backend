# models.py
import uuid

from django.db import models
from django.utils import timezone

from bail.models import BailSpecificites, Bien, Locataire, Personne


class EtatLieuxType(models.TextChoices):
    """Types d'état des lieux"""

    ENTREE = "entree", "État des lieux d'entrée"
    SORTIE = "sortie", "État des lieux de sortie"


class ElementState(models.TextChoices):
    """États possibles pour un élément"""

    MAUVAIS = "M", "Mauvais"
    PASSABLE = "P", "Passable"
    BON = "B", "Bon"
    TRES_BON = "TB", "Très bon"
    EMPTY = "", "Non renseigné"


class EtatLieux(models.Model):
    """Modèle principal pour l'état des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relations
    bail = models.ForeignKey(
        BailSpecificites, on_delete=models.CASCADE, related_name="etats_lieux"
    )

    # Type et dates
    type_etat_lieux = models.CharField(
        max_length=10, choices=EtatLieuxType.choices, help_text="Type d'état des lieux"
    )

    # PDF généré
    pdf = models.FileField(
        upload_to="etat_lieux_pdfs/",
        null=True,
        blank=True,
        help_text="PDF de l'état des lieux généré",
    )

    # Timestamps
    date_creation = models.DateTimeField(default=timezone.now)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "État des lieux"
        verbose_name_plural = "États des lieux"
        ordering = ["-date_creation"]

    def __str__(self):
        type_display = self.get_type_etat_lieux_display()
        return f"État des lieux {type_display} - {self.bail.bien.adresse}"


class EtatLieuxPiece(models.Model):
    """Pièce pour les états des lieux - rattachée directement au bien"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation directe avec le bien
    bien = models.ForeignKey(
        Bien, on_delete=models.CASCADE, related_name="pieces_etat_lieux"
    )

    # Informations de la pièce
    nom = models.CharField(max_length=100, help_text="Nom de la pièce")
    type_piece = models.CharField(max_length=50, help_text="Type de pièce")

    class Meta:
        verbose_name = "Pièce état des lieux"
        verbose_name_plural = "Pièces état des lieux"
        unique_together = [["bien", "nom"]]  # Une seule pièce par nom et par bien

    def __str__(self):
        return f"{self.nom} - {self.bien.adresse}"


class EtatLieuxPieceDetail(models.Model):
    """Détails d'une pièce pour un état des lieux spécifique"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    etat_lieux = models.ForeignKey(
        EtatLieux, on_delete=models.CASCADE, related_name="pieces_details"
    )
    piece = models.ForeignKey(
        EtatLieuxPiece, on_delete=models.CASCADE, related_name="details_etat_lieux"
    )

    # États des éléments (JSONField pour flexibilité)
    elements = models.JSONField(
        default=dict, help_text="États des différents éléments de la pièce"
    )

    # Équipements et mobilier
    equipments = models.JSONField(
        default=list, help_text="Liste des équipements de la pièce"
    )
    mobilier = models.JSONField(default=list, help_text="Liste du mobilier de la pièce")

    class Meta:
        verbose_name = "Détail pièce état des lieux"
        verbose_name_plural = "Détails pièces état des lieux"
        unique_together = [["etat_lieux", "piece"]]

    def __str__(self):
        return f"{self.piece.nom} - {self.etat_lieux}"


class EtatLieuxSignatureRequest(models.Model):
    """Demande de signature pour un état des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    etat_lieux = models.ForeignKey(
        EtatLieux, on_delete=models.CASCADE, related_name="signature_requests"
    )

    # Signataire (peut être bailleur ou locataire)
    bailleur_signataire = models.ForeignKey(
        Personne,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="etat_lieux_signatures_bailleur",
    )
    locataire = models.ForeignKey(
        Locataire,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="etat_lieux_signatures_locataire",
    )

    # Ordre de signature
    order = models.IntegerField(help_text="Ordre de signature")

    # Token et OTP
    link_token = models.UUIDField(default=uuid.uuid4, unique=True)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_generated_at = models.DateTimeField(null=True, blank=True)

    # Signature
    signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)
    signature_image = models.ImageField(
        upload_to="etat_lieux_signatures/", null=True, blank=True
    )

    # Timestamps
    date_creation = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Demande signature état des lieux"
        verbose_name_plural = "Demandes signature état des lieux"
        ordering = ["order"]

    def __str__(self):
        signer = self.bailleur_signataire or self.locataire
        return f"Signature {self.etat_lieux} - {signer}"

    def is_otp_valid(self, otp_input):
        """Vérifie si l'OTP est valide et non expiré"""
        if not self.otp or not self.otp_generated_at:
            return False

        if self.otp != otp_input:
            return False

        # Vérifier l'expiration (10 minutes)
        expiry_time = timezone.timedelta(minutes=10)
        if timezone.now() - self.otp_generated_at > expiry_time:
            return False

        return True


class EtatLieuxPhoto(models.Model):
    """Photos associées aux éléments d'état des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation avec la pièce (qui contient déjà la relation vers l'état des lieux)
    piece = models.ForeignKey(
        EtatLieuxPiece,
        on_delete=models.CASCADE,
        related_name="photos",
        help_text="Pièce à laquelle cette photo est associée",
    )

    # Localisation de la photo dans le formulaire
    element_key = models.CharField(
        max_length=50, help_text="Clé de l'élément (sol, murs, etc.)"
    )
    photo_index = models.IntegerField(help_text="Index de la photo pour cet élément")

    # Fichier photo
    image = models.ImageField(
        upload_to="etat_lieux_photos/",
        help_text="Photo de l'élément",
    )

    # Métadonnées
    nom_original = models.CharField(max_length=255, help_text="Nom original du fichier")
    date_upload = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Photo état des lieux"
        verbose_name_plural = "Photos état des lieux"
        ordering = ["piece", "element_key", "photo_index"]

    def __str__(self):
        return f"Photo {self.piece.nom}/{self.element_key} - {self.piece.bien}"
