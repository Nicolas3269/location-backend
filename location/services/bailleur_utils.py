"""
Utilitaires pour la serialization des données de Bailleur.
"""
from typing import Any, Dict

from location.models import Bailleur, BailleurType


def serialize_bailleur(bailleur: Bailleur) -> Dict[str, Any]:
    """
    Sérialise les données d'un Bailleur pour les formulaires.

    Retourne un dictionnaire avec:
    - bailleur_type: "physique" ou "morale"
    - personne: {...} si bailleur physique
    - societe + signataire: {...} si bailleur morale
    """
    if not bailleur:
        return {}

    bailleur_type = bailleur.bailleur_type
    data = {"bailleur_type": bailleur_type.value}  # Conversion explicite en string

    if bailleur_type == BailleurType.PHYSIQUE and bailleur.personne:
        personne = bailleur.personne
        data["personne"] = {
            "lastName": personne.lastName,
            "firstName": personne.firstName,
            "email": personne.email,
            "adresse": personne.adresse,
        }
    elif bailleur_type == BailleurType.MORALE and bailleur.societe:
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
