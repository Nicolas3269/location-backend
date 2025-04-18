import json
import logging
import uuid

from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from weasyprint import HTML

from bail.factories import BailSpecificitesFactory, LocataireFactory
from bail.models import BailSignatureRequest
from bail.utils import (
    create_signature_requests,
    prepare_pdf_with_signature_fields,
    process_signature,
    send_signature_email,
)

logger = logging.getLogger(__name__)


@csrf_exempt
def generate_bail_pdf(request):
    if request.method == "POST":
        # Créer un bail de test
        # Create multiple tenants first
        nbr_locataires = 1
        locataires = [LocataireFactory.create() for _ in range(nbr_locataires)]

        # Create a bail and assign both tenants
        bail = BailSpecificitesFactory.create(locataires=locataires)

        # Générer le PDF depuis le template HTML
        html = render_to_string("pdf/bail.html", {"bail": bail})
        pdf = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()

        # Noms de fichiers
        base_filename = f"bail_{bail.id}_{uuid.uuid4().hex}"
        pdf_filename = f"{base_filename}.pdf"
        bail.pdf.save(pdf_filename, ContentFile(pdf), save=True)

        prepare_pdf_with_signature_fields(bail)
        create_signature_requests(bail)

        return JsonResponse(
            {"success": True, "bailId": bail.id, "pdfUrl": bail.pdf.url}
        )


@csrf_exempt
def get_signature_request(request, token):
    req = get_object_or_404(BailSignatureRequest, link_token=token)

    if req.signed:
        return JsonResponse(
            {"error": "Cette signature a déjà été complétée."}, status=400
        )

    current = (
        BailSignatureRequest.objects.filter(bail=req.bail, signed=False)
        .order_by("order")
        .first()
    )

    if req != current:
        return JsonResponse(
            {"error": "Ce n'est pas encore votre tour de signer."}, status=403
        )

    person = req.proprietaire or req.locataire
    return JsonResponse(
        {
            "person": {"email": person.email, "first_name": person.prenom},
            "bail_id": req.bail.id,
        }
    )


@csrf_exempt
def confirm_signature_bail(request):
    try:
        data = json.loads(request.body)
        token = data.get("token")
        otp = data.get("otp")
        signature_data_url = data.get("signatureImage")

        sig_req = get_object_or_404(BailSignatureRequest, link_token=token)

        if sig_req.signed:
            return JsonResponse({"error": "Déjà signé"}, status=400)

        if sig_req.otp != otp:
            return JsonResponse({"error": "Code OTP invalide"}, status=403)

        # Vérifie que c’est bien son tour
        current = (
            BailSignatureRequest.objects.filter(bail=sig_req.bail, signed=False)
            .order_by("order")
            .first()
        )

        if sig_req != current:
            return JsonResponse({"error": "Ce n’est pas encore votre tour"}, status=403)

        if not signature_data_url or not otp:
            return JsonResponse(
                {"success": False, "error": "Données manquantes"}, status=400
            )

        process_signature(sig_req, signature_data_url)

        # Marquer comme signé
        sig_req.signed = True
        sig_req.signed_at = timezone.now()
        sig_req.save()

        # Envoi au suivant
        next_req = (
            BailSignatureRequest.objects.filter(bail=sig_req.bail, signed=False)
            .order_by("order")
            .first()
        )

        if next_req:
            send_signature_email(next_req)

        bail_url = f"{sig_req.bail.pdf.url.rsplit('.', 1)[0]}_signed.pdf"
        return JsonResponse({"success": True, "pdfUrl": bail_url})

    except Exception as e:
        logger.exception("Erreur lors de la signature du PDF")
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
            },
            status=500,
        )
