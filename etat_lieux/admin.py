from django.contrib import admin
from django.utils.html import format_html

from etat_lieux.models import (
    EtatLieux,
    EtatLieuxPhoto,
    EtatLieuxPiece,
    EtatLieuxPieceDetail,
    EtatLieuxSignatureRequest,
)


class EtatLieuxPieceInlineBien(admin.TabularInline):
    """Inline pour afficher les pièces d'état des lieux d'un bien"""

    model = EtatLieuxPiece
    extra = 0
    fields = ("nom", "type_piece")
    show_change_link = True


class EtatLieuxSignatureRequestInline(admin.TabularInline):
    """Inline pour les demandes de signature d'un état des lieux"""

    model = EtatLieuxSignatureRequest
    extra = 0
    fields = ("order", "bailleur_signataire", "locataire", "signed", "signed_at")
    readonly_fields = ("link_token", "signed_at", "otp_generated_at")


@admin.register(EtatLieux)
class EtatLieuxAdmin(admin.ModelAdmin):
    """Interface d'administration pour les états des lieux"""

    list_display = (
        "id",
        "type_etat_lieux",
        "location_info",
        "date_etat_lieux",
        "created_at",
        "pdf_link",
    )

    list_filter = (
        "type_etat_lieux",
        "date_etat_lieux",
        "created_at",
    )

    search_fields = (
        "location__bien__adresse",
        "location__locataires__lastName",
        "location__locataires__firstName",
    )

    readonly_fields = ("id", "created_at", "updated_at", "pdf_link", "latest_pdf_link")

    fieldsets = (
        (None, {"fields": ("id", "location", "type_etat_lieux", "date_etat_lieux")}),
        (
            "Inventaire",
            {
                "fields": ("nombre_cles", "compteurs", "equipements_chauffage"),
                "classes": ("collapse",),
            }
        ),
        (
            "PDF",
            {
                "fields": ("pdf", "pdf_link", "latest_pdf", "latest_pdf_link", "grille_vetuste_pdf"),
                "classes": ("collapse",)
            }
        ),
        (
            "Métadonnées",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    inlines = [EtatLieuxSignatureRequestInline]

    def location_info(self, obj):
        """Affiche les informations de la location"""
        bien_adresse = obj.location.bien.adresse
        locataires = ", ".join([f"{loc.firstName} {loc.lastName}" for loc in obj.location.locataires.all()])
        return format_html(
            "{}<br><small>{}</small>",
            bien_adresse,
            locataires
        )

    location_info.short_description = "Location"

    def pdf_link(self, obj):
        """Affiche un lien vers le PDF s'il existe"""
        if obj.pdf:
            return format_html(
                '<a href="{}" target="_blank">Télécharger PDF</a>', obj.pdf.url
            )
        return "Pas de PDF"

    pdf_link.short_description = "PDF Original"

    def latest_pdf_link(self, obj):
        """Affiche un lien vers le PDF signé s'il existe"""
        if obj.latest_pdf:
            return format_html(
                '<a href="{}" target="_blank">Télécharger PDF Signé</a>', obj.latest_pdf.url
            )
        return "Pas de PDF signé"

    latest_pdf_link.short_description = "PDF Signé"


@admin.register(EtatLieuxPiece)
class EtatLieuxPieceAdmin(admin.ModelAdmin):
    """Interface d'administration pour les pièces d'état des lieux"""

    list_display = (
        "nom",
        "type_piece",
        "bien_adresse",
    )

    list_filter = (
        "type_piece",
        "bien__type_bien",
    )

    search_fields = (
        "nom",
        "bien__adresse",
    )

    fieldsets = ((None, {"fields": ("bien", "nom", "type_piece")}),)

    def bien_adresse(self, obj):
        """Bien de la pièce"""
        return obj.bien.adresse

    bien_adresse.short_description = "Bien"


@admin.register(EtatLieuxPieceDetail)
class EtatLieuxPieceDetailAdmin(admin.ModelAdmin):
    """Interface d'administration pour les détails des pièces d'état des lieux"""

    list_display = (
        "piece_nom",
        "etat_lieux_type",
        "etat_lieux_bien",
    )

    list_filter = (
        "etat_lieux__type_etat_lieux",
        "piece__type_piece",
    )

    search_fields = (
        "piece__nom",
        "etat_lieux__location__bien__adresse",
    )

    readonly_fields = ("elements", "equipments", "mobilier", "degradations")

    fieldsets = (
        (None, {"fields": ("etat_lieux", "piece")}),
        (
            "Données JSON",
            {
                "fields": ("elements", "equipments", "mobilier", "degradations"),
                "classes": ("collapse",),
            },
        ),
    )

    def piece_nom(self, obj):
        """Nom de la pièce"""
        return obj.piece.nom

    piece_nom.short_description = "Pièce"

    def etat_lieux_type(self, obj):
        """Type d'état des lieux"""
        return obj.etat_lieux.get_type_etat_lieux_display()

    etat_lieux_type.short_description = "Type état des lieux"

    def etat_lieux_bien(self, obj):
        """Bien de l'état des lieux"""
        return obj.etat_lieux.location.bien.adresse

    etat_lieux_bien.short_description = "Bien"


@admin.register(EtatLieuxSignatureRequest)
class EtatLieuxSignatureRequestAdmin(admin.ModelAdmin):
    """Interface d'administration pour les demandes de signature d'état des lieux"""

    list_display = (
        "etat_lieux_display",
        "signataire_display",
        "order",
        "signed",
        "signed_at",
        "date_creation",
    )

    list_filter = (
        "signed",
        "etat_lieux__type_etat_lieux",
        "date_creation",
    )

    search_fields = (
        "bailleur_signataire__email",
        "locataire__email",
        "etat_lieux__location__bien__adresse",
    )

    readonly_fields = (
        "id",
        "link_token",
        "otp_generated_at",
        "signed_at",
        "date_creation",
        "signature_image_link",
    )

    fieldsets = (
        (None, {"fields": ("etat_lieux", "order", "bailleur_signataire", "locataire")}),
        (
            "Authentification",
            {
                "fields": ("link_token", "otp", "otp_generated_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Signature",
            {
                "fields": (
                    "signed",
                    "signed_at",
                    "signature_image",
                    "signature_image_link",
                ),
            },
        ),
        ("Métadonnées", {"fields": ("id", "date_creation"), "classes": ("collapse",)}),
    )

    def etat_lieux_display(self, obj):
        """Affichage de l'état des lieux"""
        etat_type = obj.etat_lieux.get_type_etat_lieux_display()
        bien_adresse = obj.etat_lieux.location.bien.adresse
        return f"{etat_type} - {bien_adresse}"

    etat_lieux_display.short_description = "État des lieux"

    def signataire_display(self, obj):
        """Affichage du signataire"""
        if obj.bailleur_signataire:
            nom = f"{obj.bailleur_signataire.firstName} {obj.bailleur_signataire.lastName}"
            return f"Bailleur: {nom}"
        elif obj.locataire:
            return f"Locataire: {obj.locataire.firstName} {obj.locataire.lastName}"
        return "Aucun signataire"

    signataire_display.short_description = "Signataire"

    def signature_image_link(self, obj):
        """Lien vers l'image de signature"""
        if obj.signature_image:
            return format_html(
                '<a href="{}" target="_blank">Voir signature</a>',
                obj.signature_image.url,
            )
        return "Pas de signature"

    signature_image_link.short_description = "Image signature"


@admin.register(EtatLieuxPhoto)
class EtatLieuxPhotoAdmin(admin.ModelAdmin):
    """Interface d'administration pour les photos d'état des lieux"""

    list_display = (
        "id",
        "piece_display",
        "element_key",
        "photo_index",
        "nom_original",
        "image_preview",
        "created_at",
    )

    list_filter = (
        "element_key",
        "created_at",
        "piece_detail__piece__nom",
    )

    search_fields = (
        "piece_detail__piece__nom",
        "element_key",
        "nom_original",
        "piece_detail__piece__bien__adresse",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "image_preview",
    )

    fieldsets = (
        (None, {"fields": ("piece_detail", "element_key", "photo_index")}),
        ("Fichier", {"fields": ("image", "image_preview", "nom_original")}),
        (
            "Métadonnées",
            {
                "fields": ("id", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def piece_display(self, obj):
        """Affichage de la pièce et du bien"""
        piece = obj.piece_detail.piece
        etat_lieux = obj.piece_detail.etat_lieux
        return f"{piece.nom} - {etat_lieux.get_type_etat_lieux_display()}"

    piece_display.short_description = "Pièce"

    def image_preview(self, obj):
        """Prévisualisation de l'image"""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px;" />',
                obj.image.url,
            )
        return "Pas d'image"

    image_preview.short_description = "Aperçu"