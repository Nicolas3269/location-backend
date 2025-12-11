"""
Adapters pour convertir les modèles internes vers le format API Mila.

Usage:
    from partenaires.services.mila import AdresseToMilaAdapter, BienToMilaAdapter

    adresse_mila = AdresseToMilaAdapter.to_mila(adresse)
    bien_mila = BienToMilaAdapter.to_mrh_quotation(bien)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from location.models import Adresse, Bien


class AdresseIncompleteError(ValueError):
    """Exception levée quand une adresse est incomplète pour l'API Mila."""

    def __init__(self, missing_fields: list[str]):
        self.missing_fields = missing_fields
        fields_str = ", ".join(missing_fields)
        super().__init__(
            f"L'adresse est incomplète pour l'assurance MRH avec Hestia. Champs manquants: {fields_str}."
        )


class AdresseToMilaAdapter:
    """Convertit une Adresse vers le format Mila API."""

    @staticmethod
    def validate_for_mila(adresse: "Adresse") -> None:
        """
        Valide qu'une adresse contient tous les champs requis par Mila.

        Raises:
            AdresseIncompleteError: Si des champs requis sont manquants
        """
        missing_fields = []

        # address_line1 = rue = numero + voie (voie est requis)
        if not adresse.voie:
            missing_fields.append("voie (nom de rue)")

        # postal_code est requis par Mila
        if not adresse.code_postal:
            missing_fields.append("code_postal")

        # city est requis (mais déjà obligatoire dans le modèle)
        if not adresse.ville:
            missing_fields.append("ville")

        if missing_fields:
            raise AdresseIncompleteError(missing_fields)

    @staticmethod
    def to_mila(adresse: "Adresse", validate: bool = True) -> dict:
        """
        Convertit une Adresse vers le format attendu par l'API Mila.

        Note: adresse.rue est une propriété calculée qui combine numero + voie.
        Ex: numero="123", voie="Rue de la Paix" → rue="123 Rue de la Paix"

        Args:
            adresse: Instance du modèle Adresse
            validate: Si True (défaut), valide la complétude de l'adresse

        Raises:
            AdresseIncompleteError: Si validate=True et des champs requis manquent

        Returns:
            {
                "address_line1": "123 Rue de la Paix",
                "address_line2": "Apt 4B" | None,
                "postal_code": "75001",
                "city": "Paris",
                "country_code": "FR",
                "latitude": 48.8566 | None,
                "longitude": 2.3522 | None
            }
        """
        if validate:
            AdresseToMilaAdapter.validate_for_mila(adresse)

        result = {
            "address_line1": adresse.rue,  # propriété: numero + voie
            "address_line2": adresse.complement or None,
            "postal_code": adresse.code_postal,
            "city": adresse.ville,
            "country_code": adresse.pays,
        }

        # Ajouter coordonnées GPS si disponibles
        if adresse.latitude is not None:
            result["latitude"] = adresse.latitude
        if adresse.longitude is not None:
            result["longitude"] = adresse.longitude

        return result


class BienToMilaAdapter:
    """Convertit un Bien vers le format Mila API pour tarification MRH."""

    # Mapping type_bien interne -> Mila
    TYPE_BIEN_MAPPING = {
        "appartement": "APARTMENT",
        "maison": "HOUSE",
        "parking": "PARKING",
        "garage": "ISOLATED_GARAGE",
        "box": "BOX",
    }

    @classmethod
    def to_mrh_quotation(
        cls,
        bien: "Bien",
        deductible: int = 170,
        effective_date: str | None = None,
    ) -> dict:
        """
        Convertit un Bien vers le format de tarification MRH Mila.

        Args:
            bien: Instance du modèle Bien
            deductible: Franchise (170 ou 290)
            effective_date: Date d'effet (optionnel, défaut: aujourd'hui)

        Returns:
            Dict compatible avec POST /brk/v1/individuals/quotations/homes/compute-pricing
        """
        if not bien.adresse:
            raise ValueError("Le bien doit avoir une adresse structurée")

        # Calculer le nombre de pièces principales
        pieces_principales = cls._count_main_rooms(bien.pieces_info or {})

        payload = {
            "deductible": deductible,
            "real_estate_lot": {
                "address": AdresseToMilaAdapter.to_mila(bien.adresse),
                "real_estate_lot_type": cls.TYPE_BIEN_MAPPING.get(
                    bien.type_bien, "APARTMENT"
                ),
                "surface": float(bien.superficie) if bien.superficie else None,
                "main_rooms_number": pieces_principales,
            },
        }

        # Ajouter l'étage si c'est un appartement
        if bien.type_bien == "appartement" and bien.etage is not None:
            payload["real_estate_lot"]["floor"] = bien.etage

        # Ajouter la date d'effet si spécifiée
        if effective_date:
            payload["effective_date"] = effective_date

        return payload

    @staticmethod
    def _count_main_rooms(pieces_info: dict) -> int:
        """
        Compte le nombre de pièces principales selon la définition Mila.

        Pièces principales = chambres + salons + bureaux
        (exclut cuisines, salles de bain, WC, couloirs)
        """
        count = 0
        count += pieces_info.get("chambres", 0)
        count += pieces_info.get("salons", 0)
        count += pieces_info.get("bureaux", 0)
        count += pieces_info.get("sallesAManger", 0)
        return max(count, 1)  # Minimum 1 pièce
