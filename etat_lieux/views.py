import base64
import json
import logging
import mimetypes
import os
import uuid

from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from weasyprint import HTML

from backend.pdf_utils import get_static_pdf_iframe_url
from etat_lieux.models import (
    EtatLieux,
    EtatLieuxEquipement,
    EtatLieuxSignatureRequest,
)
from etat_lieux.utils import (
    create_etat_lieux_from_form_data,
    create_etat_lieux_signature_requests,
)
from location.models import Bailleur, Bien, Locataire, Location
from signature.pdf_processing import prepare_pdf_with_signature_fields_generic
from signature.views import (
    confirm_signature_generic,
    get_signature_request_generic,
    resend_otp_generic,
)

logger = logging.getLogger(__name__)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def get_or_create_pieces(request, bien_id):
    """
    Récupère ou crée les pièces pour un bien donné.
    Retourne les pièces avec leurs UUIDs pour synchronisation avec le frontend.
    """
    try:
        # Récupérer le bien
        try:
            bien = Bien.objects.get(id=bien_id)
        except Bien.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": f"Bien {bien_id} non trouvé"},
                status=404,
            )

        # Avec la nouvelle architecture, les pièces sont créées avec l'état des lieux
        # et gérées côté frontend. Cette route retourne une liste vide.
        pieces_data = []

        return JsonResponse(
            {
                "success": True,
                "pieces": pieces_data,
                "bien_id": bien_id,
            }
        )

    except Exception as e:
        logger.exception(
            f"Erreur lors de la récupération des pièces pour le bien {bien_id}"
        )
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=500,
        )


def image_to_base64_data_url(image_field):
    """
    Convertit un ImageField Django en data URL Base64 pour WeasyPrint.
    Évite les timeouts lors de la génération de PDF avec des URLs externes.
    """
    if not image_field or not hasattr(image_field, "path"):
        return None

    try:
        # Lire le contenu du fichier
        with open(image_field.path, "rb") as img_file:
            img_data = img_file.read()

        # Déterminer le type MIME
        content_type, _ = mimetypes.guess_type(image_field.path)
        if not content_type:
            content_type = "image/jpeg"  # Fallback

        # Encoder en Base64
        img_base64 = base64.b64encode(img_data).decode("utf-8")

        # Retourner la data URL complète
        return f"data:{content_type};base64,{img_base64}"

    except Exception as e:
        logger.warning(
            f"Erreur lors de la conversion en Base64 de {image_field.path}: {e}"
        )
        return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_grille_vetuste_pdf(request):
    """Retourne l'URL de la grille de vétusté statique"""
    try:
        # Utiliser notre nouvelle route PDF pour iframe
        full_url = get_static_pdf_iframe_url(request, "bails/grille_vetuste.pdf")

        return JsonResponse(
            {
                "success": True,
                "grilleVetustUrl": full_url,
                "filename": "grille_vetuste.pdf",
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la récupération de la grille de vétusté")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la récupération: {str(e)}"},
            status=500,
        )


def resolve_location_id(location_id, bien_id):
    """
    Résout le location_id à partir du location_id ou bien_id fourni.

    Args:
        location_id: ID de location (peut être None)
        bien_id: ID de bien (peut être None)

    Returns:
        location_id ou None si introuvable

    Raises:
        ValueError: Si aucun ID n'est fourni
        Location.DoesNotExist: Si aucune location n'est trouvée pour le bien
    """
    if not location_id and not bien_id:
        raise ValueError("location_id ou bien_id est requis")

    # Si on a déjà un location_id, le retourner
    if location_id:
        return location_id

    # Sinon, récupérer la location active pour ce bien
    location = Location.objects.filter(bien_id=bien_id).order_by("-created_at").first()

    if not location:
        raise Location.DoesNotExist(f"Aucune location trouvée pour le bien {bien_id}")

    return location.id


