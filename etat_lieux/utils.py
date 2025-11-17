"""
Utilitaires pour la nouvelle architecture EtatLieux
"""

import logging
from typing import Dict, List

from etat_lieux.models import (
    EtatLieux,
    EtatLieuxEquipement,
    EtatLieuxPhoto,
    EtatLieuxPiece,
    EtatLieuxSignatureRequest,
)
from location.models import Location
from location.services.document_utils import determine_mandataire_doit_signer
from signature.services import create_signature_requests_generic

logger = logging.getLogger(__name__)

# Configuration des équipements de chauffage
CHAUFFAGE_EQUIPMENT_CONFIG = {
    "chaudiere": {"name": "Chaudière", "icon": "🔥"},
    "chauffe_eau": {"name": "Chauffe-eau", "icon": "🚿"},
}


class StateEquipmentUtils:
    """Classe utilitaire pour la gestion des états des éléments"""

    STATE_LABELS = {
        "TB": "Très bon",
        "B": "Bon",
        "P": "Passable",
        "M": "Mauvais",
        "": "Non renseigné",
    }

    STATE_CSS_CLASSES = {
        "TB": "state-excellent",
        "B": "state-good",
        "P": "state-fair",
        "M": "state-poor",
        "": "state-empty",
    }

    STATE_COLORS = {
        "TB": "#10b981",  # green
        "B": "#22c55e",  # light green
        "P": "#f97316",  # orange
        "M": "#ef4444",  # red
        "": "#9ca3af",  # gray
    }

    MONTHS = {
        "01": "Janvier",
        "02": "Février",
        "03": "Mars",
        "04": "Avril",
        "05": "Mai",
        "06": "Juin",
        "07": "Juillet",
        "08": "Août",
        "09": "Septembre",
        "10": "Octobre",
        "11": "Novembre",
        "12": "Décembre",
    }

    @classmethod
    def get_state_display(cls, state):
        """Retourne le label d'affichage pour un état"""
        return cls.STATE_LABELS.get(state, cls.STATE_LABELS[""])

    @classmethod
    def get_state_css_class(cls, state):
        """Retourne la classe CSS pour un état"""
        return cls.STATE_CSS_CLASSES.get(state, cls.STATE_CSS_CLASSES[""])

    @classmethod
    def get_state_color(cls, state):
        """Retourne la couleur pour un état"""
        return cls.STATE_COLORS.get(state, cls.STATE_COLORS[""])

    @classmethod
    def format_date_entretien(cls, date_str):
        """Formate une date d'entretien YYYY-MM en format lisible"""
        if not date_str:
            return ""

        date_parts = date_str.split("-")
        if len(date_parts) != 2:
            return ""

        year, month = date_parts
        month_name = cls.MONTHS.get(month, "")

        if month_name:
            return f"{month_name} {year}"

        return ""

    @classmethod
    def enrich_element(cls, element_key, element_data, photos=None):
        """Enrichit les données d'un élément avec les labels et classes CSS"""
        state = element_data.get("state", "")

        return {
            "key": element_key,
            "name": element_key.replace("_", " ").title(),
            "state": state,
            "state_display": cls.get_state_display(state),
            "state_css_class": cls.get_state_css_class(state),
            "state_color": cls.get_state_color(state),
            "comment": element_data.get("comment", ""),
            "photos": photos or [],
        }


def create_etat_lieux_signature_requests(etat_lieux, user=None):
    """
    Crée les demandes de signature pour un état des lieux.
    Utilise la fonction générique pour factoriser le code.

    Args:
        etat_lieux: Instance d'EtatLieux
        user: User qui a créé le document (sera le premier signataire)
    """

    create_signature_requests_generic(etat_lieux, EtatLieuxSignatureRequest, user=user)


