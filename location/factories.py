"""
Factories pour les tests - Crée des objets complets pour les tests E2E.

Usage dans les tests:
    from location.factories import BailFactory, BienFactory, BailleurFactory

    # Créer un bail complet (bien + bailleur + location + bail)
    bail = BailFactory()

    # Créer avec des données personnalisées
    bail = BailFactory(
        location__bien__adresse="123 Rue de la Paix, 75002 Paris",
        location__locataires__count=2,
        status="signing"
    )

    # Créer juste un bien avec un bailleur
    bien = BienFactory(bailleurs__count=1)
"""

import factory
from factory.django import DjangoModelFactory
from django.utils import timezone
from datetime import date, timedelta

from location.models import (
    Adresse,
    Personne,
    Societe,
    Bailleur,
    Bien,
    Locataire,
    Location,
    RentTerms,
)
from bail.models import Bail
from signature.document_status import DocumentStatus
from rent_control.choices import PropertyType, ConstructionPeriod, RegimeJuridique


# ==============================
# ADRESSE
# ==============================


class AdresseFactory(DjangoModelFactory):
    """Factory pour créer une adresse structurée."""

    class Meta:
        model = Adresse

    voie = factory.Faker("street_name", locale="fr_FR")
    numero = factory.Faker("building_number")
    code_postal = factory.Faker("postcode", locale="fr_FR")
    ville = factory.Faker("city", locale="fr_FR")
    pays = "FR"
    latitude = factory.Faker("latitude")
    longitude = factory.Faker("longitude")


# ==============================
# PERSONNES ET ENTITÉS
# ==============================


class PersonneFactory(DjangoModelFactory):
    """Factory pour créer une personne physique."""

    class Meta:
        model = Personne

    firstName = factory.Faker("first_name", locale="fr_FR")
    lastName = factory.Faker("last_name", locale="fr_FR")
    date_naissance = factory.Faker("date_of_birth", minimum_age=18, maximum_age=80)
    email = factory.LazyAttribute(
        lambda obj: f"{obj.firstName.lower()}.{obj.lastName.lower()}@example.com"
    )
    adresse = factory.Faker("address", locale="fr_FR")
    iban = factory.Faker("iban")


class SocieteFactory(DjangoModelFactory):
    """Factory pour créer une société."""

    class Meta:
        model = Societe

    raison_sociale = factory.Faker("company", locale="fr_FR")
    siret = factory.Sequence(lambda n: f"{n:014d}")  # Génère un SIRET à 14 chiffres
    forme_juridique = factory.Iterator(["SAS", "SARL", "SA", "SCI", "EURL"])
    adresse = factory.Faker("address", locale="fr_FR")
    email = factory.LazyAttribute(
        lambda obj: f"contact@{obj.raison_sociale.lower().replace(' ', '-')}.fr"
    )
    iban = factory.Faker("iban")


class BailleurFactory(DjangoModelFactory):
    """
    Factory pour créer un bailleur (personne physique par défaut).

    Usage:
        # Bailleur personne physique
        bailleur = BailleurFactory()

        # Bailleur société
        bailleur = BailleurFactory.as_societe()
    """

    class Meta:
        model = Bailleur

    # Par défaut: personne physique
    personne = factory.SubFactory(PersonneFactory)
    signataire = factory.LazyAttribute(lambda obj: obj.personne)
    societe = None

    @classmethod
    def as_societe(cls, **kwargs):
        """Créer un bailleur société avec un signataire."""
        return cls(
            personne=None,
            societe=factory.SubFactory(SocieteFactory),
            signataire=factory.SubFactory(PersonneFactory),
            **kwargs,
        )


class LocataireFactory(DjangoModelFactory):
    """Factory pour créer un locataire."""

    class Meta:
        model = Locataire

    firstName = factory.Faker("first_name", locale="fr_FR")
    lastName = factory.Faker("last_name", locale="fr_FR")
    date_naissance = factory.Faker("date_of_birth", minimum_age=18, maximum_age=65)
    email = factory.LazyAttribute(
        lambda obj: f"{obj.firstName.lower()}.{obj.lastName.lower()}@example.com"
    )
    adresse = factory.Faker("address", locale="fr_FR")
    lieu_naissance = factory.Faker("city", locale="fr_FR")
    profession = factory.Faker("job", locale="fr_FR")
    employeur = factory.Faker("company", locale="fr_FR")
    revenu_mensuel = factory.Faker("pydecimal", left_digits=5, right_digits=2, positive=True, min_value=1500, max_value=8000)


