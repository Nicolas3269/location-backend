from django.urls import path

from .views import create_or_update_location

app_name = "location"

urlpatterns = [
    path("create-or-update/", create_or_update_location, name="create_or_update_location"),
]