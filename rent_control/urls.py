from django.urls import path

from rent_control.views import check_zone

urlpatterns = [
    path("check-zone/", check_zone),
]
