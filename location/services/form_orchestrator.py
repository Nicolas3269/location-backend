"""
Service orchestrateur pour les formulaires adaptatifs.
Architecture refactorisée - Coordonne les services spécialisés.
"""

import uuid
from typing import Any, Dict, List, Optional

from location.models import Bien, Location, RentTerms
from location.types.form_state import (
    CreateFormState,
    EditFormState,
    ExtendFormState,
    FormState,
    PrefillFormState,
    RenewFormState,
)
from rent_control.views import get_rent_control_info

from .form_conflict_resolver import FormConflictResolver
from .form_data_fetcher import FormDataFetcher
from .form_metadata_calculator import FormMetadataCalculator
from .form_step_filter import FormStepFilter


class FormOrchestrator:
    """
    Orchestrateur léger qui coordonne les services spécialisés.

    Responsabilités:
    1. Valider les paramètres d'entrée
    2. Coordonner les appels aux services
    3. Retourner la réponse structurée au frontend
    """

    def __init__(self):
        """Initialise les services."""
        self.data_fetcher = FormDataFetcher()
        self.step_filter = FormStepFilter()
        self.conflict_resolver = FormConflictResolver()
        self.metadata_calculator = FormMetadataCalculator()

    def get_form_requirements(
        self,
        form_type: str,
        form_state: FormState,
        country: str = "FR",
        type_etat_lieux: Optional[str] = None,
        user: Optional[Any] = None,
        request: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Point d'entrée pour obtenir les requirements d'un formulaire.

        Args:
            form_type: Type de formulaire ('bail', 'etat_lieux', 'quittance')
            form_state: État du formulaire (CreateFormState | EditFormState | ExtendFormState | RenewFormState)
            country: Pays ('FR', 'BE')
            type_etat_lieux: Type d'état des lieux si applicable
            user: Utilisateur authentifié (pour modes extend)
            request: Request Django (pour tenant_documents)

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
            # Pour tenant_documents, on utilise toujours EditFormState
            # avec location_id = signature_request.id
            if isinstance(form_state, EditFormState):
                return self._get_tenant_documents_requirements(
                    str(form_state.location_id), request
                )
            return {"error": "tenant_documents requires EditFormState"}

        # 1. Obtenir le serializer approprié
        serializer_class = self._get_serializer_class(form_type, country)
        if not serializer_class:
            return {"error": f"No serializer found for {form_type} in {country}"}

        # 2. Pattern matching exhaustif sur form_state
        # Détermine : existing_data, final_location_id, is_new, has_been_renewed
        if isinstance(form_state, CreateFormState) and form_state.kind == 'create':
            # Nouveau formulaire vide
            existing_data = {}
            final_location_id = str(uuid.uuid4())
            is_new = True
            has_been_renewed = False
            source_location_id = None  # Pas de source

        elif isinstance(form_state, EditFormState) and form_state.kind == 'edit':
            # Éditer location en DRAFT
            location_id = str(form_state.location_id)

            # Vérifier conflit (si document déjà signé, on refuse l'édition)
            conflict_result = self.conflict_resolver.resolve_location_id(
                form_type, location_id, type_etat_lieux
            )

            if conflict_result["has_been_renewed"]:
                # Document signé détecté → impossible d'éditer, utiliser RenewFormState
                return {
                    "error": "Cannot edit signed document. Use RenewFormState to create a new version."
                }

            existing_data = self.data_fetcher.fetch_location_data(location_id) or {}
            final_location_id = location_id
            is_new = False
            has_been_renewed = False
            source_location_id = None  # Pas de source

        elif isinstance(form_state, ExtendFormState) and form_state.kind == 'extend':
            # Mode Extend: Location Actuelle/Ancienne - RÉUTILISER la location existante
            source_id = str(form_state.source_id)
            source_data = self.data_fetcher.fetch_location_data(source_id) or {}
            source_location_id = source_id  # Pour check lock

            # Copier TOUTES les données
            existing_data = source_data
            final_location_id = source_id  # ✅ RÉUTILISER le même location_id
            is_new = False  # ✅ Pas une nouvelle location, c'est une location existante
            has_been_renewed = False

        elif isinstance(form_state, PrefillFormState) and form_state.kind == 'prefill':
            # Mode Prefill: Nouvelle Location avec suggestions (JAMAIS de lock)
            source_id = str(form_state.source_id)

            if form_state.source_type == 'location':
                source_data = self.data_fetcher.fetch_location_data(source_id) or {}
            elif form_state.source_type == 'bien':
                source_data = self.data_fetcher.fetch_bien_data(source_id) or {}
            elif form_state.source_type == 'bailleur':
                source_data = self.data_fetcher.fetch_bailleur_data(source_id) or {}
            else:
                source_data = {}

            # Copier TOUTES les données (suggestions)
            existing_data = source_data
            final_location_id = str(uuid.uuid4())
            is_new = True
            has_been_renewed = False
            source_location_id = None  # Pas de lock check en mode prefill

        elif isinstance(form_state, RenewFormState) and form_state.kind == 'renew':
            # Renouvellement (document signé → nouveau location_id)
            previous_location_id = str(form_state.previous_location_id)
            existing_data = self.data_fetcher.fetch_location_data(previous_location_id) or {}
            final_location_id = str(uuid.uuid4())
            is_new = True
            has_been_renewed = True
            source_location_id = None  # Pas de source

        else:
            return {"error": f"Invalid FormState type: {type(form_state)}"}

        # 3. Obtenir la configuration des steps depuis le serializer
        step_config = self._get_step_config(serializer_class, form_type)

        # 4. Obtenir les steps verrouillées (SERVICE)
        # En mode extend depuis location, on vérifie le verrouillage de la source
        lock_check_location_id = source_location_id if source_location_id else final_location_id
        locked_steps = self.step_filter.get_locked_steps(
            lock_check_location_id, country, is_new
        )

        # Pour PrefillFormState depuis bien, locker tous les steps
        # SAUF ceux marqués unlocked_from_bien
        if (isinstance(form_state, PrefillFormState) and
            form_state.source_type == 'bien'):
            for step in step_config:
                step_id = step.get("id")
                # Si le step n'est pas unlocked, le locker (s'il a une valeur)
                if not step.get("unlocked_from_bien", False):
                    if self._step_has_value(step_id, existing_data):
                        locked_steps.add(step_id)

        # 5. Filtrer et enrichir les steps (SERVICE)
        steps = self.step_filter.filter_steps(
            step_config, existing_data, locked_steps, serializer_class
        )

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

        # Pour les états des lieux en mode ExtendFormState, filtrer les types disponibles
        if form_type == "etat_lieux" and isinstance(form_state, ExtendFormState):
            try:
                location = Location.objects.get(id=form_state.source_id)
                available_types = self._get_available_etat_lieux_types(location)

                # Modifier le step type_etat_lieux pour n'afficher que les types disponibles
                for step in steps:
                    if step.get("id") == "type_etat_lieux" and available_types:
                        step["available_choices"] = available_types
                        # Si un seul choix, le pré-sélectionner
                        if len(available_types) == 1 and not form_data.get("type_etat_lieux"):
                            form_data["type_etat_lieux"] = available_types[0]
            except Location.DoesNotExist:
                pass


        result = {
            "formData": form_data,
            "is_new": is_new,
            "has_been_renewed": has_been_renewed,
            "country": country,
            "form_type": form_type,
            "steps": steps,
            "prefill_data": existing_data,
            "locked_steps": list(locked_steps),  # Liste des step_ids lockés
            "locked_steps_count": len(locked_steps),
        }

        # Pour PrefillFormState, ajouter bien_id/bailleur_id au niveau racine
        if isinstance(form_state, PrefillFormState):
            if form_state.source_type == 'bien':
                result["bien_id"] = str(form_state.source_id)
                # Récupérer bailleur_id depuis le bien
                try:
                    bien = Bien.objects.prefetch_related("bailleurs").get(id=form_state.source_id)
                    if bien.bailleurs.exists():
                        result["bailleur_id"] = str(bien.bailleurs.first().id)
                except Bien.DoesNotExist:
                    pass
            elif form_state.source_type == 'bailleur':
                result["bailleur_id"] = str(form_state.source_id)
            elif form_state.source_type == 'location':
                # Pour prefill depuis location, récupérer bien_id et bailleur_id
                try:
                    location = Location.objects.select_related('bien').prefetch_related('bien__bailleurs').get(id=form_state.source_id)
                    if location.bien:
                        result["bien_id"] = str(location.bien.id)
                        if location.bien.bailleurs.exists():
                            result["bailleur_id"] = str(location.bien.bailleurs.first().id)
                except Location.DoesNotExist:
                    pass

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
                    data["locataire_ids"] = [
                        str(loc.id) for loc in location.locataires.all()
                    ]

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
            "physique" if bailleur.personne else "morale" if bailleur.societe else None
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

    def _extract_bien_and_bailleur_data(
        self, bien: Bien, country: str
    ) -> Dict[str, Any]:
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

        if (
            hasattr(bien, "annexes_collectives")
            and bien.annexes_collectives is not None
        ):
            data["bien"]["equipements"]["annexes_collectives"] = (
                bien.annexes_collectives
            )

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
                status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED],
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

    def _get_available_etat_lieux_types(self, location: Location) -> list[str]:
        """
        Retourne les types d'état des lieux disponibles pour une location.
        Un type est disponible si aucun EDL de ce type n'est SIGNED ou SIGNING.

        Args:
            location: Instance de Location

        Returns:
            Liste des types disponibles: ['entree', 'sortie'] ou ['entree'] ou ['sortie']
        """
        from etat_lieux.models import EtatLieux
        from signature.document_status import DocumentStatus

        available_types = []

        # Vérifier l'entrée
        edl_entree = EtatLieux.objects.filter(
            location=location, type_etat_lieux="entree"
        ).first()
        if not edl_entree or edl_entree.status not in [
            DocumentStatus.SIGNING,
            DocumentStatus.SIGNED,
        ]:
            available_types.append("entree")

        # Vérifier la sortie
        edl_sortie = EtatLieux.objects.filter(
            location=location, type_etat_lieux="sortie"
        ).first()
        if not edl_sortie or edl_sortie.status not in [
            DocumentStatus.SIGNING,
            DocumentStatus.SIGNED,
        ]:
            available_types.append("sortie")

        return available_types

    def _get_tenant_documents_requirements(
        self,
        location_id: str,
        request: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Retourne les requirements pour les documents tenant (MRH, Caution).
        Utilise le link_token (passé comme location_id)
        pour récupérer la signature request.

        Args:
            location_id: Link token du magic link
            request: Request Django (pour build_absolute_uri)

        Returns:
            Dict avec steps, formData, etc.
        """
        from django.shortcuts import get_object_or_404

        from bail.models import BailSignatureRequest, Document, DocumentType

        if not location_id:
            return {"error": "location_id is required for tenant_documents"}

        try:
            # Récupérer la signature request via link_token
            # Note: location_id contient en fait le link_token (magic link)
            sig_req = get_object_or_404(BailSignatureRequest, link_token=location_id)

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

            # Formatter les fichiers avec URLs absolues
            mrh_files = [
                {
                    "id": str(doc.id),
                    "name": doc.nom_original,
                    "url": request.build_absolute_uri(doc.file.url),
                    "type": "attestation_mrh",
                }
                for doc in mrh_docs
            ]

            caution_files = [
                {
                    "id": str(doc.id),
                    "name": doc.nom_original,
                    "url": request.build_absolute_uri(doc.file.url),
                    "type": "caution_solidaire",
                }
                for doc in caution_docs
            ]

            # Préparer formData
            form_data = {
                "locataire_id": str(locataire.id),
                "caution_requise": locataire.caution_requise,
                "tenant_documents": {
                    "attestation_mrh": mrh_files,
                    "caution_solidaire": caution_files
                    if locataire.caution_requise
                    else [],
                },
            }

            return {
                "steps": steps,
                "formData": form_data,
                "is_new": len(mrh_files) == 0,
                "signataire": f"{locataire.firstName} {locataire.lastName}",
                "location_id": location_id,  # UUID de la signature request
            }

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception("Error in _get_tenant_documents_requirements")
            return {"error": str(e)}

    def _step_has_value(self, step_id: str, data: Dict[str, Any]) -> bool:
        """
        Vérifie si un step a une valeur dans les données.
        Supporte les paths imbriqués (ex: "bien.localisation.adresse")
        """
        if not step_id or not data:
            return False

        parts = step_id.split(".")
        current = data

        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]

        # Vérifier si la valeur n'est pas None/vide
        if current is None:
            return False
        if isinstance(current, str) and not current:
            return False
        if isinstance(current, (list, dict)) and len(current) == 0:
            return False

        return True
