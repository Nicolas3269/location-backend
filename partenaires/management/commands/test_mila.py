"""
Test de l'API Mila MRH.

Usage:
    # Test avec données fictives
    python manage.py test_mila

    # Test avec une location existante
    python manage.py test_mila --location <location_id>
"""

from django.core.management.base import BaseCommand

from partenaires.services.mila.client import MilaMRHClient, MilaAPIError
from partenaires.services.mila.types import RealEstateLotType


class Command(BaseCommand):
    help = "Teste l'API Mila MRH avec des données de test ou une location existante"

    def add_arguments(self, parser):
        parser.add_argument(
            "--location",
            type=str,
            help="UUID d'une location existante à utiliser pour le test",
        )

    def handle(self, *args, **options):
        location_id = options.get("location")

        if location_id:
            self._test_with_location(location_id)
        else:
            self._test_with_dummy_data()

    def _test_with_dummy_data(self):
        """Test avec des données fictives."""
        self.stdout.write("\n=== Test API Mila MRH ===\n")

        client = MilaMRHClient()

        try:
            result = client.get_quotation(
                address_line1="10 Rue de la Paix",
                postal_code="75002",
                city="Paris",
                lot_type=RealEstateLotType.APARTMENT,
                surface=45,
                main_rooms=2,
                floor=3,
            )

            if result.has_results:
                self.stdout.write(
                    self.style.SUCCESS(f"\n✓ {len(result.formulas)} formules reçues:\n")
                )
                for f in result.formulas:
                    self.stdout.write(
                        f"  - {f.product_composition_label}: {f.pricing_annual_amount}€/an"
                    )

                if result.cheapest:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"\n  → Moins chère: {result.cheapest.product_composition_label} "
                            f"à {result.cheapest.pricing_annual_amount}€/an"
                        )
                    )
            else:
                self.stdout.write(
                    self.style.WARNING("Aucune formule disponible pour ce bien")
                )

        except MilaAPIError as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Erreur API: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Erreur: {e}"))
        finally:
            client.close()

    def _test_with_location(self, location_id: str):
        """Test avec une location existante."""
        from location.models import Location

        self.stdout.write(f"\n=== Test Mila MRH avec location {location_id} ===\n")

        try:
            location = Location.objects.select_related("bien__adresse").get(
                id=location_id
            )
        except Location.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Location {location_id} non trouvée"))
            return

        if not location.bien:
            self.stdout.write(self.style.ERROR("Cette location n'a pas de bien associé"))
            return

        bien = location.bien
        self.stdout.write(f"Bien: {bien.type_bien} - {bien.adresse}")
        self.stdout.write(f"Surface: {bien.superficie}m² - Étage: {bien.etage}")

        client = MilaMRHClient()

        try:
            result = client.get_quotation_from_bien(bien)

            if result.has_results:
                self.stdout.write(
                    self.style.SUCCESS(f"\n✓ {len(result.formulas)} formules:\n")
                )
                for f in result.formulas:
                    self.stdout.write(
                        f"  - {f.product_composition_label}: {f.pricing_annual_amount}€/an"
                    )
            else:
                self.stdout.write(
                    self.style.WARNING("Aucune formule disponible")
                )

        except MilaAPIError as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Erreur API: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Erreur: {e}"))
        finally:
            client.close()
