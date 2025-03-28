from datetime import datetime

import requests
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand

from rent_control.models import RentControlZone


class Command(BaseCommand):
    help = "Import rent control zone data from GeoJSON files"

    def handle(self, *args, **options):
        self.stdout.write("Importing rent control zones...")

        # Clear existing data
        RentControlZone.objects.all().delete()

        # Import Paris data
        self.import_geojson(
            "https://www.data.gouv.fr/fr/datasets/r/41a1c199-14ca-4cc7-a827-cc4779fed8c0",
            "IDF",
        )

        # Import Pays Basque data
        # self.import_geojson("URL_PAYS_BASQUE", "PAYS_BASQUE")

        # Add other regions as needed

        self.stdout.write(
            self.style.SUCCESS("Successfully imported rent control zones")
        )

    def import_geojson(self, url, region):
        """Import GeoJSON data into the database"""
        self.stdout.write(f"Importing {region} data from {url}")

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching data: {e}"))
            return

        count = 0
        for feature in data.get("features", []):
            try:
                geometry = feature.get("geometry", {})
                properties = feature.get("properties", {})

                if geometry and geometry.get("type") in ("Polygon", "MultiPolygon"):
                    # Convert to MultiPolygon if it's a simple Polygon
                    geom = GEOSGeometry(str(geometry))
                    if geometry.get("type") == "Polygon":
                        geom = MultiPolygon(geom)

                    # Mappage adapté pour Paris
                    if region == "IDF":
                        zone_val = properties.get("nom_quartier", "")
                        ref_price = properties.get("ref")
                        min_price = properties.get("min")
                        max_price = properties.get("max")
                        apt_type = "Appartement"  # Par défaut, car non spécifié
                        rooms = str(properties.get("piece", ""))
                        era = properties.get("epoque", "")
                        furnished = properties.get("meuble_txt") == "meublé"
                        reference_year = (
                            int(properties.get("annee"))
                            if properties.get("annee")
                            else None
                        )

                    else:
                        # Mappage générique pour les autres régions
                        zone_val = properties.get("zone", "")
                        ref_price = properties.get(
                            "loyer_reference", properties.get("loyer_ref", 0)
                        )
                        min_price = properties.get("loyer_min", 0)
                        max_price = properties.get("loyer_max", 0)
                        apt_type = properties.get(
                            "type_logement", properties.get("type", "")
                        )
                        rooms = properties.get("piece", properties.get("pieces", ""))
                        era = properties.get(
                            "epoque", properties.get("construction", "")
                        )
                        furnished = properties.get("meuble") == "Meublé"
                        reference_year = int(
                            properties.get(
                                "annee", properties.get("year", datetime.now().year)
                            )
                        )

                    # Create the zone object
                    RentControlZone.objects.using("geodb").create(
                        region=region,
                        zone=zone_val,
                        reference_price=float(ref_price)
                        if ref_price is not None
                        else None,
                        min_price=float(min_price) if min_price is not None else None,
                        max_price=float(max_price) if max_price is not None else None,
                        apartment_type=apt_type,
                        room_count=rooms,
                        construction_period=era,
                        furnished=furnished,
                        reference_year=reference_year,
                        geometry=geom,
                    )
                    count += 1

                    if count % 100 == 0:
                        self.stdout.write(f"  Imported {count} zones so far...")

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error importing feature: {e}"))
                self.stdout.write(self.style.ERROR(f"Feature data: {properties}"))

        self.stdout.write(f"Imported {count} zones for {region}")
