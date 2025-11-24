"""
Constantes pour le module location
"""


class UserRole:
    """
    Rôles utilisateurs pour les formulaires de location.
    Utilisé pour déterminer le parcours du formulaire et les permissions.
    """
    BAILLEUR = "bailleur"
    MANDATAIRE = "mandataire"

    @classmethod
    def choices(cls):
        """Retourne les choices pour Django ChoiceField"""
        return [
            (cls.BAILLEUR, "Bailleur"),
            (cls.MANDATAIRE, "Mandataire"),
        ]

    @classmethod
    def values(cls):
        """Retourne la liste des valeurs valides"""
        return [cls.BAILLEUR, cls.MANDATAIRE]
