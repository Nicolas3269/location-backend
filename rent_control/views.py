# Example function to get rent control info for a location
from django.contrib.gis.geos import Point
from rent_control.models import RentControlZone

def get_rent_control_info(lat, lng):
    # Create a point from the coordinates
    point = Point(float(lng), float(lat), srid=4326)
    
    # Query using the geodb database
    zones = RentControlZone.objects.using('geodb').filter(geometry__contains=point)
    
    if zones.exists():
        zone = zones.first()
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
    return None