"""
Types et dataclasses pour l'API Mila.

Ces types représentent les structures de données échangées avec l'API Mila.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class RealEstateLotType(str, Enum):
    """Types de lots immobiliers acceptés par Mila."""

    HOUSE = "HOUSE"
    APARTMENT = "APARTMENT"
    REAL_ESTATE_PROPERTY = "REAL_ESTATE_PROPERTY"
    PARKING = "PARKING"
    ISOLATED_GARAGE = "ISOLATED_GARAGE"
    BOX = "BOX"
    REAL_ESTATE_COMMERCIAL = "REAL_ESTATE_COMMERCIAL"
    OTHER = "OTHER"


class Deductible(int, Enum):
    """Montants de franchise acceptés pour MRH Locataire."""

    STANDARD = 170
    REDUCED = 290


@dataclass
class MilaAddress:
    """
    Adresse au format Mila API.

    Champs requis: address_line1, postal_code, city, country_code
    """

    # Champs requis
    address_line1: str
    postal_code: str
    city: str
    country_code: str = "FR"

    # Champs optionnels
    address_line2: str | None = None
    address_line3: str | None = None
    city_code: str | None = None  # Code INSEE
    recipient: str | None = None  # Destinataire
    main: bool | None = None  # Adresse principale
    longitude: float | None = None  # -180 à 180
    latitude: float | None = None  # -90 à 90


@dataclass
class MilaRealEstateLot:
    """Lot immobilier au format Mila API."""

    address: MilaAddress
    real_estate_lot_type: RealEstateLotType
    surface: float
    main_rooms_number: int
    floor: int | None = None


@dataclass
class MRHQuotationRequest:
    """Requête de tarification MRH Locataire."""

    deductible: int
    real_estate_lot: MilaRealEstateLot
    effective_date: date | None = None

    def to_dict(self) -> dict:
        """Convertit en dict pour l'API."""
        # Gérer le cas où deductible est un enum ou un int
        deductible_value = (
            self.deductible.value
            if isinstance(self.deductible, Deductible)
            else self.deductible
        )
        payload = {
            "deductible": deductible_value,
            "real_estate_lot": {
                "address": {
                    "address_line1": self.real_estate_lot.address.address_line1,
                    "postal_code": self.real_estate_lot.address.postal_code,
                    "city": self.real_estate_lot.address.city,
                    "country_code": self.real_estate_lot.address.country_code,
                },
                "real_estate_lot_type": self.real_estate_lot.real_estate_lot_type.value,
                "surface": self.real_estate_lot.surface,
                "main_rooms_number": self.real_estate_lot.main_rooms_number,
            },
        }

        # Ajouter champs d'adresse optionnels si présents
        addr = self.real_estate_lot.address
        addr_payload = payload["real_estate_lot"]["address"]

        if addr.address_line2:
            addr_payload["address_line2"] = addr.address_line2
        if addr.address_line3:
            addr_payload["address_line3"] = addr.address_line3
        if addr.city_code:
            addr_payload["city_code"] = addr.city_code
        if addr.recipient:
            addr_payload["recipient"] = addr.recipient
        if addr.main is not None:
            addr_payload["main"] = addr.main
        if addr.longitude is not None:
            addr_payload["longitude"] = addr.longitude
        if addr.latitude is not None:
            addr_payload["latitude"] = addr.latitude

        # Ajouter étage si présent (requis pour appartement)
        if self.real_estate_lot.floor is not None:
            # Convertir en int (peut être string depuis le modèle)
            floor = self.real_estate_lot.floor
            payload["real_estate_lot"]["floor"] = (
                int(floor) if isinstance(floor, str) else floor
            )

        # Ajouter date d'effet si spécifiée
        if self.effective_date:
            payload["effective_date"] = self.effective_date.isoformat()

        return payload


@dataclass
class MRHQuotationResponse:
    """Réponse de tarification MRH - une formule."""

    product_label: str
    product_composition_label: str
    pricing_annual_amount: Decimal
    quotation_request: dict  # Copie de la requête

    @classmethod
    def from_dict(cls, data: dict) -> "MRHQuotationResponse":
        """Crée une instance depuis la réponse API."""
        return cls(
            product_label=data.get("product_label", ""),
            product_composition_label=data.get("product_composition_label", ""),
            pricing_annual_amount=Decimal(str(data.get("pricing_annual_amount", 0))),
            quotation_request=data.get("quotation_request", {}),
        )


@dataclass
class MRHQuotationResult:
    """Résultat complet de tarification MRH avec toutes les formules."""

    formulas: list[MRHQuotationResponse]
    request: MRHQuotationRequest

    @property
    def cheapest(self) -> MRHQuotationResponse | None:
        """Retourne la formule la moins chère."""
        if not self.formulas:
            return None
        return min(self.formulas, key=lambda f: f.pricing_annual_amount)

    @property
    def has_results(self) -> bool:
        """Indique si des formules sont disponibles."""
        return len(self.formulas) > 0
