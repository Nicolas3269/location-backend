# Documentation Hestia - Location Management System

## 📚 Documentation Disponible

### Architecture

- **[Architecture Overview](./architecture-overview.md)** - Vue d'ensemble complète du système
- **[Adaptive Forms Architecture](./adaptive-forms-architecture.md)** - Architecture des formulaires adaptatifs en détail

### Guides de Développement

- **[Testing Strategy](./testing-strategy.md)** - Stratégie et commandes pour tests E2E
- **[Playwright Debug Guide](./playwright-debug-guide.md)** - Debug Playwright avec VSCode
- **[Blog Publication Guide](./blog-publication-guide.md)** - Guide pour publier des articles de blog

## 🚀 Démarrage Rapide

### Commandes Essentielles

```bash
# Backend
cd backend
python manage.py generate_composed_schemas  # Régénérer schemas Zod
python manage.py makemigrations             # Créer migrations
python manage.py migrate                    # Appliquer migrations
python manage.py test                       # Tests Django

# Frontend
cd frontend
npm run dev                                 # Dev server
npm run build                               # Build production
npm run test:e2e                           # Tests E2E
npm run test:e2e:ui                        # Tests E2E UI
```

### Structure du Projet

```
location/
├── backend/
│   ├── location/
│   │   ├── serializers/          # Source de vérité (France, Belgium)
│   │   ├── services/             # FormOrchestrator, DataFetcher, etc.
│   │   ├── types/                # FormState types
│   │   └── api/                  # Routes API
│   ├── bail/                     # Module Bail
│   ├── etat_lieux/              # Module État des lieux
│   └── quittance/               # Module Quittance
├── frontend/
│   ├── src/
│   │   ├── components/forms/adaptive/   # AdaptiveForm
│   │   ├── types/generated/             # Schemas Zod auto-générés
│   │   ├── stores/                      # Zustand stores
│   │   └── app/                         # Pages Next.js
│   └── tests/e2e/               # Tests Playwright
└── CLAUDE.md                    # Instructions projet (à lire en premier !)
```

## 📖 Flux de Développement

### 1. Modifier la validation ou ajouter un champ

1. Modifier le serializer Django (`location/serializers/france.py`)
2. Régénérer les schemas : `python manage.py generate_composed_schemas`
3. Les types TypeScript sont automatiquement mis à jour

### 2. Ajouter un nouveau formulaire

1. Créer serializer avec `get_step_config()` dans `location/serializers/`
2. Ajouter mapping dans `FormOrchestrator._get_serializer_class()`
3. Créer composants React pour les steps
4. Ajouter mapping dans `FORM_COMPONENTS_CATALOG`
5. Ajouter behavior dans `formBehaviors.ts`
6. Régénérer schemas Zod

### 3. Ajouter un nouveau pays

1. Créer `location/serializers/{country}.py`
2. Implémenter serializers avec `get_step_config()`
3. Ajouter mapping dans `FormOrchestrator`
4. Créer templates PDF pour le pays
5. Régénérer schemas Zod

## 🔍 Debugging

### Backend

```bash
# Shell Django
python manage.py shell

# Tests verbeux
python manage.py test --verbosity=2

# Debug toolbar
INSTALLED_APPS += ['debug_toolbar']
```

### Frontend

```bash
# Mode debug Playwright
PWDEBUG=1 npm run test:e2e

# Voir browser pendant tests
npm run test:e2e:headed

# UI interactive
npm run test:e2e:ui
```

## 📝 Standards

### Backend
- Django serializers = Source unique de vérité
- Services pour logique métier (pas dans views)
- Types discriminants pour FormState
- Field locking pour documents signés

### Frontend
- Schemas Zod auto-générés (ne pas modifier manuellement)
- Hooks pour séparation des concerns
- Zustand pour persistance (mode standalone uniquement)
- Design system Hestia (tokens de couleur, pas de hardcode)

## 🆘 Besoin d'Aide ?

1. Lire `CLAUDE.md` à la racine (instructions complètes)
2. Consulter les docs dans ce dossier
3. Voir les exemples dans le code existant
4. Tester avec Playwright UI (`npm run test:e2e:ui`)

---

**Note** : Cette documentation est centralisée dans `backend/docs/` même pour les parties frontend, pour faciliter la navigation.
