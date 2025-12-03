from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Avenant,
    AvenantSignatureRequest,
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


class AvenantInline(admin.TabularInline):
    """Inline pour afficher les avenants d'un bail"""

    model = Avenant
    extra = 0
    fields = ("numero", "motifs", "status", "identifiant_fiscal", "created_at")
    readonly_fields = ("numero", "created_at")
    show_change_link = True


class AvenantSignatureRequestInline(admin.TabularInline):
    """Inline pour les demandes de signature d'un avenant"""

    model = AvenantSignatureRequest
    extra = 0
    fields = (
        "order",
        "bailleur_signataire",
        "locataire",
        "mandataire",
        "signed",
        "signed_at",
    )
    readonly_fields = ("link_token", "signed_at")


@admin.register(Avenant)
class AvenantAdmin(admin.ModelAdmin):
    """Interface d'administration pour les avenants"""

    list_display = (
        "numero_display",
        "get_bail_info",
        "get_motifs_display",
        "status",
        "identifiant_fiscal",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "bail__location__bien__adresse",
        "bail__location__locataires__lastName",
        "bail__location__locataires__firstName",
        "identifiant_fiscal",
    )
    date_hierarchy = "created_at"
    inlines = [AvenantSignatureRequestInline]
    readonly_fields = ("numero", "created_at", "updated_at")

    fieldsets = (
        (
            "Bail associé",
            {"fields": ("bail", "numero")},
        ),
        (
            "Contenu de l'avenant",
            {
                "fields": (
                    "motifs",
                    "identifiant_fiscal",
                )
            },
        ),
        (
            "État",
            {"fields": ("status",)},
        ),
        (
            "Document PDF",
            {"fields": ("pdf", "latest_pdf")},
        ),
        (
            "Métadonnées",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def numero_display(self, obj):
        """Affiche le numéro d'avenant"""
        return f"Avenant n°{obj.numero}"

    numero_display.short_description = "Numéro"

    def get_bail_info(self, obj):
        """Affiche les informations du bail avec lien cliquable"""
        url = reverse("admin:bail_bail_change", args=[obj.bail.id])
        adresse = obj.bail.location.bien.adresse
        return format_html('<a href="{}">{}</a>', url, adresse)

    get_bail_info.short_description = "Bail"

    def get_motifs_display(self, obj):
        """Affiche les motifs de l'avenant"""
        motif_labels = {
            "identifiant_fiscal": "📋 Identifiant fiscal",
            "diagnostics_ddt": "📄 Diagnostics DDT",
            "permis_de_louer": "🏠 Permis de louer",
        }
        motifs = obj.motifs or []
        labels = [motif_labels.get(m, m) for m in motifs]
        return ", ".join(labels) if labels else "-"

    get_motifs_display.short_description = "Motifs"


@admin.register(AvenantSignatureRequest)
class AvenantSignatureRequestAdmin(admin.ModelAdmin):
    """Interface d'administration pour les demandes de signature d'avenant"""

    list_display = (
        "avenant_display",
        "signataire_display",
        "order",
        "signed",
        "signed_at",
        "created_at",
    )

    list_filter = ("signed", "created_at")

    search_fields = (
        "bailleur_signataire__email",
        "locataire__email",
        "avenant__bail__location__bien__adresse",
    )

    readonly_fields = (
        "link_token",
        "otp_generated_at",
        "signed_at",
        "created_at",
        "signature_image_link",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "avenant",
                    "order",
                    "bailleur_signataire",
                    "locataire",
                    "mandataire",
                )
            },
        ),
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

    def avenant_display(self, obj):
        """Affichage de l'avenant"""
        return (
            f"Avenant n°{obj.avenant.numero} - {obj.avenant.bail.location.bien.adresse}"
        )

    avenant_display.short_description = "Avenant"

    def signataire_display(self, obj):
        """Affichage du signataire"""
        if obj.mandataire:
            return f"Mandataire: {obj.mandataire}"
        elif obj.bailleur_signataire:
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
        "created_at",
    )
    list_filter = ("status", "cancelled_at")
    search_fields = (
        "location__bien__adresse",
        "location__locataires__lastName",
        "location__locataires__firstName",
    )
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    inlines = [DocumentInline, BailSignatureRequestInline, AvenantInline]
    readonly_fields = (
        "date_signature_display",
        "est_signe_display",
        "notice_information_link",
    )

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
            {"fields": ("date_signature_display", "est_signe_display")},
        ),
        (
            "Documents PDF",
            {
                "fields": (
                    "pdf",
                    "latest_pdf",
                    "notice_information_link",
                ),
                "description": (
                    "Notice d'information est un document statique. "
                    "Les diagnostics sont gérés via les Documents annexes."
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
        # Notice est toujours disponible (statique)
        docs.append('<span style="color: green;">📋 Notice info</span>')

        if not docs:
            return '<span style="color: gray;">Aucun document</span>'

        return format_html("<br>".join(docs))

    display_documents_status.short_description = "Documents"
    display_documents_status.allow_tags = True

    def date_signature_display(self, obj):
        """Affiche la date de signature complète (property calculée)"""
        if obj.date_signature:
            return obj.date_signature.strftime("%d/%m/%Y %H:%M")
        return "Non signé"

    date_signature_display.short_description = "Date signature complète"

    def est_signe_display(self, obj):
        """Affiche si le bail est complètement signé (property calculée)"""
        if obj.est_signe:
            return format_html('<span style="color: green;">✓ Signé</span>')
        return format_html('<span style="color: orange;">⏳ En attente</span>')

    est_signe_display.short_description = "État signature"

    def notice_information_link(self, obj):
        """Affiche un lien vers la notice d'information (document statique)"""
        # On a besoin de la request pour construire l'URL absolue
        # Mais dans l'admin, on n'a pas accès à la request dans les méthodes
        # On va utiliser une URL relative
        from django.urls import reverse

        url = reverse(
            "serve_static_pdf_iframe",
            kwargs={"file_path": "bails/notice_information.pdf"},
        )
        return format_html(
            '<a href="{}" target="_blank">📋 Notice d\'information (statique)</a>', url
        )

    notice_information_link.short_description = "Notice d'information"

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
