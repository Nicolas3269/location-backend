"""
Service de génération de documents assurance.

Génère les PDFs pour:
- Conditions Particulières (CP)
- Conditions Générales (CGV)
- Attestation d'assurance
- Devis
"""

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from dateutil.relativedelta import relativedelta
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from weasyprint import HTML

from backend.pdf_utils import (
    get_hestia_signature_base64_data_uri,
    get_logo_pdf_base64_data_uri,
    get_mila_signature_base64_data_uri,
)
from location.models import Bien, Location
from location.services.access_utils import get_user_info_for_location

if TYPE_CHECKING:
    from assurances.models import InsurancePolicy

logger = logging.getLogger(__name__)

# Constante taxe attentat - annuelle
TAXE_ATTENTAT = Decimal("6.50")


def _calculate_garantie_limits(bien: Bien) -> dict[str, int]:
    """
    Calcule les limites de garantie basées sur le nombre de pièces.

    Args:
        bien: Le bien assuré

    Returns:
        Dict avec nb_pieces, limite_mobilier, limite_objets_valeur

    Raises:
        ValueError: Si le bien n'a pas de nombre de pièces défini
    """
    if not bien or not bien.nombre_pieces_principales:
        raise ValueError("Le bien doit avoir un nombre de pièces principales défini")
    nb_pieces = bien.nombre_pieces_principales
    return {
        "nb_pieces": nb_pieces,
        "limite_mobilier": 8000 + (nb_pieces - 1) * 3000,
        "limite_objets_valeur": 2500 + (nb_pieces - 1) * 1000,
    }


