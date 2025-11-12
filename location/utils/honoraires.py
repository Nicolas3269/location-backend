"""
Utilitaires pour le calcul des honoraires mandataire
"""

from decimal import Decimal
from typing import Optional

from location.models import HonoraireMandataire, Location


def get_active_honoraires(location: Location) -> Optional[HonoraireMandataire]:
    """
    Récupère les honoraires mandataire actifs pour une location.

    Args:
        location: Instance de Location

    Returns:
        HonoraireMandataire actif ou None si aucun trouvé
    """
    try:
        return HonoraireMandataire.objects.get(
            location=location, date_fin__isnull=True  # Honoraires actifs
        )
    except HonoraireMandataire.DoesNotExist:
        return None


def calculate_honoraires_dict(
    tarif_par_m2: Decimal,
    superficie: Decimal,
    part_bailleur_pct: float,
) -> dict:
    """
    Calcule les montants d'honoraires et retourne un dict formaté.

    Args:
        tarif_par_m2: Tarif en €/m²
        superficie: Superficie du bien en m²
        part_bailleur_pct: Pourcentage part bailleur (0-100)

    Returns:
        Dict avec tarif_par_m2, superficie, montant_total, parts bailleur/locataire
    """
    montant_total = (tarif_par_m2 * superficie).quantize(Decimal("0.01"))
    part_pct = Decimal(str(part_bailleur_pct)) / 100
    montant_bailleur = (montant_total * part_pct).quantize(Decimal("0.01"))
    montant_locataire = montant_total - montant_bailleur

    return {
        "tarif_par_m2": float(tarif_par_m2),
        "superficie": float(superficie),
        "montant_total": float(montant_total),
        "part_bailleur_pct": part_bailleur_pct,
        "montant_bailleur": float(montant_bailleur),
        "part_locataire_pct": 100 - part_bailleur_pct,
        "montant_locataire": float(montant_locataire),
    }


def close_active_honoraires(location: Location, raison: str = "Révocation mandataire"):
    """
    Ferme tous les honoraires actifs pour une location.
    Utilisé lors de la révocation d'un mandataire.

    Args:
        location: Instance de Location
        raison: Raison de la fermeture (optionnel)

    Returns:
        Nombre d'honoraires fermés
    """
    from django.utils import timezone

    today = timezone.now().date()
    active_honoraires = HonoraireMandataire.objects.filter(
        location=location, date_fin__isnull=True
    )

    count = 0
    for honoraire in active_honoraires:
        honoraire.date_fin = today
        honoraire.raison_changement = (
            f"{honoraire.raison_changement or ''}\n{raison}".strip()
        )
        honoraire.save(update_fields=["date_fin", "raison_changement", "updated_at"])
        count += 1

    return count


def get_honoraires_mandataire_for_location(
    location: Location,
    include_bail: bool = True,
    include_edl: bool = True,
    check_doit_signer: bool = False,
    document = None,
) -> dict:
    """
    Récupère et calcule les honoraires mandataire pour une location.

    Args:
        location: Instance de Location
        include_bail: Inclure les honoraires de bail dans le résultat
        include_edl: Inclure les honoraires EDL dans le résultat
        check_doit_signer: Si True, vérifie document.mandataire_doit_signer avant calcul
        document: Instance de Bail/EtatDesLieux (requis si check_doit_signer=True)

    Returns:
        Dict avec clés 'bail' et/ou 'edl' contenant les données calculées
    """
    result = {}

    if not location.mandataire:
        return result

    # Optimisation: vérifier mandataire_doit_signer avant de calculer
    if check_doit_signer and document:
        if not getattr(document, "mandataire_doit_signer", False):
            return result

    honoraires = get_active_honoraires(location)
    if not honoraires:
        return result

    superficie = Decimal(str(location.bien.superficie or 0))

    # Honoraires de bail
    if include_bail and honoraires.honoraires_bail_par_m2 is not None:
        tarif_bail = Decimal(str(honoraires.honoraires_bail_par_m2))
        part_bailleur_pct = float(honoraires.honoraires_bail_part_bailleur_pct or 0)

        result["bail"] = calculate_honoraires_dict(
            tarif_bail, superficie, part_bailleur_pct
        )

    # Honoraires EDL
    if (
        include_edl
        and honoraires.mandataire_fait_edl
        and honoraires.honoraires_edl_par_m2 is not None
    ):
        tarif_edl = Decimal(str(honoraires.honoraires_edl_par_m2))
        part_bailleur_edl_pct = float(honoraires.honoraires_edl_part_bailleur_pct or 0)

        result["edl"] = calculate_honoraires_dict(
            tarif_edl, superficie, part_bailleur_edl_pct
        )

    return result
