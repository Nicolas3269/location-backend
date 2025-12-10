"""
Service de tarification assurance.

Utilise le client Mila existant pour obtenir les devis et les stocker en cache.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.utils import timezone

from assurances.models import InsuranceProduct
from partenaires.services.mila.client import MilaMRHClient
from partenaires.services.mila.types import MRHQuotationResponse, MRHQuotationResult

if TYPE_CHECKING:
    from assurances.models import InsuranceQuotation
    from location.models import Location

logger = logging.getLogger(__name__)


class InsuranceQuotationService:
    """
    Service pour gérer les devis d'assurance.

    Responsabilités:
    - Obtenir un devis depuis Mila
    - Stocker le devis en cache
    - Enrichir avec les informations de formules
    """

    # Cache de validité d'un devis (30 jours)
    QUOTATION_VALIDITY_DAYS = 30

    # Informations enrichies par formule (non fournies par Mila)
    # Basé sur le contrat Mila MRH Locataire
    FORMULA_INFO = {
        # MRH - Formule Essentielle
        "MRHIND_ESS": {
            "label": "Essentielle",
            "description": "Toutes les garanties obligatoires pour votre location",
            "features": [
                "Responsabilité civile locative illimitée",
                "Responsabilité civile vie privée",
                "Incendie, explosion, dégâts des eaux",
                "Catastrophes naturelles et technologiques",
                "Événements climatiques (tempête, grêle, neige)",
                "Attentats et actes de terrorisme",
            ],
            "highlights": [
                "Dégâts des eaux",
                "Incendie",
                "RC illimitée",
            ],
        },
        # MRH - Formule Sérénité (la plus complète)
        "MRHIND_SER": {
            "label": "Sérénité",
            "description": "La protection maximale pour vivre l'esprit tranquille",
            "features": [
                "Toutes les garanties Essentielle",
                "Vol et tentative de vol",
                "Vandalisme suite à vol",
                "Bris de glace (vitres, miroirs, plaques)",
                "Dommages électriques",
                "Assistance 24h/24 et 7j/7",
            ],
            "highlights": [
                "Vol",
                "Bris de glace",
                "Dommages électriques",
                "Assistance 24/7",
            ],
        },
        # PNO (à compléter avec les vraies formules Mila)
        "PNOIND_ESS": {
            "label": "Essentielle",
            "description": "Protection de base pour votre bien en location",
            "features": [
                "Responsabilité civile propriétaire",
                "Recours des locataires",
                "Dégâts des eaux",
                "Catastrophes naturelles",
            ],
            "highlights": ["RC propriétaire"],
        },
        "PNOIND_SER": {
            "label": "Sérénité",
            "description": "Protection complète pour propriétaire serein",
            "features": [
                "Toutes les garanties Essentielle",
                "Vacance locative",
                "Protection juridique",
                "Loyers impayés",
            ],
            "highlights": ["Vacance locative", "Protection juridique", "Loyers impayés"],
        },
    }

    def __init__(self):
        self._client: MilaMRHClient | None = None

    @property
    def client(self) -> MilaMRHClient:
        """Client Mila (lazy initialization)."""
        if self._client is None:
            self._client = MilaMRHClient()
        return self._client

    def get_quotation(
        self,
        location: "Location",
        user,
        product: str = InsuranceProduct.MRH,
        deductible: int = 170,
        effective_date: date | None = None,
        force_refresh: bool = False,
    ) -> "InsuranceQuotation":
        """
        Obtient un devis d'assurance pour une location.

        Vérifie d'abord si un devis valide existe en cache. Si non, ou si
        force_refresh est True, demande un nouveau devis à Mila.

        Args:
            location: Location pour laquelle obtenir le devis
            user: Utilisateur qui demande le devis
            product: Type de produit (MRH, PNO, GLI)
            deductible: Franchise (170 ou 290)
            effective_date: Date d'effet (défaut: aujourd'hui)
            force_refresh: Forcer un nouveau devis même si un existe

        Returns:
            InsuranceQuotation avec les formules disponibles

        Raises:
            ValueError: Si la location n'a pas de bien avec adresse
            MilaAPIError: Si l'API Mila retourne une erreur
        """
        from assurances.models import InsuranceQuotation

        if not effective_date:
            effective_date = timezone.now().date()

        # Vérifier le cache (devis non expiré)
        if not force_refresh:
            cached = self._get_cached_quotation(
                location, user, product, deductible, effective_date
            )
            if cached:
                logger.info(f"Using cached quotation {cached.id} for location {location.id}")
                return cached

        # Obtenir un nouveau devis depuis Mila
        logger.info(f"Requesting new {product} quotation for location {location.id}")

        bien = location.bien
        if not bien:
            raise ValueError("La location doit avoir un bien associé")

        # TODO: Utiliser différents endpoints Mila selon le produit
        result = self.client.get_quotation_from_bien(
            bien=bien,
            deductible=deductible,
            effective_date=effective_date,
        )

        # Enrichir les formules avec nos informations
        formulas_data = self._enrich_formulas(result)

        # Stocker en cache
        quotation = InsuranceQuotation.objects.create(
            user=user,
            product=product,
            location=location,
            deductible=deductible,
            effective_date=effective_date,
            formulas_data=formulas_data,
            expires_at=timezone.now() + timedelta(days=self.QUOTATION_VALIDITY_DAYS),
        )

        logger.info(f"Created {product} quotation {quotation.id} with {len(formulas_data)} formulas")
        return quotation

    def _get_cached_quotation(
        self,
        location: "Location",
        user,
        product: str,
        deductible: int,
        effective_date: date,
    ) -> "InsuranceQuotation | None":
        """Récupère un devis valide en cache pour cet utilisateur.

        Ne retourne que les devis en status DRAFT (pas encore en signature).
        """
        from assurances.models import InsuranceQuotation
        from signature.document_status import DocumentStatus

        return (
            InsuranceQuotation.objects.filter(
                user=user,
                product=product,
                location=location,
                deductible=deductible,
                effective_date=effective_date,
                expires_at__gt=timezone.now(),
                status=DocumentStatus.DRAFT,
            )
            .order_by("-created_at")
            .first()
        )

    # Mapping des codes Mila vers nos codes internes
    # Mila renvoie "Formule Essentielle", "Formule Confort", "Formule Sérénité"
    # Nous ne proposons que Essentielle et Sérénité (pas Confort)
    FORMULA_CODE_MAPPING = {
        # Codes Mila réels (product_composition_label)
        "FORMULE ESSENTIELLE": "MRHIND_ESS",
        "FORMULE SÉRÉNITÉ": "MRHIND_SER",
        "FORMULE SERENITE": "MRHIND_SER",
        # Note: "Formule Confort" est intentionnellement ignorée
        # car non proposée dans notre offre
        # Codes alternatifs (au cas où Mila change)
        "MRHIND_ESS": "MRHIND_ESS",
        "MRHIND_SER": "MRHIND_SER",
        "ESSENTIELLE": "MRHIND_ESS",
        "SERENITE": "MRHIND_SER",
        "SÉRÉNITÉ": "MRHIND_SER",
        # PNO
        "PNOIND_ESS": "PNOIND_ESS",
        "PNOIND_SER": "PNOIND_SER",
        "FORMULE PNO ESSENTIELLE": "PNOIND_ESS",
        "FORMULE PNO SÉRÉNITÉ": "PNOIND_SER",
    }

    def _enrich_formulas(self, result: MRHQuotationResult) -> list[dict]:
        """
        Enrichit les formules Mila avec nos informations (descriptions, features).

        Stratégie:
        1. Essayer de mapper les codes Mila vers nos codes internes
        2. Si aucune correspondance, utiliser heuristique par prix (moins cher = Essentielle)
        3. Ne garder que 2 formules max (Essentielle et Sérénité)

        Args:
            result: Résultat de tarification Mila

        Returns:
            Liste de dictionnaires avec les formules enrichies
        """
        formulas = []
        unmapped_formulas = []
        seen_codes = set()

        for formula in result.formulas:
            raw_code = formula.product_composition_label

            # Log pour debug
            logger.info(
                f"Mila formula: code='{raw_code}', "
                f"label='{formula.product_label}', "
                f"price={formula.pricing_annual_amount}€"
            )

            # Mapper le code vers notre format interne
            internal_code = self._map_formula_code(raw_code)

            if not internal_code:
                # Garder pour le fallback par prix
                unmapped_formulas.append(formula)
                continue

            # Éviter les doublons
            if internal_code in seen_codes:
                logger.debug(f"Duplicate formula {internal_code}, keeping first one")
                continue
            seen_codes.add(internal_code)

            info = self.FORMULA_INFO.get(internal_code, {})
            annual = formula.pricing_annual_amount
            monthly = (annual / Decimal("12")).quantize(Decimal("0.01"))

            formulas.append({
                "code": internal_code,
                "label": info.get("label", formula.product_label),
                "description": info.get("description", ""),
                "features": info.get("features", []),
                "highlights": info.get("highlights", []),
                "pricing_annual": float(annual),
                "pricing_monthly": float(monthly),
                "raw_response": formula.quotation_request,
            })

        # Fallback: si aucune formule mappée, utiliser heuristique par prix
        if not formulas and unmapped_formulas:
            logger.warning(
                f"No formula codes matched, using price-based heuristic for "
                f"{len(unmapped_formulas)} formulas"
            )
            formulas = self._assign_formulas_by_price(unmapped_formulas)

        # Trier: Essentielle en premier, Sérénité en second
        formula_order = {"MRHIND_ESS": 0, "MRHIND_SER": 1, "PNOIND_ESS": 0, "PNOIND_SER": 1}
        formulas.sort(key=lambda f: formula_order.get(f["code"], 99))

        logger.info(f"Final: {len(formulas)} formulas from {len(result.formulas)} Mila responses")
        return formulas

    def _assign_formulas_by_price(
        self, formulas: list[MRHQuotationResponse]
    ) -> list[dict]:
        """
        Assigne les formules Essentielle/Sérénité basé sur le prix.

        - La moins chère → Essentielle
        - La plus chère → Sérénité

        Args:
            formulas: Formules Mila non mappées

        Returns:
            Liste de 2 formules max (Essentielle et Sérénité)
        """
        if not formulas:
            return []

        # Trier par prix croissant
        sorted_formulas = sorted(formulas, key=lambda f: f.pricing_annual_amount)

        result = []

        # Moins chère = Essentielle
        cheapest = sorted_formulas[0]
        info = self.FORMULA_INFO["MRHIND_ESS"]
        annual = cheapest.pricing_annual_amount
        monthly = (annual / Decimal("12")).quantize(Decimal("0.01"))

        result.append({
            "code": "MRHIND_ESS",
            "label": info["label"],
            "description": info["description"],
            "features": info["features"],
            "highlights": info["highlights"],
            "pricing_annual": float(annual),
            "pricing_monthly": float(monthly),
            "raw_response": cheapest.quotation_request,
        })

        # Plus chère = Sérénité (si différente de la moins chère)
        if len(sorted_formulas) > 1:
            most_expensive = sorted_formulas[-1]
            info = self.FORMULA_INFO["MRHIND_SER"]
            annual = most_expensive.pricing_annual_amount
            monthly = (annual / Decimal("12")).quantize(Decimal("0.01"))

            result.append({
                "code": "MRHIND_SER",
                "label": info["label"],
                "description": info["description"],
                "features": info["features"],
                "highlights": info["highlights"],
                "pricing_annual": float(annual),
                "pricing_monthly": float(monthly),
                "raw_response": most_expensive.quotation_request,
            })

        return result

    def _map_formula_code(self, raw_code: str) -> str | None:
        """
        Mappe un code Mila vers notre code interne.

        Essaie plusieurs stratégies:
        1. Correspondance exacte dans FORMULA_CODE_MAPPING
        2. Correspondance partielle (contient ESS ou SER)
        3. Retourne None si non reconnu

        Args:
            raw_code: Code brut retourné par Mila

        Returns:
            Code interne ou None si non reconnu
        """
        # Normaliser
        code_upper = raw_code.upper().strip()

        # 1. Correspondance exacte
        if code_upper in self.FORMULA_CODE_MAPPING:
            return self.FORMULA_CODE_MAPPING[code_upper]

        # 2. Correspondance partielle pour MRH
        if "MRH" in code_upper or "LOCATAIRE" in code_upper:
            if "ESS" in code_upper or "ESSENTIEL" in code_upper:
                return "MRHIND_ESS"
            if "SER" in code_upper or "SERENITE" in code_upper or "SÉRÉNITÉ" in code_upper:
                return "MRHIND_SER"

        # 3. Correspondance partielle pour PNO
        if "PNO" in code_upper or "PROPRIETAIRE" in code_upper:
            if "ESS" in code_upper or "ESSENTIEL" in code_upper:
                return "PNOIND_ESS"
            if "SER" in code_upper or "SERENITE" in code_upper or "SÉRÉNITÉ" in code_upper:
                return "PNOIND_SER"

        return None

    def close(self):
        """Ferme les connexions."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
