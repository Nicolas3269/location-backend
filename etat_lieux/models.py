"""
Nouveau modèle EtatLieux refactorisé
À renommer en models.py après validation
"""

import uuid

from django.db import models
from django.utils import timezone

from location.models import BaseModel, Bien, Locataire, Location, Personne
from signature.models import AbstractSignatureRequest
from signature.models_base import SignableDocumentMixin
from signature.document_status import DocumentStatus


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


class EtatLieux(SignableDocumentMixin, BaseModel):
    """État des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="etats_lieux"
    )

    type_etat_lieux = models.CharField(max_length=10, choices=EtatLieuxType.choices)
    
    # Statut du document
    status = models.CharField(
        max_length=20, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT
    )

    # Date de l'état des lieux
    date_etat_lieux = models.DateField(default=timezone.now)
    # Inventaire (garde en JSON car structure simple)
    nombre_cles = models.JSONField(default=dict)
    compteurs = models.JSONField(default=dict)
    # Équipements de chauffage avec leur état et date d'entretien
    # Structure: { "uuid": { "type": str, "etat": str, "date_entretien": str } }
    equipements_chauffage = models.JSONField(default=dict)

    # Équipements des annexes privatives - état global simple
    # Structure: { "annexe_id": { "state": str, "comment": str, "photos": [...] } }
    annexes_privatives_equipements = models.JSONField(default=dict)

    # PDF spécifique EDL
    grille_vetuste_pdf = models.FileField(
        upload_to="etat_lieux_pdfs/",
        null=True,
        blank=True,
        verbose_name="Grille de vétusté PDF",
    )

    # Note: Les détails des pièces sont dans EtatLieuxPieceDetail
    # Note: Les photos sont dans EtatLieuxPhoto
    # Note: date_signature est gérée par SignableDocumentMixin

    class Meta:
        verbose_name = "État des lieux"
        verbose_name_plural = "États des lieux"
        ordering = ["-created_at"]
        db_table = "etat_lieux_etatlieux"
        # Unicité : un seul état des lieux par type (entrée/sortie) et par location
        unique_together = [['location', 'type_etat_lieux']]

    def __str__(self):
        type_display = self.get_type_etat_lieux_display()
        return f"État des lieux {type_display} - {self.location.bien.adresse}"

    # Interface SignableDocument
    def get_document_name(self):
        """Retourne le nom du type de document"""
        return "État des lieux"

    def get_file_prefix(self):
        """Retourne le préfixe pour les noms de fichiers"""
        return "etat_lieux"
    
    def check_and_update_status(self):
        """Met à jour automatiquement le statut selon les signatures"""
        from signature.document_status import DocumentStatus
        current_status = self.status

        # Ne pas passer automatiquement de DRAFT à SIGNING
        # Cela sera fait par send_signature_email quand on envoie vraiment l'email

        # Passer de SIGNING à SIGNED si toutes les signatures sont complètes
        if self.status == DocumentStatus.SIGNING:
            if (
                self.signature_requests.exists()
                and not self.signature_requests.filter(signed=False).exists()
            ):
                self.status = DocumentStatus.SIGNED

        if current_status != self.status:
            self.save(update_fields=["status"])

    def get_equipements_chauffage_formatted(self):
        """Prépare les données des équipements de chauffage pour l'affichage dans le PDF"""
        from etat_lieux.utils import EtatElementUtils

        if not self.equipements_chauffage:
            return {'chaudieres': [], 'chauffe_eaux': []}

        chaudieres = []
        chauffe_eaux = []

        for uuid, data in self.equipements_chauffage.items():
            if isinstance(data, dict):
                equipment = EtatElementUtils.format_equipment(data.get('type', ''), data)
                equipment['uuid'] = uuid

                if data.get('type') == 'chaudiere':
                    chaudieres.append(equipment)
                else:
                    chauffe_eaux.append(equipment)

        # Trier par UUID pour un ordre cohérent
        chaudieres.sort(key=lambda x: x['uuid'])
        chauffe_eaux.sort(key=lambda x: x['uuid'])

        return {
            'chaudieres': chaudieres,
            'chauffe_eaux': chauffe_eaux
        }


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
        unique_together = [["bien", "nom"]]
        db_table = "etat_lieux_piece"

    def __str__(self):
        return f"{self.nom} - {self.bien.adresse}"


class EtatLieuxPieceDetail(BaseModel):
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

    # Spécifique sortie
    degradations = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "Détail pièce état des lieux"
        verbose_name_plural = "Détails pièces état des lieux"
        unique_together = [["etat_lieux", "piece"]]
        db_table = "etat_lieux_piecedetail"

    def __str__(self):
        return f"{self.piece.nom} - {self.etat_lieux}"


class EtatLieuxPhoto(BaseModel):
    """Photos associées aux états des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation avec le détail de pièce spécifique à un état des lieux
    piece_detail = models.ForeignKey(
        EtatLieuxPieceDetail,
        on_delete=models.CASCADE,
        related_name="photos",
        help_text="Détail de pièce spécifique à un état des lieux",
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

    class Meta:
        verbose_name = "Photo état des lieux"
        verbose_name_plural = "Photos état des lieux"
        ordering = ["piece_detail", "element_key", "photo_index"]
        db_table = "etat_lieux_photo"

    def __str__(self):
        piece_nom = self.piece_detail.piece.nom
        etat_id = str(self.piece_detail.etat_lieux.id)[:8]
        return f"Photo {piece_nom}/{self.element_key} - EDL {etat_id}"


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
        return f"{type_display} - {self.etat_lieux.location.bien.adresse}"

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
    
    def mark_as_signed(self):
        """Marque la demande comme signée et met à jour le statut du document"""
        super().mark_as_signed()
        # Vérifier et mettre à jour le statut du document
        self.etat_lieux.check_and_update_status()
