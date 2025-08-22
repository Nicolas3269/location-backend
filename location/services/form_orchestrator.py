"""
Orchestrateur de formulaires adaptatifs.
Détermine les étapes nécessaires selon le contexte et l'état de la Location.
"""

from typing import Any, Dict, List, Optional

from ..models import Location


class FormOrchestrator:
    """Orchestre la construction des formulaires adaptatifs."""

    # Définition des étapes par type de formulaire
    FORM_STEPS = {
        "bail": {
            "bien": [
                "bien.adresse",
                "bien.typeLogement",
                "bien.regimeJuridique",
                "bien.periodeConstruction",
                "bien.surface",
                "bien.pieces",
                "bien.annexesPrivatives",
                "bien.annexesCollectives",
                "bien.meuble",
                "bien.information",
                "bien.chauffage",
                "bien.eauChaude",
                "bien.dpe",
                "bien.depensesEnergie",
                "bien.identificationFiscale",
            ],
            "personnes": [
                "personnes.bailleurType",
                "personnes.landlord",
                "personnes.siretSociete",
                "personnes.otherLandlords",
                "personnes.locataires",
                "personnes.solidaires",
            ],
            "modalites": [
                "modalites.startDate",
                "modalites.premiereMiseEnLocation",
                "modalites.locataireDerniers18Mois",
                "modalites.dernierMontantLoyer",
                "modalites.prix",
                "modalites.charges",
            ],
            "signature": [
                "signature.signatureBail",
            ],
        },
        "quittance": {
            "full": [
                "bien.adresse",
                "personnes.bailleurType",
                "personnes.landlord",
                "personnes.siretSociete",
                "personnes.otherLandlords",
                "personnes.locataires",
                "quittance.prix",
                "quittance.charges",
                "quittance.moisAnnee",
                "quittance.result",
            ],
            "simplified": [
                "quittance.moisAnnee",
                "quittance.result",
            ],
        },
        "etat_lieux": {
            "full": [
                "bien.adresse",
                "bien.typeLogement",
                "bien.surface",
                "bien.pieces",
                "bien.meuble",
                "bien.chauffage",
                "bien.eauChaude",
                "personnes.bailleurType",
                "personnes.landlord",
                "personnes.siretSociete",
                "personnes.otherLandlords",
                "personnes.locataires",
                "modalites.typeEtatLieux",
                "modalites.dateEtatLieux",
                "etat_lieux.descriptionPieces",
                "etat_lieux.nombreCles",
                "etat_lieux.equipementsChauffage",
                "etat_lieux.releveCompteurs",
                "signature.signatureEtatDesLieux",
            ],
            "simplified": [
                "modalites.typeEtatLieux",
                "modalites.dateEtatLieux",
                "etat_lieux.descriptionPieces",
                "etat_lieux.nombreCles",
                "etat_lieux.equipementsChauffage",
                "etat_lieux.releveCompteurs",
                "signature.signatureEtatDesLieux",
            ],
        },
    }

    # Champs conditionnels et leurs dépendances
    CONDITIONAL_FIELDS = {
        "bien.depensesEnergie": {
            "condition": 'dpeGrade !== "NA"',
            "depends_on": "bien.dpe",
        },
        "personnes.siretSociete": {
            "condition": 'bailleurType === "morale"',
            "depends_on": "personnes.bailleurType",
        },
        "personnes.solidaires": {
            "condition": "locataires.length > 1",
            "depends_on": "personnes.locataires",
        },
        "modalites.premiereMiseEnLocation": {
            "condition": "zoneTendue === true",
            "depends_on": "modalites.zoneTendue",
        },
        "modalites.locataireDerniers18Mois": {
            "condition": 'zoneTendue === true && modalites.premiereMiseEnLocation === "false"',
            "depends_on": ["modalites.zoneTendue", "modalites.premiereMiseEnLocation"],
        },
        "modalites.dernierMontantLoyer": {
            "condition": 'zoneTendue === true && modalites.premiereMiseEnLocation === "false" && modalites.locataireDerniers18Mois === "true"',
            "depends_on": [
                "modalites.zoneTendue",
                "modalites.premiereMiseEnLocation",
                "modalites.locataireDerniers18Mois",
            ],
        },
    }

    # Champs en lecture seule une fois remplis
    READONLY_ONCE_SET = [
        "bien.adresse",
        "bien.identificationFiscale",
        "personnes.landlord.dateNaissance",
        "personnes.siret",
        "modalites.startDate",  # Date de début ne change pas après signature
    ]

    def get_form_requirements(
        self, form_type: str, location_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retourne les requirements pour un formulaire donné.

        Args:
            form_type: Type de formulaire ('bail', 'quittance', 'etat_lieux')
            location_id: ID de la location existante (optionnel)

        Returns:
            Dict contenant les steps, données pré-remplies, et contexte
        """
        if not location_id:
            # Nouveau formulaire - toutes les étapes
            return self._get_new_form_requirements(form_type)

        try:
            location = (
                Location.objects.select_related("bien", "rent_terms")
                .prefetch_related("bien__bailleurs", "locataires", "garants")
                .get(id=location_id)
            )

            return self._get_adaptive_form_requirements(form_type, location)

        except Location.DoesNotExist:
            return {
                "error": "Location not found",
                "steps": [],
                "prefill_data": {},
                "context": {},
            }

    def _get_new_form_requirements(self, form_type: str) -> Dict[str, Any]:
        """Retourne les requirements pour un nouveau formulaire."""

        if form_type == "bail":
            steps = (
                self.FORM_STEPS["bail"]["bien"]
                + self.FORM_STEPS["bail"]["personnes"]
                + self.FORM_STEPS["bail"]["modalites"]
                + self.FORM_STEPS["bail"]["signature"]
            )
        elif form_type == "quittance":
            steps = self.FORM_STEPS["quittance"]["full"]
        elif form_type == "etat_lieux":
            steps = self.FORM_STEPS["etat_lieux"]["full"]
        else:
            return {"error": f"Unknown form type: {form_type}"}

        return {
            "steps": self._build_steps_config(steps, {}),
            "prefill_data": {},
            "readonly_fields": [],
            "context": {
                "location_exists": False,
                "is_new": True,
                "form_type": form_type,
            },
        }

    def _get_adaptive_form_requirements(
        self, form_type: str, location: Location
    ) -> Dict[str, Any]:
        """Retourne les requirements adaptés selon la Location existante."""

        from .location_analyzer import LocationAnalyzer

        analyzer = LocationAnalyzer()
        completeness = analyzer.analyze_completeness(location)
        existing_data = self._extract_location_data(location)

        # Déterminer les steps nécessaires
        required_steps = self._determine_required_steps(
            form_type, completeness, existing_data
        )

        # Identifier les champs readonly
        readonly_fields = self._get_readonly_fields(location, existing_data)

        return {
            "steps": self._build_steps_config(required_steps, existing_data),
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

    def _determine_required_steps(
        self, form_type: str, completeness: Dict, existing_data: Dict
    ) -> List[str]:
        """Détermine les étapes requises selon le contexte."""

        required_steps = []

        if form_type == "bail":
            # Pour un bail, on vérifie section par section
            if not completeness["bien"]["is_complete"]:
                required_steps.extend(
                    [
                        step
                        for step in self.FORM_STEPS["bail"]["bien"]
                        if not self._is_field_complete(step, existing_data)
                    ]
                )

            if not completeness["personnes"]["has_all_required"]:
                required_steps.extend(
                    [
                        step
                        for step in self.FORM_STEPS["bail"]["personnes"]
                        if not self._is_field_complete(step, existing_data)
                    ]
                )

            if not completeness["rent_terms"]["is_complete"]:
                required_steps.extend(self.FORM_STEPS["bail"]["modalites"])

            # Toujours ajouter la signature pour un bail
            required_steps.extend(self.FORM_STEPS["bail"]["signature"])

        elif form_type == "quittance":
            # Quittance simplifiée si on a déjà les infos de base
            if (
                completeness["rent_terms"]["is_complete"]
                and completeness["personnes"]["has_all_required"]
            ):
                required_steps = self.FORM_STEPS["quittance"]["simplified"]
            else:
                required_steps = self.FORM_STEPS["quittance"]["full"]

        elif form_type == "etat_lieux":
            # État des lieux simplifié si on a déjà le bien et les personnes
            if (
                completeness["bien"]["is_complete"]
                and completeness["personnes"]["has_all_required"]
            ):
                required_steps = self.FORM_STEPS["etat_lieux"]["simplified"]
            else:
                required_steps = self.FORM_STEPS["etat_lieux"]["full"]

        return required_steps

    def _is_field_complete(self, field_path: str, data: Dict) -> bool:
        """Vérifie si un champ est complet dans les données."""

        parts = field_path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict):
                if part not in current or current[part] is None:
                    return False
                current = current[part]
            else:
                return False

        # Vérifier que la valeur n'est pas vide
        if isinstance(current, str):
            return bool(current.strip())
        elif isinstance(current, (list, dict)):
            return bool(current)
        else:
            return current is not None

    def _extract_location_data(self, location: Location) -> Dict[str, Any]:
        """Extrait toutes les données de la Location pour pré-remplissage."""

        data = {}

        # Données du bien
        if location.bien:
            bien = location.bien
            data.update(
                {
                    "adresse": bien.adresse,
                    "typeLogement": bien.type_bien,
                    "regimeJuridique": bien.regime_juridique,
                    "periodeConstruction": bien.periode_construction,
                    "surface": float(bien.superficie) if bien.superficie else None,
                    "pieces": bien.pieces_info or {},
                    "annexesPrivatives": bien.annexes_privatives or [],
                    "annexesCollectives": bien.annexes_collectives or [],
                    "meuble": bien.meuble,
                    "information": bien.information or [],
                    "chauffage": {
                        "type": bien.chauffage_type,
                        "energie": bien.chauffage_energie,
                    },
                    "eauChaude": {
                        "type": bien.eau_chaude_type,
                        "energie": bien.eau_chaude_energie,
                    },
                    "dpeGrade": bien.classe_dpe,
                    "depensesDPE": bien.depenses_energetiques,
                    "identificationFiscale": bien.identifiant_fiscal,
                }
            )

            # Données des bailleurs
            bailleurs = bien.bailleurs.all()
            if bailleurs:
                bailleur_principal = bailleurs.first()

                # Type de bailleur
                data["bailleurType"] = (
                    "morale" if bailleur_principal.societe else "physique"
                )

                # Infos du bailleur
                if bailleur_principal.personne:
                    data["landlord"] = {
                        "firstName": bailleur_principal.personne.prenom,
                        "lastName": bailleur_principal.personne.nom,
                        "email": bailleur_principal.personne.email,
                        "address": bailleur_principal.personne.adresse,
                        "dateNaissance": str(bailleur_principal.personne.date_naissance)
                        if bailleur_principal.personne.date_naissance
                        else None,
                    }
                elif bailleur_principal.societe:
                    data["siret"] = bailleur_principal.societe.siret
                    data["societe"] = {
                        "raisonSociale": bailleur_principal.societe.raison_sociale,
                        "formeJuridique": bailleur_principal.societe.forme_juridique,
                        "adresse": bailleur_principal.societe.adresse,
                    }
                    if bailleur_principal.signataire:
                        data["landlord"] = {
                            "firstName": bailleur_principal.signataire.prenom,
                            "lastName": bailleur_principal.signataire.nom,
                            "email": bailleur_principal.signataire.email,
                        }

                # Autres bailleurs
                if bailleurs.count() > 1:
                    data["otherLandlords"] = [
                        {
                            "firstName": b.personne.prenom
                            if b.personne
                            else b.signataire.prenom,
                            "lastName": b.personne.nom
                            if b.personne
                            else b.signataire.nom,
                            "email": b.personne.email
                            if b.personne
                            else b.societe.email,
                        }
                        for b in bailleurs[1:]
                    ]

        # Données des locataires
        if location.locataires.exists():
            data["locataires"] = [
                {
                    "firstName": loc.prenom,
                    "lastName": loc.nom,
                    "email": loc.email,
                    "dateNaissance": str(loc.date_naissance)
                    if loc.date_naissance
                    else None,
                }
                for loc in location.locataires.all()
            ]
            data["solidaires"] = location.solidaires

        # Données des modalités
        if hasattr(location, "rent_terms") and location.rent_terms:
            rent = location.rent_terms
            data["modalites"] = {
                "prix": float(rent.montant_loyer) if rent.montant_loyer else None,
                "chargeType": rent.type_charges,
                "chargeAmount": float(rent.montant_charges)
                if rent.montant_charges
                else None,
                "zoneTendue": rent.zone_tendue,
            }
            data["zoneTendue"] = rent.zone_tendue  # Pour les conditions

        # Dates
        if location.date_debut:
            data["startDate"] = location.date_debut.isoformat()
        if location.date_fin:
            data["endDate"] = location.date_fin.isoformat()

        # Champs vides mais nécessaires pour le watch des conditions
        if "modalites" not in data:
            data["modalites"] = {}

        data["modalites"].update(
            {
                "premiereMiseEnLocation": None,
                "locataireDerniers18Mois": None,
                "dernierMontantLoyer": None,
            }
        )

        return data

    def _get_readonly_fields(self, location: Location, data: Dict) -> List[str]:
        """Détermine les champs en lecture seule."""

        readonly = []

        # Champs toujours readonly s'ils ont une valeur
        for field in self.READONLY_ONCE_SET:
            if self._is_field_complete(field, data):
                readonly.append(field)

        # Si un bail existe, certains champs deviennent readonly
        from bail.models import Bail

        if Bail.objects.filter(location=location, date_signature__isnull=False).exists():
            readonly.extend(
                [
                    "bien.surface",
                    "bien.pieces",
                    "personnes.locataires",
                    "modalites.startDate",
                ]
            )

        return list(set(readonly))  # Supprimer les doublons

    # Steps qui gèrent leur propre navigation (auto-next après sélection)
    NAVIGATION_PROPS_STEPS = [
        "bien.typeLogement",
        "bien.regimeJuridique", 
        "bien.periodeConstruction",
        "bien.meuble",
        "personnes.bailleurType",
        "modalites.premiereMiseEnLocation",
        "modalites.locataireDerniers18Mois",
        "modalites.typeEtatLieux",
    ]
    
    # Questions pour chaque step
    STEP_QUESTIONS = {
        # BIEN
        "bien.adresse": "Quelle est l'adresse du logement ?",
        "bien.typeLogement": "Quel est le type de logement ?",
        "bien.regimeJuridique": "Quel est le régime juridique du logement ?",
        "bien.periodeConstruction": "Quelle est l'année de construction du logement ?",
        "bien.surface": "Quelle est la surface du logement ?",
        "bien.pieces": "Quelles pièces y a-t-il dans le logement ?",
        "bien.annexesPrivatives": "Quelles sont les annexes privatives du logement ?",
        "bien.annexesCollectives": "Quelles sont les annexes partagées du logement ?",
        "bien.meuble": "Le logement est-il meublé ?",
        "bien.information": "Quels sont les équipements d'accès aux technologies de l'information ?",
        "bien.chauffage": "Quel est le type de chauffage du logement ?",
        "bien.eauChaude": "Quel est le type de production d'eau chaude ?",
        "bien.dpe": "Quelle est la classe énergétique du logement (DPE) ?",
        "bien.depensesEnergie": "Quel est le montant des dépenses énergétiques théoriques ?",
        "bien.identificationFiscale": "Quel est l'identifiant fiscal du logement ?",
        # PERSONNES
        "personnes.bailleurType": "Êtes-vous un particulier ou une société ?",
        "personnes.landlord": "Vos informations en tant que propriétaire",
        "personnes.siretSociete": "Informations de la société",
        "personnes.otherLandlords": "Voulez-vous ajouter d'autres bailleurs au bail ?",
        "personnes.locataires": "Qui sont le ou les locataires ?",
        "personnes.solidaires": "Les locataires sont-ils solidaires du bail ?",
        # MODALITÉS
        "modalites.startDate": "Quelle est la date d'entrée dans le logement ?",
        "modalites.endDate": "Quelle est la date de fin du bail ?",
        "modalites.premiereMiseEnLocation": "Est-ce la première mise en location du logement ?",
        "modalites.locataireDerniers18Mois": "Y a-t-il eu un locataire dans le logement durant les 18 derniers mois ?",
        "modalites.dernierMontantLoyer": "Quel était le montant du dernier loyer (hors charges) ?",
        "modalites.prix": "Quel est le montant du loyer du logement ?",
        "modalites.charges": "Quelles sont les charges du logement ?",
        "modalites.typeEtatLieux": "Quel type d'état des lieux souhaitez-vous effectuer ?",
        "modalites.dateEtatLieux": "Quelle est la date de l'état des lieux ?",
        # QUITTANCE
        "quittance.prix": "Quel est le montant du loyer ?",
        "quittance.charges": "Quelles sont les charges ?",
        "quittance.moisAnnee": "Pour quel mois générez-vous la quittance ?",
        "quittance.result": "Votre quittance",
        # ÉTAT DES LIEUX
        "etat_lieux.descriptionPieces": "Décrivez l'état de chaque pièce en détail",
        "etat_lieux.nombreCles": "Combien de clés sont remises au locataire ?",
        "etat_lieux.equipementsChauffage": "Quels sont les équipements de chauffage / eau chaude ?",
        "etat_lieux.releveCompteurs": "Quels sont les relevés des compteurs ?",
        # SIGNATURE
        "signature.signatureBail": "Signature du bail",
        "signature.signatureEtatDesLieux": "Signature de l'état des lieux",
    }

    def _build_steps_config(
        self, step_ids: List[str], existing_data: Dict
    ) -> List[Dict[str, Any]]:
        """Construit la configuration détaillée des steps."""

        steps = []

        for step_id in step_ids:
            step_config = {
                "id": step_id,
                "question": self.STEP_QUESTIONS.get(step_id, ""),
                "required": True,
                "prefilled": self._is_field_complete(step_id, existing_data),
                "navigationProps": step_id in self.NAVIGATION_PROPS_STEPS,
            }

            # Ajouter les conditions si elles existent
            if step_id in self.CONDITIONAL_FIELDS:
                condition_info = self.CONDITIONAL_FIELDS[step_id]
                step_config["condition"] = condition_info["condition"]
                step_config["depends_on"] = condition_info["depends_on"]

                # Pré-évaluer la visibilité initiale
                step_config["initially_visible"] = self._evaluate_condition(
                    condition_info["condition"], existing_data
                )

            steps.append(step_config)

        return steps

    def _evaluate_condition(self, condition: str, data: Dict) -> bool:
        """
        Évalue une condition simple côté backend.
        Pour des conditions complexes, le frontend prendra le relais.
        """

        # Conditions simples qu'on peut évaluer côté backend
        if condition == 'bailleurType === "morale"':
            return data.get("bailleurType") == "morale"
        elif condition == 'dpeGrade !== "NA"':
            return data.get("dpeGrade") not in [None, "NA"]
        elif condition == "zoneTendue === true":
            return data.get("zoneTendue") is True
        elif condition == "locataires.length > 1":
            locataires = data.get("locataires", [])
            return len(locataires) > 1

        # Pour les conditions complexes, on retourne True par défaut
        # Le frontend fera l'évaluation précise
        return True
