from django.urls import path

from bail.views import (
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
    save_draft,
    upload_document,
)
urlpatterns = [
    path("get-rent-prices/", get_rent_prices, name="get_rent_prices"),
    path("generate-bail/", generate_bail_pdf, name="generate_bail_pdf"),
    # La route create-partial est maintenant dans quittance/urls.py
    path("save-draft/", save_draft, name="save_draft"),
    path("bail/<str:bail_id>/bien-id/", get_bail_bien_id, name="get_bail_bien_id"),
    path("bien/detail/<int:bien_id>/", get_bien_detail, name="get_bien_detail"),
    path("bien/<int:bien_id>/baux/", get_bien_baux, name="get_bien_baux"),
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
        "get-signature-request/<uuid:token>/",
        get_signature_request,
        name="get_signature_request",
    ),
    path("resend-otp/", resend_otp_bail, name="resend_otp_bail"),
]
