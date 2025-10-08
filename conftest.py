"""
Configuration pytest pour les tests E2E.

Ce fichier définit des fixtures réutilisables pour tous les tests.
"""

import pytest
from django.conf import settings
from rest_framework.test import APIClient
from location.factories import (
    BienFactory,
    BailleurFactory,
    LocataireFactory,
    LocationFactory,
    RentTermsFactory,
    BailFactory,
    create_complete_bail,
)
from signature.document_status import DocumentStatus


# ==============================
# CONFIGURATION DJANGO POUR TESTS
# ==============================

@pytest.fixture(scope="session", autouse=True)
def configure_django_for_tests():
    """Configure Django settings pour les tests."""
    if "testserver" not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS.append("testserver")
    yield


# ==============================
# FIXTURES DJANGO
# ==============================


@pytest.fixture
def db_access(db):
    """
    Fixture pour accéder à la base de données.
    Simplement importer 'db' de pytest-django.
    """
    return db


# ==============================
# FIXTURES API CLIENT
# ==============================


@pytest.fixture
def api_client():
    """Client API REST Framework pour les tests."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, user):
    """Client API authentifié avec un utilisateur."""
    api_client.force_authenticate(user=user)
    return api_client


# ==============================
# FIXTURES UTILISATEURS
# ==============================


@pytest.fixture
def user(django_user_model):
    """Utilisateur de test basique."""
    return django_user_model.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123"
    )


# ==============================
# FIXTURES ENTITÉS
# ==============================


@pytest.fixture
def personne():
    """Personne physique de test."""
    from location.factories import PersonneFactory
    return PersonneFactory()


@pytest.fixture
def societe():
    """Société de test."""
    from location.factories import SocieteFactory
    return SocieteFactory()


@pytest.fixture
def bailleur():
    """Bailleur personne physique de test."""
    return BailleurFactory()


@pytest.fixture
def bailleur_societe():
    """Bailleur société de test."""
    return BailleurFactory.as_societe()


@pytest.fixture
def locataire():
    """Locataire de test."""
    return LocataireFactory()


# ==============================
# FIXTURES BIENS
# ==============================


@pytest.fixture
def bien():
    """Bien immobilier de test avec un bailleur."""
    return BienFactory()


@pytest.fixture
def bien_paris():
    """Bien situé à Paris."""
    return BienFactory(
        adresse="12 Rue Eugénie Eboué, 75012 Paris, France",
        latitude=48.8566,
        longitude=2.3522
    )


@pytest.fixture
def bien_zone_tendue():
    """Bien en zone tendue."""
    return BienFactory(
        adresse="12 Rue Eugénie Eboué, 75012 Paris, France",
        latitude=48.8566,
        longitude=2.3522
    )


# ==============================
# FIXTURES LOCATIONS
# ==============================


@pytest.fixture
def location(bien):
    """Location de test basique (1 locataire)."""
    return LocationFactory(bien=bien)


@pytest.fixture
def location_with_locataires(bien):
    """Location avec 2 locataires solidaires."""
    return LocationFactory(
        bien=bien,
        locataires__count=2,
        solidaires=True
    )


@pytest.fixture
def rent_terms(location):
    """Modalités financières de test."""
    return RentTermsFactory(location=location)


# ==============================
# FIXTURES BAILS
# ==============================


@pytest.fixture
def bail():
    """
    Bail complet en DRAFT avec toutes les relations.

    Inclut:
    - 1 bien
    - 1 bailleur
    - 1 locataire
    - 1 location
    - RentTerms
    """
    return BailFactory()


@pytest.fixture
def bail_draft():
    """Bail en statut DRAFT."""
    return BailFactory(status=DocumentStatus.DRAFT)


@pytest.fixture
def bail_signing():
    """Bail en statut SIGNING."""
    return BailFactory(status=DocumentStatus.SIGNING)


@pytest.fixture
def bail_signed():
    """Bail en statut SIGNED."""
    return BailFactory(status=DocumentStatus.SIGNED)


@pytest.fixture
def bail_multiple_locataires():
    """Bail avec 2 locataires solidaires."""
    return BailFactory(
        location__locataires__count=2,
        location__solidaires=True
    )


@pytest.fixture
def bail_zone_tendue():
    """Bail en zone tendue."""
    return BailFactory(
        location__bien__adresse="12 Rue Eugénie Eboué, 75012 Paris, France",
        location__bien__latitude=48.8566,
        location__bien__longitude=2.3522,
        rent_terms__zone_tendue=True
    )


# ==============================
# FIXTURES HELPER FUNCTIONS
# ==============================


@pytest.fixture
def create_bail():
    """
    Factory function pour créer des bails personnalisés.

    Usage dans un test:
        def test_something(create_bail):
            bail = create_bail(num_locataires=2, zone_tendue=True)
            assert bail.location.locataires.count() == 2
    """
    return create_complete_bail


# ==============================
# MARKERS PYTEST
# ==============================


def pytest_configure(config):
    """Configure les markers pytest personnalisés."""
    config.addinivalue_line(
        "markers", "e2e: Tests end-to-end complets"
    )
    config.addinivalue_line(
        "markers", "unit: Tests unitaires"
    )
    config.addinivalue_line(
        "markers", "integration: Tests d'intégration"
    )
    config.addinivalue_line(
        "markers", "slow: Tests lents"
    )
