import os

from django.core.management.base import BaseCommand

from algo.encadrement_loyer.ile_de_france.main import (
    build_url,
    extract_data_from_kml,
)
from algo.encadrement_loyer.montpellier.ods_to_rentprice_json import (
    extract_ods_file_to_json,
)
from algo.encadrement_loyer.pays_basques.combinaison import (
    retrieve_data_from_json_for_pays_basques,
)
from rent_control.choices import ConstructionPeriod, PropertyType, Region, RoomCount
from rent_control.models import RentControlArea, RentPrice

from .constants import DEFAULT_YEAR

DATA = {
    Region.PARIS: "custom",
    Region.EST_ENSEMBLE: "custom",
    Region.PLAINE_COMMUNE: "custom",
    Region.LYON: "custom",
    Region.MONTPELLIER: "custom",
    Region.BORDEAUX: "custom",
    Region.PAYS_BASQUE: "custom",
    Region.LILLE: "custom",
    Region.GRENOBLE: "custom",
}


def set_prices_for_ods_file(self, region, file_path, property_type=None):
    """Set prices for the ODS file"""
    # Extraire les données du fichier ODS
    prices_data = extract_ods_file_to_json(file_path, property_type=property_type)

    # Récupérer toutes les zones correspondant à la région et l'année
    areas = RentControlArea.objects.filter(region=region, reference_year=DEFAULT_YEAR)

    # Si aucune zone, signaler une erreur et sortir
    if not areas.exists():
        self.stdout.write(
            self.style.ERROR(f"No areas found for {region} {DEFAULT_YEAR}")
        )
        return

    # Parcourir les données de prix extraites
    for price_data in prices_data:
        # Créer un nouveau prix
        price = RentPrice.objects.create(
            property_type=price_data["property_type"],
            room_count=price_data["room_count"],
            construction_period=price_data["construction_period"],
            furnished=price_data["furnished"],
            reference_year=DEFAULT_YEAR,
            reference_price=price_data["reference_price"],
            min_price=price_data["min_price"],
            max_price=price_data["max_price"],
        )

        # Pour chaque zone correspondant au critère de localisation du prix
        for area in areas.filter(zone_id=price_data["zone_id"]):
            # Associer le prix à la zone
            price.areas.add(area)

        self.stdout.write(f"Created price: {price}")


def import_pays_basque_prices(self, region):
    """Importe les prix du Pays Basque"""
    self.stdout.write("Importing Pays Basque prices...")

    # Récupérer les données formatées
    prices_data = retrieve_data_from_json_for_pays_basques()

    # Récupérer toutes les zones du Pays Basque
    areas = RentControlArea.objects.filter(region=region, reference_year=DEFAULT_YEAR)

    if not areas.exists():
        self.stdout.write(
            self.style.ERROR(f"No areas found for {region} {DEFAULT_YEAR}")
        )
        return

    # Parcourir les données et créer les prix
    for price_data in prices_data:
        price = RentPrice.objects.create(
            property_type=price_data["property_type"],
            room_count=price_data["room_count"],
            construction_period=price_data["construction_period"],
            furnished=price_data["furnished"],
            reference_year=DEFAULT_YEAR,
            reference_price=price_data["reference_price"],
            min_price=price_data["min_price"],
            max_price=price_data["max_price"],
        )

        # Associer à toutes les zones correspondantes
        for area in areas.filter(zone_id=price_data["zone_id"]):
            price.areas.add(area)

        self.stdout.write(f"Created price: {price}")


