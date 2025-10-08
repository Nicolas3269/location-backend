"""
Management command pour créer un bail de test rapidement.

Usage:
    python manage.py create_test_bail
    python manage.py create_test_bail --locataires=2 --solidaires
    python manage.py create_test_bail --zone-tendue --status=signing
    python manage.py create_test_bail --adresse="12 Rue de la Paix, 75002 Paris"
"""

from django.core.management.base import BaseCommand
from location.factories import create_complete_bail
from signature.document_status import DocumentStatus


class Command(BaseCommand):
    help = "Crée un bail de test complet avec toutes les relations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--locataires",
            type=int,
            default=1,
            help="Nombre de locataires (default: 1)",
        )
        parser.add_argument(
            "--solidaires",
            action="store_true",
            help="Locataires solidaires",
        )
        parser.add_argument(
            "--zone-tendue",
            action="store_true",
            help="Bien en zone tendue",
        )
        parser.add_argument(
            "--status",
            type=str,
            default="draft",
            choices=["draft", "signing", "signed"],
            help="Statut du bail (default: draft)",
        )
        parser.add_argument(
            "--adresse",
            type=str,
            help="Adresse du bien (optionnel)",
        )

    def handle(self, *args, **options):
        num_locataires = options["locataires"]
        solidaires = options["solidaires"]
        zone_tendue = options["zone_tendue"]
        status_str = options["status"]
        adresse = options["adresse"]

        # Mapper le statut
        status_map = {
            "draft": DocumentStatus.DRAFT,
            "signing": DocumentStatus.SIGNING,
            "signed": DocumentStatus.SIGNED,
        }
        status = status_map[status_str]

        # Préparer les kwargs
        kwargs = {}
        if adresse:
            kwargs["location__bien__adresse"] = adresse

        # Créer le bail
        self.stdout.write(self.style.SUCCESS("Création du bail..."))

        bail = create_complete_bail(
            num_locataires=num_locataires,
            solidaires=solidaires,
            zone_tendue=zone_tendue,
            status=status,
            **kwargs
        )

        # Afficher les infos
        self.stdout.write(self.style.SUCCESS(f"\n✅ Bail créé avec succès!"))
        self.stdout.write(f"  ID: {bail.id}")
        self.stdout.write(f"  Location ID: {bail.location.id}")
        self.stdout.write(f"  Statut: {bail.status}")
        self.stdout.write(f"  Bien: {bail.location.bien.adresse}")
        self.stdout.write(f"  Bailleur(s): {', '.join([str(b) for b in bail.location.bien.bailleurs.all()])}")
        self.stdout.write(f"  Locataire(s): {', '.join([str(l) for l in bail.location.locataires.all()])}")
        self.stdout.write(f"  Solidaires: {'Oui' if bail.location.solidaires else 'Non'}")
        self.stdout.write(f"  Loyer: {bail.location.rent_terms.montant_loyer}€")
        self.stdout.write(f"  Charges: {bail.location.rent_terms.montant_charges}€")
        self.stdout.write(f"  Zone tendue: {'Oui' if bail.location.rent_terms.zone_tendue else 'Non'}")
