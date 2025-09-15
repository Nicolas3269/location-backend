import logging

from django.conf import settings

from bail.utils import send_mail
from etat_lieux.models import (
    EtatLieux,
    EtatLieuxPhoto,
    EtatLieuxPiece,
    EtatLieuxPieceDetail,
    EtatLieuxSignatureRequest,
)

logger = logging.getLogger(__name__)


class EtatElementUtils:
    """Classe utilitaire pour la gestion des états des éléments"""

    ETAT_LABELS = {
        'TB': 'Très bon',
        'B': 'Bon',
        'P': 'Passable',
        'M': 'Mauvais',
        '': 'Non renseigné'
    }

    ETAT_CSS_CLASSES = {
        'TB': 'state-excellent',
        'B': 'state-good',
        'P': 'state-fair',
        'M': 'state-poor',
        '': 'state-empty'
    }

    ETAT_COLORS = {
        'TB': '#10b981',  # green
        'B': '#22c55e',   # light green
        'P': '#f97316',   # orange
        'M': '#ef4444',   # red
        '': '#9ca3af'     # gray
    }

    MONTHS = {
        '01': 'Janvier', '02': 'Février', '03': 'Mars', '04': 'Avril',
        '05': 'Mai', '06': 'Juin', '07': 'Juillet', '08': 'Août',
        '09': 'Septembre', '10': 'Octobre', '11': 'Novembre', '12': 'Décembre'
    }

    @classmethod
    def get_etat_display(cls, etat):
        """Retourne le label d'affichage pour un état"""
        return cls.ETAT_LABELS.get(etat, cls.ETAT_LABELS[''])

    @classmethod
    def get_etat_css_class(cls, etat):
        """Retourne la classe CSS pour un état"""
        return cls.ETAT_CSS_CLASSES.get(etat, cls.ETAT_CSS_CLASSES[''])

    @classmethod
    def get_etat_color(cls, etat):
        """Retourne la couleur pour un état"""
        return cls.ETAT_COLORS.get(etat, cls.ETAT_COLORS[''])

    @classmethod
    def format_date_entretien(cls, date_str):
        """Formate une date d'entretien YYYY-MM en format lisible"""
        if not date_str:
            return ''

        date_parts = date_str.split('-')
        if len(date_parts) != 2:
            return ''

        year, month = date_parts
        month_name = cls.MONTHS.get(month, '')

        if month_name:
            return f"{month_name} {year}"

        return ''

    @classmethod
    def enrich_element(cls, element_key, element_data, photos=None):
        """Enrichit les données d'un élément avec les labels et classes CSS"""
        state = element_data.get("state", "")

        return {
            "key": element_key,
            "name": element_key.replace("_", " ").title(),
            "state": state,
            "state_display": cls.get_etat_display(state),
            "state_css_class": cls.get_etat_css_class(state),
            "state_color": cls.get_etat_color(state),
            "comment": element_data.get("comment", ""),
            "photos": photos or [],
        }

    @classmethod
    def format_equipment(cls, equipment_type, equipment_data):
        """Formate les données d'un équipement de chauffage"""
        etat = equipment_data.get('etat', '')

        result = {
            'type': equipment_type,
            'type_label': 'Chaudière' if equipment_type == 'chaudiere' else 'Chauffe-eau',
            'etat': etat,
            'etat_label': cls.get_etat_display(etat),
            'etat_color': cls.get_etat_color(etat),
            'etat_css_class': cls.get_etat_css_class(etat),
            'date_entretien': '',
            'date_entretien_formatted': ''
        }

        # Format date d'entretien pour les chaudières
        if equipment_type == 'chaudiere' and equipment_data.get('date_entretien'):
            result['date_entretien'] = equipment_data['date_entretien']
            result['date_entretien_formatted'] = cls.format_date_entretien(equipment_data['date_entretien'])

        return result


def create_etat_lieux_signature_requests(etat_lieux):
    """
    Crée les demandes de signature pour un état des lieux.
    Utilise la fonction générique pour factoriser le code.
    """
    from signature.services import create_signature_requests_generic

    create_signature_requests_generic(etat_lieux, EtatLieuxSignatureRequest)


