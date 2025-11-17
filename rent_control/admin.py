from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path

from rent_control.management.commands.constants import DEFAULT_YEAR

from .choices import Region
from .models import (
    PermisDeLouer,
    RentControlArea,
    RentMap,
    RentPrice,
    ZoneTendue,
    ZoneTendueTouristique,
    ZoneTresTendue,
)


class RegionListFilter(admin.SimpleListFilter):
    title = "Région"
    parameter_name = "region"

    def lookups(self, request, model_admin):
        # Optimisation: n'afficher que les régions qui ont des prix
        regions_with_prices = RentControlArea.objects.values("region").distinct()
        return [
            (code, name)
            for code, name in Region.choices
            if code in [r["region"] for r in regions_with_prices]
        ]

    def queryset(self, request, queryset):
        if self.value():
            # Utiliser une sous-requête pour de meilleures performances
            return queryset.filter(
                areas__in=RentControlArea.objects.filter(region=self.value())
            ).distinct()
        return queryset


class RentPriceInline(admin.TabularInline):
    """Affiche les prix associés à une zone avec leurs caractéristiques"""

    model = RentPrice.areas.through
    extra = 0
    verbose_name = "Prix associé"
    verbose_name_plural = "Prix associés"

    # Définir les champs en lecture seule pour afficher les informations du prix
    readonly_fields = (
        "get_property_type",
        "get_room_count",
        "get_construction_period",
        "get_furnished",
        "get_reference_price",
        "get_price_range",
    )

    # Contrôle les champs à afficher et leur ordre
    fields = (
        "rentprice",
        "get_property_type",
        "get_room_count",
        "get_construction_period",
        "get_furnished",
        "get_price_range",
    )

    def get_property_type(self, obj):
        """Affiche le type de bien"""
        return obj.rentprice.get_property_type_display()

    get_property_type.short_description = "Type de bien"

    def get_room_count(self, obj):
        """Affiche le nombre de pièces"""
        return obj.rentprice.room_count

    get_room_count.short_description = "Pièces"

    def get_construction_period(self, obj):
        """Affiche la période de construction"""
        return obj.rentprice.get_construction_period_display()

    get_construction_period.short_description = "Construction"

    def get_furnished(self, obj):
        """Affiche si meublé ou non"""
        return "Meublé" if obj.rentprice.furnished else "Non meublé"

    get_furnished.short_description = "Meublé"

    def get_reference_price(self, obj):
        """Affiche le prix de référence"""
        return f"{obj.rentprice.reference_price}€/m²"

    get_reference_price.short_description = "Prix réf."

    def get_price_range(self, obj):
        """Affiche la fourchette de prix"""
        return f"{obj.rentprice.min_price}€ - {obj.rentprice.max_price}€"

    get_price_range.short_description = "Fourchette"

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields["rentprice"].label = "Prix"
        return formset

    # Empêcher la modification directe dans l'inline
    def has_change_permission(self, request, obj=None):
        return False


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
                region=selected_region, reference_year=DEFAULT_YEAR
            )

        # Générer des couleurs pour les zone_id (exclure ACCEPTED)
        zone_colors = {}
        unique_zone_ids = set(
            zone.zone_id for zone in zones if zone.zone_id != "ACCEPTED"
        )

        for i, zone_id in enumerate(unique_zone_ids):
            hue = (i * 137) % 360  # Distribue les couleurs harmonieusement
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
            <h1>Carte des zones d'encadrement des loyers 2025</h1>
            
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
        # Première passe : zones normales (pas ACCEPTED)
        for zone in zones:
            if zone.zone_id == "ACCEPTED":
                continue  # Skip ACCEPTED zones for now

            color = zone_colors.get(zone.zone_id, "#ff0000")
            style_config = f"""
                            style: {{
                                color: '#333',
                                weight: 1,
                                fillColor: "{color}",
                                fillOpacity: 0.7
                            }},"""

            html_content += f"""
                    try {{
                        var geojson = {zone.geometry.geojson};
                        
                        var layer = L.geoJSON(geojson, {{{style_config}
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

        # Deuxième passe : zones ACCEPTED (affichées au-dessus)
        for zone in zones:
            if zone.zone_id != "ACCEPTED":
                continue  # Only process ACCEPTED zones now

            style_config = """
                            style: {
                                color: '#000',
                                weight: 3,
                                fillOpacity: 0
                            },
                            interactive: false,"""

            html_content += f"""
                    try {{
                        var geojson = {zone.geometry.geojson};
                        
                        var layer = L.geoJSON(geojson, {{{style_config}
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

        # Ajouter les entrées de légende (exclure ACCEPTED)
        for zone_id, color in zone_colors.items():
            if zone_id != "ACCEPTED":
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

    list_per_page = 20

    # Exclure le champ areas de l'édition directe (géré par un widget spécialisé)
    exclude = ("areas",)

    list_display = (
        "areas_display",  # Changé de area_display à areas_display
        "property_type",
        "room_count",
        "construction_period",
        "furnished",
        "reference_price",
        "get_price_range",
    )

    list_filter = (
        "property_type",
        RegionListFilter,
        "room_count",
        "construction_period",
        "furnished",
        # Modifier les filtres pour utiliser lookup à travers ManyToMany
    )

    # Filtre personnalisé pour region et référence_year
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("areas")  # Optimiser les requêtes

    def get_price_range(self, obj):
        """Affiche la fourchette de prix"""
        return f"{obj.min_price}€ - {obj.max_price}€"

    get_price_range.short_description = "Fourchette de prix"

    def areas_display(self, obj):
        """Affiche les zones associées à ce prix"""
        areas = obj.areas.all()[:3]  # Limiter pour l'affichage
        if not areas:
            return "-"

        area_list = ", ".join([f"{a.get_region_display()}: {a.zone_id}" for a in areas])
        count = obj.areas.count()
        if count > 3:
            area_list += f" et {count - 3} autre(s)"
        return area_list

    areas_display.short_description = "Zones"

    # Ajouter un filtre pour région
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "areas":
            kwargs["widget"] = admin.widgets.FilteredSelectMultiple("zones", False)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class RentMapView(admin.ModelAdmin):
    """Admin view for the rent map only"""

    # Ce modèle ne permet pas d'ajouter/modifier des objets
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # Rediriger vers la carte des régions
    def changelist_view(self, request, extra_context=None):
        return redirect("admin:rentcontrolarea_region_map")


@admin.register(RentMap)
class RentMapAdmin(RentMapView):
    pass


@admin.register(ZoneTendue)
class ZoneTendueAdmin(admin.ModelAdmin):
    """Admin view for ZoneTendue"""

    list_display = ("communes", "code_insee", "departements", "agglomerations")
    list_filter = ("departements",)
    search_fields = ("communes", "code_insee", "departements", "agglomerations")
    ordering = ("departements", "communes")

    # Pagination pour gérer les nombreux enregistrements
    list_per_page = 50

    # Grouper les champs dans le formulaire
    fieldsets = (
        ("Informations principales", {"fields": ("communes", "code_insee")}),
        ("Localisation administrative", {"fields": ("departements", "agglomerations")}),
    )

    # Actions personnalisées
    actions = ["export_selected_zones"]

    def export_selected_zones(self, request, queryset):
        """Exporter les zones sélectionnées en CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="zones_tendues.csv"'

        writer = csv.writer(response)
        writer.writerow(["Code INSEE", "Communes", "Départements", "Agglomérations"])

        for zone in queryset:
            writer.writerow(
                [
                    zone.code_insee,
                    zone.communes,
                    zone.departements,
                    zone.agglomerations or "",
                ]
            )

        self.message_user(request, f"{queryset.count()} zones exportées avec succès.")
        return response

    export_selected_zones.short_description = "Exporter les zones sélectionnées en CSV"  # type: ignore


@admin.register(ZoneTresTendue)
class ZoneTresTendueAdmin(admin.ModelAdmin):
    """Admin view for ZoneTresTendue (Zone A bis)"""

    list_display = ("commune", "departement_code", "departement_nom")
    list_filter = ("departement_nom", "departement_code")
    search_fields = ("commune", "departement_nom", "departement_code")
    ordering = ("departement_code", "commune")

    # Pagination pour gérer les enregistrements
    list_per_page = 50

    # Grouper les champs dans le formulaire
    fieldsets = (
        ("Informations principales", {"fields": ("commune",)}),
        ("Localisation administrative", {"fields": ("departement_code", "departement_nom")}),
    )

    # Actions personnalisées
    actions = ["export_selected_zones_tres_tendues"]

    def export_selected_zones_tres_tendues(self, request, queryset):
        """Exporter les zones très tendues sélectionnées en CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="zones_tres_tendues.csv"'

        writer = csv.writer(response)
        writer.writerow(["Département Code", "Département", "Commune"])

        for zone in queryset:
            writer.writerow(
                [
                    zone.departement_code,
                    zone.departement_nom,
                    zone.commune,
                ]
            )

        self.message_user(request, f"{queryset.count()} zones très tendues exportées avec succès.")
        return response

    export_selected_zones_tres_tendues.short_description = "Exporter les zones très tendues sélectionnées en CSV"  # type: ignore


@admin.register(ZoneTendueTouristique)
class ZoneTendueTouristiqueAdmin(admin.ModelAdmin):
    """Admin view for ZoneTendueTouristique"""

    list_display = ("commune", "code_insee", "departement_code")
    list_filter = ("departement_code",)
    search_fields = ("commune", "code_insee", "departement_code")
    ordering = ("departement_code", "commune")

    # Pagination pour gérer les enregistrements
    list_per_page = 50

    # Grouper les champs dans le formulaire
    fieldsets = (
        ("Informations principales", {"fields": ("commune", "code_insee")}),
        ("Localisation administrative", {"fields": ("departement_code",)}),
    )

    # Actions personnalisées
    actions = ["export_selected_zones_touristiques"]

    def export_selected_zones_touristiques(self, request, queryset):
        """Exporter les zones tendues touristiques sélectionnées en CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="zones_tendues_touristiques.csv"'

        writer = csv.writer(response)
        writer.writerow(["Département", "Commune", "Code INSEE"])

        for zone in queryset:
            writer.writerow(
                [
                    zone.departement_code,
                    zone.commune,
                    zone.code_insee,
                ]
            )

        self.message_user(request, f"{queryset.count()} zones tendues touristiques exportées avec succès.")
        return response

    export_selected_zones_touristiques.short_description = "Exporter les zones tendues touristiques sélectionnées en CSV"  # type: ignore


@admin.register(PermisDeLouer)
class PermisDeLouerAdmin(admin.ModelAdmin):
    """Admin view for PermisDeLouer"""

    list_display = (
        "villes",
        "specificite_par_quartier",
        "date_inconnues",
        "raw_data_preview",
    )
    list_filter = ("specificite_par_quartier", "date_inconnues")
    search_fields = ("villes", "raw_data")
    ordering = ("villes",)

    # Pagination pour gérer les enregistrements
    list_per_page = 50

    # Grouper les champs dans le formulaire
    fieldsets = (
        ("Informations principales", {"fields": ("villes", "raw_data")}),
        ("Spécificités", {"fields": ("specificite_par_quartier", "date_inconnues")}),
    )

    # Actions personnalisées
    actions = ["export_selected_permis"]

    def raw_data_preview(self, obj):
        """Affiche un aperçu des données brutes"""
        if len(obj.raw_data) > 50:
            return f"{obj.raw_data[:50]}..."
        return obj.raw_data

    raw_data_preview.short_description = "Aperçu des données brutes"  # type: ignore

    def export_selected_permis(self, request, queryset):
        """Exporter les permis sélectionnés en CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="permis_de_louer.csv"'

        writer = csv.writer(response)
        writer.writerow(
            ["Raw data", "Villes", "Spécificité par Quartier", "Date inconnues"]
        )

        for permis in queryset:
            writer.writerow(
                [
                    permis.raw_data,
                    permis.villes,
                    "Oui" if permis.specificite_par_quartier else "Non",
                    "Oui" if permis.date_inconnues else "Non",
                ]
            )

        self.message_user(request, f"{queryset.count()} permis exportés avec succès.")
        return response

    export_selected_permis.short_description = "Exporter les permis sélectionnés en CSV"  # type: ignore
