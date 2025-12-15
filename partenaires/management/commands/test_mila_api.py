"""
Test direct de l'API Mila MRH.

Usage:
    # Test par défaut (appartement Paris)
    python manage.py test_mila_api

    # Test avec paramètres personnalisés
    python manage.py test_mila_api --address "95 Rue du Cherche-Midi" --postal-code 75006 --city Paris --type maison --rooms 3

    # Test avec plage de pièces (1 à 7)
    python manage.py test_mila_api --address "95 Rue du Cherche-Midi" --postal-code 75006 --city Paris --type maison --rooms 1-7

    # Avec surface personnalisée
    python manage.py test_mila_api --type appartement --rooms 2 --surface 50 --floor 3
"""

from django.core.management.base import BaseCommand

from partenaires.services.mila.client import MilaMRHClient, MilaAPIError
from partenaires.services.mila.types import RealEstateLotType


class Command(BaseCommand):
    help = "Teste directement l'API Mila MRH avec des paramètres personnalisés"

    def add_arguments(self, parser):
        parser.add_argument(
            "--address",
            type=str,
            default="10 Rue de la Paix",
            help="Adresse du bien (défaut: '10 Rue de la Paix')",
        )
        parser.add_argument(
            "--postal-code",
            type=str,
            default="75002",
            help="Code postal (défaut: '75002')",
        )
        parser.add_argument(
            "--city",
            type=str,
            default="Paris",
            help="Ville (défaut: 'Paris')",
        )
        parser.add_argument(
            "--type",
            type=str,
            choices=["appartement", "maison", "apartment", "house"],
            default="appartement",
            help="Type de bien (défaut: appartement)",
        )
        parser.add_argument(
            "--rooms",
            type=str,
            default="2",
            help="Nombre de pièces: '3' ou '1-7' pour une plage (défaut: 2)",
        )
        parser.add_argument(
            "--surface",
            type=int,
            help="Surface en m² (calculée automatiquement si non spécifiée)",
        )
        parser.add_argument(
            "--floor",
            type=int,
            help="Étage (0 pour maison, 1 pour appartement par défaut)",
        )

    def handle(self, *args, **options):
        address = options["address"]
        postal_code = options["postal_code"]
        city = options["city"]
        lot_type = self._get_lot_type(options["type"])
        rooms_list = self._parse_rooms(options["rooms"])
        custom_surface = options.get("surface")
        floor = options.get("floor")

        if floor is None:
            floor = 0 if lot_type == RealEstateLotType.HOUSE else 1

        type_label = "Maison" if lot_type == RealEstateLotType.HOUSE else "Appartement"

        self.stdout.write(f"\n=== Test API Mila MRH ===")
        self.stdout.write(f"Adresse: {address}, {postal_code} {city}")
        self.stdout.write(f"Type: {type_label}")
        self.stdout.write("")

        client = MilaMRHClient()

        # Header du tableau
        self.stdout.write("")
        self.stdout.write(
            f"{'Pièces':<8} {'Surface':<10} {'Essentielle':<20} {'Sérénité':<20}"
        )
        self.stdout.write("-" * 60)

        try:
            for rooms in rooms_list:
                surface = custom_surface or self._estimate_surface(rooms, lot_type)

                try:
                    result = client.get_quotation(
                        address_line1=address,
                        postal_code=postal_code,
                        city=city,
                        lot_type=lot_type,
                        surface=surface,
                        main_rooms=rooms,
                        floor=floor,
                    )

                    if result.has_results:
                        # Filtrer Essentielle et Sérénité uniquement
                        essentielle = next(
                            (f for f in result.formulas if "Essentielle" in f.product_composition_label),
                            None
                        )
                        serenite = next(
                            (f for f in result.formulas if "Sérénité" in f.product_composition_label),
                            None
                        )

                        ess_str = f"{essentielle.pricing_annual_amount / 12:.2f}€/mois" if essentielle else "-"
                        ser_str = f"{serenite.pricing_annual_amount / 12:.2f}€/mois" if serenite else "-"

                        self.stdout.write(
                            f"{rooms:<8} {surface:<10} {ess_str:<20} {ser_str:<20}"
                        )
                    else:
                        self.stdout.write(
                            f"{rooms:<8} {surface:<10} {'N/A':<20} {'N/A':<20}"
                        )
                except MilaAPIError as e:
                    self.stdout.write(
                        f"{rooms:<8} {surface:<10} {self.style.ERROR('Erreur'):<20}"
                    )

            self.stdout.write("-" * 60)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Erreur: {e}"))
        finally:
            client.close()

    def _parse_rooms(self, rooms_str: str) -> list[int]:
        """Parse le paramètre rooms: '3' ou '1-7'."""
        if "-" in rooms_str:
            start, end = rooms_str.split("-")
            return list(range(int(start), int(end) + 1))
        return [int(rooms_str)]

    def _get_lot_type(self, type_str: str) -> RealEstateLotType:
        """Convertit le type string en RealEstateLotType."""
        if type_str in ["maison", "house"]:
            return RealEstateLotType.HOUSE
        return RealEstateLotType.APARTMENT

    def _estimate_surface(self, rooms: int, lot_type: RealEstateLotType) -> int:
        """Estime la surface en fonction du nombre de pièces."""
        base = 25 if lot_type == RealEstateLotType.APARTMENT else 30
        return base + (rooms * 15)
