"""
Adapters pour convertir les modèles internes vers le format API Mila.

Usage:
    from partenaires.services.mila.adapters import (
        AdresseToMilaAdapter,
        BienToMilaAdapter,
    )

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


class BienValidationError(ValueError):
    """Exception levée quand un bien ne respecte pas les contraintes de l'API Mila."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        errors_str = " | ".join(errors)
        super().__init__(
            f"Le bien ne respecte pas les contraintes pour l'assurance: {errors_str}."
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

    # Contraintes API Mila (from OpenAPI spec)
    MILA_CONSTRAINTS = {
        "surface_min": 1,
        "surface_max": 2000,
        "main_rooms_min": 1,
        "main_rooms_max": 50,
        "floor_min": 0,
        "floor_max": 99,
        "deductibles": [170, 290],
    }

    @classmethod
    def validate_for_mila(
        cls,
        bien: "Bien",
        deductible: int = 170,
    ) -> None:
        """
        Valide qu'un bien respecte les contraintes de l'API Mila.

        Contraintes (OpenAPI spec):
        - surface: 1 à 2000 m²
        - main_rooms_number: 1 à 50
        - floor: 0 à 99 (si appartement)
        - deductible: 170 ou 290

        Args:
            bien: Instance du modèle Bien
            deductible: Franchise demandée

        Raises:
            BienValidationError: Si des contraintes ne sont pas respectées
        """
        errors = []
        constraints = cls.MILA_CONSTRAINTS

        # Validation adresse
        if not bien.adresse:
            errors.append("Le bien doit avoir une adresse")

        # Validation surface
        surface = bien.superficie
        if surface is None:
            errors.append("La superficie est requise")
        elif surface < constraints["surface_min"]:
            errors.append(
                f"Superficie trop petite: {surface}m² "
                f"(min: {constraints['surface_min']}m²)"
            )
        elif surface > constraints["surface_max"]:
            errors.append(
                f"Superficie trop grande: {surface}m² "
                f"(max: {constraints['surface_max']}m²)"
            )

        # Validation nombre de pièces principales
        main_rooms = cls._count_main_rooms(bien.pieces_info or {})
        if main_rooms > constraints["main_rooms_max"]:
            errors.append(
                f"Trop de pièces principales: {main_rooms} "
                f"(max: {constraints['main_rooms_max']})"
            )

        # Validation étage (si appartement)
        if bien.type_bien == "appartement":
            if bien.etage is None:
                errors.append("L'étage est requis pour un appartement")
            elif bien.etage < constraints["floor_min"]:
                errors.append(
                    f"Étage invalide: {bien.etage} (min: {constraints['floor_min']})"
                )
            elif bien.etage > constraints["floor_max"]:
                errors.append(
                    f"Étage trop élevé: {bien.etage} (max: {constraints['floor_max']})"
                )

        # Validation franchise
        if deductible not in constraints["deductibles"]:
            errors.append(
                f"Franchise invalide: {deductible}€ "
                f"(valeurs acceptées: {constraints['deductibles']})"
            )

        # Validation type de bien
        if bien.type_bien and bien.type_bien not in cls.TYPE_BIEN_MAPPING:
            errors.append(
                f"Type de bien non supporté: {bien.type_bien} "
                f"(acceptés: {list(cls.TYPE_BIEN_MAPPING.keys())})"
            )

        if errors:
            raise BienValidationError(errors)

    @classmethod
    def to_mrh_quotation(
        cls,
        bien: "Bien",
        deductible: int = 170,
        effective_date: str | None = None,
        validate: bool = True,
    ) -> dict:
        """
        Convertit un Bien vers le format de tarification MRH Mila.

        Args:
            bien: Instance du modèle Bien
            deductible: Franchise (170 ou 290)
            effective_date: Date d'effet (optionnel, défaut: aujourd'hui)
            validate: Si True (défaut), valide les contraintes Mila

        Returns:
            Dict compatible avec POST /brk/v1/individuals/quotations/homes/compute-pricing

        Raises:
            BienValidationError: Si validate=True et des contraintes Mila
                ne sont pas respectées
        """
        if validate:
            cls.validate_for_mila(bien, deductible)

        # Calculer le nombre de pièces principales
        pieces_principales = cls._count_main_rooms(bien.pieces_info or {})

        payload = {
            "deductible": deductible,
            "real_estate_lot": {
                "address": AdresseToMilaAdapter.to_mila(bien.adresse),
                "real_estate_lot_type": cls.TYPE_BIEN_MAPPING.get(bien.type_bien),
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

        Pièces principales = chambres + séjours + bureaux + salle à manger
        (exclut cuisines, salles de bain, WC, couloirs)

        """
        count = 0
        count += pieces_info.get("chambres", 0)
        count += pieces_info.get("sejours", 0)
        count += pieces_info.get("bureaux", 0)
        count += pieces_info.get("sallesAManger", 0)
        return max(count, 1)  # Minimum 1 pièce
