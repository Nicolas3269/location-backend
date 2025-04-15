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

from algo.signature.main import add_signature_fields, sign_pdf
from bail.factories import BailSpecificitesFactory
from bail.models import BailSpecificites

logger = logging.getLogger(__name__)


@csrf_exempt
def generate_bail_pdf(request):
    if request.method == "POST":
        # Créer un bail de test
        bail = BailSpecificitesFactory.create()

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

        # TODO: Vérifier l’OTP ici (logique à implémenter selon ton backend)

        bail = get_object_or_404(BailSpecificites, id=bail_id)
        bail_path = bail.pdf.path
        base_url = bail.pdf.url.split(".")[0]
        base_filename = bail_path.split(".")[0]
        landlord_path = f"{base_filename}_landlord.pdf"
        final_path = f"{base_filename}_signed.pdf"
        final_url = f"{base_url}_signed.pdf"

        # Ajouter la signature manuscrite dans le PDF original
        signature_bytes = base64.b64decode(signature_data_url.split(",")[1])

        # Ajouter les champs de signature
        add_signature_fields(bail_path)

        # Signer par le propriétaire
        # Phase 1 - BAILLEUR
        landlord = bail.bien.proprietaire
        sign_pdf(bail_path, landlord_path, landlord, "Landlord", signature_bytes)

        # Signer par le locataire
        tenant = bail.locataire
        final_path = sign_pdf(
            landlord_path, final_path, tenant, "Tenant", signature_bytes
        )

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
