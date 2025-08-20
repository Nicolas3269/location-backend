from django.urls import path

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
]
