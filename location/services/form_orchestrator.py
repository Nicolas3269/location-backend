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
        self,
        form_type: str,
        location_id: Optional[str] = None,
        country: str = "FR",
        type_etat_lieux: Optional[str] = None,
        context_mode: str = "new",
        context_source_id: Optional[str] = None,
        user: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Point d'entrée pour obtenir les requirements d'un formulaire.

        Args:
            form_type: Type de formulaire ('bail', 'etat_lieux', 'quittance')
            location_id: ID de la location (optionnel)
            country: Pays ('FR', 'BE')
            type_etat_lieux: Type d'état des lieux si applicable
            context_mode: Mode de contexte ('new', 'from_bailleur', 'from_bien', 'from_location')
            context_source_id: ID de la source contextuelle (bailleur_id, bien_id, location_id)
            user: Utilisateur authentifié (pour modes contextuels)

        Returns:
            - steps: Liste des steps avec données manquantes (ordonnées)
            - prefill_data: Données existantes pour pré-remplissage
        """
        # Validation du type de formulaire
        valid_types = ["bail", "quittance", "etat_lieux", "tenant_documents"]
        if form_type not in valid_types:
            return {
                "error": f"Invalid form type. Must be one of: {', '.join(valid_types)}"
            }

        # Cas spécial pour tenant_documents (pas de serializer classique)
        if form_type == "tenant_documents":
            return self._get_tenant_documents_requirements(
                location_id, context_source_id
            )

        # Obtenir le serializer approprié
        serializer_class = self._get_serializer_class(form_type, country)
        if not serializer_class:
            return {"error": f"No serializer found for {form_type} in {country}"}

        import uuid

        # Extraire les données contextuelles selon le mode
        contextual_prefill = self._get_contextual_prefill(
            context_mode, context_source_id, user, country
        )

        # Vérifier les conflits de documents et déterminer le location_id à utiliser
        has_conflict = False
        is_new = False
        has_been_renewed = False  # Nouveau flag pour indiquer un renouvellement suite à conflit
        existing_data = contextual_prefill  # Initialiser avec les données contextuelles

        if location_id:
            try:
                location = Location.objects.get(id=location_id)
                has_conflict = self._check_document_conflict(
                    location, form_type, type_etat_lieux
                )
            except Location.DoesNotExist:
                # Si la location n'existe pas, pas de conflit possible
                print(f"Location not found: {location_id}")

        # Déterminer le location_id final
        if has_conflict:
            # Document verrouillé - créer un nouveau
            final_location_id = str(uuid.uuid4())
            is_new = True
            has_been_renewed = True  # Indique qu'on a créé un nouveau à cause d'un conflit
        elif not location_id:
            # Première création
            final_location_id = str(uuid.uuid4())
            is_new = True
            has_been_renewed = False
        else:
            # Obtenir les données existantes
            try:
                location = Location.objects.get(id=location_id)
                location_data = self._extract_location_data(location)
                # Merger les données de location avec les données contextuelles
                # Les données de location ont priorité
                existing_data = {**existing_data, **location_data}
                final_location_id = location_id
                is_new = False
                has_been_renewed = False

            except Location.DoesNotExist:
                print(f"Location not found: {location_id}")
                # Réutiliser l'existant (données contextuelles seulement)
                final_location_id = location_id
                is_new = True
                has_been_renewed = False

        # Obtenir la configuration des steps depuis le serializer
        step_config = self._get_step_config(serializer_class, form_type)

        # Obtenir d'abord les steps verrouillées si c'est une mise à jour
        # Mais seulement si on réutilise la location existante (pas si is_new)
        locked_steps = set()
        if not is_new and location_id:
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

        # Construire le formData avec le location_id approprié
        form_data = {
            "location_id": final_location_id,
            "source": form_type,
            "country": country,
        }

        # Ajouter type_etat_lieux si c'est un état des lieux
        if form_type == "etat_lieux" and type_etat_lieux:
            form_data["type_etat_lieux"] = type_etat_lieux

        # Merger avec les données existantes si disponibles
        if existing_data:
            form_data.update(existing_data)

        result = {
            "formData": form_data,
            "is_new": is_new,
            "has_been_renewed": has_been_renewed,  # Nouveau flag
            "country": country,
            "form_type": form_type,
            "context_mode": context_mode,
            "steps": steps,
            "prefill_data": existing_data,
            "locked_steps_count": len(locked_steps) if location_id else 0,
        }

        # Ajouter la configuration des équipements depuis le serializer si disponible
        if hasattr(serializer_class, "get_equipment_config"):
            result["equipment_config"] = serializer_class.get_equipment_config()

        return result

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

    def _get_contextual_prefill(
        self,
        context_mode: str,
        context_source_id: Optional[str],
        user: Optional[Any],
        country: str,
    ) -> Dict[str, Any]:
        """
        Extrait les données de pré-remplissage selon le mode contextuel.

        Modes:
        - 'new': Aucun pré-remplissage (mode standalone)
        - 'from_bailleur': Pré-remplit le bailleur depuis bailleur_id
        - 'from_bien': Pré-remplit bien + bailleur depuis bien_id
        - 'from_location': Pré-remplit tout depuis location_id (cas édition)

        Returns:
            Dictionnaire de données pré-remplies selon le contexte
        """
        from location.models import Bailleur

        if context_mode == "new":
            return {}

        if not context_source_id:
            return {}

        try:
            if context_mode == "from_bailleur":
                # Pré-remplir uniquement les données du bailleur
                bailleur = Bailleur.objects.get(id=context_source_id)
                return self._extract_bailleur_data(bailleur)

            elif context_mode == "from_bien":
                # Pré-remplir bien + bailleur
                bien = Bien.objects.get(id=context_source_id)
                return self._extract_bien_and_bailleur_data(bien, country)

            elif context_mode == "from_location":
                # Pré-remplir tout - utilisé pour édition
                location = Location.objects.get(id=context_source_id)
                data = self._extract_location_data(location)

                # Pour les quittances, ajouter locataire_ids (UUIDs des locataires existants)
                # Cela permet à get_or_create_quittance de récupérer directement les locataires
                if location.locataires.exists():
                    data["locataire_ids"] = [str(loc.id) for loc in location.locataires.all()]

                return data

        except Exception as e:
            import traceback
            print(f"Error extracting contextual prefill: {e}")
            traceback.print_exc()
            return {}

        return {}

    def _extract_bailleur_data(self, bailleur) -> Dict[str, Any]:
        """Extrait uniquement les données du bailleur."""
        data = {"bailleur": {}}

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

        return data

    def _extract_bien_and_bailleur_data(self, bien: Bien, country: str) -> Dict[str, Any]:
        """Extrait les données du bien ET du bailleur principal."""
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
        }

        # Données du bien (même logique que _extract_location_data)
        if bien.adresse:
            data["bien"]["localisation"]["adresse"] = bien.adresse
            if bien.latitude:
                data["bien"]["localisation"]["latitude"] = bien.latitude
            if bien.longitude:
                data["bien"]["localisation"]["longitude"] = bien.longitude
                # Ajouter area_id
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

        # Équipements
        if hasattr(bien, "annexes_privatives") and bien.annexes_privatives is not None:
            data["bien"]["equipements"]["annexes_privatives"] = bien.annexes_privatives

        if hasattr(bien, "annexes_collectives") and bien.annexes_collectives is not None:
            data["bien"]["equipements"]["annexes_collectives"] = bien.annexes_collectives

        if hasattr(bien, "information") and bien.information is not None:
            data["bien"]["equipements"]["information"] = bien.information

        # Énergie
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

        # Bailleur principal
        if bien.bailleurs.exists():
            bailleur = bien.bailleurs.first()
            bailleur_data = self._extract_bailleur_data(bailleur)
            data["bailleur"] = bailleur_data.get("bailleur", {})

        return data

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
                    "id": str(loc.id),  # IMPORTANT: UUID pour éviter les duplications
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

    def _check_document_conflict(
        self, location: Location, source: str, type_etat_lieux: Optional[str] = None
    ) -> bool:
        """
        Vérifie s'il y a un conflit pour le type de document demandé.
        Un conflit existe si le document est signé ou en cours de signature.

        Args:
            location_id: ID de la location
            source: Type de document ('bail', 'etat_lieux', 'quittance')
            type_etat_lieux: Type d'état des lieux si source == 'etat_lieux'

        Returns:
            True si conflit (document verrouillé), False sinon

        """

        if source == "bail":
            # Un bail existe et est signé ou en cours de signature ?
            from bail.models import Bail
            from signature.document_status import DocumentStatus

            # Chercher un bail SIGNING ou SIGNED pour cette location
            signing_or_signed_bail = Bail.objects.filter(
                location=location,
                status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED]
            ).first()

            return signing_or_signed_bail is not None

        elif source == "etat_lieux":
            if not type_etat_lieux:
                return False  # Pas de type spécifié, pas de conflit

            # Un état des lieux de ce type existe et est signé ou en cours ?
            from etat_lieux.models import EtatLieux

            etat_lieux = EtatLieux.objects.filter(
                location=location, type_etat_lieux=type_etat_lieux
            ).first()

            if etat_lieux:
                from signature.document_status import DocumentStatus

                # Status SIGNING ou SIGNED = document verrouillé
                return etat_lieux.status in [
                    DocumentStatus.SIGNING,
                    DocumentStatus.SIGNED,
                ]
            return False

        elif source == "quittance":
            # Les quittances n'ont pas de processus de signature
            # Elles sont toujours éditables et écrasées si elles existent
            return False  # Jamais verrouillé pour les quittances

        return False

    def _get_tenant_documents_requirements(
        self, location_id: Optional[str], token: Optional[str]
    ) -> Dict[str, Any]:
        """
        Retourne les requirements pour les documents tenant (MRH, Caution).
        Utilise le token de signature pour récupérer le locataire.

        Args:
            location_id: ID de la location (non utilisé pour tenant_documents)
            token: Token de signature (utilisé comme context_source_id)

        Returns:
            Dict avec steps, formData, etc.
        """
        from bail.models import BailSignatureRequest, Document, DocumentType
        from django.shortcuts import get_object_or_404

        if not token:
            return {"error": "Token is required for tenant_documents"}

        try:
            # Récupérer la signature request via le token
            sig_req = get_object_or_404(BailSignatureRequest, link_token=token)

            # Vérifier que c'est bien un locataire (pas un bailleur)
            locataire = sig_req.locataire
            if not locataire:
                return {"error": "This page is reserved for tenants"}

            # Importer les steps
            from location.serializers.france import (
                TENANT_DOCUMENT_CAUTION_STEPS,
                TENANT_DOCUMENT_MRH_STEPS,
                TENANT_DOCUMENT_SIGNATURE_STEPS,
            )

            # Construire les steps
            steps = []
            steps.extend(TENANT_DOCUMENT_MRH_STEPS)

            # Ajouter caution si requise
            if locataire.caution_requise:
                steps.extend(TENANT_DOCUMENT_CAUTION_STEPS)

            # Ajouter signature comme dernière étape
            steps.extend(TENANT_DOCUMENT_SIGNATURE_STEPS)

            # Récupérer les documents existants
            mrh_docs = Document.objects.filter(
                locataire=locataire, type_document=DocumentType.ATTESTATION_MRH
            )
            caution_docs = Document.objects.filter(
                locataire=locataire, type_document=DocumentType.CAUTION_SOLIDAIRE
            )

            # Formatter les fichiers
            mrh_files = [
                {
                    "id": str(doc.id),
                    "name": doc.nom_original,
                    "url": doc.file.url,
                    "type": "attestation_mrh",
                }
                for doc in mrh_docs
            ]

            caution_files = [
                {
                    "id": str(doc.id),
                    "name": doc.nom_original,
                    "url": doc.file.url,
                    "type": "caution_solidaire",
                }
                for doc in caution_docs
            ]

            # Préparer formData
            form_data = {
                "locataire_id": str(locataire.id),
                "tenant_documents": {
                    "attestation_mrh": mrh_files,
                    "caution_solidaire": caution_files if locataire.caution_requise else [],
                },
            }

            return {
                "steps": steps,
                "formData": form_data,
                "is_new": len(mrh_files) == 0,
                "signataire": f"{locataire.firstName} {locataire.lastName}",
                "location_id": token,  # On utilise le token comme ID
            }

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Error in _get_tenant_documents_requirements")
            return {"error": str(e)}
