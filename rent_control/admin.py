from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from .models import RentControlZone

@admin.register(RentControlZone)
class RentControlZoneAdmin(GISModelAdmin):
    """Admin view for RentControlZone with map display"""
    list_display = ('region', 'zone', 'reference_price', 'construction_period', 'reference_year', 'room_count','furnished', 'apartment_type')
    list_filter = ('region', 'zone', 'construction_period', 'apartment_type', 'reference_year', 'room_count', 'furnished')
    search_fields = ('region', 'zone', 'apartment_type')
    
    # GIS-specific settings
    gis_widget_kwargs = {
        'attrs': {
            'default_lon': 2.3488,  # Paris longitude
            'default_lat': 48.8534,  # Paris latitude 
            'default_zoom': 6,
        }
    }
    
    def get_price_range(self, obj):
        if obj.min_price and obj.max_price:
            return f"{obj.min_price}€ - {obj.max_price}€"
        return "-"
    get_price_range.short_description = "Fourchette de prix"