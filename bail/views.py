import json
import logging
import os
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from weasyprint import HTML

from bail.factories import BailSpecificitesFactory, LocataireFactory
from bail.models import (
    BailSignatureRequest,
)
from bail.utils import (
    create_signature_requests,
    prepare_pdf_with_signature_fields,
    process_signature,
    send_signature_email,
)

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_bail_pdf(request):
    try:
        form_data = json.loads(request.body)
        bail_id = form_data.get("bail_id")

        if not bail_id:
            return JsonResponse(
                {"success": False, "error": "bail_id est requis"}, status=400
            )

        # Récupérer le bail existant
        from bail.models import BailSpecificites

        bail = get_object_or_404(BailSpecificites, id=bail_id)

        # Générer le PDF depuis le template HTML
        html = render_to_string("pdf/bail_wrapper.html", {"bail": bail})
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()

        # Noms de fichiers
        base_filename = f"bail_{bail.id}_{uuid.uuid4().hex}"
        pdf_filename = f"{base_filename}.pdf"
        tmp_pdf_path = f"/tmp/{pdf_filename}"
        try:
            # 1. Sauver temporairement
            with open(tmp_pdf_path, "wb") as f:
                f.write(pdf_bytes)

            # 2. Ajouter champs
            prepare_pdf_with_signature_fields(tmp_pdf_path, bail)
            # 3. Recharger dans bail.pdf
            with open(tmp_pdf_path, "rb") as f:
                bail.pdf.save(pdf_filename, ContentFile(f.read()), save=True)

        finally:
            # 4. Supprimer le fichier temporaire
            try:
                os.remove(tmp_pdf_path)
            except Exception as e:
                logger.warning(
                    f"Impossible de supprimer le fichier temporaire {tmp_pdf_path}: {e}"
                )

        create_signature_requests(bail)

        first_sign_req = bail.signature_requests.order_by("order").first()

        return JsonResponse(
            {
                "success": True,
                "bailId": bail.id,
                "pdfUrl": bail.pdf.url,
                "linkTokenFirstSigner": str(first_sign_req.link_token),
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la génération du bail PDF")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la génération: {str(e)}"},
            status=500,
        )


@csrf_exempt
@ratelimit(key="ip", rate="5/m", block=True) if not settings.DEBUG else lambda x: x
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
            "person": {
                "email": person.email,
                "first_name": person.prenom,
                "last_name": person.nom,
            },
            "bail_id": req.bail.id,
        }
    )


