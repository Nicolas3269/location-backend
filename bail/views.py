import json
import logging
import os
import uuid

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from pyproj import Transformer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from weasyprint import HTML

from backend.pdf_utils import (
    get_logo_pdf_base64_data_uri,
    get_static_pdf_iframe_url,
)
from backend.storage_utils import truncate_filename
from bail.constants import FORMES_JURIDIQUES
from bail.generate_bail.mapping import BailMapping
from bail.models import (
    Bail,
    BailSignatureRequest,
    Document,
    DocumentType,
)
from bail.utils import (
    create_signature_requests,
)

# from etat_lieux.utils import get_or_create_pieces_for_bien  # Supprimé - nouvelle architecture
from location.models import (
    Bien,
    RentTerms,
)
from location.serializers.composed import BienRentPriceSerializer
from location.services.access_utils import user_has_bien_access
from rent_control.utils import get_rent_price_for_bien
from signature.document_status import DocumentStatus
from signature.document_types import SignableDocumentType
from signature.pdf_processing import prepare_pdf_with_signature_fields_generic
from signature.views import (
    cancel_signature_generic,
    confirm_signature_generic,
    get_signature_request_generic,
    resend_otp_generic,
)

logger = logging.getLogger(__name__)

# Transformer Lambert-93 (EPSG:2154) → WGS84 (EPSG:4326) pour les coordonnées SIRENE
_lambert_to_wgs84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)

