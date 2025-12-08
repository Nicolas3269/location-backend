"""
Commande Django pour migrer les adresses legacy vers le modèle Adresse structuré.

Utilise Google Geocoding API pour parser les adresses texte et les convertir
en format structuré (numero, voie, code_postal, ville, pays, lat/lng).

Usage:
    python manage.py migrate_legacy_addresses --dry-run  # Prévisualiser
    python manage.py migrate_legacy_addresses            # Exécuter
    python manage.py migrate_legacy_addresses --model=Bien  # Un seul modèle
"""

import time

import googlemaps
from django.conf import settings
from django.core.management.base import BaseCommand

from location.models import Adresse, Bien, Personne, Societe


class Command(BaseCommand):
    help = "Migre les adresses legacy vers le modèle Adresse via Google Geocoding"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche ce qui serait fait sans modifier la DB",
        )
        parser.add_argument(
            "--model",
            type=str,
            choices=["Bien", "Personne", "Societe"],
            help="Migrer uniquement un modèle spécifique",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limiter le nombre d'adresses à traiter",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        model_filter = options["model"]
        limit = options["limit"]

        # Vérifier la clé API Google
        api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", None)
        if not api_key:
            self.stderr.write(
                self.style.ERROR(
                    "GOOGLE_MAPS_API_KEY non configurée dans settings. "
                    "Ajoutez-la dans .env ou settings.py"
                )
            )
            return

        # Attention googlemps est une dependance dev
        gmaps = googlemaps.Client(key=api_key)

        # Stats
        stats = {"processed": 0, "success": 0, "failed": 0, "skipped": 0}

        # Traiter chaque modèle
        models_to_process = []
        if model_filter:
            models_to_process = [{"name": model_filter, "model": eval(model_filter)}]
        else:
            models_to_process = [
                {"name": "Bien", "model": Bien},
                {"name": "Personne", "model": Personne},
                {"name": "Societe", "model": Societe},
            ]

        for model_info in models_to_process:
            model_name = model_info["name"]
            model_class = model_info["model"]

            self.stdout.write(f"\n{'=' * 50}")
            self.stdout.write(self.style.HTTP_INFO(f"Traitement de {model_name}..."))

            # Récupérer les objets avec legacy mais sans adresse FK
            queryset = model_class.objects.filter(
                _adresse_legacy__isnull=False,
                adresse__isnull=True,
            ).exclude(_adresse_legacy="")

            if limit:
                queryset = queryset[:limit]

            count = queryset.count()
            self.stdout.write(f"  {count} adresses legacy à migrer")

            for obj in queryset:
                stats["processed"] += 1
                legacy = obj._adresse_legacy

                if dry_run:
                    self.stdout.write(f"  [DRY-RUN] {model_name} {obj.id}: {legacy}")
                    continue

                # Appeler Google Geocoding
                result = self._geocode_address(gmaps, legacy)

                if result:
                    # Créer ou récupérer l'adresse
                    adresse = self._create_adresse(result)
                    obj.adresse = adresse
                    obj.save(update_fields=["adresse"])

                    stats["success"] += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ {model_name} {obj.id}: {adresse}")
                    )
                else:
                    stats["failed"] += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"  ✗ {model_name} {obj.id}: Impossible de géocoder '{legacy}'"
                        )
                    )

                # Rate limiting (Google limite à 50 req/sec)
                time.sleep(0.1)

        # Résumé
        self.stdout.write(f"\n{'=' * 50}")
        self.stdout.write(self.style.HTTP_INFO("RÉSUMÉ:"))
        self.stdout.write(f"  Traitées: {stats['processed']}")
        self.stdout.write(self.style.SUCCESS(f"  Succès: {stats['success']}"))
        self.stdout.write(self.style.WARNING(f"  Échecs: {stats['failed']}"))

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\n[DRY-RUN] Aucune modification effectuée")
            )

    def _geocode_address(self, gmaps, address_text: str) -> dict | None:
        """Appelle Google Geocoding API et retourne les composants structurés."""
        try:
            results = gmaps.geocode(address_text, region="fr", language="fr")

            if not results:
                return None

            result = results[0]
            components = result.get("address_components", [])
            geometry = result.get("geometry", {}).get("location", {})

            return {
                "components": components,
                "lat": geometry.get("lat"),
                "lng": geometry.get("lng"),
                "formatted": result.get("formatted_address", ""),
            }
        except Exception as e:
            self.stderr.write(f"    Erreur API: {e}")
            return None

    def _create_adresse(self, geocode_result: dict) -> Adresse:
        """Crée un objet Adresse à partir du résultat Google Geocoding."""
        components = geocode_result["components"]

        def get_component(comp_type: str, use_short: bool = False) -> str:
            for comp in components:
                if comp_type in comp.get("types", []):
                    return comp.get("short_name" if use_short else "long_name", "")
            return ""

        numero = get_component("street_number") or None
        voie = get_component("route") or None
        code_postal = get_component("postal_code") or None
        ville = get_component("locality") or get_component(
            "administrative_area_level_2"
        )
        pays = get_component("country", use_short=True) or "FR"

        # Fallback pour la voie si non trouvée
        if not voie:
            formatted = geocode_result.get("formatted", "")
            first_part = formatted.split(",")[0].strip() if formatted else ""
            # Retirer le numéro du début si présent
            if first_part and numero and first_part.startswith(numero):
                voie = first_part[len(numero) :].strip() or None
            else:
                voie = first_part or None

        # Chercher une adresse existante identique pour éviter les doublons
        existing = Adresse.objects.filter(
            numero=numero,
            voie=voie,
            code_postal=code_postal,
            ville=ville,
            pays=pays,
        ).first()

        if existing:
            return existing

        # Créer nouvelle adresse
        adresse = Adresse.objects.create(
            numero=numero,
            voie=voie,
            code_postal=code_postal,
            ville=ville,
            pays=pays,
            latitude=geocode_result.get("lat"),
            longitude=geocode_result.get("lng"),
        )

        return adresse
