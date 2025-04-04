import logging
import os
import uuid

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from weasyprint import HTML

from algo.signature.main import add_signature_fields, sign_pdf, verify_pdf_signature
from bail.factories import BailSpecificitesFactory

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
        landlord_filename = f"{base_filename}_landlord.pdf"
        tenant_filename = f"{base_filename}_tenant.pdf"
        final_filename = f"{base_filename}_signed.pdf"

        # Créer les chemins complets
        bail_dir = os.path.join(settings.MEDIA_ROOT, "bails")
        os.makedirs(bail_dir, exist_ok=True)

        pdf_path = os.path.join(bail_dir, pdf_filename)
        landlord_path = os.path.join(bail_dir, landlord_filename)
        tenant_path = os.path.join(bail_dir, tenant_filename)
        final_path = os.path.join(bail_dir, final_filename)

        # Sauvegarder le PDF original
        with open(pdf_path, "wb") as f:
            f.write(pdf)

        try:
            # 1. Ajouter des champs de signature
            add_signature_fields(pdf_path)

            # 2. Signer par le propriétaire
            landlord = bail.bien.proprietaire
            sign_pdf(pdf_path, landlord_path, landlord, "Landlord")

            # 3. Signer par le locataire (en utilisant le PDF signé par le propriétaire comme base)
            tenant = bail.locataire
            final_path = sign_pdf(landlord_path, final_path, tenant, "Tenant")

            # 4. Vérifier les signatures
            verification = verify_pdf_signature(final_path)
            logger.info(f"Vérification des signatures: {verification}")

            # Renvoyer l'URL du PDF signé
            file_url = f"{settings.MEDIA_URL}bails/{final_filename}"

            return JsonResponse(
                {
                    "success": True,
                    "bail_id": bail.id,
                    "pdfUrl": file_url,
                    "verification": verification,
                }
            )

        except Exception as e:
            logger.exception(f"Erreur lors de la signature du PDF: {e}")
            # En cas d'erreur, renvoyer quand même le PDF non signé
            file_url = f"{settings.MEDIA_URL}bails/{pdf_filename}"
            return JsonResponse(
                {
                    "success": False,
                    "bail_id": bail.id,
                    "pdfUrl": file_url,
                    "error": str(e),
                }
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
