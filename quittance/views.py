import json
import logging
import os
import uuid
from datetime import datetime

from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from num2words import num2words
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from weasyprint import HTML

from backend.pdf_utils import get_logo_pdf_base64_data_uri
from location.models import Bailleur, Locataire

# Déterminer le rôle de l'utilisateur pour la redirection (fonction factorisée)
from location.services.access_utils import get_user_role_for_location
from location.services.bailleur_utils import get_primary_bailleur_for_user
from signature.document_status import DocumentStatus

from .email_service import send_quittance_email as send_email
from .models import Quittance
from .signature_utils import generate_text_signature

logger = logging.getLogger(__name__)


def amount_to_words_french(amount):
    """
    Convertit un montant en euros en mots français avec num2words.
    Exemple: 650.50 -> "six cent cinquante euros et cinquante centimes"
    """
    euros = int(amount)
    centimes = int(round((amount - euros) * 100))

    # Convertir les euros en mots
    if euros == 0:
        euros_text = "zéro euro"
    elif euros == 1:
        euros_text = "un euro"
    else:
        euros_text = num2words(euros, lang="fr") + " euros"

    # Ajouter les centimes si nécessaire
    if centimes > 0:
        if centimes == 1:
            centimes_text = "un centime"
        else:
            centimes_text = num2words(centimes, lang="fr") + " centimes"
        return euros_text + " et " + centimes_text
    else:
        return euros_text


