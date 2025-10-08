# Architecture - Vue d'Ensemble

## Principe Fondamental

**Une seule source de vérité** : Django Serializers → Auto-génération → Zod Schemas → Frontend

```
Django (validation + règles métier)
  → python manage.py generate_composed_schemas
    → Zod Schemas TypeScript (auto-générés)
      → Frontend validation (react-hook-form + zodResolver)
```

## Architecture des Formulaires Adaptatifs

### Composants Clés

**Backend** :
- **Serializers par pays** (`france.py`, `belgium.py`) - Source unique de vérité
- **FormOrchestrator** - Filtre steps manquantes, gère field locking
- **FormState types** - Types discriminants (Create, Edit, Extend, Renew)
- **Services** - Data fetching, conflict resolution, field locking

**Frontend** :
- **AdaptiveForm** - Composant universel pour tous les formulaires
- **Schemas Zod auto-générés** - Validation TypeScript depuis Django
- **Hooks** - useFormRequirements, useFormInitialization, useFormPersistence
- **Zustand stores** - Persistance localStorage (mode standalone uniquement)

### 4 Modes de Formulaire (FormState)

1. **Create** - Nouveau document vide
2. **Edit** - Éditer document DRAFT existant
3. **Extend** - Nouveau document depuis source (ex: quittance depuis bail)
4. **Renew** - Créer nouvelle version d'un document signé

### Flux de Données

1. Frontend appelle `/location/forms/{formType}/requirements/` avec FormState
2. Backend (FormOrchestrator) détermine steps à afficher
3. Frontend rend AdaptiveForm avec steps filtrées
4. Validation Zod côté client, Django côté serveur (même logique)
5. Soumission via `/location/create-or-update/`

## Gestion des Documents

### Statuts
- **DRAFT** - Éditable
- **SIGNING** - Immuable, signature en cours
- **SIGNED** - Immuable, toutes signatures complètes
- **CANCELLED** - Annulé

### Field Locking
- Documents SIGNING/SIGNED → Steps correspondantes verrouillées
- Steps verrouillées = skippées dans le formulaire
- Données présentes dans formData (prefill automatique)

### Renouvellement
Si tentative d'édition d'un document SIGNED :
- Backend détecte conflit (ConflictResolver)
- Retourne `has_been_renewed: true` + nouveau `location_id`
- Frontend crée nouveau document avec données copiées

## Modèle de Données

**Location** = Entité pivot centrale
- Contient : bien, bailleur, locataires, rent_terms
- Référencée par : Bail, EtatLieux, Quittance
- Un Bail/EDL/Quittance = Une Location

**GPS → Calculs automatiques** :
- Zone tendue (loi Alur)
- Permis de louer (villes concernées)

## Extensibilité

### Ajouter un nouveau pays
1. Créer `location/serializers/{country}.py` avec serializers
2. Ajouter mapping dans `FormOrchestrator._get_serializer_class()`
3. Régénérer schemas : `python manage.py generate_composed_schemas`

### Ajouter un nouveau type de formulaire
1. Définir serializer avec `get_step_config()`
2. Créer composants React pour les steps
3. Ajouter mapping dans `FORM_COMPONENTS_CATALOG`
4. Ajouter behavior dans `formBehaviors.ts`

## Commandes Importantes

```bash
# Régénérer schemas Zod depuis Django
python manage.py generate_composed_schemas

# Créer migrations après modification modèle
python manage.py makemigrations
python manage.py migrate
```

## Fichiers Critiques

### Backend
- `/location/serializers/france.py` - Source de vérité France
- `/location/services/form_orchestrator.py` - Orchestrateur central
- `/location/types/form_state.py` - Types discriminants
- `/location/api/form_requirements.py` - Routes API

### Frontend
- `/types/generated/schemas-composed.zod.ts` - Schemas auto-générés
- `/components/forms/adaptive/AdaptiveForm.tsx` - Composant principal
- `/components/forms/configs/formsConfig.ts` - Mapping steps/composants
- `/stores/*FormStore.ts` - Zustand stores pour persistance

## Bénéfices

- ✅ **Zéro duplication** - Une seule source de vérité
- ✅ **Type-safety** - TypeScript bout en bout
- ✅ **Maintenabilité** - Modifier Django propage partout
- ✅ **Scalabilité** - Ajouter pays/formulaire simplement
- ✅ **Complexité réduite** - Architecture minimale et claire

---

Pour plus de détails, voir :
- `adaptive-forms-architecture.md` - Architecture complète
- `CLAUDE.md` - Instructions projet
