"""
Utilitaires pour les assurances.
"""

from assurances.models import InsuranceQuotation, InsuranceQuotationSignatureRequest
from location.services.access_utils import get_user_info_for_location
from signature.services import create_single_signature_request


def create_insurance_signature_request(
    quotation: InsuranceQuotation,
    user_email: str,
) -> InsuranceQuotationSignatureRequest:
    """
    Crée ou récupère la demande de signature pour un devis d'assurance.

    Pour l'assurance MRH, il n'y a qu'un seul signataire : le locataire souscripteur.

    Args:
        quotation: Instance d'InsuranceQuotation
        user_email: Email du souscripteur (locataire)

    Returns:
        InsuranceQuotationSignatureRequest créée ou existante
    """
    if not quotation.location:
        raise ValueError("Le devis n'est pas associé à une location")

    user_info = get_user_info_for_location(quotation.location, user_email)
    if not user_info.locataire:
        raise ValueError(
            f"L'utilisateur {user_email} n'est pas locataire de cette location"
        )

    return create_single_signature_request(
        document=quotation,
        signature_request_model=InsuranceQuotationSignatureRequest,
        locataire=user_info.locataire,
    )
