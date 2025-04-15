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
from slugify import slugify
from weasyprint import HTML

from algo.signature.main import (
    add_signature_fields_dynamic,
    compose_signature_stamp,
    generate_dynamic_boxes,
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
        locataire2 = LocataireFactory.create()

        # Create a bail and assign both tenants
        bail = BailSpecificitesFactory.create(locataires=[locataire1, locataire2])

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


def full_name(user):
    """
    Retourne le nom complet d'un utilisateur.
    """
    return f"{user.first_name} {user.last_name}"


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

        # TODO: Vérifier l'OTP ici (logique à implémenter selon ton backend)

        bail = get_object_or_404(BailSpecificites, id=bail_id)
        bail_path = bail.pdf.path
        base_url = bail.pdf.url.split(".")[0]
        base_filename = bail_path.split(".")[0]
        final_path = f"{base_filename}_signed.pdf"
        final_url = f"{base_url}_signed.pdf"

        # Decode signature image
        signature_bytes = base64.b64decode(signature_data_url.split(",")[1])

        # Get all parties from the bail
        landlords = list(bail.bien.proprietaires.all())
        tenants = list(bail.locataires.all())

        # Create signature stamps for all parties
        landlord_images = []
        landlord_buffers = []
        for landlord in landlords:
            img, buffer = compose_signature_stamp(signature_bytes, landlord)
            landlord_images.append(img)
            landlord_buffers.append(buffer)

        tenant_images = []
        tenant_buffers = []
        for tenant in tenants:
            img, buffer = compose_signature_stamp(signature_bytes, tenant)
            tenant_images.append(img)
            tenant_buffers.append(buffer)

        # Generate signature boxes for all parties
        landlord_boxes, tenant_boxes = generate_dynamic_boxes(
            landlord_images, tenant_images
        )

        # Create signature fields for all parties
        landlord_fields = []
        for idx, landlord in enumerate(landlords):
            landlord_fields.append(
                {
                    "field_name": slugify(f"bailleur {landlord.get_full_name()}_{idx}"),
                    "box": landlord_boxes[idx]
                    if isinstance(landlord_boxes, list)
                    else landlord_boxes,
                }
            )

        tenant_fields = []
        for idx, tenant in enumerate(tenants):
            tenant_fields.append(
                {
                    "field_name": slugify(f"locataire {tenant.get_full_name()}_{idx}"),
                    "box": tenant_boxes[idx]
                    if isinstance(tenant_boxes, list)
                    else tenant_boxes,
                }
            )

        # Add all signature fields to the document
        all_fields = landlord_fields + tenant_fields
        add_signature_fields_dynamic(bail_path, all_fields)

        # Chain signatures through temporary files
        current_path = bail_path
        all_signatories = list(zip(landlords, landlord_fields)) + list(
            zip(tenants, tenant_fields)
        )

        for idx, (signatory, field) in enumerate(all_signatories):
            # Last signature goes to the final path
            if idx == len(all_signatories) - 1:
                output_path = final_path
            else:
                output_path = f"{base_filename}_temp_{idx}.pdf"

            sign_pdf(
                current_path,
                output_path,
                signatory,
                field["field_name"],
                signature_bytes,
            )

            # Update current_path for next iteration
            current_path = output_path

        # Clean up temporary files
        for idx in range(len(all_signatories) - 1):
            temp_file = f"{base_filename}_temp_{idx}.pdf"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    logger.warning(f"Failed to remove temporary file {temp_file}")

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
