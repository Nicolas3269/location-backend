"""
Serializers pour l'API Assurances (MRH, PNO, GLI).
"""

from rest_framework import serializers

from location.models import Location

from .models import InsurancePolicy, InsuranceProduct, InsuranceQuotation


class InsuranceFormulaSerializer(serializers.Serializer):
    """Serializer pour une formule d'assurance."""

    code = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    features = serializers.ListField(child=serializers.CharField())
    pricing_annual = serializers.FloatField()
    pricing_monthly = serializers.FloatField()


class InsuranceQuotationSerializer(serializers.ModelSerializer):
    """Serializer pour un devis d'assurance."""

    formulas = serializers.SerializerMethodField()
    is_valid = serializers.BooleanField(read_only=True)
    est_signe = serializers.BooleanField(read_only=True)
    selected_formula = serializers.SerializerMethodField()
    devis_document_url = serializers.SerializerMethodField()
    cp_document_url = serializers.SerializerMethodField()

    class Meta:
        model = InsuranceQuotation
        fields = [
            "id",
            "product",
            "location",
            "deductible",
            "effective_date",
            "formulas",
            "selected_formula_code",
            "selected_formula",
            "devis_document_url",
            "cp_document_url",
            "status",
            "is_valid",
            "est_signe",
            "created_at",
            "expires_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "expires_at",
            "is_valid",
            "est_signe",
            "status",
        ]

    def get_formulas(self, obj: InsuranceQuotation) -> list[dict]:
        """Retourne les formules enrichies."""
        return obj.formulas_data or []

    def get_selected_formula(self, obj: InsuranceQuotation) -> dict | None:
        """Retourne les données de la formule sélectionnée."""
        return obj.selected_formula

    def get_devis_document_url(self, obj: InsuranceQuotation) -> str | None:
        """Retourne l'URL du devis PDF stocké."""
        if obj.devis_document:
            return obj.devis_document.url
        return None

    def get_cp_document_url(self, obj: InsuranceQuotation) -> str | None:
        """Retourne l'URL des Conditions Particulières PDF."""
        # Priorité: latest_pdf (signé) > pdf (original)
        if obj.latest_pdf:
            return obj.latest_pdf.url
        if obj.pdf:
            return obj.pdf.url
        return None


class InsuranceQuotationRequestSerializer(serializers.Serializer):
    """Serializer pour demander un devis d'assurance."""

    location_id = serializers.UUIDField()
    product = serializers.ChoiceField(
        choices=InsuranceProduct.choices,
        default=InsuranceProduct.MRH,
    )
    deductible = serializers.IntegerField(default=170)
    effective_date = serializers.DateField(required=False, allow_null=True)

    def validate_deductible(self, value: int) -> int:
        """Valide que la franchise est 170 ou 290."""
        if value not in [170, 290]:
            raise serializers.ValidationError("La franchise doit être 170€ ou 290€")
        return value


class InsuranceSubscribeRequestSerializer(serializers.Serializer):
    """Serializer pour souscrire à une formule d'assurance."""

    quotation_id = serializers.UUIDField()
    formula_code = serializers.CharField()
    subscriber_email = serializers.EmailField(required=False)
    # Contexte pour les URLs de retour Stripe
    context = serializers.ChoiceField(
        choices=["standalone", "tenant_documents"],
        default="standalone",
        required=False,
        help_text="Contexte d'origine pour les URLs de retour",
    )
    return_token = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Token de signature pour le retour (context=tenant_documents)",
    )


class InsurancePolicySerializer(serializers.ModelSerializer):
    """Serializer pour une police d'assurance."""

    # Champs du subscriber
    subscriber_email = serializers.EmailField(source="subscriber.email", read_only=True)
    subscriber_name = serializers.SerializerMethodField()

    # Champs via quotation (utiliser select_related)
    product = serializers.CharField(source="quotation.product", read_only=True)
    product_label = serializers.SerializerMethodField()
    effective_date = serializers.DateField(
        source="quotation.effective_date", read_only=True
    )
    deductible = serializers.IntegerField(source="quotation.deductible", read_only=True)
    formula_code = serializers.CharField(
        source="quotation.selected_formula_code", read_only=True
    )
    formula_label = serializers.SerializerMethodField()
    pricing_annual = serializers.SerializerMethodField()
    pricing_monthly = serializers.SerializerMethodField()
    location_address = serializers.SerializerMethodField()

    class Meta:
        model = InsurancePolicy
        fields = [
            "id",
            "policy_number",
            "product",
            "product_label",
            "formula_label",
            "formula_code",
            "pricing_annual",
            "pricing_monthly",
            "deductible",
            "effective_date",
            "end_date",
            "status",
            "subscriber_email",
            "subscriber_name",
            "location_address",
            "created_at",
            "activated_at",
        ]
        read_only_fields = fields

    def get_subscriber_name(self, obj: InsurancePolicy) -> str:
        """Retourne le nom complet du souscripteur."""
        subscriber = obj.subscriber
        name = f"{subscriber.first_name} {subscriber.last_name}".strip()
        return name or subscriber.email

    def get_product_label(self, obj: InsurancePolicy) -> str:
        """Retourne le label du produit."""
        return obj.quotation.get_product_label()

    def get_formula_label(self, obj: InsurancePolicy) -> str:
        """Retourne le label de la formule."""
        formula = obj.quotation.selected_formula
        return formula.get("label", "") if formula else ""

    def get_pricing_annual(self, obj: InsurancePolicy) -> float:
        """Retourne le prix annuel."""
        formula = obj.quotation.selected_formula
        return formula.get("pricing_annual", 0) if formula else 0

    def get_pricing_monthly(self, obj: InsurancePolicy) -> float:
        """Retourne le prix mensuel."""
        formula = obj.quotation.selected_formula
        return formula.get("pricing_monthly", 0) if formula else 0

    def get_location_address(self, obj: InsurancePolicy) -> str | None:
        """Retourne l'adresse du bien."""
        location: Location = obj.quotation.location
        if location and location.bien and location.bien.adresse:
            return str(location.bien.adresse)
        return None


class InsuranceSubscribeResponseSerializer(serializers.Serializer):
    """Serializer pour la réponse de souscription."""

    policy_id = serializers.UUIDField()
    policy_number = serializers.CharField()
    checkout_url = serializers.URLField()
    session_id = serializers.CharField()


class InsuranceCheckoutStatusSerializer(serializers.Serializer):
    """Serializer pour le statut d'une session Checkout."""

    status = serializers.CharField()
    payment_status = serializers.CharField()
    policy_number = serializers.CharField(allow_null=True)
    product = serializers.CharField(allow_null=True)
    customer_email = serializers.EmailField(allow_null=True)
    policy = InsurancePolicySerializer(allow_null=True, required=False)


class SelectFormulaRequestSerializer(serializers.Serializer):
    """Serializer pour sélectionner une formule et générer le devis."""

    quotation_id = serializers.UUIDField()
    formula_code = serializers.CharField()
