from django.urls import path
from .views import check_zone

urlpatterns = [
    path("check-zone/", check_zone),
]
