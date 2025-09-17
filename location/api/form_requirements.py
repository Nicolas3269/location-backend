"""
API endpoints pour les requirements de formulaires adaptatifs.
"""

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..services import FormOrchestrator


@api_view(["GET"])
def get_form_requirements(request, form_type):
    """
    Retourne les requirements pour un formulaire donné.

    GET /api/forms/{form_type}/requirements
    Query params:
        - location_id: ID de la location existante (optionnel)
        - type_etat_lieux: Type d'état des lieux si form_type == 'etat_lieux' (optionnel)

    Args:
        form_type: Type de formulaire ('bail', 'quittance', 'etat_lieux')

    Returns:
        JSON avec formData, is_new, steps, données pré-remplies
    """

    # Valider le type de formulaire
    valid_form_types = ["bail", "quittance", "etat_lieux"]
    if form_type not in valid_form_types:
        return Response(
            {
                "error": f"Invalid form type. Must be one of: {', '.join(valid_form_types)}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Récupérer les paramètres depuis les query params
    location_id = request.query_params.get("location_id")
    type_etat_lieux = request.query_params.get("type_etat_lieux")

    # Utiliser l'orchestrateur pour obtenir les requirements
    orchestrator = FormOrchestrator()

    try:
        requirements = orchestrator.get_form_requirements(
            form_type, location_id, type_etat_lieux=type_etat_lieux
        )

        # Vérifier si une erreur a été retournée
        if "error" in requirements:
            return Response(
                requirements,
                status=status.HTTP_404_NOT_FOUND
                if requirements["error"] == "Location not found"
                else status.HTTP_400_BAD_REQUEST,
            )

        return Response(requirements, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
