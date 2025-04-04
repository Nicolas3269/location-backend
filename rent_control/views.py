import json
import logging

from django.contrib.gis.geos import Point
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from rent_control.models import RentControlArea, RentPrice

logger = logging.getLogger(__name__)


def get_available_options_for_area(area):
    """
    Récupère toutes les options disponibles pour une zone donnée
    """
    # Filtre les prix associés à cette zone
    area_prices = RentPrice.objects.filter(areas=area)

    # Récupère les valeurs distinctes pour chaque attribut
    return {
        "property_types": list(
            area_prices.values_list("property_type", flat=True).distinct()
        ),
        "room_counts": list(
            area_prices.values_list("room_count", flat=True).distinct()
        ),
        "construction_periods": list(
            area_prices.values_list("construction_period", flat=True).distinct()
        ),
        "furnished_options": list(
            area_prices.values_list("furnished", flat=True).distinct()
        ),
    }


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
        return {}

    area = area_query.first()

    # Récupérer les options disponibles si demandé
    options = get_available_options_for_area(area)

    return options


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
            options = get_rent_control_info(lat, lng)

            if len(options) > 0:
                return JsonResponse(
                    {
                        "zoneTendue": True,
                        "message": "⚠️ Cette adresse est dans une zone critique.",
                        "options": options,
                    }
                )
            else:
                return JsonResponse(
                    {
                        "zoneTendue": False,
                        "message": "✅ Cette adresse est sûre.",
                        "options": options,
                    }
                )

        except Exception as e:
            logger.error(f"❌ Erreur Django: {str(e)}")
            return JsonResponse({"message": f"Erreur: {str(e)}"}, status=500)

    return JsonResponse({"message": "Méthode non autorisée"}, status=405)
