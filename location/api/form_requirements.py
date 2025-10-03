"""
API endpoints pour les requirements de formulaires adaptatifs.

Architecture: 2 routes séparées
- Route publique (standalone): GET /forms/{form_type}/requirements/
- Route authentifiée (contextualisée): GET /forms/{form_type}/requirements/authenticated/
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..services import FormOrchestrator


@api_view(["GET"])
def get_form_requirements(request, form_type):
    """
    Route publique - mode standalone (new)

    GET /api/forms/{form_type}/requirements/

    Query params:
        - location_id: ID de la location existante pour édition DRAFT (optionnel)
        - type_etat_lieux: Type d'état des lieux ('entree'|'sortie') si form_type == 'etat_lieux' (optionnel)

    Args:
        form_type: Type de formulaire ('bail', 'quittance', 'etat_lieux')

    Returns:
        JSON avec formData, location_id, requiredSteps, lockedSteps, etc.
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

    # Récupérer les paramètres
    location_id = request.query_params.get("location_id")
    type_etat_lieux = request.query_params.get("type_etat_lieux")

    # Utiliser l'orchestrateur en mode "new" (standalone)
    orchestrator = FormOrchestrator()

    try:
        requirements = orchestrator.get_form_requirements(
            form_type=form_type,
            location_id=location_id,
            context_mode="new",
            context_source_id=None,
            type_etat_lieux=type_etat_lieux,
            user=None
        )

        # Vérifier si une erreur a été retournée
        if "error" in requirements:
            return Response(
                requirements,
                status=status.HTTP_404_NOT_FOUND
                if "not found" in requirements["error"].lower()
                else status.HTTP_400_BAD_REQUEST,
            )

        return Response(requirements, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_form_requirements_authenticated(request, form_type):
    """
    Route authentifiée - modes from_bailleur/from_bien/from_location

    GET /api/forms/{form_type}/requirements/authenticated/

    Query params (required):
        - context_mode: "from_bailleur" | "from_bien" | "from_location"
        - context_source_id: UUID de la source (bien_id ou location_id selon context_mode)
        - type_etat_lieux: Type d'état des lieux ('entree'|'sortie') si form_type == 'etat_lieux'

    Optional:
        - location_id: ID de la location pour édition/correction (optionnel)

    Args:
        form_type: Type de formulaire ('bail', 'quittance', 'etat_lieux')

    Returns:
        JSON avec formData pré-rempli, lockedSteps, requiredSteps, etc.
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

    # Récupérer et valider les paramètres
    context_mode = request.query_params.get("context_mode")
    context_source_id = request.query_params.get("context_source_id")
    location_id = request.query_params.get("location_id")
    type_etat_lieux = request.query_params.get("type_etat_lieux")

    # Validation du context_mode
    valid_context_modes = ["from_bailleur", "from_bien", "from_location"]
    if context_mode not in valid_context_modes:
        return Response(
            {
                "error": f"Invalid context_mode. Must be one of: {', '.join(valid_context_modes)}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # context_source_id est requis pour les modes authentifiés
    if not context_source_id:
        return Response(
            {"error": "context_source_id is required for authenticated routes"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Utiliser l'orchestrateur avec le context_mode approprié
    orchestrator = FormOrchestrator()

    try:
        requirements = orchestrator.get_form_requirements(
            form_type=form_type,
            location_id=location_id,
            context_mode=context_mode,
            context_source_id=context_source_id,
            type_etat_lieux=type_etat_lieux,
            user=request.user
        )

        # Vérifier si une erreur a été retournée
        if "error" in requirements:
            return Response(
                requirements,
                status=status.HTTP_404_NOT_FOUND
                if "not found" in requirements["error"].lower()
                else status.HTTP_400_BAD_REQUEST,
            )

        return Response(requirements, status=status.HTTP_200_OK)

    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_form_requirements_authenticated: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
