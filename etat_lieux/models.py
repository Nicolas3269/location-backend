"""
Nouveau modèle EtatLieux refactorisé
À renommer en models.py après validation
"""

from django.db import models
from simple_history.models import HistoricalRecords

from backend.pdf_utils import get_static_pdf_iframe_url
from location.models import (
    BaseModel,
    DocumentAvecMandataireMixin,
    Locataire,
    Location,
    Mandataire,
    Personne,
)
from signature.document_types import SignableDocumentType
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


class EtatLieux(DocumentAvecMandataireMixin, SignableDocumentMixin, BaseModel):
    """État des lieux"""

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="etats_lieux"
    )

    type_etat_lieux = models.CharField(max_length=10, choices=EtatLieuxType.choices)

    # Date de l'état des lieux
    date_etat_lieux = models.DateField()
    # Inventaire (garde en JSON car structure simple)
    nombre_cles = models.JSONField(default=dict)
    compteurs = models.JSONField(default=None, null=True, blank=True)

    # Commentaires généraux sur l'état des lieux
    commentaires_generaux = models.TextField(
        default=None,
        null=True,
        blank=True,
        help_text="Commentaires généraux sur l'état des lieux",
    )

    # Annulation
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Historique automatique
    history = HistoricalRecords()

    # Les équipements sont maintenant gérés via le modèle EtatLieuxEquipement
    # (anciennement stockés dans des JSONField)

    # Note: grille_vetuste est un document statique accessible via
    # get_grille_vetuste_url() - pas de champ FileField

    # Note: Les détails des pièces sont dans EtatLieuxPieceDetail
    # Note: Les photos sont dans EtatLieuxPhoto
    # Note: date_signature est gérée par SignableDocumentMixin

    class Meta:
        verbose_name = "État des lieux"
        verbose_name_plural = "États des lieux"
        ordering = ["-created_at"]
        db_table = "etat_lieux_etatlieux"
        constraints = [
            models.UniqueConstraint(
                fields=["location", "type_etat_lieux"],
                condition=models.Q(status__in=["SIGNING", "SIGNED"]),
                name="unique_signing_or_signed_edl_per_location_and_type",
            )
        ]

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

    # Méthode de DocumentAvecMandataireMixin
    def get_reference_date_for_honoraires(self):
        """
        Date de référence pour les honoraires (fallback si pas encore signé).
        Pour un EDL : date effective de l'état des lieux.
        """
        return self.date_etat_lieux

    def get_grille_vetuste_url(self, request):
        """
        Retourne l'URL de la grille de vétusté (document statique).
        Factorise la logique au lieu d'utiliser le champ grille_vetuste_pdf.

        Args:
            request: L'objet request Django pour construire l'URL absolue

        Returns:
            str: URL complète de la grille de vétusté statique
        """

        return get_static_pdf_iframe_url(request, "bails/grille_vetuste.pdf")

    def _format_equipment_data(self, equipment, include_date_entretien=False):
        """Méthode commune pour formater les données d'un équipement"""
        from etat_lieux.utils import StateEquipmentUtils
        from etat_lieux.views import image_to_base64_data_url

        # Récupérer les photos de l'équipement et convertir en Base64 pour WeasyPrint
        photos = []
        for photo in equipment.photos.all():
            if photo.image:
                photo_data_url = image_to_base64_data_url(photo.image)
                if photo_data_url:
                    photos.append(photo_data_url)

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
    """
    Équipement pour un état des lieux (sol, mur, chaudière, cave, etc.)

    Note: L'ID peut être fourni par le frontend lors de la création.
    Si non fourni, Django génère automatiquement un UUID via BaseModel.
    """

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
        help_text="Quantité de l'équipement (pour les équipements comptables)",
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

    # Relation directe avec l'équipement
    # SET_NULL permet de conserver les photos temporairement lors du submit final
    # (évite la perte lors de la recréation des équipements)
    # Un job de nettoyage supprimera les photos orphelines > 7 jours
    equipment = models.ForeignKey(
        EtatLieuxEquipement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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
        if self.equipment:
            return (
                f"Photo {self.equipment.equipment_name} - "
                f"{self.equipment.etat_lieux}"
            )
        else:
            return f"Photo standalone {self.nom_original} (ID: {self.id})"


class EtatLieuxSignatureRequest(AbstractSignatureRequest):
    """Demande de signature pour un état des lieux"""

    etat_lieux = models.ForeignKey(
        EtatLieux, on_delete=models.CASCADE, related_name="signature_requests"
    )

    # Override les champs related_name pour éviter les conflits avec bail
    mandataire = models.ForeignKey(
        Mandataire,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="etat_lieux_signature_requests",
        help_text="Mandataire qui signe pour le compte du bailleur",
    )
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

    class Meta:
        verbose_name = "Demande signature état des lieux"
        verbose_name_plural = "Demandes signature état des lieux"
        # Contraintes uniques PARTIELLES : seulement pour les non-annulées
        # Permet de garder les anciennes signature requests annulées (soft delete)
        # tout en créant de nouvelles pour le même etat_lieux/signataire
        constraints = [
            models.UniqueConstraint(
                fields=["etat_lieux", "bailleur_signataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_edl_bailleur_signataire_active"
            ),
            models.UniqueConstraint(
                fields=["etat_lieux", "locataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_edl_locataire_active"
            ),
            models.UniqueConstraint(
                fields=["etat_lieux", "mandataire"],
                condition=models.Q(cancelled_at__isnull=True),
                name="unique_edl_mandataire_active"
            ),
        ]
        ordering = ["order"]

    def get_document_name(self):
        """Retourne le nom du document à signer"""
        type_display = self.etat_lieux.get_type_etat_lieux_display()
        return f"{type_display} - {self.etat_lieux.location.bien.adresse}"

    def get_page_title(self):
        """Retourne le titre de la page de signature"""
        if self.etat_lieux.type_etat_lieux == EtatLieuxType.ENTREE:
            return "Signer l'état des lieux d'entrée"
        return "Signer l'état des lieux de sortie"

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

    def get_document_type(self):
        """Retourne le type de document"""
        return SignableDocumentType.ETAT_LIEUX.value

    # NOTE: mark_as_signed() n'est PAS surchargé ici.
    # Le statut du document (SIGNING → SIGNED) est géré par
    # process_signature_generic dans pdf_processing.py qui vérifie
    # si TOUTES les signatures sont complètes avant de passer à SIGNED.
