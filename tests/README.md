# Guide des Tests et Factories

## 📦 Installation

Les dépendances de test sont déjà installées si vous avez exécuté `poetry install`. Sinon:

```bash
poetry add --group dev pytest pytest-django
```

## 🚀 Lancer les Tests

```bash
# Tous les tests
poetry run pytest

# Tests spécifiques
poetry run pytest tests/test_bail_factories.py
poetry run pytest tests/test_bail_factories.py::TestBailFactory
poetry run pytest tests/test_bail_factories.py::TestBailFactory::test_create_simple_bail

# Avec output verbeux
poetry run pytest -v

# Seulement les tests marqués
poetry run pytest -m unit
poetry run pytest -m integration
poetry run pytest -m e2e
```

## 🏭 Utilisation des Factories

Les factories permettent de créer rapidement des objets complets pour les tests.

### 📝 Imports

```python
from location.factories import (
    BienFactory,
    BailleurFactory,
    LocataireFactory,
    LocationFactory,
    BailFactory,
    create_complete_bail,
)
```

### 👤 Créer un Bailleur

```python
# Bailleur personne physique
bailleur = BailleurFactory()

# Bailleur société
bailleur = BailleurFactory.as_societe()
```

### 🏠 Créer un Bien

```python
# Bien avec 1 bailleur (par défaut)
bien = BienFactory()

# Bien avec plusieurs bailleurs
bien = BienFactory(bailleurs__count=2)

# Bien avec adresse spécifique
bien = BienFactory(adresse__voie="Rue de la Paix", adresse__ville="Paris")

# Bien complet personnalisé
bien = BienFactory(
    adresse__voie="Avenue des Champs-Élysées",
    adresse__numero="123",
    adresse__code_postal="75008",
    adresse__ville="Paris",
    adresse__latitude=48.8698,
    adresse__longitude=2.3318,
    type_bien="appartement",
    superficie=85.5,
    meuble=True,
    bailleurs__count=1
)
```

### 📄 Créer un Bail Complet

```python
# Bail minimal (1 locataire, DRAFT)
bail = BailFactory()

# Bail personnalisé
bail = BailFactory(
    status=DocumentStatus.SIGNING,
    location__locataires__count=2,
    location__solidaires=True,
    rent_terms__zone_tendue=True,
    rent_terms__montant_loyer=1500
)

# Bail avec adresse spécifique
bail = BailFactory(
    location__bien__adresse="12 Rue Eugénie Eboué, 75012 Paris"
)
```

### ⚡ Helper `create_complete_bail`

Pour des cas d'usage courants, utilisez la fonction helper:

```python
# Bail par défaut
bail = create_complete_bail()

# Bail avec 2 locataires solidaires
bail = create_complete_bail(num_locataires=2, solidaires=True)

# Bail en zone tendue
bail = create_complete_bail(zone_tendue=True)

# Bail en statut SIGNING
bail = create_complete_bail(status=DocumentStatus.SIGNING)

# Combinaison
bail = create_complete_bail(
    num_locataires=2,
    solidaires=True,
    zone_tendue=True,
    status=DocumentStatus.SIGNING,
    location__bien__adresse="12 Rue de la Paix, 75002 Paris"
)
```

## 🧪 Exemples de Tests

### Test Unitaire Simple

```python
import pytest
from location.factories import BailleurFactory

@pytest.mark.django_db
def test_create_bailleur():
    bailleur = BailleurFactory()
    assert bailleur.personne is not None
    assert bailleur.signataire == bailleur.personne
```

### Test avec Fixture

```python
import pytest

@pytest.mark.django_db
def test_bail_has_relations(bail):
    """Utilise la fixture 'bail' du conftest.py"""
    assert bail.location is not None
    assert bail.location.bien is not None
    assert bail.location.locataires.count() >= 1
```

### Test de Réutilisation d'Entités

```python
import pytest
from location.factories import BienFactory, LocationFactory

@pytest.mark.django_db
def test_bien_can_have_multiple_locations():
    # Créer un bien
    bien = BienFactory()

    # Créer 2 locations pour le même bien
    location1 = LocationFactory(bien=bien)
    location2 = LocationFactory(bien=bien)

    # Vérifications
    assert location1.bien.id == bien.id
    assert location2.bien.id == bien.id
    assert bien.locations.count() == 2
```

## 📋 Fixtures Disponibles

Les fixtures sont définies dans `conftest.py` et disponibles automatiquement:

### Entités de Base

- `personne` - Personne physique
- `societe` - Société
- `bailleur` - Bailleur personne physique
- `bailleur_societe` - Bailleur société
- `locataire` - Locataire

### Biens

- `bien` - Bien avec 1 bailleur
- `bien_paris` - Bien à Paris avec coordonnées GPS
- `bien_zone_tendue` - Bien en zone tendue

### Locations

