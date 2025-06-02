from django.urls import path

from bail.views import (
    confirm_signature_bail,
    generate_bail_pdf,
    generate_grille_vetuste_pdf,
    generate_notice_information_pdf,
    get_signature_request,
    save_draft,
    upload_dpe_diagnostic,
)

urlpatterns = [
    path("generate-bail/", generate_bail_pdf, name="generate_bail_pdf"),
    path("save-draft/", save_draft, name="save_draft"),
    path(
        "generate-grille-vetuste/",
        generate_grille_vetuste_pdf,
        name="generate_grille_vetuste_pdf",
    ),
    path(
        "generate-notice-information/",
        generate_notice_information_pdf,
        name="generate_notice_information_pdf",
    ),
    path("upload-dpe/", upload_dpe_diagnostic, name="upload_dpe_diagnostic"),
    path("confirm-signature/", confirm_signature_bail, name="confirm_signature_bail"),
    path(
        "get-signature-request/<uuid:token>/",
        get_signature_request,
        name="get_signature_request",
    ),
]
