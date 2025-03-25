from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
from algo.encadrement_loyer.utils import geocode_address
from django.contrib.gis.geos import Point
from rent_control.models import RentControlZone


logger = logging.getLogger(__name__)

def get_rent_control_info(lat, lng):
    # Create a point from the coordinates
    point = Point(float(lng), float(lat), srid=4326)
    
    # Query using the geodb database
    year = 2021
    room_count = 2
    furnished = False
    construction_period = "Avant 1946"

    # Ajouter les filtres secondaires si spécifiés
    query = RentControlZone.objects.filter(geometry__contains=point)
    if year:
        query = query.filter(reference_year=year)
    if room_count:
        query = query.filter(room_count=room_count)
    if furnished is not None:  # Booléen peut être False
        query = query.filter(furnished=furnished)
    if construction_period:
        query = query.filter(construction_period=construction_period)
    
    if query.exists():
        zone = query.first()
        return {
            'region': zone.region,
            'zone': zone.zone,
            'reference_price': zone.reference_price,
            'min_price': zone.min_price,
            'max_price': zone.max_price,
            'apartment_type': zone.apartment_type,
            'room_count': zone.room_count,
            'construction_period': zone.construction_period,
            'furnished': zone.furnished
        }
    return False


@csrf_exempt
def check_zone(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            address = data.get("address", "")

            logger.info(f"🔍 Adresse reçue : {address}")

            if not address:
                return JsonResponse({"message": "Adresse requise"}, status=400)

            # Ici, on appelle une fonction existante `is_critical_zone(address)`
            # is_critical=False
            lat, lng = geocode_address(address)
            zone_tendue = get_rent_control_info(lat, lng)

            if zone_tendue:
                return JsonResponse(
                    {   "zoneTendue": zone_tendue,
                        "message": "⚠️ Cette adresse est dans une zone critique."}
                )
            else:
                return JsonResponse({"zoneTendue": zone_tendue,
                        "message": "✅ Cette adresse est sûre."})

        except Exception as e:
            logger.error(f"❌ Erreur Django: {str(e)}")
            return JsonResponse({"message": f"Erreur: {str(e)}"}, status=500)

    return JsonResponse({"message": "Méthode non autorisée"}, status=405)

