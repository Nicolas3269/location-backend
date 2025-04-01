import requests
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand

from algo.encadrement_loyer.bordeaux.main import get_bordeaux_zone_geometries
from algo.encadrement_loyer.lille.main import get_lille_zone_geometries
from algo.encadrement_loyer.pays_basques.main import get_pays_basque_zone_geometries
from rent_control.choices import Region
from rent_control.models import RentControlArea

### POUR ILE DE FRANCE ###
# Il faut la geométrie et la carte de prix pour chaque zone

### Pour LYON
# On peut tout avoir directement


DATA = {
    # CAN BE DONE with the url
    Region.PARIS: "https://www.data.gouv.fr/fr/datasets/r/41a1c199-14ca-4cc7-a827-cc4779fed8c0",
    Region.EST_ENSEMBLE: "https://www.data.gouv.fr/fr/datasets/r/7d70e696-ef9d-429d-8284-79d0ecd59ccd",
    Region.PLAINE_COMMUNE: "https://www.data.gouv.fr/fr/datasets/r/de5c9cb9-6215-4e88-aef7-ea0041984d1d",
    # #
    # #
    # Can be done all in one
    Region.LYON: "https://www.data.gouv.fr/fr/datasets/r/57266456-f9c9-4ee0-9245-26bb4e537cd6",
    # #
    # #
    # #
    Region.MONTPELLIER: "https://www.data.gouv.fr/fr/datasets/r/c00fa2a7-f84c-4ca4-8224-3b734242bae7",
    Region.BORDEAUX: "custom",
    Region.LILLE: "custom",
    Region.PAYS_BASQUE: "custom",
}
DEFAULT_YEAR = 2024


class Command(BaseCommand):
    help = "Import rent control zone data from GeoJSON files"

    def handle(self, *args, **options):
        self.stdout.write("Importing rent control zones...")

        # Clear existing data
        RentControlArea.objects.all().delete()

        # Import
        for region, url in DATA.items():
            self.import_geojson(url, region)

        self.stdout.write(
            self.style.SUCCESS("Successfully imported rent control zones")
        )

    def import_geojson(self, url, region):
        """Import GeoJSON data into the database"""
        self.stdout.write(f"Importing {region} data from {url}")

        try:
            if region == Region.BORDEAUX:
                # Bordeaux data is not available via the API
                # You can add a different method to handle it if needed
                data = get_bordeaux_zone_geometries()

            elif region == Region.LILLE:
                data = get_lille_zone_geometries(DEFAULT_YEAR)
            elif region == Region.PAYS_BASQUE:
                data = get_pays_basque_zone_geometries()
            else:
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
                id_quartier = None
                zone_name = None
                if region in [Region.BORDEAUX, Region.LILLE]:
                    geom = GEOSGeometry(geometry)
                    # Pas besoin de vérifier geometry type ici, tu peux le faire après
                    if geom.geom_type == "Polygon":
                        geom = MultiPolygon(geom)
                else:
                    if geometry and geometry.get("type") in ("Polygon", "MultiPolygon"):
                        geom = GEOSGeometry(str(geometry))
                        if geometry.get("type") == "Polygon":
                            geom = MultiPolygon(geom)

                # Mappage adapté pour Paris
                if region == Region.PARIS:
                    id_zone = properties.get("id_zone")
                    id_quartier = properties.get("id_quartier")
                    zone_name = properties.get("nom_quartier")
                    reference_year = (
                        int(properties.get("annee"))
                        if properties.get("annee")
                        else DEFAULT_YEAR
                    )
                elif region == Region.EST_ENSEMBLE:
                    id_zone = properties.get("Zone")
                    id_quartier = properties.get("com_cv_code")
                    zone_name = properties.get("arrdep_name")
                    reference_year = DEFAULT_YEAR

                elif region == Region.PLAINE_COMMUNE:
                    id_zone = properties.get("Zone")
                    id_quartier = properties.get("INSEE_COM")
                    zone_name = properties.get("NOM_COM")
                    reference_year = (
                        int(properties.get("annee"))
                        if properties.get("annee")
                        else DEFAULT_YEAR
                    )
                elif region == Region.LYON:
                    id_zone = properties.get("zonage")
                    # ici c'est probablemment la qu'on doit améliorer car c'est plusieurs id_quartier
                    id_quartier = properties.get("gid")
                    zone_name = properties.get("commune")
                    reference_year = DEFAULT_YEAR

                elif region == Region.MONTPELLIER:
                    id_zone = properties.get("Zone")
                    reference_year = DEFAULT_YEAR

                elif region == Region.BORDEAUX:
                    id_zone = properties.get("Zonage_val")
                    zone_name = properties.get("ZET_lib")
                    id_quartier = properties.get("CODE_IRIS")
                    reference_year = DEFAULT_YEAR

                elif region == Region.LILLE:
                    id_zone = properties.get("zone_id")
                    id_quartier = properties.get("id_quartier")
                    zone_name = properties.get("zone_name")
                    reference_year = DEFAULT_YEAR
                elif region == Region.PAYS_BASQUE:
                    id_zone = properties.get("zone_encadr_loyers")
                    id_quartier = properties.get("gid")
                    zone_name = properties.get("nom_iris")
                    reference_year = DEFAULT_YEAR
                else:
                    id_zone = properties.get("Zone", "")
                    reference_year = DEFAULT_YEAR

                # Create the zone object
                RentControlArea.objects.using("geodb").create(
                    region=region,
                    zone_id=id_zone,
                    quartier_id=id_quartier,
                    zone_name=zone_name,
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
