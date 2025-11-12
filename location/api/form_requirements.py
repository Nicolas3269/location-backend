"""
API endpoints pour les requirements de formulaires adaptatifs.

Architecture: 2 routes avec FormState (types discriminants)
- Route publique (standalone): GET /forms/{form_type}/requirements/
- Route authentifiée (mode extend): GET /forms/{form_type}/requirements/authenticated/
"""

from uuid import UUID

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..services import FormOrchestrator
from ..services.user_role_detector import get_user_role_for_context
from ..types.form_state import (
    CreateFormState,
    EditFormState,
    ExtendFormState,
    PrefillFormState,
    RenewFormState,
)


@api_view(["GET"])
def get_form_requirements(request, form_type):
    """
    Route publique - mode create uniquement (nouveaux formulaires).

    GET /api/forms/{form_type}/requirements/

    Query params:
        - type_etat_lieux: Type d'état des lieux si form_type == 'etat_lieux'

    Note: Pour éditer un document existant, utiliser la route authentifiée.

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

    # SÉCURITÉ : Interdire location_id sur route publique
    if location_id:
        return Response(
            {
                "error": (
                    "Édition de documents existants nécessite authentification. "
                    "Utilisez la route /authenticated/."
                )
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # Route publique = toujours CreateFormState
    form_state = CreateFormState()

    # Utiliser l'orchestrateur avec le FormState approprié
    orchestrator = FormOrchestrator()

    try:
        requirements = orchestrator.get_form_requirements(
            form_type=form_type,
            form_state=form_state,
            type_etat_lieux=type_etat_lieux,
            user=None,
            request=request
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
        logger.error(f"Error in get_form_requirements: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_form_requirements_authenticated(request, form_type):
    """
    Route authentifiée - modes edit/renew/extend.

    GET /api/forms/{form_type}/requirements/authenticated/

    Query params:
        - location_id: Pour edit/renew d'un document existant
        - context_mode: "from_bailleur" | "from_bien" | "from_location" |
                        "location_actuelle" | "location_ancienne" |
                        "location_nouvelle"
        - context_source_id: UUID source si context_mode fourni
        - type_etat_lieux: Type état des lieux si form_type == 'etat_lieux'
        - lock_fields: Champs à lock (mode extend), ignoré en mode prefill

    Args:
        form_type: Type de formulaire

    Returns:
        JSON avec formData pré-rempli, lockedSteps, requiredSteps, etc.
    """

    # Valider le type de formulaire
    valid_form_types = ["bail", "quittance", "etat_lieux", "tenant_documents"]
    if form_type not in valid_form_types:
        return Response(
            {
                "error": f"Invalid form type. "
                f"Must be one of: {', '.join(valid_form_types)}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Récupérer les paramètres
    location_id = request.query_params.get("location_id")
    context_mode = request.query_params.get("context_mode")
    context_source_id = request.query_params.get("context_source_id")
    type_etat_lieux = request.query_params.get("type_etat_lieux")

    # Cas 1: Édition/Renouvellement (location_id fourni)
    # Inclut tenant_documents (locataire authentifié via magic link)
    if location_id:
        # Pour tenant_documents, on skip le conflict resolver
        # (pas de concept de DRAFT/SIGNED pour documents locataires)
        if form_type == "tenant_documents":
            form_state = EditFormState(location_id=UUID(location_id))
        else:
            # Bail/Quittance/EDL : vérifier si edit vs renew
            from ..services.form_conflict_resolver import FormConflictResolver

            resolver = FormConflictResolver()
            conflict_result = resolver.resolve_location_id(
                form_type, location_id, type_etat_lieux
            )

            if conflict_result["has_been_renewed"]:
                # Document signé → RenewFormState
                form_state = RenewFormState(previous_location_id=UUID(location_id))
            else:
                # Document DRAFT → EditFormState
                form_state = EditFormState(location_id=UUID(location_id))

    # Cas 2: Mode extend/prefill (créer depuis source existante)
    elif context_mode and context_source_id:
        valid_modes = [
            "from_bailleur", "from_bien", "from_location",
            "location_actuelle", "location_ancienne", "location_nouvelle"
        ]
        if context_mode not in valid_modes:
            return Response(
                {
                    "error": f"Invalid context_mode. "
                    f"Must be one of: {', '.join(valid_modes)}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Modes Espace Bailleur
        if context_mode in ["location_actuelle", "location_ancienne"]:
            # Mode Extend: Lock SI source a docs signés
            lock_fields_str = request.query_params.get("lock_fields", "")
            lock_fields = [
                f.strip() for f in lock_fields_str.split(",") if f.strip()
            ]
            if not lock_fields:
                lock_fields = [
                    "bien", "bailleur", "locataires", "rent_terms"
                ]

            form_state = ExtendFormState(
                source_type="location",
                source_id=UUID(context_source_id),
                lock_fields=lock_fields,
            )

        elif context_mode == "location_nouvelle":
            # Mode Prefill: Suggestions modifiables (pas de lock)
            # sourceType pourrait être bien/bailleur/location
            # Pour l'instant on assume location
            form_state = PrefillFormState(
                source_type="location",
                source_id=UUID(context_source_id),
            )

        # Legacy modes (from_location, from_bien, from_bailleur)
        else:
            if context_mode == "from_location":
                # Legacy: from_location = Extend avec lock
                form_state = ExtendFormState(
                    source_type="location",
                    source_id=UUID(context_source_id),
                    lock_fields=[
                        "bien", "bailleur", "locataires", "rent_terms"
                    ],
                )
            else:
                # Legacy: from_bien/from_bailleur = Prefill sans lock
                source_type_map = {
                    "from_bien": "bien",
                    "from_bailleur": "bailleur",
                }
                source_type = source_type_map[context_mode]

                form_state = PrefillFormState(
                    source_type=source_type,  # type: ignore
                    source_id=UUID(context_source_id),
                )

    # Cas 3: Aucun paramètre → CreateFormState (nouveau formulaire)
    else:
        form_state = CreateFormState()

    # Déterminer le user_role basé sur les paramètres de la requête
    # AVANT d'appeler l'orchestrateur (plus propre et direct)
    user_role_location_id = None
    user_role_bien_id = None
    user_role_bailleur_id = None

    # Cas 1: location_id fourni directement (edit/renew)
    if location_id:
        user_role_location_id = location_id

    # Cas 2: context_mode et context_source_id (extend/prefill)
    elif context_mode and context_source_id:
        if context_mode in ["from_location", "location_actuelle", "location_ancienne"]:
            user_role_location_id = context_source_id
        elif context_mode == "from_bien":
            user_role_bien_id = context_source_id
        elif context_mode == "from_bailleur":
            user_role_bailleur_id = context_source_id
        elif context_mode == "location_nouvelle":
            # Pour location_nouvelle, on assume que source peut être
            # location/bien/bailleur. On passe context_source_id comme
            # location_id par défaut
            user_role_location_id = context_source_id

    # Déterminer le user_role
    user_role = get_user_role_for_context(
        user=request.user,
        location_id=user_role_location_id,
        bien_id=user_role_bien_id,
        bailleur_id=user_role_bailleur_id,
    )

    # Utiliser l'orchestrateur avec ExtendFormState
    orchestrator = FormOrchestrator()

    try:
        requirements = orchestrator.get_form_requirements(
            form_type=form_type,
            form_state=form_state,
            type_etat_lieux=type_etat_lieux,
            user=request.user,
            request=request
        )

        # Vérifier si une erreur a été retournée
        if "error" in requirements:
            return Response(
                requirements,
                status=status.HTTP_404_NOT_FOUND
                if "not found" in requirements["error"].lower()
                else status.HTTP_400_BAD_REQUEST,
            )

        # Injecter user_role dans formData si déterminé
        if user_role:
            if "formData" not in requirements:
                requirements["formData"] = {}
            requirements["formData"]["user_role"] = user_role

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