def price_ile_de_france(
    self, region, region_uri, start_date, property_type_uri, property_type
):
    room_counts = {
        1: RoomCount.ONE,
        2: RoomCount.TWO,
        3: RoomCount.THREE,
        4: RoomCount.FOUR_PLUS,
    }
    construction_periods = {
        "inf1946": ConstructionPeriod.BEFORE_1946,
        "1946-1970": ConstructionPeriod.FROM_1946_TO_1970,
        "1971-1990": ConstructionPeriod.FROM_1971_TO_1990,
        "sup1990": ConstructionPeriod.AFTER_1990,
    }
    meubles = {"meuble": True, "non-meuble": False}

    areas = RentControlArea.objects.filter(
        region=region,
        reference_year=DEFAULT_YEAR,
    )
    for room_count, room_count_v in room_counts.items():
        for (
            construction_period,
            construction_period_v,
        ) in construction_periods.items():
            for meuble, furnished in meubles.items():
                try:
                    url = build_url(
                        region_uri,
                        property_type_uri,
                        room_count,
                        construction_period,
                        meuble,
                        start_date,
                    )
                    print(
                        f"Extraction: {property_type_uri}, {room_count} pièces, {construction_period}, {'meublé' if furnished else 'non meublé'}"
                    )

                    data = extract_data_from_kml(url)

                    for zone_id, price_data in data.items():
                        price = RentPrice.objects.create(
                            property_type=property_type,
                            room_count=room_count_v,
                            construction_period=construction_period_v,
                            furnished=furnished,
                            reference_year=DEFAULT_YEAR,
                            reference_price=price_data["ref"],
                            min_price=price_data["refmin"],
                            max_price=price_data["refmaj"],
                        )

                        # Associer à toutes les zones correspondantes
                        for area in areas.filter(zone_id=zone_id):
                            price.areas.add(area)

                        self.stdout.write(f"Created price: {price}")

                except Exception as e:
                    print(f"  Erreur: {e}")


def price_est_ensemble(self, region):
    region_uri = "est-ensemble"
    start_date = f"{DEFAULT_YEAR}-06-01"
    property_types = {
        "appartement": PropertyType.APARTMENT,
        "maison": PropertyType.HOUSE,
    }  # Attention paris y a rien
    for property_type_uri, property_type in property_types.items():
        price_ile_de_france(
            self, region, region_uri, start_date, property_type_uri, property_type
        )


def price_plaine_commune(self, region):
    region_uri = "plaine-commune"
    start_date = f"{DEFAULT_YEAR}-06-01"
    property_types = {
        "appartement": PropertyType.APARTMENT,
        "maison": PropertyType.HOUSE,
    }  # Attention paris y a rien
    for property_type_uri, property_type in property_types.items():
        price_ile_de_france(
            self, region, region_uri, start_date, property_type_uri, property_type
        )


def price_paris(self, region):
    region_uri = "paris"
    start_date = f"{DEFAULT_YEAR}-07-01"
    price_ile_de_france(self, region, region_uri, start_date, None, None)


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
                set_prices_for_ods_file(self, region, file_path, property_type=None)

            elif region == Region.BORDEAUX:
                extract_dir = "algo/encadrement_loyer/bordeaux"
                # APPARTEMENT
                file_path = os.path.join(extract_dir, f"{DEFAULT_YEAR}_appart.ods")
                set_prices_for_ods_file(
                    self, region, file_path, property_type=PropertyType.APARTMENT
                )
                # MAISON
                file_path = os.path.join(extract_dir, f"{DEFAULT_YEAR}_maison.ods")
                set_prices_for_ods_file(
                    self, region, file_path, property_type=PropertyType.HOUSE
                )

            elif region == Region.LILLE:
                extract_dir = "algo/encadrement_loyer/lille"
                file_path = os.path.join(extract_dir, f"{DEFAULT_YEAR}.ods")
                set_prices_for_ods_file(self, region, file_path, property_type=None)

            elif region == Region.PAYS_BASQUE:
                import_pays_basque_prices(self, region)

            elif region == Region.LYON:
                extract_dir = "algo/encadrement_loyer/lyon_Villeurbanne"
                file_path = os.path.join(extract_dir, f"{DEFAULT_YEAR}.ods")
                set_prices_for_ods_file(self, region, file_path, property_type=None)

            elif region == Region.EST_ENSEMBLE:
                price_est_ensemble(self, region)

            elif region == Region.PLAINE_COMMUNE:
                price_plaine_commune(self, region)

            elif region == Region.PARIS:
                price_paris(self, region)

            elif region == Region.GRENOBLE:
                extract_dir = "algo/encadrement_loyer/grenoble"
                file_path = os.path.join(extract_dir, f"{DEFAULT_YEAR}.ods")
                set_prices_for_ods_file(self, region, file_path, property_type=None)

            else:
                raise ValueError(f"Unknown region: {region}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching data: {e}"))
            return
