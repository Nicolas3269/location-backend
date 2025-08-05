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

from bail.models import Bailleur, BailSpecificites, Locataire

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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_quittance_pdf(request):
    """
    Génère une quittance de loyer en PDF à partir des données du bail et des informations complémentaires
    """
    try:
        # Récupérer les données JSON
        data = json.loads(request.body)

        bail_id = data.get("bail_id")
        mois = data.get("mois")  # Format: "janvier", "février", etc.
        annee = data.get("annee")  # Format: 2025
        date_paiement = data.get("date_paiement")  # Format: "2025-01-15"

        # Validation des données requises
        if not bail_id:
            return JsonResponse(
                {"success": False, "error": "bail_id est requis"}, status=400
            )

        if not mois or not annee:
            return JsonResponse(
                {"success": False, "error": "mois et annee sont requis"}, status=400
            )

        if not date_paiement:
            return JsonResponse(
                {"success": False, "error": "date_paiement est requise"}, status=400
            )

        # Récupérer le bail
        try:
            bail = (
                BailSpecificites.objects.select_related("bien", "mandataire")
                .prefetch_related("locataires", "bien__bailleurs")
                .get(id=bail_id)
            )
        except BailSpecificites.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": f"Bail {bail_id} introuvable"}, status=404
            )

        # Convertir la date de paiement
        try:
            date_paiement_obj = datetime.strptime(date_paiement, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Format de date_paiement invalide (attendu: YYYY-MM-DD)",
                },
                status=400,
            )

        # Préparer les données pour le template
        montant_loyer = float(bail.montant_loyer)
        montant_en_lettres = amount_to_words_french(montant_loyer)

        # Récupérer le premier bailleur et le premier locataire
        premier_bailleur: Bailleur = bail.bien.bailleurs.first()
        premier_locataire: Locataire = bail.locataires.first()

        if not premier_bailleur:
            return JsonResponse(
                {"success": False, "error": "Aucun bailleur trouvé pour ce bail"},
                status=400,
            )

        if not premier_locataire:
            return JsonResponse(
                {"success": False, "error": "Aucun locataire trouvé pour ce bail"},
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

        # Supprimer les anciennes quittances pour la même période
        anciennes_quittances = Quittance.objects.filter(
            bail=bail, mois=mois, annee=annee
        )

        if anciennes_quittances.exists():
            count = anciennes_quittances.count()
            logger.info(
                f"Suppression de {count} ancienne(s) quittance(s) "
                f"pour {mois} {annee} du bail {bail_id}"
            )
            # Supprimer les fichiers PDF associés
            for ancienne_quittance in anciennes_quittances:
                if ancienne_quittance.pdf:
                    try:
                        ancienne_quittance.pdf.delete(save=False)
                    except Exception as e:
                        logger.warning(
                            f"Impossible de supprimer le PDF de la quittance "
                            f"{ancienne_quittance.id}: {e}"
                        )
            # Supprimer les objets
            anciennes_quittances.delete()

        # Créer l'objet Quittance
        quittance = Quittance.objects.create(
            bail=bail,
            mois=mois,
            annee=annee,
            date_paiement=date_paiement_obj,
            montant_loyer=montant_loyer,
        )

        # Générer la signature automatique (signataire qui signe)
        signature_data_url = generate_text_signature(signataire_full_name)

        context = {
            "bail": bail,
            "quittance": quittance,
            "mois": mois,
            "annee": annee,
            "date_paiement": date_paiement_obj,
            "date_generation": timezone.now().date(),
            "montant_loyer": montant_loyer,
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
            "adresse_bien": bail.bien.adresse,
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
