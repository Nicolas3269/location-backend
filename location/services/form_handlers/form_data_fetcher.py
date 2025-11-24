"""
Service responsable du fetch des données depuis la BDD pour pré-remplir les formulaires.

Responsabilité unique : Récupérer les données existantes d'une Location
et les transformer en dictionnaire utilisable par le frontend.

Utilise les serializers READ pour éviter la duplication de code.
"""

from typing import Any, Dict, Optional, Tuple

from bail.models import Bail
from etat_lieux.models import EquipmentType, EtatLieux
from location.models import Bailleur, Bien, Location
from location.serializers.helpers import (
    extract_bailleurs_with_priority,
    serialize_bailleur_to_dict,
)
from location.serializers.read import (
    BienReadSerializer,
    LocationReadSerializer,
)


class FormDataFetcher:
    """Récupère les données depuis la BDD pour pré-remplir un formulaire."""

    def fetch_location_data(
        self, location_id: str, user: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Récupère toutes les données d'une Location existante.
        Utilise LocationReadSerializer pour garantir cohérence avec la lecture.

        Args:
            location_id: UUID de la location
            user: Utilisateur connecté (optionnel).
                  Si fourni, son bailleur sera mis en premier.

        Returns:
            Dict avec toutes les données extraites ou None si location inexistante
        """
        try:
            # Query optimisée
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

            # Utiliser le serializer READ
            serializer = LocationReadSerializer(location, context={"user": user})
            return serializer.data

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

            from location.serializers.helpers import restructure_bien_to_nested_format

            # Données du bien - utiliser le serializer READ
            bien_serializer = BienReadSerializer(bien)
            bien_data = bien_serializer.data

            # Restructurer en format nested avec zone calculée depuis GPS
            data = {
                "bien": restructure_bien_to_nested_format(
                    bien_data, calculate_zone_from_gps=True
                ),
                "bailleur": extract_bailleurs_with_priority(bien.bailleurs, user),
            }

            return data

        except Bien.DoesNotExist:
            return None

    def fetch_bailleur_data(self, bailleur_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les données d'un Bailleur pour pré-remplir un formulaire.

        Args:
            bailleur_id: UUID du bailleur

        Returns:
            Dict avec les données du bailleur ou None si inexistant
        """

        try:
            bailleur = Bailleur.objects.select_related(
                "personne", "societe", "signataire"
            ).get(id=bailleur_id)

            # Utiliser directement le helper
            return {"bailleur": serialize_bailleur_to_dict(bailleur)}

        except Bailleur.DoesNotExist:
            return None

    def fetch_draft_bail_data(
        self, bail_id: str, user: Optional[Any] = None
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Récupère les données d'un Bail DRAFT pour reprendre l'édition.
        Réutilise fetch_location_data() + ajoute données spécifiques Bail.

        Args:
            bail_id: UUID du bail
            user: Utilisateur connecté (optionnel).
                  Si fourni, son bailleur sera mis en premier.

        Returns:
            Tuple (données, location_id) ou None si bail inexistant
        """
        try:
            bail = Bail.objects.select_related("location").get(id=bail_id)

            # Réutiliser fetch_location_data (utilise LocationReadSerializer)
            data = self.fetch_location_data(str(bail.location_id), user)

            if not data:
                return None

            # Ajouter les données spécifiques du bail DRAFT
            if bail.duree_mois:
                if "dates" not in data:
                    data["dates"] = {}
                data["dates"]["duree_mois"] = bail.duree_mois

            # Retourner les données ET le location_id
            return data, str(bail.location_id)

        except Exception as e:
            import logging

            logging.error(f"Error in fetch_draft_bail_data: {e}", exc_info=True)
            return None

    def fetch_draft_edl_data(
        self, etat_lieux_id: str, user: Optional[Any] = None
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Récupère les données d'un État des Lieux DRAFT pour reprendre l'édition.

        Args:
            etat_lieux_id: UUID de l'état des lieux
            user: Utilisateur connecté (optionnel).
                  Si fourni, son bailleur sera mis en premier.

        Returns:
            Tuple (données, location_id) ou None si EDL inexistant
        """
        try:
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

            # Récupérer les données de la location (utilise LocationReadSerializer)
            if edl.location:
                data = self.fetch_location_data(str(edl.location_id), user)

                if not data:
                    return None

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
                from etat_lieux.models import (
                    EtatLieuxEquipement,
                    EtatLieuxPhoto,
                    EtatLieuxPiece,
                )

                pieces: list[EtatLieuxPiece] = edl.pieces.all()
                for piece in pieces:
                    piece_data = {
                        "id": str(piece.id),
                        "name": piece.nom,  # Frontend attend "name"
                        "type": piece.type_piece,  # Frontend attend "type"
                        "equipments": [],  # Frontend attend "equipments"
                        "selected_equipment_keys": [],
                    }

                    # Charger les équipements de la pièce
                    equipements: list[EtatLieuxEquipement] = piece.equipements.all()
                    for equipement in equipements:
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
                                "name": photo.nom_original,
                            }
                            equipement_data["photos"].append(photo_data)

                        piece_data["equipments"].append(equipement_data)
                        piece_data["selected_equipment_keys"].append(
                            equipement.equipment_key
                        )

                    pieces_data.append(piece_data)

                # Le serializer s'attend à "rooms" pas "pieces"
                data["rooms"] = pieces_data
                # Alias pour le step "description_pieces"
                data["description_pieces"] = pieces_data

                # Charger les équipements de chauffage (niveau global)
                equipements_chauffage = []
                chauffage_querylist: list[EtatLieuxEquipement] = edl.equipements.filter(
                    equipment_type=EquipmentType.CHAUFFAGE
                )
                for equipement in chauffage_querylist:
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
                    photos: list[EtatLieuxPhoto] = equipement.photos.all()
                    for photo in photos:
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
                annexes_privatives_equipements = {}
                annexes_privatives_querylist: list[EtatLieuxEquipement] = (
                    edl.equipements.filter(equipment_type=EquipmentType.ANNEXE)
                )
                for equipement in annexes_privatives_querylist:
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

                # Retourner les données ET le location_id
                return data, str(edl.location_id)

            return None

        except Exception as e:
            import traceback

            print(f"Error in fetch_draft_edl_data: {e}")
            traceback.print_exc()
            return None
