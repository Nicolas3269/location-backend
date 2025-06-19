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
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from weasyprint import HTML

from bail.constants import FORMES_JURIDIQUES
from bail.generate_bail.mapping import BailMapping
from bail.models import (
    BailSignatureRequest,
    BailSpecificites,
    Document,
    DocumentType,
    Locataire,
    Proprietaire,
)
from bail.utils import (
    create_bien_from_form_data,
    create_signature_requests,
    prepare_pdf_with_signature_fields,
    process_signature,
    send_signature_email,
)
from rent_control.models import RentPrice
from rent_control.utils import get_rent_price_for_bien

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

        bail = get_object_or_404(BailSpecificites, id=bail_id)

        # Vérifier si au moins un locataire a une caution requise
        acte_de_cautionnement = bail.locataires.filter(caution_requise=True).exists()

        # Générer le PDF depuis le template HTML
        html = render_to_string(
            "pdf/bail_wrapper.html",
            {
                "bail": bail,
                "acte_de_cautionnement": acte_de_cautionnement,
                "title_bail": BailMapping.title_bail(bail.bien),
                "subtitle_bail": BailMapping.subtitle_bail(bail.bien),
                "article_objet_du_contrat": BailMapping.article_objet_du_contrat(
                    bail.bien
                ),
                "article_duree_contrat": BailMapping.article_duree_contrat(bail.bien),
                "pieces_info": BailMapping.pieces_info(bail.bien),
                "annexes_privatives_info": BailMapping.annexes_privatives_info(
                    bail.bien
                ),
                "annexes_collectives_info": BailMapping.annexes_collectives_info(
                    bail.bien
                ),
                "information_info": BailMapping.information_info(bail.bien),
                "energy_info": BailMapping.energy_info(bail.bien),
                "indice_irl": INDICE_IRL,
                "prix_reference": BailMapping.prix_reference(bail),
                "prix_majore": BailMapping.prix_majore(bail),
                "complement_loyer": BailMapping.complement_loyer(bail),
                "justificatif_complement_loyer": bail.justificatif_complement_loyer,
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
        bail_absolute_url = request.build_absolute_uri(bail_url)
        return JsonResponse({"success": True, "pdfUrl": bail_absolute_url})

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
    """Retourne l'URL de la grille de vétusté statique"""
    try:
        # URL media du fichier PDF avec URL complète
        media_pdf_url = f"{settings.MEDIA_URL}bails/grille_vetuste.pdf"
        full_url = request.build_absolute_uri(media_pdf_url)

        return JsonResponse(
            {
                "success": True,
                "grillVetustUrl": full_url,
                "filename": "grille_vetuste.pdf",
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la récupération de la grille de vétusté")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la récupération: {str(e)}"},
            status=500,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_notice_information_pdf(request):
    """Retourne l'URL de la notice d'information statique"""
    try:
        # URL media du fichier PDF
        media_pdf_url = f"{settings.MEDIA_URL}bails/notice_information.pdf"
        full_url = request.build_absolute_uri(media_pdf_url)

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
def upload_diagnostics(request):
    """Upload de diagnostics pour un bien spécifique"""
    try:
        # Vérifier si des fichiers sont fournis
        if not request.FILES:
            return JsonResponse(
                {"success": False, "error": "Aucun fichier fourni"}, status=400
            )

        bail_id = request.POST.get("bail_id")

        if not bail_id:
            return JsonResponse(
                {"success": False, "error": "ID du bail requis"}, status=400
            )

        bail = get_object_or_404(BailSpecificites, id=bail_id)
        bien = bail.bien

        uploaded_files = []

        # Récupérer tous les fichiers uploadés avec le nom 'diagnostic_files'
        diagnostic_files = request.FILES.getlist("diagnostic_files")

        # Traiter chaque fichier uploadé
        for diagnostic_file in diagnostic_files:
            # Vérifier le type de fichier
            if not diagnostic_file.name.lower().endswith(".pdf"):
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Le fichier {diagnostic_file.name} doit être PDF",
                    },
                    status=400,
                )

            # Vérifier la taille du fichier (max 10MB)
            if diagnostic_file.size > 10 * 1024 * 1024:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Le fichier {diagnostic_file.name} trop volumineux",
                    },
                    status=400,
                )

            # Créer le document via le modèle Document
            document = Document.objects.create(
                bail=bail,
                bien=bien,
                type_document=DocumentType.DIAGNOSTIC,
                nom_original=diagnostic_file.name,
                file=diagnostic_file,
                uploade_par=request.user,
            )

            uploaded_files.append(
                {
                    "id": str(document.id),
                    "name": document.nom_original,
                    "url": request.build_absolute_uri(document.url),
                    "type": "Diagnostic",
                    "created_at": document.date_creation.isoformat(),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "documents": uploaded_files,
                "message": f"{len(uploaded_files)} diagnostic(s) uploadé(s) "
                f"avec succès",
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de l'upload des diagnostics")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de l'upload: {str(e)}"},
            status=500,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_draft(request):
    """Sauvegarde un brouillon de bail à partir des données du formulaire"""
    import time
    from datetime import datetime
    from decimal import Decimal

    from django.db import OperationalError, transaction

    max_retries = 3
    retry_delay = 0.1  # 100ms

    for attempt in range(max_retries):
        try:
            with transaction.atomic():
                form_data = json.loads(request.body)

                # Validation des données requises
                if not form_data.get("adresse"):
                    return JsonResponse(
                        {"success": False, "error": "L'adresse est requise"}, status=400
                    )

                if not form_data.get("landlord", {}).get("firstName"):
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Le prénom du propriétaire est requis",
                        },
                        status=400,
                    )

                # 1. Créer les propriétaires
                # Propriétaire principal
                landlord_data = form_data.get("landlord", {})
                proprietaire_principal = Proprietaire.objects.create(
                    nom=landlord_data.get("lastName", ""),
                    prenom=landlord_data.get("firstName", ""),
                    adresse=landlord_data.get("address", ""),
                    email=landlord_data.get("email", ""),
                    telephone="",  # Pas fourni dans le formulaire
                )

                # Propriétaires additionnels
                proprietaires = [proprietaire_principal]
                other_landlords = form_data.get("otherLandlords", [])
                for landlord in other_landlords:
                    proprietaire = Proprietaire.objects.create(
                        nom=landlord.get("lastName", ""),
                        prenom=landlord.get("firstName", ""),
                        adresse=landlord.get("address", ""),
                        email=landlord.get("email", ""),
                        telephone="",  # Pas fourni dans le formulaire
                    )
                    proprietaires.append(proprietaire)

                # 2. Créer le bien
                bien = create_bien_from_form_data(form_data, save=True)

                # Associer les propriétaires au bien
                bien.proprietaires.set(proprietaires)

                # 3. Créer les locataires
                locataires_data = form_data.get("locataires", [])
                locataires = []
                for locataire_data in locataires_data:
                    locataire = Locataire.objects.create(
                        nom=locataire_data.get("lastName", ""),
                        prenom=locataire_data.get("firstName", ""),
                        email=locataire_data.get("email", ""),
                        caution_requise=locataire_data.get("cautionRequise", ""),
                        # Les autres champs ne sont pas fournis dans le formulaire
                    )
                    locataires.append(locataire)

                # 4. Créer le bail
                start_date_str = form_data.get("startDate", "")
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                modalites = form_data.get("modalites", {})
                solidaire_string = form_data.get("solidaires", "")
                solidaires = solidaire_string.lower() == "true"

                montant_loyer = Decimal(str(modalites.get("prix", 0)))
                is_meuble = bien.meuble
                depot_garantie = 2 * montant_loyer if is_meuble else montant_loyer

                # Calculer le rent_price_id si on est en zone tendue
                area_id = form_data.get("areaId")
                if area_id:
                    try:
                        rent_price: RentPrice = get_rent_price_for_bien(bien, area_id)
                        rent_price_id = rent_price.pk
                    except Exception as e:
                        logger.warning(f"Impossible de récupérer le RentPrice: {e}")
                else:
                    rent_price_id = None
                bail = BailSpecificites.objects.create(
                    bien=bien,
                    solidaires=solidaires,
                    date_debut=start_date,
                    montant_loyer=Decimal(str(modalites.get("prix", 0))),
                    type_charges=modalites.get("chargeType", ""),
                    montant_charges=Decimal(str(modalites.get("chargeAmount", 0))),
                    rent_price_id=rent_price_id,
                    depot_garantie=depot_garantie,
                    zone_tendue=form_data.get("zoneTendue", False),
                    justificatif_complement_loyer=modalites.get(
                        "justificationPrix", ""
                    ),
                    is_draft=True,  # Brouillon
                )

                # Associer les locataires au bail
                bail.locataires.set(locataires)

                return JsonResponse(
                    {
                        "success": True,
                        "bailId": bail.id,
                        "message": "Brouillon sauvegardé avec succès",
                    }
                )

        except OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                logger.warning(
                    f"Database locked, retry attempt {attempt + 1}/{max_retries}"
                )
                time.sleep(retry_delay * (2**attempt))  # Exponential backoff
                continue
            else:
                logger.exception(
                    "Erreur de base de données lors de la sauvegarde du brouillon"
                )
                return JsonResponse(
                    {"success": False, "error": f"Erreur de base de données: {str(e)}"},
                    status=500,
                )
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde du brouillon")
            return JsonResponse(
                {"success": False, "error": f"Erreur lors de la sauvegarde: {str(e)}"},
                status=500,
            )

    # Si on arrive ici, toutes les tentatives ont échoué
    return JsonResponse(
        {
            "success": False,
            "error": "Erreur de base de données persistante après plusieurs tentatives",
        },
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
    selon les caractéristiques complètes du bien du formulaire
    """
    try:
        data = request.data
        area_id = data.get("areaId")

        if not area_id:
            return JsonResponse({"error": "Area ID requis"}, status=400)

        # Créer un objet Bien temporaire avec les données du formulaire
        # en utilisant la même logique que save_draft

        bien = create_bien_from_form_data(data, save=False)

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
        unite_legale = etablissement.get("uniteLegale", {})
        adresse_etablissement = etablissement.get("adresseEtablissement", {})

        # Construire la réponse avec les données formatées
        company_data = {
            "raison_sociale": (
                unite_legale.get("denominationUniteLegale")
                or (
                    f"{unite_legale.get('prenom1UniteLegale', '')} "
                    f"{unite_legale.get('nomUniteLegale', '')}"
                ).strip()
                or None
            ),
            "forme_juridique": FORMES_JURIDIQUES.get(
                unite_legale.get("categorieJuridiqueUniteLegale"),
                unite_legale.get("categorieJuridiqueUniteLegale"),
            ),
            "adresse": {
                "numero": adresse_etablissement.get("numeroVoieEtablissement", ""),
                "voie": (
                    f"{adresse_etablissement.get('typeVoieEtablissement', '')} "
                    f"{adresse_etablissement.get('libelleVoieEtablissement', '')}"
                ).strip(),
                "code_postal": adresse_etablissement.get("codePostalEtablissement", ""),
                "ville": adresse_etablissement.get("libelleCommuneEtablissement", ""),
            },
        }

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
