import decimal
import random
from datetime import date, timedelta

import factory
from factory.django import DjangoModelFactory
from faker import Faker

from rent_control.choices import ConstructionPeriod, PropertyType, RoomCount

from .models import BailSpecificites, Bien, DPEClass, Locataire, Proprietaire

fake = Faker("fr_FR")


class ProprietaireFactory(DjangoModelFactory):
    class Meta:
        model = Proprietaire

    nom = factory.Faker("last_name")
    prenom = factory.Faker("first_name")
    adresse = factory.Faker("address")
    telephone = factory.LazyFunction(lambda: f"+33 {fake.msisdn()[3:]}")
    email = factory.LazyAttribute(
        lambda o: f"{o.prenom.lower()}.{o.nom.lower()}@example.com"
    )
    iban = factory.LazyFunction(lambda: fake.iban())


class BienFactory(DjangoModelFactory):
    class Meta:
        model = Bien

    adresse = factory.Faker("street_address")

    # Coordonnées géographiques françaises approximatives
    latitude = factory.LazyFunction(
        lambda: 46.0 + random.random() * 2
    )  # France: ~46-48 N
    longitude = factory.LazyFunction(
        lambda: 2.0 + random.random() * 3
    )  # France: ~2-5 E

    type_bien = factory.LazyFunction(
        lambda: random.choice([c[0] for c in PropertyType.choices])
    )
    etage = factory.LazyFunction(lambda: random.choice([None, 0, 1, 2, 3, 4, 5]))
    porte = factory.LazyFunction(
        lambda: random.choice(["", "A", "B", "101", "102", "201"])
    )
    dernier_etage = factory.LazyFunction(lambda: random.choice([True, False]))

    periode_construction = factory.LazyFunction(
        lambda: random.choice([c[0] for c in ConstructionPeriod.choices])
    )
    superficie = factory.LazyFunction(
        lambda: decimal.Decimal(random.uniform(20.0, 150.0)).quantize(
            decimal.Decimal("0.01")
        )
    )
    nb_pieces = factory.LazyFunction(
        lambda: random.choice([c[0] for c in RoomCount.choices])
    )
    meuble = factory.LazyFunction(lambda: random.choice([True, False]))

    # Informations DPE
    classe_dpe = factory.LazyFunction(
        lambda: random.choice([c[0] for c in DPEClass.choices])
    )
    depenses_energetiques = factory.LazyFunction(
        lambda: decimal.Decimal(random.uniform(800.0, 2500.0)).quantize(
            decimal.Decimal("0.01")
        )
    )

    # Caractéristiques supplémentaires
    annexes = factory.LazyFunction(
        lambda: random.choice(["", "Cave", "Parking", "Balcon", "Cave et parking"])
    )
    additionnal_description = factory.Faker("paragraph")

    @factory.post_generation
    def proprietaires(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            # Add specific proprietaires if provided
            for proprietaire in extracted:
                self.proprietaires.add(proprietaire)
        else:
            # Add one proprietaire by default
            self.proprietaires.add(ProprietaireFactory())


class LocataireFactory(DjangoModelFactory):
    class Meta:
        model = Locataire

    nom = factory.Faker("last_name")
    prenom = factory.Faker("first_name")
    date_naissance = factory.LazyFunction(
        lambda: fake.date_of_birth(minimum_age=18, maximum_age=70)
    )
    lieu_naissance = factory.Faker("city")
    adresse_actuelle = factory.Faker("address")
    telephone = factory.LazyFunction(lambda: f"+33 {fake.msisdn()[3:]}")
    email = factory.LazyAttribute(
        lambda o: f"{o.prenom.lower()}.{o.nom.lower()}@example.com"
    )

    # Données supplémentaires
    profession = factory.Faker("job")
    employeur = factory.Faker("company")
    revenu_mensuel = factory.LazyFunction(
        lambda: decimal.Decimal(random.uniform(1500.0, 5000.0)).quantize(
            decimal.Decimal("0.01")
        )
    )
    num_carte_identite = factory.LazyFunction(lambda: fake.numerify(text="##########"))
    date_emission_ci = factory.LazyFunction(
        lambda: fake.date_between(start_date="-10y", end_date="today")
    )


class BailSpecificitesFactory(DjangoModelFactory):
    class Meta:
        model = BailSpecificites

    # Relations
    bien = factory.SubFactory(BienFactory)

    # Durée du bail (3 ans par défaut)
    date_debut = factory.LazyFunction(lambda: date.today())
    date_fin = factory.LazyAttribute(lambda o: o.date_debut + timedelta(days=365 * 3))

    # Loyer et charges
    montant_loyer = factory.LazyFunction(
        lambda: decimal.Decimal(random.uniform(500.0, 2000.0)).quantize(
            decimal.Decimal("0.01")
        )
    )
    montant_charges = factory.LazyFunction(
        lambda: decimal.Decimal(random.uniform(50.0, 300.0)).quantize(
            decimal.Decimal("0.01")
        )
    )
    jour_paiement = factory.LazyFunction(lambda: random.randint(1, 10))
    depot_garantie = factory.LazyAttribute(lambda o: o.montant_loyer)

    # Compteurs
    releve_eau_entree = factory.LazyFunction(lambda: str(random.randint(100, 9999)))
    releve_elec_entree = factory.LazyFunction(lambda: str(random.randint(1000, 99999)))
    releve_gaz_entree = factory.LazyFunction(lambda: str(random.randint(100, 9999)))

    # Dates importantes
    date_signature = factory.LazyFunction(
        lambda: date.today() - timedelta(days=random.randint(1, 30))
    )
    date_etat_lieux_entree = factory.LazyAttribute(lambda o: o.date_debut)

    # Commentaires
    observations = factory.Faker("paragraph")

    # Informations d'encadrement des loyers
    zone_tendue = factory.LazyFunction(lambda: random.choice([True, False]))
    prix_reference = factory.LazyFunction(
        lambda: decimal.Decimal(random.uniform(10.0, 30.0)).quantize(
            decimal.Decimal("0.01")
        )
        if random.choice([True, False])
        else None
    )
    complement_loyer = factory.LazyFunction(
        lambda: decimal.Decimal(random.uniform(10.0, 100.0)).quantize(
            decimal.Decimal("0.01")
        )
        if random.choice([True, False])
        else None
    )

    @factory.post_generation
    def locataires(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            # Add specific locataires if provided
            for locataire in extracted:
                self.locataires.add(locataire)
        else:
            # Add one locataire by default
            self.locataires.add(LocataireFactory())
