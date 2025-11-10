"""
Utilitaires pour la sérialisation des modèles Location.
Centralise la logique de sérialisation pour éviter les duplications.
"""

from typing import Any, Dict, Optional

from bail.models import Bail
from location.models import Bien, Locataire, Location, RentTerms
from signature.document_status import DocumentStatus


def serialize_locataire_basic(locataire: Locataire) -> Dict[str, str]:
    """
    Sérialise un locataire en format API basique.

    Args:
        locataire: Instance de Locataire

    Returns:
        Dict avec lastName, firstName, email
    """
    return {
        "lastName": locataire.lastName,
        "firstName": locataire.firstName,
        "email": locataire.email,
    }


def serialize_rent_terms(rent_terms: Optional[RentTerms]) -> Dict[str, float]:
    """
    Extrait les montants financiers depuis RentTerms.

    Args:
        rent_terms: Instance de RentTerms (peut être None)

    Returns:
        Dict avec montant_loyer, montant_charges, depot_garantie (0.0 si None)
    """
    return {
        "montant_loyer": (float(rent_terms.montant_loyer or 0) if rent_terms else 0.0),
        "montant_charges": (
            float(rent_terms.montant_charges or 0) if rent_terms else 0.0
        ),
        "depot_garantie": (
            float(rent_terms.depot_garantie or 0) if rent_terms else 0.0
        ),
    }


def serialize_location_with_bail(location: Location) -> Dict[str, Any]:
    """
    Sérialise une location avec son bail actif, locataires et montants.

    Format unifié utilisé par :
    - get_bien_locations
    - get_mandataire_bien_detail
    - autres endpoints API

    Args:
        location: Instance de Location

    Returns:
        Dict avec toutes les données de la location + bail
    """
    # Récupérer le bail le plus récent
    bail = Bail.objects.filter(location=location).order_by("-created_at").first()

    # Sérialiser les locataires
    locataires_data = [
        serialize_locataire_basic(loc) for loc in location.locataires.all()
    ]

    # Extraire les montants financiers
    rent_data = serialize_rent_terms(getattr(location, "rent_terms", None))

    # Informations du bail
    bail_actif_id = None
    pdf_url = None
    status = "draft"
    signatures_completes = False

    if bail:
        if bail.status == DocumentStatus.SIGNED:
            bail_actif_id = str(bail.id)
        pdf_url = bail.pdf.url if bail.pdf else None
        status = bail.status
        signatures_completes = bail.status == DocumentStatus.SIGNED

    return {
        "id": str(location.id),
        "date_debut": location.date_debut.isoformat() if location.date_debut else None,
        "date_fin": location.date_fin.isoformat() if location.date_fin else None,
        "montant_loyer": rent_data["montant_loyer"],
        "montant_charges": rent_data["montant_charges"],
        "depot_garantie": rent_data["depot_garantie"],
        "locataires": locataires_data,
        "nombre_baux": Bail.objects.filter(location=location).count(),
        "bail_actif_id": bail_actif_id,
        "pdf_url": pdf_url,
        "latest_pdf_url": pdf_url,  # Alias pour compatibilité
        "status": status,
        "signatures_completes": signatures_completes,
        "created_at": location.created_at.isoformat() if location.created_at else None,
        "created_from": location.created_from,
    }


def serialize_bien_with_stats(bien: Bien) -> Dict[str, Any]:
    """
    Sérialise un bien avec ses statistiques (nombre de baux, baux actifs).

    Args:
        bien: Instance de Bien

    Returns:
        Dict avec les données du bien + statistiques
    """
    # Compter les locations et baux actifs
    nombre_baux = Location.objects.filter(bien=bien).count()
    baux_actifs = Bail.objects.filter(
        location__bien=bien, status=DocumentStatus.SIGNED
    ).count()

    return {
        "id": str(bien.id),
        "adresse": bien.adresse,
        "type_bien": bien.type_bien,
        "superficie": float(bien.superficie) if bien.superficie else 0.0,
        "meuble": bien.meuble,
        "nombre_baux": nombre_baux,
        "baux_actifs": baux_actifs,
    }


def serialize_bien_with_locations(bien: Bien) -> Dict[str, Any]:
    """
    Sérialise un bien avec toutes ses locations détaillées.

    Args:
        bien: Instance de Bien

    Returns:
        Dict avec bien + liste de locations
    """
    locations = Location.objects.filter(bien=bien).prefetch_related("locataires")
    locations_data = [serialize_location_with_bail(loc) for loc in locations]

    return {
        "bien": serialize_bien_with_stats(bien),
        "locations": locations_data,
    }