def extract_photos_with_references(request, photo_references):
    """
    Extrait les photos depuis une requête multipart en utilisant les références fournies.

    Args:
        request: La requête HTTP
        photo_references: Liste des références de photos depuis validated_data

    Returns:
        dict: Dictionnaire des photos uploadées avec leurs clés
    """
    uploaded_photos = {}

    if photo_references and request.FILES:
        # Extraire les photos selon les références
        for photo_ref in photo_references:
            # Utiliser directement la photo_key fournie par le frontend
            photo_key = photo_ref.get("photo_key")
            if photo_key and photo_key in request.FILES:
                uploaded_file = request.FILES[photo_key]
                uploaded_photos[photo_key] = uploaded_file

        if uploaded_photos:
            logger.info(f"Reçu {len(uploaded_photos)} photos uploadées")

    return uploaded_photos


def extract_form_data_and_photos(request):
    """
    Extrait les données du formulaire et les photos depuis la requête.

    Returns:
        tuple: (form_data, uploaded_photos)
    """
    if request.content_type and "multipart/form-data" in request.content_type:
        json_data_str = request.POST.get("json_data")
        if not json_data_str:
            raise ValueError("json_data est requis pour les requêtes multipart")

        form_data = json.loads(json_data_str)
        # Extraire les photos avec leurs références
        photo_references = form_data.get("photo_references", [])
        uploaded_photos = extract_photos_with_references(request, photo_references)
    else:
        # Traitement des données JSON simple (sans photos)
        form_data = json.loads(request.body)
        uploaded_photos = {}

    return form_data, uploaded_photos


def update_or_create_etat_lieux(location_id, form_data, uploaded_photos, user):
    from django.db import transaction

    etat_lieux_type = form_data.get("type_etat_lieux")

    logger.info(
        f"update_or_create_etat_lieux appelé pour location {location_id}, type {etat_lieux_type}"
    )

    # Utiliser une transaction atomique pour éviter les race conditions
    with transaction.atomic():
        anciens_etats_lieux = EtatLieux.objects.filter(
            location_id=location_id, type_etat_lieux=etat_lieux_type
        )

        if anciens_etats_lieux.exists():
            count = anciens_etats_lieux.count()
            logger.info(
                f"Suppression de {count} ancien(s) état(s) des lieux "
                f"de type '{etat_lieux_type}' pour la location {location_id}"
            )

            for ancien_etat_lieux in anciens_etats_lieux:
                # Supprimer le fichier PDF associé avant de supprimer l'objet
                if ancien_etat_lieux.pdf:
                    try:
                        ancien_etat_lieux.pdf.delete(save=False)
                    except Exception as e:
                        logger.warning(
                            f"Impossible de supprimer le PDF de l'état des lieux "
                            f"{ancien_etat_lieux.id}: {e}"
                        )

                # Supprimer l'état des lieux (CASCADE supprimera automatiquement:
                # - Les pièces (EtatLieuxPiece)
                # - Les équipements (EtatLieuxEquipement)
                # - Les demandes de signature
                # - Les photos associées
                ancien_etat_lieux.delete()
                logger.info(f"État des lieux {ancien_etat_lieux.id} supprimé avec toutes ses dépendances")
        else:
            logger.info(
                f"Aucun ancien état des lieux trouvé pour location {location_id}"
            )

        # Vérifier qu'il n'y a plus d'état des lieux pour cette location avant de créer
        verification = EtatLieux.objects.filter(
            location_id=location_id, type_etat_lieux=etat_lieux_type
        ).exists()
        if verification:
            logger.error("ERREUR: Un état des lieux existe encore après suppression!")

        etat_lieux, equipment_id_map = create_etat_lieux_from_form_data(
            form_data, location_id
        )

    # Sauvegarder les photos si présentes
    if uploaded_photos:
        # Ne PAS supprimer toutes les photos du bien !
        # Les photos sont liées aux pièces, pas aux états des lieux
        # Chaque état des lieux peut avoir ses propres photos
        logger.info(f"Traitement de {len(uploaded_photos)} photos uploadées")

        from etat_lieux.utils import save_equipment_photos

        save_equipment_photos(
            etat_lieux,
            uploaded_photos,
            form_data.get("photo_references", []),
            equipment_id_map,
        )

    return etat_lieux


