import time
from typing import List

from django.core.management.base import BaseCommand
from django.db import connections, transaction

from rent_control.models import RentControlArea, RentPrice


class Command(BaseCommand):
    help = (
        "Migre les données rent_control de la DB locale vers Production "
        "en utilisant Django ORM"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Taille des batches pour l'insertion (défaut: 1000)",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Simulation sans écriture en base"
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force la migration même si des données existent déjà",
        )
        parser.add_argument(
            "--clear-target",
            action="store_true",
            help="Vide les tables de destination avant migration",
        )

    def handle(self, *args, **options):
        self.batch_size = options["batch_size"]
        self.dry_run = options["dry_run"]
        self.force = options["force"]
        self.clear_target = options["clear_target"]

        self.stdout.write(
            self.style.SUCCESS("🚀 Démarrage de la migration rent_control")
        )

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  Mode DRY-RUN activé - aucune modification ne sera effectuée"
                )
            )

        try:
            self.setup_databases()
            self.migrate_data()

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Erreur durant la migration: {str(e)}")
            )
            raise

    def setup_databases(self):
        """Teste les connexions vers les bases de données"""

        self.stdout.write("🔗 Test des connexions...")

        # Test connexion par défaut (production)
        try:
            default_cursor = connections["default"].cursor()
            default_cursor.execute("SELECT version();")
            self.stdout.write(
                self.style.SUCCESS("✅ Connexion default (production) OK")
            )
        except Exception as e:
            raise ConnectionError(f"Connexion default échouée: {str(e)}")

        # Test connexion locale
        try:
            local_cursor = connections["local"].cursor()
            local_cursor.execute("SELECT version();")
            self.stdout.write(self.style.SUCCESS("✅ Connexion local OK"))
        except Exception as e:
            raise ConnectionError(f"Connexion local échouée: {str(e)}")

    def migrate_data(self):
        """Effectue la migration des données"""

        start_time = time.time()

        # Nettoyage si demandé (AVANT la vérification)
        if self.clear_target and not self.dry_run:
            self.clear_target_data()

        # Vérification des données existantes
        if not self.force:
            self.check_existing_data()

        # Migration des RentControlArea
        areas_count = self.migrate_rent_control_areas()

        # Migration des RentPrice
        prices_count = self.migrate_rent_prices()

        elapsed_time = time.time() - start_time

        self.stdout.write(
            self.style.SUCCESS(
                f"🎉 Migration terminée en {elapsed_time:.2f}s\n"
                f"   - {areas_count} RentControlArea migrées\n"
                f"   - {prices_count} RentPrice migrées"
            )
        )

    def check_existing_data(self):
        """Vérifie s'il y a déjà des données dans la base de destination"""

        # Utiliser la connexion default (production) pour vérifier
        prod_areas_count = RentControlArea.objects.using("default").count()
        prod_prices_count = RentPrice.objects.using("default").count()

        if prod_areas_count > 0 or prod_prices_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  Des données existent déjà en production:\n"
                    f"   - {prod_areas_count} RentControlArea\n"
                    f"   - {prod_prices_count} RentPrice\n"
                    f"   Utilisez --force pour continuer ou --clear-target pour vider"
                )
            )
            if not self.force:
                raise ValueError(
                    "Données existantes trouvées. Utilisez --force ou --clear-target"
                )

    def clear_target_data(self):
        """Vide les tables de destination"""

        self.stdout.write("🗑️  Nettoyage des données de destination...")

        with transaction.atomic(using="default"):
            # Supprimer dans l'ordre (relations M2M d'abord)
            RentPrice.objects.using("default").all().delete()
            RentControlArea.objects.using("default").all().delete()

        self.stdout.write(self.style.SUCCESS("✅ Tables de destination vidées"))

    def migrate_rent_control_areas(self) -> int:
        """Migre les RentControlArea"""

        self.stdout.write("📍 Migration des RentControlArea...")

        # Récupération depuis la base locale
        local_areas = RentControlArea.objects.using("local").all()
        total_areas = local_areas.count()

        if total_areas == 0:
            self.stdout.write(
                self.style.WARNING("⚠️  Aucune RentControlArea trouvée en local")
            )
            return 0

        self.stdout.write(f"📊 {total_areas} RentControlArea à migrer")

        migrated_count = 0
        batch = []

        # Mapping pour les IDs (local -> Prod)
        id_mapping = {}

        for i, area in enumerate(local_areas.iterator(chunk_size=self.batch_size)):
            # Créer une nouvelle instance pour Production
            new_area = RentControlArea(
                region=area.region,
                reference_year=area.reference_year,
                zone_id=area.zone_id,
                quartier_id=area.quartier_id,
                zone_name=area.zone_name,
                geometry=area.geometry,
            )

            batch.append(new_area)

            # Insertion par batch
            if len(batch) >= self.batch_size or i == total_areas - 1:
                if not self.dry_run:
                    try:
                        with transaction.atomic(using="default"):
                            created_areas = RentControlArea.objects.using(
                                "default"
                            ).bulk_create(batch, batch_size=self.batch_size)

                            # Mapper les IDs pour les relations M2M
                            for orig_area, new_area in zip(
                                local_areas[
                                    migrated_count : migrated_count + len(batch)
                                ],
                                created_areas,
                            ):
                                id_mapping[orig_area.id] = new_area.id

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f"❌ Erreur batch RentControlArea: {str(e)}"
                            )
                        )
                        raise

                migrated_count += len(batch)
                progress = (migrated_count / total_areas) * 100

                self.stdout.write(
                    f"📍 {migrated_count}/{total_areas} "
                    f"RentControlArea ({progress:.1f}%)"
                )

                batch = []

        # Stocker le mapping pour les relations M2M
        self.area_id_mapping = id_mapping

        return migrated_count

    def migrate_rent_prices(self) -> int:
        """Migre les RentPrice avec leurs relations M2M"""

        self.stdout.write("💰 Migration des RentPrice...")

        local_prices = RentPrice.objects.using("local").prefetch_related("areas")
        total_prices = local_prices.count()

        if total_prices == 0:
            self.stdout.write(
                self.style.WARNING("⚠️  Aucune RentPrice trouvée en local")
            )
            return 0

        self.stdout.write(f"📊 {total_prices} RentPrice à migrer")

        migrated_count = 0
        batch = []
        m2m_relations = []

        for i, price in enumerate(local_prices.iterator(chunk_size=self.batch_size)):
            # Créer une nouvelle instance pour Production
            new_price = RentPrice(
                reference_year=price.reference_year,
                property_type=price.property_type,
                room_count=price.room_count,
                construction_period=price.construction_period,
                furnished=price.furnished,
                reference_price=price.reference_price,
                min_price=price.min_price,
                max_price=price.max_price,
            )

            batch.append(new_price)

            # Stocker les relations M2M pour plus tard
            area_ids = [self.area_id_mapping.get(area.id) for area in price.areas.all()]
            area_ids = [aid for aid in area_ids if aid is not None]  # Filtrer les None
            m2m_relations.append(area_ids)

            # Insertion par batch
            if len(batch) >= self.batch_size or i == total_prices - 1:
                if not self.dry_run:
                    try:
                        with transaction.atomic(using="default"):
                            # Créer les RentPrice
                            created_prices = RentPrice.objects.using(
                                "default"
                            ).bulk_create(batch, batch_size=self.batch_size)

                            # Créer les relations M2M
                            self.create_m2m_relations(
                                created_prices, m2m_relations[: len(batch)]
                            )

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"❌ Erreur batch RentPrice: {str(e)}")
                        )
                        raise

                migrated_count += len(batch)
                progress = (migrated_count / total_prices) * 100

                self.stdout.write(
                    f"💰 {migrated_count}/{total_prices} RentPrice ({progress:.1f}%)"
                )

                batch = []
                m2m_relations = []  # Reset aussi les relations M2M

        return migrated_count

    def create_m2m_relations(
        self, created_prices: List[RentPrice], m2m_relations: List[List[int]]
    ):
        """Crée les relations M2M entre RentPrice et RentControlArea"""

        for price, area_ids in zip(created_prices, m2m_relations):
            if area_ids:
                # Utiliser add() pour créer les relations M2M
                areas = RentControlArea.objects.using("default").filter(id__in=area_ids)
                price.areas.set(areas)
