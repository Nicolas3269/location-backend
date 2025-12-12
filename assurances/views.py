"""
API Views pour Assurances (MRH, PNO, GLI).

Endpoints:
- GET /api/assurances/quotation/ : Obtenir un devis
- POST /api/assurances/select-formula/ : Sélectionner formule et générer CP
- GET /api/assurances/signing/<token>/ : Infos signature (générique)
- POST /api/assurances/signing/confirm/ : Confirmer signature (générique)
- POST /api/assurances/signing/resend-otp/ : Renvoyer OTP (générique)
- POST /api/assurances/subscribe/ : Souscrire et obtenir l'URL Checkout
- GET /api/assurances/checkout-status/ : Vérifier le statut du paiement
- GET /api/assurances/policies/ : Lister les polices d'un utilisateur
- GET /api/assurances/policies/<id>/ : Détail d'une police
- GET /api/assurances/documents/cgv/ : Télécharger les CGV
"""

import logging
import os
import uuid
from datetime import date

from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from location.models import Location
from location.services.access_utils import get_user_info_for_location
from signature.pdf_processing import prepare_pdf_with_signature_fields_generic
from signature.views import (
    confirm_signature_generic,
    get_signature_request_generic,
    resend_otp_generic,
)

from .models import (
    InsurancePolicy,
    InsuranceProduct,
    InsuranceQuotation,
    InsuranceQuotationSignatureRequest,
)
from .serializers import (
    InsuranceCheckoutStatusSerializer,
    InsurancePolicySerializer,
    InsuranceQuotationRequestSerializer,
    InsuranceQuotationSerializer,
    InsuranceSubscribeRequestSerializer,
    InsuranceSubscribeResponseSerializer,
    SelectFormulaRequestSerializer,
)
from .services.documents import InsuranceDocumentService
from .services.quotation import InsuranceQuotationService
from .services.stripe_service import InsuranceStripeService
from .services.subscription import InsuranceSubscriptionService
from .utils import create_insurance_signature_request

logger = logging.getLogger(__name__)


