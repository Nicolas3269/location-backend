from django.urls import path

from etat_lieux.views import generate_etat_lieux_pdf

app_name = "etat_lieux"

urlpatterns = [
    path(
        "generate-etat-lieux/",
        generate_etat_lieux_pdf,
        name="generate_etat_lieux_pdf",
    ),
]
