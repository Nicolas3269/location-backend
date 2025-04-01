import os

import requests
from django.core.management.base import BaseCommand

from algo.encadrement_loyer.montpellier.ods_to_rentprice_json import (
    extract_ods_file_to_json,
)
from rent_control.choices import Region
from rent_control.models import RentControlArea, RentPrice

DATA = {
    # # CAN BE DONE with the url
    # Region.PARIS: "https://www.data.gouv.fr/fr/datasets/r/41a1c199-14ca-4cc7-a827-cc4779fed8c0",
    # Region.EST_ENSEMBLE: "https://www.data.gouv.fr/fr/datasets/r/7d70e696-ef9d-429d-8284-79d0ecd59ccd",
    # Region.PLAINE_COMMUNE: "https://www.data.gouv.fr/fr/datasets/r/de5c9cb9-6215-4e88-aef7-ea0041984d1d",
    # # #
    # # #
    # # Can be done all in one
    # Region.LYON: "https://www.data.gouv.fr/fr/datasets/r/57266456-f9c9-4ee0-9245-26bb4e537cd6",
    # # #
    # # #
    # # #
    Region.MONTPELLIER: "https://www.data.gouv.fr/fr/datasets/r/c00fa2a7-f84c-4ca4-8224-3b734242bae7",
    # Region.BORDEAUX: "custom",
    # Region.LILLE: "custom",
    # Region.PAYS_BASQUE: "custom",
}
DEFAULT_YEAR = 2024


class Command(BaseCommand):
    help = "Import rent control prices data"

    def handle(self, *args, **options):
        self.stdout.write("Importing rent control prices...")

        # Clear existing data
        RentPrice.objects.all().delete()

        # Import
        for region, url in DATA.items():
            self.import_prices(url, region)

        self.stdout.write(
            self.style.SUCCESS("Successfully imported rent control zones")
        )

    def import_prices(self, url, region):
        """Import Prices data into the database"""
        self.stdout.write(f"Importing {region} prices data")

        try:
            if region == Region.MONTPELLIER:
                extract_dir = "algo/encadrement_loyer/montpellier"
                file_path = os.path.join(extract_dir, f"{DEFAULT_YEAR}.ods")
                json_file = extract_ods_file_to_json(file_path)
                for area in RentControlArea.objects.using("geodb").filter(
                    region=region.BORDEAUX, reference_year=DEFAULT_YEAR
                ):
                    a = 1
                # Bordeaux data is not available via the API
                # You can add a different method to handle it if needed

            else:
                response = requests.get(url)
                response.raise_for_status()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching data: {e}"))
            return
