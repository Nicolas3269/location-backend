from django.urls import path

from bail.views import generate_bail_pdf

urlpatterns = [
    path("generate-bail/", generate_bail_pdf),
]
