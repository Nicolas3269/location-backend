from django.db.models import TextChoices


class Region(TextChoices):
    PARIS = "PARIS", "Paris"
    EST_ENSEMBLE = "EST_ENSEMBLE", "Est Ensemble"
    PLAINE_COMMUNE = "PLAINE_COMMUNE", "Plaine Commune"
    LYON = "LYON", "Lyon"
    MONTPELLIER = "MONTPELLIER", "Montpellier"
    BORDEAUX = "BORDEAUX", "Bordeaux"
    LILLE = "LILLE", "Lille"
    PAYS_BASQUE = "PAYS_BASQUE", "Pays Basque"


class PropertyType(TextChoices):
    APARTMENT = "appartement", "Appartement"
    HOUSE = "maison", "Maison"


class RegimeJuridique(TextChoices):
    MONOPROPRIETE = "monopropriete", "Monopropriété"
    COPROPRIETE = "copropriete", "Copropriété"


class RoomCount(TextChoices):
    ONE = "1", "1 pièce"
    TWO = "2", "2 pièces"
    THREE = "3", "3 pièces"
    FOUR_PLUS = "4", "4 pièces et plus"


class ConstructionPeriod(TextChoices):
    BEFORE_1946 = "avant 1946", "Avant 1946"
    FROM_1946_TO_1970 = "1946-1970", "1946-1970"
    FROM_1971_TO_1990 = "1971-1990", "1971-1990"
    FROM_1990_TO_2005 = "1990-2005", "1990-2005"
    AFTER_1990 = "apres 1990", "Après 1990"
    AFTER_2005 = "apres 2005", "Après 2005"


class SystemType(TextChoices):
    COLLECTIF = "collectif", "Collectif"
    INDIVIDUEL = "individuel", "Individuel"


class ChargeType(TextChoices):
    FORFAITAIRES = "forfaitaires", "Forfaitaires"
    PROVISIONNELLES = "provisionnelles", "Provisionnelles"
