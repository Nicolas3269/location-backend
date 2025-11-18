"""
Service responsable du fetch des données depuis la BDD pour pré-remplir les formulaires.

Responsabilité unique : Récupérer les données existantes d'une Location
et les transformer en dictionnaire utilisable par le frontend.
"""

from typing import Any, Dict, Optional

from location.models import Bailleur, Bien, Location, RentTerms
from location.services.bailleur_utils import serialize_bailleur, serialize_mandataire
from rent_control.views import check_zone_status_via_ban, get_rent_control_info


class FormDataFetcher:
    """Récupère les données depuis la BDD pour pré-remplir un formulaire."""

    def fetch_location_data(
        self, location_id: str, user: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Récupère toutes les données d'une Location existante.

        Args:
            location_id: UUID de la location
            user: Utilisateur connecté (optionnel).
                  Si fourni, son bailleur sera mis en premier.

        Returns:
            Dict avec toutes les données extraites ou None si location inexistante
        """
        try:
            location = (
                Location.objects.select_related(
                    "bien",
                    "mandataire__signataire",
                    "mandataire__societe",
                    "rent_terms",
                )
                .prefetch_related(
                    "bien__bailleurs__personne",
                    "bien__bailleurs__societe",
                    "bien__bailleurs__signataire",
                    "locataires",
                )
                .get(id=location_id)
            )
            return self._extract_location_data(location, user)
        except Location.DoesNotExist:
            return None

    def fetch_bien_data(
        self, bien_id: str, user: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Récupère les données d'un Bien pour pré-remplir un formulaire.

        Args:
            bien_id: UUID du bien
            user: Utilisateur connecté (optionnel).
                  Si fourni, son bailleur sera mis en premier.

        Returns:
            Dict avec les données du bien ou None si inexistant
        """
        try:
            # Note: bailleurs est une relation ManyToMany, pas ForeignKey
            # donc on ne peut pas utiliser select_related
            bien = Bien.objects.prefetch_related(
                "bailleurs__personne",
                "bailleurs__societe",
                "bailleurs__signataire",
            ).get(id=bien_id)

            data = {}

            # Données du bien
            if bien:
                data["bien"] = self._extract_bien_data(bien)

            # Données du bailleur (+ co-bailleurs)
            data["bailleur"] = self._extract_bailleurs_data(bien.bailleurs, user)

            return data
        except Bien.DoesNotExist:
            return None

    def _extract_location_data(
        self, location: Location, user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Extrait les données d'une Location pour pré-remplissage.
        Format aligné avec les serializers.

        Args:
            location: Location à extraire
            user: Utilisateur connecté (optionnel).
                  Si fourni, son bailleur sera mis en premier.

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
                    "depenses_energetiques": (
                        bien.depenses_energetiques
                        if bien.depenses_energetiques
                        else None
                    ),
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
                data["bien"]["zone_reglementaire"]["zone_tres_tendue"] = (
                    rent_terms.zone_tres_tendue
                )
                data["bien"]["zone_reglementaire"]["zone_tendue_touristique"] = (
                    rent_terms.zone_tendue_touristique
                )

            # Équipements
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

        # Données du bailleur (+ co-bailleurs)
        if location.bien:
            data["bailleur"] = self._extract_bailleurs_data(
                location.bien.bailleurs, user
            )

        # Mandataire
        if location.mandataire:
            data["mandataire"] = serialize_mandataire(location.mandataire)

        # Locataires
        if location.locataires.exists():
            data["locataires"] = [
                {
                    "id": str(loc.id),
                    "firstName": loc.firstName,
                    "lastName": loc.lastName,
                    "email": loc.email,
                }
                for loc in location.locataires.all()
            ]
            data["solidaires"] = location.solidaires

        # Modalités financières (toujours inclure si rent_terms existe)
        if rent_terms:
            data["modalites_financieres"] = {}
            if rent_terms.montant_loyer:
                data["modalites_financieres"]["loyer_hors_charges"] = float(
                    rent_terms.montant_loyer
                )
            if rent_terms.montant_charges:
                data["modalites_financieres"]["charges"] = float(
                    rent_terms.montant_charges
                )
            if hasattr(rent_terms, "type_charges") and rent_terms.type_charges:
                data["modalites_financieres"]["type_charges"] = rent_terms.type_charges

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
                if hasattr(rent_terms, "dernier_loyer_periode"):
                    data["modalites_zone_tendue"]["dernier_loyer_periode"] = (
                        rent_terms.dernier_loyer_periode
                    )
                if hasattr(rent_terms, "justificatif_complement_loyer"):
                    data["modalites_zone_tendue"]["justificatif_complement_loyer"] = (
                        rent_terms.justificatif_complement_loyer
                    )

        # Dates
        if location.date_debut or location.date_fin:
            data["dates"] = {}
            if location.date_debut:
                data["dates"]["date_debut"] = location.date_debut.isoformat()
            if location.date_fin:
                data["dates"]["date_fin"] = location.date_fin.isoformat()

        return data

    def _extract_bien_data(self, bien: Bien) -> Dict[str, Any]:
        """Extrait les données d'un Bien pour prefill."""
        data = {
            "localisation": {},
            "caracteristiques": {},
            "performance_energetique": {},
            "equipements": {},
            "energie": {},
            "regime": {},
            "zone_reglementaire": {},
        }

        # Localisation
        if bien.adresse:
            data["localisation"]["adresse"] = bien.adresse
            if bien.latitude:
                data["localisation"]["latitude"] = bien.latitude
            if bien.longitude:
                data["localisation"]["longitude"] = bien.longitude
            # Calculer données réglementaires GPS (évoluent avec le temps)
            if bien.latitude and bien.longitude:
                # Zone tendue et permis de louer (via API BAN)
                zone_status = check_zone_status_via_ban(bien.latitude, bien.longitude)
                if zone_status:
                    data["zone_reglementaire"]["zone_tendue"] = zone_status.get(
                        "is_zone_tendue", False
                    )
                    data["zone_reglementaire"]["zone_tres_tendue"] = zone_status.get(
                        "is_zone_tres_tendue", False
                    )
                    data["zone_reglementaire"]["zone_tendue_touristique"] = (
                        zone_status.get("is_zone_tendue_touristique", False)
                    )
                    data["zone_reglementaire"]["permis_de_louer"] = zone_status.get(
                        "is_permis_de_louer", False
                    )

                # Area ID pour encadrement des loyers (calcul prix de référence)
                _, area = get_rent_control_info(bien.latitude, bien.longitude)
                if area:
                    data["localisation"]["area_id"] = area.id

        # Caractéristiques
        if bien.superficie or bien.type_bien:
            data["caracteristiques"] = {
                "superficie": bien.superficie,
                "type_bien": bien.type_bien,
                "etage": bien.etage if bien.etage else None,
                "porte": bien.porte if bien.porte else None,
                "dernier_etage": bien.dernier_etage,
                "meuble": bien.meuble,
            }
            if bien.pieces_info:
                data["caracteristiques"]["pieces_info"] = bien.pieces_info

        # Performance énergétique
        if bien.classe_dpe:
            data["performance_energetique"] = {
                "classe_dpe": bien.classe_dpe,
                "depenses_energetiques": (
                    bien.depenses_energetiques if bien.depenses_energetiques else None
                ),
            }

        # Régime juridique
        if hasattr(bien, "regime_juridique"):
            data["regime"] = {
                "regime_juridique": bien.regime_juridique or "monopropriete",
                "periode_construction": bien.periode_construction
                if hasattr(bien, "periode_construction")
                else None,
                "identifiant_fiscal": bien.identifiant_fiscal
                if hasattr(bien, "identifiant_fiscal")
                else None,
            }

        # Équipements
        if hasattr(bien, "annexes_privatives") and bien.annexes_privatives is not None:
            data["equipements"]["annexes_privatives"] = bien.annexes_privatives

        if (
            hasattr(bien, "annexes_collectives")
            and bien.annexes_collectives is not None
        ):
            data["equipements"]["annexes_collectives"] = bien.annexes_collectives

        if hasattr(bien, "information") and bien.information is not None:
            data["equipements"]["information"] = bien.information

        # Énergie
        if hasattr(bien, "chauffage_type") and bien.chauffage_type is not None:
            chauffage_data = {"type": bien.chauffage_type}
            if bien.chauffage_energie is not None:
                chauffage_data["energie"] = bien.chauffage_energie
            data["energie"]["chauffage"] = chauffage_data

        if hasattr(bien, "eau_chaude_type") and bien.eau_chaude_type is not None:
            eau_chaude_data = {"type": bien.eau_chaude_type}
            if bien.eau_chaude_energie is not None:
                eau_chaude_data["energie"] = bien.eau_chaude_energie
            data["energie"]["eau_chaude"] = eau_chaude_data

        return data

    def _extract_bailleur_data(self, bailleur: Bailleur) -> Dict[str, Any]:
        """Extrait les données d'un Bailleur."""

        return serialize_bailleur(bailleur)

    def _extract_bailleurs_data(
        self, bailleurs, user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Extrait les données du bailleur principal et des co-bailleurs.

        Args:
            bailleurs: QuerySet de bailleurs (ManyToMany depuis Bien)
            user: Utilisateur connecté (optionnel).
                  Si fourni, son bailleur sera mis en premier.

        Returns:
            Dict avec bailleur principal et co_bailleurs
        """
        if not bailleurs.exists():
            return {}

        # Trouver le bailleur correspondant au user connecté
        bailleur = None
        if user and hasattr(user, "email"):
            user_email = user.email
            for b in bailleurs.all():
                if b.email == user_email:
                    bailleur = b
                    break

        # Si pas trouvé ou pas de user, prendre le premier
        if not bailleur:
            bailleur = bailleurs.first()

        # Extraire les données du bailleur principal
        data = self._extract_bailleur_data(bailleur)

        # Co-bailleurs = tous SAUF celui en position principale
        # Format attendu : PersonneSerializer (simple)
        co_bailleurs = bailleurs.exclude(id=bailleur.id)
        if co_bailleurs.exists():
            co_bailleurs_list = []
            for co_bailleur in co_bailleurs:
                # Extraire les données de la personne (physique ou signataire)
                if co_bailleur.personne:
                    co_bailleurs_list.append({
                        "lastName": co_bailleur.personne.lastName,
                        "firstName": co_bailleur.personne.firstName,
                        "email": co_bailleur.personne.email,
                        "adresse": co_bailleur.personne.adresse,
                    })
                elif co_bailleur.societe and co_bailleur.signataire:
                    # Pour société, utiliser le signataire
                    co_bailleurs_list.append({
                        "lastName": co_bailleur.signataire.lastName,
                        "firstName": co_bailleur.signataire.firstName,
                        "email": co_bailleur.signataire.email,
                        "adresse": co_bailleur.signataire.adresse,
                    })
            data["co_bailleurs"] = co_bailleurs_list
        else:
            data["co_bailleurs"] = []

        return data

    def fetch_bailleur_data(self, bailleur_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les données d'un Bailleur pour pré-remplir un formulaire.

        Args:
            bailleur_id: UUID du bailleur

        Returns:
            Dict avec les données du bailleur ou None si inexistant
        """
        try:
            bailleur = Bailleur.objects.get(id=bailleur_id)
            return {"bailleur": self._extract_bailleur_data(bailleur)}
        except Bailleur.DoesNotExist:
            return None

    def fetch_draft_bail_data(
        self, bail_id: str, user: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Récupère les données d'un Bail DRAFT pour reprendre l'édition.

        Args:
            bail_id: UUID du bail
            user: Utilisateur connecté (optionnel).
                  Si fourni, son bailleur sera mis en premier.

        Returns:
            Dict avec toutes les données du bail DRAFT
        """
        try:
            from bail.models import Bail

            bail = (
                Bail.objects.select_related(
                    "location__bien",
                    "location__mandataire__signataire",
                    "location__mandataire__societe",
                    "location__rent_terms",
                )
                .prefetch_related(
                    "location__bien__bailleurs__personne",
                    "location__bien__bailleurs__societe",
                    "location__bien__bailleurs__signataire",
                    "location__locataires",
                )
                .get(id=bail_id)
            )

            # Récupérer les données de la location
            if bail.location:
                data = self._extract_location_data(bail.location, user)

                # Ajouter les données spécifiques du bail DRAFT
                # duree_mois est dans le modèle Bail
                if bail.duree_mois:
                    if "dates" not in data:
                        data["dates"] = {}
                    data["dates"]["duree_mois"] = bail.duree_mois

                # Retourner les données ET le location_id (évite requête dupliquée)
                return data, str(bail.location_id)
            return None

        except Exception as e:
            import logging

            logging.error(f"Error in fetch_draft_bail_data: {e}", exc_info=True)
            return None

    def fetch_draft_edl_data(
        self, etat_lieux_id: str, user: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Récupère les données d'un État des Lieux DRAFT pour reprendre l'édition.

        Args:
            etat_lieux_id: UUID de l'état des lieux
            user: Utilisateur connecté (optionnel).
                  Si fourni, son bailleur sera mis en premier.

        Returns:
            Dict avec toutes les données de l'EDL DRAFT (location + pièces + équipements)
        """
        try:
            from etat_lieux.models import EtatLieux

            edl = (
                EtatLieux.objects.select_related(
                    "location__bien",
                    "location__mandataire__signataire",
                    "location__mandataire__societe",
                    "location__rent_terms",
                )
                .prefetch_related(
                    "location__bien__bailleurs__personne",
                    "location__bien__bailleurs__societe",
                    "location__bien__bailleurs__signataire",
                    "location__locataires",
                    "pieces__equipements__photos",  # Charger pièces + équipements + photos
                )
                .get(id=etat_lieux_id)
            )

            # Récupérer les données de la location
            if edl.location:
                data = self._extract_location_data(edl.location, user)

                # Ajouter les données spécifiques de l'EDL
                data["type_etat_lieux"] = edl.type_etat_lieux
                data["date_etat_lieux"] = edl.date_etat_lieux.isoformat()

                # Nombre de clés
                if edl.nombre_cles:
                    data["nombre_cles"] = edl.nombre_cles

                # Compteurs
                if edl.compteurs:
                    data["compteurs"] = edl.compteurs

                # Commentaires généraux
                if edl.commentaires_generaux:
                    data["commentaires_generaux"] = edl.commentaires_generaux

                # Charger les pièces avec leurs équipements
                pieces_data = []
                for piece in edl.pieces.all():
                    piece_data = {
                        "id": str(piece.id),
                        "name": piece.nom,  # Frontend attend "name"
                        "type": piece.type_piece,  # Frontend attend "type"
                        "equipments": [],  # Frontend attend "equipments"
                        # Liste des equipment_key sélectionnés
                        "selected_equipment_keys": [],
                    }

                    # Charger les équipements de la pièce
                    for equipement in piece.equipements.all():
                        equipement_data = {
                            "id": str(equipement.id),
                            "equipment_type": equipement.equipment_type,
                            "equipment_key": equipement.equipment_key,
                            "equipment_name": equipement.equipment_name,
                            "piece_id": str(piece.id),
                            "state": equipement.state,
                            "comment": equipement.comment or "",
                            "photos": [],
                        }
                        # Ajouter quantity si présent
                        if (
                            hasattr(equipement, "quantity")
                            and equipement.quantity is not None
                        ):
                            equipement_data["quantity"] = equipement.quantity

                        # Charger les photos
                        for photo in equipement.photos.all():
                            photo_data = {
                                "id": str(photo.id),
                                "url": photo.image.url,
                                "name": photo.nom_original,  # Frontend attend "name"
                            }
                            equipement_data["photos"].append(photo_data)

                        piece_data["equipments"].append(equipement_data)
                        # Ajouter l'equipment_key à la liste des sélectionnés
                        piece_data["selected_equipment_keys"].append(
                            equipement.equipment_key
                        )

                    pieces_data.append(piece_data)

                # Le serializer s'attend à "rooms" pas "pieces"
                data["rooms"] = pieces_data
                # Alias pour le step "description_pieces"
                # (pour que _step_has_value le détecte)
                data["description_pieces"] = pieces_data

                # Charger les équipements de chauffage (niveau global)
                from etat_lieux.models import EquipmentType

                equipements_chauffage = []
                chauffage_query = edl.equipements.filter(
                    equipment_type=EquipmentType.CHAUFFAGE
                )
                for equipement in chauffage_query:
                    equipement_data = {
                        "id": str(equipement.id),
                        "equipment_type": equipement.equipment_type,
                        "equipment_key": equipement.equipment_key,
                        "equipment_name": equipement.equipment_name,
                        "marque": getattr(equipement, "marque", None),
                        "numero_serie": getattr(equipement, "numero_serie", None),
                        "date_entretien": getattr(equipement, "date_entretien", None),
                        "state": equipement.state,
                        "comment": equipement.comment or "",
                        "photos": [],
                    }
                    # Charger les photos
                    for photo in equipement.photos.all():
                        photo_data = {
                            "id": str(photo.id),
                            "url": photo.image.url,
                            "name": photo.nom_original,
                        }
                        equipement_data["photos"].append(photo_data)
                    equipements_chauffage.append(equipement_data)
                if equipements_chauffage:
                    data["equipements_chauffage"] = equipements_chauffage

                # Charger les annexes privatives (niveau global)
                # Le step attend le chemin: bien.equipements.annexes_privatives_equipements
                # Format: {uuid: {id, type, label, state, comment, photos}}
                annexes_privatives_equipements = {}
                for equipement in edl.equipements.filter(
                    equipment_type=EquipmentType.ANNEXE
                ):
                    annexes_privatives_equipements[str(equipement.id)] = {
                        "id": str(equipement.id),
                        "type": equipement.equipment_key,
                        "label": equipement.equipment_name,
                        "state": equipement.state,
                        "comment": equipement.comment or "",
                        "photos": [
                            {
                                "id": str(photo.id),
                                "url": photo.image.url,
                                "name": photo.nom_original,
                            }
                            for photo in equipement.photos.all()
                        ],
                    }
                if annexes_privatives_equipements:
                    # Mettre au bon endroit dans l'arborescence
                    if "bien" not in data:
                        data["bien"] = {}
                    if "equipements" not in data["bien"]:
                        data["bien"]["equipements"] = {}
                    bien_equipements = data["bien"]["equipements"]
                    bien_equipements["annexes_privatives_equipements"] = (
                        annexes_privatives_equipements
                    )
                    # Alias au niveau racine pour le formulaire
                    data["annexes_privatives_equipements"] = (
                        annexes_privatives_equipements
                    )

                # Retourner les données ET le location_id (évite requête dupliquée)
                return data, str(edl.location_id)
            return None

        except Exception as e:
            import traceback

            print(f"Error in fetch_draft_edl_data: {e}")
            traceback.print_exc()
            return None
