from django.urls import path

from etat_lieux.views import (
    confirm_signature_etat_lieux,
    generate_etat_lieux_pdf,
    generate_grille_vetuste_pdf,
    get_etat_lieux_signature_request,
    get_or_create_pieces,
    resend_otp_etat_lieux,
)

app_name = "etat_lieux"

urlpatterns = [
    path(
        "pieces/<int:bien_id>/",
        get_or_create_pieces,
        name="get_or_create_pieces",
    ),
    path(
        "generate-etat-lieux/",
        generate_etat_lieux_pdf,
        name="generate_etat_lieux_pdf",
    ),
    path(
        "generate-grille-vetuste/",
        generate_grille_vetuste_pdf,
        name="generate_grille_vetuste_pdf",
    ),
    # Routes pour la signature
    path(
        "signature/<str:token>/",
        get_etat_lieux_signature_request,
        name="get_etat_lieux_signature_request",
    ),
    path(
        "confirm-signature/",
        confirm_signature_etat_lieux,
        name="confirm_signature_etat_lieux",
    ),
    path(
        "resend-otp/",
        resend_otp_etat_lieux,
        name="resend_otp_etat_lieux",
    ),
]
