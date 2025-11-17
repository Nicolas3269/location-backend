import os

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from rent_control.models import ZoneTendueTouristique


class Command(BaseCommand):
    help = "Import zones tendues touristiques from ODS file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="algo/zone_tendue/zone_tendue_touristique.ods",
            help="Path to the ODS file relative to the project root",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of records to process in each batch",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before import",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        batch_size = options["batch_size"]
        clear_data = options["clear"]

        # Construct absolute file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(settings.BASE_DIR, file_path)

        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        self.stdout.write(f"Reading data from: {file_path}")

        try:
            # Read the ODS file
            df = pd.read_excel(file_path, engine="odf")

            # Display column names to help with mapping
            self.stdout.write(f"Columns found: {list(df.columns)}")

            # Clean column names (remove extra spaces, special characters)
            df.columns = df.columns.str.strip()

            self.stdout.write(f"Total records found: {len(df)}")

            if clear_data:
                self.stdout.write("Clearing existing data...")
                ZoneTendueTouristique.objects.all().delete()
                self.stdout.write("Existing data cleared.")

            # Process data in batches
            total_created = 0
            total_updated = 0

            for start_idx in range(0, len(df), batch_size):
                end_idx = min(start_idx + batch_size, len(df))
                batch_df = df.iloc[start_idx:end_idx]

                created, updated = self._process_batch(batch_df)
                total_created += created
                total_updated += updated

                self.stdout.write(
                    f"Processed batch {start_idx // batch_size + 1}: "
                    f"records {start_idx + 1}-{end_idx}, "
                    f"created: {created}, updated: {updated}"
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Import completed successfully! "
                    f"Total created: {total_created}, "
                    f"Total updated: {total_updated}"
                )
            )

        except Exception as e:
            raise CommandError(f"Error importing data: {str(e)}")

    def _process_batch(self, batch_df):
        """Process a batch of records"""
        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for _, row in batch_df.iterrows():
                try:
                    # Map columns based on ODS structure (plural form in file)
                    departement_code = self._clean_value(row.get("DÉPARTEMENTS", ""))
                    commune = self._clean_value(row.get("COMMUNES", ""))
                    code_insee = self._clean_value(row.get("CODE INSEE", ""))

                    if not departement_code or not commune or not code_insee:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Skipping row with missing required fields: "
                                f"{row.to_dict()}"
                            )
                        )
                        continue

                    # Use update_or_create to handle duplicates
                    # Unique key: code_insee
                    zone, created = ZoneTendueTouristique.objects.update_or_create(
                        code_insee=code_insee,
                        defaults={
                            "departement_code": departement_code,
                            "commune": commune,
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Error processing row {row.to_dict()}: {str(e)}"
                        )
                    )
                    continue

        return created_count, updated_count

    def _clean_value(self, value):
        """Clean and normalize a value from the DataFrame"""
        if pd.isna(value) or value is None:
            return None

        # Convert to string and strip whitespace
        cleaned = str(value).strip()

        # Return None for empty strings
        if not cleaned:
            return None

        return cleaned
