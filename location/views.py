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
