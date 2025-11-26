# Stratégie de Tests

## Vue d'ensemble

Tests E2E avec Playwright couvrant les 3 modules principaux :
- **Bail** - Génération et signature
- **État des lieux** - Entrée/sortie
- **Quittance** - Génération

## Structure Tests E2E

```
frontend/tests/e2e/
├── fixtures/
│   ├── test-data.ts      # Données de test
│   └── auth.setup.ts     # Auth config
├── utils/
│   ├── form-helpers.ts   # Helpers formulaires
│   └── pdf-validator.ts  # Validation PDF
└── specs/
    ├── bail/
    ├── etat-lieux/
    └── quittance/
```

## Scénarios Critiques

### Bail
1. **Création basique** - Location nue appartement
2. **Bail meublé** - Avec inventaire
3. **Zone tendue** - Paris avec encadrement loyers
4. **Multi-propriétaires** - Indivision
5. **Colocation** - Clause solidarité
6. **Signature** - Flux complet bailleur → locataires

### État des Lieux
1. **EDL Entrée** - Neuf locataire
2. **EDL Sortie** - Avec dégradations
3. **Comparaison** - Entrée vs Sortie
4. **Photos** - Upload et compression

### Quittance
1. **Génération simple** - Mensuel
2. **Batch** - Multiple mois
3. **Révision loyer** - Avec IRL

## Services à Tester

### MailHog (Emails)
```bash
# Accès: http://localhost:8025
# Vérifier emails signature/notification
```

### Backend API
```bash
# Tests unitaires Django
python manage.py test

# Coverage
coverage run --source='.' manage.py test
coverage report
```

### Frontend
```bash
# Tests composants
npm test

# E2E Playwright
npm run test:e2e
npm run test:e2e:ui  # Mode interactif
```

## Données de Test

### User de test
```typescript
const TEST_USER = {
  email: 'test@example.com',
  password: 'testpass123'
}
```

### Bien de test
```typescript
const TEST_PROPERTY = {
  adresse: '123 Rue Test, 75001 Paris',
  type: 'APPARTEMENT',
  surface: 50
}
```

## Priorités

### P0 - Critiques (blocker release)
- Création bail basique
- Signature complète
- Génération quittance

### P1 - Importantes
- EDL entrée/sortie
- Zone tendue
- Multi-propriétaires

### P2 - Nice to have
- Colocation
- Batch quittances
- Edge cases

## CI/CD

```yaml
# .github/workflows/tests.yml
- Backend tests (Django)
- Frontend tests (Jest)
- E2E tests (Playwright)
- Coverage > 80%
```

## Commandes Utiles

```bash
# Backend
python manage.py test
coverage run --source='.' manage.py test
coverage html

# Frontend
npm test
npm run test:e2e
npm run test:e2e:headed  # Voir browser

# Playwright
npx playwright test
npx playwright test --ui
npx playwright show-report
```

## Debugging

### Playwright
```bash
# Mode debug
PWDEBUG=1 npm run test:e2e

# Screenshots on failure

npx playwright test bail-multi-parties-with-edl.spec.ts --project="chromium"
npx playwright test bail-multi-parties-with-edl.spec.ts --project="chromium" --debug
```

### Django
```python
# Debug toolbar
INSTALLED_APPS += ['debug_toolbar']

# Verbose tests
python manage.py test --verbosity=2
```

---

Pour stratégie complète détaillée, voir repo archive ou demander.