def send_etat_lieux_signature_email(signature_request):
    """
    Envoie un email de demande de signature pour un état des lieux.
    Factorisation de la logique d'envoi d'email.
    """

    person = signature_request.bailleur_signataire or signature_request.locataire
    etat_lieux = signature_request.etat_lieux

    subject = (
        f"Signature requise - État des lieux {etat_lieux.get_type_etat_lieux_display()}"
    )

    # URL de signature (à adapter selon votre frontend)
    signature_url = (
        f"{settings.FRONTEND_URL}/etat-lieux/signature/{signature_request.link_token}"
    )

    message = f"""
    Bonjour {person.firstName} {person.lastName},

    Vous êtes invité(e) à signer l'état des lieux {etat_lieux.get_type_etat_lieux_display()} 
    pour le bien situé à : {etat_lieux.location.bien.adresse}

    Pour procéder à la signature, cliquez sur le lien suivant :
    {signature_url}

    Cordialement,
    L'équipe Location
    """

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[person.email],
        )
        logger.info(
            f"Email de signature envoyé à {person.email} pour l'état des lieux {etat_lieux.id}"
        )
    except Exception as e:
        logger.error(
            f"Erreur lors de l'envoi de l'email de signature à {person.email}: {e}"
        )
        raise


def get_or_create_pieces_for_bien(bien):
    """
    Récupère ou crée les pièces pour un bien donné.
    Simple et direct.
    """

    # Vérifier si des pièces existent déjà
    pieces = EtatLieuxPiece.objects.filter(bien=bien)

    if pieces.exists():
        return pieces

    # Sinon, créer les pièces depuis bien.pieces_info
    if not bien.pieces_info:
        # Créer une pièce par défaut
        piece = EtatLieuxPiece.objects.create(
            bien=bien, nom="Pièce principale", type_piece="room"
        )
        return [piece]

    pieces_created = []

    # Créer les pièces basées sur pieces_info
    type_mapping = {
        "chambres": {"type": "bedroom", "nom_base": "Chambre"},
        "sejours": {"type": "living", "nom_base": "Séjour"},
        "cuisines": {"type": "kitchen", "nom_base": "Cuisine"},
        "sallesDeBain": {"type": "bathroom", "nom_base": "Salle de bain"},
        "sallesEau": {"type": "bathroom", "nom_base": "Salle d'eau"},
        "wc": {"type": "bathroom", "nom_base": "WC"},
        "bureau": {"type": "other", "nom_base": "Bureau"},
        "entrees": {"type": "room", "nom_base": "Entrée"},
        "couloirs": {"type": "room", "nom_base": "Couloir"},
        "dressings": {"type": "room", "nom_base": "Dressing"},
        "celliers": {"type": "room", "nom_base": "Cellier"},
        "buanderies": {"type": "room", "nom_base": "Buanderie"},
    }

    for piece_type, count in bien.pieces_info.items():
        if isinstance(count, int) and count > 0 and piece_type in type_mapping:
            mapping = type_mapping[piece_type]
            for i in range(count):
                nom = f"{mapping['nom_base']}"
                if count > 1:
                    nom += f" {i + 1}"

                piece = EtatLieuxPiece.objects.create(
                    bien=bien, nom=nom, type_piece=mapping["type"]
                )
                pieces_created.append(piece)

    logger.info(f"Créé {len(pieces_created)} pièces pour le bien {bien.id}")
    return pieces_created


