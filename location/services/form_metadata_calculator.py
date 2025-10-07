"""
Service responsable du calcul des métadonnées automatiques.

Responsabilité unique : Calculer zone tendue, permis de louer, et autres
métadonnées dérivées des données de localisation.
"""

from typing import Any, Dict, Optional


class FormMetadataCalculator:
    """Calcule les métadonnées automatiques pour un formulaire."""

    def calculate_metadata(
        self, form_data: Dict[str, Any], country: str = "FR"
    ) -> Dict[str, Any]:
        """
        Calcule toutes les métadonnées automatiques.

        Args:
            form_data: Données du formulaire
            country: Code pays (FR, BE)

        Returns:
            Dict avec les métadonnées calculées
        """
        metadata = {}

        # Extraction des coordonnées GPS
        latitude = self._extract_latitude(form_data)
        longitude = self._extract_longitude(form_data)

        if latitude and longitude and country == "FR":
            # Zone tendue (seulement France)
            zone_tendue = self._calculate_zone_tendue(latitude, longitude)
            if zone_tendue is not None:
                metadata["zone_tendue"] = zone_tendue

            # Permis de louer (seulement France)
            permis_louer = self._calculate_permis_louer(latitude, longitude)
            if permis_louer is not None:
                metadata["permis_de_louer"] = permis_louer

        return metadata

    def _extract_latitude(self, form_data: Dict[str, Any]) -> Optional[float]:
        """Extrait la latitude depuis les données du formulaire."""
        try:
            return form_data.get("bien", {}).get("localisation", {}).get("latitude")
        except (AttributeError, KeyError):
            return None

    def _extract_longitude(self, form_data: Dict[str, Any]) -> Optional[float]:
        """Extrait la longitude depuis les données du formulaire."""
        try:
            return form_data.get("bien", {}).get("localisation", {}).get("longitude")
        except (AttributeError, KeyError):
            return None

    def _calculate_zone_tendue(
        self, latitude: float, longitude: float
    ) -> Optional[bool]:
        """
        Détermine si le bien est en zone tendue.

        TODO: Implémenter la logique réelle avec une API ou base de données
        des zones tendues.

        Args:
            latitude: Latitude GPS
            longitude: Longitude GPS

        Returns:
            True si en zone tendue, False sinon, None si impossible à déterminer
        """
        # Pour l'instant, retourner None pour laisser l'utilisateur choisir
        # À implémenter avec API geo.gouv.fr ou base de données
        return None

    def _calculate_permis_louer(
        self, latitude: float, longitude: float
    ) -> Optional[bool]:
        """
        Détermine si un permis de louer est requis.

        TODO: Implémenter la logique réelle avec API ou base de données
        des communes nécessitant un permis de louer.

        Args:
            latitude: Latitude GPS
            longitude: Longitude GPS

        Returns:
            True si permis requis, False sinon, None si impossible à déterminer
        """
        # Pour l'instant, retourner None pour laisser l'utilisateur choisir
        # À implémenter avec API geo.gouv.fr ou base de données
        return None

    def enrich_with_rent_control(
        self, form_data: Dict[str, Any], country: str = "FR"
    ) -> Dict[str, Any]:
        """
        Enrichit les données avec les informations d'encadrement des loyers.

        Args:
            form_data: Données du formulaire
            country: Code pays

        Returns:
            Dict enrichi avec les données de rent control
        """
        if country != "FR":
            return form_data

        # Vérifier si on a les données nécessaires pour le rent control
        latitude = self._extract_latitude(form_data)
        longitude = self._extract_longitude(form_data)

        if not latitude or not longitude:
            return form_data

        # TODO: Appeler l'API rent_control pour enrichir
        # from rent_control.views import get_rent_control_info
        # rent_info = get_rent_control_info(latitude, longitude)

        return form_data
