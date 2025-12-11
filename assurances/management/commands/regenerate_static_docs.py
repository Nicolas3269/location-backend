"""
Commande pour régénérer les documents statiques (DER, CGV).

Usage:
    python manage.py regenerate_static_docs          # Régénère tous les documents
    python manage.py regenerate_static_docs --type DER  # Régénère seulement le DER
    python manage.py regenerate_static_docs --type CGV_MRH  # Régénère seulement les CGV MRH
"""

from django.core.management.base import BaseCommand

from assurances.models import StaticDocument


class Command(BaseCommand):
    help = "Régénère les documents statiques (DER, CGV)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            type=str,
            help="Type de document à régénérer (DER, CGV_MRH, CGV_PNO, CGV_GLI). Si non spécifié, régénère tous.",
        )

    def handle(self, *args, **options):
        doc_type = options.get("type")

        if doc_type:
            # Régénérer un seul type
            self.regenerate_document(doc_type)
        else:
            # Régénérer tous les types
            for doc_type_choice in StaticDocument.DocumentType.values:
                self.regenerate_document(doc_type_choice)

        self.stdout.write(self.style.SUCCESS("✅ Régénération terminée"))

    def regenerate_document(self, doc_type: str):
        self.stdout.write(f"📄 Régénération de {doc_type}...")
        try:
            doc = StaticDocument.get_or_generate(doc_type, force_regenerate=True)
            self.stdout.write(
                self.style.SUCCESS(f"   ✓ {doc_type} → {doc.url}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"   ✗ Erreur pour {doc_type}: {e}")
            )
