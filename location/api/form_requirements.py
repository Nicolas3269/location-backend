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

    GET /api/forms/{form_type}/requirements?location_id=xxx

    Args:
        form_type: Type de formulaire ('bail', 'quittance', 'etat_lieux')
        location_id (query param): ID de la location existante (optionnel)

    Returns:
        JSON avec les steps, données pré-remplies, et contexte
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

    # Récupérer l'ID de location depuis les query params
    location_id = request.query_params.get("location_id")

    # Utiliser l'orchestrateur pour obtenir les requirements
    orchestrator = FormOrchestrator()

    try:
        requirements = orchestrator.get_form_requirements(form_type, location_id)

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
