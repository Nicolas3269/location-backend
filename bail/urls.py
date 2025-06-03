from django.urls import path

from bail.progressive_views import (
    add_additional_landlord,
    finalize_bail,
    get_bail_progress,
    save_step_landlord,
    save_step_property,
    save_step_tenants,
)
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
    # Nouvelles routes pour l'approche progressive
    path("step/landlord/", save_step_landlord, name="save_step_landlord"),
    path("step/property/", save_step_property, name="save_step_property"),
    path(
        "step/additional-landlord/",
        add_additional_landlord,
        name="add_additional_landlord",
    ),
    path("step/tenants/", save_step_tenants, name="save_step_tenants"),
    path("step/finalize/", finalize_bail, name="finalize_bail"),
    path("progress/<int:bail_id>/", get_bail_progress, name="get_bail_progress"),
]
