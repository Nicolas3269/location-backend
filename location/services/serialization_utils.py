"""
Utilitaires pour la sérialisation des modèles Location.
Centralise la logique de sérialisation pour éviter les duplications.
IMPORTANT: Utilise les serializers READ pour retourner format PREFILL/WRITE nested.
"""

from typing import Any, Dict

from bail.models import Bail
from location.models import Bien, Location
from signature.document_status import DocumentStatus


def serialize_location_with_bail(
    location: Location, user=None
) -> Dict[str, Any]:
    """
    Sérialise une location avec son bail actif en format PREFILL/WRITE nested.

    Utilise LocationReadSerializer (source de vérité) + ajoute métadonnées bail.

    Args:
        location: Instance de Location
        user: User pour prioriser bailleur connecté (optionnel)

    Returns:
        Dict avec structure nested (dates, modalites_financieres, etc.) + métadonnées bail
    """
    # Utiliser LocationReadSerializer pour structure nested
    from location.serializers.read import LocationReadSerializer

    serializer = LocationReadSerializer(location, context={"user": user})
    data = serializer.data

    # Récupérer le bail le plus récent
    bail = Bail.objects.filter(location=location).order_by("-created_at").first()

    # Ajouter métadonnées spécifiques au bail
    if bail:
        if bail.status == DocumentStatus.SIGNED:
            data["bail_actif_id"] = str(bail.id)
        else:
            data["bail_actif_id"] = None

        data["pdf_url"] = bail.pdf.url if bail.pdf else None
        data["latest_pdf_url"] = bail.latest_pdf.url if bail.latest_pdf else None
        data["status"] = bail.get_status_display()
        data["signatures_completes"] = bail.status == DocumentStatus.SIGNED
    else:
        data["bail_actif_id"] = None
        data["pdf_url"] = None
        data["latest_pdf_url"] = None
        data["status"] = "Brouillon"
        data["signatures_completes"] = False

    data["nombre_baux"] = Bail.objects.filter(location=location).count()

    return data


def serialize_bien_with_stats(bien: Bien) -> Dict[str, Any]:
    """
    Sérialise un bien avec ses statistiques en format PREFILL/WRITE nested.

    Utilise BienReadSerializer + restructure_bien_to_nested_format.

    Args:
        bien: Instance de Bien

    Returns:
        Dict avec structure nested (localisation, caracteristiques, etc.) + stats
    """
    from location.serializers.helpers import restructure_bien_to_nested_format
    from location.serializers.read import BienReadSerializer

    # Sérialiser le bien en format nested
    serializer = BienReadSerializer(bien)
    bien_data = restructure_bien_to_nested_format(
        serializer.data, calculate_zone_from_gps=False
    )

    # Ajouter statistiques
    bien_data["nombre_baux"] = Location.objects.filter(bien=bien).count()
    bien_data["baux_actifs"] = Bail.objects.filter(
        location__bien=bien, status=DocumentStatus.SIGNED
    ).count()

    return bien_data


def serialize_bien_with_locations(bien: Bien, user=None) -> Dict[str, Any]:
    """
    Sérialise un bien avec toutes ses locations détaillées en format nested.

    Args:
        bien: Instance de Bien
        user: User pour prioriser bailleur connecté (optionnel)

    Returns:
        Dict avec bien nested + liste de locations nested
    """
    locations = Location.objects.filter(bien=bien).prefetch_related(
        "locataires", "rent_terms"
    )
    locations_data = [
        serialize_location_with_bail(loc, user=user) for loc in locations
    ]

    return {
        "bien": serialize_bien_with_stats(bien),
        "locations": locations_data,
    }
