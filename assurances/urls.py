"""
URLs pour l'API Assurances (MRH, PNO, GLI).
"""

from django.urls import path

from . import views, webhooks

app_name = "assurances"

urlpatterns = [
    # === Devis ===
    path("quotation/", views.get_quotation, name="quotation"),
    path("quotation/<uuid:quotation_id>/", views.get_quotation_by_id, name="quotation-detail"),
    path("quotation/<uuid:quotation_id>/cancel-signature/", views.cancel_quotation_signature, name="cancel-signature"),
    path("select-formula/", views.select_formula, name="select-formula"),
    # === Signature (génériques) ===
    path(
        "signing/<uuid:token>/",
        views.get_signature_request,
        name="get-signature-request",
    ),
    path("signing/confirm/", views.confirm_signature, name="confirm-signature"),
    path("signing/resend-otp/", views.resend_otp, name="resend-otp"),
    # === Souscription & Paiement ===
    path("subscribe/", views.subscribe, name="subscribe"),
    path("checkout-status/", views.checkout_status, name="checkout-status"),
    # === Polices ===
    path("policies/", views.list_policies, name="policies-list"),
    path("policies/<uuid:policy_id>/", views.get_policy, name="policy-detail"),
    path(
        "policies/by-number/<str:policy_number>/",
        views.get_policy_by_number,
        name="policy-by-number",
    ),
    # === Documents ===
    path("documents/cgv/", views.get_cgv_document, name="documents-cgv"),
    path("documents/dipa/", views.get_dipa_document, name="documents-dipa"),
    path("documents/der/", views.get_der_document, name="documents-der"),
    path("documents/devis/", views.get_devis_document, name="documents-devis"),
    # === Webhook ===
    path("webhooks/stripe/", webhooks.stripe_webhook, name="stripe-webhook"),
]