# ==============================
# BIENS
# ==============================


class BienFactory(DjangoModelFactory):
    """
    Factory pour créer un bien immobilier.

    Usage:
        # Bien avec un bailleur
        bien = BienFactory()

        # Bien avec plusieurs bailleurs
        bien = BienFactory(bailleurs__count=2)

        # Bien avec adresse spécifique
        bien = BienFactory(adresse__voie="Rue de la Paix", adresse__ville="Paris")
    """

    class Meta:
        model = Bien

    # FK vers Adresse (contient latitude/longitude)
    adresse = factory.SubFactory(AdresseFactory)
    type_bien = PropertyType.APARTMENT
    superficie = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True, min_value=15, max_value=150)
    regime_juridique = RegimeJuridique.MONOPROPRIETE
    periode_construction = ConstructionPeriod.BEFORE_1946
    etage = factory.Faker("random_int", min=0, max=10)
    porte = factory.Faker("random_element", elements=["A", "B", "C", "D", "1", "2"])
    dernier_etage = False
    meuble = False

    # DPE
    classe_dpe = factory.Iterator(["A", "B", "C", "D", "E", "F", "G"])
    depenses_energetiques = "1200 à 1800 € par an"

    # Pièces (JSON)
    pieces_info = factory.LazyFunction(
        lambda: {"chambres": 2, "sejours": 1, "sallesDeBain": 1, "cuisines": 1, "wc": 1}
    )

    # Équipements (JSON)
    annexes_privatives = factory.LazyFunction(
        lambda: {"cave": True, "parking": False, "balcon": True}
    )
    annexes_collectives = factory.LazyFunction(
        lambda: {"local_velo": True, "jardin_commun": False}
    )
    information = factory.LazyFunction(
        lambda: {"ascenseur": True, "digicode": True, "gardien": False}
    )

    # Énergie
    chauffage_type = "individuel"
    chauffage_energie = "gaz"
    eau_chaude_type = "individuel"
    eau_chaude_energie = "electrique"

    @factory.post_generation
    def bailleurs(self, create, extracted, **kwargs):
        """
        Ajoute des bailleurs au bien.

        Usage:
            BienFactory()  # 1 bailleur par défaut
            BienFactory(bailleurs__count=2)  # 2 bailleurs
            BienFactory(bailleurs=[bailleur1, bailleur2])  # Bailleurs existants
        """
        if not create:
            return

        if extracted:
            # Liste de bailleurs fournie
            for bailleur in extracted:
                self.bailleurs.add(bailleur)
        else:
            # Créer le nombre de bailleurs spécifié (default: 1)
            count = kwargs.get("count", 1)
            for _ in range(count):
                self.bailleurs.add(BailleurFactory())


# ==============================
# LOCATIONS
# ==============================


class LocationFactory(DjangoModelFactory):
    """
    Factory pour créer une location (bien + locataires).

    Usage:
        # Location basique (1 locataire)
        location = LocationFactory()

        # Location avec 2 locataires solidaires
        location = LocationFactory(locataires__count=2, solidaires=True)

        # Location avec bien existant
        location = LocationFactory(bien=mon_bien)
    """

    class Meta:
        model = Location

    bien = factory.SubFactory(BienFactory)
    solidaires = False
    date_debut = factory.LazyFunction(lambda: date.today())
    date_fin = factory.LazyFunction(lambda: date.today() + timedelta(days=365))
    created_from = "bail"

    @factory.post_generation
    def locataires(self, create, extracted, **kwargs):
        """
        Ajoute des locataires à la location.

        Usage:
            LocationFactory()  # 1 locataire par défaut
            LocationFactory(locataires__count=2)  # 2 locataires
            LocationFactory(locataires=[locataire1, locataire2])  # Locataires existants
        """
        if not create:
            return

        if extracted:
            # Liste de locataires fournie
            for locataire in extracted:
                self.locataires.add(locataire)
        else:
            # Créer le nombre de locataires spécifié (default: 1)
            count = kwargs.get("count", 1)
            for _ in range(count):
                self.locataires.add(LocataireFactory())


