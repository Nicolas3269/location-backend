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
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from weasyprint import HTML

from backend.pdf_utils import get_pdf_iframe_url, get_static_pdf_iframe_url
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
)
from rent_control.utils import get_rent_price_for_bien
from signature.pdf_processing import prepare_pdf_with_signature_fields_generic
from signature.views import (
    confirm_signature_generic,
    get_signature_request_generic,
    resend_otp_generic,
)

logger = logging.getLogger(__name__)

INDICE_IRL = 145.47


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

        # Vérifier si au moins un locataire a une caution requise
        acte_de_cautionnement = bail.location.locataires.filter(
            caution_requise=True
        ).exists()

        # Calculer une seule fois les données d'encadrement des loyers
        encadrement_data = BailMapping.get_encadrement_loyers_data(bail)
        zone_tendue_avec_loyer_encadre = bool(encadrement_data["prix_reference"])
        # Générer le PDF depuis le template HTML
        html = render_to_string(
            "pdf/bail.html",
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
                "zone_tendue_avec_loyer_encadre": zone_tendue_avec_loyer_encadre,
                "prix_reference": encadrement_data["prix_reference"],
                "prix_majore": encadrement_data["prix_majore"],
                "complement_loyer": encadrement_data["complement_loyer"],
                "justificatif_complement_loyer": bail.location.rent_terms.justificatif_complement_loyer
                if hasattr(bail.location, "rent_terms")
                else None,
                "is_copropriete": BailMapping.is_copropriete(bail),
                "potentiel_permis_de_louer": BailMapping.potentiel_permis_de_louer(
                    bail
                ),
            },
        )
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
            prepare_pdf_with_signature_fields_generic(tmp_pdf_path, bail)

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
                "pdfUrl": request.build_absolute_uri(bail.pdf.url),
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
    return confirm_signature_generic(request, BailSignatureRequest, "bail")


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
                nom_original=file.name,
                file=file,
                uploade_par=request.user,
            )

            uploaded_files.append(
                {
                    "id": str(document.id),
                    "name": document.nom_original,
                    "url": request.build_absolute_uri(document.file.url),
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

        # Supprimer le fichier du système de fichiers si il existe
        if document.file and hasattr(document.file, "path"):
            try:
                if os.path.exists(document.file.path):
                    os.remove(document.file.path)
            except Exception as e:
                logger.warning(
                    f"Impossible de supprimer le fichier {document.file.path}: {e}"
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_rent_prices(request):
    """
    Récupère les prix de référence pour une zone donnée
    selon les caractéristiques minimales du bien
    """
    try:
        from location.serializers_composed import BienRentPriceSerializer

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
                "bien_id": bail.location.bien.id if bail.location and bail.location.bien else None,
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
        # L'utilisateur doit être le signataire d'un des bailleurs du bien
        # ou être un locataire d'un bail sur ce bien
        user_bails = Bail.objects.filter(location__bien=bien)
        has_access = False

        # Récupérer l'email de l'utilisateur connecté
        user_email = request.user.email

        # Vérifier si l'utilisateur est signataire d'un des bailleurs
        for bailleur in bien.bailleurs.all():
            if bailleur.signataire and bailleur.signataire.email == user_email:
                has_access = True
                break

        # Si pas encore d'accès, vérifier si l'utilisateur est locataire
        if not has_access:
            for bail in user_bails:
                if bail.location.locataires.filter(email=user_email).exists():
                    has_access = True
                    break

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
        has_access = False

        # Vérifier si l'utilisateur est signataire d'un des bailleurs
        for bailleur in bien.bailleurs.all():
            if bailleur.signataire and bailleur.signataire.email == user_email:
                has_access = True
                break

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

            pdf_url = get_pdf_iframe_url(request, bail.pdf) if bail.pdf else None
            latest_pdf_url = (
                get_pdf_iframe_url(request, bail.latest_pdf)
                if bail.latest_pdf
                else None
            )
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
    return resend_otp_generic(request, BailSignatureRequest, "bail")


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

        # Vérifier que le type est MRH ou Caution
        if document_type not in [
            DocumentType.ATTESTATION_MRH,
            DocumentType.CAUTION_SOLIDAIRE,
        ]:
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "Type invalide. Attendu: attestation_mrh ou "
                        "caution_solidaire"
                    ),
                },
                status=400,
            )

        locataire = get_object_or_404(Locataire, id=locataire_id)

        # Pour attestation_mrh (document unique), supprimer les anciens documents
        # avant d'uploader le nouveau (comportement "remplacer")
        if document_type == DocumentType.ATTESTATION_MRH:
            old_documents = Document.objects.filter(
                locataire=locataire,
                type_document=DocumentType.ATTESTATION_MRH
            )
            # Supprimer les fichiers physiques avant de supprimer les entrées BDD
            for old_doc in old_documents:
                if old_doc.file:
                    old_doc.file.delete(save=False)
            old_documents.delete()

        uploaded_files = []
        files = request.FILES.getlist("files")

        for file in files:
            # Créer le document
            document = Document.objects.create(
                locataire=locataire,
                type_document=document_type,
                nom_original=file.name,
                file=file,
                uploade_par=request.user,
            )

            uploaded_files.append(
                {
                    "id": str(document.id),
                    "name": document.nom_original,
                    "url": request.build_absolute_uri(document.file.url),
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