def create_etat_lieux_from_form_data(form_data, location_id, user):
    """
    Crée un état des lieux à partir des données du formulaire.
    Gère la création/récupération des pièces avec leurs UUIDs.
    Supprime et recrée les pièces si nécessaire pour éviter les incohérences.
    """
    import uuid as uuid_module
    from datetime import datetime

    from django.utils.dateparse import parse_datetime

    from location.models import Location

    # Récupérer la location et le bien
    location = Location.objects.select_related("bien").get(id=location_id)
    bien = location.bien

    # Créer l'état des lieux principal avec les informations complémentaires
    etat_lieux = EtatLieux.objects.create(
        location=location,
        type_etat_lieux=form_data.get("type_etat_lieux", "entree"),
        nombre_cles=form_data.get("nombre_cles", {}),
        equipements_chauffage=form_data.get("equipements_chauffage", {}),
        compteurs=form_data.get("releve_compteurs", {}),
    )

    # Stocker la date de l'état des lieux
    date_etat_lieux = form_data.get("date_etat_lieux")
    if date_etat_lieux:
        # Parser la date si c'est une chaîne
        if isinstance(date_etat_lieux, str):
            date_parsed = parse_datetime(date_etat_lieux)
            if date_parsed:
                date_etat_lieux = date_parsed.date()
            else:
                # Essayer de parser comme date simple
                try:
                    date_etat_lieux = datetime.fromisoformat(
                        date_etat_lieux.replace("Z", "+00:00")
                    ).date()
                except:
                    date_etat_lieux = None

        etat_lieux.date_etat_lieux = date_etat_lieux
        etat_lieux.save(update_fields=["date_etat_lieux"])

    # Gérer les pièces selon le contexte
    # Si on a des rooms avec pieceUuid, on doit créer/récupérer les pièces avec ces UUIDs
    rooms_data = form_data.get("rooms", [])
    pieces_by_uuid = {}

    # Collecter tous les UUIDs des rooms pour savoir quelles pièces garder/créer
    room_uuids = set()
    for room_data in rooms_data:
        piece_uuid = room_data.get("pieceUuid") or room_data.get("id")
        if piece_uuid:
            room_uuids.add(piece_uuid)

    # Récupérer les pièces existantes du bien
    existing_pieces = EtatLieuxPiece.objects.filter(bien=bien)
    existing_uuids = {str(piece.id) for piece in existing_pieces}

    # IMPORTANT: Supprimer les pièces qui ne sont plus dans les rooms
    # pour éviter les incohérences lors de la régénération
    pieces_to_delete = existing_pieces.exclude(id__in=room_uuids)
    if pieces_to_delete.exists():
        logger.info(f"Suppression de {pieces_to_delete.count()} pièces obsolètes")
        pieces_to_delete.delete()

    # Récupérer les pièces restantes
    for piece in existing_pieces.filter(id__in=room_uuids):
        pieces_by_uuid[str(piece.id)] = piece

    # Créer les nouvelles pièces avec les UUIDs fournis
    for room_data in rooms_data:
        piece_uuid = room_data.get("pieceUuid") or room_data.get("id")
        if piece_uuid and piece_uuid not in pieces_by_uuid:
            try:
                # Vérifier si c'est un UUID valide
                uuid_obj = uuid_module.UUID(piece_uuid)

                # Créer ou mettre à jour la pièce
                piece, created = EtatLieuxPiece.objects.update_or_create(
                    id=uuid_obj,
                    defaults={
                        "bien": bien,
                        "nom": room_data.get("name", "Pièce"),
                        "type_piece": room_data.get("type", "room"),
                    },
                )
                pieces_by_uuid[piece_uuid] = piece
                action = "Créé" if created else "Mis à jour"
                logger.info(f"{action} pièce {piece.nom} avec UUID {piece_uuid}")
            except (ValueError, TypeError) as e:
                logger.warning(f"UUID invalide {piece_uuid}: {e}")
                # Si l'UUID n'est pas valide, ignorer cette room
                continue

    # Si aucune pièce n'a été créée/trouvée, utiliser la méthode traditionnelle
    if not pieces_by_uuid:
        logger.warning(
            "Aucune pièce créée depuis les rooms, utilisation de la méthode par défaut"
        )
        pieces = get_or_create_pieces_for_bien(bien)
        pieces_by_uuid = {str(p.id): p for p in pieces}

    pieces = list(pieces_by_uuid.values())

    # Créer les détails pour chaque pièce depuis les données du formulaire
    # Créer un mapping par UUID pour un matching direct et rapide
    rooms_by_uuid = {}

    for room_data in form_data.get("rooms", []):
        # Utiliser pieceUuid (ou id comme fallback) pour le mapping direct
        # Dans le mode standalone, id et pieceUuid sont identiques
        piece_uuid = room_data.get("pieceUuid") or room_data.get("id")
        if piece_uuid:
            rooms_by_uuid[piece_uuid] = room_data

    logger.info(f"Rooms disponibles par UUID: {list(rooms_by_uuid.keys())[:5]}")

    for piece in pieces:
        # Utiliser directement l'UUID de la pièce pour trouver la room correspondante
        room_data = rooms_by_uuid.get(str(piece.id), None)

        if not room_data:
            logger.warning(
                f"Pas de room data trouvée pour la pièce '{piece.nom}' (UUID: {piece.id})"
            )
            logger.debug(f"UUIDs disponibles: {list(rooms_by_uuid.keys())}")
        else:
            logger.debug(
                f"Room data trouvée pour la pièce {piece.nom} via UUID {piece.id}"
            )

        EtatLieuxPieceDetail.objects.create(
            etat_lieux=etat_lieux,
            piece=piece,
            elements=room_data.get("elements", {}) if room_data else {},
            equipments=room_data.get("equipments", []) if room_data else [],
            mobilier=room_data.get("mobilier", []) if room_data else [],
        )

    logger.info(f"État des lieux créé: {etat_lieux.id} avec {len(pieces)} pièces")
    return etat_lieux


