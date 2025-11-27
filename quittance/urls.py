from django.urls import path

from . import views

app_name = "quittance"

urlpatterns = [
    path("generate/", views.generate_quittance_pdf, name="generate"),
    path(
        "send-email/<uuid:quittance_id>/",
        views.send_quittance_email,
        name="send-email",
    ),
]