def create_equipments(etat_lieux: EtatLieux, equipments_data: List[Dict]) -> None:
    """
    Crée les équipements d'un état des lieux.
    Note: Les équipements sont toujours créés, jamais mis à jour car
    l'ancien état des lieux est supprimé avant.

    Args:
        etat_lieux: L'état des lieux
        equipments_data: Liste des équipements avec leur données
    """
    logger.info(f"create_equipments: création de {len(equipments_data)} équipements")

    # Créer un mapping des pièces par ID
    # Note: Les IDs des pièces ont déjà été transformés en IDs uniques
    pieces_by_id = {str(piece.id): piece for piece in etat_lieux.pieces.all()}
    logger.info(f"Pièces disponibles pour liaison: {list(pieces_by_id.keys())}")

    for equipment_data in equipments_data:
        equipment_id = equipment_data.get("id")

        if not equipment_id:
            logger.warning(f"Équipement sans ID ignoré: {equipment_data}")
            continue

        # Préparer les données de l'équipement
        equipment_type = equipment_data.get("equipment_type")
        logger.info(
            f"Création équipement {equipment_id}: type={equipment_type}, "
            f"key={equipment_data.get('equipment_key')}"
        )

        equipment_fields = {
            "etat_lieux": etat_lieux,
            "equipment_type": equipment_type,
            "equipment_key": equipment_data.get("equipment_key"),
            "equipment_name": equipment_data.get("equipment_name"),
            "state": equipment_data.get("state"),
            "comment": equipment_data.get("comment"),
            "quantity": equipment_data.get("quantity"),
            "data": equipment_data.get("data"),
        }

        # Ajouter la pièce si c'est un équipement de pièce
        if equipment_fields["equipment_type"] == "piece":
            piece_id = equipment_data.get("piece_id")
            if piece_id and piece_id in pieces_by_id:
                equipment_fields["piece"] = pieces_by_id[piece_id]
            else:
                logger.warning(
                    f"Pièce {piece_id} non trouvée pour équipement {equipment_id}"
                )

        # Toujours créer un nouvel équipement pour ce nouvel état des lieux
        # L'ancien état des lieux et ses équipements ont été supprimés avant
        equipment_fields["id"] = equipment_id
        EtatLieuxEquipement.objects.create(**equipment_fields)
        logger.info(f"Équipement créé: {equipment_id}")


def save_equipment_photos(
    etat_lieux: EtatLieux,
    uploaded_photos: Dict,
    photo_references: List[Dict],
    equipment_id_map: Dict = None,
) -> List[Dict]:
    """
    Sauvegarde les photos des équipements.

    Args:
        etat_lieux: L'état des lieux
        uploaded_photos: Dictionnaire des fichiers uploadés {key: file} (DEPRECATED)
        photo_references: Liste des références de photos avec photo_id
        equipment_id_map: Mapping des clés composites vers les vrais UUIDs

    Note: Depuis l'upload immédiat, toutes les photos utilisent photo_id.
          Le paramètre uploaded_photos est gardé pour compatibilité
          mais n'est plus utilisé.
    """
    if not photo_references:
        logger.info("Aucune photo_reference reçue")
        return []

    logger.info(
        f"Traitement de {len(photo_references)} photo_references "
        f"pour EDL {etat_lieux.id}"
    )

    saved_photos = []

    # Récupérer tous les équipements de cet état des lieux
    equipments_by_id = {str(eq.id): eq for eq in etat_lieux.equipements.all()}
    logger.info(f"Équipements disponibles : {list(equipments_by_id.keys())}")

    # Créer aussi un mapping par clé composite pour compatibilité
    equipments_by_composite_key = {}
    for eq in etat_lieux.equipements.all():
        if eq.piece_id and eq.equipment_key:
            # Créer la clé composite pièce_id + equipment_key
            composite_key = f"{eq.piece_id}_{eq.equipment_key}"
            equipments_by_composite_key[composite_key] = eq

    for photo_ref in photo_references:
        equipment_id = photo_ref.get("equipment_id")
        photo_index = photo_ref.get("photo_index")
        photo_id = photo_ref.get("photo_id")  # ✅ UUID de photo uploadée

        logger.info(
            f"Traitement photo_ref: equipment_id={equipment_id}, "
            f"photo_index={photo_index}, photo_id={photo_id}"
        )

        # Essayer d'abord avec l'ID direct
        equipment = equipments_by_id.get(equipment_id)

        # Si pas trouvé et qu'on a un mapping, essayer avec le mapping
        if not equipment and equipment_id_map and equipment_id in equipment_id_map:
            real_equipment_id = equipment_id_map[equipment_id]
            equipment = equipments_by_id.get(real_equipment_id)

        # Si toujours pas trouvé, essayer avec la clé composite
        if not equipment:
            equipment = equipments_by_composite_key.get(equipment_id)

        if not equipment:
            logger.warning(
                f"Photo ignorée - équipement {equipment_id} non trouvé. "
                f"IDs disponibles: {list(equipments_by_id.keys())[:5]}..."
            )
            continue

        logger.info(f"Équipement trouvé : {equipment.equipment_name} ({equipment.id})")

        # ✅ CAS 1 : Photo existante (uploadée via /upload-photo/)
        if photo_id:
            try:
                photo = EtatLieuxPhoto.objects.get(id=photo_id)
                # Attacher au nouvel équipement
                photo.equipment = equipment
                photo.photo_index = photo_index
                photo.save()

                saved_photos.append(
                    {
                        "id": str(photo.id),
                        "equipment_id": str(equipment.id),
                        "photo_index": photo_index,
                        "url": photo.image.url,
                        "original_name": photo.nom_original,
                    }
                )

                logger.info(
                    f"Photo {photo_id} attachée à "
                    f"équipement {equipment.equipment_name}"
                )
            except EtatLieuxPhoto.DoesNotExist:
                logger.warning(
                    f"Photo {photo_id} non trouvée, ignorée"
                )
        # Note: Toutes les photos sont uploadées via /upload-photo/ avant submit
        # Donc photo_id est toujours présent, pas de photo_key
        else:
            logger.warning(
                f"Photo sans photo_id pour équipement {equipment_id} - ignorée"
            )

    logger.info(
        f"Sauvegardé {len(saved_photos)} photos sur {len(photo_references)} références"
    )

    return saved_photos


