from django.db import IntegrityError
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import NotificationRequest
from .serializers import (
    BulkNotificationRequestSerializer,
    NotificationRequestListSerializer,
    NotificationRequestSerializer,
)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])  # Pas besoin d'auth pour s'inscrire
def create_notification_request(request):
    """
    Créer une demande de notification pour une fonctionnalité

    POST /api/notifications/request/
    {
        "email": "user@example.com",
        "feature": "quittance",  // ou "etat_des_lieux"
        "role": "proprietaire",
        "additional_info": {"properties_count": "2-5"},
        "wants_updates": true
    }
    """
    serializer = NotificationRequestSerializer(data=request.data)

    if serializer.is_valid():
        try:
            notification_request = serializer.save()

            # Retourner les données avec l'ID
            response_serializer = NotificationRequestListSerializer(
                notification_request
            )

            return Response(
                {
                    "success": True,
                    "message": "Demande de notification enregistrée avec succès",
                    "data": response_serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

        except IntegrityError:
            # Cas où l'utilisateur a déjà fait une demande pour cette feature
            return Response(
                {
                    "success": False,
                    "message": "Vous êtes déjà inscrit pour cette fonctionnalité",
                    "error": "ALREADY_REGISTERED",
                },
                status=status.HTTP_409_CONFLICT,
            )

    return Response(
        {"success": False, "message": "Données invalides", "errors": serializer.errors},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def create_bulk_notification_request(request):
    """
    Créer plusieurs demandes de notification en une fois.

    POST /api/notifications/bulk/
    {
        "email": "user@example.com",
        "features": ["assurance", "demenagement", "energie"],
        "role": "proprietaire"
    }

    Retourne:
    - created: liste des features nouvellement créées
    - already_registered: liste des features où l'email était déjà inscrit
    """
    serializer = BulkNotificationRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {"success": False, "message": "Données invalides", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = serializer.validated_data["email"]
    features = serializer.validated_data["features"]
    role = serializer.validated_data["role"]

    created = []
    already_registered = []

    for feature in features:
        try:
            NotificationRequest.objects.create(
                email=email,
                feature=feature,
                role=role,
            )
            created.append(feature)
        except IntegrityError:
            already_registered.append(feature)

    # Déterminer le statut de réponse
    if not created and already_registered:
        # Toutes les features étaient déjà enregistrées
        return Response(
            {
                "success": True,
                "message": "Vous êtes déjà inscrit pour tous ces services",
                "created": [],
                "already_registered": already_registered,
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {
            "success": True,
            "message": f"{len(created)} inscription(s) enregistrée(s)",
            "created": created,
            "already_registered": already_registered,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])  # Admin seulement
def list_notification_requests(request):
    """
    Lister toutes les demandes de notification (admin only)

    GET /api/notifications/requests/
    Paramètres optionnels:
    - feature: filtrer par fonctionnalité
    - notified: filtrer par statut de notification
    """
    queryset = NotificationRequest.objects.all()

    # Filtres optionnels
    feature = request.GET.get("feature")
    if feature:
        queryset = queryset.filter(feature=feature)

    notified = request.GET.get("notified")
    if notified is not None:
        is_notified = notified.lower() in ["true", "1", "yes"]
        queryset = queryset.filter(notified=is_notified)

    serializer = NotificationRequestListSerializer(queryset, many=True)

    return Response(
        {"success": True, "count": queryset.count(), "data": serializer.data}
    )


@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])  # Admin seulement
def mark_notifications_sent(request):
    """
    Marquer des notifications comme envoyées

    POST /api/notifications/mark-sent/
    {
        "feature": "quittance",  // optionnel, tous si non spécifié
        "emails": ["email1@example.com", "email2@example.com"]  // optionnel
    }
    """
    feature = request.data.get("feature")
    emails = request.data.get("emails", [])

    queryset = NotificationRequest.objects.filter(notified=False)

    if feature:
        queryset = queryset.filter(feature=feature)

    if emails:
        queryset = queryset.filter(email__in=emails)

    from django.utils import timezone

    updated_count = queryset.update(notified=True, notified_at=timezone.now())

    return Response(
        {
            "success": True,
            "message": f"{updated_count} notifications marquées comme envoyées",
            "updated_count": updated_count,
        }
    )
