import json
import os

import requests
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
    Region.LYON: "https://www.data.gouv.fr/fr/datasets/r/57266456-f9c9-4ee0-9245-26bb4e537cd6",
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
        # Rechercher un prix existant avec les mêmes caractéristiques ou en créer un nouveau
        price, created = RentPrice.objects.get_or_create(
            property_type=price_data["property_type"],
            room_count=price_data["room_count"],
            construction_period=price_data["construction_period"],
            furnished=price_data["furnished"],
            reference_year=DEFAULT_YEAR,
            defaults={
                "reference_price": price_data["reference_price"],
                "min_price": price_data["min_price"],
                "max_price": price_data["max_price"],
            },
        )

        # Pour chaque zone correspondant au critère de localisation du prix
        for area in areas.filter(zone_id=price_data["zone_id"]):
            # Associer le prix à la zone
            price.areas.add(area)

        if created:
            self.stdout.write(f"Created price: {price}")
        else:
            self.stdout.write(f"Using existing price: {price}")


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
        price, created = RentPrice.objects.get_or_create(
            property_type=price_data["property_type"],
            room_count=price_data["room_count"],
            construction_period=price_data["construction_period"],
            furnished=price_data["furnished"],
            reference_year=DEFAULT_YEAR,
            defaults={
                "reference_price": price_data["reference_price"],
                "min_price": price_data["min_price"],
                "max_price": price_data["max_price"],
            },
        )

        # Associer à toutes les zones correspondantes
        for area in areas.filter(zone_id=price_data["zone_id"]):
            price.areas.add(area)

        if created:
            self.stdout.write(f"Created price: {price}")
        else:
            self.stdout.write(f"Using existing price: {price}")


def get_lyon_prices(self, url, region):
    dict_room_count = {
        "1": RoomCount.ONE,
        "2": RoomCount.TWO,
        "3": RoomCount.THREE,
        "4 et plus": RoomCount.FOUR_PLUS,
    }
    dict_construction_period = {
        "avant 1946": ConstructionPeriod.BEFORE_1946,
        "1946-1970": ConstructionPeriod.FROM_1946_TO_1970,
        "1971-1990": ConstructionPeriod.FROM_1971_TO_1990,
        "1991-2005": ConstructionPeriod.FROM_1990_TO_2005,
        "après 2005": ConstructionPeriod.AFTER_2005,
    }
    dict_furnished = {
        "meuble": True,
        "non meuble": False,
    }
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
            properties = feature.get("properties", {})
            id_quartier = properties.get("gid")
            areas = RentControlArea.objects.filter(
                region=region, reference_year=DEFAULT_YEAR, quartier_id=id_quartier
            )
            if not areas.exists() or len(areas) > 1:
                self.stdout.write(
                    self.style.ERROR(
                        f"Issue with quartier_id {id_quartier} for {region} in {DEFAULT_YEAR}"
                    )
                )
                return
            area = areas.first()

            valeurs = json.loads(properties["valeurs"])
            for room_count, room_data in valeurs.items():
                for construction_period, construction_data in room_data.items():
                    for furnished, price_data in construction_data.items():
                        price, created = RentPrice.objects.get_or_create(
                            property_type=None,
                            room_count=dict_room_count[room_count],
                            construction_period=dict_construction_period[
                                construction_period
                            ],
                            furnished=dict_furnished[furnished],
                            reference_year=DEFAULT_YEAR,
                            defaults={
                                "reference_price": price_data["loyer_reference"],
                                "min_price": price_data["loyer_reference_minore"],
                                "max_price": price_data["loyer_reference_majore"],
                            },
                        )
                        price.areas.add(area)
            count += 1

            if count % 100 == 0:
                self.stdout.write(f"  Imported {count} zones so far...")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing feature: {e}"))
            self.stdout.write(self.style.ERROR(f"Feature data: {properties}"))


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
                        price, created = RentPrice.objects.get_or_create(
                            property_type=property_type,
                            room_count=room_count_v,
                            construction_period=construction_period_v,
                            furnished=furnished,
                            reference_year=DEFAULT_YEAR,
                            defaults={
                                "reference_price": price_data["ref"],
                                "min_price": price_data["refmin"],
                                "max_price": price_data["refmaj"],
                            },
                        )

                        # Associer à toutes les zones correspondantes
                        for area in areas.filter(zone_id=zone_id):
                            price.areas.add(area)

                        if created:
                            self.stdout.write(f"Created price: {price}")
                        else:
                            self.stdout.write(f"Using existing price: {price}")

                except Exception as e:
                    print(f"  Erreur: {e}")


def price_est_ensemble(self, region):
    region_uri = "est-ensemble"
    start_date = "2024-06-01"
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
    start_date = "2024-06-01"
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
    start_date = "2024-07-01"
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
                # Lyon data can be fetched from the URL
                get_lyon_prices(self, url, region)

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
