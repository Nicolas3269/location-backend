# progressive_views.py
"""
Vues pour l'approche progressive de création de bail
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import BailSpecificites, Bien, Locataire, Proprietaire
from .serializers import (
    BailSpecificitesSerializer,
    BienSerializer,
    LocataireSerializer,
    ProprietaireSerializer,
)

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_step_landlord(request):
    """Créer/mettre à jour le propriétaire principal"""
    try:
        proprietaire_id = request.data.get("proprietaire_id")

        if proprietaire_id:
            try:
                proprietaire = Proprietaire.objects.get(id=proprietaire_id)
                serializer = ProprietaireSerializer(proprietaire, data=request.data)
            except Proprietaire.DoesNotExist:
                return Response(
                    {"error": "Propriétaire non trouvé"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            serializer = ProprietaireSerializer(data=request.data)

        if serializer.is_valid():
            proprietaire = serializer.save()
            return Response(
                {
                    "proprietaire_id": proprietaire.id,
                    "message": "Propriétaire sauvegardé avec succès",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("Erreur lors de la sauvegarde du propriétaire")
        return Response(
            {"error": f"Erreur lors de la sauvegarde: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_step_property(request):
    """Créer le bien et l'associer au propriétaire"""
    try:
        proprietaire_id = request.data.get("proprietaire_id")
        bien_id = request.data.get("bien_id")

        if not proprietaire_id:
            return Response(
                {"error": "proprietaire_id est requis"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            proprietaire = Proprietaire.objects.get(id=proprietaire_id)
        except Proprietaire.DoesNotExist:
            return Response(
                {"error": "Propriétaire non trouvé"}, status=status.HTTP_404_NOT_FOUND
            )

        if bien_id:
            try:
                bien = Bien.objects.get(id=bien_id)
                serializer = BienSerializer(bien, data=request.data)
            except Bien.DoesNotExist:
                return Response(
                    {"error": "Bien non trouvé"}, status=status.HTTP_404_NOT_FOUND
                )
        else:
            serializer = BienSerializer(data=request.data)

        if serializer.is_valid():
            bien = serializer.save()
            if proprietaire not in bien.proprietaires.all():
                bien.proprietaires.add(proprietaire)

            return Response(
                {
                    "bien_id": bien.id,
                    "message": "Bien sauvegardé avec succès",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("Erreur lors de la sauvegarde du bien")
        return Response(
            {"error": f"Erreur lors de la sauvegarde: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_additional_landlord(request):
    """Ajouter un propriétaire supplémentaire au bien"""
    try:
        bien_id = request.data.get("bien_id")

        if not bien_id:
            return Response(
                {"error": "bien_id est requis"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            bien = Bien.objects.get(id=bien_id)
        except Bien.DoesNotExist:
            return Response(
                {"error": "Bien non trouvé"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = ProprietaireSerializer(data=request.data)
        if serializer.is_valid():
            proprietaire = serializer.save()
            bien.proprietaires.add(proprietaire)

            return Response(
                {
                    "proprietaire_id": proprietaire.id,
                    "message": "Propriétaire supplémentaire ajouté avec succès",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("Erreur lors de l'ajout du propriétaire supplémentaire")
        return Response(
            {"error": f"Erreur lors de l'ajout: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_step_tenants(request):
    """Créer ou mettre à jour les locataires"""
    try:
        locataires_data = request.data.get("locataires", [])
        existing_locataires_ids = request.data.get("existing_locataires_ids", [])

        if not locataires_data:
            return Response(
                {"error": "Au moins un locataire est requis"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_locataires = []
        updated_locataires = []

        for i, locataire_data in enumerate(locataires_data):
            # Si on a un ID existant, on met à jour
            if i < len(existing_locataires_ids) and existing_locataires_ids[i]:
                try:
                    locataire = Locataire.objects.get(id=existing_locataires_ids[i])
                    serializer = LocataireSerializer(locataire, data=locataire_data)
                    if serializer.is_valid():
                        locataire = serializer.save()
                        updated_locataires.append(locataire.id)
                    else:
                        return Response(
                            serializer.errors, status=status.HTTP_400_BAD_REQUEST
                        )
                except Locataire.DoesNotExist:
                    return Response(
                        {"error": f"Locataire {existing_locataires_ids[i]} non trouvé"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            else:
                # Créer un nouveau locataire
                serializer = LocataireSerializer(data=locataire_data)
                if serializer.is_valid():
                    locataire = serializer.save()
                    created_locataires.append(locataire.id)
                else:
                    return Response(
                        serializer.errors, status=status.HTTP_400_BAD_REQUEST
                    )

        all_locataires_ids = updated_locataires + created_locataires

        return Response(
            {
                "locataires_ids": all_locataires_ids,
                "created_count": len(created_locataires),
                "updated_count": len(updated_locataires),
                "message": (
                    f"{len(created_locataires)} locataire(s) créé(s), "
                    f"{len(updated_locataires)} mis à jour"
                ),
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception("Erreur lors de la sauvegarde des locataires")
        return Response(
            {"error": f"Erreur lors de la sauvegarde: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def finalize_bail(request):
    """Créer ou mettre à jour le BailSpecificites final"""
    try:
        bien_id = request.data.get("bien_id")
        locataires_ids = request.data.get("locataires_ids", [])
        bail_id = request.data.get("bail_id")

        if not bien_id:
            return Response(
                {"error": "bien_id est requis"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not locataires_ids:
            return Response(
                {"error": "Au moins un locataire est requis"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            bien = Bien.objects.get(id=bien_id)
            locataires = Locataire.objects.filter(id__in=locataires_ids)

            if len(locataires) != len(locataires_ids):
                return Response(
                    {"error": "Certains locataires sont introuvables"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        except Bien.DoesNotExist:
            return Response(
                {"error": "Bien non trouvé"}, status=status.HTTP_404_NOT_FOUND
            )

        # Préparer les données du bail
        bail_data = request.data.copy()
        bail_data["bien"] = bien.id

        # Créer ou mettre à jour le bail
        if bail_id:
            try:
                bail = BailSpecificites.objects.get(id=bail_id)
                serializer = BailSpecificitesSerializer(bail, data=bail_data)
            except BailSpecificites.DoesNotExist:
                return Response(
                    {"error": "Bail non trouvé"}, status=status.HTTP_404_NOT_FOUND
                )
        else:
            serializer = BailSpecificitesSerializer(data=bail_data)

        if serializer.is_valid():
            bail = serializer.save()
            bail.locataires.set(locataires)

            return Response(
                {
                    "bail_id": bail.id,
                    "message": "Bail finalisé avec succès",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("Erreur lors de la finalisation du bail")
        return Response(
            {"error": f"Erreur lors de la finalisation: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_bail_progress(request, bail_id):
    """Récupérer les informations de progression d'un bail"""
    try:
        bail = (
            BailSpecificites.objects.select_related("bien")
            .prefetch_related("bien__proprietaires", "locataires")
            .get(id=bail_id)
        )

        proprietaires_data = ProprietaireSerializer(
            bail.bien.proprietaires.all(), many=True
        ).data
        locataires_data = LocataireSerializer(bail.locataires.all(), many=True).data
        bien_data = BienSerializer(bail.bien).data
        bail_data = BailSpecificitesSerializer(bail).data

        return Response(
            {
                "bail": bail_data,
                "bien": bien_data,
                "proprietaires": proprietaires_data,
                "locataires": locataires_data,
                "message": "Données récupérées avec succès",
            },
            status=status.HTTP_200_OK,
        )

    except BailSpecificites.DoesNotExist:
        return Response({"error": "Bail non trouvé"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Erreur lors de la récupération des données")
        return Response(
            {"error": f"Erreur lors de la récupération: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
