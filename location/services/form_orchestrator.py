"""
Service orchestrateur pour les formulaires adaptatifs.
Version nettoyée - Architecture basée sur les serializers par pays.
"""

from typing import Any, Dict, List, Optional

from location.models import Bailleur, Locataire, Location, Personne, RentTerms, Societe


class FormOrchestrator:
    """
    Orchestrateur pour la gestion des formulaires adaptatifs.

    Responsabilités:
    1. Déterminer les champs manquants via les serializers par pays
    2. Extraire les données existantes d'une Location
    3. Retourner les requirements pour le frontend
    """

    def get_form_requirements(
        self, form_type: str, location_id: Optional[str] = None, country: str = "FR"
    ) -> Dict[str, Any]:
        """
        Point d'entrée principal pour obtenir les requirements d'un formulaire.

        Args:
            form_type: Type de formulaire ('bail', 'quittance', 'etat_lieux')
            location_id: ID de la location existante (optionnel)
            country: Code pays (FR, BE, etc.)

        Returns:
            Dict contenant country, form_type, fields_status, prefill_data, etc.
        """
        # Validation du type de formulaire
        valid_types = ["bail", "quittance", "etat_lieux"]
        if form_type not in valid_types:
            return {
                "error": f"Invalid form type. Must be one of: {', '.join(valid_types)}"
            }

        # Cas 1: Nouveau formulaire (pas de location existante)
        if not location_id:
            return self._get_new_form_requirements(form_type, country)

        # Cas 2: Formulaire basé sur une location existante
        try:
            location = Location.objects.get(id=location_id)
            return self._get_adaptive_form_requirements(form_type, location, country)
        except Location.DoesNotExist:
            return {"error": "Location not found"}

    def _get_new_form_requirements(
        self, form_type: str, country: str = "FR"
    ) -> Dict[str, Any]:
        """
        Requirements pour un nouveau formulaire (sans données existantes).
        """
        # Analyser tous les champs requis (tout est manquant)
        fields_status = self._analyze_fields_status(form_type, {}, country)

        return {
            "country": country,
            "form_type": form_type,
            "fields_status": fields_status,
            "prefill_data": {},
            "readonly_fields": [],
            "context": {
                "location_exists": False,
                "is_new": True,
                "form_type": form_type,
            },
        }

    def _get_adaptive_form_requirements(
        self, form_type: str, location: Location, country: str = "FR"
    ) -> Dict[str, Any]:
        """
        Requirements adaptatifs basés sur une location existante.
        """
        from .location_analyzer import LocationAnalyzer

        # Analyser la complétude de la location
        analyzer = LocationAnalyzer()
        completeness = analyzer.analyze_completeness(location)

        # Extraire les données existantes
        existing_data = self._extract_location_data(location)

        # Analyser les champs manquants selon le serializer du pays
        # existing_data est déjà au format serializer
        fields_status = self._analyze_fields_status(form_type, existing_data, country)

        # Déterminer les champs en lecture seule
        readonly_fields = self._get_readonly_fields(location, existing_data)

        return {
            "country": country,
            "form_type": form_type,
            "fields_status": fields_status,
            "prefill_data": existing_data,
            "readonly_fields": readonly_fields,
            "context": {
                "location_exists": True,
                "location_id": str(location.id),
                "is_new": False,
                "form_type": form_type,
                "completion_rate": completeness["overall_completion"],
                "has_bail": completeness["documents"]["has_bail"],
                "has_quittances": completeness["documents"]["quittances_count"],
                "has_etat_lieux_entree": completeness["documents"][
                    "has_etat_lieux_entree"
                ],
            },
        }

    def _get_always_show_fields(self, form_type: str) -> List[str]:
        """
        Champs qui doivent toujours être affichés même s'ils sont optionnels.
        Ces champs seront ajoutés aux champs requis pour l'affichage.
        """
        if form_type == "bail":
            return [
                "bien.equipements.annexes_privatives",
                "bien.equipements.annexes_collectives",
                "bien.equipements.information",  # Équipements d'accès aux technologies
                "bien.energie.chauffage",  # Type de chauffage
                "bien.energie.eau_chaude",  # Type d'eau chaude
                "bien.performance_energetique.classe_dpe",  # DPE
                "bien.regime.identifiant_fiscal",  # Identifiant fiscal
                "bailleur.co_bailleurs",  # Autres co-bailleurs (optionnel mais important)
            ]
        elif form_type == "etat_lieux":
            return [
                "nombre_cles",  # Optionnel mais utile
                "equipements_chauffage",  # Optionnel mais utile
                "releve_compteurs",  # Optionnel mais utile
            ]
        return []

    def _get_field_order(self, form_type: str) -> List[str]:
        """
        Définit l'ordre d'affichage des champs pour chaque type de formulaire.
        """
        if form_type == "bail":
            return [
                # BIEN - Informations de base
                "bien.localisation.adresse",
                "bien.caracteristiques.type_bien",
                "bien.regime.regime_juridique",
                "bien.regime.periode_construction",
                "bien.caracteristiques.superficie",
                "bien.caracteristiques.pieces_info",
                "bien.caracteristiques.etage",
                "bien.caracteristiques.porte",
                "bien.caracteristiques.dernier_etage",
                "bien.equipements.annexes_privatives",
                "bien.equipements.annexes_collectives",
                "bien.caracteristiques.meuble",
                "bien.equipements.information",
                "bien.energie.chauffage",
                "bien.energie.eau_chaude",
                "bien.performance_energetique.classe_dpe",
                "bien.performance_energetique.depenses_energetiques",  # Juste après DPE
                "bien.regime.identifiant_fiscal",
                # zone_tendue est déterminée automatiquement via l'adresse
                # PERSONNES
                "bailleur.bailleur_type",
                "bailleur.personne",  # Conditionnel selon bailleur_type
                "bailleur.societe",  # Conditionnel selon bailleur_type
                "bailleur.co_bailleurs",  # Optionnel - autres co-bailleurs
                "locataires",
                "solidaires",  # Conditionnel si plusieurs locataires
                # MODALITÉS
                "dates.date_debut",
                # Zone tendue - juste après la date de début
                "modalites_zone_tendue.premiere_mise_en_location",
                "modalites_zone_tendue.locataire_derniers_18_mois",
                "modalites_zone_tendue.dernier_montant_loyer",
                # Modalités financières
                "modalites_financieres.loyer_mensuel",
                "modalites_financieres.charges_mensuelles",
                # Note: date_fin est optionnelle, sera ajoutée via always_show si nécessaire
            ]
        elif form_type == "quittance":
            return [
                "bien.localisation.adresse",
                "bien.caracteristiques.type_bien",
                "bien.regime.regime_juridique",
                "bien.regime.periode_construction",
                "bien.caracteristiques.superficie",
                "bien.caracteristiques.pieces_info",
                "bien.caracteristiques.etage",
                "bien.caracteristiques.porte",
                "bien.caracteristiques.dernier_etage",
                "bien.caracteristiques.meuble",
                # PERSONNES
                "bailleur.bailleur_type",
                "bailleur.personne",  # Conditionnel selon bailleur_type
                "bailleur.societe",  # Conditionnel selon bailleur_type
                "bailleur.co_bailleurs",  # Optionnel - autres co-bailleurs
                "locataires",
                "solidaires",  # Conditionnel si plusieurs locataires
                # QUITTANCE
                "modalites_financieres.loyer_mensuel",
                "modalites_financieres.charges_mensuelles",
                "periode_quittance",
            ]
        elif form_type == "etat_lieux":
            return [
                # BIEN - Informations de base
                "bien.localisation.adresse",
                "bien.caracteristiques.type_bien",
                "bien.regime.regime_juridique",
                "bien.regime.periode_construction",
                "bien.caracteristiques.superficie",
                "bien.caracteristiques.pieces_info",
                "bien.caracteristiques.etage",
                "bien.caracteristiques.porte",
                "bien.caracteristiques.dernier_etage",
                "bien.caracteristiques.meuble",
                "bien.energie.chauffage",
                "bien.energie.eau_chaude",
                # PERSONNES
                "bailleur.bailleur_type",
                "bailleur.personne",  # Conditionnel selon bailleur_type
                "bailleur.societe",  # Conditionnel selon bailleur_type
                "bailleur.co_bailleurs",  # Optionnel - autres co-bailleurs
                "locataires",
                "solidaires",  # Conditionnel si plusieurs locataires
                "type_etat_lieux",
                "date_etat_lieux",
                "description_pieces",
                "nombre_cles",
                "equipements_chauffage",
                "releve_compteurs",
            ]
        return []

    def _analyze_fields_status(
        self, form_type: str, existing_data: Dict, country: str = "FR"
    ) -> Dict[str, Any]:
        """
        Analyse les champs selon le serializer du pays.

        Returns:
            Dict avec:
            - required: Liste des champs obligatoires manquants (dans l'ordre défini)
            - conditional: Liste des champs conditionnels avec leur statut
            - optional: Liste des champs optionnels
        """
        # Importer les serializers par pays
        from location.serializers import (
            BelgiumBailSerializer,
            BelgiumEtatLieuxSerializer,
            BelgiumQuittanceSerializer,
            FranceBailSerializer,
            FranceEtatLieuxSerializer,
            FranceQuittanceSerializer,
        )

        # Mapping des serializers
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

        # Obtenir le bon serializer
        if country not in serializers_map:
            country = "FR"  # Défaut

        serializer_class = serializers_map[country].get(form_type)
        if not serializer_class:
            return {"required": [], "conditional": [], "optional": []}

        # Les données sont déjà au format serializer grâce à _extract_location_data
        # Instancier et valider directement
        serializer = serializer_class(data=existing_data)
        serializer.is_valid()

        # Résultat structuré
        fields_status = {
            "required": [],
            "conditional": [],
            "optional": [],
            "field_order": [],  # Ordre global de tous les champs
        }

        # 1. Extraire les champs requis manquants
        required_unordered = []
        if serializer.errors:
            for field_name in serializer.errors:
                if field_name != "non_field_errors":
                    # Mapper vers les chemins frontend (peut être plusieurs)
                    frontend_paths = self._serializer_field_to_frontend_path(field_name)
                    for path in frontend_paths:
                        if path not in required_unordered:
                            required_unordered.append(path)

        # Ajouter les champs qui doivent toujours être affichés (optionnels mais importants)
        always_show = self._get_always_show_fields(form_type)
        for field in always_show:
            if field not in required_unordered:
                required_unordered.append(field)

        # Appliquer l'ordre défini
        field_order = self._get_field_order(form_type)
        if field_order:
            # Trier les champs requis selon l'ordre défini
            ordered_required = []
            for field in field_order:
                if field in required_unordered:
                    ordered_required.append(field)
            # Ajouter les champs non prévus dans l'ordre à la fin
            for field in required_unordered:
                if field not in ordered_required:
                    ordered_required.append(field)
            fields_status["required"] = ordered_required
        else:
            fields_status["required"] = required_unordered

        # 2. Obtenir les champs conditionnels depuis le serializer
        if hasattr(serializer_class, "get_conditional_fields"):
            instance = serializer_class()
            conditional_fields = instance.get_conditional_fields()

            for field_config in conditional_fields:
                # Vérifier le statut actuel du champ
                field_path = field_config["field"]
                if self._is_field_present(field_path, existing_data):
                    field_config["status"] = "present"
                else:
                    # Si le champ n'est pas présent, il est potentiellement requis
                    # Le frontend décidera en fonction de la condition
                    field_config["status"] = "missing"

            fields_status["conditional"] = conditional_fields

        # 3. Les champs optionnels (non requis et sans condition)
        # Pour l'instant on ne les liste pas tous, mais on pourrait

        # 4. Créer l'ordre global incluant tous les champs (requis + conditionnels)
        field_order = self._get_field_order(form_type)
        if field_order:
            # Filtrer pour ne garder que les champs qui sont soit requis soit conditionnels
            all_active_fields = set(fields_status["required"])
            for cond_field in fields_status.get("conditional", []):
                all_active_fields.add(cond_field["field"])

            # Créer la liste ordonnée finale
            fields_status["field_order"] = [
                field for field in field_order if field in all_active_fields
            ]

            # Ajouter les champs actifs non prévus dans l'ordre à la fin
            for field in all_active_fields:
                if field not in fields_status["field_order"]:
                    fields_status["field_order"].append(field)

        return fields_status

    def _extract_location_data(self, location: Location) -> Dict[str, Any]:
        """
        Extrait les données d'une Location pour pré-remplissage.
        Retourne directement au format des serializers (structure imbriquée).
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
            "solidaires": False,
        }
        if hasattr(location, "rent_terms") and location.rent_terms:
            rent_terms: RentTerms = location.rent_terms

        # Données du bien
        if location.bien:
            bien = location.bien

            # Localisation
            data["bien"]["localisation"]["adresse"] = bien.adresse
            if bien.latitude:
                data["bien"]["localisation"]["latitude"] = bien.latitude
            if bien.longitude:
                data["bien"]["localisation"]["longitude"] = bien.longitude

            # Caractéristiques
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
                    "depenses_energetiques": bien.depenses_energetiques,
                }

            # Zone réglementaire - zone_tendue est dans RentTerms (OneToOne)
            if hasattr(location, "rent_terms") and location.rent_terms:
                data["bien"]["zone_reglementaire"]["zone_tendue"] = (
                    rent_terms.zone_tendue
                )
            else:
                data["bien"]["zone_reglementaire"]["zone_tendue"] = False

        # Données du bailleur - les bailleurs sont sur le Bien, pas la Location
        if location.bien and location.bien.bailleurs.exists():
            bailleur: Bailleur = (
                location.bien.bailleurs.first()
            )  # Prendre le premier bailleur principal
            if bailleur:
                data["bailleur"] = {
                    "bailleur_type": bailleur.bailleur_type,
                }

                # Si personne physique
                if bailleur.bailleur_type == "physique":
                    personne: Personne = bailleur.personne
                    data["bailleur"]["personne"] = {
                        "lastName": personne.lastName if personne else "",
                        "firstName": personne.firstName if personne else "",
                        "email": personne.email if personne else "",
                        "adresse": personne.adresse if personne else "",
                    }
                # Si personne morale
                elif bailleur.bailleur_type == "morale":
                    societe: Societe = bailleur.societe
                    data["bailleur"]["societe"] = {
                        "raison_sociale": societe.raison_sociale if societe else "",
                        "siret": societe.siret if societe else "",
                        "forme_juridique": societe.forme_juridique if societe else "",
                        "adresse": societe.adresse if societe else "",
                        "email": societe.email if societe else "",
                    }
                    # Le signataire (représentant de la société)
                    signataire: Personne = bailleur.signataire
                    if not signataire:
                        raise ValueError("Bailleur signataire manquant")
                    data["bailleur"]["signataire"] = {
                        "lastName": signataire.lastName,
                        "firstName": signataire.firstName,
                        "email": signataire.email,
                    }

                # Co-bailleurs (si présents) - ils sont sur le Bien
                autres_bailleurs: list[Bailleur] = location.bien.bailleurs.exclude(
                    id=bailleur.id
                )
                if autres_bailleurs.exists():
                    data["bailleur"]["co_bailleurs"] = [
                        {
                            "lastName": b.personne.lastName
                            if b.personne
                            else b.societe.raison_sociale,
                            "firstName": b.personne.firstName if b.personne else "",
                            "email": b.personne.email
                            if b.personne
                            else b.societe.email,
                        }
                        for b in autres_bailleurs
                    ]

        # Locataires
        if location.locataires.exists():
            data["locataires"] = []
            locataires: list[Locataire] = location.locataires.all()
            for loc in locataires:
                data["locataires"].append(
                    {
                        "firstName": loc.firstName,
                        "lastName": loc.lastName,
                        "email": loc.email,
                        "adresse": loc.adresse if hasattr(loc, "adresse") else None,
                    }
                )
            data["solidaires"] = location.solidaires

        # Modalités financières

        if rent_terms:
            data["modalites_financieres"] = {
                "loyer_mensuel": rent_terms.montant_loyer,
                "charges_mensuelles": rent_terms.montant_charges,
            }

        # Dates
        data["dates"] = {
            "date_debut": location.date_debut.isoformat()
            if location.date_debut
            else None,
            "date_fin": location.date_fin.isoformat() if location.date_fin else None,
        }

        # Zone tendue (si applicable) - zone_tendue est dans RentTerms (OneToOne)
        zone_tendue = False
        if rent_terms:
            zone_tendue = rent_terms.zone_tendue

        if zone_tendue:
            data["modalites_zone_tendue"] = {}
            if hasattr(rent_terms, "premiere_mise_location"):
                data["modalites_zone_tendue"]["premiere_mise_en_location"] = (
                    rent_terms.premiere_mise_en_location
                )
            if hasattr(rent_terms, "locataire_18_derniers_mois"):
                data["modalites_zone_tendue"]["locataire_derniers_18_mois"] = (
                    rent_terms.locataire_derniers_18_mois
                )
            if hasattr(rent_terms, "dernier_loyer"):
                data["modalites_zone_tendue"]["dernier_montant_loyer"] = (
                    rent_terms.dernier_montant_loyer
                )

        return data

    def _serializer_field_to_frontend_path(self, field_name: str) -> List[str]:
        """
        Convertit un chemin de champ serializer vers les chemins frontend.

        Avec la nouvelle architecture alignée, les chemins sont identiques entre
        le backend (serializers) et le frontend (schémas Zod).

        Pour les champs composés, retourne tous les sous-champs requis.
        Ex: "bien" -> tous les champs obligatoires du bien
        """
        # Pour les champs de haut niveau, retourner les champs obligatoires
        if field_name == "bien":
            return [
                "bien.localisation.adresse",
                "bien.caracteristiques.superficie",
                "bien.caracteristiques.type_bien",
                "bien.caracteristiques.pieces_info",
                "bien.caracteristiques.meuble",
                "bien.regime.regime_juridique",
                "bien.regime.periode_construction",
                "bien.energie.chauffage",
                "bien.energie.eau_chaude",
            ]
        elif field_name == "bailleur":
            # Le bailleur est un composant unique qui gère type + infos
            return ["bailleur.bailleur_type", "bailleur.personne"]
        elif field_name == "locataires":
            # Les locataires sont gérés par un seul composant
            return ["locataires"]
        elif field_name == "modalites_financieres":
            return [
                "modalites_financieres.loyer_mensuel",
                "modalites_financieres.charges_mensuelles",
            ]
        elif field_name == "modalites_zone_tendue":
            return [
                "modalites_zone_tendue.premiere_mise_en_location",
                "modalites_zone_tendue.locataire_derniers_18_mois",
                "modalites_zone_tendue.dernier_montant_loyer",
            ]
        elif field_name == "dates":
            return ["dates.date_debut"]  # date_fin est optionnelle
        elif field_name == "type_etat_lieux":
            return ["type_etat_lieux"]
        elif field_name == "date_etat_lieux":
            return ["date_etat_lieux"]
        elif field_name == "description_pieces":
            return ["description_pieces"]
        elif field_name == "nombre_cles":
            return ["nombre_cles"]
        elif field_name == "equipements_chauffage":
            return ["equipements_chauffage"]
        elif field_name == "releve_compteurs":
            return ["releve_compteurs"]

        # Pour les autres champs, retourner tel quel
        return [field_name]

    def _is_field_missing(self, field_path: str, errors: Dict) -> bool:
        """Vérifie si un champ est dans les erreurs."""
        return field_path in errors

    def _is_field_present(self, field_path: str, data: Dict) -> bool:
        """Vérifie si un champ est présent et non vide dans les données."""
        parts = field_path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
                if current is None:
                    return False
            else:
                return False

        return True

    def _get_readonly_fields(self, location: Location, data: Dict) -> List[str]:
        """
        Détermine les champs en lecture seule.
        Tous les champs existants (avec des données) sont en lecture seule.
        """
        readonly = []

        # Parcourir récursivement le dictionnaire de données pour trouver tous les champs non-vides
        def find_non_empty_fields(obj, prefix=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    field_path = f"{prefix}.{key}" if prefix else key
                    if isinstance(value, dict):
                        find_non_empty_fields(value, field_path)
                    elif isinstance(value, list):
                        if value:  # Liste non vide
                            readonly.append(field_path)
                    elif value is not None and value != "" and value != False:
                        readonly.append(field_path)

        find_non_empty_fields(data)
        return readonly
