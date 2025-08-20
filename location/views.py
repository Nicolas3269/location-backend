import json
import logging

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from location.models import (
    Bailleur,
    Bien,
    Locataire,
    Location,
    Personne,
    RentTerms,
    Societe,
)

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_or_update_location(request):
    """
    Créer ou mettre à jour une location avec les données minimales.
    Peut être appelé depuis bail, quittance ou état des lieux.

    Cette fonction est le point d'entrée central pour créer une Location,
    qui est l'entité pivot du système.
    """
    try:
        data = json.loads(request.body)
        source = data.get("source", "manual")  # bail, quittance, etat_lieux, manual

        # Si on a un location_id, on met à jour
        location_id = data.get("location_id")
        if location_id:
            try:
                location = Location.objects.get(id=location_id)
                return _update_location(location, data)
            except Location.DoesNotExist:
                pass  # Continuer avec la création

        # 1. Créer le bien (sera associé aux bailleurs plus tard)
        bien = Bien.objects.create(
            adresse=data.get("adresse", ""),
            type_bien=data.get("typeBien", "appartement"),
            superficie=data.get("superficie", 1),  # Valeur par défaut minimale
            regime_juridique=data.get("regimeJuridique", "monopropriete"),
            dernier_etage=data.get("dernierEtage", False),
            meuble=data.get("meuble", False),
            classe_dpe=data.get("classeDpe", "NA"),
        )
        logger.info(f"Bien créé: {bien.id}")

        # 2. Créer les personnes (bailleur)
        landlord_data = data.get("landlord", {})
        bailleur_type = data.get("bailleurType", "physique")

        if bailleur_type == "morale":
            # Créer la société
            societe_data = data.get("societe", {})
            societe = Societe.objects.create(
                raison_sociale=societe_data.get("raisonSociale", ""),
                forme_juridique=societe_data.get("formeJuridique", ""),
                siret=data.get("siret", ""),
                adresse=societe_data.get("adresse", ""),
                email=landlord_data.get("email", ""),
            )

            # Créer le signataire
            personne_signataire = Personne.objects.create(
                nom=landlord_data.get("lastName", ""),
                prenom=landlord_data.get("firstName", ""),
                email=landlord_data.get("email", ""),
                adresse=landlord_data.get("address", ""),
            )

            bailleur = Bailleur.objects.create(
                societe=societe,
                signataire=personne_signataire,
            )
        else:
            # Créer la personne physique
            personne_bailleur = Personne.objects.create(
                nom=landlord_data.get("lastName", ""),
                prenom=landlord_data.get("firstName", ""),
                email=landlord_data.get("email", ""),
                adresse=landlord_data.get("address", ""),
            )

            bailleur = Bailleur.objects.create(
                personne=personne_bailleur,
                signataire=personne_bailleur,  # Pour une personne physique, elle est son propre signataire
            )

        logger.info(f"Bailleur créé: {bailleur.id}")

        # Associer le bailleur principal au bien
        bien.bailleurs.add(bailleur)

        # Ajouter les autres bailleurs si présents
        other_landlords = data.get("otherLandlords", [])
        for other_data in other_landlords:
            personne_autre = Personne.objects.create(
                nom=other_data.get("lastName", ""),
                prenom=other_data.get("firstName", ""),
                email=other_data.get("email", ""),
                adresse=other_data.get("address", ""),
            )

            autre_bailleur = Bailleur.objects.create(
                personne=personne_autre,
                signataire=personne_autre,
            )
            bien.bailleurs.add(autre_bailleur)

        # 3. Créer les locataires
        locataires_data = data.get("locataires", [])
        locataires = []

        for idx, loc_data in enumerate(locataires_data):
            locataire = Locataire.objects.create(
                nom=loc_data.get("lastName", ""),
                prenom=loc_data.get("firstName", ""),
                email=loc_data.get("email", ""),
                adresse=loc_data.get("address", ""),
            )
            locataires.append(locataire)
            logger.info(f"Locataire créé: {locataire.id}")

        # 4. Créer la Location (entité pivot)
        location = Location.objects.create(
            bien=bien,
            created_from=source,  # bail, quittance, etat_lieux, manual
            date_debut=data.get("dateDebut"),
            date_fin=data.get("dateFin"),
            solidaires=data.get("solidaires", False),
        )

        # Associer les locataires à la location
        for locataire in locataires:
            location.locataires.add(locataire)

        # Ajouter les garants si présents
        garants_data = data.get("garants", [])
        for garant_data in garants_data:
            garant = Personne.objects.create(
                nom=garant_data.get("lastName", ""),
                prenom=garant_data.get("firstName", ""),
                email=garant_data.get("email", ""),
                adresse=garant_data.get("address", ""),
            )
            location.garants.add(garant)

        # 5. Créer les conditions financières (RentTerms) si fournies
        modalites = data.get("modalites", {})
        if modalites:
            rent_terms = RentTerms.objects.create(
                location=location,
                montant_loyer=modalites.get("prix", 0),
                montant_charges=modalites.get("charges", 0),
                type_charges=modalites.get("typeCharges", "FORFAITAIRES"),
                depot_garantie=modalites.get("depotGarantie", 0),
                jour_paiement=modalites.get("jourPaiement", 5),
                zone_tendue=modalites.get("zoneTendue", False),
                permis_de_louer=modalites.get("permisDeLouer", False),
                rent_price_id=modalites.get("rentPriceId"),
                justificatif_complement_loyer=modalites.get(
                    "justificatifComplementLoyer", ""
                ),
            )

        logger.info(f"Location créée avec succès: {location.id}")

        return JsonResponse(
            {
                "success": True,
                "location_id": str(location.id),
                "bien_id": bien.id,
                "message": f"Location créée avec succès depuis {source}",
            }
        )

    except Exception as e:
        logger.error(f"Erreur lors de la création de la location: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_bien_locations(request, bien_id):
    """
    Récupère toutes les locations d'un bien spécifique avec leurs baux associés
    """
    try:
        # Récupérer le bien
        bien = Bien.objects.get(id=bien_id)

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

        # Récupérer toutes les locations du bien
        locations = Location.objects.filter(bien=bien).order_by("-created_at")

        locations_data = []
        for location in locations:
            # Récupérer les locataires
            locataires = [
                {
                    "nom": locataire.nom,
                    "prenom": locataire.prenom,
                    "email": locataire.email,
                }
                for locataire in location.locataires.all()
            ]

            # Récupérer les baux associés à cette location
            from bail.models import Bail

            baux = Bail.objects.filter(location=location).order_by("-version")

            # Récupérer le bail actif s'il existe
            bail_actif = baux.filter(is_active=True).first()

            # Déterminer le statut global
            status = bail_actif.status if bail_actif else "draft"
            signatures_completes = True
            pdf_url = None
            latest_pdf_url = None

            if bail_actif:
                signatures_completes = not bail_actif.signature_requests.filter(
                    signed=False
                ).exists()

                from backend.pdf_utils import get_pdf_iframe_url

                pdf_url = (
                    get_pdf_iframe_url(request, bail_actif.pdf)
                    if bail_actif.pdf
                    else None
                )
                latest_pdf_url = (
                    get_pdf_iframe_url(request, bail_actif.latest_pdf)
                    if bail_actif.latest_pdf
                    else None
                )

            # Récupérer les montants depuis RentTerms
            montant_loyer = 0
            montant_charges = 0
            depot_garantie = 0
            if hasattr(location, "rent_terms"):
                montant_loyer = float(location.rent_terms.montant_loyer or 0)
                montant_charges = float(location.rent_terms.montant_charges or 0)
                depot_garantie = float(location.rent_terms.depot_garantie or 0)

            location_data = {
                "id": str(location.id),
                "date_debut": location.date_debut.isoformat()
                if location.date_debut
                else None,
                "date_fin": location.date_fin.isoformat()
                if location.date_fin
                else None,
                "montant_loyer": montant_loyer,
                "montant_charges": montant_charges,
                "depot_garantie": depot_garantie,
                "status": status,
                "locataires": locataires,
                "nombre_baux": baux.count(),
                "bail_actif_id": bail_actif.id if bail_actif else None,
                "signatures_completes": signatures_completes,
                "pdf_url": pdf_url,
                "latest_pdf_url": latest_pdf_url,
                "created_at": location.created_at.isoformat()
                if location.created_at
                else None,
                "created_from": location.created_from,
            }

            locations_data.append(location_data)

        return JsonResponse(
            {
                "success": True,
                "bien": {
                    "id": bien.id,
                    "adresse": bien.adresse,
                    "type": bien.get_type_bien_display(),
                    "superficie": float(bien.superficie),
                    "meuble": bien.meuble,
                },
                "locations": locations_data,
                "count": len(locations_data),
            }
        )

    except Bien.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": f"Bien {bien_id} introuvable"}, status=404
        )
    except Exception as e:
        logger.error(
            f"Erreur lors de la récupération des locations du bien {bien_id}: {str(e)}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def _update_location(location, data):
    """
    Met à jour une location existante avec de nouvelles données
    """
    try:
        # Mettre à jour les dates si fournies
        if "dateDebut" in data:
            location.date_debut = data["dateDebut"]
        if "dateFin" in data:
            location.date_fin = data["dateFin"]
        if "solidaires" in data:
            location.solidaires = data["solidaires"]

        location.save()

        # Mettre à jour les conditions financières si elles existent
        modalites = data.get("modalites", {})
        if modalites and hasattr(location, "rent_terms"):
            rent_terms = location.rent_terms
            if "prix" in modalites:
                rent_terms.montant_loyer = modalites["prix"]
            if "charges" in modalites:
                rent_terms.montant_charges = modalites["charges"]
            if "typeCharges" in modalites:
                rent_terms.type_charges = modalites["typeCharges"]
            if "depotGarantie" in modalites:
                rent_terms.depot_garantie = modalites["depotGarantie"]
            rent_terms.save()

        return JsonResponse(
            {
                "success": True,
                "location_id": str(location.id),
                "message": "Location mise à jour avec succès",
            }
        )
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de la location: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_location_documents(request, location_id):
    """
    Récupère tous les documents associés à une location spécifique:
    - Bail(s)
    - Quittances
    - États des lieux (entrée et sortie)
    """
    try:
        # Récupérer la location
        location = Location.objects.get(id=location_id)

        # Vérifier que l'utilisateur a accès à cette location
        user_email = request.user.email
        has_access = False

        # Vérifier si l'utilisateur est signataire d'un des bailleurs du bien
        for bailleur in location.bien.bailleurs.all():
            if bailleur.signataire and bailleur.signataire.email == user_email:
                has_access = True
                break

        # Vérifier si l'utilisateur est un des locataires
        if not has_access:
            for locataire in location.locataires.all():
                if locataire.email == user_email:
                    has_access = True
                    break

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à cette location"}, status=403
            )

        documents = []

        # 1. Récupérer les baux associés à cette location
        from bail.models import Bail

        baux = Bail.objects.filter(location=location).order_by("-version")

        for bail in baux:
            if bail.pdf or bail.latest_pdf:
                from backend.pdf_utils import get_pdf_iframe_url

                # Déterminer le statut du bail
                status = "Signé" if bail.status == "signed" else "En cours"
                if bail.status == "draft":
                    status = "Brouillon"

                documents.append(
                    {
                        "id": f"bail-{bail.id}",
                        "type": "bail",
                        "nom": f"Bail v{bail.version} - {', '.join([f'{l.prenom} {l.nom}' for l in location.locataires.all()])}",
                        "date": bail.date_signature.isoformat()
                        if bail.date_signature
                        else bail.created_at.isoformat(),
                        "url": get_pdf_iframe_url(request, bail.latest_pdf)
                        if bail.latest_pdf
                        else get_pdf_iframe_url(request, bail.pdf),
                        "status": status,
                        "version": bail.version,
                        "is_active": bail.is_active,
                    }
                )

        # 2. Récupérer les quittances
        from quittance.models import Quittance

        quittances = Quittance.objects.filter(location=location).order_by(
            "-annee", "-mois"
        )

        for quittance in quittances:
            if quittance.pdf:
                from backend.pdf_utils import get_pdf_iframe_url

                documents.append(
                    {
                        "id": f"quittance-{quittance.id}",
                        "type": "quittance",
                        "nom": f"Quittance - {quittance.mois} {quittance.annee}",
                        "date": quittance.date_paiement.isoformat()
                        if quittance.date_paiement
                        else quittance.created_at.isoformat(),
                        "url": get_pdf_iframe_url(request, quittance.pdf),
                        "status": "Émise",
                        "periode": f"{quittance.mois} {quittance.annee}",
                    }
                )

        # 3. Récupérer les états des lieux
        from etat_lieux.models import EtatLieux

        etats_lieux = EtatLieux.objects.filter(location=location).order_by(
            "-date_etat_lieux"
        )

        for etat in etats_lieux:
            if etat.pdf or etat.latest_pdf:
                from backend.pdf_utils import get_pdf_iframe_url

                type_doc = (
                    "etat_lieux_entree"
                    if etat.type_etat_lieux == "entree"
                    else "etat_lieux_sortie"
                )
                type_label = (
                    "d'entrée" if etat.type_etat_lieux == "entree" else "de sortie"
                )
                nom = f"État des lieux {type_label}"

                # Déterminer le statut via les signatures
                has_signatures = etat.signature_requests.exists()
                all_signed = (
                    not etat.signature_requests.filter(signed=False).exists()
                    if has_signatures
                    else False
                )

                if not has_signatures:
                    status = "Brouillon"
                elif all_signed:
                    status = "Signé"
                else:
                    status = "En cours"

                documents.append(
                    {
                        "id": f"etat-{etat.id}",
                        "type": type_doc,
                        "nom": nom,
                        "date": etat.date_etat_lieux.isoformat()
                        if etat.date_etat_lieux
                        else etat.created_at.isoformat(),
                        "url": get_pdf_iframe_url(request, etat.latest_pdf)
                        if etat.latest_pdf
                        else get_pdf_iframe_url(request, etat.pdf),
                        "status": status,
                    }
                )

        # Informations sur la location
        location_info = {
            "id": str(location.id),
            "bien": {
                "id": location.bien.id,
                "adresse": location.bien.adresse,
                "type": location.bien.get_type_bien_display(),
            },
            "locataires": [
                {
                    "nom": locataire.nom,
                    "prenom": locataire.prenom,
                    "email": locataire.email,
                }
                for locataire in location.locataires.all()
            ],
            "date_debut": location.date_debut.isoformat()
            if location.date_debut
            else None,
            "date_fin": location.date_fin.isoformat() if location.date_fin else None,
        }

        # Ajouter les informations financières si disponibles
        if hasattr(location, "rent_terms"):
            location_info["montant_loyer"] = float(
                location.rent_terms.montant_loyer or 0
            )
            location_info["montant_charges"] = float(
                location.rent_terms.montant_charges or 0
            )

        return JsonResponse(
            {
                "success": True,
                "location": location_info,
                "documents": documents,
                "count": len(documents),
            }
        )

    except Location.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": f"Location {location_id} introuvable"},
            status=404,
        )
    except Exception as e:
        logger.error(
            f"Erreur lors de la récupération des documents de la location {location_id}: {str(e)}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)
