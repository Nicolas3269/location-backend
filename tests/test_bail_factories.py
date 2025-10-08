"""
Tests unitaires pour les factories de création de bails.

Usage:
    pytest tests/test_bail_factories.py -v
    pytest tests/test_bail_factories.py::test_create_simple_bail -v
"""

import pytest
from location.factories import (
    BienFactory,
    BailleurFactory,
    LocataireFactory,
    LocationFactory,
    BailFactory,
    create_complete_bail,
)
from signature.document_status import DocumentStatus


@pytest.mark.django_db
class TestBailleurFactory:
    """Tests pour BailleurFactory."""

    def test_create_bailleur_personne(self):
        """Test création d'un bailleur personne physique."""
        bailleur = BailleurFactory()
        assert bailleur.personne is not None
        assert bailleur.societe is None
        assert bailleur.signataire == bailleur.personne

    def test_create_bailleur_societe(self):
        """Test création d'un bailleur société."""
        bailleur = BailleurFactory.as_societe()
        assert bailleur.societe is not None
        assert bailleur.personne is None
        assert bailleur.signataire is not None
        assert bailleur.signataire != bailleur.personne


@pytest.mark.django_db
class TestBienFactory:
    """Tests pour BienFactory."""

    def test_create_bien_with_one_bailleur(self):
        """Test création d'un bien avec un bailleur."""
        bien = BienFactory()
        assert bien.bailleurs.count() == 1

    def test_create_bien_with_multiple_bailleurs(self):
        """Test création d'un bien avec plusieurs bailleurs."""
        bien = BienFactory(bailleurs__count=2)
        assert bien.bailleurs.count() == 2

    def test_bien_has_all_required_fields(self):
        """Test que le bien a tous les champs requis."""
        bien = BienFactory()
        assert bien.adresse is not None
        assert bien.type_bien is not None
        assert bien.superficie is not None
        assert bien.pieces_info is not None


@pytest.mark.django_db
class TestLocationFactory:
    """Tests pour LocationFactory."""

    def test_create_location_with_one_locataire(self):
        """Test création d'une location avec un locataire."""
        location = LocationFactory()
        assert location.locataires.count() == 1
        assert location.bien is not None

    def test_create_location_with_multiple_locataires(self):
        """Test création d'une location avec plusieurs locataires."""
        location = LocationFactory(locataires__count=2, solidaires=True)
        assert location.locataires.count() == 2
        assert location.solidaires is True


@pytest.mark.django_db
class TestBailFactory:
    """Tests pour BailFactory."""

    def test_create_simple_bail(self):
        """Test création d'un bail simple."""
        bail = BailFactory()
        assert bail.location is not None
        assert bail.status == DocumentStatus.DRAFT

    def test_bail_has_all_relations(self):
        """Test que le bail a toutes les relations."""
        bail = BailFactory()
        assert bail.location.bien is not None
        assert bail.location.bien.bailleurs.count() >= 1
        assert bail.location.locataires.count() >= 1
        assert hasattr(bail.location, 'rent_terms')

    def test_create_bail_with_custom_status(self):
        """Test création d'un bail avec un statut personnalisé."""
        bail = BailFactory(status=DocumentStatus.SIGNING)
        assert bail.status == DocumentStatus.SIGNING

    def test_create_bail_with_zone_tendue(self):
        """Test création d'un bail en zone tendue."""
        bail = BailFactory(rent_terms__zone_tendue=True)
        assert bail.location.rent_terms.zone_tendue is True


@pytest.mark.django_db
class TestCreateCompleteBail:
    """Tests pour la fonction helper create_complete_bail."""

    def test_create_bail_default(self):
        """Test création d'un bail avec paramètres par défaut."""
        bail = create_complete_bail()
        assert bail.location.locataires.count() == 1
        assert bail.location.solidaires is False
        assert bail.location.rent_terms.zone_tendue is False
        assert bail.status == DocumentStatus.DRAFT

    def test_create_bail_with_multiple_locataires(self):
        """Test création d'un bail avec plusieurs locataires."""
        bail = create_complete_bail(num_locataires=2, solidaires=True)
        assert bail.location.locataires.count() == 2
        assert bail.location.solidaires is True

    def test_create_bail_zone_tendue(self):
        """Test création d'un bail en zone tendue."""
        bail = create_complete_bail(zone_tendue=True)
        assert bail.location.rent_terms.zone_tendue is True

    def test_create_bail_with_custom_address(self):
        """Test création d'un bail avec une adresse personnalisée."""
        bail = create_complete_bail(
            location__bien__adresse="12 Rue de la Paix, 75002 Paris"
        )
        assert "Rue de la Paix" in bail.location.bien.adresse


@pytest.mark.django_db
class TestBienReuse:
    """Tests pour la réutilisation des biens."""

    def test_bien_can_have_multiple_locations(self):
        """Test qu'un bien peut avoir plusieurs locations."""
        bien = BienFactory()

        # Créer 2 locations pour le même bien
        location1 = LocationFactory(bien=bien)
        location2 = LocationFactory(bien=bien)

        assert location1.bien.id == bien.id
        assert location2.bien.id == bien.id
        assert bien.locations.count() == 2

    def test_bailleur_can_have_multiple_biens(self):
        """Test qu'un bailleur peut avoir plusieurs biens."""
        bailleur = BailleurFactory()

        # Créer 2 biens avec le même bailleur
        bien1 = BienFactory(bailleurs=[bailleur])
        bien2 = BienFactory(bailleurs=[bailleur])

        assert bailleur.biens.count() == 2
        assert bien1 in bailleur.biens.all()
        assert bien2 in bailleur.biens.all()
