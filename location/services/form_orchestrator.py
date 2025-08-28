"""
Service orchestrateur pour les formulaires adaptatifs.
Architecture simplifiée - Le backend retourne uniquement les steps avec données manquantes.
"""

from typing import Any, Dict, Optional

from location.models import Location


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

        # Filtrer les steps pour ne garder que celles avec données manquantes
        steps = []
        for step_id, config in step_config.items():
            # Vérifier si cette step a des données complètes
            if self._step_has_complete_data(step_id, config, existing_data):
                continue

            step_def = {
                "id": step_id,
                "order": config.get("order", 999),
            }

            # Ajouter la condition si elle existe
            if "condition" in config:
                step_def["condition"] = config["condition"]

            steps.append(step_def)

        # Trier les steps par ordre
        steps = sorted(steps, key=lambda x: x["order"])

        return {
            "country": country,
            "form_type": form_type,
            "steps": steps,
            "prefill_data": existing_data,
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

    def _get_step_config(self, serializer_class, form_type: str) -> Dict[str, Any]:
        """
        Obtient la configuration des steps depuis le serializer.
        Raise une erreur si pas de config définie.
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
        """Vérifie si un champ a une valeur non vide dans les données."""
        parts = field_path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
                # Considérer None, "", [], {} comme vides
                if current is None or current == "" or current == [] or current == {}:
                    return False
            else:
                return False

        return True

    def _extract_location_data(self, location: Location) -> Dict[str, Any]:
        """
        Extrait les données d'une Location pour pré-remplissage.
        Format aligné avec les serializers.
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
            "modalites_financieres": {},
            "dates": {},
            "modalites_zone_tendue": {},
        }

        # RentTerms pour les données financières
        rent_terms = None
        if hasattr(location, "rent_terms"):
            rent_terms = location.rent_terms

        # Données du bien
        if location.bien:
            bien = location.bien

            # Localisation
            if bien.adresse:
                data["bien"]["localisation"]["adresse"] = bien.adresse
                if bien.latitude:
                    data["bien"]["localisation"]["latitude"] = bien.latitude
                if bien.longitude:
                    data["bien"]["localisation"]["longitude"] = bien.longitude

            # Caractéristiques
            if bien.superficie or bien.type_bien:
                data["bien"]["caracteristiques"] = {
                    "superficie": bien.superficie,
                    "type_bien": bien.type_bien,
                    "etage": bien.etage or "",
                    "porte": bien.porte or "",
                    "dernier_etage": bien.dernier_etage,
                    "meuble": bien.meuble,
                }
                if bien.pieces_info:
                    data["bien"]["caracteristiques"]["pieces_info"] = bien.pieces_info

            # Performance énergétique
            if bien.classe_dpe:
                data["bien"]["performance_energetique"] = {
                    "classe_dpe": bien.classe_dpe,
                    "depenses_energetiques": bien.depenses_energetiques or "",
                }

            # Régime juridique
            if hasattr(bien, "regime_juridique"):
                data["bien"]["regime"] = {
                    "regime_juridique": bien.regime_juridique or "monopropriete",
                    "periode_construction": bien.periode_construction or "",
                    "identifiant_fiscal": getattr(bien, "identifiant_fiscal", ""),
                }

            # Zone réglementaire
            if rent_terms:
                data["bien"]["zone_reglementaire"]["zone_tendue"] = (
                    rent_terms.zone_tendue
                )

            # Équipements et énergie
            if hasattr(bien, "chauffage_type"):
                data["bien"]["energie"]["chauffage"] = {
                    "type": bien.chauffage_type or "",
                    "energie": bien.chauffage_energie or "",
                }
            if hasattr(bien, "eau_chaude_type"):
                data["bien"]["energie"]["eau_chaude"] = {
                    "type": bien.eau_chaude_type or "",
                    "energie": bien.eau_chaude_energie or "",
                }

        # Données du bailleur
        if location.bien and location.bien.bailleurs.exists():
            bailleur = location.bien.bailleurs.first()
            if bailleur:
                data["bailleur"]["bailleur_type"] = bailleur.bailleur_type

                if bailleur.bailleur_type == "physique" and bailleur.personne:
                    personne = bailleur.personne
                    data["bailleur"]["personne"] = {
                        "lastName": personne.lastName,
                        "firstName": personne.firstName,
                        "email": personne.email or "",
                        "adresse": personne.adresse or "",
                    }
                elif bailleur.bailleur_type == "morale" and bailleur.societe:
                    societe = bailleur.societe
                    data["bailleur"]["societe"] = {
                        "raison_sociale": societe.raison_sociale,
                        "siret": societe.siret or "",
                        "forme_juridique": societe.forme_juridique or "",
                        "adresse": societe.adresse or "",
                        "email": societe.email or "",
                    }
                    if bailleur.signataire:
                        data["bailleur"]["signataire"] = {
                            "lastName": bailleur.signataire.lastName,
                            "firstName": bailleur.signataire.firstName,
                            "email": bailleur.signataire.email or "",
                        }

        # Locataires
        if location.locataires.exists():
            data["locataires"] = [
                {
                    "firstName": loc.firstName,
                    "lastName": loc.lastName,
                    "email": loc.email or "",
                }
                for loc in location.locataires.all()
            ]
            data["solidaires"] = location.solidaires

        # Modalités financières
        if rent_terms:
            data["modalites_financieres"] = {
                "loyer_mensuel": float(rent_terms.montant_loyer)
                if rent_terms.montant_loyer
                else None,
                "charges_mensuelles": float(rent_terms.montant_charges)
                if rent_terms.montant_charges
                else None,
            }

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

        # Dates
        if location.date_debut:
            data["dates"]["date_debut"] = location.date_debut.isoformat()
        if location.date_fin:
            data["dates"]["date_fin"] = location.date_fin.isoformat()

        return data
