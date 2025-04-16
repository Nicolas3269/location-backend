import base64
import json
import logging
import os
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from weasyprint import HTML

from algo.signature.main import (
    add_signature_fields_dynamic,
    compose_signature_stamp,
    get_named_dest_coordinates,
    sign_pdf,
)
from bail.factories import BailSpecificitesFactory, LocataireFactory
from bail.models import BailSpecificites

logger = logging.getLogger(__name__)


@csrf_exempt
def generate_bail_pdf(request):
    if request.method == "POST":
        # Créer un bail de test
        # Create multiple tenants first
        locataire1 = LocataireFactory.create()
        # locataire2 = LocataireFactory.create()

        # locataires = [locataire1, locataire2]
        locataires = [locataire1]

        # Create a bail and assign both tenants
        bail = BailSpecificitesFactory.create(locataires=locataires)

        # Générer le PDF depuis le template HTML
        html = render_to_string("pdf/bail.html", {"bail": bail})
        pdf = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()

        # Noms de fichiers
        base_filename = f"bail_{bail.id}_{uuid.uuid4().hex}"
        pdf_filename = f"{base_filename}.pdf"
        bail.pdf.save(pdf_filename, ContentFile(pdf), save=True)

        return JsonResponse(
            {"success": True, "bailId": bail.id, "pdfUrl": bail.pdf.url}
        )


@csrf_exempt
def sign_bail(request):
    try:
        data = json.loads(request.body)

        signature_data_url = data.get("signatureImage")
        otp = data.get("otp")
        bail_id = data.get("bailId")

        if not signature_data_url or not otp or not bail_id:
            return JsonResponse(
                {"success": False, "error": "Données manquantes"}, status=400
            )

        bail = get_object_or_404(BailSpecificites, id=bail_id)
        bail_path = bail.pdf.path
        base_url = bail.pdf.url.rsplit(".", 1)[0]
        base_filename = bail_path.rsplit(".", 1)[0]
        final_path = f"{base_filename}_signed.pdf"
        final_url = f"{base_url}_signed.pdf"

        signature_bytes = base64.b64decode(signature_data_url.split(",")[1])

        landlords = list(bail.bien.proprietaires.all())
        tenants = list(bail.locataires.all())
        signatories = landlords + tenants

        all_fields = []

        for person in signatories:
            img_pil, buffer = compose_signature_stamp(signature_bytes, person)
            width, img_height_px = img_pil.size

            page, rect, field_name = get_named_dest_coordinates(
                bail_path, person, img_height_px
            )
            if rect is None:
                raise ValueError(f"Aucun champ de signature trouvé pour {person.email}")

            all_fields.append(
                {
                    "field_name": field_name,
                    "rect": rect,
                    "person": person,
                    "page": page,
                }
            )

        # Ajouter les champs de signature
        add_signature_fields_dynamic(bail_path, all_fields)

        # Appliquer les signatures une par une (chaînées)
        source = bail_path
        for i, field in enumerate(all_fields):
            dest = (
                final_path
                if i == len(all_fields) - 1
                else f"{base_filename}_temp_{i}.pdf"
            )
            sign_pdf(
                source,
                dest,
                field["person"],
                field["field_name"],
                signature_bytes,
            )
            source = dest  # pour le suivant

        return JsonResponse(
            {
                "success": True,
                "bail_id": bail.id,
                "pdfUrl": final_url,
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la signature du PDF")
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
            },
            status=500,
        )


# Endpoint pour voir/télécharger un PDF
def view_signed_pdf(request, bail_id):
    # Trouver le dernier PDF signé pour ce bail
    bail_dir = os.path.join(settings.MEDIA_ROOT, "bails")
    matching_files = [
        f
        for f in os.listdir(bail_dir)
        if f.startswith(f"bail_{bail_id}_") and f.endswith("_signed.pdf")
    ]

    if matching_files:
        # Prendre le plus récent
        latest_pdf = sorted(matching_files)[-1]
        pdf_path = os.path.join(bail_dir, latest_pdf)

        return FileResponse(open(pdf_path, "rb"), content_type="application/pdf")
    else:
        return JsonResponse({"error": "PDF signé non trouvé"}, status=404)