def get_or_create_quittance_for_location(location, validated_data):
    """
    Récupère ou crée une quittance pour une location.

    UNICITÉ : mois + année + combinaison exacte de locataires

    Exemples :
    - Janvier : Alice + Bob → Quittance 1
    - Janvier : Charlie → Quittance 2 (NOUVELLE, indépendante de la 1)
    - Janvier : Alice + Bob → Trouve Quittance 1 (mise à jour si nécessaire)

    Returns:
        quittance_id: L'ID de la quittance existante ou nouvellement créée
    """
    logger.info("=== get_or_create_quittance_for_location ===")
    logger.info(f"Location: {location.id}")
    logger.info(f"Validated data keys: {list(validated_data.keys())}")

    periode_quittance = validated_data.get("periode_quittance", {})
    mois = periode_quittance.get("mois")
    annee = periode_quittance.get("annee")
    date_paiement = validated_data.get("date_paiement")

    # Récupérer les montants depuis validated_data (champs à la racine du serializer)
    loyer_hors_charges = validated_data.get("loyer_hors_charges")
    charges = validated_data.get("charges")

    logger.info(f"Période: {mois} {annee}, Date paiement: {date_paiement}")
    logger.info(f"Montants: loyer={loyer_hors_charges}, charges={charges}")

    if not mois or not annee or not date_paiement:
        logger.error("Erreur: mois, annee ou date_paiement manquant")
        raise ValueError(
            "mois, annee et date_paiement sont requis pour générer une quittance"
        )

    if loyer_hors_charges is None or charges is None:
        logger.error(
            f"Erreur: loyer_hors_charges={loyer_hors_charges}, charges={charges}"
        )
        raise ValueError(
            "loyer_hors_charges et charges sont requis pour générer une quittance"
        )

    # Convertir la date de paiement
    if isinstance(date_paiement, str):
        date_paiement_obj = datetime.strptime(date_paiement, "%Y-%m-%d").date()
    else:
        date_paiement_obj = date_paiement

    # Déterminer les locataires concernés par cette quittance

    locataire_ids = validated_data.get("locataire_ids", [])

    if locataire_ids:
        # Récupérer les locataires sélectionnés
        locataires_selectionnes = list(Locataire.objects.filter(id__in=locataire_ids))
        locataires_ids_set = set(str(loc.id) for loc in locataires_selectionnes)
        logger.info(f"Locataires sélectionnés: {locataires_ids_set}")
    else:
        # Tous les locataires de la location
        locataires_selectionnes = list(location.locataires.all())
        locataires_ids_set = set(str(loc.id) for loc in locataires_selectionnes)
        logger.info(f"TOUS les locataires de la location: {locataires_ids_set}")

    # Chercher une quittance existante avec la MÊME combinaison de locataires
    # (pas juste location + mois, mais aussi la combinaison exacte de locataires)
    existing_quittances = Quittance.objects.filter(
        location=location, mois=mois, annee=annee
    ).prefetch_related("locataires")

    existing_quittance = None
    for quittance in existing_quittances:
        # Comparer les ensembles de locataires (ordre n'importe pas)
        quittance_locataires_ids = set(
            str(loc.id) for loc in quittance.locataires.all()
        )
        if quittance_locataires_ids == locataires_ids_set:
            existing_quittance = quittance
            logger.info(
                f"Quittance existante trouvée avec même combinaison de locataires: {existing_quittance.id}"
            )
            break

    if existing_quittance:
        # Mettre à jour les champs si différents
        updated = False
        if existing_quittance.date_paiement != date_paiement_obj:
            existing_quittance.date_paiement = date_paiement_obj
            updated = True
        if existing_quittance.montant_loyer != loyer_hors_charges:
            existing_quittance.montant_loyer = loyer_hors_charges
            updated = True
        if existing_quittance.montant_charges != charges:
            existing_quittance.montant_charges = charges
            updated = True

        if updated:
            existing_quittance.save()
            logger.info(f"Quittance mise à jour: {existing_quittance.id}")

        return str(existing_quittance.id)

    # Créer une nouvelle quittance avec le statut DRAFT par défaut

    quittance = Quittance.objects.create(
        location=location,
        mois=mois,
        annee=annee,
        date_paiement=date_paiement_obj,
        montant_loyer=loyer_hors_charges,
        montant_charges=charges,
        status=DocumentStatus.DRAFT,
    )

    # Associer les locataires
    if locataires_selectionnes:
        quittance.locataires.set(locataires_selectionnes)
        locataires_names = ", ".join(
            [f"{loc.firstName} {loc.lastName}" for loc in locataires_selectionnes]
        )
        logger.info(
            f"Quittance créée pour {len(locataires_selectionnes)} locataire(s): {locataires_names}"
        )
    else:
        logger.warning("Aucun locataire pour cette quittance")

    logger.info(f"Quittance créée: {quittance.id}")
    return str(quittance.id)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_quittance_pdf(request):
    """
    Génère une quittance de loyer en PDF à partir d'un quittance_id
    """
    try:
        # Récupérer les données JSON
        data = json.loads(request.body)
        quittance_id = data.get("quittance_id")

        logger.info(f"Génération PDF quittance - données reçues: {data}")
        logger.info(f"quittance_id extrait: {quittance_id}")

        if not quittance_id:
            logger.error("Erreur: quittance_id manquant dans la requête")
            return JsonResponse(
                {"success": False, "error": "quittance_id est requis"},
                status=400,
            )

        # Récupérer la quittance avec toutes les relations nécessaires
        try:
            quittance = (
                Quittance.objects.select_related(
                    "location__bien", "location__mandataire"
                )
                .prefetch_related("location__locataires", "location__bien__bailleurs")
                .get(id=quittance_id)
            )
            logger.info(f"Quittance trouvée: {quittance.id}")
        except Quittance.DoesNotExist:
            logger.error(f"Quittance introuvable: {quittance_id}")
            return JsonResponse(
                {"success": False, "error": "Quittance introuvable"}, status=404
            )

        # Toutes les informations sont déduites de la quittance
        location = quittance.location
        mois = quittance.mois
        annee = quittance.annee
        date_paiement_obj = quittance.date_paiement

        logger.info(
            f"Montants de la quittance: loyer={quittance.montant_loyer}, charges={quittance.montant_charges}"
        )

        # Préparer les données pour le template
        # Récupérer les montants depuis la Quittance (pas depuis RentTerms)
        if quittance.montant_loyer is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Le montant du loyer n'est pas défini pour cette quittance",
                },
                status=400,
            )

        montant_loyer_hc = float(quittance.montant_loyer)
        montant_charges = float(quittance.montant_charges or 0)
        montant_total = montant_loyer_hc + montant_charges
        montant_en_lettres = amount_to_words_french(montant_total)

        # Récupérer le bailleur (priorité au user connecté)
        premier_bailleur: Bailleur = get_primary_bailleur_for_user(
            location.bien.bailleurs, request.user
        )
        logger.info(f"Bailleur pour génération PDF: {premier_bailleur}")

        if not premier_bailleur:
            logger.error("Aucun bailleur trouvé pour cette location")
            return JsonResponse(
                {
                    "success": False,
                    "error": "Aucun bailleur trouvé pour cette location",
                },
                status=400,
            )

        # Récupérer les locataires de la quittance (toujours définis lors de la création/mise à jour)
        locataires = list(quittance.locataires.all())
        logger.info(f"{len(locataires)} locataire(s) pour cette quittance")

        if not locataires:
            logger.error(
                "Aucun locataire associé à cette quittance - données incohérentes"
            )
            return JsonResponse(
                {
                    "success": False,
                    "error": "Aucun locataire associé à cette quittance",
                },
                status=400,
            )

        # Déterminer qui signe et le texte approprié
        logger.info(
            f"Bailleur personne: {premier_bailleur.personne}, societe: {premier_bailleur.societe}, signataire: {premier_bailleur.signataire}"
        )
        if premier_bailleur.personne:
            # Personne physique
            signataire_full_name = premier_bailleur.personne.full_name
            bailleur_type = "personne_physique"
            bailleur_adresse = premier_bailleur.personne.adresse
            logger.info(
                f"Bailleur type: personne_physique, signataire: {signataire_full_name}"
            )
        elif premier_bailleur.societe and premier_bailleur.signataire:
            # Société avec signataire
            signataire_full_name = premier_bailleur.signataire.full_name
            bailleur_type = "societe"
            bailleur_adresse = premier_bailleur.societe.adresse
            logger.info(f"Bailleur type: societe, signataire: {signataire_full_name}")
        else:
            logger.error(
                "Configuration de bailleur invalide - ni personne ni societe+signataire"
            )
            return JsonResponse(
                {"success": False, "error": "Configuration de bailleur invalide"},
                status=400,
            )

        # Pas besoin de créer la quittance, elle existe déjà

        # Générer la signature automatique (signataire qui signe)
        signature_data_url = generate_text_signature(signataire_full_name)

        # Formater les montants (sans décimales si entier)
        def format_amount(amount):
            if amount % 1 == 0:
                return f"{int(amount)}"
            else:
                return f"{amount:.2f}"

        context = {
            "location": location,
            "quittance": quittance,
            "mois": mois,
            "annee": annee,
            "date_paiement": date_paiement_obj,
            "date_generation": timezone.now().date(),
            "montant_loyer_hc": format_amount(montant_loyer_hc),
            "montant_charges": format_amount(montant_charges),
            "montant_total": format_amount(montant_total),
            "montant_en_lettres": montant_en_lettres,
            # Informations du bailleur
            "premier_bailleur": premier_bailleur,
            "bailleur_type": bailleur_type,
            "signataire_full_name": signataire_full_name,
            "bailleur_adresse": bailleur_adresse,
            "bailleur_signature": signature_data_url,
            # Informations des locataires
            "locataires": locataires,
            "locataire_full_name": locataires[0].full_name
            if locataires
            else "",  # Pour compatibilité
            "nb_locataires": len(locataires),
            # Adresse du bien loué
            "adresse_bien": location.bien.adresse,
            # Logo
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
        }

        # Générer le HTML depuis le template (nouveau template factorisé)
        html = render_to_string("pdf/quittance/quittance.html", context)

        # Générer le PDF
        pdf_bytes = HTML(
            string=html,
            base_url=request.build_absolute_uri(),
        ).write_pdf()

        # Noms de fichiers
        base_filename = f"quittance_{quittance.id}_{uuid.uuid4().hex}"
        pdf_filename = f"{base_filename}.pdf"
        tmp_pdf_path = f"/tmp/{pdf_filename}"

        try:
            # 1. Sauver temporairement
            with open(tmp_pdf_path, "wb") as f:
                f.write(pdf_bytes)

            # 2. Recharger dans quittance.pdf
            with open(tmp_pdf_path, "rb") as f:
                quittance.pdf.save(pdf_filename, ContentFile(f.read()), save=True)

            # 3. Mettre à jour le statut vers SIGNED car la quittance n'a pas besoin de signature
            from signature.document_status import DocumentStatus

            quittance.status = DocumentStatus.SIGNED.value
            quittance.save(update_fields=["status"])
            logger.info(
                f"Quittance {quittance.id} passée en status SIGNED après génération du PDF"
            )

        finally:
            # 3. Supprimer le fichier temporaire
            try:
                os.remove(tmp_pdf_path)
            except Exception as e:
                logger.warning(
                    f"Impossible de supprimer le fichier temporaire {tmp_pdf_path}: {e}"
                )

        # Récupérer le bailleurId pour la redirection mandataire (priorité au user)
        bailleur = get_primary_bailleur_for_user(location.bien.bailleurs, request.user)
        response_data = {
            "success": True,
            "quittanceId": str(quittance.id),
            "pdfUrl": quittance.pdf.url,
            "filename": pdf_filename,
            "bienId": location.bien.id,
            "context_info": {
                "bailleur": f"{signataire_full_name}",
                "locataire": ", ".join([loc.full_name for loc in locataires]),
                "periode": f"{mois} {annee}",
                "montant": f"{montant_total}€",
            },
        }

        # Ajouter bailleurId pour la redirection mandataire vers /mon-compte/mes-mandats/{bailleurId}/biens/{bienId}
        if bailleur:
            response_data["bailleurId"] = str(bailleur.id)

        user_roles = get_user_role_for_location(location, request.user.email)
        response_data.update(user_roles)

        return JsonResponse(response_data)

    except Exception as e:
        logger.exception("Erreur lors de la génération de la quittance")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la génération: {str(e)}"},
            status=500,
        )


