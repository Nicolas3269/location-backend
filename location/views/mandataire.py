"""
Vues pour l'espace mandataire
"""

import logging
from collections import defaultdict

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# Compter les bails actifs
from location.models import Bailleur, Bien, Location
from location.services.access_utils import (
    get_user_mandataires,
    user_has_bailleur_access_via_mandataire,
    user_has_bien_access_via_mandataire,
    user_has_mandataire_role,
)
from location.services.serialization_utils import (
    serialize_bien_with_locations,
    serialize_bien_with_stats,
)

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_mandataire_bailleurs(request):
    """
    Récupère la liste des bailleurs gérés par le mandataire connecté.

    Retourne un tableau de bailleurs avec leurs biens.
    """
    user_email = request.user.email

    # Vérifier que l'utilisateur est mandataire
    if not user_has_mandataire_role(user_email):
        return Response(
            {"success": False, "error": "Aucun mandataire trouvé pour cet utilisateur"},
            status=404,
        )

    # Récupérer les mandataires de l'utilisateur
    mandataires = get_user_mandataires(user_email)

    # Récupérer toutes les locations gérées par ces mandataires
    locations = Location.objects.filter(mandataire__in=mandataires).select_related(
        "bien"
    )

    # Grouper les biens par bailleur
    # Structure: {bailleur_id: {bailleur_info, biens: []}}
    bailleurs_dict = defaultdict(lambda: {"bailleur": None, "biens": []})

    for location in locations:
        bien: Bien = location.bien

        # Un bien peut avoir plusieurs bailleurs (copropriété, indivision)
        for bailleur_obj in bien.bailleurs.all():
            bailleur: Bailleur = bailleur_obj
            bailleur_id = str(bailleur.id)

            # Si c'est la première fois qu'on rencontre ce bailleur
            if bailleurs_dict[bailleur_id]["bailleur"] is None:
                bailleurs_dict[bailleur_id]["bailleur"] = {
                    "id": bailleur_id,
                    "nom": bailleur.full_name,
                    "type": bailleur.bailleur_type.value,  # Enum → string
                }

            # Ajouter le bien (si pas déjà présent)
            bien_id = str(bien.id)
            if not any(
                b["id"] == bien_id for b in bailleurs_dict[bailleur_id]["biens"]
            ):
                # Utiliser le helper de sérialisation
                bailleurs_dict[bailleur_id]["biens"].append(
                    serialize_bien_with_stats(bien)
                )

    # Convertir le dictionnaire en liste
    bailleurs_list = []
    for bailleur_data in bailleurs_dict.values():
        bailleurs_list.append(
            {
                "id": bailleur_data["bailleur"]["id"],
                "nom": bailleur_data["bailleur"]["nom"],
                "type": bailleur_data["bailleur"]["type"],
                "nombre_biens": len(bailleur_data["biens"]),
                "biens": bailleur_data["biens"],
            }
        )

    # Trier par nom
    bailleurs_list.sort(key=lambda x: x["nom"])

    return Response({"success": True, "bailleurs": bailleurs_list})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_mandataire_bailleur_detail(request, bailleur_id):
    """
    Récupère les détails d'un bailleur spécifique avec ses biens.

    Vérifie que le mandataire connecté a bien accès à ce bailleur.
    """
    user_email = request.user.email

    # Vérifier que l'utilisateur est mandataire
    if not user_has_mandataire_role(user_email):
        raise ValueError("Aucun mandataire trouvé pour cet utilisateur")

    # Récupérer le bailleur
    try:
        bailleur = Bailleur.objects.get(id=bailleur_id)
    except Bailleur.DoesNotExist:
        raise ValueError("Le bailleur spécifié est introuvable")

    # Vérifier l'accès
    if not user_has_bailleur_access_via_mandataire(bailleur, user_email):
        raise ValueError("Vous n'avez pas accès à ce bailleur")

    # Récupérer les biens gérés par ce mandataire pour ce bailleur
    mandataires = get_user_mandataires(user_email)
    biens_geres = Bien.objects.filter(
        bailleurs=bailleur, locations__mandataire__in=mandataires
    ).distinct()

    # Sérialiser les biens avec leurs statistiques
    biens_list = [serialize_bien_with_stats(bien) for bien in biens_geres]

    return Response(
        {
            "success": True,
            "bailleur": {
                "id": str(bailleur.id),
                "nom": bailleur.full_name,
                "type": bailleur.bailleur_type.value,  # Enum → string
            },
            "biens": biens_list,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_mandataire_bien_detail(request, bien_id):
    """
    Récupère les détails d'un bien géré par le mandataire en format PREFILL/WRITE nested.

    Retourne bien + locations en structure nested (source de vérité).
    Vérifie que le mandataire connecté gère bien ce bien.
    """
    user_email = request.user.email

    # Vérifier que l'utilisateur est mandataire
    if not user_has_mandataire_role(user_email):
        raise ValueError("Aucun mandataire trouvé pour cet utilisateur")

    # Récupérer le bien
    try:
        bien = Bien.objects.get(id=bien_id)
    except Bien.DoesNotExist:
        raise ValueError("Le bien spécifié est introuvable")

    # Vérifier l'accès
    if not user_has_bien_access_via_mandataire(bien, user_email):
        raise ValueError("Vous n'avez pas accès à ce bien")

    # Utiliser le helper de sérialisation (retourne format nested)
    data = serialize_bien_with_locations(bien, user=request.user)

    return Response(
        {
            "success": True,
            **data,  # bien et locations en format nested
        }
    )
