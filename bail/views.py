import json
import logging
import os
import uuid

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from weasyprint import HTML

from authentication.utils import (
    generate_otp,
    get_tokens_for_user,
    set_refresh_token_cookie,
)
from backend.pdf_utils import get_pdf_iframe_url, get_static_pdf_iframe_url
from bail.constants import FORMES_JURIDIQUES
from bail.generate_bail.mapping import BailMapping
from bail.models import (
    Bailleur,
    BailSignatureRequest,
    BailSpecificites,
    Bien,
    Document,
    DocumentType,
    Locataire,
    Personne,
    Societe,
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
            "pdf/bail.html",
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
                # Ne pas envoyer d'email ici, juste retourner le token
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

    person = req.bailleur_signataire or req.locataire
    signer_email = person.email

    # Générer un nouvel OTP et l'envoyer par email

    new_otp = generate_otp()
    req.otp = new_otp
    req.otp_generated_at = timezone.now()  # Enregistrer l'horodatage
    req.save()

    # Envoyer l'OTP par email
    try:
        send_mail(
            subject="Code de vérification pour la signature de votre bail",
            message=(
                f"Votre code de vérification est : {new_otp}\n\n"
                "Ce code expire dans 10 minutes."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            # recipient_list=[person.email],
            recipient_list=["nicolas3269@gmail.com"],
        )
        logger.info(f"OTP envoyé par email à {signer_email}")
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'OTP à {signer_email}: {e}")
        # Continuer le processus même si l'email échoue
        pass

    # Préparer la réponse de base
    response_data = {
        "person": {
            "email": signer_email,
            "first_name": person.prenom,
            "last_name": person.nom,
        },
        "bail_id": req.bail.id,
        "otp_sent": True,  # Indiquer que l'OTP a été envoyé
    }

    # Tenter d'authentifier automatiquement l'utilisateur
    User = get_user_model()
    try:
        user = User.objects.get(email=signer_email)
        tokens = get_tokens_for_user(user)

        # Le refresh token sera placé en cookie, pas d'access token dans la réponse
        response_data["user"] = {"email": user.email}

        # Créer la réponse avec le refresh token en cookie
        response = JsonResponse(response_data)

        # Configurer le refresh token en cookie HttpOnly
        set_refresh_token_cookie(response, tokens["refresh"])

        logger.info(f"Auto-authentication successful for {signer_email}")
        return response

    except User.DoesNotExist:
        logger.info(f"No user account found for {signer_email}")
        # L'utilisateur n'a pas de compte, retourner sans authentification
        return JsonResponse(response_data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_signature_bail(request):
    try:
        data = json.loads(request.body)
        token = data.get("token")
        otp = data.get("otp")
        signature_data_url = data.get("signatureImage")

        sig_req = get_object_or_404(BailSignatureRequest, link_token=token)

        if sig_req.signed:
            return JsonResponse({"error": "Déjà signé"}, status=400)

        # Vérifier que l'OTP est valide (correct et non expiré)
        if not sig_req.is_otp_valid(otp):
            return JsonResponse({"error": "Code OTP invalide ou expiré"}, status=403)

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
        # Utiliser notre nouvelle route PDF pour iframe
        full_url = get_static_pdf_iframe_url(request, "bails/grille_vetuste.pdf")

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
                    "error": f"Type de document invalide. Types acceptés: {valid_types}",
                },
                status=400,
            )

        bail = get_object_or_404(BailSpecificites, id=bail_id)
        bien = bail.bien

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
                    "url": request.build_absolute_uri(document.url),
                    "type": document.get_type_document_display(),
                    "created_at": document.date_creation.isoformat(),
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

    def create_or_get_user(email, first_name, last_name):
        """Crée ou récupère un utilisateur, non vérifié par défaut"""
        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
                # L'utilisateur n'est pas vérifié initialement
                # Il sera vérifié lors de l'authentification automatique
            },
        )
        if created:
            logger.info(f"Créé nouvel utilisateur non vérifié: {email}")
        return user

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

                # 1. Créer les bailleurs
                # Bailleur principal
                landlord_data = form_data.get("landlord", {})
                bailleur_type = form_data.get("bailleurType", "physique")

                if bailleur_type == "morale":
                    # Créer la société
                    societe_data = form_data.get("societe", {})
                    societe = Societe.objects.create(
                        siret=form_data.get("siret", ""),
                        raison_sociale=societe_data.get("raisonSociale", ""),
                        forme_juridique=societe_data.get("formeJuridique", ""),
                        adresse=societe_data.get("adresse", ""),
                        email=societe_data.get("email", ""),
                    )

                    # Créer le signataire (personne physique) et son User
                    signataire_email = landlord_data.get("email", "")
                    create_or_get_user(
                        signataire_email,
                        landlord_data.get("firstName", ""),
                        landlord_data.get("lastName", ""),
                    )

                    signataire = Personne.objects.create(
                        nom=landlord_data.get("lastName", ""),
                        prenom=landlord_data.get("firstName", ""),
                        email=signataire_email,
                    )

                    # Créer le bailleur société
                    bailleur_principal = Bailleur.objects.create(
                        societe=societe, signataire=signataire
                    )
                else:
                    # Créer l'utilisateur pour la personne physique
                    landlord_email = landlord_data.get("email", "")
                    create_or_get_user(
                        landlord_email,
                        landlord_data.get("firstName", ""),
                        landlord_data.get("lastName", ""),
                    )

                    # Créer la personne physique
                    personne = Personne.objects.create(
                        nom=landlord_data.get("lastName", ""),
                        prenom=landlord_data.get("firstName", ""),
                        adresse=landlord_data.get("address", ""),
                        email=landlord_email,
                    )

                    # Créer le bailleur personne physique
                    bailleur_principal = Bailleur.objects.create(
                        personne=personne, signataire=personne
                    )

                # Bailleurs additionnels (pour l'instant, seulement personnes physiques)
                bailleurs = [bailleur_principal]
                other_landlords = form_data.get("otherLandlords", [])
                for landlord in other_landlords:
                    # Créer l'utilisateur pour le bailleur additionnel
                    additional_email = landlord.get("email", "")
                    create_or_get_user(
                        additional_email,
                        landlord.get("firstName", ""),
                        landlord.get("lastName", ""),
                    )

                    personne = Personne.objects.create(
                        nom=landlord.get("lastName", ""),
                        prenom=landlord.get("firstName", ""),
                        adresse=landlord.get("address", ""),
                        email=additional_email,
                    )
                    bailleur = Bailleur.objects.create(
                        personne=personne, signataire=personne
                    )
                    bailleurs.append(bailleur)

                # 2. Créer le bien
                bien = create_bien_from_form_data(form_data, save=True)

                # Associer les bailleurs au bien
                bien.bailleurs.set(bailleurs)

                # 3. Créer les locataires
                locataires_data = form_data.get("locataires", [])
                locataires = []
                for locataire_data in locataires_data:
                    # Créer l'utilisateur pour le locataire
                    locataire_email = locataire_data.get("email", "")
                    create_or_get_user(
                        locataire_email,
                        locataire_data.get("firstName", ""),
                        locataire_data.get("lastName", ""),
                    )

                    locataire = Locataire.objects.create(
                        nom=locataire_data.get("lastName", ""),
                        prenom=locataire_data.get("firstName", ""),
                        email=locataire_email,
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
                    permis_de_louer=form_data.get("permisDeLouer", False),
                    justificatif_complement_loyer=modalites.get(
                        "justificationPrix", ""
                    ),
                    status="draft",  # Brouillon
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_bien_detail(request, bien_id):
    """
    Récupère les détails d'un bien avec ses pièces pour l'état des lieux.
    Utilise le champ pieces_info JSONField existant.
    """
    try:
        # Récupérer le bien
        bien = get_object_or_404(Bien, id=bien_id)

        # Vérifier que l'utilisateur a accès à ce bien
        # L'utilisateur doit être le signataire d'un des bailleurs du bien
        # ou être un locataire d'un bail sur ce bien
        user_bails = BailSpecificites.objects.filter(bien=bien)
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
                if bail.locataires.filter(email=user_email).exists():
                    has_access = True
                    break

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à ce bien"}, status=403
            )

        # Convertir pieces_info en format de pièces pour le frontend
        pieces_data = []
        if bien.pieces_info:
            # pieces_info contient des données comme
            # {"chambres": 2, "salons": 1, "cuisines": 1, "sallesDeBain": 1}
            piece_counter = 1

            for piece_type, count in bien.pieces_info.items():
                if isinstance(count, int) and count > 0:
                    # Mapper les types de pièces du JSONField vers noms lisibles
                    type_mapping = {
                        "chambres": {"type": "bedroom", "nom_base": "Chambre"},
                        "salons": {"type": "living", "nom_base": "Salon"},
                        "cuisines": {"type": "kitchen", "nom_base": "Cuisine"},
                        "sallesDeBain": {
                            "type": "bathroom",
                            "nom_base": "Salle de bain",
                        },
                        "sallesEau": {"type": "bathroom", "nom_base": "Salle d'eau"},
                        "wc": {"type": "bathroom", "nom_base": "WC"},
                        "entrees": {"type": "room", "nom_base": "Entrée"},
                        "couloirs": {"type": "room", "nom_base": "Couloir"},
                        "dressings": {"type": "room", "nom_base": "Dressing"},
                        "celliers": {"type": "room", "nom_base": "Cellier"},
                        "buanderies": {"type": "room", "nom_base": "Buanderie"},
                    }

                    if piece_type in type_mapping:
                        mapping = type_mapping[piece_type]
                        for i in range(count):
                            nom = f"{mapping['nom_base']}"
                            if count > 1:
                                nom += f" {i + 1}"

                            pieces_data.append(
                                {
                                    "id": piece_counter,
                                    "nom": nom,
                                    "type": mapping["type"],
                                }
                            )
                            piece_counter += 1

        # Si aucune pièce n'est définie, créer des pièces par défaut
        if not pieces_data:
            pieces_data = [{"id": 1, "nom": "Pièce principale", "type": "room"}]

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

        # Récupérer tous les baux du bien
        baux = BailSpecificites.objects.filter(bien=bien).order_by("-date_debut")

        baux_data = []
        for bail in baux:
            # Récupérer les locataires
            locataires = [
                {
                    "nom": locataire.nom,
                    "prenom": locataire.prenom,
                    "email": locataire.email,
                }
                for locataire in bail.locataires.all()
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
                "date_debut": bail.date_debut.isoformat(),
                "date_fin": bail.date_fin.isoformat() if bail.date_fin else None,
                "montant_loyer": float(bail.montant_loyer),
                "montant_charges": float(bail.montant_charges),
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
