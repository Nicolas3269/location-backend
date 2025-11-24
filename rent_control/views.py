import json
import logging

import requests
from django.conf import settings
from django.contrib.gis.geos import Point
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit

from algo.encadrement_loyer.grenoble.main import ACCEPTED_ZONE, WHITELIST_ZONES
from algo.encadrement_loyer.montpellier.main import (
    ACCEPTED_ZONE as ACCEPTED_ZONE_MONTPELLIER,
)
from algo.encadrement_loyer.montpellier.main import (
    WHITELIST_ZONES as WHITELIST_ZONES_MONTPELLIER,
)
from rent_control.choices import Region
from rent_control.management.commands.constants import DEFAULT_YEAR
from rent_control.models import (
    PermisDeLouer,
    RentControlArea,
    RentPrice,
    ZoneTendue,
    ZoneTendueTouristique,
    ZoneTresTendue,
)

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


def check_zone_status_via_ban(lat, lng):
    """
    Utilise l'API BAN pour récupérer le code INSEE et vérifier si c'est une zone tendue
    et si elle requiert un permis de louer
    https://adresse.data.gouv.fr/outils/api-doc/adresse#reverse
    Pour garantir un usage équitable de ce service très sollicité,
    une limite d'usage est appliquée. Elle est de 50 appels/IP/seconde.
    """
    try:
        # Appel à l'API BAN pour géocodage inverse
        ban_url = "https://api-adresse.data.gouv.fr/reverse/"
        params = {
            "lon": lng,
            "lat": lat,
            "limit": 5,
        }

        response = requests.get(ban_url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data.get("features"):
            # Récupérer le premier résultat
            feature = data["features"][0]
            properties = feature.get("properties", {})
            citycode = properties.get("citycode")
            city = properties.get("city", "")

            if citycode or city:
                # Vérifier si ce code INSEE ou cette commune est dans les zones tendues
                # Recherche par code INSEE OU par nom de commune (exact, insensible)
                zone_tendue_exists = ZoneTendue.objects.filter(
                    Q(code_insee=citycode) | Q(communes__iexact=city)
                ).exists()

                # Vérifier si cette ville est dans les zones très tendues (Zone A bis)
                # Recherche par nom de commune (comparaison exacte, insensible à la casse)
                zone_tres_tendue_exists = ZoneTresTendue.objects.filter(
                    Q(commune__iexact=city)
                ).exists()

                # Vérifier si cette ville est dans les zones tendues touristiques
                # Recherche par code INSEE OU par nom de commune
                zone_tendue_touristique_exists = ZoneTendueTouristique.objects.filter(
                    Q(code_insee=citycode) | Q(commune__iexact=city)
                ).exists()

                # Vérifier si cette ville nécessite un permis de louer
                # Recherche par nom de ville (comparaison exacte, insensible à la casse)
                permis_louer_exists = PermisDeLouer.objects.filter(
                    Q(villes__iexact=city)
                ).exists()

                return {
                    "is_zone_tendue": zone_tendue_exists,
                    "is_zone_tres_tendue": zone_tres_tendue_exists,
                    "is_zone_tendue_touristique": zone_tendue_touristique_exists,
                    "is_permis_de_louer": permis_louer_exists,
                    "citycode": citycode,
                    "city": city,
                    "postcode": properties.get("postcode", ""),
                }

        return {
            "is_zone_tendue": False,
            "is_zone_tres_tendue": False,
            "is_zone_tendue_touristique": False,
            "is_permis_de_louer": False,
            "error": "Aucune commune trouvée pour ces coordonnées",
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur lors de l'appel à l'API BAN: {str(e)}")
        return {
            "is_zone_tendue": False,
            "is_zone_tres_tendue": False,
            "is_zone_tendue_touristique": False,
            "is_permis_de_louer": False,
            "error": f"Erreur API BAN: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Erreur lors de la vérification zone tendue/permis: {str(e)}")
        return {
            "is_zone_tendue": False,
            "is_zone_tres_tendue": False,
            "is_zone_tendue_touristique": False,
            "is_permis_de_louer": False,
            "error": f"Erreur: {str(e)}",
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
            whitelist_areas = area_query.filter(zone_id__in=WHITELIST_ZONES_MONTPELLIER)
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

            # Vérifier si c'est une zone tendue et si elle nécessite un permis de louer
            ban_result = check_zone_status_via_ban(lat, lng)

            is_zone_tendue = ban_result["is_zone_tendue"]
            is_zone_tres_tendue = ban_result["is_zone_tres_tendue"]
            is_zone_tendue_touristique = ban_result["is_zone_tendue_touristique"]
            is_permis_de_louer = ban_result["is_permis_de_louer"]

            return JsonResponse(
                {
                    "zoneTendue": is_zone_tendue,
                    "zoneTresTendue": is_zone_tres_tendue,
                    "zoneTendueTouristique": is_zone_tendue_touristique,
                    "permisDeLouer": is_permis_de_louer,
                    "options": options,
                    "areaId": area.id if area else None,
                }
            )

        except Exception as e:
            logger.error(f"❌ Erreur Django: {str(e)}")
            return JsonResponse({"message": f"Erreur: {str(e)}"}, status=500)

    return JsonResponse({"message": "Méthode non autorisée"}, status=405)