def save_etat_lieux_photos(etat_lieux, uploaded_photos, photo_references):
    """
    Sauvegarde les photos uploadées pour un état des lieux.
    Les photos sont maintenant liées aux EtatLieuxPieceDetail spécifiques.
    """

    if not uploaded_photos:
        return

    saved_photos = []

    # Récupérer tous les piece_details de cet état des lieux
    piece_details = etat_lieux.pieces_details.all()

    # Créer un mapping par UUID de pièce -> piece_detail
    piece_details_by_piece_uuid = {str(pd.piece.id): pd for pd in piece_details}

    logger.info(
        f"Photos upload - PieceDetails disponibles: {len(piece_details_by_piece_uuid)}"
    )

    for photo_ref in photo_references:
        # Utiliser l'UUID de la pièce pour trouver le piece_detail
        piece_uuid = photo_ref.get("piece_uuid") or photo_ref.get(
            "room_id"
        )  # room_id pour compatibilité

        photo_key = (
            f"{piece_uuid}_{photo_ref['element_key']}_{photo_ref['photo_index']}"
        )

        # Trouver le piece_detail correspondant
        piece_detail = piece_details_by_piece_uuid.get(piece_uuid)

        if photo_key in uploaded_photos and piece_detail:
            uploaded_file = uploaded_photos[photo_key]

            # Créer la photo liée au piece_detail (spécifique à cet état des lieux)
            photo = EtatLieuxPhoto.objects.create(
                piece_detail=piece_detail,
                element_key=photo_ref["element_key"],
                photo_index=photo_ref["photo_index"],
                image=uploaded_file,
                nom_original=uploaded_file.name,
            )

            saved_photos.append(
                {
                    "id": str(photo.id),
                    "piece_detail_id": str(photo.piece_detail.id),
                    "piece_nom": photo.piece_detail.piece.nom,
                    "element_key": photo.element_key,
                    "photo_index": photo.photo_index,
                    "url": photo.image.url,
                    "original_name": photo.nom_original,
                }
            )
        else:
            logger.warning(
                f"Photo non sauvegardée - piece_uuid: {piece_uuid}, "
                f"piece_detail trouvé: {piece_detail is not None}, "
                f"photo dans uploads: {photo_key in uploaded_photos}"
            )

    logger.info(
        f"Sauvegardé {len(saved_photos)} photos sur {len(photo_references)} références"
    )
    return saved_photos