INDICE_IRL = 145.78


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

        bail = get_object_or_404(Bail, id=bail_id)

        # IDEMPOTENCE: Si le bail est déjà SIGNING ou SIGNED, retourner les données existantes
        # Cela évite de recréer des signature requests en cas de refresh de page
        if bail.status in [DocumentStatus.SIGNING, DocumentStatus.SIGNED]:
            # Récupérer le linkToken du premier signataire non-signé (ou None si tous ont signé)
            first_unsigned_req = (
                bail.signature_requests.filter(signed=False).order_by("order").first()
            )
            link_token = (
                str(first_unsigned_req.link_token) if first_unsigned_req else None
            )

            return JsonResponse(
                {
                    "success": True,
                    "bailId": str(bail.id),
                    "pdfUrl": bail.pdf.url if bail.pdf else None,
                    "linkTokenFirstSigner": link_token,
                    "status": bail.status,
                    "alreadySigning": bail.status == DocumentStatus.SIGNING,
                    "alreadySigned": bail.status == DocumentStatus.SIGNED,
                }
            )

        # Vérifier si les documents annexes sont uploadés
        has_reglement_copropriete_uploaded = Document.objects.filter(
            bail=bail, type_document=DocumentType.REGLEMENT_COPROPRIETE
        ).exists()
        has_permis_de_louer_uploaded = Document.objects.filter(
            bail=bail, type_document=DocumentType.PERMIS_DE_LOUER
        ).exists()
        has_diagnostic_uploaded = Document.objects.filter(
            bail=bail, type_document=DocumentType.DIAGNOSTIC
        ).exists()

        # Vérifier si au moins un locataire a une caution requise
        acte_de_cautionnement = bail.location.locataires.filter(
            caution_requise=True
        ).exists()

        # Calculer une seule fois les données d'encadrement des loyers
        encadrement_data = BailMapping.get_encadrement_loyers_data(bail)
        zone_tendue_avec_loyer_encadre = bool(encadrement_data["prix_reference"])
        # Récupérer les données du dernier loyer si disponibles
        dernier_montant_loyer = None
        dernier_loyer_periode_formatted = None
        display_precedent_loyer = False
        if hasattr(bail.location, "rent_terms") and bail.location.rent_terms:
            rent_terms: RentTerms = bail.location.rent_terms
            dernier_montant_loyer = rent_terms.dernier_montant_loyer
            dernier_loyer_periode = rent_terms.dernier_loyer_periode
            display_precedent_loyer = (
                rent_terms.zone_tendue
                and not rent_terms.premiere_mise_en_location
                and rent_terms.locataire_derniers_18_mois
                and dernier_montant_loyer
                and dernier_loyer_periode
            )

            # Formater la période (YYYY-MM -> "Mois Année")
            if dernier_loyer_periode:
                from datetime import datetime

                try:
                    date_obj = datetime.strptime(dernier_loyer_periode, "%Y-%m")
                    # Formater en français: "janvier 2024", "février 2024", etc.
                    mois_fr = [
                        "janvier",
                        "février",
                        "mars",
                        "avril",
                        "mai",
                        "juin",
                        "juillet",
                        "août",
                        "septembre",
                        "octobre",
                        "novembre",
                        "décembre",
                    ]
                    dernier_loyer_periode_formatted = (
                        f"{mois_fr[date_obj.month - 1]} {date_obj.year}"
                    )
                except ValueError:
                    # Si le format n'est pas valide, garder la valeur originale
                    dernier_loyer_periode_formatted = dernier_loyer_periode

        # Calculer les honoraires du mandataire
        honoraires_data = BailMapping.get_honoraires_mandataire_data(bail)

        # Générer le PDF depuis le template HTML
        html = render_to_string(
            "pdf/bail/bail.html",
            {
                "bail": bail,
                "acte_de_cautionnement": acte_de_cautionnement,
                "title_bail": BailMapping.title_bail(bail.location.bien),
                "subtitle_bail": BailMapping.subtitle_bail(bail.location.bien),
                "article_objet_du_contrat": BailMapping.article_objet_du_contrat(
                    bail.location.bien
                ),
                "article_duree_contrat": BailMapping.article_duree_contrat(
                    bail.location.bien
                ),
                "pieces_info": BailMapping.pieces_info(bail.location.bien),
                "annexes_privatives_info": BailMapping.annexes_privatives_info(
                    bail.location.bien
                ),
                "annexes_collectives_info": BailMapping.annexes_collectives_info(
                    bail.location.bien
                ),
                "information_info": BailMapping.information_info(bail.location.bien),
                "energy_info": BailMapping.energy_info(bail.location.bien),
                "indice_irl": INDICE_IRL,
                "display_precedent_loyer": display_precedent_loyer,
                "zone_tendue_avec_loyer_encadre": zone_tendue_avec_loyer_encadre,
                "prix_reference": encadrement_data["prix_reference"],
                "prix_majore": encadrement_data["prix_majore"],
                "complement_loyer": encadrement_data["complement_loyer"],
                "justificatif_complement_loyer": bail.location.rent_terms.justificatif_complement_loyer
                if hasattr(bail.location, "rent_terms")
                else None,
                "dernier_montant_loyer": dernier_montant_loyer,
                "dernier_loyer_periode": dernier_loyer_periode_formatted,
                "is_copropriete": BailMapping.is_copropriete(bail),
                "potentiel_permis_de_louer": BailMapping.potentiel_permis_de_louer(
                    bail
                ),
                "logo_base64_uri": get_logo_pdf_base64_data_uri(),
                "honoraires_mandataire": honoraires_data,
                "has_reglement_copropriete_uploaded": has_reglement_copropriete_uploaded,
                "has_permis_de_louer_uploaded": has_permis_de_louer_uploaded,
                "has_diagnostic_uploaded": has_diagnostic_uploaded,
            },
        )
        pdf_bytes = HTML(
            string=html,
            base_url=request.build_absolute_uri(),
        ).write_pdf()

        # Noms de fichiers
        base_filename = f"bail_{bail.id}_{uuid.uuid4().hex}"
        pdf_filename = f"{base_filename}.pdf"
        tmp_pdf_path = f"/tmp/{pdf_filename}"
        try:
            # 1. Sauver temporairement
            with open(tmp_pdf_path, "wb") as f:
                f.write(pdf_bytes)

            # 2. Ajouter les champs de signature
            # La fonction gère automatiquement le téléchargement depuis R2 si nécessaire
            prepare_pdf_with_signature_fields_generic(tmp_pdf_path, bail)

            # 3. ✅ NOUVEAU : Certifier avec Hestia (certify=True + DocMDP)
            try:
                from signature.certification_flow import certify_document_hestia

                certified_pdf_path = tmp_pdf_path.replace(".pdf", "_certified.pdf")
                certify_document_hestia(
                    source_path=tmp_pdf_path,
                    output_path=certified_pdf_path,
                    document_type=SignableDocumentType.BAIL.value,
                )

                # Utiliser le PDF certifié au lieu du PDF vierge
                tmp_pdf_path = certified_pdf_path
                logger.info(f"✅ Bail {bail.id} certifié Hestia avec succès")
            except FileNotFoundError as e:
                logger.warning(f"⚠️ Certificat Hestia AATL manquant (mode dev) : {e}")
                logger.warning("⚠️ PDF non certifié, continuons quand même")
            except ValueError as e:
                logger.warning(f"⚠️ PASSWORD_CERT_SERVER manquant : {e}")
                logger.warning("⚠️ PDF non certifié, continuons quand même")
            except Exception as e:
                logger.error(f"❌ Erreur certification Hestia : {e}")
                logger.error("⚠️ PDF non certifié, continuons quand même")

            # 4. Recharger dans bail.pdf
            with open(tmp_pdf_path, "rb") as f:
                bail.pdf.save(pdf_filename, ContentFile(f.read()), save=True)

        finally:
            # 5. Supprimer les fichiers temporaires
            for temp_file in [
                tmp_pdf_path,
                tmp_pdf_path.replace("_certified.pdf", ".pdf"),
            ]:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logger.warning(f"Impossible de supprimer {temp_file}: {e}")

        create_signature_requests(bail, user=request.user)

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


