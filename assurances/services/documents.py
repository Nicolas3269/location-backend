"""
Service de génération de documents assurance.

Génère les PDFs pour:
- Conditions Particulières (CP)
- Conditions Générales (CGV)
- Attestation d'assurance
- Devis
"""

import logging
from typing import TYPE_CHECKING, Any

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from weasyprint import HTML

from backend.pdf_utils import get_logo_pdf_base64_data_uri

if TYPE_CHECKING:
    from assurances.models import InsurancePolicy

logger = logging.getLogger(__name__)


class InsuranceDocumentService:
    """
    Service pour générer les documents assurance en PDF.

    Utilise WeasyPrint pour la conversion HTML → PDF.
    Supporte tous les produits: MRH, PNO, GLI.
    """

    def generate_conditions_particulieres(self, policy: "InsurancePolicy") -> bytes:
        """
        Génère les Conditions Particulières en PDF.

        Args:
            policy: Police assurance

        Returns:
            Contenu PDF en bytes
        """
        quotation = policy.quotation
        location = quotation.location
        bien = location.bien if location else None
        subscriber = policy.subscriber

        context = {
            "policy": policy,
            "location": location,
            "bien": bien,
            "subscriber": subscriber,
            "adresse": bien.adresse if bien else None,
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
        }

        # Template selon le produit
        template = (
            f"pdf/assurances/{quotation.product.lower()}/conditions_particulieres.html"
        )
        html = render_to_string(template, context)
        return HTML(string=html).write_pdf()

    def generate_attestation(self, policy: "InsurancePolicy") -> bytes:
        """
        Génère l'attestation d'assurance en PDF.

        Args:
            policy: Police assurance

        Returns:
            Contenu PDF en bytes
        """
        quotation = policy.quotation
        location = quotation.location
        bien = location.bien if location else None

        context = {
            "policy": policy,
            "bien": bien,
            "subscriber": policy.subscriber,
            "adresse": bien.adresse if bien else None,
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
        }

        # Template selon le produit
        template = f"pdf/assurances/{quotation.product.lower()}/attestation.html"
        html = render_to_string(template, context)
        return HTML(string=html).write_pdf()

    def generate_conditions_generales(self, product: str = "MRH") -> bytes:
        """
        Génère les Conditions Générales en PDF.

        Les CGV sont un document statique (non personnalisé).

        Args:
            product: Type de produit (MRH, PNO, GLI)

        Returns:
            Contenu PDF en bytes
        """
        # Référence des CGV selon le produit
        references = {
            "MRH": "CG-MRH-I-2024061",
            "PNO": "CG-PNO-I-2024061",
            "GLI": "CG-GLI-I-2024061",
        }

        context = {
            "reference": references.get(product, "CG-MRH-I-2024061"),
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
        }

        template = f"pdf/assurances/{product.lower()}/conditions_generales.html"
        html = render_to_string(template, context)
        return HTML(string=html).write_pdf()

    def generate_conditions_particulieres_preview(
        self,
        quotation_data: dict[str, Any],
        formula_data: dict[str, Any],
        subscriber: Any | None = None,
        bien: Any | None = None,
        location: Any | None = None,
        locataire: Any | None = None,
    ) -> bytes:
        """
        Génère une prévisualisation des Conditions Particulières en PDF.

        Utilisé avant la souscription pour montrer à l'utilisateur
        ce qu'il va signer.

        Args:
            quotation_data: Données du devis
            formula_data: Données de la formule sélectionnée
            subscriber: Informations du souscripteur
            bien: Informations du bien
            location: Location associée
            locataire: Locataire souscripteur (pour marqueur de signature)

        Returns:
            Contenu PDF en bytes
        """

        # Créer un objet "policy-like" pour le template
        class PolicyPreview:
            def __init__(self, q_data: dict, f_data: dict):
                self.policy_number = "DRAFT"  # Numéro provisoire
                self.product = q_data.get("product", "MRH")
                self.formula_label = f_data.get("label", "")
                self.formula_code = f_data.get("code", "")
                self.pricing_annual = f_data.get("pricing_annual", 0)
                self.pricing_monthly = f_data.get("pricing_monthly", 0)
                self.deductible = q_data.get("deductible", 170)
                self.effective_date = q_data.get("effective_date")

        policy_preview = PolicyPreview(quotation_data, formula_data)

        context = {
            "policy": policy_preview,
            "location": location,
            "bien": bien,
            "subscriber": subscriber,
            "locataire": locataire,  # Pour le marqueur de signature
            "adresse": bien.adresse if bien else None,
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
            "is_preview": True,  # Flag pour afficher "PROJET" dans le template
        }

        product = quotation_data.get("product", "MRH").lower()
        template = f"pdf/assurances/{product}/conditions_particulieres.html"
        html = render_to_string(template, context)
        return HTML(string=html).write_pdf()

    def generate_devis(
        self,
        quotation_data: dict[str, Any],
        subscriber: Any | None = None,
        bien: Any | None = None,
    ) -> bytes:
        """
        Génère un devis d'assurance en PDF.

        Args:
            quotation_data: Données du devis (id, formulas, created_at, expires_at, etc.)
            subscriber: Informations du souscripteur (optionnel)
            bien: Informations du bien (optionnel)

        Returns:
            Contenu PDF en bytes
        """

        # Créer un objet simple pour le template
        class QuotationObj:
            def __init__(self, data: dict):
                self.id = data.get("id", "")
                self.created_at = data.get("created_at")
                self.expires_at = data.get("expires_at")
                self.product = data.get("product", "MRH")

        quotation = QuotationObj(quotation_data)

        context = {
            "quotation": quotation,
            "formulas": quotation_data.get("formulas", []),
            "subscriber": subscriber,
            "bien": bien,
            "adresse": bien.adresse if bien else None,
            "deductible": quotation_data.get("deductible", 170),
            "effective_date": quotation_data.get("effective_date"),
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
        }

        product = quotation_data.get("product", "MRH").lower()
        template = f"pdf/assurances/{product}/devis.html"
        html = render_to_string(template, context)
        return HTML(string=html).write_pdf()

    def generate_all_documents(self, policy: "InsurancePolicy") -> None:
        """
        Génère et sauvegarde tous les documents de la police.

        Note: Les CP (Conditions Particulières) sont déjà signées et stockées
        dans quotation.latest_pdf. On génère ici uniquement l'attestation.

        Args:
            policy: Police assurance
        """
        logger.info(f"📄 Starting document generation for policy {policy.policy_number}")

        # Log context pour debug
        quotation = policy.quotation
        location = quotation.location
        bien = location.bien if location else None
        logger.info(
            f"📄 Context: quotation={quotation.id}, "
            f"location={location.id if location else None}, "
            f"bien={bien.id if bien else None}, product={quotation.product}"
        )

        # Vérifier que les CP sont bien signées
        if quotation.latest_pdf:
            logger.info(
                f"📄 CP already signed and stored in quotation.latest_pdf "
                f"for {policy.policy_number}"
            )
        else:
            logger.warning(
                f"⚠️ CP not found in quotation.latest_pdf for {policy.policy_number}"
            )

        # Attestation
        try:
            logger.info(f"📄 Generating attestation for {policy.policy_number}...")
            attestation_pdf = self.generate_attestation(policy)
            logger.info(f"📄 Attestation PDF generated, size={len(attestation_pdf)} bytes")
            policy.attestation_document.save(
                f"attestation_{policy.policy_number}.pdf",
                ContentFile(attestation_pdf),
            )
            logger.info(f"✅ Attestation document saved for {policy.policy_number}")
        except Exception as e:
            logger.exception(
                f"❌ Failed to generate attestation for {policy.policy_number}: {e}"
            )
            raise

        policy.save()
        logger.info(f"✅ All documents generated and saved for policy {policy.policy_number}")