def transform_rooms_to_pieces_and_equipments(
    rooms: List[Dict],
) -> tuple[List[Dict], List[Dict]]:
    """
    Transforme la structure rooms du frontend en pièces et équipements.

    Args:
        rooms: Liste des rooms depuis le frontend

    Returns:
        Tuple (pieces, equipments)
    """

    pieces = []
    equipments = []

    for room in rooms:
        if not room:
            continue

        # La pièce DOIT avoir un ID (UUID)
        piece_id = room.get("id")
        if not piece_id:
            raise ValueError(f"Room sans ID: {room.get('name')}")

        pieces.append(
            {
                "id": piece_id,  # Utiliser directement l'UUID du frontend
                "nom": room.get("name"),
                "type_piece": room.get("type"),
            }
        )

        # Traiter tous les équipements du frontend
        room_equipments = room.get("equipments", [])

        for equipment in room_equipments:
            if not equipment:
                continue

            equipment_id = equipment.get("id")
            if not equipment_id:
                raise ValueError(f"Equipment sans ID dans la pièce {piece_id}")

            equipments.append(
                {
                    "id": equipment_id,
                    "equipment_type": equipment.get("equipment_type"),
                    "equipment_key": equipment.get("equipment_key"),
                    "equipment_name": equipment.get("equipment_name"),
                    "piece_id": piece_id,
                    "state": equipment.get("state"),
                    "comment": equipment.get("comment"),
                    "quantity": equipment.get("quantity"),
                    "data": equipment.get("data", {}),
                }
            )

    logger.info(f"Transformation: {len(pieces)} pièces, {len(equipments)} équipements")
    return pieces, equipments


