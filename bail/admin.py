from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Bail,
    BailSignatureRequest,
    Document,
)


class DocumentInline(admin.TabularInline):
    """Inline pour afficher les documents attachés au bail"""

    model = Document
    fk_name = "bail"
    extra = 0
    fields = (
        "type_document",
        "nom_original",
        "file_link",
        "created_at",
        "uploade_par",
    )
    readonly_fields = ("file_link", "created_at", "uploade_par")
    show_change_link = True

    def file_link(self, obj):
        """Affiche un lien vers le fichier"""
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank">📄 Voir le fichier</a>',
                obj.file.url,
            )
        return "-"

    file_link.short_description = "Fichier"


class BailSignatureRequestInline(admin.TabularInline):
    """Inline pour les demandes de signature d'un bail"""

    model = BailSignatureRequest
    extra = 0
    fields = ("order", "bailleur_signataire", "locataire", "signed", "signed_at")
    readonly_fields = ("link_token", "signed_at")


@admin.register(Bail)
class BailAdmin(admin.ModelAdmin):
    """Interface d'administration pour les baux"""

    list_display = (
        "get_bien_address",
        "display_locataires",
        "get_date_debut",
        "get_date_fin",
        "get_montant_loyer",
        "status",
        "display_documents_status",
        "cancelled_at",
    )
    list_filter = ("status", "cancelled_at")
    search_fields = (
        "location__bien__adresse",
        "location__locataires__lastName",
        "location__locataires__firstName",
    )
    date_hierarchy = "date_signature"
    inlines = [DocumentInline, BailSignatureRequestInline]

    fieldsets = (
        ("Location associée", {"fields": ("location",)}),
        (
            "Informations du bail",
            {
                "fields": (
                    "status",
                    "cancelled_at",
                    "duree_mois",
                )
            },
        ),
        (
            "Dates importantes",
            {"fields": ("date_signature",)},
        ),
        (
            "Documents PDF",
            {
                "fields": (
                    "pdf",
                    "latest_pdf",
                    "notice_information_pdf",
                    "dpe_pdf",
                    "grille_vetuste_pdf",
                ),
            },
        ),
        (
            "Clauses et observations",
            {
                "fields": (
                    "clauses_particulieres",
                    "observations",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Travaux",
            {
                "fields": (
                    "travaux_bailleur",
                    "travaux_locataire",
                    "honoraires_ttc",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Justificatifs",
            {
                "fields": ("justificatifs",),
                "classes": ("collapse",),
            },
        ),
    )

    def get_bien_address(self, obj):
        """Affiche l'adresse du bien"""
        return obj.location.bien.adresse

    get_bien_address.short_description = "Adresse du bien"
    get_bien_address.admin_order_field = "location__bien__adresse"

    def display_locataires(self, obj):
        """Affiche les locataires"""
        locataires = [
            f"{loc.firstName} {loc.lastName}" for loc in obj.location.locataires.all()
        ]
        return ", ".join(locataires)

    display_locataires.short_description = "Locataires"

    def get_date_debut(self, obj):
        """Affiche la date de début de la location"""
        return obj.location.date_debut

    get_date_debut.short_description = "Date début"
    get_date_debut.admin_order_field = "location__date_debut"

    def get_date_fin(self, obj):
        """Affiche la date de fin de la location"""
        return obj.location.date_fin

    get_date_fin.short_description = "Date fin"
    get_date_fin.admin_order_field = "location__date_fin"

    def get_montant_loyer(self, obj):
        """Affiche le montant du loyer"""
        if hasattr(obj.location, "rent_terms"):
            return obj.location.rent_terms.montant_loyer
        return "-"

    get_montant_loyer.short_description = "Loyer"

    def display_documents_status(self, obj):
        """Affiche le statut des documents annexes"""
        docs = []
        if obj.pdf:
            docs.append('<span style="color: green;">📄 Bail</span>')
        if obj.grille_vetuste_pdf:
            docs.append('<span style="color: green;">📋 Grille vétusté</span>')
        if obj.notice_information_pdf:
            docs.append('<span style="color: green;">📋 Notice info</span>')
        if obj.dpe_pdf:
            docs.append('<span style="color: green;">📋 DPE</span>')

        if not docs:
            return '<span style="color: gray;">Aucun document</span>'

        return format_html("<br>".join(docs))

    display_documents_status.short_description = "Documents"
    display_documents_status.allow_tags = True

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "location":
            kwargs["queryset"] = db_field.remote_field.model.objects.select_related(
                "bien"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Interface d'administration pour les documents"""

    list_display = (
        "nom_original",
        "type_document",
        "get_bail_info",
        "get_bien_info",
        "get_locataire_info",
        "get_uploade_par_info",
        "created_at",
    )
    list_filter = ("type_document", "created_at", "uploade_par")
    search_fields = (
        "nom_original",
        "bail__location__bien__adresse",
        "bien__adresse",
        "locataire__lastName",
        "locataire__firstName",
        "locataire__email",
        "uploade_par__email",
        "uploade_par__first_name",
        "uploade_par__last_name",
    )
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Relations",
            {
                "fields": ("bail", "bien", "locataire"),
                "description": "Un document peut être lié à un bail, un bien, ou un locataire",
            },
        ),
        (
            "Informations du document",
            {
                "fields": (
                    "type_document",
                    "nom_original",
                    "file",
                )
            },
        ),
        (
            "Métadonnées",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                    "uploade_par",
                ),
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")

    def get_bail_info(self, obj):
        """Affiche les informations du bail associé avec lien cliquable"""
        if obj.bail:
            url = reverse("admin:bail_bail_change", args=[obj.bail.id])
            adresse = obj.bail.location.bien.adresse
            status_badge = {
                "draft": "🟡",
                "signing": "🟠",
                "signed": "🟢",
                "cancelled": "🔴",
            }.get(obj.bail.status, "⚪")
            return format_html(
                '<a href="{}">{} {} ({})</a>',
                url,
                status_badge,
                adresse,
                obj.bail.status,
            )
        return "-"

    get_bail_info.short_description = "Bail"

    def get_bien_info(self, obj):
        """Affiche les informations du bien associé avec lien cliquable"""
        if obj.bien:
            url = reverse("admin:location_bien_change", args=[obj.bien.id])
            return format_html(
                '<a href="{}">🏠 {}</a>',
                url,
                obj.bien.adresse,
            )
        return "-"

    get_bien_info.short_description = "Bien"

    def get_locataire_info(self, obj):
        """Affiche les informations du locataire associé avec lien cliquable"""
        if obj.locataire:
            url = reverse("admin:location_locataire_change", args=[obj.locataire.id])
            nom_complet = f"{obj.locataire.firstName} {obj.locataire.lastName}"
            return format_html(
                '<a href="{}">👤 {}</a>',
                url,
                nom_complet,
            )
        return "-"

    get_locataire_info.short_description = "Locataire"

    def get_uploade_par_info(self, obj):
        """Affiche l'utilisateur qui a uploadé le document avec lien cliquable"""
        if obj.uploade_par:
            url = reverse("admin:auth_user_change", args=[obj.uploade_par.id])
            # Afficher nom/prénom si disponibles, sinon email
            display_name = (
                f"{obj.uploade_par.first_name} {obj.uploade_par.last_name}".strip()
            )
            if not display_name:
                display_name = obj.uploade_par.email

            return format_html('<a href="{}">👤 {}</a>', url, display_name)
        return "-"

    get_uploade_par_info.short_description = "Uploadé par"


@admin.register(BailSignatureRequest)
class BailSignatureRequestAdmin(admin.ModelAdmin):
    """Interface d'administration pour les demandes de signature de bail"""

    list_display = (
        "bail_display",
        "signataire_display",
        "order",
        "signed",
        "signed_at",
        "created_at",
    )

    list_filter = (
        "signed",
        "created_at",
    )

    search_fields = (
        "bailleur_signataire__email",
        "locataire__email",
        "bail__location__bien__adresse",
    )

    readonly_fields = (
        "link_token",
        "otp_generated_at",
        "signed_at",
        "created_at",
        "signature_image_link",
    )

    fieldsets = (
        (None, {"fields": ("bail", "order", "bailleur_signataire", "locataire")}),
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
        ("Métadonnées", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def bail_display(self, obj):
        """Affichage du bail"""
        return f"Bail {obj.bail.location.bien.adresse} - {obj.bail.status}"

    bail_display.short_description = "Bail"

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
