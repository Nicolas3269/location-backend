"""
Admin pour Assurances (MRH, PNO, GLI).
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    InsurancePolicy,
    InsuranceQuotation,
    InsuranceQuotationSignatureRequest,
)


@admin.register(InsuranceQuotation)
class InsuranceQuotationAdmin(admin.ModelAdmin):
    """Admin pour les devis d'assurance."""

    list_display = [
        "id",
        "user",
        "product",
        "location",
        "deductible",
        "effective_date",
        "selected_formula_code",
        "status",
        "is_valid_display",
        "created_at",
    ]
    list_filter = ["product", "status", "deductible", "created_at"]
    search_fields = ["id", "user__email", "location__id"]
    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
        "formulas_count",
        "is_valid",
        "est_signe",
    ]
    date_hierarchy = "created_at"
    raw_id_fields = ["user", "location"]

    fieldsets = [
        (
            "Informations générales",
            {
                "fields": [
                    "id",
                    "user",
                    "product",
                    "location",
                    "status",
                ]
            },
        ),
        (
            "Tarification",
            {
                "fields": [
                    "deductible",
                    "effective_date",
                    "formulas_data",
                    "formulas_count",
                    "selected_formula_code",
                ]
            },
        ),
        (
            "Documents",
            {
                "fields": [
                    "pdf",
                    "latest_pdf",
                    "devis_document",
                    "est_signe",
                ]
            },
        ),
        (
            "Dates",
            {
                "fields": [
                    "expires_at",
                    "created_at",
                    "updated_at",
                ]
            },
        ),
    ]

    def is_valid_display(self, obj: InsuranceQuotation) -> str:
        """Affiche si le devis est valide avec couleur."""
        if obj.is_valid:
            return format_html('<span style="color: green;">✓ Valide</span>')
        return format_html('<span style="color: red;">✗ Expiré</span>')

    is_valid_display.short_description = "Validité"

    def get_queryset(self, request):
        """Optimise les requêtes avec select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related("user", "location", "location__bien")
        )


@admin.register(InsurancePolicy)
class InsurancePolicyAdmin(admin.ModelAdmin):
    """Admin pour les polices d'assurance."""

    list_display = [
        "policy_number",
        "get_product",
        "subscriber",
        "get_formula_label",
        "get_pricing_annual",
        "status_display",
        "get_effective_date",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = [
        "policy_number",
        "subscriber__email",
        "subscriber__first_name",
        "subscriber__last_name",
    ]
    readonly_fields = [
        "id",
        "policy_number",
        "created_at",
        "updated_at",
        "activated_at",
        "stripe_checkout_session_id",
        "stripe_payment_intent_id",
        "stripe_subscription_id",
        "stripe_customer_id",
        "get_product",
        "get_location",
        "get_formula_label",
        "get_formula_code",
        "get_pricing_annual",
        "get_pricing_monthly",
        "get_deductible",
        "get_effective_date",
        "get_cp_document",
    ]
    date_hierarchy = "created_at"
    raw_id_fields = ["quotation", "subscriber"]

    fieldsets = [
        (
            "Informations générales",
            {
                "fields": [
                    "id",
                    "policy_number",
                    "quotation",
                    "get_product",
                    "get_location",
                    "status",
                    "subscriber",
                ]
            },
        ),
        (
            "Formule (via devis)",
            {
                "fields": [
                    "get_formula_label",
                    "get_formula_code",
                    "get_pricing_annual",
                    "get_pricing_monthly",
                    "get_deductible",
                ]
            },
        ),
        (
            "Dates",
            {
                "fields": [
                    "get_effective_date",
                    "end_date",
                    "created_at",
                    "updated_at",
                    "activated_at",
                ]
            },
        ),
        (
            "Stripe",
            {
                "fields": [
                    "stripe_checkout_session_id",
                    "stripe_payment_intent_id",
                    "stripe_subscription_id",
                    "stripe_customer_id",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Documents",
            {
                "fields": [
                    "get_cp_document",
                    "attestation_document",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    # ===== Méthodes pour accéder aux champs via quotation =====

    @admin.display(description="Produit")
    def get_product(self, obj: InsurancePolicy) -> str:
        return obj.quotation.get_product_label()

    @admin.display(description="Location")
    def get_location(self, obj: InsurancePolicy) -> str:
        location = obj.quotation.location
        if location and location.bien and location.bien.adresse:
            return str(location.bien.adresse)
        return "-"

    @admin.display(description="Formule")
    def get_formula_label(self, obj: InsurancePolicy) -> str:
        formula = obj.quotation.selected_formula
        return formula.get("label", "-") if formula else "-"

    @admin.display(description="Code formule")
    def get_formula_code(self, obj: InsurancePolicy) -> str:
        return obj.quotation.selected_formula_code or "-"

    @admin.display(description="Prix annuel")
    def get_pricing_annual(self, obj: InsurancePolicy) -> str:
        formula = obj.quotation.selected_formula
        if formula:
            return f"{formula.get('pricing_annual', 0):.2f} €"
        return "-"

    @admin.display(description="Prix mensuel")
    def get_pricing_monthly(self, obj: InsurancePolicy) -> str:
        formula = obj.quotation.selected_formula
        if formula:
            return f"{formula.get('pricing_monthly', 0):.2f} €"
        return "-"

    @admin.display(description="Franchise")
    def get_deductible(self, obj: InsurancePolicy) -> str:
        return f"{obj.quotation.deductible} €"

    @admin.display(description="Date d'effet")
    def get_effective_date(self, obj: InsurancePolicy):
        return obj.quotation.effective_date

    @admin.display(description="CP signées")
    def get_cp_document(self, obj: InsurancePolicy) -> str:
        """Accède aux CP signées via quotation.latest_pdf."""
        cp = obj.quotation.latest_pdf
        if cp:
            return format_html('<a href="{}" target="_blank">📄 Voir</a>', cp.url)
        return "-"

    def status_display(self, obj: InsurancePolicy) -> str:
        """Affiche le statut avec couleur."""
        colors = {
            InsurancePolicy.Status.PENDING: "orange",
            InsurancePolicy.Status.ACTIVE: "green",
            InsurancePolicy.Status.CANCELLED: "red",
            InsurancePolicy.Status.EXPIRED: "gray",
        }
        color = colors.get(obj.status, "black")
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_display.short_description = "Statut"

    def get_queryset(self, request):
        """Optimise les requêtes avec select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related(
                "quotation",
                "quotation__location",
                "quotation__location__bien",
                "quotation__location__bien__adresse",
                "subscriber",
            )
        )


@admin.register(InsuranceQuotationSignatureRequest)
class InsuranceQuotationSignatureRequestAdmin(admin.ModelAdmin):
    """Admin pour les demandes de signature assurance."""

    list_display = [
        "id",
        "quotation",
        "locataire",
        "order",
        "signed",
        "signed_at",
        "created_at",
    ]
    list_filter = ["signed", "created_at"]
    search_fields = [
        "quotation__id",
        "locataire__email",
        "locataire__first_name",
        "locataire__last_name",
    ]
    readonly_fields = [
        "id",
        "link_token",
        "otp",
        "otp_generated_at",
        "signed",
        "signed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    ]
    raw_id_fields = ["quotation", "locataire"]
