from django.urls import path

from bail.views import generate_bail_pdf, sign_bail

urlpatterns = [
    path("generate-bail/", generate_bail_pdf),
    path("sign/", sign_bail),
]
