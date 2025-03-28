from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import RentControlArea, RentPrice


class RentPriceInline(admin.TabularInline):
    """Affiche les prix inline dans l'admin de la zone"""

    model = RentPrice
    extra = 0
    fields = (
        "property_type",
        "room_count",
        "construction_period",
        "furnished",
        "reference_price",
        "min_price",
        "max_price",
    )

    # Limiter le nombre d'entrées affichées pour éviter de surcharger la page
    max_num = 10


@admin.register(RentControlArea)
class RentControlAreaAdmin(GISModelAdmin):
    """Admin view for RentControlArea with map display"""

    list_display = ("region", "zone_name", "zone_id", "reference_year", "has_prices")
    list_filter = ("region", "reference_year")
    search_fields = ("region", "zone_name", "zone_id")

    inlines = [RentPriceInline]

    # GIS-specific settings
    gis_widget_kwargs = {
        "attrs": {
            "default_lon": 2.3488,  # Paris longitude
            "default_lat": 48.8534,  # Paris latitude
            "default_zoom": 6,
        }
    }

    def has_prices(self, obj):
        """Indique si la zone a des prix associés"""
        return obj.prices.exists()

    has_prices.boolean = True
    has_prices.short_description = "Prix définis"


@admin.register(RentPrice)
class RentPriceAdmin(admin.ModelAdmin):
    """Admin view for RentPrice"""

    list_display = (
        "area_display",
        "property_type",
        "room_count",
        "construction_period",
        "furnished",
        "reference_price",
        "get_price_range",
    )
    list_filter = (
        "property_type",
        "room_count",
        "construction_period",
        "furnished",
        "area__region",
        "area__reference_year",
    )
    search_fields = ("area__zone_name", "property_type", "room_count")

    def area_display(self, obj):
        """Affiche la zone de manière plus lisible"""
        return f"{obj.area.region} - {obj.area.zone_name} ({obj.area.reference_year})"

    area_display.short_description = "Zone"

    def get_price_range(self, obj):
        """Affiche la fourchette de prix"""
        return f"{obj.min_price}€ - {obj.max_price}€"

    get_price_range.short_description = "Fourchette de prix"
