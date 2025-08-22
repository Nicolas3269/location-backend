from django.urls import path

from .api.form_requirements import get_form_requirements
from .views import create_or_update_location, get_bien_locations, get_location_documents

app_name = "location"

urlpatterns = [
    path(
        "create-or-update/", create_or_update_location, name="create_or_update_location"
    ),
    path(
        "bien/<int:bien_id>/locations/", get_bien_locations, name="get_bien_locations"
    ),
    path(
        "<uuid:location_id>/documents/",
        get_location_documents,
        name="get_location_documents",
    ),
    # API pour les formulaires adaptatifs
    path(
        "forms/<str:form_type>/requirements/",
        get_form_requirements,
        name="get_form_requirements",
    ),
]
