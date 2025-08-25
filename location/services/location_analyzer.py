"""
Analyseur de complétude des Locations.
Détermine quels champs sont remplis et lesquels manquent.
"""

from decimal import Decimal
from typing import Any, Dict

from bail.models import Bail
from etat_lieux.models import EtatLieux
from quittance.models import Quittance
from rent_control.choices import ChargeType

from ..models import Location


class LocationAnalyzer:
    """Analyse la complétude d'une Location."""

    def analyze_completeness(self, location: Location) -> Dict[str, Any]:
        """
        Analyse complète d'une Location.

        Returns:
            Dict avec le statut de complétude par section
        """

        analysis = {
            "bien": self._analyze_bien(location),
            "personnes": self._analyze_personnes(location),
            "rent_terms": self._analyze_rent_terms(location),
            "documents": self._analyze_documents(location),
            "overall_completion": 0.0,
        }

        # Calculer le taux de complétude global
        total_fields = 0
        completed_fields = 0

        for section in ["bien", "personnes", "rent_terms"]:
            if section in analysis:
                total_fields += analysis[section].get("total_fields", 0)
                completed_fields += analysis[section].get("completed_fields", 0)

        if total_fields > 0:
            analysis["overall_completion"] = completed_fields / total_fields

        return analysis

    def _analyze_bien(self, location: Location) -> Dict[str, Any]:
        """Analyse la complétude du Bien."""

        if not location.bien:
            return {
                "exists": False,
                "is_complete": False,
                "missing_required": ["bien"],
                "missing_optional": [],
                "completed_fields": 0,
                "total_fields": 15,
            }

        bien = location.bien
        required_fields = {
            "adresse": bien.adresse,
            "type_bien": bien.type_bien,
            "superficie": bien.superficie,
            "pieces_info": bien.pieces_info,
            "regime_juridique": bien.regime_juridique,
        }

        optional_fields = {
            "periode_construction": bien.periode_construction,
            "meuble": bien.meuble,
            "annexes_privatives": bien.annexes_privatives,
            "annexes_collectives": bien.annexes_collectives,
            "information": bien.information,
            "chauffage_type": bien.chauffage_type,
            "eau_chaude_type": bien.eau_chaude_type,
            "classe_dpe": bien.classe_dpe if bien.classe_dpe != "NA" else None,
            "depenses_energetiques": bien.depenses_energetiques,
            "identifiant_fiscal": bien.identifiant_fiscal,
        }

        missing_required = [
            field
            for field, value in required_fields.items()
            if not self._is_value_set(value)
        ]

        missing_optional = [
            field
            for field, value in optional_fields.items()
            if not self._is_value_set(value)
        ]

        completed = len([v for v in required_fields.values() if self._is_value_set(v)])
        completed += len([v for v in optional_fields.values() if self._is_value_set(v)])

        return {
            "exists": True,
            "is_complete": len(missing_required) == 0,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "has_dpe": bien.classe_dpe and bien.classe_dpe != "NA",
            "has_bailleurs": bien.bailleurs.exists(),
            "completed_fields": completed,
            "total_fields": len(required_fields) + len(optional_fields),
        }

    def _analyze_personnes(self, location: Location) -> Dict[str, Any]:
        """Analyse la complétude des Personnes."""

        analysis = {
            "has_bailleur": False,
            "has_locataires": False,
            "has_all_required": False,
            "missing_fields": [],
            "completed_fields": 0,
            "total_fields": 0,
        }

        # Vérifier les bailleurs
        if location.bien and location.bien.bailleurs.exists():
            analysis["has_bailleur"] = True
            bailleur = location.bien.bailleurs.first()

            # Vérifier les infos du bailleur
            if bailleur.personne:
                analysis["bailleur_type"] = "physique"
                analysis["bailleur_complete"] = all(
                    [
                        bailleur.personne.lastName,
                        bailleur.personne.firstName,
                        bailleur.personne.email,
                        bailleur.personne.adresse,
                    ]
                )
            elif bailleur.societe:
                analysis["bailleur_type"] = "morale"
                analysis["bailleur_complete"] = all(
                    [
                        bailleur.societe.siret,
                        bailleur.societe.raison_sociale,
                        bailleur.societe.forme_juridique,
                        bailleur.societe.adresse,
                        bailleur.signataire,
                    ]
                )

            if not analysis.get("bailleur_complete"):
                analysis["missing_fields"].append("bailleur_info")
        else:
            analysis["missing_fields"].append("bailleur")

        # Vérifier les locataires
        if location.locataires.exists():
            analysis["has_locataires"] = True
            analysis["locataires_count"] = location.locataires.count()

            # Vérifier que tous les locataires ont les infos requises
            for loc in location.locataires.all():
                if not all([loc.lastName, loc.firstName, loc.email]):
                    analysis["missing_fields"].append(f"locataire_{loc.id}_info")
        else:
            analysis["missing_fields"].append("locataires")

        # Calculer les champs complétés
        analysis["total_fields"] = 4  # bailleur + locataires minimum
        analysis["completed_fields"] = analysis["total_fields"] - len(
            analysis["missing_fields"]
        )

        analysis["has_all_required"] = (
            analysis["has_bailleur"]
            and analysis["has_locataires"]
            and len(analysis["missing_fields"]) == 0
        )

        return analysis

    def _analyze_rent_terms(self, location: Location) -> Dict[str, Any]:
        """Analyse la complétude des RentTerms."""

        if not hasattr(location, "rent_terms") or not location.rent_terms:
            return {
                "exists": False,
                "is_complete": False,
                "missing_fields": ["rent_terms"],
                "completed_fields": 0,
                "total_fields": 5,
            }

        rent = location.rent_terms

        required_fields = {
            "montant_loyer": rent.montant_loyer,
            "type_charges": rent.type_charges,
            "montant_charges": rent.montant_charges if rent.type_charges else True,
            "jour_paiement": rent.jour_paiement,
            "depot_garantie": rent.depot_garantie,
        }

        missing = [
            field
            for field, value in required_fields.items()
            if not self._is_value_set(value)
        ]

        completed = len([v for v in required_fields.values() if self._is_value_set(v)])

        return {
            "exists": True,
            "is_complete": len(missing) == 0,
            "missing_fields": missing,
            "zone_tendue": rent.zone_tendue,
            "has_rent_price_ref": rent.rent_price_id is not None,
            "completed_fields": completed,
            "total_fields": len(required_fields),
        }

    def _analyze_documents(self, location: Location) -> Dict[str, Any]:
        """Analyse les documents existants pour cette Location."""

        analysis = {
            "has_bail": Bail.objects.filter(location=location).exists(),
            "bail_signed": Bail.objects.filter(
                location=location, date_signature__isnull=False
            ).exists(),
            "quittances_count": Quittance.objects.filter(location=location).count(),
            "has_etat_lieux_entree": EtatLieux.objects.filter(
                location=location, type_etat_lieux="entree"
            ).exists(),
            "has_etat_lieux_sortie": EtatLieux.objects.filter(
                location=location, type_etat_lieux="sortie"
            ).exists(),
        }

        # Dernière quittance
        last_quittance = (
            Quittance.objects.filter(location=location)
            .order_by("-annee", "-mois")
            .first()
        )

        if last_quittance:
            # Créer une date à partir du mois et de l'année
            from datetime import date
            try:
                last_date = date(last_quittance.annee, last_quittance.mois, 1)
                analysis["last_quittance_date"] = last_date.isoformat()
            except (ValueError, TypeError):
                # Si les données ne sont pas valides, on ignore
                pass

        return analysis

    def _is_value_set(self, value: Any) -> bool:
        """Vérifie si une valeur est considérée comme remplie."""

        if value is None:
            return False

        if isinstance(value, str):
            return bool(value.strip())

        if isinstance(value, (list, dict)):
            return bool(value)

        if isinstance(value, (int, float, Decimal)):
            return True

        if isinstance(value, bool):
            return True

        return bool(value)