def add_signature_fields_to_pdf(pdf_bytes, etat_lieux):
    """
    Ajoute les champs de signature à un PDF d'état des lieux.

    Args:
        pdf_bytes: Le contenu du PDF en bytes
        etat_lieux: L'instance EtatLieux

    Returns:
        None (sauvegarde directement dans etat_lieux.pdf)
    """
    # Noms de fichiers
    base_filename = f"etat_lieux_{etat_lieux.id}_{uuid.uuid4().hex}"
    pdf_filename = f"{base_filename}.pdf"
    tmp_pdf_path = f"/tmp/{pdf_filename}"

    try:
        # 1. Sauver temporairement
        with open(tmp_pdf_path, "wb") as f:
            f.write(pdf_bytes)

        # 2. Ajouter champs de signature
        prepare_pdf_with_signature_fields_generic(tmp_pdf_path, etat_lieux)

        # 3. Recharger dans etat_lieux.pdf
        with open(tmp_pdf_path, "rb") as f:
            etat_lieux.pdf.save(pdf_filename, ContentFile(f.read()), save=True)

    finally:
        # 4. Supprimer le fichier temporaire
        try:
            os.remove(tmp_pdf_path)
        except Exception as e:
            logger.warning(
                f"Impossible de supprimer le fichier temporaire {tmp_pdf_path}: {e}"
            )


