"""
Constantes pour le module location
"""

from enum import StrEnum


class UserRole(StrEnum):
    """
    Rôles utilisateurs pour les formulaires de location.
    Utilisé pour déterminer le parcours du formulaire, les permissions,
    et la construction des URLs.
    """

    BAILLEUR = "bailleur"
    MANDATAIRE = "mandataire"
    LOCATAIRE = "locataire"

    @classmethod
    def choices(cls):
        """Retourne les choices pour Django ChoiceField"""
        return [
            (cls.BAILLEUR, "Bailleur"),
            (cls.MANDATAIRE, "Mandataire"),
            (cls.LOCATAIRE, "Locataire"),
        ]

    @classmethod
    def values(cls):
        """Retourne la liste des valeurs valides"""
        return [cls.BAILLEUR, cls.MANDATAIRE, cls.LOCATAIRE]
