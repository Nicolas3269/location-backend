from django.urls import path

from .api.form_requirements import (
    get_form_requirements,
    get_form_requirements_authenticated,
)
from .views import (
    create_or_update_location,
    get_bien_locations,
    get_location_detail,
    get_location_documents,
    get_locataire_locations,
    cancel_bail,
    cancel_etat_lieux,
    cancel_quittance,
)
from .views_mandataire import (
    get_mandataire_bailleurs,
    get_mandataire_bailleur_detail,
    get_mandataire_bien_detail,
)

app_name = "location"

urlpatterns = [
    path(
        "create-or-update/", create_or_update_location, name="create_or_update_location"
    ),
    path(
        "bien/<uuid:bien_id>/locations/", get_bien_locations, name="get_bien_locations"
    ),
    path(
        "mes-locations/", get_locataire_locations, name="get_locataire_locations"
    ),
    path(
        "<uuid:location_id>/",
        get_location_detail,
        name="get_location_detail",
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
    path(
        "forms/<str:form_type>/requirements/authenticated/",
        get_form_requirements_authenticated,
        name="get_form_requirements_authenticated",
    ),
    # Annulation de documents
    path(
        "bails/<uuid:bail_id>/cancel/",
        cancel_bail,
        name="cancel_bail",
    ),
    path(
        "etats-lieux/<uuid:etat_lieux_id>/cancel/",
        cancel_etat_lieux,
        name="cancel_etat_lieux",
    ),
    path(
        "quittances/<uuid:quittance_id>/cancel/",
        cancel_quittance,
        name="cancel_quittance",
    ),
    # Endpoints mandataire
    path(
        "mandataire/bailleurs/",
        get_mandataire_bailleurs,
        name="get_mandataire_bailleurs",
    ),
    path(
        "mandataire/bailleurs/<uuid:bailleur_id>/",
        get_mandataire_bailleur_detail,
        name="get_mandataire_bailleur_detail",
    ),
    path(
        "mandataire/biens/<uuid:bien_id>/",
        get_mandataire_bien_detail,
        name="get_mandataire_bien_detail",
    ),
]
