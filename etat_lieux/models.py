# models.py
import uuid

from django.db import models
from django.utils import timezone

from bail.models import BailSpecificites, Bien, Locataire, Personne
from signature.models import AbstractSignatureRequest
from signature.models_base import SignableDocumentMixin


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


class EtatLieux(SignableDocumentMixin):
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

    # Informations complémentaires
    nombre_cles = models.JSONField(
        default=dict, 
        help_text="Nombre et types de clés remises",
        blank=True
    )
    equipements_chauffage = models.JSONField(
        default=dict,
        help_text="Équipements de chauffage et eau chaude",
        blank=True
    )
    compteurs = models.JSONField(
        default=dict,
        help_text="Relevés des compteurs",
        blank=True
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

    # Interface SignableDocument
    def get_document_name(self):
        """Retourne le nom du type de document"""
        return "État des lieux"

    def get_file_prefix(self):
        """Retourne le préfixe pour les noms de fichiers"""
        return "etat_lieux"


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


class EtatLieuxSignatureRequest(AbstractSignatureRequest):
    """Demande de signature pour un état des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    etat_lieux = models.ForeignKey(
        EtatLieux, on_delete=models.CASCADE, related_name="signature_requests"
    )

    # Override les champs related_name pour éviter les conflits avec bail
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

    # Garder l'ancien champ pour compatibilité
    date_creation = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Demande signature état des lieux"
        verbose_name_plural = "Demandes signature état des lieux"
        ordering = ["order"]

    def get_document_name(self):
        """Retourne le nom du document à signer"""
        type_display = self.etat_lieux.get_type_etat_lieux_display()
        return f"{type_display} - {self.etat_lieux.bail.bien.adresse}"

    def get_document(self):
        """Retourne l'objet document associé"""
        return self.etat_lieux

    def get_next_signature_request(self):
        """Retourne la prochaine demande de signature dans l'ordre"""
        return (
            EtatLieuxSignatureRequest.objects.filter(
                etat_lieux=self.etat_lieux,
                signed=False,
                order__gt=self.order,
            )
            .order_by("order")
            .first()
        )


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
