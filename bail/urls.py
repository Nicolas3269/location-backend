from django.urls import path

from bail.views import (
    confirm_signature_bail,
    generate_bail_pdf,
    get_signature_request,
)

urlpatterns = [
    path("generate-bail/", generate_bail_pdf, name="generate_bail_pdf"),
    path("confirm-signature/", confirm_signature_bail, name="confirm_signature_bail"),
    path(
        "get-signature-request/<uuid:token>/",
        get_signature_request,
        name="get_signature_request",
    ),
]