# =============================================================================
# Devis
# =============================================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_quotation(request: Request) -> Response:
    """
    Obtient un devis d'assurance pour une location.

    Query params:
        location_id: UUID de la location
        product: Type de produit (MRH, PNO, GLI, défaut: MRH)
        deductible: Franchise (170 ou 290, défaut: 170)
        effective_date: Date d'effet (YYYY-MM-DD, défaut: aujourd'hui)

    Returns:
        InsuranceQuotation avec les formules disponibles
    """
    serializer = InsuranceQuotationRequestSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)

    location_id = serializer.validated_data["location_id"]
    product = serializer.validated_data.get("product", InsuranceProduct.MRH)
    deductible = serializer.validated_data.get("deductible", 170)
    effective_date = serializer.validated_data.get("effective_date")
    force_refresh = serializer.validated_data.get("force_refresh", False)

    # Récupérer la location
    location = get_object_or_404(Location, id=location_id)

    # Vérifier que l'utilisateur est locataire de cette location
    user_info = get_user_info_for_location(location, request.user.email)
    if not user_info.is_locataire:
        return Response(
            {"error": "Seul un locataire peut demander un devis MRH"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Vérifier que la location a un bien
    if not location.bien:
        return Response(
            {"error": "La location doit avoir un bien associé"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Obtenir le devis
    logger.info(f"🔍 get_quotation: location={location_id}, refresh={force_refresh}")
    try:
        quotation_service = InsuranceQuotationService()
        quotation = quotation_service.get_quotation(
            location=location,
            user=request.user,
            product=product,
            deductible=deductible,
            effective_date=effective_date or date.today(),
            force_refresh=force_refresh,
        )
    except ValueError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.exception(f"Error getting {product} quotation: {e}")
        return Response(
            {"error": "Erreur lors de la tarification"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(InsuranceQuotationSerializer(quotation).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def select_formula(request: Request) -> Response:
    """
    Sélectionne une formule et génère le devis PDF + CP.

    Body:
        quotation_id: UUID du devis
        formula_code: Code de la formule choisie

    Returns:
        InsuranceQuotation avec signature_token pour le flow de signature
    """
    serializer = SelectFormulaRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    quotation_id = serializer.validated_data["quotation_id"]
    formula_code = serializer.validated_data["formula_code"]

    # Récupérer le devis
    quotation = get_object_or_404(
        InsuranceQuotation.objects.select_related(
            "location",
            "location__bien",
            "location__bien__adresse",
        ).prefetch_related("location__locataires"),
        id=quotation_id,
    )

    # Vérifier que l'utilisateur est locataire de cette location
    if not quotation.location:
        return Response(
            {"error": "Le devis n'est pas associé à une location"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user_info = get_user_info_for_location(quotation.location, request.user.email)
    if not user_info.is_locataire:
        return Response(
            {"error": "Seul un locataire peut sélectionner une formule MRH"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Vérifier la validité
    if not quotation.is_valid:
        return Response(
            {"error": "Le devis a expiré, veuillez en demander un nouveau"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Vérifier que la formule existe
    formula_data = None
    for formula in quotation.formulas_data:
        if formula.get("code") == formula_code:
            formula_data = formula
            break

    if not formula_data:
        return Response(
            {"error": f"Formule {formula_code} non trouvée dans ce devis"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Mettre à jour la formule sélectionnée
    quotation.selected_formula_code = formula_code

    # Générer le devis PDF et les CP (preview)
    try:
        quotation_data = {
            "id": str(quotation.id),
            "product": quotation.product,
            "deductible": quotation.deductible,
            "effective_date": quotation.effective_date,
            "created_at": quotation.created_at,
            "expires_at": quotation.expires_at,
            "formulas": [formula_data],  # Seulement la formule sélectionnée
        }

        documents_service = InsuranceDocumentService()

        # 1. Générer le devis PDF
        devis_pdf_bytes = documents_service.generate_devis(
            quotation_data=quotation_data,
            subscriber=request.user,
            bien=quotation.location.bien if quotation.location else None,
        )

        # Stocker le devis PDF
        devis_filename = f"devis_{quotation.product}_{quotation.id}_{formula_code}.pdf"
        quotation.devis_document.save(
            devis_filename, ContentFile(devis_pdf_bytes), save=False
        )

        # 2. Générer les Conditions Particulières (aperçu)
        # Le locataire est nécessaire pour le marqueur de signature dans le PDF
        cp_pdf_bytes = documents_service.generate_conditions_particulieres_preview(
            quotation_data=quotation_data,
            formula_data=formula_data,
            subscriber=request.user,
            bien=quotation.location.bien if quotation.location else None,
            location=quotation.location,
            locataire=user_info.locataire,
        )

        # 3. Ajouter les champs de signature au PDF

        tmp_pdf_path = f"/tmp/cp_{uuid.uuid4()}.pdf"
        with open(tmp_pdf_path, "wb") as f:
            f.write(cp_pdf_bytes)

        # Ajouter les champs de signature basés sur les marqueurs dans le PDF
        prepare_pdf_with_signature_fields_generic(tmp_pdf_path, quotation)

        # 4. Optionnel: Certifier avec Hestia
        try:
            from signature.certification_flow import certify_document_hestia

            certified_pdf_path = f"/tmp/cp_{uuid.uuid4()}_certified.pdf"
            certify_document_hestia(tmp_pdf_path, certified_pdf_path, quotation)
            final_pdf_path = certified_pdf_path
            logger.info("✅ CP certifié avec Hestia")
        except Exception as cert_error:
            logger.warning(f"⚠️ Certification Hestia optionnelle échouée: {cert_error}")
            final_pdf_path = tmp_pdf_path

        # Stocker les CP dans le champ pdf (hérité de SignableDocumentMixin)
        cp_filename = f"cp_{quotation.product}_{quotation.id}_{formula_code}.pdf"
        with open(final_pdf_path, "rb") as f:
            quotation.pdf.save(cp_filename, ContentFile(f.read()), save=False)

        # Nettoyer les fichiers temporaires
        try:
            os.remove(tmp_pdf_path)
            if final_pdf_path != tmp_pdf_path:
                os.remove(final_pdf_path)
        except OSError:
            pass

        quotation.save()

        # 5. Créer la signature request pour le flow générique
        sig_request = create_insurance_signature_request(
            quotation, user_email=request.user.email
        )

    except Exception as e:
        logger.exception(f"Error generating documents PDF: {e}")
        return Response(
            {"error": "Erreur lors de la génération des documents"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Retourner le quotation avec le token de signature
    response_data = InsuranceQuotationSerializer(quotation).data
    response_data["signature_token"] = str(sig_request.link_token)
    return Response(response_data)


# =============================================================================
# Signature générique (même pattern que bail/etat_lieux)
# =============================================================================


@api_view(["GET"])
@permission_classes([AllowAny])
def get_signature_request(request: Request, token: str) -> Response:
    """
    Récupère les informations d'une demande de signature d'assurance.

    Utilise le système générique de signature.

    Args:
        token: UUID du link_token de la signature request

    Query params:
        send_otp: Si "true", envoie un code OTP par email
    """

    return get_signature_request_generic(
        request, token, InsuranceQuotationSignatureRequest
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_signature(request: Request) -> Response:
    """
    Confirme la signature d'un devis d'assurance avec OTP.

    Body:
        token: UUID du link_token
        otp: Code OTP à 6 chiffres
        signatureImage: Image de la signature en base64

    Returns:
        {"success": true, "pdfUrl": "...", "location_id": "..."}
    """

    return confirm_signature_generic(
        request, InsuranceQuotationSignatureRequest, "assurance"
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_otp(request: Request) -> Response:
    """
    Renvoie un code OTP pour la signature d'assurance.

    Body:
        token: UUID du link_token

    Returns:
        {"success": true, "message": "..."}
    """

    return resend_otp_generic(request, InsuranceQuotationSignatureRequest, "assurance")


# =============================================================================
# Souscription & Paiement
# =============================================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subscribe(request: Request) -> Response:
    """
    Souscrit à une formule d'assurance et retourne l'URL de paiement Stripe.

    Body:
        quotation_id: UUID du devis
        formula_code: Code de la formule choisie

    Returns:
        {
            policy_id: UUID,
            policy_number: str,
            checkout_url: str,
            session_id: str
        }
    """
    serializer = InsuranceSubscribeRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    quotation_id = serializer.validated_data["quotation_id"]
    formula_code = serializer.validated_data["formula_code"]
    context = serializer.validated_data.get("context", "standalone")
    return_token = serializer.validated_data.get("return_token", "")

    # Récupérer le devis
    quotation = get_object_or_404(
        InsuranceQuotation.objects.select_related("location").prefetch_related(
            "location__locataires"
        ),
        id=quotation_id,
    )

    # Vérifier que l'utilisateur est locataire de cette location
    if not quotation.location:
        return Response(
            {"error": "Le devis n'est pas associé à une location"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user_info = get_user_info_for_location(quotation.location, request.user.email)
    if not user_info.is_locataire:
        return Response(
            {"error": "Seul un locataire peut souscrire à une assurance MRH"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Vérifier la validité
    if not quotation.is_valid:
        return Response(
            {"error": "Le devis a expiré, veuillez en demander un nouveau"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Vérifier que les documents sont signés
    if not quotation.est_signe:
        return Response(
            {"error": "Vous devez d'abord accepter les documents"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Le souscripteur est l'utilisateur connecté
    subscriber = request.user

    # Créer la police
    try:
        subscription_service = InsuranceSubscriptionService()
        policy = subscription_service.create_policy(
            quotation=quotation,
            formula_code=formula_code,
            subscriber=subscriber,
        )
    except ValueError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Créer la session Checkout
    # Passer le nom du locataire pour pré-remplir le formulaire SEPA
    locataire = user_info.locataire
    subscriber_name = locataire.full_name if locataire else None

    try:
        stripe_service = InsuranceStripeService()
        checkout_data = stripe_service.create_checkout_session(
            policy,
            context=context,
            return_token=return_token,
            subscriber_name=subscriber_name,
        )
    except Exception as e:
        logger.exception(f"Error creating Stripe session: {e}")
        return Response(
            {"error": "Erreur lors de la création du paiement"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    response_data = {
        "policy_id": str(policy.id),
        "policy_number": policy.policy_number,
        "checkout_url": checkout_data["checkout_url"],
        "session_id": checkout_data["session_id"],
    }

    return Response(
        InsuranceSubscribeResponseSerializer(response_data).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def checkout_status(request: Request) -> Response:
    """
    Vérifie le statut d'une session Checkout.

    Query params:
        session_id: ID de la session Checkout Stripe

    Returns:
        {
            status: 'complete' | 'expired' | 'open',
            payment_status: 'paid' | 'unpaid',
            policy_number: str | null,
            product: str | null,
            customer_email: str | null,
            policy: InsurancePolicy | null (si status=complete)
        }
    """
    session_id = request.query_params.get("session_id")

    if not session_id:
        return Response(
            {"error": "session_id requis"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        stripe_service = InsuranceStripeService()
        status_data = stripe_service.get_session_status(session_id)
    except Exception as e:
        logger.exception(f"Error getting session status: {e}")
        return Response(
            {"error": "Session non trouvée"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Si le checkout est complete, activer la police si pas déjà fait
    # (approche "pull" en plus des webhooks "push")
    if status_data.get("status") == "complete" and status_data.get("policy_number"):
        try:
            policy = InsurancePolicy.objects.select_related(
                "quotation",
                "quotation__location",
                "quotation__location__bien",
                "quotation__location__bien__adresse",
                "subscriber",
            ).get(policy_number=status_data["policy_number"], subscriber=request.user)

            # Activer la police si elle est encore PENDING
            # (le webhook peut ne pas avoir encore été reçu)
            if policy.status == InsurancePolicy.Status.PENDING:
                logger.info(
                    f"Activating policy {policy.policy_number} via checkout_status API "
                    f"(webhook may not have arrived yet)"
                )
                subscription_service = InsuranceSubscriptionService()
                subscription_service.activate_policy(policy)
                # Recharger la policy après activation
                policy.refresh_from_db()

            # Cas de récupération: police ACTIVE mais sans documents
            # (peut arriver si le webhook a activé mais la génération a échoué)
            elif (
                policy.status == InsurancePolicy.Status.ACTIVE
                and not policy.attestation_document
            ):
                logger.warning(
                    f"🔧 Policy {policy.policy_number} is ACTIVE but no attestation"
                    f" - regenerating documents"
                )
                doc_service = InsuranceDocumentService()
                try:
                    doc_service.generate_all_documents(policy)
                    policy.refresh_from_db()

                    # Attacher l'attestation aux documents locataire
                    if policy.attestation_document:
                        subscription_service = InsuranceSubscriptionService()
                        subscription_service._attach_attestation_to_locataire(policy)

                    logger.info(
                        f"✅ Regenerated documents for {policy.policy_number}"
                    )
                except Exception as e:
                    logger.exception(
                        f"❌ Failed to regenerate documents for "
                        f"{policy.policy_number}: {e}"
                    )

            status_data["policy"] = policy
        except InsurancePolicy.DoesNotExist:
            status_data["policy"] = None
    else:
        status_data["policy"] = None

    return Response(InsuranceCheckoutStatusSerializer(status_data).data)


# =============================================================================
# Polices
# =============================================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_policies(request: Request) -> Response:
    """
    Liste les polices d'assurance de l'utilisateur connecté.

    Query params (optionnel):
        product: Filtrer par type de produit (MRH, PNO, GLI)

    Returns:
        Liste des polices avec leurs détails
    """
    policies = (
        InsurancePolicy.objects.filter(subscriber=request.user)
        .select_related(
            "quotation",
            "quotation__location",
            "quotation__location__bien",
            "quotation__location__bien__adresse",
        )
        .order_by("-created_at")
    )

    # Filtrer par produit si spécifié
    product = request.query_params.get("product")
    if product:
        policies = policies.filter(quotation__product=product)

    return Response(InsurancePolicySerializer(policies, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_policy(request: Request, policy_id: str) -> Response:
    """
    Récupère les détails d'une police d'assurance.

    Args:
        policy_id: UUID de la police

    Returns:
        Détails de la police
    """
    policy = get_object_or_404(
        InsurancePolicy.objects.select_related(
            "quotation",
            "quotation__location",
            "quotation__location__bien",
            "quotation__location__bien__adresse",
            "subscriber",
        ),
        id=policy_id,
        subscriber=request.user,
    )

    return Response(InsurancePolicySerializer(policy).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_policy_by_number(request: Request, policy_number: str) -> Response:
    """
    Récupère une police par son numéro.

    Utilisé pour la page de succès après paiement.

    Args:
        policy_number: Numéro de la police (PO-MRHIND-..., PO-PNOIND-..., etc.)

    Returns:
        Détails de la police
    """
    policy = get_object_or_404(
        InsurancePolicy.objects.select_related(
            "quotation",
            "quotation__location",
            "quotation__location__bien",
            "quotation__location__bien__adresse",
            "subscriber",
        ),
        policy_number=policy_number,
        subscriber=request.user,
    )

    return Response(InsurancePolicySerializer(policy).data)


# =============================================================================
# Documents
# =============================================================================


@api_view(["GET"])
@permission_classes([AllowAny])
def get_cgv_document(request: Request) -> Response:
    """
    Retourne l'URL des Conditions Générales de Vente (CGV) stockées sur S3/R2.

    Les CGV sont des documents publics accessibles sans authentification.
    Le PDF est généré une seule fois puis stocké sur S3.

    Query params (optionnel):
        product: Type de produit (MRH, PNO, GLI, défaut: MRH)
        force: Si "true", force la régénération du PDF même s'il existe

    Returns:
        {"url": "https://..."}
    """
    from .models import StaticDocument

    product = request.query_params.get("product", "MRH").upper()
    force_regenerate = request.query_params.get("force", "").lower() == "true"

    if product not in ["MRH", "PNO", "GLI"]:
        product = "MRH"

    document_type = f"CGV_{product}"

    try:
        doc = StaticDocument.get_or_generate(document_type, force_regenerate=force_regenerate)
        return Response({"url": doc.url})
    except Exception as e:
        logger.exception(f"Error getting CGV PDF: {e}")
        return Response(
            {"error": "Erreur lors de la récupération du document"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_dipa_document(request: Request) -> Response:
    """
    Retourne l'URL du DIPA (Document d'Information sur le Produit d'Assurance).

    Le DIPA est un document réglementaire statique stocké dans static/pdfs/assurances/.
    Même mécanisme que la notice d'information pour les baux.

    Query params (optionnel):
        product: Type de produit (MRH, PNO, GLI, défaut: MRH)

    Returns:
        {"url": "http://localhost:8003/pdf/static/assurances/dipa_mrh.pdf"}
    """
    from backend.pdf_utils import get_static_pdf_iframe_url

    product = request.query_params.get("product", "MRH").upper()

    if product not in ["MRH", "PNO", "GLI"]:
        product = "MRH"

    # Mapping des fichiers DIPA par produit (dans static/pdfs/assurances/)
    dipa_files = {
        "MRH": "assurances/dipa_mrh.pdf",
        # TODO: Ajouter PNO et GLI quand disponibles
        "PNO": "assurances/dipa_mrh.pdf",
        "GLI": "assurances/dipa_mrh.pdf",
    }

    pdf_path = dipa_files.get(product, dipa_files["MRH"])

    # Utiliser le même mécanisme que la notice d'information
    full_url = get_static_pdf_iframe_url(request, pdf_path)

    return Response({"url": full_url})


@api_view(["GET"])
@permission_classes([AllowAny])
def get_der_document(request: Request) -> Response:
    """
    Retourne l'URL du DER (Document d'Entrée en Relation).

    Le DER est un document réglementaire obligatoire pour les courtiers en assurance.
    Il est stocké en media storage et retourné via URL.

    Query params (optionnel):
        force: "true" pour forcer la régénération

    Returns:
        {"url": "https://..."}
    """
    from .models import StaticDocument

    force_regenerate = request.query_params.get("force", "").lower() == "true"

    try:
        doc = StaticDocument.get_or_generate("DER", force_regenerate=force_regenerate)
        return Response({"url": doc.url})
    except Exception as e:
        logger.exception(f"Error getting DER PDF: {e}")
        return Response(
            {"error": "Erreur lors de la récupération du document"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_devis_document(request: Request) -> HttpResponse:
    """
    Génère un devis personnalisé en PDF.

    Query params:
        quotation_id: UUID du devis
        formula_code: Code de la formule sélectionnée (optionnel)

    Returns:
        PDF du devis
    """
    quotation_id = request.query_params.get("quotation_id")
    formula_code = request.query_params.get("formula_code")

    if not quotation_id:
        return HttpResponse("quotation_id requis", status=400)

    # Récupérer le devis
    quotation = get_object_or_404(
        InsuranceQuotation.objects.select_related(
            "location",
            "location__bien",
            "location__bien__adresse",
        ).prefetch_related("location__locataires"),
        id=quotation_id,
    )

    # Vérifier que l'utilisateur est locataire de cette location
    if quotation.location:
        user_info = get_user_info_for_location(quotation.location, request.user.email)
        if not user_info.is_locataire:
            return HttpResponse("Accès non autorisé", status=403)

    # Construire les données pour le PDF
    quotation_data = {
        "id": str(quotation.id),
        "product": quotation.product,
        "deductible": quotation.deductible,
        "effective_date": quotation.effective_date,
        "created_at": quotation.created_at,
        "expires_at": quotation.expires_at,
        "formulas": quotation.formulas_data,
    }

    # Si un code de formule est spécifié, ne garder que celle-ci
    if formula_code:
        quotation_data["formulas"] = [
            f for f in quotation.formulas_data if f.get("code") == formula_code
        ]

    try:
        documents_service = InsuranceDocumentService()
        pdf_bytes = documents_service.generate_devis(
            quotation_data=quotation_data,
            subscriber=request.user,
            bien=quotation.location.bien if quotation.location else None,
        )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = f"Devis_Assurance_{quotation.product}_{quotation.id}.pdf"
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

    except Exception as e:
        logger.exception(f"Error generating devis PDF: {e}")
        return HttpResponse(
            "Erreur lors de la génération du document",
            status=500,
        )
