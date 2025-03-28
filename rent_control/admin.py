from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.http import HttpResponse
from django.urls import path

from .choices import Region
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

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "region_map/",
                self.admin_site.admin_view(self.region_map_view),
                name="rentcontrolarea_region_map",
            ),
        ]
        return custom_urls + urls

    def region_map_view(self, request):
        """Vue pour afficher une carte de toutes les zones par région"""
        selected_region = request.GET.get("region", None)

        # Si aucune région sélectionnée, prendre la première disponible
        regions = Region.choices
        default_region = "MONTPELLIER" if regions else None

        if selected_region:
            # Vérifier que la région existe
            if selected_region not in [r[0] for r in regions]:
                selected_region = default_region
        else:
            selected_region = default_region

        # Récupérer le nom lisible de la région
        region_name = dict(regions).get(selected_region, "")

        # Récupérer les zones pour cette région

        zones = []
        if selected_region:
            zones = RentControlArea.objects.filter(
                region=selected_region, reference_year=2024
            )

        # Générer des couleurs pour les zone_id
        zone_colors = {}
        unique_zone_ids = set(zone.zone_id for zone in zones)

        for i, zone_id in enumerate(unique_zone_ids):
            hue = (i * 137) % 360  # Distribue les couleurs de manière harmonieuse
            zone_colors[zone_id] = f"hsl({hue}, 70%, 60%)"

        # Préparer le contexte pour le template
        context = {
            **self.admin_site.each_context(request),
            "title": "Carte des zones par région",
            "regions": regions,
            "selected_region": selected_region,
            "region_name": region_name,
            "zones": zones,
            "zone_colors": zone_colors,
        }

        # Créer une réponse HTML directement dans la fonction
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{context["title"]} | {context["site_title"]}</title>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
            <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
            <style>
                #map {{
                    height: 600px;
                    width: 100%;
                    margin-bottom: 20px;
                }}
                .legend {{
                    background: white;
                    padding: 10px;
                    border-radius: 5px;
                    box-shadow: 0 0 15px rgba(0, 0, 0, 0.2);
                }}
                .legend-item {{
                    margin-bottom: 5px;
                }}
                .color-box {{
                    display: inline-block;
                    width: 20px;
                    height: 20px;
                    margin-right: 8px;
                    vertical-align: middle;
                    border: 1px solid #999;
                }}
                .region-selector {{
                    margin-bottom: 15px;
                }}
            </style>
        </head>
        <body>
            <h1>Carte des zones d'encadrement des loyers 2024-2025</h1>
            
            <div class="region-selector">
                <form method="get">
                    <label for="region">Sélectionner une région:</label>
                    <select name="region" id="region" onchange="this.form.submit()">
        """

        # Ajouter les options de région
        for region_code, region_label in regions:
            selected = "selected" if region_code == selected_region else ""
            html_content += (
                f'<option value="{region_code}" {selected}>{region_label}</option>'
            )

        html_content += """
                    </select>
                </form>
            </div>
            
            <div id="map"></div>
            
            <script>
                document.addEventListener('DOMContentLoaded', function() {
                    // Créer la carte
                    var map = L.map('map').setView([48.8534, 2.3488], 10);
                    
                    // Ajouter les tuiles OpenStreetMap
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    }).addTo(map);
                    
                    // Variable pour stocker les limites
                    var bounds = null;
        """

        # Ajouter le code JavaScript pour chaque zone
        for zone in zones:
            color = zone_colors.get(zone.zone_id, "#ff0000")
            html_content += f"""
                    try {{
                        var geojson = {zone.geometry.geojson};
                        
                        var layer = L.geoJSON(geojson, {{
                            style: {{
                                color: '#333',
                                weight: 1,
                                fillColor: "{color}",
                                fillOpacity: 0.7
                            }},
                            onEachFeature: function(feature, layer) {{
                                layer.bindPopup(
                                    "<strong>{zone.zone_name or "Zone " + zone.zone_id}</strong><br>" +
                                    "ID: {zone.zone_id}<br>" +
                                    "Année: {zone.reference_year}<br>" +
                                    "<a href='/admin/rent_control/rentcontrolarea/{zone.id}/change/'>Modifier</a>"
                                );
                            }}
                        }}).addTo(map);
                        
                        // Étendre les limites
                        if (bounds === null) {{
                            bounds = layer.getBounds();
                        }} else {{
                            bounds.extend(layer.getBounds());
                        }}
                    }} catch (e) {{
                        console.error("Erreur avec la zone {zone.id}: " + e);
                    }}
            """

        # Ajouter la légende et le code pour ajuster la vue
        html_content += """
                    // Ajuster la vue
                    if (bounds !== null) {
                        map.fitBounds(bounds);
                    }
                    
                    // Ajouter une légende
                    var legend = L.control({position: 'bottomright'});
                    legend.onAdd = function(map) {
                        var div = L.DomUtil.create('div', 'legend');
                        div.innerHTML = '<h4>Légende des zones</h4>';
        """

        # Ajouter les entrées de légende
        for zone_id, color in zone_colors.items():
            html_content += f"""
                        div.innerHTML += '<div class="legend-item"><span class="color-box" style="background: {color}"></span>Zone {zone_id}</div>';
            """

        html_content += """
                        return div;
                    };
                    legend.addTo(map);
                });
            </script>
            
            <div style="margin-top: 20px;">
                <a href="/admin/rent_control/rentcontrolarea/" class="button">Retour à la liste</a>
            </div>
        </body>
        </html>
        """

        # Renvoyer la réponse HTTP
        return HttpResponse(html_content)

    def has_prices(self, obj):
        """Indique si la zone a des prix associés"""
        return obj.prices.exists()

    has_prices.boolean = True
    has_prices.short_description = "Prix définis"

    def changelist_view(self, request, extra_context=None):
        """Ajoute un lien vers la vue carte"""
        extra_context = extra_context or {}
        extra_context["show_map_link"] = True
        return super().changelist_view(request, extra_context=extra_context)


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