def _calculate_echeancier(
    effective_date: date,
    pricing_monthly: Decimal | float,
    pricing_annual: Decimal | float,
) -> dict[str, Any]:
    """
    Calcule l'échéancier des prélèvements pour la première année.

    La taxe attentat (6,50€) est incluse dans le premier prélèvement.

    Args:
        effective_date: Date d'effet du contrat
        pricing_monthly: Cotisation mensuelle TTC
        pricing_annual: Cotisation annuelle TTC

    Returns:
        Dict avec:
        - taxe_attentat: Montant de la taxe (6.50€)
        - prelevements: Liste de 12 dicts {numero, date, montant, detail}
        - total_annuel: Total de l'année (annuel + taxe)
    """
    pricing_monthly = Decimal(str(pricing_monthly))
    pricing_annual = Decimal(str(pricing_annual))

    prelevements = []

    for i in range(12):
        prelevement_date = effective_date + relativedelta(months=i)
        numero = i + 1

        if i == 0:
            # Premier prélèvement : cotisation + taxe attentat
            montant = pricing_monthly + TAXE_ATTENTAT
            detail = f"Cotisation {pricing_monthly:.2f} € + Taxe attentat {TAXE_ATTENTAT:.2f} €"
            is_first = True
        else:
            # Prélèvements suivants : cotisation seule
            montant = pricing_monthly
            detail = "Cotisation mensuelle"
            is_first = False

        prelevements.append(
            {
                "numero": numero,
                "date": prelevement_date,
                "montant": float(montant),
                "detail": detail,
                "is_first": is_first,
            }
        )

    total_annuel = pricing_annual + TAXE_ATTENTAT

    return {
        "taxe_attentat": float(TAXE_ATTENTAT),
        "prelevements": prelevements,
        "total_annuel": float(total_annuel),
        "pricing_annual": float(pricing_annual),
    }


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
        location: Location = quotation.location
        bien = location.bien if location else None
        subscriber = policy.subscriber

        # Récupérer le locataire souscripteur via user_info (source de vérité)
        locataire = None
        if location and subscriber:
            user_info = get_user_info_for_location(location, subscriber.email)
            locataire = user_info.locataire

        # Calculer les limites de garantie
        limites = _calculate_garantie_limits(bien)

        # Calculer l'échéancier des prélèvements
        formula = quotation.selected_formula or {}
        echeancier = _calculate_echeancier(
            effective_date=quotation.effective_date,
            pricing_monthly=formula.get("pricing_monthly", 0),
            pricing_annual=formula.get("pricing_annual", 0),
        )

        context = {
            "policy": policy,
            "quotation": quotation,
            "location": location,
            "bien": bien,
            "locataire": locataire,
            "adresse": bien.adresse if bien else None,
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
            "mila_signature_base64_uri": get_mila_signature_base64_data_uri(),
            "hestia_signature_base64_uri": get_hestia_signature_base64_data_uri(),
            "echeancier": echeancier,
            **limites,
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
        subscriber = policy.subscriber

        # Récupérer le locataire souscripteur via user_info (source de vérité)
        locataire = None
        if location and subscriber:
            user_info = get_user_info_for_location(location, subscriber.email)
            locataire = user_info.locataire

        context = {
            "policy": policy,
            "bien": bien,
            "locataire": locataire,
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

    def generate_der(self) -> bytes:
        """
        Génère le Document d'Entrée en Relation (DER) en PDF.

        Le DER est un document réglementaire obligatoire pour les courtiers.

        Returns:
            Contenu PDF en bytes
        """
        context = {
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
        }

        html = render_to_string("pdf/assurances/der.html", context)
        return HTML(string=html).write_pdf()

    def generate_static_document(self, document_type: str) -> bytes:
        """
        Génère un document statique selon son type.

        Args:
            document_type: Type de document (DER, CGV_MRH, CGV_PNO, CGV_GLI)

        Returns:
            Contenu PDF en bytes
        """
        if document_type == "DER":
            return self.generate_der()
        elif document_type.startswith("CGV_"):
            product = document_type.replace("CGV_", "")
            return self.generate_conditions_generales(product=product)
        else:
            raise ValueError(f"Type de document inconnu: {document_type}")

    def generate_conditions_particulieres_preview(
        self,
        quotation_data: dict[str, Any],
        formula_data: dict[str, Any],
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
            bien: Informations du bien
            location: Location associée
            locataire: Locataire souscripteur (source de vérité pour nom/prénom)

        Returns:
            Contenu PDF en bytes
        """

        # Générer un numéro de police prévisualisation
        from .policy_number import generate_policy_number

        product = quotation_data.get("product", "MRH")
        preview_policy_number = generate_policy_number(product)

        # Créer un objet "policy-like" pour le template
        class PolicyPreview:
            def __init__(self, q_data: dict, f_data: dict, policy_num: str):
                self.policy_number = policy_num
                self.product = q_data.get("product", "MRH")
                self.formula_label = f_data.get("label", "")
                self.formula_code = f_data.get("code", "")
                self.pricing_annual = f_data.get("pricing_annual", 0)
                self.pricing_monthly = f_data.get("pricing_monthly", 0)
                self.deductible = q_data.get("deductible", 170)
                self.effective_date = q_data.get("effective_date")

        # Créer un objet "quotation-like" pour le template
        class QuotationPreview:
            def __init__(self, q_data: dict, f_data: dict):
                self.effective_date = q_data.get("effective_date")
                self.deductible = q_data.get("deductible", 170)
                self._selected_formula = f_data

            @property
            def selected_formula(self):
                return self._selected_formula

        policy_preview = PolicyPreview(
            quotation_data, formula_data, preview_policy_number
        )
        quotation_preview = QuotationPreview(quotation_data, formula_data)

        # Calculer les limites de garantie
        limites = _calculate_garantie_limits(bien)

        # Calculer l'échéancier des prélèvements
        echeancier = _calculate_echeancier(
            effective_date=quotation_data.get("effective_date"),
            pricing_monthly=formula_data.get("pricing_monthly", 0),
            pricing_annual=formula_data.get("pricing_annual", 0),
        )

        context = {
            "policy": policy_preview,
            "quotation": quotation_preview,
            "location": location,
            "bien": bien,
            "locataire": locataire,
            "adresse": bien.adresse if bien else None,
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
            "mila_signature_base64_uri": get_mila_signature_base64_data_uri(),
            "hestia_signature_base64_uri": get_hestia_signature_base64_data_uri(),
            "is_preview": True,  # Flag pour afficher "PROJET" dans le template
            "echeancier": echeancier,
            **limites,
        }

        product = quotation_data.get("product", "MRH").lower()
        template = f"pdf/assurances/{product}/conditions_particulieres.html"
        html = render_to_string(template, context)
        return HTML(string=html).write_pdf()

    def generate_devis(
        self,
        quotation_data: dict[str, Any],
        bien: Any | None = None,
        locataire: Any | None = None,
    ) -> bytes:
        """
        Génère un devis d'assurance en PDF.

        Args:
            quotation_data: Données du devis (id, formulas, created_at, expires_at, etc.)
            bien: Informations du bien (optionnel)
            locataire: Locataire souscripteur (source de vérité pour nom/prénom)

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

        # Calculer les limites de garantie
        limites = _calculate_garantie_limits(bien)

        context = {
            "quotation": quotation,
            "formulas": quotation_data.get("formulas", []),
            "locataire": locataire,
            "bien": bien,
            "adresse": bien.adresse if bien else None,
            "deductible": quotation_data.get("deductible", 170),
            "effective_date": quotation_data.get("effective_date"),
            "logo_base64_uri": get_logo_pdf_base64_data_uri(),
            **limites,
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
        logger.info(
            f"📄 Starting document generation for policy {policy.policy_number}"
        )

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
            logger.info(
                f"📄 Attestation PDF generated, size={len(attestation_pdf)} bytes"
            )
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
        logger.info(
            f"✅ All documents generated and saved for policy {policy.policy_number}"
        )