def prepare_etat_lieux_data_for_pdf(etat_lieux: EtatLieux):
    """
    Prépare et enrichit les données de l'état des lieux pour la génération PDF.
    Convertit les photos en Base64 et structure les données.

    Utilise la nouvelle architecture avec EtatLieuxEquipment.

    Returns:
        dict: Données enrichies pour le template PDF
    """
    logger.info(
        f"Préparation des données pour le PDF de l'état des lieux {etat_lieux.id}"
    )

    from etat_lieux.models import EquipmentType
    from etat_lieux.utils import StateEquipmentUtils

    pieces_enrichies = []

    # Calculer le nombre total de radiateurs
    total_radiateurs = 0

    # Nouvelle architecture : parcourir les pièces
    for piece in etat_lieux.pieces.all():
        # Récupérer les équipements de cette pièce
        equipments: list[EtatLieuxEquipement] = piece.equipements.filter(
            equipment_type=EquipmentType.PIECE
        )

        elements_enrichis = []
        for equipment in equipments:
            # Compter les radiateurs
            if equipment.equipment_key == "radiateur" and equipment.quantity:
                total_radiateurs += equipment.quantity
            # Récupérer les photos de cet équipement
            photos_enrichies = []
            for photo in equipment.photos.all():
                # Convertir l'image en Base64 pour WeasyPrint
                photo_data_url = image_to_base64_data_url(photo.image)
                if photo_data_url:
                    photos_enrichies.append(
                        {
                            "id": photo.id,
                            "nom_original": photo.nom_original,
                            "data_url": photo_data_url,  # Base64 data URL
                            "url": photo.image.url,  # URL originale (pour debug)
                        }
                    )
                else:
                    logger.warning(
                        f"Impossible de convertir la photo {photo.nom_original}"
                    )

            # Créer l'élément enrichi
            element_enrichi = {
                "key": equipment.equipment_key,
                "name": equipment.equipment_name,
                "state": equipment.state,
                "state_display": StateEquipmentUtils.get_state_display(equipment.state),
                "state_css_class": StateEquipmentUtils.get_state_css_class(
                    equipment.state
                ),
                "state_color": StateEquipmentUtils.get_state_color(equipment.state),
                "comment": equipment.comment,
                "quantity": equipment.quantity if hasattr(equipment, 'quantity') else None,
                "photos": photos_enrichies,
            }
            elements_enrichis.append(element_enrichi)

        piece_enrichie = {"piece": piece, "elements": elements_enrichis}
        pieces_enrichies.append(piece_enrichie)

        logger.info(
            f"Pièce {piece.nom} enrichie avec {len(elements_enrichis)} éléments"
        )

    # Support de l'ancienne architecture si des pieces_details existent encore
    if hasattr(etat_lieux, "pieces_details") and etat_lieux.pieces_details.exists():
        logger.info(
            "Détection de l'ancienne architecture pieces_details, support de compatibilité activé"
        )
        for piece_detail in etat_lieux.pieces_details.all():
            piece = piece_detail.piece

            # Récupérer les photos de ce piece_detail
            piece_photos = piece_detail.photos.all()

            # Grouper les photos par élément
            photos_by_element = {}
            for photo in piece_photos:
                element_key = photo.element_key
                if element_key not in photos_by_element:
                    photos_by_element[element_key] = []

                photo_data_url = image_to_base64_data_url(photo.image)
                if photo_data_url:
                    photos_by_element[element_key].append(
                        {
                            "id": photo.id,
                            "nom_original": photo.nom_original,
                            "data_url": photo_data_url,
                            "url": photo.image.url,
                        }
                    )

            # Enrichir chaque élément
            elements_enrichis = []
            if piece_detail.elements:
                for element_key, element_data in piece_detail.elements.items():
                    element_enrichi = StateEquipmentUtils.enrich_element(
                        element_key,
                        element_data,
                        photos=photos_by_element.get(element_key, []),
                    )
                    elements_enrichis.append(element_enrichi)

            piece_enrichie = {"piece": piece, "elements": elements_enrichis}
            pieces_enrichies.append(piece_enrichie)

    # Récupérer les bailleurs et locataires de la location
    location: Location = etat_lieux.location
    bailleurs: list[Bailleur] = location.bien.bailleurs.all() if location.bien else []
    locataires: list[Locataire] = (
        location.locataires.all() if location.locataires else []
    )

    return {
        "etat_lieux": etat_lieux,
        "now": timezone.now(),
        "location": location,
        "bailleurs": bailleurs,
        "locataires": locataires,
        "pieces_enrichies": pieces_enrichies,
        "total_radiateurs": total_radiateurs,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_etat_lieux_pdf(request):
    """
    Génère uniquement le PDF pour un état des lieux existant.
    L'état des lieux doit avoir été créé au préalable via /location/create-or-update/

    Attend:
    - etat_lieux_id: ID de l'état des lieux (obligatoire)
    """
    try:
        etat_lieux_id = request.data.get("etat_lieux_id")
        if not etat_lieux_id:
            return JsonResponse(
                {"success": False, "error": "etat_lieux_id est requis"}, status=400
            )

        # Récupérer l'état des lieux
        from etat_lieux.models import EtatLieux

        try:
            etat_lieux = EtatLieux.objects.get(id=etat_lieux_id)
        except EtatLieux.DoesNotExist:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"État des lieux {etat_lieux_id} non trouvé",
                },
                status=404,
            )

        # Générer le PDF
        context = prepare_etat_lieux_data_for_pdf(etat_lieux)

        # Générer le HTML et le convertir en PDF
        html = render_to_string("pdf/etat_lieux.html", context)
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()

        # Ajouter les champs de signature et sauvegarder le PDF
        add_signature_fields_to_pdf(pdf_bytes, etat_lieux)

        # Créer les demandes de signature
        create_etat_lieux_signature_requests(etat_lieux)

        # Récupérer le token du premier signataire
        first_sign_req = etat_lieux.signature_requests.order_by("order").first()

        # Retourner la réponse
        return JsonResponse(
            {
                "success": True,
                "etatLieuxId": str(etat_lieux.id),
                "pdfUrl": request.build_absolute_uri(etat_lieux.pdf.url),
                "linkTokenFirstSigner": (
                    str(first_sign_req.link_token) if first_sign_req else None
                ),
                "grilleVetustUrl": get_static_pdf_iframe_url(
                    request, "bails/grille_vetuste.pdf"
                ),
                "type": etat_lieux.type_etat_lieux,
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la génération de l'état des lieux PDF")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la génération: {str(e)}"},
            status=500,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_etat_lieux_signature_request(request, token):
    """
    Récupère les informations d'une demande de signature d'état des lieux
    """
    return get_signature_request_generic(request, token, EtatLieuxSignatureRequest)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_signature_etat_lieux(request):
    """
    Confirme la signature d'un état des lieux
    """
    return confirm_signature_generic(request, EtatLieuxSignatureRequest, "etat_lieux")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_otp_etat_lieux(request):
    """
    Renvoie un OTP pour la signature d'état des lieux
    """
    return resend_otp_generic(request, EtatLieuxSignatureRequest, "etat_lieux")
