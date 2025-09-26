"""
Nouveau modèle EtatLieux refactorisé
À renommer en models.py après validation
"""

import uuid

from django.db import models
from django.utils import timezone

from location.models import BaseModel, Locataire, Location, Personne
from signature.document_status import DocumentStatus
from signature.models import AbstractSignatureRequest
from signature.models_base import SignableDocumentMixin


# Enums pour les équipements
class EquipmentType(models.TextChoices):
    PIECE = "piece", "Équipement de pièce"
    CHAUFFAGE = "chauffage", "Chauffage"
    ANNEXE = "annexe", "Annexe"


class ElementState(models.TextChoices):
    """États possibles pour un élément"""

    TRES_BON = "TB", "Très bon"
    BON = "B", "Bon"
    PASSABLE = "P", "Passable"
    MAUVAIS = "M", "Mauvais"
    EMPTY = "", "Non renseigné"


class EtatLieuxType(models.TextChoices):
    """Types d'état des lieux"""

    ENTREE = "entree", "État des lieux d'entrée"
    SORTIE = "sortie", "État des lieux de sortie"


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
    compteurs = models.JSONField(default=None, null=True, blank=True)

    # Commentaires généraux sur l'état des lieux
    commentaires_generaux = models.TextField(
        default=None,
        null=True,
        blank=True,
        help_text="Commentaires généraux sur l'état des lieux"
    )

    # Les équipements sont maintenant gérés via le modèle EtatLieuxEquipement
    # (anciennement stockés dans des JSONField)

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
        unique_together = [["location", "type_etat_lieux"]]

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

    def _format_equipment_data(self, equipment, include_date_entretien=False):
        """Méthode commune pour formater les données d'un équipement"""
        from etat_lieux.utils import StateEquipmentUtils

        # Récupérer les photos de l'équipement
        photos = [photo.image.url for photo in equipment.photos.all() if photo.image]

        formatted = {
            "uuid": str(equipment.id),
            "type": equipment.equipment_key,
            "type_label": equipment.equipment_name,
            "state": equipment.state,
            "state_label": StateEquipmentUtils.get_state_display(equipment.state),
            "state_color": StateEquipmentUtils.get_state_color(equipment.state),
            "state_css_class": StateEquipmentUtils.get_state_css_class(equipment.state),
            "comment": equipment.comment,
            "photos": photos,
        }

        # Ajouter les données spécifiques au chauffage si nécessaire
        if include_date_entretien:
            formatted["date_entretien"] = (
                equipment.data.get("date_entretien", "") if equipment.data else ""
            )
            formatted["date_entretien_formatted"] = (
                StateEquipmentUtils.format_date_entretien(
                    equipment.data.get("date_entretien", "") if equipment.data else ""
                )
            )

        return formatted

    def get_equipements_chauffage_formatted(self):
        """Prépare les données des équipements de chauffage pour l'affichage dans le PDF"""
        chaudieres = []
        chauffe_eaux = []

        # Récupérer tous les équipements de chauffage
        for equipment in self.equipements.filter(
            equipment_type=EquipmentType.CHAUFFAGE
        ):
            formatted = self._format_equipment_data(
                equipment, include_date_entretien=True
            )

            if equipment.equipment_key == "chaudiere":
                chaudieres.append(formatted)
            else:
                chauffe_eaux.append(formatted)

        # Trier par UUID pour un ordre cohérent
        chaudieres.sort(key=lambda x: x["uuid"])
        chauffe_eaux.sort(key=lambda x: x["uuid"])

        return {"chaudieres": chaudieres, "chauffe_eaux": chauffe_eaux}

    def get_annexes_privatives_formatted(self):
        """Prépare les données des annexes privatives pour l'affichage dans le PDF"""
        formatted_annexes = {}

        # Récupérer tous les équipements d'annexes
        for equipment in self.equipements.filter(equipment_type=EquipmentType.ANNEXE):
            # Utiliser la méthode commune pour formater les données
            formatted = self._format_equipment_data(equipment)

            # Adapter le format pour les annexes (garder la compatibilité avec le template)
            formatted_annexes[equipment.equipment_key] = formatted

        return formatted_annexes


