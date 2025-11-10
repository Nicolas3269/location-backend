"""
Vues pour l'espace mandataire
"""

import logging
from collections import defaultdict

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# Compter les bails actifs
from bail.models import Bail
from location.models import Bailleur, Bien, Location, Mandataire, RentTerms
from signature.document_status import DocumentStatus

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_mandataire_bailleurs(request):
    """
    Récupère la liste des bailleurs gérés par le mandataire connecté.

    Retourne un tableau de bailleurs avec leurs biens.
    """
    user = request.user

    # Trouver tous les mandataires de l'utilisateur connecté
    # Un signataire peut signer pour plusieurs agences
    mandataires = Mandataire.objects.filter(signataire__email=user.email)

    if not mandataires.exists():
        return Response(
            {"success": False, "error": "Aucun mandataire trouvé pour cet utilisateur"},
            status=404,
        )

    # Récupérer toutes les locations gérées par ces mandataires
    locations = Location.objects.filter(mandataire__in=mandataires).select_related(
        "bien"
    )

    # Grouper les biens par bailleur
    # Structure: {bailleur_id: {bailleur_info, biens: []}}
    bailleurs_dict = defaultdict(lambda: {"bailleur": None, "biens": []})

    for location in locations:
        bien: Bien = location.bien

        # Un bien peut avoir plusieurs bailleurs (copropriété, indivision)
        for bailleur_obj in bien.bailleurs.all():
            bailleur: Bailleur = bailleur_obj
            bailleur_id = str(bailleur.id)

            # Si c'est la première fois qu'on rencontre ce bailleur
            if bailleurs_dict[bailleur_id]["bailleur"] is None:
                bailleurs_dict[bailleur_id]["bailleur"] = {
                    "id": bailleur_id,
                    "nom": bailleur.full_name,
                    "type": bailleur.bailleur_type,  # "physique" ou "morale"
                }

            # Ajouter le bien (si pas déjà présent)
            bien_id = str(bien.id)
            if not any(
                b["id"] == bien_id for b in bailleurs_dict[bailleur_id]["biens"]
            ):
                # Compter les locations pour ce bien
                nombre_locations = Location.objects.filter(bien=bien).count()

                baux_actifs = Bail.objects.filter(
                    location__bien=bien, status=DocumentStatus.SIGNED
                ).count()

                bailleurs_dict[bailleur_id]["biens"].append(
                    {
                        "id": bien_id,
                        "adresse": bien.adresse,
                        "type_bien": bien.type_bien,
                        "superficie": bien.superficie,
                        "meuble": bien.meuble,
                        "nombre_baux": nombre_locations,
                        "baux_actifs": baux_actifs,
                    }
                )

    # Convertir le dictionnaire en liste
    bailleurs_list = []
    for bailleur_data in bailleurs_dict.values():
        bailleurs_list.append(
            {
                "id": bailleur_data["bailleur"]["id"],
                "nom": bailleur_data["bailleur"]["nom"],
                "type": bailleur_data["bailleur"]["type"],
                "nombre_biens": len(bailleur_data["biens"]),
                "biens": bailleur_data["biens"],
            }
        )

    # Trier par nom
    bailleurs_list.sort(key=lambda x: x["nom"])

    return Response({"success": True, "bailleurs": bailleurs_list})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_mandataire_bailleur_detail(request, bailleur_id):
    """
    Récupère les détails d'un bailleur spécifique avec ses biens.

    Vérifie que le mandataire connecté a bien accès à ce bailleur.
    """
    user = request.user

    # Trouver tous les mandataires de l'utilisateur connecté
    # Un signataire peut signer pour plusieurs agences
    mandataires = Mandataire.objects.filter(signataire__email=user.email)

    if not mandataires.exists():
        raise ValueError("Aucun mandataire trouvé pour cet utilisateur")

    try:
        bailleur = Bailleur.objects.get(id=bailleur_id)
    except Bailleur.DoesNotExist:
        raise ValueError("Le bailleur spécifié est introuvable")

    # Vérifier que ces mandataires gèrent au moins un bien de ce bailleur
    biens_geres = Bien.objects.filter(
        bailleurs=bailleur, locations__mandataire__in=mandataires
    ).distinct()

    if not biens_geres.exists():
        raise ValueError("Vous n'avez pas accès à ce bailleur")
    # Liste des biens
    biens_list = []
    for bien in biens_geres:
        nombre_locations = Location.objects.filter(bien=bien).count()
        baux_actifs = Bail.objects.filter(
            location__bien=bien, status=DocumentStatus.SIGNED
        ).count()

        biens_list.append(
            {
                "id": str(bien.id),
                "adresse": bien.adresse,
                "type_bien": bien.type_bien,
                "superficie": bien.superficie,
                "meuble": bien.meuble,
                "nombre_baux": nombre_locations,
                "baux_actifs": baux_actifs,
            }
        )

    return Response(
        {
            "success": True,
            "bailleur": {
                "id": str(bailleur.id),
                "nom": bailleur.full_name,
                "type": bailleur.bailleur_type,  # "physique" ou "morale"
            },
            "biens": biens_list,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_mandataire_bien_detail(request, bien_id):
    """
    Récupère les détails d'un bien géré par le mandataire.

    Retourne les mêmes données que l'endpoint bailleur, mais avec vérification
    que le mandataire connecté gère bien ce bien.
    """
    user = request.user

    # Trouver tous les mandataires de l'utilisateur connecté
    # Un signataire peut signer pour plusieurs agences
    mandataires = Mandataire.objects.filter(signataire__email=user.email)

    if not mandataires.exists():
        raise ValueError("Aucun mandataire trouvé pour cet utilisateur")
    # Vérifier que ce bien est bien géré par un de ces mandataires
    try:
        bien = Bien.objects.get(id=bien_id)
    except Bien.DoesNotExist:
        raise ValueError("Le bien spécifié est introuvable")
    # Vérifier que ces mandataires gèrent ce bien (via une location)
    if not Location.objects.filter(bien=bien, mandataire__in=mandataires).exists():
        raise ValueError("Vous n'avez pas accès à ce bien")

    # Récupérer toutes les locations pour ce bien

    locations_qs = Location.objects.filter(bien=bien).prefetch_related("locataires")
    locations_list = []

    for location_raw in locations_qs:
        location: Location = location_raw
        # Récupérer le bail le plus récent pour cette location
        bail = Bail.objects.filter(location=location).order_by("-created_at").first()

        locataires_data = [
            {
                "lastName": loc.lastName,
                "firstName": loc.firstName,
                "email": loc.email,
            }
            for loc in location.locataires.all()
        ]

        # Récupérer les informations financières depuis RentTerms
        rent_terms: RentTerms = getattr(location, "rent_terms", None)

        date_debut = location.date_debut.isoformat() if location.date_debut else None
        date_fin = location.date_fin.isoformat() if location.date_fin else None

        # Les montants sont dans RentTerms
        montant_loyer = (
            float(rent_terms.montant_loyer)
            if rent_terms and rent_terms.montant_loyer
            else 0
        )
        montant_charges = (
            float(rent_terms.montant_charges)
            if rent_terms and rent_terms.montant_charges
            else 0
        )
        depot = (
            float(rent_terms.depot_garantie)
            if rent_terms and rent_terms.depot_garantie
            else 0
        )

        bail_actif = (
            str(bail.id) if bail and bail.status == DocumentStatus.SIGNED else None
        )
        is_signed = bail.status == DocumentStatus.SIGNED if bail else False
        created = location.created_at.isoformat() if location.created_at else None

        location_data = {
            "id": str(location.id),
            "date_debut": date_debut,
            "date_fin": date_fin,
            "montant_loyer": montant_loyer,
            "montant_charges": montant_charges,
            "depot_garantie": depot,
            "locataires": locataires_data,
            "nombre_baux": Bail.objects.filter(location=location).count(),
            "bail_actif_id": bail_actif,
            "pdf_url": bail.pdf.url if bail and bail.pdf else None,
            "latest_pdf_url": bail.pdf.url if bail and bail.pdf else None,
            "status": bail.status if bail else "draft",
            "signatures_completes": is_signed,
            "created_at": created,
            "created_from": location.created_from,  # Valeur du champ du modèle
        }

        locations_list.append(location_data)

    # Données du bien
    bien_data = {
        "id": str(bien.id),
        "adresse": bien.adresse,
        "type": bien.type_bien,
        "superficie": float(bien.superficie) if bien.superficie else 0,
        "meuble": bien.meuble,
        "nombre_baux": Location.objects.filter(bien=bien).count(),
        "baux_actifs": Bail.objects.filter(
            location__bien=bien, status=DocumentStatus.SIGNED
        ).count(),
    }

    return Response(
        {
            "success": True,
            "bien": bien_data,
            "locations": locations_list,
        }
    )