- `location` - Location avec 1 locataire
- `location_with_locataires` - Location avec 2 locataires solidaires
- `rent_terms` - Modalités financières

### Bails

- `bail` - Bail en DRAFT
- `bail_draft` - Bail en DRAFT
- `bail_signing` - Bail en SIGNING
- `bail_signed` - Bail en SIGNED
- `bail_multiple_locataires` - Bail avec 2 locataires
- `bail_zone_tendue` - Bail en zone tendue

### Helpers

- `create_bail` - Fonction factory pour créer des bails personnalisés

### Exemple d'utilisation des fixtures

```python
import pytest

@pytest.mark.django_db
def test_with_existing_bien(bien_paris):
    """Test avec un bien existant à Paris"""
    assert "Paris" in bien_paris.adresse.ville
    assert bien_paris.adresse.latitude is not None

@pytest.mark.django_db
def test_create_custom_bail(create_bail):
    """Test avec factory function"""
    bail = create_bail(num_locataires=3, zone_tendue=True)
    assert bail.location.locataires.count() == 3
    assert bail.location.rent_terms.zone_tendue is True
```

## 🎯 Cas d'Usage Pratiques

### Tester la Réutilisation d'un Bien

```python
@pytest.mark.django_db
def test_bien_reuse_no_duplicate():
    from location.models import Bien

    # Créer un bien
    bien = BienFactory()
    bien_count_before = Bien.objects.count()

    # Créer un bail depuis ce bien (simulation PrefillFormState)
    bail = BailFactory(location__bien=bien)

    # Vérifier qu'aucun nouveau bien n'est créé
    bien_count_after = Bien.objects.count()
    assert bien_count_after == bien_count_before
```

### Tester un Workflow Complet

```python
@pytest.mark.django_db
def test_bail_workflow():
    # 1. Créer un bien avec bailleur
    bien = BienFactory(adresse="Test Address")

    # 2. Créer une location avec locataire
    location = LocationFactory(bien=bien, locataires__count=1)

    # 3. Créer les modalités financières
    rent_terms = RentTermsFactory(
        location=location,
        montant_loyer=1200,
        zone_tendue=True
    )

    # 4. Créer le bail
    bail = BailFactory(location=location, status=DocumentStatus.DRAFT)

    # Vérifications
    assert bail.location.bien.adresse == "Test Address"
    assert bail.location.rent_terms.zone_tendue is True
    assert bail.status == DocumentStatus.DRAFT
```

### Tester le Verrouillage des Champs

```python
@pytest.mark.django_db
def test_locked_fields_from_signed_bail(bail_signed, api_client):
    """Test que les champs sont verrouillés depuis un bail signé"""
    response = api_client.get(
        f"/api/location/forms/bail/requirements/authenticated/",
        {"location_id": str(bail_signed.location.id)}
    )

    data = response.json()
    assert len(data.get("locked_steps", [])) > 0
```

## 📚 Structure des Fichiers

```
backend/
├── conftest.py                    # Fixtures pytest globales
├── pytest.ini                     # Configuration pytest
├── location/
│   └── factories.py              # Factory definitions
└── tests/
    ├── README.md                 # Ce fichier
    ├── test_bail_factories.py    # Tests unitaires des factories
    └── test_bail_creation_e2e.py # Tests E2E (à implémenter)
```

## ⚙️ Configuration

### pytest.ini

```ini
[pytest]
DJANGO_SETTINGS_MODULE = backend.settings
testpaths = tests
addopts = --verbose --reuse-db --nomigrations

markers =
    unit: Tests unitaires rapides
    integration: Tests d'intégration
    e2e: Tests end-to-end complets
    slow: Tests lents
```

### Markers Personnalisés

```python
@pytest.mark.unit
def test_fast_unit_test():
    pass

@pytest.mark.e2e
@pytest.mark.slow
def test_slow_integration():
    pass
```

## 💡 Tips

1. **Réutiliser la DB entre tests** : `--reuse-db` (déjà configuré)
2. **Pas de migrations** : `--nomigrations` (déjà configuré)
3. **Déboguer un test** : Ajouter `import pdb; pdb.set_trace()`
4. **Voir les print()** : Utiliser `-s` flag
5. **Tests parallèles** : Installer `pytest-xdist` et utiliser `-n auto`

## 🐛 Troubleshooting

### "No module named 'location.factories'"

Assurez-vous d'être dans le bon répertoire:
```bash
cd /home/havardn/location/backend
poetry run pytest
```

### "django.core.exceptions.ImproperlyConfigured"

Vérifiez que `DJANGO_SETTINGS_MODULE` est correct dans `pytest.ini`.

### Tests lents

Utilisez `--reuse-db` et `--nomigrations` (déjà configurés par défaut).

## 📖 Ressources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-django Documentation](https://pytest-django.readthedocs.io/)
- [factory_boy Documentation](https://factoryboy.readthedocs.io/)
