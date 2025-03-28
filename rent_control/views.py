import json
import logging

from django.contrib.gis.geos import Point
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from rent_control.models import RentControlArea, RentPrice

logger = logging.getLogger(__name__)


def get_rent_control_info(
    lat,
    lng,
    property_type="appartement",
    room_count=2,
    construction_period="avant 1946",
    furnished=False,
    year=2024,
):
    """
    Trouve les informations d'encadrement des loyers pour une localisation et
    des caractéristiques de logement spécifiques.
    """
    # Créer un point à partir des coordonnées
    point = Point(float(lng), float(lat), srid=4326)

    # D'abord trouver la zone qui contient le point
    area_query = RentControlArea.objects.filter(
        geometry__contains=point, reference_year=year
    )

    if not area_query.exists():
        return False

    area = area_query.first()

    # Puis trouver le prix correspondant aux caractéristiques
    price_query = RentPrice.objects.filter(
        area=area,
        property_type=property_type,
        room_count=str(room_count),
        construction_period=construction_period,
        furnished=furnished,
    )

    if not price_query.exists():
        # Si aucune correspondance exacte, chercher la plus proche
        price_query = RentPrice.objects.filter(area=area)
        # Vous pourriez ici implémenter une logique de "meilleure correspondance"

    if price_query.exists():
        price = price_query.first()

        return {
            "region": area.region,
            "zone": area.zone_name,
            "reference_price": price.reference_price,
            "min_price": price.min_price,
            "max_price": price.max_price,
            "apartment_type": price.property_type,
            "room_count": price.room_count,
            "construction_period": price.construction_period,
            "furnished": price.furnished,
            "reference_year": area.reference_year,
        }

    # Si aucun prix trouvé, retourner les informations de base de la zone
    return {
        "region": area.region,
        "zone": area.zone_name,
        "reference_year": area.reference_year,
        "message": "Prix non disponibles pour ces caractéristiques",
    }


@csrf_exempt
def check_zone(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            address = data.get("address", "")
            lat = data.get("lat", "")
            lng = data.get("lng", "")

            logger.info(f"🔍 Adresse reçue : {address}")

            if not address:
                return JsonResponse({"message": "Adresse requise"}, status=400)

            # Ici, on appelle une fonction existante `is_critical_zone(address)`
            zone_tendue = get_rent_control_info(lat, lng)

            if zone_tendue:
                return JsonResponse(
                    {
                        "zoneTendue": zone_tendue,
                        "message": "⚠️ Cette adresse est dans une zone critique.",
                    }
                )
            else:
                return JsonResponse(
                    {"zoneTendue": zone_tendue, "message": "✅ Cette adresse est sûre."}
                )

        except Exception as e:
            logger.error(f"❌ Erreur Django: {str(e)}")
            return JsonResponse({"message": f"Erreur: {str(e)}"}, status=500)

    return JsonResponse({"message": "Méthode non autorisée"}, status=405)
