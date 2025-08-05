from django.urls import path

from bail.views import generate_grille_vetuste_pdf
from etat_lieux.views import generate_etat_lieux_pdf

app_name = "etat_lieux"

urlpatterns = [
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
]