@api_view(["GET"])
@permission_classes([AllowAny])
def get_signature_request(request, token):
    """Vue pour récupérer les informations d'une demande de signature de bail"""
    return get_signature_request_generic(request, token, BailSignatureRequest)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_signature_bail(request):
    """Vue pour confirmer une signature de bail"""
    return confirm_signature_generic(
        request, BailSignatureRequest, SignableDocumentType.BAIL.value
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_signature_bail(request, bail_id):
    """Vue pour annuler une signature de bail en cours"""
    return cancel_signature_generic(request, bail_id, Bail)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_notice_information_pdf(request):
    """Retourne l'URL de la notice d'information statique"""
    try:
        # Utiliser notre nouvelle route PDF pour iframe
        full_url = get_static_pdf_iframe_url(request, "bails/notice_information.pdf")

        return JsonResponse(
            {
                "success": True,
                "noticeUrl": full_url,
                "filename": "notice_information.pdf",
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la récupération de la notice d'information")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la récupération: {str(e)}"},
            status=500,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_document(request):
    """Upload générique de documents pour un bail spécifique"""
    try:
        # Vérifier si des fichiers sont fournis
        if not request.FILES:
            return JsonResponse(
                {"success": False, "error": "Aucun fichier fourni"}, status=400
            )

        bail_id = request.POST.get("bail_id")
        document_type = request.POST.get("document_type")

        if not bail_id:
            return JsonResponse(
                {"success": False, "error": "ID du bail requis"}, status=400
            )

        if not document_type:
            return JsonResponse(
                {"success": False, "error": "Type de document requis"}, status=400
            )

        # Vérifier que le type de document est valide
        valid_types = [choice[0] for choice in DocumentType.choices]
        if document_type not in valid_types:
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        f"Type de document invalide. Types acceptés: {valid_types}"
                    ),
                },
                status=400,
            )

        bail = get_object_or_404(Bail, id=bail_id)
        bien = bail.location.bien

        uploaded_files = []

        # Récupérer tous les fichiers uploadés avec le nom 'files'
        files = request.FILES.getlist("files")

        # Traiter chaque fichier uploadé
        for file in files:
            # Vérifier le type de fichier selon le type de document
            allowed_extensions = [".pdf"]

            file_extension = None
            for ext in allowed_extensions:
                if file.name.lower().endswith(ext):
                    file_extension = ext
                    break

            if not file_extension:
                extensions_str = ", ".join(allowed_extensions)
                error_msg = (
                    f"Le fichier {file.name} doit être de type: {extensions_str}"
                )
                return JsonResponse(
                    {
                        "success": False,
                        "error": error_msg,
                    },
                    status=400,
                )

            # Vérifier la taille du fichier (max 10MB)
            if file.size > 10 * 1024 * 1024:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Le fichier {file.name} trop volumineux (max 10MB)",
                    },
                    status=400,
                )

            # Créer le document via le modèle Document
            document = Document.objects.create(
                bail=bail,
                bien=bien,
                type_document=document_type,
                nom_original=truncate_filename(file.name),
                file=file,
                uploade_par=request.user,
            )

            uploaded_files.append(
                {
                    "id": str(document.id),
                    "name": document.nom_original,
                    "url": document.file.url,
                    "type": document.get_type_document_display(),
                    "created_at": document.created_at.isoformat(),
                }
            )

        document_type_display = DocumentType(document_type).label
        success_msg = (
            f"{len(uploaded_files)} document(s) de type "
            f"'{document_type_display}' uploadé(s) avec succès"
        )
        return JsonResponse(
            {
                "success": True,
                "documents": uploaded_files,
                "message": success_msg,
            }
        )

    except Exception as e:
        log_msg = f"Erreur lors de l'upload des documents de type {document_type}"
        logger.exception(log_msg)
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de l'upload: {str(e)}"},
            status=500,
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_document(request, document_id):
    """
    Supprimer un document spécifique
    """
    try:
        # Récupérer le document
        document = get_object_or_404(Document, id=document_id)

        # Vérifier que l'utilisateur a le droit de supprimer ce document
        # (seul celui qui l'a uploadé peut le supprimer)
        if document.uploade_par != request.user:
            return JsonResponse(
                {"success": False, "error": "Non autorisé à supprimer ce document"},
                status=403,
            )

        # Supprimer le fichier du storage (R2 ou local filesystem)
        if document.file:
            try:
                document.file.delete(save=False)
            except Exception as e:
                logger.warning(
                    f"Impossible de supprimer le fichier {document.file.name}: {e}"
                )

        # Supprimer l'entrée de la base de données
        document.delete()

        return JsonResponse(
            {"success": True, "message": "Document supprimé avec succès"}
        )

    except Exception as e:
        logger.exception(f"Erreur lors de la suppression du document {document_id}")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la suppression: {str(e)}"},
            status=500,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_bail_documents(request, bail_id):
    """
    Récupère les documents annexes associés à un bail (diagnostics, permis de louer).
    Utilisé pour recharger les documents après un refresh de page.
    """
    try:
        bail = get_object_or_404(Bail, id=bail_id)

        # Vérifier que l'utilisateur a accès au bien
        if not user_has_bien_access(bail.location.bien, request.user.email):
            return JsonResponse({"success": False, "error": "Non autorisé"}, status=403)

        # Récupérer les documents de type diagnostic, permis_de_louer et reglement_copropriete
        documents = Document.objects.filter(
            bail=bail,
            type_document__in=[
                DocumentType.DIAGNOSTIC,
                DocumentType.PERMIS_DE_LOUER,
                DocumentType.REGLEMENT_COPROPRIETE,
            ],
        ).order_by("type_document", "created_at")

        diagnostics = []
        permis_de_louer = []
        reglement_copropriete = []

        for doc in documents:
            doc_data = {
                "id": str(doc.id),
                "name": doc.nom_original,
                "url": doc.file.url if doc.file else None,
                "type": doc.get_type_document_display(),
            }
            if doc.type_document == DocumentType.DIAGNOSTIC:
                diagnostics.append(doc_data)
            elif doc.type_document == DocumentType.PERMIS_DE_LOUER:
                permis_de_louer.append(doc_data)
            elif doc.type_document == DocumentType.REGLEMENT_COPROPRIETE:
                reglement_copropriete.append(doc_data)

        return JsonResponse(
            {
                "success": True,
                "diagnostics": diagnostics,
                "permis_de_louer": permis_de_louer,
                "reglement_copropriete": reglement_copropriete,
            }
        )

    except Exception as e:
        logger.exception(
            f"Erreur lors de la récupération des documents du bail {bail_id}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_rent_prices(request):
    """
    Récupère les prix de référence pour une zone donnée
    selon les caractéristiques minimales du bien
    """
    try:
        data = request.data

        # Utiliser le serializer minimal pour valider et extraire les données
        if "bien" not in data:
            return JsonResponse({"error": "Données du bien requises"}, status=400)
        bien_data = data["bien"]
        serializer = BienRentPriceSerializer(data=bien_data)

        if not serializer.is_valid():
            return JsonResponse(
                {"error": "Données invalides", "details": serializer.errors}, status=400
            )

        validated = serializer.validated_data
        area_id = validated.get("area_id")

        if not area_id:
            return JsonResponse({"error": "Area ID requis"}, status=400)

        # Utiliser le serializer pour créer l'instance Bien
        bien = serializer.create_bien_instance(validated)

        try:
            rent_price = get_rent_price_for_bien(bien, area_id)

            return JsonResponse(
                {
                    "success": True,
                    "rentPrice": {
                        "id": rent_price.id,
                        "reference_price": float(rent_price.reference_price),
                        "min_price": float(rent_price.min_price),
                        "max_price": float(rent_price.max_price),
                    },
                }
            )

        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)

    except Exception as e:
        logger.error(f"❌ Erreur: {str(e)}")
        return JsonResponse({"error": f"Erreur: {str(e)}"}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_company_data(request):
    """
    Récupère les données d'une société via l'API SIRENE (SIRET)
    """
    # Mapping des codes de formes juridiques INSEE vers leurs libellés
    siret = request.GET.get("siret")

    if not siret:
        return JsonResponse({"error": "Le numéro SIRET est requis"}, status=400)

    # Valider le format SIRET (14 chiffres)
    if not siret.isdigit() or len(siret) != 14:
        return JsonResponse(
            {"error": "Le numéro SIRET doit contenir exactement 14 chiffres"},
            status=400,
        )

    try:
        # Appel à l'API SIRENE
        # 90020721800018
        api_url = f"https://api.insee.fr/api-sirene/3.11/siret/{siret}"
        headers = {
            "accept": "application/json",
            "X-INSEE-Api-Key-Integration": settings.SIRENE_API_KEY,
        }

        response = requests.get(api_url, headers=headers, timeout=10)

        if response.status_code == 400:
            return JsonResponse({"error": "Société non trouvée"}, status=404)

        if response.status_code != 200:
            return JsonResponse(
                {"error": "Erreur lors de la récupération des données"}, status=500
            )

        data = response.json()

        # Extraire les informations de l'établissement et de l'unité légale
        if "etablissement" not in data:
            return JsonResponse(
                {"error": "Aucune donnée trouvée pour ce SIRET"}, status=404
            )

        etablissement = data["etablissement"]
        unite_legale = etablissement.get("uniteLegale") or {}
        adresse_etablissement = etablissement.get("adresseEtablissement") or {}

        # Construire la réponse avec les données formatées
        company_data = {}

        # Raison sociale
        denomination = unite_legale.get("denominationUniteLegale")
        if denomination:
            company_data["raison_sociale"] = denomination
        else:
            prenom = unite_legale.get("prenom1UniteLegale")
            nom = unite_legale.get("nomUniteLegale")
            if prenom and nom:
                company_data["raison_sociale"] = f"{prenom} {nom}"
            elif nom:
                company_data["raison_sociale"] = nom

        # Forme juridique
        categorie = unite_legale.get("categorieJuridiqueUniteLegale")
        if categorie:
            company_data["forme_juridique"] = FORMES_JURIDIQUES.get(
                categorie, categorie
            )

        # Adresse
        adresse = {}
        if "numeroVoieEtablissement" in adresse_etablissement:
            adresse["numero"] = adresse_etablissement["numeroVoieEtablissement"]

        voie_parts = []
        if "typeVoieEtablissement" in adresse_etablissement:
            voie_parts.append(adresse_etablissement["typeVoieEtablissement"])
        if "libelleVoieEtablissement" in adresse_etablissement:
            voie_parts.append(adresse_etablissement["libelleVoieEtablissement"])
        if voie_parts:
            adresse["voie"] = " ".join(voie_parts)

        if "codePostalEtablissement" in adresse_etablissement:
            adresse["code_postal"] = adresse_etablissement["codePostalEtablissement"]
        if "libelleCommuneEtablissement" in adresse_etablissement:
            adresse["ville"] = adresse_etablissement["libelleCommuneEtablissement"]

        if adresse:
            adresse["pays"] = "FR"  # INSEE = toujours France

            # Coordonnées GPS (conversion Lambert-93 → WGS84)
            lambert_x = adresse_etablissement.get(
                "coordonneeLambertAbscisseEtablissement"
            )
            lambert_y = adresse_etablissement.get(
                "coordonneeLambertOrdonneeEtablissement"
            )

            if lambert_x and lambert_y:
                try:
                    lng, lat = _lambert_to_wgs84.transform(
                        float(lambert_x), float(lambert_y)
                    )
                    adresse["longitude"] = round(lng, 7)
                    adresse["latitude"] = round(lat, 7)
                except (ValueError, TypeError):
                    logger.error(
                        f"Coordonnées Lambert-93 invalides pour SIRET {siret}: "
                        f"x={lambert_x}, y={lambert_y}"
                    )

            company_data["adresse"] = adresse

        return JsonResponse(company_data)

    except requests.exceptions.Timeout:
        return JsonResponse(
            {"error": "Timeout lors de la récupération des données"}, status=500
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur lors de l'appel à l'API SIRENE: {str(e)}")
        return JsonResponse(
            {"error": "Erreur lors de la récupération des données"}, status=500
        )
    except Exception as e:
        logger.error(f"Erreur inattendue: {str(e)}")
        return JsonResponse({"error": "Erreur interne du serveur"}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_bail_bien_id(request, bail_id):
    """
    Récupère le bien_id associé à un bail.
    Endpoint simple pour obtenir le bien_id depuis un bail_id.
    """
    try:
        bail = get_object_or_404(Bail, id=bail_id)
        return JsonResponse(
            {
                "success": True,
                "bail_id": bail_id,
                "bien_id": bail.location.bien.id
                if bail.location and bail.location.bien
                else None,
            }
        )
    except Exception as e:
        logger.error(
            f"Erreur lors de la récupération du bien_id pour le bail {bail_id}: {e}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_bien_detail(request, bien_id):
    """
    Récupère les détails d'un bien avec ses pièces pour l'état des lieux.
    Crée des EtatLieuxPiece en base si elles n'existent pas déjà.
    """
    try:
        # Récupérer le bien
        bien = get_object_or_404(Bien, id=bien_id)

        # Vérifier que l'utilisateur a accès à ce bien
        # L'utilisateur doit être bailleur ou locataire d'un bail sur ce bien
        user_email = request.user.email
        has_access = user_has_bien_access(bien, user_email, check_locataires=True)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à ce bien"}, status=403
            )

        # Avec la nouvelle architecture, les pièces sont créées avec l'état des lieux
        # et gérées côté frontend. Cette route retourne une liste vide.
        pieces_data = []

        # Données du bien
        bien_data = {
            "id": bien.id,
            "adresse": bien.adresse,
            "type_bien": bien.get_type_bien_display(),
            "superficie": float(bien.superficie),
            "meuble": bien.meuble,
            "pieces": pieces_data,
            "pieces_info": bien.pieces_info,
        }

        return JsonResponse(bien_data)

    except Exception as e:
        logger.error(f"Erreur lors de la récupération du bien {bien_id}: {str(e)}")
        return JsonResponse(
            {"error": "Erreur lors de la récupération des données du bien"}, status=500
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_bien_baux(request, bien_id):
    """
    Récupère tous les baux (actifs et finalisés) d'un bien spécifique
    """
    try:
        # Récupérer le bien
        bien = get_object_or_404(Bien, id=bien_id)

        # Vérifier que l'utilisateur a accès à ce bien
        user_email = request.user.email
        has_access = user_has_bien_access(bien, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à ce bien"}, status=403
            )

        # Récupérer tous les baux du bien via les locations
        baux = Bail.objects.filter(location__bien=bien).order_by(
            "-location__date_debut"
        )

        baux_data = []
        for bail in baux:
            # Récupérer les locataires depuis la location
            locataires = [
                {
                    "lastName": locataire.lastName,
                    "firstName": locataire.firstName,
                    "email": locataire.email,
                }
                for locataire in bail.location.locataires.all()
            ]

            # Déterminer le statut du bail
            signatures_completes = not bail.signature_requests.filter(
                signed=False
            ).exists()

            pdf_url = bail.pdf.url if bail.pdf else None
            latest_pdf_url = bail.latest_pdf.url if bail.latest_pdf else None
            created_at = (
                bail.date_signature.isoformat() if bail.date_signature else None
            )

            bail_data = {
                "id": bail.id,
                "location_id": str(bail.location.id),
                "date_debut": bail.location.date_debut.isoformat()
                if bail.location.date_debut
                else None,
                "date_fin": bail.location.date_fin.isoformat()
                if bail.location.date_fin
                else None,
                "montant_loyer": float(bail.location.rent_terms.montant_loyer)
                if hasattr(bail.location, "rent_terms")
                else 0,
                "montant_charges": float(bail.location.rent_terms.montant_charges)
                if hasattr(bail.location, "rent_terms")
                else 0,
                "status": bail.status,
                "signatures_completes": signatures_completes,
                "locataires": locataires,
                "pdf_url": pdf_url,
                "latest_pdf_url": latest_pdf_url,
                "created_at": created_at,
            }
            baux_data.append(bail_data)

        return JsonResponse(
            {
                "success": True,
                "bien": {
                    "id": bien.id,
                    "adresse": bien.adresse,
                    "type_bien": bien.get_type_bien_display(),
                    "superficie": float(bien.superficie),
                    "meuble": bien.meuble,
                },
                "baux": baux_data,
            }
        )

    except Exception as e:
        error_msg = f"Erreur lors de la récupération des baux du bien {bien_id}"
        logger.error(f"{error_msg}: {str(e)}")
        return JsonResponse(
            {"error": "Erreur lors de la récupération des baux"}, status=500
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_otp_bail(request):
    """
    Renvoie un OTP pour la signature de bail
    """
    return resend_otp_generic(
        request, BailSignatureRequest, SignableDocumentType.BAIL.value
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_locataire_document(request):
    """Upload de documents pour un locataire (MRH, Caution)"""
    from location.models import Locataire

    try:
        if not request.FILES:
            return JsonResponse(
                {"success": False, "error": "Aucun fichier fourni"}, status=400
            )

        locataire_id = request.POST.get("locataire_id")
        document_type = request.POST.get("document_type")

        if not locataire_id:
            return JsonResponse(
                {"success": False, "error": "ID du locataire requis"}, status=400
            )

        if not document_type:
            return JsonResponse(
                {"success": False, "error": "Type de document requis"}, status=400
            )

        # Vérifier que le type est MRH, Caution ou Carte d'identité
        if document_type not in [
            DocumentType.ATTESTATION_MRH,
            DocumentType.CAUTION_SOLIDAIRE,
            DocumentType.CARTE_IDENTITE,
        ]:
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "Type invalide. Attendu: attestation_mrh, "
                        "caution_solidaire ou carte_identite"
                    ),
                },
                status=400,
            )

        locataire = get_object_or_404(Locataire, id=locataire_id)

        # Trouver le bail et le bien associés au locataire
        # (pour remplissage automatique)
        bail_associe = None
        bien_associe = None

        # Chercher la location active du locataire
        location_active = locataire.locations.order_by("-created_at").first()
        if location_active:
            # Récupérer le bail le plus récent (SIGNED ou SIGNING prioritaires)
            bail_associe = (
                location_active.bails.filter(status__in=["signed", "signing"])
                .order_by("-created_at")
                .first()
            )
            # Si pas de bail signé/en signature, prendre le plus récent (même DRAFT)
            if not bail_associe:
                bail_associe = location_active.bails.order_by("-created_at").first()

            # Récupérer le bien de la location
            bien_associe = location_active.bien

        # Pour attestation_mrh (document unique),
        # supprimer les anciens documents avant d'uploader le nouveau
        # Note: carte_identite permet plusieurs fichiers (recto/verso)
        if document_type == DocumentType.ATTESTATION_MRH:
            old_documents = Document.objects.filter(
                locataire=locataire, type_document=document_type
            )
            # Supprimer les fichiers physiques avant de supprimer les entrées BDD
            for old_doc in old_documents:
                if old_doc.file:
                    old_doc.file.delete(save=False)
            old_documents.delete()

        uploaded_files = []
        files = request.FILES.getlist("files")

        for file in files:
            # Créer le document avec relations automatiques
            document = Document.objects.create(
                locataire=locataire,
                bail=bail_associe,  # ✅ Auto-renseigné depuis la location
                bien=bien_associe,  # ✅ Auto-renseigné depuis la location
                type_document=document_type,
                nom_original=truncate_filename(file.name),
                file=file,
                uploade_par=request.user,
            )

            uploaded_files.append(
                {
                    "id": str(document.id),
                    "name": document.nom_original,
                    "url": document.file.url,
                    "type": document.get_type_document_display(),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "message": "Documents uploadés avec succès",
                "files": uploaded_files,
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de l'upload des documents locataire")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# ============================================================================
# Test-only endpoint for E2E tests
# ============================================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_test_signed_bail(request):
    """
    Crée un bail avec statut SIGNED pour les tests E2E.
    DEBUG mode uniquement - utilise les factories.

    Permet de tester les fonctionnalités qui nécessitent un bail signé
    (ex: création d'avenant) sans avoir à signer le bail via l'UI.

    Note: Le PDF n'est pas généré - seul le status SIGNED est défini.
    """
    if not settings.DEBUG:
        return JsonResponse(
            {"success": False, "error": "Test endpoint only available in DEBUG mode"},
            status=403,
        )

    try:
        import json

        data = json.loads(request.body)
        bailleur_email = data.get("bailleur_email")
        locataire_email = data.get("locataire_email")

        if not bailleur_email or not locataire_email:
            return JsonResponse(
                {
                    "success": False,
                    "error": "bailleur_email and locataire_email required",
                },
                status=400,
            )

        # Import factories (uniquement en DEBUG)
        from location.factories import create_complete_bail
        from signature.document_status import DocumentStatus

        # Créer le bail via factory avec status SIGNED
        bail = create_complete_bail(
            status=DocumentStatus.SIGNED,
        )

        # Mettre à jour les emails pour matcher les users créés via OTP
        bailleur = bail.location.bien.bailleurs.first()
        if bailleur and bailleur.personne:
            # Reset user pour re-link au bon User lors du save
            bailleur.personne.user = None
            bailleur.personne.email = bailleur_email
            bailleur.personne.save()

        locataire = bail.location.locataires.first()
        if locataire:
            # Reset user pour re-link au bon User lors du save
            locataire.user = None
            locataire.email = locataire_email
            locataire.save()

        logger.info(
            f"[TEST] Created signed bail {bail.id} for E2E tests "
            f"(bailleur: {bailleur_email}, locataire: {locataire_email})"
        )

        return JsonResponse(
            {
                "success": True,
                "bail_id": str(bail.id),
                "location_id": str(bail.location.id),
                "bien_id": str(bail.location.bien.id),
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la création du bail de test")
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=500,
        )
