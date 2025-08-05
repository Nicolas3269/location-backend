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
from rest_framework.permissions import IsAuthenticated
from weasyprint import HTML

from backend.pdf_utils import get_static_pdf_iframe_url
from bail.models import BailSpecificites
from etat_lieux.models import (
    EtatLieux,
    EtatLieuxPhoto,
)
from etat_lieux.utils import (
    create_etat_lieux_from_form_data,
    create_etat_lieux_signature_requests,
    prepare_etat_lieux_pdf_with_signature_fields,
    save_etat_lieux_photos,
)

logger = logging.getLogger(__name__)


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

        bail_id = form_data.get("bail_id")
        bien_id = form_data.get("bien_id")

        if not bail_id and not bien_id:
            return JsonResponse(
                {"success": False, "error": "bail_id ou bien_id est requis"}, status=400
            )

        # Si on a un bien_id, récupérer le bail actif pour ce bien
        if bien_id and not bail_id:
            try:
                # Récupérer le bail le plus récent pour ce bien
                bail = (
                    BailSpecificites.objects.filter(bien_id=bien_id)
                    .order_by("-date_debut")
                    .first()
                )
                if not bail:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": f"Aucun bail trouvé pour le bien {bien_id}",
                        },
                        status=404,
                    )
                bail_id = bail.id
            except Exception as e:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Erreur lors de la récupération du bail: {str(e)}",
                    },
                    status=400,
                )

        # Créer l'état des lieux à partir des données du formulaire

        # Supprimer les anciens états des lieux du même type pour ce bail
        # On ne peut avoir qu'un seul état des lieux d'entrée et un seul de sortie
        etat_lieux_type = form_data.get("type", "entree")
        anciens_etats_lieux = EtatLieux.objects.filter(
            bail_id=bail_id, type_etat_lieux=etat_lieux_type
        )

        if anciens_etats_lieux.exists():
            count = anciens_etats_lieux.count()
            logger.info(
                f"Suppression de {count} ancien(s) état(s) des lieux "
                f"de type '{etat_lieux_type}' pour le bail {bail_id}"
            )
            # Supprimer les fichiers PDF associés
            for ancien_etat_lieux in anciens_etats_lieux:
                if ancien_etat_lieux.pdf:
                    try:
                        ancien_etat_lieux.pdf.delete(save=False)
                    except Exception as e:
                        logger.warning(
                            f"Impossible de supprimer le PDF de l'état des lieux "
                            f"{ancien_etat_lieux.id}: {e}"
                        )
            # Supprimer les objets (les photos seront supprimées en cascade)
            anciens_etats_lieux.delete()

        etat_lieux: EtatLieux = create_etat_lieux_from_form_data(
            form_data, bail_id, request.user
        )

        # Sauvegarder les photos si présentes
        if uploaded_photos:
            # Supprimer toutes les photos existantes pour cet état des lieux
            # (au cas où il y en aurait déjà)

            photos_existantes = EtatLieuxPhoto.objects.filter(
                piece__bien=etat_lieux.bail.bien
            )
            if photos_existantes.exists():
                count = photos_existantes.count()
                bien_id = etat_lieux.bail.bien.id
                logger.info(
                    f"Suppression de {count} photo(s) existante(s) "
                    f"pour le bien {bien_id}"
                )
                # Supprimer les fichiers image du disque
                for photo in photos_existantes:
                    if photo.image:
                        try:
                            photo.image.delete(save=False)
                        except Exception as e:
                            logger.warning(
                                f"Impossible de supprimer l'image "
                                f"{photo.image.path}: {e}"
                            )
                # Supprimer les objets de la base
                photos_existantes.delete()

            save_etat_lieux_photos(
                etat_lieux, uploaded_photos, form_data.get("photo_references", [])
            )

        # Préparer les données complètes pour le template

        # Récupérer toutes les photos liées aux pièces du bien
        photos = EtatLieuxPhoto.objects.filter(
            piece__bien=etat_lieux.bail.bien
        ).select_related("piece")

        logger.info(f"Nombre de photos trouvées: {photos.count()}")

        # Créer la structure complète des pièces avec éléments enrichis
        pieces_enrichies = []

        for piece_detail in etat_lieux.pieces_details.all():
            piece = piece_detail.piece

            # Récupérer les photos de cette pièce
            piece_photos = photos.filter(piece=piece)
            logger.info(
                f"Pièce {piece.nom} ({piece.id}): {piece_photos.count()} photos"
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
                "bail": etat_lieux.bail,
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
            prepare_etat_lieux_pdf_with_signature_fields(tmp_pdf_path, etat_lieux)

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
