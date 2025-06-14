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

from bail.generate_bail.mapping import BailMapping
from bail.models import (
    BailSignatureRequest,
    BailSpecificites,
    Bien,
    Locataire,
    Proprietaire,
)
from bail.utils import (
    create_signature_requests,
    process_signature,
    send_signature_email,
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

        # Récupérer le bail existant
        from bail.models import BailSpecificites

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
                "prix_majore": BailMapping.prix_majore(bail),
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
            # prepare_pdf_with_signature_fields(tmp_pdf_path, bail)
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
                file_url = request.build_absolute_uri(bail.dpe_pdf.url)
            except BailSpecificites.DoesNotExist:
                logger.warning(f"Bail avec l'ID {bail_id} introuvable")
                # Fallback si le bail n'existe pas
                file_path = f"bail_pdfs/{filename}"
                saved_path = default_storage.save(file_path, dpe_file)
                file_url = request.build_absolute_uri(default_storage.url(saved_path))
        else:
            # Fallback pour les cas sans bail_id
            file_path = f"bail_pdfs/{filename}"
            saved_path = default_storage.save(file_path, dpe_file)
            file_url = request.build_absolute_uri(default_storage.url(saved_path))

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
                # Calculer le nombre de pièces principales
                pieces = form_data.get("pieces", {})
                chambres = pieces.get("chambres", 0)
                salons = pieces.get("salons", 0)
                nombre_pieces_principales = chambres + salons

                # Mapper le nombre de pièces au choix du modèle
                if nombre_pieces_principales == 1:
                    nb_pieces = "1"
                elif nombre_pieces_principales == 2:
                    nb_pieces = "2"
                elif nombre_pieces_principales == 3:
                    nb_pieces = "3"
                else:
                    nb_pieces = "4"  # 4 pièces et plus

                # Mapper la période de construction
                periode_construction_map = {
                    "avant_1946": "avant 1946",
                    "1946_1970": "1946-1970",
                    "1971_1990": "1971-1990",
                    "apres_1990": "apres 1990",
                }
                periode_construction = periode_construction_map.get(
                    form_data.get("periodeConstruction", ""), "avant 1946"
                )

                # Mapper le type de logement
                type_logement_map = {
                    "appartement": "appartement",
                    "maison": "maison",
                }
                type_bien = type_logement_map.get(
                    form_data.get("typeLogement", ""), "appartement"
                )

                # Mapper le meublé
                meuble_map = {
                    "meuble": True,
                    "vide": False,
                }
                meuble = meuble_map.get(form_data.get("meuble", "vide"), False)

                # Extract DPE expenses if provided
                dpe_grade = form_data.get("dpeGrade", "NA")
                depenses_energetiques = form_data.get("depensesDPE", "").lower()

                # Extract autre energies if needed
                chauffage_energie = form_data.get("chauffage", {}).get("energie", "")
                if chauffage_energie == "autre":
                    chauffage_energie = form_data.get("chauffage", {}).get(
                        "autreDetail", ""
                    )
                eau_chaude_energie = form_data.get("eauChaude", {}).get("energie", "")
                if eau_chaude_energie == "autre":
                    eau_chaude_energie = form_data.get("eauChaude", {}).get(
                        "autreDetail", ""
                    )

                bien = Bien.objects.create(
                    adresse=form_data.get("adresse", ""),
                    identifiant_fiscal=form_data.get("identificationFiscale", ""),
                    regime_juridique=form_data.get("regimeJuridique", ""),
                    type_bien=type_bien,
                    etage=form_data.get("etage", ""),
                    porte=form_data.get("porte", ""),
                    periode_construction=periode_construction,
                    superficie=Decimal(str(form_data.get("surface", 0))),
                    nb_pieces=nb_pieces,
                    meuble=meuble,
                    classe_dpe=dpe_grade,
                    depenses_energetiques=depenses_energetiques,
                    annexes_privatives=form_data.get("annexes", []),
                    annexes_collectives=form_data.get("annexesCollectives", []),
                    information=form_data.get("information", []),
                    pieces_info=form_data.get("pieces", {}),
                    chauffage_type=form_data.get("chauffage", {}).get("type", ""),
                    chauffage_energie=chauffage_energie,
                    eau_chaude_type=form_data.get("eauChaude", {}).get("type", ""),
                    eau_chaude_energie=eau_chaude_energie,
                )

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

                prix_reference = 1000

                bail = BailSpecificites.objects.create(
                    bien=bien,
                    solidaires=solidaires,
                    date_debut=start_date,
                    montant_loyer=Decimal(str(modalites.get("prix", 0))),
                    type_charges=modalites.get("chargeType", ""),
                    montant_charges=Decimal(str(modalites.get("chargeAmount", 0))),
                    prix_reference=Decimal(
                        str(prix_reference)
                    ),  # Prix de référence pour le calcul
                    # Par défaut égal au loyer
                    depot_garantie=depot_garantie,
                    zone_tendue=form_data.get("zoneTendue", False),
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
