import json
import logging

from django.conf import settings
from django.contrib.gis.geos import Point
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit

from algo.encadrement_loyer.grenoble.main import ACCEPTED_ZONE, WHITELIST_ZONES
from algo.encadrement_loyer.montpellier.main import (
    ACCEPTED_ZONE as ACCEPTED_ZONE_MONTPELLIER,
    WHITELIST_ZONES as WHITELIST_ZONES_MONTPELLIER,
)
from rent_control.choices import Region
from rent_control.management.commands.constants import DEFAULT_YEAR
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
    year=DEFAULT_YEAR,
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
        return {}, None

    if area_query.filter(region=Region.GRENOBLE).exists():
        # Pour Grenoble, chercher d'abord s'il y au moins une zone ACCEPTED
        accepted_areas = area_query.filter(zone_id=ACCEPTED_ZONE)
        if accepted_areas.exists():
            # S'il y a une zone ACCEPTED, prendre la première zone whitelistée
            whitelist_areas = area_query.filter(zone_id__in=WHITELIST_ZONES)
            if whitelist_areas.exists():
                area = whitelist_areas.first()
            else:
                return {}, None
        else:
            return {}, None
    elif area_query.filter(region=Region.MONTPELLIER).exists():
        # Pour Montpellier, même logique que Grenoble
        accepted_areas = area_query.filter(zone_id=ACCEPTED_ZONE_MONTPELLIER)
        if accepted_areas.exists():
            # S'il y a une zone ACCEPTED, prendre la première zone whitelistée
            whitelist_areas = area_query.filter(
                zone_id__in=WHITELIST_ZONES_MONTPELLIER
            )
            if whitelist_areas.exists():
                area = whitelist_areas.first()
            else:
                return {}, None
        else:
            return {}, None
    else:
        area = area_query.first()

    # Récupérer les options disponibles si demandé
    options = get_available_options_for_area(area)

    return options, area


@csrf_exempt
@ratelimit(key="ip", rate="5/m", block=True) if not settings.DEBUG else lambda x: x
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

            # Récupérer les options disponibles ET l'area
            options, area = get_rent_control_info(lat, lng)

            is_zone_tendue = len(options) > 0 and area is not None

            if is_zone_tendue:
                return JsonResponse(
                    {
                        "zoneTendue": True,
                        "message": "⚠️ Cette adresse est dans une zone critique.",
                        "options": options,
                        "areaId": area.id,
                    }
                )
            else:
                return JsonResponse(
                    {
                        "zoneTendue": False,
                        "message": "✅ Cette adresse est sûre.",
                        "options": {},
                        "areaId": None,
                    }
                )

        except Exception as e:
            logger.error(f"❌ Erreur Django: {str(e)}")
            return JsonResponse({"message": f"Erreur: {str(e)}"}, status=500)

    return JsonResponse({"message": "Méthode non autorisée"}, status=405)
