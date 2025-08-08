import logging

from django.conf import settings

from bail.models import BailSpecificites
from bail.utils import send_mail
from etat_lieux.models import (
    EtatLieux,
    EtatLieuxPhoto,
    EtatLieuxPiece,
    EtatLieuxPieceDetail,
    EtatLieuxSignatureRequest,
)

logger = logging.getLogger(__name__)


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
    Bonjour {person.prenom} {person.nom},

    Vous êtes invité(e) à signer l'état des lieux {etat_lieux.get_type_etat_lieux_display()} 
    pour le bien situé à : {etat_lieux.bien.adresse}

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
        "salons": {"type": "living", "nom_base": "Salon"},
        "cuisines": {"type": "kitchen", "nom_base": "Cuisine"},
        "sallesDeBain": {"type": "bathroom", "nom_base": "Salle de bain"},
        "sallesEau": {"type": "bathroom", "nom_base": "Salle d'eau"},
        "wc": {"type": "bathroom", "nom_base": "WC"},
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


def create_etat_lieux_from_form_data(form_data, bail_id, user):
    """
    Crée un état des lieux à partir des données du formulaire.
    Simple et direct.
    """

    # Récupérer le bail
    bail = BailSpecificites.objects.get(id=bail_id)

    # Créer l'état des lieux principal avec les informations complémentaires
    etat_lieux = EtatLieux.objects.create(
        bail=bail,
        type_etat_lieux=form_data.get("type", "entree"),
        nombre_cles=form_data.get("nombreCles", {}),
        equipements_chauffage=form_data.get("equipementsChauffage", {}),
        compteurs=form_data.get("compteurs", {}),
    )

    # Récupérer les pièces du bien (ou les créer si elles n'existent pas)
    pieces = get_or_create_pieces_for_bien(bail.bien)

    # Créer les détails pour chaque pièce depuis les données du formulaire
    rooms_by_id = {}
    for room_data in form_data.get("rooms", []):
        room_id = room_data.get("id")
        if room_id:
            rooms_by_id[room_id] = room_data

    for piece in pieces:
        room_data = rooms_by_id.get(str(piece.id), {})
        EtatLieuxPieceDetail.objects.create(
            etat_lieux=etat_lieux,
            piece=piece,
            elements=room_data.get("elements", {}),
            equipments=room_data.get("equipments", []),
            mobilier=room_data.get("mobilier", []),
        )

    logger.info(f"État des lieux créé: {etat_lieux.id} avec {len(pieces)} pièces")
    return etat_lieux


def save_etat_lieux_photos(etat_lieux, uploaded_photos, photo_references):
    """
    Sauvegarde les photos uploadées pour un état des lieux.
    Super simple maintenant !
    """

    if not uploaded_photos:
        return

    saved_photos = []

    # Récupérer toutes les pièces du bien
    pieces = etat_lieux.bail.bien.pieces_etat_lieux.all()
    pieces_map = {str(piece.id): piece for piece in pieces}

    for photo_ref in photo_references:
        frontend_room_id = photo_ref["room_id"]  # UUID de la pièce
        photo_key = (
            f"{frontend_room_id}_{photo_ref['element_key']}_{photo_ref['photo_index']}"
        )

        if photo_key in uploaded_photos and frontend_room_id in pieces_map:
            uploaded_file = uploaded_photos[photo_key]
            piece = pieces_map[frontend_room_id]

            # Créer la photo directement liée à la pièce
            photo = EtatLieuxPhoto.objects.create(
                piece=piece,
                element_key=photo_ref["element_key"],
                photo_index=photo_ref["photo_index"],
                image=uploaded_file,
                nom_original=uploaded_file.name,
            )

            saved_photos.append(
                {
                    "id": str(photo.id),
                    "piece_id": str(photo.piece.id),
                    "piece_nom": photo.piece.nom,
                    "element_key": photo.element_key,
                    "photo_index": photo.photo_index,
                    "url": photo.image.url,
                    "original_name": photo.nom_original,
                }
            )

    logger.info(f"Sauvegardé {len(saved_photos)} photos")
    return saved_photos
