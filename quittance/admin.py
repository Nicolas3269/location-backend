from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Quittance


@admin.register(Quittance)
class QuittanceAdmin(admin.ModelAdmin):
    """Administration des quittances de loyer"""

    list_display = [
        "id_short",
        "location_info",
        "periode",
        "montant_loyer",
        "montant_charges",
        "montant_total",
        "date_paiement",
        "pdf_link",
        "created_at",
    ]

    list_filter = [
        "annee",
        "mois",
        "created_at",
        "date_paiement",
    ]

    search_fields = [
        "location__bien__adresse",
        "location__locataires__lastName",
        "location__locataires__firstName",
        "location__bien__bailleurs__personne__lastName",
        "location__bien__bailleurs__personne__firstName",
        "location__bien__bailleurs__societe__raison_sociale",
    ]

    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
        "pdf_preview",
        "periode_display",
        "locataires_display",
        "montant_loyer",
        "montant_charges",
        "montant_total",
    ]

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "id",
                    "location",
                    "locataires_display",
                    "periode_display",
                    "date_paiement",
                )
            },
        ),
        (
            "Montants",
            {
                "fields": (
                    "montant_loyer",
                    "montant_charges",
                    "montant_total",
                ),
                "description": "Ces montants sont récupérés automatiquement depuis les conditions financières de la location",
            },
        ),
        (
            "Fichier PDF",
            {
                "fields": (
                    "pdf",
                    "pdf_preview",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def id_short(self, obj):
        """Affiche l'UUID raccourci avec lien vers le détail"""
        detail_url = reverse("admin:quittance_quittance_change", args=[obj.pk])
        return format_html(
            '<a href="{}" title="Voir le détail">{}</a>',
            detail_url,
            str(obj.id)[:8]
        )

    id_short.short_description = "ID"
    id_short.admin_order_field = "id"

    def location_info(self, obj):
        """Affiche les informations de la location avec lien"""
        location_url = reverse("admin:location_location_change", args=[obj.location.pk])
        locataires = ", ".join(
            [f"{loc.firstName} {loc.lastName}" for loc in obj.location.locataires.all()]
        )

        # Chercher s'il y a un bail actif (SIGNING ou SIGNED) pour cette location
        from signature.document_status import DocumentStatus
        bail = obj.location.bails.filter(
            status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED]
        ).first()
        bail_link = ""
        if bail:
            bail_url = reverse("admin:bail_bail_change", args=[bail.pk])
            bail_link = f'<br><small><a href="{bail_url}" title="Voir le bail">📋 Bail actif</a></small>'

        return format_html(
            '<a href="{}" title="Voir la location">{}</a><br><small>{}</small>{}',
            location_url,
            obj.location.bien.adresse,
            locataires,
            bail_link,
        )

    location_info.short_description = "Location / Locataires"
    location_info.admin_order_field = "location__bien__adresse"

    def periode(self, obj):
        """Affiche la période formatée"""
        return f"{obj.mois.title()} {obj.annee}"

    periode.short_description = "Période"
    periode.admin_order_field = "annee"

    def periode_display(self, obj):
        """Affiche la période en lecture seule"""
        return f"{obj.mois.title()} {obj.annee}"

    periode_display.short_description = "Période"

    def locataires_display(self, obj):
        """Affiche les locataires liés à cette quittance"""
        locataires = obj.locataires.all()
        if locataires.exists():
            # Si des locataires sont spécifiquement liés à la quittance
            locataires_list = [f"{loc.firstName} {loc.lastName}" for loc in locataires]
            return format_html("<br>".join(locataires_list))
        else:
            # Sinon, afficher tous les locataires de la location
            location_locataires = obj.location.locataires.all()
            locataires_list = [f"{loc.firstName} {loc.lastName}" for loc in location_locataires]
            return format_html("<br>".join(locataires_list) + "<br><small>(Tous les locataires de la location)</small>")

    locataires_display.short_description = "Locataire(s) concerné(s)"

    def pdf_link(self, obj):
        """Lien vers le PDF"""
        if obj.pdf:
            return format_html(
                '<a href="{}" target="_blank">📄 Télécharger</a>', obj.pdf.url
            )
        return "❌ Aucun PDF"

    pdf_link.short_description = "PDF"

    def pdf_preview(self, obj):
        """Prévisualisation du PDF"""
        if obj.pdf:
            return format_html(
                '<iframe src="{}" width="100%" height="400px" '
                'style="border: 1px solid #ddd;"></iframe>',
                obj.pdf.url,
            )
        return "Aucun PDF disponible"

    pdf_preview.short_description = "Prévisualisation PDF"

    def get_queryset(self, request):
        """Optimise les requêtes avec select_related et prefetch_related"""
        queryset = super().get_queryset(request)
        return queryset.select_related(
            "location",
            "location__bien",
            "location__mandataire",
        ).prefetch_related(
            "location__locataires",
            "location__bien__bailleurs",
            "location__bien__bailleurs__personne",
            "location__bien__bailleurs__societe",
        )

    def has_add_permission(self, request):
        """Empêche la création manuelle de quittances via l'admin"""
        return False

    def has_change_permission(self, request, obj=None):
        """Autorise seulement la consultation/modification pour les superutilisateurs"""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Autorise la suppression seulement aux superutilisateurs"""
        return request.user.is_superuser