# create_location_for_quittance supprimé - utiliser /location/create-or-update/ à la place


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_quittance_email(request, quittance_id):
    """
    Envoie une quittance par email au locataire.

    POST /quittance/send-email/<quittance_id>/

    La quittance doit avoir un PDF généré (status SIGNED).
    """

    try:
        # Récupérer la quittance avec les relations nécessaires
        quittance = (
            Quittance.objects.select_related("location__bien")
            .prefetch_related("location__locataires", "location__bien__bailleurs")
            .get(id=quittance_id)
        )

        # Vérifier que la quittance a un PDF
        if not quittance.pdf:
            return JsonResponse(
                {"success": False, "error": "La quittance n'a pas de PDF généré"},
                status=400,
            )

        # Vérifier que l'utilisateur a accès (est bailleur ou mandataire)
        user_email = request.user.email
        is_bailleur = any(
            bailleur.email == user_email
            for bailleur in quittance.location.bien.bailleurs.all()
        )
        is_mandataire = (
            quittance.location.mandataire
            and quittance.location.mandataire.signataire.email == user_email
        )

        if not is_bailleur and not is_mandataire:
            return JsonResponse(
                {"success": False, "error": "Vous n'avez pas accès à cette quittance"},
                status=403,
            )

        # URL du PDF (déjà absolue car stocké sur S3/R2)
        pdf_url = quittance.pdf.url

        # Envoyer l'email (CC: l'expéditeur)
        success = send_email(quittance, pdf_url, user_email)

        if success:
            recipients = [loc.email for loc in quittance.location.locataires.all()]
            logger.info(f"Quittance {quittance_id} envoyée par email à {recipients}")
            return JsonResponse(
                {
                    "success": True,
                    "message": f"Quittance envoyée à {', '.join(recipients)}",
                    "recipients": recipients,
                }
            )
        else:
            logger.error(f"Échec de l'envoi de la quittance {quittance_id}")
            return JsonResponse(
                {"success": False, "error": "Échec de l'envoi de l'email"},
                status=500,
            )

    except Quittance.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Quittance introuvable"}, status=404
        )
    except Exception as e:
        logger.exception(f"Erreur lors de l'envoi de la quittance {quittance_id}")
        return JsonResponse(
            {"success": False, "error": f"Erreur: {str(e)}"}, status=500
        )