class EtatLieuxPiece(BaseModel):
    """Pièce pour un état des lieux spécifique"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation directe avec l'état des lieux
    etat_lieux = models.ForeignKey(
        EtatLieux, on_delete=models.CASCADE, related_name="pieces"
    )

    # Informations de la pièce
    nom = models.CharField(max_length=100, help_text="Nom de la pièce")
    type_piece = models.CharField(max_length=50, help_text="Type de pièce")

    class Meta:
        verbose_name = "Pièce état des lieux"
        verbose_name_plural = "Pièces état des lieux"
        unique_together = [["etat_lieux", "nom"]]
        db_table = "etat_lieux_piece"

    def __str__(self):
        return f"{self.nom} - {self.etat_lieux}"


class EtatLieuxEquipement(BaseModel):
    """Équipement pour un état des lieux (sol, mur, chaudière, cave, etc.)"""

    # L'ID est généré côté frontend
    id = models.UUIDField(primary_key=True, editable=False)

    etat_lieux = models.ForeignKey(
        EtatLieux, on_delete=models.CASCADE, related_name="equipements"
    )

    # Type d'équipement
    equipment_type = models.CharField(
        max_length=20, choices=EquipmentType.choices, help_text="Type d'équipement"
    )

    # Clé de l'équipement
    equipment_key = models.CharField(
        max_length=50,
        help_text="Identifiant de l'équipement (sol, murs, chaudiere, cave, etc.)",
    )

    # Nom d'affichage de l'équipement
    equipment_name = models.CharField(
        max_length=100,
        help_text="Nom d'affichage de l'équipement (Sol, Murs, Chaudière, Cave, etc.)",
    )

    # Relation optionnelle avec la pièce (seulement pour type='piece')
    piece = models.ForeignKey(
        EtatLieuxPiece,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="equipements",
        help_text="Pièce associée (si équipement de pièce)",
    )

    # État et commentaires
    state = models.CharField(
        max_length=20,
        choices=ElementState.choices,
        blank=True,
        help_text="État de l'équipement",
    )
    comment = models.TextField(blank=True, help_text="Commentaire sur l'équipement")

    # Quantité (pour les équipements comptables)
    quantity = models.IntegerField(
        null=True,
        blank=True,
        help_text="Quantité de l'équipement (pour les équipements comptables)"
    )

    # Données additionnelles (date_entretien, etc.)
    data = models.JSONField(
        default=dict,
        help_text="Données additionnelles spécifiques au type d'équipement",
    )

    class Meta:
        verbose_name = "Équipement état des lieux"
        verbose_name_plural = "Équipements état des lieux"
        unique_together = [["etat_lieux", "equipment_type", "equipment_key", "piece"]]
        db_table = "etat_lieux_equipement"

    def __str__(self):
        if self.piece:
            return f"{self.equipment_name} - {self.piece.nom}"
        return f"{self.equipment_name} - {self.etat_lieux}"


class EtatLieuxPhoto(BaseModel):
    """Photos associées aux équipements d'état des lieux"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation directe avec l'équipement
    equipment = models.ForeignKey(
        EtatLieuxEquipement,
        on_delete=models.CASCADE,
        related_name="photos",
        help_text="Équipement associé",
    )

    # Index de la photo
    photo_index = models.IntegerField(
        default=0, help_text="Index de la photo pour cet équipement"
    )

    # Fichier photo
    image = models.ImageField(
        upload_to="etat_lieux_photos/",
        help_text="Photo de l'équipement",
    )

    # Métadonnées
    nom_original = models.CharField(max_length=255, help_text="Nom original du fichier")

    class Meta:
        verbose_name = "Photo état des lieux"
        verbose_name_plural = "Photos état des lieux"
        ordering = ["equipment", "photo_index"]
        db_table = "etat_lieux_photo"

    def __str__(self):
        return f"Photo {self.equipment.equipment_name} - {self.equipment.etat_lieux}"


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