def create_etat_lieux_from_form_data(
    form_data: Dict, location_id: str, user=None
) -> tuple[EtatLieux, Dict]:
    """
    Crée un état des lieux à partir des données du formulaire.

    Args:
        form_data: Données du formulaire
        location_id: ID de la location
    """

    # Récupérer la location
    location = Location.objects.get(id=location_id)
    type_etat_lieux = form_data.get("type_etat_lieux")

    # Déterminer si le mandataire doit signer

    user_role = form_data.get("user_role")
    mandataire_doit_signer = determine_mandataire_doit_signer(user_role, form_data)

    # Créer l'état des lieux
    etat_lieux = EtatLieux.objects.create(
        location=location,
        type_etat_lieux=type_etat_lieux,
        date_etat_lieux=form_data.get("date_etat_lieux"),
        nombre_cles=form_data.get("nombre_cles"),
        compteurs=form_data.get("compteurs"),
        commentaires_generaux=form_data.get("commentaires_generaux"),
        mandataire_doit_signer=mandataire_doit_signer,
    )

    # Initialiser les variables
    pieces = []
    equipments = []

    # 1. Traiter les rooms (pièces et leurs équipements)
    rooms = form_data.get("rooms", [])
    if rooms:
        logger.info(f"Traitement de {len(rooms)} rooms")
        pieces, equipments = transform_rooms_to_pieces_and_equipments(rooms)
        for piece_data in pieces:
            piece_id = piece_data.get("id")
            if piece_id:
                EtatLieuxPiece.objects.create(
                    id=piece_id,
                    etat_lieux=etat_lieux,
                    nom=piece_data.get("nom"),
                    type_piece=piece_data.get("type_piece"),
                )
                logger.info(f"Pièce créée: {piece_id} - {piece_data.get('nom')}")

    # 2. Traiter les équipements de chauffage (indépendant des rooms)
    equipements_chauffage = form_data.get("equipements_chauffage", [])
    for chauffage_data in equipements_chauffage:
        if not chauffage_data:
            continue

        equipment_id = chauffage_data.get("id")
        if not equipment_id:
            logger.warning("Équipement de chauffage sans ID ignoré")
            continue

        equipment_type_key = chauffage_data.get("equipment_key")
        if not equipment_type_key:
            logger.warning(f"Chauffage sans equipment_key ignoré: {equipment_id}")
            continue

        # Les données sont déjà au bon format depuis le frontend
        equipment_data = {
            "id": equipment_id,
            "equipment_type": chauffage_data.get("equipment_type"),
            "equipment_key": equipment_type_key,
            "equipment_name": chauffage_data.get("equipment_name"),
            "state": chauffage_data.get("state"),
            "comment": chauffage_data.get("comment"),
            "data": chauffage_data.get("data", {}),
        }

        equipments.append(equipment_data)

    # 3. Traiter les annexes privatives (dict avec UUID comme clés)
    annexes_privatives = form_data.get("annexes_privatives_equipements", {})

    if isinstance(annexes_privatives, dict):
        logger.info(f"Annexes privatives: {len(annexes_privatives)} annexe(s)")

        # Format dict: {uuid: {type, state, comment, photos, ...}}
        for annexe_uuid, annexe_data in annexes_privatives.items():
            if not annexe_data or not isinstance(annexe_data, dict):
                continue

            annexe_type = annexe_data.get("type")
            annexe_label = annexe_data.get("label")

            if not annexe_type:
                logger.warning(f"Annexe {annexe_uuid} sans type ignorée")
                continue

            # Utiliser le label fourni, sinon fallback sur le type formaté
            equipment_name = (
                annexe_label if annexe_label else annexe_type.replace("_", " ").title()
            )

            equipments.append(
                {
                    "id": annexe_uuid,  # ✅ UUID de la clé dict
                    "equipment_type": "annexe",
                    "equipment_key": annexe_type,
                    "equipment_name": equipment_name,
                    "state": annexe_data.get("state"),
                    "comment": annexe_data.get("comment"),
                    "data": {},
                }
            )
    else:
        logger.warning(
            f"annexes_privatives_equipements format invalide: "
            f"{type(annexes_privatives).__name__}, attendu: dict"
        )

    # 4. Créer tous les équipements (rooms + chauffage + annexes)
    logger.info(f"Création de {len(equipments)} équipements")
    if equipments:
        create_equipments(etat_lieux, equipments)
    else:
        logger.warning("Aucun équipement à créer!")

    logger.info(f"État des lieux créé: {etat_lieux.id}")

    # Plus besoin d'equipment_id_map, les IDs sont fournis par le frontend
    return etat_lieux, {}


def save_etat_lieux_photos(etat_lieux, uploaded_photos, photo_references):
    """
    Wrapper pour la compatibilité avec l'ancien nom de fonction.
    """
    return save_equipment_photos(etat_lieux, uploaded_photos, photo_references)
