"""
Vues pour la gestion des avenants au bail.
"""

import json
import logging

from django.core.files.base import ContentFile
from django.http import HttpResponse, QueryDict
from django.template.loader import render_to_string
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from weasyprint import HTML

from location.serializers import FranceAvenantSerializer
from location.services.form_handlers.form_orchestrator import FormOrchestrator
from location.types.form_state import ExtendFormState
from signature.certification_flow import certify_document_hestia
from signature.document_status import DocumentStatus
from signature.document_types import SignableDocumentType

from .models import Avenant, AvenantMotif, AvenantSignatureRequest
from .utils import (
    create_avenant_signature_requests,
    get_avenant_with_access_check,
    get_bail_for_avenant,
)

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_avenant_requirements(request, bail_id):
    """
    Récupère les requirements pour créer un avenant à un bail.

    GET /api/avenant/{bail_id}/requirements/

    Retourne les informations du bail et les steps du formulaire avenant.
    """
    # 1. Valider accès et règles métier (bail doit être locked)
    # Lève NotFound/PermissionDenied/ValidationError si erreur
    bail = get_bail_for_avenant(bail_id, request.user.email)

    # 2. Utiliser l'orchestrateur avec la location du bail
    # Note: pas de lock_fields pour avenant car on veut pouvoir modifier
    # certains champs du bien (identifiant_fiscal, diagnostics, etc.)
    orchestrator = FormOrchestrator()
    form_state = ExtendFormState(
        source_type="location",
        source_id=bail.location.id,
        lock_fields=[],  # Avenant: pas de lock, on modifie des champs existants
    )

    result = orchestrator.get_form_requirements(
        form_type="avenant",
        form_state=form_state,
        country="FR",
        user=request.user,
    )

    if "error" in result:
        return Response(result, status=status.HTTP_400_BAD_REQUEST)

    # Ajouter bail_id dans formData pour le frontend
    if "formData" in result:
        result["formData"]["bail_id"] = str(bail_id)
    else:
        result["formData"] = {"bail_id": str(bail_id)}

    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_avenant(request, bail_id):
    """
    Crée ou met à jour un avenant pour un bail.

    POST /api/avenant/{bail_id}/create/

    Body:
        - motifs: Liste des motifs (identifiant_fiscal, diagnostics_ddt, permis_de_louer)
        - identifiant_fiscal: Numéro fiscal (si motif sélectionné)
        - avenant_id: (optionnel) ID d'un avenant DRAFT existant à mettre à jour
    """

    # 1. Valider accès et règles métier
    # Lève NotFound/PermissionDenied/ValidationError si erreur
    bail = get_bail_for_avenant(bail_id, request.user.email, prefetch=False)

    # 2. Préparer les données (FormData envoie motifs en JSON string)
    # QueryDict nécessite .dict() pour une conversion propre
    if isinstance(request.data, QueryDict):
        data = request.data.dict()
    else:
        data = dict(request.data)
    data["bail_id"] = str(bail_id)

    # Parser motifs si c'est un JSON string (envoyé depuis FormData)
    if isinstance(data.get("motifs"), str):
        try:
            data["motifs"] = json.loads(data["motifs"])
        except json.JSONDecodeError:
            pass

    # 3. Valider avec le serializer
    serializer = FranceAvenantSerializer(data=data)
    if not serializer.is_valid():
        return Response(
            {"error": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    validated = serializer.validated_data
    motifs = validated["motifs"]

    # 4. Créer ou mettre à jour l'avenant
    avenant_id = data.get("avenant_id")
    is_update = False

    if avenant_id:
        # Mode édition: mettre à jour l'avenant existant

        try:
            avenant = Avenant.objects.get(id=avenant_id, bail=bail)
            if avenant.status != DocumentStatus.DRAFT:
                return Response(
                    {"error": "Seuls les avenants en brouillon peuvent être modifiés"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Mettre à jour les champs
            avenant.motifs = motifs
            avenant.identifiant_fiscal = (
                validated.get("identifiant_fiscal")
                if "identifiant_fiscal" in motifs
                else None
            )
            # Réinitialiser pour nouvelle édition (supprime PDF + signature_requests)
            avenant.reset_for_edit()
            avenant.save()
            is_update = True
        except Avenant.DoesNotExist:
            return Response(
                {"error": "Avenant non trouvé"},
                status=status.HTTP_404_NOT_FOUND,
            )
    else:
        # Mode création: nouvel avenant
        avenant = Avenant.objects.create(
            bail=bail,
            motifs=motifs,
            identifiant_fiscal=validated.get("identifiant_fiscal")
            if "identifiant_fiscal" in motifs
            else None,
        )

    # 5. Créer les demandes de signature
    create_avenant_signature_requests(avenant, user=request.user)

    # 6. Récupérer le token du premier signataire
    first_sign_req = avenant.signature_requests.order_by("order").first()

    return Response(
        {
            "id": str(avenant.id),
            "numero": avenant.numero,
            "linkTokenFirstSigner": (
                str(first_sign_req.link_token) if first_sign_req else None
            ),
            "message": (
                "Avenant mis à jour avec succès"
                if is_update
                else "Avenant créé avec succès"
            ),
        },
        status=status.HTTP_200_OK if is_update else status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def generate_avenant_pdf(request, avenant_id):
    """
    Génère le PDF de l'avenant.

    GET /api/avenant/{avenant_id}/pdf/
    """
    import os
    import uuid

    from signature.pdf_processing import prepare_pdf_with_signature_fields_generic

    # 1. Valider accès
    avenant, error = get_avenant_with_access_check(avenant_id, request.user.email)
    if error:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if error == "Avenant non trouvé"
            else status.HTTP_403_FORBIDDEN
        )
        return Response({"error": error}, status=status_code)

    # 2. Préparer le contexte pour le template (même structure que bail)
    bail = avenant.bail
    location = bail.location
    bien = location.bien

    # Flags pour les articles conditionnels
    has_diagnostics_ddt = AvenantMotif.DIAGNOSTICS_DDT in avenant.motifs
    has_identifiant_fiscal = AvenantMotif.IDENTIFIANT_FISCAL in avenant.motifs
    has_permis_de_louer = AvenantMotif.PERMIS_DE_LOUER in avenant.motifs

    # Calculer le numéro de l'article final (Article 1 = parties, puis +1 par motif)
    final_article_number = 2 + sum(
        [has_diagnostics_ddt, has_identifiant_fiscal, has_permis_de_louer]
    )

    context = {
        "avenant": avenant,
        "bail": bail,
        "location": location,
        "bien": bien,
        # Mêmes variables que bail pour les parties et signatures
        "bailleurs": list(bien.bailleurs.all()),
        "locataires": list(location.locataires.all()),
        "mandataire": location.mandataire,
        "mandataire_doit_signer": bail.mandataire_doit_signer,
        # Flags pour les articles conditionnels
        "has_identifiant_fiscal": has_identifiant_fiscal,
        "has_diagnostics_ddt": has_diagnostics_ddt,
        "has_permis_de_louer": has_permis_de_louer,
        # Numéro de l'article final
        "final_article_number": final_article_number,
    }

    # 3. Générer le PDF HTML
    html_content = render_to_string("pdf/bail/avenant.html", context)
    pdf_bytes = HTML(
        string=html_content, base_url=request.build_absolute_uri()
    ).write_pdf()

    # 4. Ajouter les champs de signature et sauvegarder
    base_filename = f"avenant_{avenant.id}_{uuid.uuid4().hex}"
    pdf_filename = f"{base_filename}.pdf"
    tmp_pdf_path = f"/tmp/{pdf_filename}"

    try:
        # Sauver temporairement
        with open(tmp_pdf_path, "wb") as f:
            f.write(pdf_bytes)

        # Ajouter les champs de signature
        prepare_pdf_with_signature_fields_generic(tmp_pdf_path, avenant)

        # Certifier avec Hestia (optionnel)
        try:
            certified_pdf_path = tmp_pdf_path.replace(".pdf", "_certified.pdf")
            certify_document_hestia(
                source_path=tmp_pdf_path,
                output_path=certified_pdf_path,
                document_type=SignableDocumentType.AVENANT.value,
            )
            tmp_pdf_path = certified_pdf_path
            logger.info(f"✅ Avenant {avenant.id} certifié Hestia avec succès")
        except FileNotFoundError as e:
            logger.warning(f"⚠️ Certificat Hestia AATL manquant (mode dev) : {e}")
        except ValueError as e:
            logger.warning(f"⚠️ PASSWORD_CERT_SERVER manquant : {e}")
        except Exception as e:
            logger.error(f"❌ Erreur certification Hestia : {e}")

        # Recharger le PDF final
        with open(tmp_pdf_path, "rb") as f:
            final_pdf_content = f.read()

        # Sauvegarder dans avenant.pdf
        avenant.pdf.save(
            f"avenant_{avenant.id}_{avenant.numero}.pdf",
            ContentFile(final_pdf_content),
            save=True,
        )

    finally:
        # Nettoyer les fichiers temporaires
        for temp_file in [
            tmp_pdf_path,
            tmp_pdf_path.replace("_certified.pdf", ".pdf"),
        ]:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                logger.warning(f"Impossible de supprimer {temp_file}: {e}")

    response = HttpResponse(final_pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="avenant_{avenant.numero}.pdf"'

    return response


# ============================================================================
# Vues de signature pour l'avenant
# ============================================================================


@api_view(["GET"])
def get_avenant_signature_request(request, token):
    """Vue pour récupérer les informations d'une demande de signature d'avenant."""
    from signature.views import get_signature_request_generic

    return get_signature_request_generic(request, token, AvenantSignatureRequest)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_signature_avenant(request):
    """Vue pour confirmer une signature d'avenant."""
    from signature.views import confirm_signature_generic

    return confirm_signature_generic(
        request, AvenantSignatureRequest, SignableDocumentType.AVENANT.value
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_signature_avenant(request, avenant_id):
    """Vue pour annuler une signature d'avenant en cours."""
    from signature.views import cancel_signature_generic

    return cancel_signature_generic(request, avenant_id, Avenant)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_otp_avenant(request):
    """Renvoie un OTP pour la signature d'avenant."""
    from signature.views import resend_otp_generic

    return resend_otp_generic(
        request, AvenantSignatureRequest, SignableDocumentType.AVENANT.value
    )
