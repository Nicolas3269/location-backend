"""
Service orchestrateur pour les formulaires adaptatifs.
Architecture simplifiée - Le backend retourne uniquement les steps avec données manquantes.
"""

from typing import Any, Dict, List, Optional

from location.models import Bien, Location, RentTerms
from rent_control.views import get_rent_control_info


class FormOrchestrator:
    """
    Orchestrateur minimaliste pour les formulaires adaptatifs.

    Responsabilités:
    1. Déterminer quelles steps ont des données manquantes
    2. Retourner la liste des steps à afficher avec leur ordre
    3. Fournir les données existantes pour pré-remplissage
    """

    def get_form_requirements(
        self, form_type: str, location_id: Optional[str] = None, country: str = "FR"
    ) -> Dict[str, Any]:
        """
        Point d'entrée pour obtenir les requirements d'un formulaire.

        Returns:
            - steps: Liste des steps avec données manquantes (ordonnées)
            - prefill_data: Données existantes pour pré-remplissage
        """
        # Validation du type de formulaire
        valid_types = ["bail", "quittance", "etat_lieux"]
        if form_type not in valid_types:
            return {
                "error": f"Invalid form type. Must be one of: {', '.join(valid_types)}"
            }

        # Obtenir le serializer approprié
        serializer_class = self._get_serializer_class(form_type, country)
        if not serializer_class:
            return {"error": f"No serializer found for {form_type} in {country}"}

        # Obtenir les données existantes si location_id fourni
        existing_data = {}
        if location_id:
            try:
                location = Location.objects.get(id=location_id)
                existing_data = self._extract_location_data(location)
            except Location.DoesNotExist:
                return {"error": "Location not found"}

        # Obtenir la configuration des steps depuis le serializer
        step_config = self._get_step_config(serializer_class, form_type)

        # Obtenir d'abord les steps verrouillées si c'est une mise à jour
        locked_steps = set()
        if location_id:
            import logging

            from .field_locking import FieldLockingService

            logger = logging.getLogger(__name__)

            locked_steps = FieldLockingService.get_locked_steps(location_id, country)
            if locked_steps:
                logger.info(
                    f"Found {len(locked_steps)} locked steps for location {location_id}"
                )

        # Enrichir les steps avec les infos de validation depuis les Field Mappings

        # Filtrer les steps : garder seulement celles qui sont non verrouillées
        # Les steps avec données existantes sont gardées (pour permettre modification)
        steps = []
        for step in step_config:
            step_id = step["id"]

            # Si la step est verrouillée, on la skip
            if step_id in locked_steps:
                logger.debug(f"Skipping locked step: {step_id}")
                continue

            # Copier la step SANS les fields (qui contiennent des objets Django non sérialisables)
            step_copy = {k: v for k, v in step.items() if k != "fields"}

            # Enrichir avec les infos du Field Mapping si disponibles
            step_full_config = serializer_class.get_step_config_by_id(step_id)
            if step_full_config:
                # Ajouter les business rules
                if "business_rules" in step_full_config:
                    step_copy["business_rules"] = step_full_config["business_rules"]

                # Ajouter le flag always_unlocked
                if "always_unlocked" in step_full_config:
                    step_copy["always_unlocked"] = step_full_config["always_unlocked"]

                # Ajouter les required_fields définis explicitement
                if "required_fields" in step_full_config:
                    step_copy["required_fields"] = step_full_config["required_fields"]

                # Extraire les champs mappés (pour info seulement, pas pour validation)
                mapped_fields = []
                fields = step_full_config.get("fields", {})
                for field_path in fields.keys():
                    mapped_fields.append(field_path)

                if mapped_fields:
                    step_copy["mapped_fields"] = mapped_fields

            # Si une valeur par défaut est définie et qu'il n'y a pas de données existantes
            # on ajoute la valeur par défaut dans les données de pré-remplissage
            if "default" in step and not self._field_has_value(step_id, existing_data):
                self._set_field_value(step_id, step["default"], existing_data)

            steps.append(step_copy)

        return {
            "country": country,
            "form_type": form_type,
            "steps": steps,
            "prefill_data": existing_data,
            "locked_steps_count": len(locked_steps) if location_id else 0,
        }

    def _get_serializer_class(self, form_type: str, country: str):
        """Retourne la classe de serializer appropriée."""
        from location.serializers import (
            BelgiumBailSerializer,
            BelgiumEtatLieuxSerializer,
            BelgiumQuittanceSerializer,
            FranceBailSerializer,
            FranceEtatLieuxSerializer,
            FranceQuittanceSerializer,
        )

        serializers_map = {
            "FR": {
                "bail": FranceBailSerializer,
                "quittance": FranceQuittanceSerializer,
                "etat_lieux": FranceEtatLieuxSerializer,
            },
            "BE": {
                "bail": BelgiumBailSerializer,
                "quittance": BelgiumQuittanceSerializer,
                "etat_lieux": BelgiumEtatLieuxSerializer,
            },
        }

        return serializers_map.get(country, {}).get(form_type)

    def _get_step_config(
        self, serializer_class, form_type: str
    ) -> List[Dict[str, Any]]:
        """
        Obtient la configuration des steps depuis le serializer.
        Retourne maintenant une liste ordonnée au lieu d'un dict.
        """
        if not hasattr(serializer_class, "get_step_config"):
            raise ValueError(
                f"Le serializer {serializer_class.__name__} doit implémenter get_step_config()"
            )

        return serializer_class.get_step_config()

    def _step_has_complete_data(
        self, step_id: str, config: Dict, existing_data: Dict
    ) -> bool:
        """
        Vérifie si une step a ses données complètes.
        Maintenant que l'ID de la step EST le chemin du field,
        on vérifie directement si ce field a une valeur.
        """
        # L'ID de la step est maintenant le chemin complet du field
        # Ex: "bien.localisation.adresse", "bailleur.personne", etc.
        return self._field_has_value(step_id, existing_data)

    def _field_has_value(self, field_path: str, data: Dict) -> bool:
        """
        Vérifie si un champ a une valeur dans les données.

        IMPORTANT:
        - None ou champ manquant = pas de valeur (step à afficher)
        - [], {}, "" = valeur explicitement vide (step à NE PAS afficher)
        """
        parts = field_path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
                # Seul None est considéré comme "pas de valeur"
                # [], {}, "" sont des valeurs explicites (vides mais définies)
                if current is None:
                    return False
            else:
                # Champ manquant = pas de valeur
                return False

        return True

    def _set_field_value(self, field_path: str, value: Any, data: Dict) -> None:
        """
        Définit une valeur dans les données en créant la structure nécessaire.

        Args:
            field_path: Chemin du champ (ex: "bien.equipements.annexes_privatives")
            value: Valeur à définir
            data: Dictionnaire de données à modifier
        """
        parts = field_path.split(".")
        current = data

        # Naviguer jusqu'au parent du champ final
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Définir la valeur finale
        current[parts[-1]] = value

    def _extract_location_data(self, location: Location) -> Dict[str, Any]:
        """
        Extrait les données d'une Location pour pré-remplissage.
        Format aligné avec les serializers.

        Note: Cette fonction fait du mapping inverse (modèle -> formulaire).
        Les field mappings du serializer sont dans l'autre sens (formulaire -> modèle),
        donc on garde le mapping manuel pour l'instant.
        """
        data = {
            "bien": {
                "localisation": {},
                "caracteristiques": {},
                "performance_energetique": {},
                "equipements": {},
                "energie": {},
                "regime": {},
                "zone_reglementaire": {},
            },
            "bailleur": {},
            "locataires": [],
            # Ne pas initialiser ces champs avec {}, les laisser non définis
            # jusqu'à ce qu'on ait vraiment des données
            # "modalites_financieres": {},
            # "dates": {},
            # "modalites_zone_tendue": {},
        }

        # RentTerms pour les données financières
        rent_terms = None
        if hasattr(location, "rent_terms"):
            rent_terms: RentTerms = location.rent_terms

        # Données du bien
        if location.bien:
            bien: Bien = location.bien

            # Localisation
            if bien.adresse:
                data["bien"]["localisation"]["adresse"] = bien.adresse
                if bien.latitude:
                    data["bien"]["localisation"]["latitude"] = bien.latitude
                if bien.longitude:
                    data["bien"]["localisation"]["longitude"] = bien.longitude
                # Ajouter area_id
                if bien.latitude and bien.longitude:
                    _, area = get_rent_control_info(bien.latitude, bien.longitude)
                    if area:
                        data["bien"]["localisation"]["area_id"] = area.id

            # Caractéristiques
            if bien.superficie or bien.type_bien:
                data["bien"]["caracteristiques"] = {
                    "superficie": bien.superficie,
                    "type_bien": bien.type_bien,
                    "etage": bien.etage if bien.etage else None,
                    "porte": bien.porte if bien.porte else None,
                    "dernier_etage": bien.dernier_etage,
                    "meuble": bien.meuble,
                }
                if bien.pieces_info:
                    data["bien"]["caracteristiques"]["pieces_info"] = bien.pieces_info

            # Performance énergétique
            if bien.classe_dpe:
                data["bien"]["performance_energetique"] = {
                    "classe_dpe": bien.classe_dpe,
                    "depenses_energetiques": bien.depenses_energetiques
                    if bien.depenses_energetiques
                    else None,
                }

            # Régime juridique
            if hasattr(bien, "regime_juridique"):
                data["bien"]["regime"] = {
                    "regime_juridique": bien.regime_juridique or "monopropriete",
                    "periode_construction": bien.periode_construction,
                    "identifiant_fiscal": bien.identifiant_fiscal,
                }

            # Zone réglementaire
            if rent_terms:
                data["bien"]["zone_reglementaire"]["zone_tendue"] = (
                    rent_terms.zone_tendue
                )

            # Équipements
            # Important: ne mettre les listes que si elles ont été définies (même vides)
            # Une liste vide [] signifie "pas d'équipements" (défini)
            # None signifie "non renseigné" (non défini)
            if (
                hasattr(bien, "annexes_privatives")
                and bien.annexes_privatives is not None
            ):
                if "equipements" not in data["bien"]:
                    data["bien"]["equipements"] = {}
                data["bien"]["equipements"]["annexes_privatives"] = (
                    bien.annexes_privatives
                )

            if (
                hasattr(bien, "annexes_collectives")
                and bien.annexes_collectives is not None
            ):
                if "equipements" not in data["bien"]:
                    data["bien"]["equipements"] = {}
                data["bien"]["equipements"]["annexes_collectives"] = (
                    bien.annexes_collectives
                )

            if hasattr(bien, "information") and bien.information is not None:
                if "equipements" not in data["bien"]:
                    data["bien"]["equipements"] = {}
                data["bien"]["equipements"]["information"] = bien.information

            # Énergie - ne créer l'objet que si on a des valeurs non-None
            if hasattr(bien, "chauffage_type") and bien.chauffage_type is not None:
                chauffage_data = {"type": bien.chauffage_type}
                if bien.chauffage_energie is not None:
                    chauffage_data["energie"] = bien.chauffage_energie
                data["bien"]["energie"]["chauffage"] = chauffage_data

            if hasattr(bien, "eau_chaude_type") and bien.eau_chaude_type is not None:
                eau_chaude_data = {"type": bien.eau_chaude_type}
                if bien.eau_chaude_energie is not None:
                    eau_chaude_data["energie"] = bien.eau_chaude_energie
                data["bien"]["energie"]["eau_chaude"] = eau_chaude_data

        # Données du bailleur
        if location.bien and location.bien.bailleurs.exists():
            bailleur = location.bien.bailleurs.first()
            if bailleur:
                # Mapper "personne" vers "physique" pour cohérence avec le frontend
                bailleur_type = (
                    "physique"
                    if bailleur.personne
                    else "morale"
                    if bailleur.societe
                    else None
                )
                data["bailleur"]["bailleur_type"] = bailleur_type

                if bailleur_type == "physique" and bailleur.personne:
                    personne = bailleur.personne
                    data["bailleur"]["personne"] = {
                        "lastName": personne.lastName,
                        "firstName": personne.firstName,
                        "email": personne.email,
                        "adresse": personne.adresse,
                    }
                elif bailleur_type == "morale" and bailleur.societe:
                    societe = bailleur.societe
                    data["bailleur"]["societe"] = {
                        "raison_sociale": societe.raison_sociale,
                        "siret": societe.siret,
                        "forme_juridique": societe.forme_juridique,
                        "adresse": societe.adresse,
                        "email": societe.email,
                    }
                    if bailleur.signataire:
                        data["bailleur"]["signataire"] = {
                            "lastName": bailleur.signataire.lastName,
                            "firstName": bailleur.signataire.firstName,
                            "email": bailleur.signataire.email,
                        }

                # Extraire les co-bailleurs (tous sauf le premier)
                all_bailleurs = list(location.bien.bailleurs.all())
                if len(all_bailleurs) > 1:
                    # Il y a des co-bailleurs
                    co_bailleurs_list = []
                    for co_bailleur in all_bailleurs[1:]:
                        if co_bailleur.personne:
                            co_bailleurs_list.append(
                                {
                                    "lastName": co_bailleur.personne.lastName,
                                    "firstName": co_bailleur.personne.firstName,
                                    "email": co_bailleur.personne.email,
                                    "adresse": co_bailleur.personne.adresse,
                                }
                            )
                    if co_bailleurs_list:
                        data["bailleur"]["co_bailleurs"] = co_bailleurs_list
                else:
                    # Explicitement mettre une liste vide si pas de co-bailleurs
                    data["bailleur"]["co_bailleurs"] = []

        # Locataires
        if location.locataires.exists():
            data["locataires"] = [
                {
                    "firstName": loc.firstName,
                    "lastName": loc.lastName,
                    "email": loc.email,
                }
                for loc in location.locataires.all()
            ]
            data["solidaires"] = location.solidaires

        # Modalités financières - seulement si on a des valeurs
        if rent_terms and (rent_terms.montant_loyer or rent_terms.montant_charges):
            data["modalites_financieres"] = {}
            if rent_terms.montant_loyer:
                data["modalites_financieres"]["loyer_hors_charges"] = float(
                    rent_terms.montant_loyer
                )
            if rent_terms.montant_charges:
                data["modalites_financieres"]["charges_mensuelles"] = float(
                    rent_terms.montant_charges
                )

            # Zone tendue - modalités spécifiques
            if rent_terms.zone_tendue:
                data["modalites_zone_tendue"] = {}
                if hasattr(rent_terms, "premiere_mise_en_location"):
                    data["modalites_zone_tendue"]["premiere_mise_en_location"] = (
                        rent_terms.premiere_mise_en_location
                    )
                if hasattr(rent_terms, "locataire_derniers_18_mois"):
                    data["modalites_zone_tendue"]["locataire_derniers_18_mois"] = (
                        rent_terms.locataire_derniers_18_mois
                    )
                if hasattr(rent_terms, "dernier_montant_loyer"):
                    data["modalites_zone_tendue"]["dernier_montant_loyer"] = (
                        float(rent_terms.dernier_montant_loyer)
                        if rent_terms.dernier_montant_loyer
                        else None
                    )

        # Dates - créer le dict seulement si on a des dates
        if location.date_debut or location.date_fin:
            data["dates"] = {}
            if location.date_debut:
                data["dates"]["date_debut"] = location.date_debut.isoformat()
            if location.date_fin:
                data["dates"]["date_fin"] = location.date_fin.isoformat()

        return data
