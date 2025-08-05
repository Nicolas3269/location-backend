from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import Quittance


@admin.register(Quittance)
class QuittanceAdmin(admin.ModelAdmin):
    """Administration des quittances de loyer"""

    list_display = [
        "bail_info",
        "periode",
        "montant_loyer",
        "date_paiement",
        "pdf_link",
        "date_creation",
    ]

    list_filter = [
        "annee",
        "mois",
        "date_creation",
        "date_paiement",
        "bail__bien__type_bien",
    ]

    search_fields = [
        "bail__bien__adresse",
        "bail__locataires__nom",
        "bail__locataires__prenom",
        "bail__bien__bailleurs__personne__nom",
        "bail__bien__bailleurs__personne__prenom",
        "bail__bien__bailleurs__societe__raison_sociale",
    ]

    readonly_fields = [
        "id",
        "date_creation",
        "date_modification",
        "pdf_preview",
        "periode_display",
    ]

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "id",
                    "bail",
                    "periode_display",
                    "montant_loyer",
                    "date_paiement",
                )
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
                    "date_creation",
                    "date_modification",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def bail_info(self, obj):
        """Affiche les informations du bail avec lien vers la quittance"""
        quittance_url = reverse("admin:quittance_quittance_change", args=[obj.pk])
        bail_url = reverse("admin:bail_bailspecificites_change", args=[obj.bail.pk])
        return format_html(
            '<a href="{}" title="Voir la quittance">{}</a><br>'
            '<small>{}</small><br>'
            '<small><a href="{}" title="Voir le bail">📋 Bail</a></small>',
            quittance_url,
            obj.bail.bien.adresse,
            ", ".join([f"{loc.prenom} {loc.nom}" for loc in obj.bail.locataires.all()]),
            bail_url,
        )

    bail_info.short_description = "Bail / Locataires"
    bail_info.admin_order_field = "bail__bien__adresse"

    def periode(self, obj):
        """Affiche la période formatée"""
        return f"{obj.mois.title()} {obj.annee}"

    periode.short_description = "Période"
    periode.admin_order_field = "annee"

    def periode_display(self, obj):
        """Affiche la période en lecture seule"""
        return f"{obj.mois.title()} {obj.annee}"

    periode_display.short_description = "Période"

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
            "bail",
            "bail__bien",
            "bail__mandataire",
        ).prefetch_related(
            "bail__locataires",
            "bail__bien__bailleurs",
            "bail__bien__bailleurs__personne",
            "bail__bien__bailleurs__societe",
        )

    def has_add_permission(self, request):
        """Empêche la création manuelle de quittances"""
        return False

    def has_change_permission(self, request, obj=None):
        """Autorise seulement la consultation"""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Autorise la suppression seulement aux superutilisateurs"""
        return request.user.is_superuser
