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

from location.models import Bailleur, Locataire

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
    Returns:
        quittance_id: L'ID de la quittance existante ou nouvellement créée
    """
    periode_quittance = validated_data.get("periode_quittance", {})
    mois = periode_quittance.get("mois")
    annee = periode_quittance.get("annee")
    date_paiement = validated_data.get("date_paiement")
    
    if not mois or not annee or not date_paiement:
        raise ValueError("mois, annee et date_paiement sont requis pour générer une quittance")
    
    # Convertir la date de paiement
    if isinstance(date_paiement, str):
        date_paiement_obj = datetime.strptime(date_paiement, "%Y-%m-%d").date()
    else:
        date_paiement_obj = date_paiement
    
    # Vérifier si une quittance existe déjà pour cette période
    existing_quittance = Quittance.objects.filter(
        location=location, mois=mois, annee=annee
    ).first()
    
    if existing_quittance:
        logger.info(f"Quittance existante trouvée: {existing_quittance.id}")
        # Mettre à jour la date de paiement si différente
        if existing_quittance.date_paiement != date_paiement_obj:
            existing_quittance.date_paiement = date_paiement_obj
            existing_quittance.save()
        return str(existing_quittance.id)
    
    # Créer une nouvelle quittance avec le statut DRAFT par défaut
    from signature.document_status import DocumentStatus
    quittance = Quittance.objects.create(
        location=location,
        mois=mois,
        annee=annee,
        date_paiement=date_paiement_obj,
        status=DocumentStatus.DRAFT,
    )
    
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

        if not quittance_id:
            return JsonResponse(
                {"success": False, "error": "quittance_id est requis"},
                status=400,
            )

        # Récupérer la quittance avec toutes les relations nécessaires
        try:
            quittance = Quittance.objects.select_related(
                "location__bien", "location__mandataire"
            ).prefetch_related(
                "location__locataires", "location__bien__bailleurs"
            ).get(id=quittance_id)
        except Quittance.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Quittance introuvable"}, status=404
            )

        # Toutes les informations sont déduites de la quittance
        location = quittance.location
        mois = quittance.mois
        annee = quittance.annee
        date_paiement_obj = quittance.date_paiement

        # Préparer les données pour le template
        # Récupérer le montant du loyer depuis RentTerms
        if hasattr(location, "rent_terms"):
            montant_loyer = float(location.rent_terms.montant_loyer)
        else:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Aucune condition financière trouvée pour cette location",
                },
                status=400,
            )
        montant_en_lettres = amount_to_words_french(montant_loyer)

        # Récupérer le premier bailleur et le premier locataire
        premier_bailleur: Bailleur = location.bien.bailleurs.first()
        premier_locataire: Locataire = location.locataires.first()

        if not premier_bailleur:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Aucun bailleur trouvé pour cette location",
                },
                status=400,
            )

        if not premier_locataire:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Aucun locataire trouvé pour cette location",
                },
                status=400,
            )

        # Déterminer qui signe et le texte approprié
        if premier_bailleur.personne:
            # Personne physique
            signataire_full_name = premier_bailleur.personne.full_name
            bailleur_type = "personne_physique"
            bailleur_adresse = premier_bailleur.personne.adresse
        elif premier_bailleur.societe and premier_bailleur.signataire:
            # Société avec signataire
            signataire_full_name = premier_bailleur.signataire.full_name
            bailleur_type = "societe"
            bailleur_adresse = premier_bailleur.societe.adresse
        else:
            return JsonResponse(
                {"success": False, "error": "Configuration de bailleur invalide"},
                status=400,
            )

        # Pas besoin de créer la quittance, elle existe déjà

        # Générer la signature automatique (signataire qui signe)
        signature_data_url = generate_text_signature(signataire_full_name)

        # Formater le montant du loyer (sans décimales si entier)
        if montant_loyer % 1 == 0:
            montant_loyer_formate = f"{int(montant_loyer)}"
        else:
            montant_loyer_formate = f"{montant_loyer:.2f}"

        context = {
            "location": location,
            "quittance": quittance,
            "mois": mois,
            "annee": annee,
            "date_paiement": date_paiement_obj,
            "date_generation": timezone.now().date(),
            "montant_loyer": montant_loyer_formate,
            "montant_en_lettres": montant_en_lettres,
            # Informations du bailleur
            "premier_bailleur": premier_bailleur,
            "bailleur_type": bailleur_type,
            "signataire_full_name": signataire_full_name,
            "bailleur_adresse": bailleur_adresse,
            "bailleur_signature": signature_data_url,
            # Informations du locataire
            "locataire_full_name": premier_locataire.full_name,
            # Adresse du bien loué
            "adresse_bien": location.bien.adresse,
        }

        # Générer le HTML depuis le template
        html = render_to_string("pdf/quittance.html", context)

        # Générer le PDF
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()

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
            quittance.status = DocumentStatus.SIGNED
            quittance.save(update_fields=["status"])
            logger.info(f"Quittance {quittance.id} passée en status SIGNED après génération du PDF")

        finally:
            # 3. Supprimer le fichier temporaire
            try:
                os.remove(tmp_pdf_path)
            except Exception as e:
                logger.warning(
                    f"Impossible de supprimer le fichier temporaire {tmp_pdf_path}: {e}"
                )

        return JsonResponse(
            {
                "success": True,
                "quittanceId": str(quittance.id),
                "pdfUrl": request.build_absolute_uri(quittance.pdf.url),
                "filename": pdf_filename,
                "bienId": location.bien.id,
                "context_info": {
                    "bailleur": f"{signataire_full_name}",
                    "locataire": f"{premier_locataire.full_name}",
                    "periode": f"{mois} {annee}",
                    "montant": f"{montant_loyer}€",
                },
            }
        )

    except Exception as e:
        logger.exception("Erreur lors de la génération de la quittance")
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la génération: {str(e)}"},
            status=500,
        )


# create_location_for_quittance supprimé - utiliser /location/create-or-update/ à la place
