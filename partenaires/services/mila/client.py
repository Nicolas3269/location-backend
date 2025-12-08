"""
Client API Mila pour MRH Locataire.

Usage:
    from partenaires.services.mila import MilaMRHClient

    client = MilaMRHClient()
    result = client.get_quotation(bien)
    for formula in result.formulas:
        print(f"{formula.product_composition_label}: {formula.pricing_annual_amount}€/an")
"""

import logging
from datetime import date
from typing import TYPE_CHECKING

import requests
from django.conf import settings

from .adapters import AdresseToMilaAdapter, BienToMilaAdapter
from .auth import MilaAuthClient, MilaAuthError
from .types import (
    Deductible,
    MilaAddress,
    MilaRealEstateLot,
    MRHQuotationRequest,
    MRHQuotationResponse,
    MRHQuotationResult,
    RealEstateLotType,
)

if TYPE_CHECKING:
    from location.models import Bien

logger = logging.getLogger(__name__)


class MilaAPIError(Exception):
    """Erreur API Mila."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class MilaMRHClient:
    """
    Client pour l'API MRH Locataire de Mila.

    Permet d'obtenir des devis d'assurance habitation pour les locataires.

    Usage:
        client = MilaMRHClient()

        # Depuis un objet Bien
        result = client.get_quotation_from_bien(bien)

        # Ou avec des données manuelles
        result = client.get_quotation(
            address_line1="123 Rue de la Paix",
            postal_code="75001",
            city="Paris",
            lot_type=RealEstateLotType.APARTMENT,
            surface=45,
            main_rooms=2,
            floor=3,
        )
    """

    QUOTATION_ENDPOINT = "/brk/v1/individuals/quotations/homes/compute-pricing"

    def __init__(self, auth_client: MilaAuthClient | None = None):
        """
        Initialise le client MRH.

        Args:
            auth_client: Client d'authentification (créé automatiquement si None)
        """
        self._auth = auth_client or MilaAuthClient()
        self._session: requests.Session | None = None

    @property
    def base_url(self) -> str:
        return (settings.MILA_API_URL or "").rstrip("/")

    @property
    def session(self) -> requests.Session:
        """Session HTTP réutilisable."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({"Content-Type": "application/json"})
        return self._session

    def get_quotation(
        self,
        address_line1: str,
        postal_code: str,
        city: str,
        lot_type: RealEstateLotType,
        surface: float,
        main_rooms: int,
        floor: int | None = None,
        address_line2: str | None = None,
        country_code: str = "FR",
        deductible: int = Deductible.STANDARD,
        effective_date: date | None = None,
    ) -> MRHQuotationResult:
        """
        Obtient un devis MRH avec des données manuelles.

        Args:
            address_line1: Adresse ligne 1 (numéro + voie)
            postal_code: Code postal
            city: Ville
            lot_type: Type de lot (APARTMENT, HOUSE, etc.)
            surface: Surface en m²
            main_rooms: Nombre de pièces principales
            floor: Étage (requis si appartement)
            address_line2: Complément d'adresse
            country_code: Code pays (défaut: FR)
            deductible: Franchise (170€ ou 290€)
            effective_date: Date d'effet (défaut: aujourd'hui)

        Returns:
            MRHQuotationResult avec les formules disponibles

        Raises:
            MilaAPIError: Si l'API retourne une erreur
            MilaAuthError: Si l'authentification échoue
        """
        request = MRHQuotationRequest(
            deductible=deductible,
            real_estate_lot=MilaRealEstateLot(
                address=MilaAddress(
                    address_line1=address_line1,
                    address_line2=address_line2,
                    postal_code=postal_code,
                    city=city,
                    country_code=country_code,
                ),
                real_estate_lot_type=lot_type,
                surface=surface,
                main_rooms_number=main_rooms,
                floor=floor,
            ),
            effective_date=effective_date,
        )

        return self._execute_quotation(request)

    def get_quotation_from_bien(
        self,
        bien: "Bien",
        deductible: int = Deductible.STANDARD,
        effective_date: date | None = None,
    ) -> MRHQuotationResult:
        """
        Obtient un devis MRH depuis un objet Bien.

        Args:
            bien: Instance du modèle Bien
            deductible: Franchise (170€ ou 290€)
            effective_date: Date d'effet (défaut: aujourd'hui)

        Returns:
            MRHQuotationResult avec les formules disponibles

        Raises:
            ValueError: Si le bien n'a pas d'adresse
            MilaAPIError: Si l'API retourne une erreur
        """
        if not bien.adresse:
            raise ValueError("Le bien doit avoir une adresse structurée")

        # Utiliser les adapters existants
        mila_address = AdresseToMilaAdapter.to_mila(bien.adresse)
        lot_type_str = BienToMilaAdapter.TYPE_BIEN_MAPPING.get(
            bien.type_bien, "APARTMENT"
        )
        main_rooms = BienToMilaAdapter._count_main_rooms(bien.pieces_info or {})

        request = MRHQuotationRequest(
            deductible=deductible,
            real_estate_lot=MilaRealEstateLot(
                address=MilaAddress(
                    address_line1=mila_address["address_line1"],
                    address_line2=mila_address.get("address_line2"),
                    postal_code=mila_address["postal_code"],
                    city=mila_address["city"],
                    country_code=mila_address.get("country_code", "FR"),
                ),
                real_estate_lot_type=RealEstateLotType(lot_type_str),
                surface=float(bien.superficie) if bien.superficie else 0,
                main_rooms_number=main_rooms,
                floor=bien.etage if bien.type_bien == "appartement" else None,
            ),
            effective_date=effective_date,
        )

        return self._execute_quotation(request)

    def _execute_quotation(self, request: MRHQuotationRequest) -> MRHQuotationResult:
        """Exécute la requête de tarification."""
        payload = request.to_dict()
        url = f"{self.base_url}{self.QUOTATION_ENDPOINT}"

        logger.info(f"Mila MRH quotation request: {payload}")

        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._auth.get_auth_headers(),
                timeout=30,
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            logger.error(f"Mila API error: {e.response.status_code} - {e.response.text}")
            raise MilaAPIError(
                f"Erreur API Mila: {e.response.status_code}",
                status_code=e.response.status_code,
            ) from e
        except requests.RequestException as e:
            logger.error(f"Mila request failed: {e}")
            raise MilaAPIError(f"Erreur de connexion à Mila: {e}") from e

        data = response.json()
        logger.info(f"Mila MRH response: {data}")

        # L'API retourne une liste de formules
        formulas = [MRHQuotationResponse.from_dict(item) for item in data]

        logger.info(f"Mila MRH quotation: {len(formulas)} formulas received")

        return MRHQuotationResult(formulas=formulas, request=request)

    def close(self) -> None:
        """Ferme les sessions HTTP."""
        if self._session:
            self._session.close()
            self._session = None
        self._auth.close()

    def __enter__(self) -> "MilaMRHClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()
