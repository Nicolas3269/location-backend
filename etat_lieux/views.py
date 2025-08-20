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
    EtatLieuxPieceDetail,
    EtatLieuxSignatureRequest,
)
from etat_lieux.utils import (
    create_etat_lieux_from_form_data,
    create_etat_lieux_signature_requests,
    save_etat_lieux_photos,
)
from location.models import Bien
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

        # Récupérer ou créer les pièces
        from etat_lieux.utils import get_or_create_pieces_for_bien

        pieces = get_or_create_pieces_for_bien(bien)

        # Formater la réponse avec les UUIDs
        pieces_data = []
        for piece in pieces:
            pieces_data.append(
                {
                    "id": str(piece.id),  # UUID as string
                    "nom": piece.nom,
                    "type": piece.type_piece,
                }
            )

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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_etat_lieux_pdf(request):
    """
    Génère un PDF d'état des lieux à partir des données du formulaire
    """
    try:
        # Vérifier si c'est du FormData (avec photos) ou du JSON simple
        if request.content_type and "multipart/form-data" in request.content_type:
            # Traitement des données avec photos
            json_data_str = request.POST.get("json_data")
            if not json_data_str:
                return JsonResponse(
                    {"success": False, "error": "json_data est requis"}, status=400
                )

            form_data = json.loads(json_data_str)

            # Traiter les photos uploadées
            uploaded_photos = {}
            photo_references = form_data.get("photo_references", [])

            for photo_ref in photo_references:
                field_name = photo_ref["file_field_name"]
                if field_name in request.FILES:
                    uploaded_file = request.FILES[field_name]

                    # Créer une clé unique pour cette photo
                    photo_key = (
                        f"{photo_ref['room_id']}_{photo_ref['element_key']}_"
                        f"{photo_ref['photo_index']}"
                    )
                    uploaded_photos[photo_key] = uploaded_file

            logger.info(f"Reçu {len(uploaded_photos)} photos uploadées")
        else:
            # Traitement des données JSON simple (sans photos)
            form_data = json.loads(request.body)
            uploaded_photos = {}

        location_id = form_data.get("location_id")
        bien_id = form_data.get("bien_id")

        if not location_id and not bien_id:
            return JsonResponse(
                {"success": False, "error": "location_id ou bien_id est requis"}, status=400
            )

        # Si on a un bien_id, récupérer la location active pour ce bien
        if bien_id and not location_id:
            try:
                from location.models import Location
                # Récupérer la location la plus récente pour ce bien
                location = (
                    Location.objects.filter(bien_id=bien_id).order_by("-created_at").first()
                )
                if not location:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": f"Aucune location trouvée pour le bien {bien_id}",
                        },
                        status=404,
                    )
                location_id = location.id
            except Exception as e:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Erreur lors de la récupération de la location: {str(e)}",
                    },
                    status=400,
                )

        # Créer l'état des lieux à partir des données du formulaire

        # Supprimer les anciens états des lieux du même type pour cette location
        # On ne peut avoir qu'un seul état des lieux d'entrée et un seul de sortie
        etat_lieux_type = form_data.get("type", "entree")
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
                # Supprimer d'abord les détails des pièces associés
                # (même si on_delete=CASCADE devrait le faire automatiquement)
                EtatLieuxPieceDetail.objects.filter(
                    etat_lieux=ancien_etat_lieux
                ).delete()

                # Supprimer les demandes de signature associées
                # (au cas où on_delete=CASCADE ne fonctionnerait pas correctement)
                ancien_etat_lieux.signature_requests.all().delete()

                # Supprimer le fichier PDF associé
                if ancien_etat_lieux.pdf:
                    try:
                        ancien_etat_lieux.pdf.delete(save=False)
                    except Exception as e:
                        logger.warning(
                            f"Impossible de supprimer le PDF de l'état des lieux "
                            f"{ancien_etat_lieux.id}: {e}"
                        )

                # Maintenant supprimer l'état des lieux lui-même
                ancien_etat_lieux.delete()

        etat_lieux: EtatLieux = create_etat_lieux_from_form_data(
            form_data, location_id, request.user
        )

        # Sauvegarder les photos si présentes
        if uploaded_photos:
            # Ne PAS supprimer toutes les photos du bien !
            # Les photos sont liées aux pièces, pas aux états des lieux
            # Chaque état des lieux peut avoir ses propres photos
            logger.info(f"Traitement de {len(uploaded_photos)} photos uploadées")

            save_etat_lieux_photos(
                etat_lieux, uploaded_photos, form_data.get("photo_references", [])
            )

        # Préparer les données complètes pour le template

        # Les photos sont maintenant liées aux piece_details spécifiques à cet état des lieux
        # Pas besoin de requête supplémentaire, on va les récupérer via les piece_details

        logger.info(
            f"Préparation des données pour le PDF de l'état des lieux {etat_lieux.id}"
        )

        # Créer la structure complète des pièces avec éléments enrichis
        pieces_enrichies = []

        for piece_detail in etat_lieux.pieces_details.all():
            piece = piece_detail.piece

            # Récupérer les photos de ce piece_detail (spécifiques à cet état des lieux)
            piece_photos = piece_detail.photos.all()
            logger.info(
                f"Pièce {piece.nom} - État des lieux {etat_lieux.id}: {piece_photos.count()} photos"
            )

            # Grouper les photos par élément et convertir en Base64
            photos_by_element = {}
            for photo in piece_photos:
                element_key = photo.element_key
                logger.info(f"Photo: {photo.nom_original}, élément: {element_key}")
                if element_key not in photos_by_element:
                    photos_by_element[element_key] = []

                # Convertir l'image en Base64 pour WeasyPrint
                photo_data_url = image_to_base64_data_url(photo.image)
                if photo_data_url:
                    # Créer un objet photo enrichi avec la data URL
                    photo_enrichi = {
                        "id": photo.id,
                        "nom_original": photo.nom_original,
                        "data_url": photo_data_url,  # Base64 data URL
                        "url": photo.image.url,  # URL originale (pour debug)
                    }
                    photos_by_element[element_key].append(photo_enrichi)
                else:
                    logger.warning(
                        f"Impossible de convertir la photo {photo.nom_original}"
                    )

            # Enrichir chaque élément avec ses données et ses photos
            elements_enrichis = []
            if piece_detail.elements:
                for element_key, element_data in piece_detail.elements.items():
                    element_enrichi = {
                        "key": element_key,
                        "name": element_key.replace("_", " ").title(),
                        "state": element_data.get("state", ""),
                        "state_display": {
                            "TB": "Très bon",
                            "B": "Bon",
                            "P": "Passable",
                            "M": "Mauvais",
                        }.get(element_data.get("state", ""), "Non renseigné"),
                        "state_css_class": {
                            "TB": "state-excellent",
                            "B": "state-good",
                            "P": "state-fair",
                            "M": "state-poor",
                        }.get(element_data.get("state", ""), "state-empty"),
                        "comment": element_data.get("comment", ""),
                        "photos": photos_by_element.get(element_key, []),
                    }
                    elements_enrichis.append(element_enrichi)

            piece_enrichie = {"piece": piece, "elements": elements_enrichis}
            pieces_enrichies.append(piece_enrichie)

            logger.info(
                f"Pièce {piece.nom} enrichie avec {len(elements_enrichis)} éléments"
            )

        # Générer le PDF depuis le template HTML
        html = render_to_string(
            "pdf/etat_lieux.html",
            {
                "etat_lieux": etat_lieux,
                "now": timezone.now(),
                "location": etat_lieux.location,
                "pieces_enrichies": pieces_enrichies,
            },
        )
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()

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

        # Créer les demandes de signature
        create_etat_lieux_signature_requests(etat_lieux)

        first_sign_req = etat_lieux.signature_requests.order_by("order").first()

        return JsonResponse(
            {
                "success": True,
                "etatLieuxId": str(etat_lieux.id),
                "pdfUrl": request.build_absolute_uri(etat_lieux.pdf.url),
                "linkTokenFirstSigner": str(first_sign_req.link_token)
                if first_sign_req
                else None,
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
