# 🏭 Guide Rapide: Utilisation des Factories

## Dans le Shell Django

```bash
poetry run python manage.py shell
```

```python
# Import des factories
from location.factories import create_complete_bail, BienFactory, BailleurFactory
from signature.document_status import DocumentStatus

# 1. Créer un bail complet rapidement
bail = create_complete_bail()
print(f"Bail créé: {bail.id}")
print(f"Location: {bail.location.id}")
print(f"Bien: {bail.location.bien.adresse}")
print(f"Bailleur: {bail.location.bien.bailleurs.first()}")
print(f"Locataires: {list(bail.location.locataires.all())}")

# 2. Créer un bail avec 2 locataires solidaires en zone tendue
bail = create_complete_bail(
    num_locataires=2,
    solidaires=True,
    zone_tendue=True
)
print(f"Locataires: {bail.location.locataires.count()}")
print(f"Solidaires: {bail.location.solidaires}")
print(f"Zone tendue: {bail.location.rent_terms.zone_tendue}")

# 3. Créer un bail avec une adresse spécifique
bail = create_complete_bail(
    location__bien__adresse="12 Rue de la Paix, 75002 Paris",
    location__bien__latitude=48.8698,
    location__bien__longitude=2.3318
)
print(f"Adresse: {bail.location.bien.adresse}")

# 4. Créer juste un bien pour tester le prefill
bien = BienFactory(
    adresse="123 Rue Test, 75001 Paris",
    type_bien="appartement",
    superficie=75.5,
    bailleurs__count=1
)
print(f"Bien créé: {bien.id}")
print(f"Adresse: {bien.adresse}")
print(f"Bailleur: {bien.bailleurs.first()}")
```

## Dans les Tests Pytest

Voir `tests/README.md` pour le guide complet.

```python
import pytest
from location.factories import create_complete_bail

@pytest.mark.django_db
def test_example():
    bail = create_complete_bail(num_locataires=2)
    assert bail.location.locataires.count() == 2
```

## Exemples Pratiques

### Créer un Bien pour Tester le Prefill

```python
from location.factories import BienFactory

# Créer un bien complet
bien = BienFactory(
    adresse="12 Rue Eugénie Eboué, 75012 Paris, France",
    latitude=48.8566,
    longitude=2.3522,
    type_bien="appartement",
    superficie=45.5,
    meuble=False,
    bailleurs__count=1
)

# Utiliser ce bien pour tester le prefill dans le frontend
print(f"Bien ID: {bien.id}")
print(f"Bailleur ID: {bien.bailleurs.first().id}")

# Tester l'API de prefill
# GET /api/location/forms/bail/requirements/authenticated/?context_mode=from_bien&source_id={bien.id}
```

### Créer un Bailleur pour Tests

```python
from location.factories import BailleurFactory

# Bailleur personne physique
bailleur = BailleurFactory()

# Bailleur société
bailleur = BailleurFactory.as_societe()
```

### Créer Plusieurs Bails pour Tests

```python
from location.factories import create_complete_bail
from signature.document_status import DocumentStatus

# Créer 5 bails différents
bails = []
for i in range(5):
    bail = create_complete_bail(
        num_locataires=1 if i % 2 == 0 else 2,
        solidaires=i % 2 == 1,
        zone_tendue=i % 3 == 0,
        status=DocumentStatus.DRAFT if i < 3 else DocumentStatus.SIGNING
    )
    bails.append(bail)
    print(f"Bail {i+1}: {bail.id} - {bail.status}")
```
