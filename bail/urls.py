from django.urls import path

from bail.avenant_views import (
    cancel_signature_avenant,
    confirm_signature_avenant,
    create_avenant,
    delete_avenant_document,
    generate_avenant_pdf,
    get_avenant_requirements,
    get_avenant_signature_request,
    resend_otp_avenant,
    upload_avenant_document,
)
from bail.views import (
    cancel_signature_bail,
    confirm_signature_bail,
    delete_document,
    generate_bail_pdf,
    generate_notice_information_pdf,
    get_bail_bien_id,
    get_bien_baux,
    get_bien_detail,
    get_company_data,
    get_rent_prices,
    get_signature_request,
    resend_otp_bail,
    upload_document,
    upload_locataire_document,
)

urlpatterns = [
    path("get-rent-prices/", get_rent_prices, name="get_rent_prices"),
    path("generate-bail/", generate_bail_pdf, name="generate_bail_pdf"),
    # La route create-partial est maintenant dans quittance/urls.py
    path("bail/<str:bail_id>/bien-id/", get_bail_bien_id, name="get_bail_bien_id"),
    path("bien/detail/<uuid:bien_id>/", get_bien_detail, name="get_bien_detail"),
    path("bien/<uuid:bien_id>/baux/", get_bien_baux, name="get_bien_baux"),
    path(
        "generate-notice-information/",
        generate_notice_information_pdf,
        name="generate_notice_information_pdf",
    ),
    path("upload-document/", upload_document, name="upload_document"),
    path("get-company-data/", get_company_data, name="get_company_data"),
    path("documents/<uuid:document_id>/", delete_document, name="delete_document"),
    path("confirm-signature/", confirm_signature_bail, name="confirm_signature_bail"),
    path(
        "cancel-signature/<uuid:bail_id>/",
        cancel_signature_bail,
        name="cancel_signature_bail",
    ),
    path(
        "get-signature-request/<uuid:token>/",
        get_signature_request,
        name="get_signature_request",
    ),
    path("resend-otp/", resend_otp_bail, name="resend_otp_bail"),
    path(
        "upload-locataire-document/",
        upload_locataire_document,
        name="upload_locataire_document",
    ),
    # Avenant routes
    path(
        "avenant/<uuid:bail_id>/requirements/",
        get_avenant_requirements,
        name="get_avenant_requirements",
    ),
    path(
        "avenant/<uuid:bail_id>/create/",
        create_avenant,
        name="create_avenant",
    ),
    path(
        "avenant/<uuid:avenant_id>/pdf/",
        generate_avenant_pdf,
        name="generate_avenant_pdf",
    ),
    # Avenant signature routes
    path(
        "avenant/get-signature-request/<uuid:token>/",
        get_avenant_signature_request,
        name="get_avenant_signature_request",
    ),
    path(
        "avenant/confirm-signature/",
        confirm_signature_avenant,
        name="confirm_signature_avenant",
    ),
    path(
        "avenant/cancel-signature/<uuid:avenant_id>/",
        cancel_signature_avenant,
        name="cancel_signature_avenant",
    ),
    path(
        "avenant/resend-otp/",
        resend_otp_avenant,
        name="resend_otp_avenant",
    ),
    # Avenant documents routes
    path(
        "avenant/upload-document/",
        upload_avenant_document,
        name="upload_avenant_document",
    ),
    path(
        "avenant/documents/<uuid:document_id>/",
        delete_avenant_document,
        name="delete_avenant_document",
    ),
]
