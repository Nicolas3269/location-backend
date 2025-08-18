import json
import logging

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from bail.models import (
    Bailleur,
    BailSpecificites,
    Bien,
    Locataire,
    Personne,
    Societe,
)

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_partial_bail(request):
    """
    Créer un bail partiel avec les données minimales nécessaires
    pour générer une quittance.
    Utilisé par le formulaire de quittance standalone.
    """
    try:
        data = json.loads(request.body)

        # 1. Créer le bien (sera associé aux bailleurs plus tard)
        bien = Bien.objects.create(
            adresse=data.get("adresse", ""),
            type_bien="appartement",  # Valeur par défaut
            superficie=1,  # Valeur par défaut minimale (1m² au lieu de 0)
            # Les autres champs obligatoires avec valeurs par défaut
            regime_juridique="monopropriete",
            dernier_etage=False,
            meuble=False,
            classe_dpe="NA",
        )
        logger.info(f"Bien partiel créé: {bien.id}")

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
            )

            # Créer le signataire
            personne_signataire = Personne.objects.create(
                nom=landlord_data.get("lastName", ""),
                prenom=landlord_data.get("firstName", ""),
                email=landlord_data.get("email", ""),
                # telephone=landlord_data.get("phone", ""),
            )

            bailleur = Bailleur.objects.create(
                # type_bailleur="societe",
                societe=societe,
                signataire=personne_signataire,
                # is_primary=True,
            )
        else:
            # Créer la personne physique
            personne_bailleur = Personne.objects.create(
                nom=landlord_data.get("lastName", ""),
                prenom=landlord_data.get("firstName", ""),
                email=landlord_data.get("email", ""),
                # telephone=landlord_data.get("phone", ""),
                adresse=landlord_data.get("address", ""),
            )

            bailleur = Bailleur.objects.create(
                # type_bailleur="personne_physique",
                personne=personne_bailleur,
                # is_primary=True,
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
                # telephone=other_data.get("phone", ""),
                adresse=other_data.get("address", ""),
            )

            autre_bailleur = Bailleur.objects.create(
                # type_bailleur="personne_physique",
                personne=personne_autre,
                # is_primary=False,
            )
            bien.bailleurs.add(autre_bailleur)

        # 3. Créer les locataires
        locataires_data = data.get("locataires", [])
        locataires = []

        for idx, loc_data in enumerate(locataires_data):
            locataire = Locataire.objects.create(
                nom=loc_data.get("lastName", ""),
                prenom=loc_data.get("firstName", ""),
                email=loc_data.get(
                    "email", ""
                ),  # Le premier est le locataire principal
            )
            locataires.append(locataire)
            logger.info(f"Locataire créé: {locataire.id}")

        # 4. Créer le bail avec les données minimales
        modalites = data.get("modalites", {})

        bail = BailSpecificites.objects.create(
            bien=bien,
            montant_loyer=modalites.get("prix", 0),
            montant_charges=modalites.get("charges", 0),
            type_charges="provisionnelles",
            depot_garantie=0,  # Valeur par défaut, pas de dépôt pour une quittance
            # Status de brouillon pour bail partiel
            status="draft",
            # Note: Les champs is_partial et source n'existent pas encore
            # Ils pourraient être ajoutés au modèle si nécessaire
        )

        # Associer les locataires au bail
        for locataire in locataires:
            bail.locataires.add(locataire)

        logger.info(f"Bail partiel créé avec succès: {bail.id}")

        return JsonResponse(
            {
                "success": True,
                "bail_id": bail.id,
                "bien_id": bien.id,
                "message": "Bail partiel créé avec succès",
            }
        )

    except Exception as e:
        logger.error(f"Erreur lors de la création du bail partiel: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
