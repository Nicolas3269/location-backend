"""
Service responsable du fetch des données depuis la BDD pour pré-remplir les formulaires.

Responsabilité unique : Récupérer les données existantes d'une Location
et les transformer en dictionnaire utilisable par le frontend.
"""

from typing import Any, Dict, Optional

from location.models import Bien, Location, RentTerms
from rent_control.views import get_rent_control_info


class FormDataFetcher:
    """Récupère les données depuis la BDD pour pré-remplir un formulaire."""

    def fetch_location_data(self, location_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère toutes les données d'une Location existante.

        Args:
            location_id: UUID de la location

        Returns:
            Dict avec toutes les données extraites ou None si location inexistante
        """
        try:
            location = Location.objects.get(id=location_id)
            return self._extract_location_data(location)
        except Location.DoesNotExist:
            return None

    def fetch_bien_data(self, bien_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les données d'un Bien pour pré-remplir un formulaire.

        Args:
            bien_id: UUID du bien

        Returns:
            Dict avec les données du bien ou None si inexistant
        """
        try:
            bien = Bien.objects.select_related("bailleur").get(id=bien_id)

            data = {}

            # Données du bien
            if bien:
                data["bien"] = self._extract_bien_data(bien)

            # Données du bailleur
            if bien.bailleurs.exists():
                bailleur = bien.bailleurs.first()
                if bailleur:
                    data["bailleur"] = self._extract_bailleur_data(bailleur)

            return data
        except Bien.DoesNotExist:
            return None

    def _extract_location_data(self, location: Location) -> Dict[str, Any]:
        """
        Extrait les données d'une Location pour pré-remplissage.
        Format aligné avec les serializers.

        Note: Cette fonction fait du mapping inverse (modèle -> formulaire).
        Les field mappings du serializer sont dans l'autre sens (formulaire -> modèle),
        donc on garde le mapping manuel pour l'instant.
        """
        data = {
            "bien": {
                "localisation": {},
                "caracteristiques": {},
                "performance_energetique": {},
                "equipements": {},
                "energie": {},
                "regime": {},
                "zone_reglementaire": {},
            },
            "bailleur": {},
            "locataires": [],
        }

        # RentTerms pour les données financières
        rent_terms = None
        if hasattr(location, "rent_terms"):
            rent_terms: RentTerms = location.rent_terms

        # Données du bien
        if location.bien:
            bien: Bien = location.bien

            # Localisation
            if bien.adresse:
                data["bien"]["localisation"]["adresse"] = bien.adresse
                if bien.latitude:
                    data["bien"]["localisation"]["latitude"] = bien.latitude
                if bien.longitude:
                    data["bien"]["localisation"]["longitude"] = bien.longitude
                # Ajouter area_id
                if bien.latitude and bien.longitude:
                    _, area = get_rent_control_info(bien.latitude, bien.longitude)
                    if area:
                        data["bien"]["localisation"]["area_id"] = area.id

            # Caractéristiques
            if bien.superficie or bien.type_bien:
                data["bien"]["caracteristiques"] = {
                    "superficie": bien.superficie,
                    "type_bien": bien.type_bien,
                    "etage": bien.etage if bien.etage else None,
                    "porte": bien.porte if bien.porte else None,
                    "dernier_etage": bien.dernier_etage,
                    "meuble": bien.meuble,
                }
                if bien.pieces_info:
                    data["bien"]["caracteristiques"]["pieces_info"] = bien.pieces_info

            # Performance énergétique
            if bien.classe_dpe:
                data["bien"]["performance_energetique"] = {
                    "classe_dpe": bien.classe_dpe,
                    "depenses_energetiques": (
                        bien.depenses_energetiques
                        if bien.depenses_energetiques
                        else None
                    ),
                }

            # Régime juridique
            if hasattr(bien, "regime_juridique"):
                data["bien"]["regime"] = {
                    "regime_juridique": bien.regime_juridique or "monopropriete",
                    "periode_construction": bien.periode_construction,
                    "identifiant_fiscal": bien.identifiant_fiscal,
                }

            # Zone réglementaire
            if rent_terms:
                data["bien"]["zone_reglementaire"]["zone_tendue"] = (
                    rent_terms.zone_tendue
                )

            # Équipements
            if (
                hasattr(bien, "annexes_privatives")
                and bien.annexes_privatives is not None
            ):
                if "equipements" not in data["bien"]:
                    data["bien"]["equipements"] = {}
                data["bien"]["equipements"]["annexes_privatives"] = (
                    bien.annexes_privatives
                )

            if (
                hasattr(bien, "annexes_collectives")
                and bien.annexes_collectives is not None
            ):
                if "equipements" not in data["bien"]:
                    data["bien"]["equipements"] = {}
                data["bien"]["equipements"]["annexes_collectives"] = (
                    bien.annexes_collectives
                )

            if hasattr(bien, "information") and bien.information is not None:
                if "equipements" not in data["bien"]:
                    data["bien"]["equipements"] = {}
                data["bien"]["equipements"]["information"] = bien.information

            # Énergie
            if hasattr(bien, "chauffage_type") and bien.chauffage_type is not None:
                chauffage_data = {"type": bien.chauffage_type}
                if bien.chauffage_energie is not None:
                    chauffage_data["energie"] = bien.chauffage_energie
                data["bien"]["energie"]["chauffage"] = chauffage_data

            if hasattr(bien, "eau_chaude_type") and bien.eau_chaude_type is not None:
                eau_chaude_data = {"type": bien.eau_chaude_type}
                if bien.eau_chaude_energie is not None:
                    eau_chaude_data["energie"] = bien.eau_chaude_energie
                data["bien"]["energie"]["eau_chaude"] = eau_chaude_data

        # Données du bailleur
        if location.bien and location.bien.bailleurs.exists():
            bailleur = location.bien.bailleurs.first()
            data["bailleur"] = self._extract_bailleur_data(bailleur)

            # Extraire les co-bailleurs
            all_bailleurs = list(location.bien.bailleurs.all())
            if len(all_bailleurs) > 1:
                co_bailleurs_list = []
                for co_bailleur in all_bailleurs[1:]:
                    if co_bailleur.personne:
                        co_bailleurs_list.append(
                            {
                                "lastName": co_bailleur.personne.lastName,
                                "firstName": co_bailleur.personne.firstName,
                                "email": co_bailleur.personne.email,
                                "adresse": co_bailleur.personne.adresse,
                            }
                        )
                if co_bailleurs_list:
                    data["bailleur"]["co_bailleurs"] = co_bailleurs_list
            else:
                data["bailleur"]["co_bailleurs"] = []

        # Locataires
        if location.locataires.exists():
            data["locataires"] = [
                {
                    "id": str(loc.id),
                    "firstName": loc.firstName,
                    "lastName": loc.lastName,
                    "email": loc.email,
                }
                for loc in location.locataires.all()
            ]
            data["solidaires"] = location.solidaires

        # Modalités financières
        if rent_terms and (rent_terms.montant_loyer or rent_terms.montant_charges):
            data["modalites_financieres"] = {}
            if rent_terms.montant_loyer:
                data["modalites_financieres"]["loyer_hors_charges"] = float(
                    rent_terms.montant_loyer
                )
            if rent_terms.montant_charges:
                data["modalites_financieres"]["charges_mensuelles"] = float(
                    rent_terms.montant_charges
                )

            # Zone tendue - modalités spécifiques
            if rent_terms.zone_tendue:
                data["modalites_zone_tendue"] = {}
                if hasattr(rent_terms, "premiere_mise_en_location"):
                    data["modalites_zone_tendue"]["premiere_mise_en_location"] = (
                        rent_terms.premiere_mise_en_location
                    )
                if hasattr(rent_terms, "locataire_derniers_18_mois"):
                    data["modalites_zone_tendue"]["locataire_derniers_18_mois"] = (
                        rent_terms.locataire_derniers_18_mois
                    )
                if hasattr(rent_terms, "dernier_montant_loyer"):
                    data["modalites_zone_tendue"]["dernier_montant_loyer"] = (
                        float(rent_terms.dernier_montant_loyer)
                        if rent_terms.dernier_montant_loyer
                        else None
                    )

        # Dates
        if location.date_debut or location.date_fin:
            data["dates"] = {}
            if location.date_debut:
                data["dates"]["date_debut"] = location.date_debut.isoformat()
            if location.date_fin:
                data["dates"]["date_fin"] = location.date_fin.isoformat()

        return data

    def _extract_bien_data(self, bien: Bien) -> Dict[str, Any]:
        """Extrait les données d'un Bien (simplifié pour fetch_bien_data)."""
        data = {
            "localisation": {},
            "caracteristiques": {},
            "performance_energetique": {},
            "regime": {},
        }

        # Localisation
        if bien.adresse:
            data["localisation"]["adresse"] = bien.adresse
        if bien.latitude:
            data["localisation"]["latitude"] = bien.latitude
        if bien.longitude:
            data["localisation"]["longitude"] = bien.longitude

        # Caractéristiques
        if bien.superficie or bien.type_bien:
            data["caracteristiques"] = {
                "superficie": bien.superficie,
                "type_bien": bien.type_bien,
                "meuble": bien.meuble,
            }

        # Performance énergétique
        if bien.classe_dpe:
            data["performance_energetique"] = {"classe_dpe": bien.classe_dpe}

        # Régime juridique
        if hasattr(bien, "regime_juridique"):
            data["regime"] = {
                "regime_juridique": bien.regime_juridique or "monopropriete",
            }

        return data

    def _extract_bailleur_data(self, bailleur) -> Dict[str, Any]:
        """Extrait les données d'un Bailleur."""
        data = {}

        if not bailleur:
            return data

        # Mapper "personne" vers "physique" pour cohérence avec le frontend
        bailleur_type = (
            "physique"
            if bailleur.personne
            else "morale"
            if bailleur.societe
            else None
        )
        data["bailleur_type"] = bailleur_type

        if bailleur_type == "physique" and bailleur.personne:
            personne = bailleur.personne
            data["personne"] = {
                "lastName": personne.lastName,
                "firstName": personne.firstName,
                "email": personne.email,
                "adresse": personne.adresse,
            }
        elif bailleur_type == "morale" and bailleur.societe:
            societe = bailleur.societe
            data["societe"] = {
                "raison_sociale": societe.raison_sociale,
                "siret": societe.siret,
                "forme_juridique": societe.forme_juridique,
                "adresse": societe.adresse,
                "email": societe.email,
            }
            if bailleur.signataire:
                data["signataire"] = {
                    "lastName": bailleur.signataire.lastName,
                    "firstName": bailleur.signataire.firstName,
                    "email": bailleur.signataire.email,
                }

        return data