@csrf_exempt  # au lieu de @csrf_exempt
@ratelimit(key="ip", rate="5/m", block=True) if not settings.DEBUG else lambda x: x
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_grille_vetuste_pdf(request):
    """Génère et retourne une grille de vétusté"""
    try:
        form_data = json.loads(request.body)
        bail_id = form_data.get("bail_id")

        # Si un bail_id est fourni, récupérer le bail existant
        if bail_id:
            from bail.models import BailSpecificites

            bail = get_object_or_404(BailSpecificites, id=bail_id)
        else:
            # Créer un bail de test pour la démonstration
            nbr_locataires = 2
            locataires = [LocataireFactory.create() for _ in range(nbr_locataires)]
            bail = BailSpecificitesFactory.create(locataires=locataires)

        # Données pour la grille de vétusté
        grille_data = {
            "bail": bail,
            "elements": [
                {
                    "piece": "Salon",
                    "element": "Murs",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Salon",
                    "element": "Sol",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Salon",
                    "element": "Plafond",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Cuisine",
                    "element": "Murs",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Cuisine",
                    "element": "Sol",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Cuisine",
                    "element": "Électroménager",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Chambre",
                    "element": "Murs",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Chambre",
                    "element": "Sol",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Salle de bain",
                    "element": "Murs",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Salle de bain",
                    "element": "Sol",
                    "etat_initial": "Bon",
                    "observations": "",
                },
                {
                    "piece": "Salle de bain",
                    "element": "Sanitaires",
                    "etat_initial": "Bon",
                    "observations": "",
                },
            ],
        }

        # Générer le PDF depuis un template HTML
        html = render_to_string("pdf/grille_vetuste.html", grille_data)
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()

        # Sauvegarder le fichier
        filename = f"grille_vetuste_{bail.id}_{uuid.uuid4().hex}.pdf"

        # Sauvegarder directement dans le modèle BailSpecificites si bail_id fourni
        if bail_id:
            bail.grille_vetuste_pdf.save(filename, ContentFile(pdf_bytes), save=True)
            file_url = bail.grille_vetuste_pdf.url
        else:
            # Fallback pour les cas de test sans bail_id
            file_path = f"bail_pdfs/{filename}"
            saved_path = default_storage.save(file_path, ContentFile(pdf_bytes))
            file_url = default_storage.url(saved_path)

        return JsonResponse(
            {"success": True, "grillVetustUrl": file_url, "filename": filename}
        )

    except Exception as e:
        logger.exception("Erreur lors de la génération de la grille de vétusté")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la génération: {str(e)}"},
            status=500,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_notice_information_pdf(request):
    """Génère et retourne une notice d'information"""
    try:
        form_data = json.loads(request.body)
        bail_id = form_data.get("bail_id")

        # Si un bail_id est fourni, récupérer le bail existant
        if bail_id:
            from bail.models import BailSpecificites

            bail = get_object_or_404(BailSpecificites, id=bail_id)
        else:
            # Créer un bail de test pour la démonstration
            nbr_locataires = 2
            locataires = [LocataireFactory.create() for _ in range(nbr_locataires)]
            bail = BailSpecificitesFactory.create(locataires=locataires)

        # Données pour la notice d'information
        notice_data = {
            "bail": bail,
            "droits_locataire": [
                "Droit à un logement décent",
                "Droit au respect de la vie privée",
                "Droit à la jouissance paisible des lieux",
                "Droit à l'information sur les charges",
                "Droit de préavis en cas de congé",
            ],
            "obligations_locataire": [
                "Payer le loyer et les charges aux échéances convenues",
                "User paisiblement des locaux loués",
                (
                    "Répondre des dégradations et pertes survenues pendant "
                    "la durée du contrat"
                ),
                ("Laisser exécuter les travaux d'amélioration des parties communes"),
                "Assurer le logement contre les risques locatifs",
            ],
            "droits_bailleur": [
                "Percevoir le loyer aux échéances convenues",
                "Vérifier le bon usage du logement",
                "Récupérer le logement en fin de bail",
                "Être indemnisé en cas de dégradations",
            ],
            "obligations_bailleur": [
                "Délivrer un logement décent",
                "Assurer la jouissance paisible du logement",
                "Entretenir les locaux en état de servir",
                "Effectuer les réparations autres que locatives",
            ],
        }

        # Générer le PDF depuis un template HTML
        html = render_to_string("pdf/notice_information.html", notice_data)
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()

        # Sauvegarder le fichier
        filename = f"notice_information_{bail.id}_{uuid.uuid4().hex}.pdf"

        # Sauvegarder directement dans le modèle BailSpecificites si bail_id fourni
        if bail_id:
            bail.notice_information_pdf.save(
                filename, ContentFile(pdf_bytes), save=True
            )
            file_url = bail.notice_information_pdf.url
        else:
            # Fallback pour les cas de test sans bail_id
            file_path = f"bail_pdfs/{filename}"
            saved_path = default_storage.save(file_path, ContentFile(pdf_bytes))
            file_url = default_storage.url(saved_path)

        return JsonResponse(
            {"success": True, "noticeUrl": file_url, "filename": filename}
        )

    except Exception as e:
        logger.exception("Erreur lors de la génération de la notice d'information")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la génération: {str(e)}"},
            status=500,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_dpe_diagnostic(request):
    """Upload du diagnostic de performance énergétique"""
    try:
        if "dpe_file" not in request.FILES:
            return JsonResponse(
                {"success": False, "error": "Aucun fichier DPE fourni"}, status=400
            )

        dpe_file = request.FILES["dpe_file"]
        bail_id = request.POST.get("bail_id")

        # Vérifier le type de fichier
        if not dpe_file.name.lower().endswith(".pdf"):
            return JsonResponse(
                {"success": False, "error": "Le fichier doit être au format PDF"},
                status=400,
            )

        # Vérifier la taille du fichier (max 10MB)
        if dpe_file.size > 10 * 1024 * 1024:
            return JsonResponse(
                {"success": False, "error": "Le fichier ne peut pas dépasser 10MB"},
                status=400,
            )

        # Générer un nom de fichier unique
        filename = f"dpe_{bail_id or uuid.uuid4().hex}_{uuid.uuid4().hex}.pdf"

        # Sauvegarder directement dans le modèle BailSpecificites si bail_id fourni
        if bail_id:
            try:
                from bail.models import BailSpecificites

                bail = BailSpecificites.objects.get(id=bail_id)
                bail.dpe_pdf.save(filename, dpe_file, save=True)
                file_url = bail.dpe_pdf.url
            except BailSpecificites.DoesNotExist:
                logger.warning(f"Bail avec l'ID {bail_id} introuvable")
                # Fallback si le bail n'existe pas
                file_path = f"bail_pdfs/{filename}"
                saved_path = default_storage.save(file_path, dpe_file)
                file_url = default_storage.url(saved_path)
        else:
            # Fallback pour les cas sans bail_id
            file_path = f"bail_pdfs/{filename}"
            saved_path = default_storage.save(file_path, dpe_file)
            file_url = default_storage.url(saved_path)

        return JsonResponse(
            {
                "success": True,
                "dpeUrl": file_url,
                "filename": filename,
                "message": "DPE uploadé avec succès",
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de l'upload du DPE")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de l'upload: {str(e)}"},
            status=500,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_draft(request):
    """Sauvegarde un brouillon de bail à partir des données du formulaire"""
    try:
        form_data = json.loads(request.body)

        # traiter les infos du formulaires
        # Créer un bail de test
        # Create multiple tenants first
        nbr_locataires = 2
        locataires = [LocataireFactory.create() for _ in range(nbr_locataires)]

        # Create a bail and assign both tenants
        bail = BailSpecificitesFactory.create(locataires=locataires)

        return JsonResponse(
            {
                "success": True,
                "bailId": bail.id,
                "message": "Brouillon sauvegardé avec succès",
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la sauvegarde du brouillon")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la sauvegarde: {str(e)}"},
            status=500,
        )