class RentTermsFactory(DjangoModelFactory):
    """
    Factory pour créer les modalités financières d'une location.

    Usage:
        # Modalités de base
        rent_terms = RentTermsFactory(location=ma_location)

        # Zone tendue
        rent_terms = RentTermsFactory(location=ma_location, zone_tendue=True)
    """

    class Meta:
        model = RentTerms

    location = factory.SubFactory(LocationFactory)
    montant_loyer = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True, min_value=500, max_value=2500)
    type_charges = "provisionnelles"
    montant_charges = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True, min_value=50, max_value=300)
    jour_paiement = 5
    depot_garantie = factory.LazyAttribute(lambda obj: obj.montant_loyer)

    # Zone tendue
    zone_tendue = False
    premiere_mise_en_location = True
    locataire_derniers_18_mois = False
    dernier_montant_loyer = None
    permis_de_louer = False


# ==============================
# BAILS
# ==============================


class BailFactory(DjangoModelFactory):
    """
    Factory pour créer un bail complet (bien + bailleur + location + rent_terms + bail).

    Usage:
        # Bail complet en DRAFT
        bail = BailFactory()

        # Bail en SIGNING
        bail = BailFactory(status=DocumentStatus.SIGNING)

        # Bail avec 2 locataires
        bail = BailFactory(location__locataires__count=2, location__solidaires=True)

        # Bail avec adresse spécifique
        bail = BailFactory(
            location__bien__adresse="12 Rue Eugénie Eboué, 75012 Paris, France",
            location__bien__latitude=48.8566,
            location__bien__longitude=2.3522
        )

        # Bail avec zone tendue
        bail = BailFactory(rent_terms__zone_tendue=True)
    """

    class Meta:
        model = Bail

    location = factory.SubFactory(LocationFactory)
    status = DocumentStatus.DRAFT
    duree_mois = 12
    date_signature = factory.LazyFunction(lambda: date.today())
    justificatifs = factory.LazyFunction(list)
    clauses_particulieres = ""
    observations = ""
    travaux_bailleur = ""
    travaux_locataire = ""
    honoraires_ttc = None

    @factory.post_generation
    def rent_terms(self, create, extracted, **kwargs):
        """
        Crée automatiquement les RentTerms pour la location.

        Usage:
            BailFactory()  # RentTerms créés automatiquement
            BailFactory(rent_terms__zone_tendue=True)  # Zone tendue
            BailFactory(rent_terms__montant_loyer=1200)  # Loyer spécifique
        """
        if not create:
            return

        if extracted:
            # RentTerms fourni
            pass  # Déjà lié via location
        else:
            # Créer RentTerms avec les kwargs
            RentTermsFactory(location=self.location, **kwargs)


# ==============================
# HELPERS
# ==============================


def create_complete_bail(
    num_locataires=1,
    solidaires=False,
    zone_tendue=False,
    status=DocumentStatus.DRAFT,
    **kwargs
):
    """
    Helper pour créer un bail complet avec toutes les relations.

    Args:
        num_locataires: Nombre de locataires (default: 1)
        solidaires: Si les locataires sont solidaires (default: False)
        zone_tendue: Si le bien est en zone tendue (default: False)
        status: Statut du bail (default: DRAFT)
        **kwargs: Arguments supplémentaires pour BailFactory

    Returns:
        Bail: Instance de Bail avec toutes les relations créées

    Usage:
        bail = create_complete_bail()
        bail = create_complete_bail(num_locataires=2, solidaires=True, zone_tendue=True)
        bail = create_complete_bail(
            status=DocumentStatus.SIGNING,
            location__bien__adresse="12 Rue de la Paix, 75002 Paris"
        )
    """
    return BailFactory(
        location__locataires__count=num_locataires,
        location__solidaires=solidaires,
        rent_terms__zone_tendue=zone_tendue,
        status=status,
        **kwargs
    )
