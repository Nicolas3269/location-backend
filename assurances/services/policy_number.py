"""
Génération des numéros de police d'assurance.

Format: PO-{PRODUCT}IND-67XXXXXXX
- PO: Préfixe police
- {PRODUCT}IND: Produit (MRH, PNO, GLI) Individuel
- 67: Code courtier Hestia
- XXXXXXX: 7 chiffres séquentiels (par produit)
"""

from django.db import transaction
from django.db.models import Max

from assurances.models import POLICY_NUMBER_PREFIXES, InsuranceProduct


def generate_policy_number(product: str = InsuranceProduct.MRH) -> str:
    """
    Génère un numéro de police unique pour le produit donné.

    Args:
        product: Type de produit (MRH, PNO, GLI)

    Returns:
        Numéro de police au format PO-{PRODUCT}IND-67XXXXXXX

    Examples:
        generate_policy_number("MRH") → "PO-MRHIND-670000001"
        generate_policy_number("PNO") → "PO-PNOIND-670000001"
    """
    from assurances.models import InsurancePolicy

    prefix = POLICY_NUMBER_PREFIXES.get(product, POLICY_NUMBER_PREFIXES[InsuranceProduct.MRH])

    with transaction.atomic():
        # Récupérer le dernier numéro pour ce produit avec verrou
        # Le product est sur quotation, pas sur policy
        last_policy = (
            InsurancePolicy.objects.filter(quotation__product=product)
            .select_for_update()
            .aggregate(max_number=Max("policy_number"))
        )

        if last_policy["max_number"]:
            # Extraire le numéro séquentiel
            try:
                last_seq = int(last_policy["max_number"].replace(prefix, ""))
                new_seq = last_seq + 1
            except (ValueError, AttributeError):
                new_seq = 1
        else:
            new_seq = 1

        return f"{prefix}{new_seq:07d}"
