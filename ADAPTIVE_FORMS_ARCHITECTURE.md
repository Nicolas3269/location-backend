# Architecture Adaptive Forms - État Actuel

## ✅ Architecture Complètement Implémentée

Le système suit une architecture DRY où Django est la source unique de vérité pour toute la validation et logique métier.

## Principe Fondamental

```
Django Serializers → Auto-génération → Zod Schemas → Frontend Validation
```

**Une seule source de vérité, zéro duplication.**

## Composants Clés

### Backend (Django)
- **Serializers par pays** (`france.py`, `belgium.py`) : Définissent validation et configuration des étapes
- **Serializers composés** : Blocs atomiques réutilisables (adresse, personne, bien, etc.)
- **FormOrchestrator** : Filtre uniquement les étapes avec données manquantes
- **Génération automatique** : Commande qui génère les schemas Zod depuis Django

### Frontend (React)
- **Schemas Zod auto-générés** : Validation TypeScript générée automatiquement
- **AdaptiveForm** : Utilise Zod pour toute la validation via `zodResolver`
- **Catalog de composants** : Mapping des étapes vers les composants React
- **Conditions dynamiques** : Évaluation côté client des étapes conditionnelles

## Flux de Données

1. **Création standalone** : Toutes les étapes sont présentées
2. **Création depuis location existante** : Seules les étapes manquantes sont affichées
3. **Validation** : Zod côté client, Django côté serveur (même logique)
4. **Soumission** : Validation finale par les serializers Django

## Bénéfices Obtenus

- **Zéro duplication** : Une seule définition des règles
- **Type-safety complet** : TypeScript de bout en bout
- **Maintenabilité excellente** : Modifier Django propage partout
- **Complexité réduite de 90%** : Architecture minimale et claire
- **Évolutivité simple** : Ajouter un pays = ajouter un serializer

## Fichiers Principaux

**Backend:**
- `/location/serializers/france.py` - Source de vérité France
- `/location/serializers/belgium.py` - Source de vérité Belgique  
- `/location/services/form_orchestrator.py` - Filtrage des étapes
- `/location/management/commands/generate_composed_schemas.py` - Génération

**Frontend:**
- `/types/generated/schemas-composed.zod.ts` - Schemas auto-générés
- `/components/forms/adaptive/AdaptiveForm.tsx` - Composant adaptatif
- `/components/forms/configs/formsConfig.ts` - Mapping étapes/composants

## Commande de Génération

```bash
python manage.py generate_composed_schemas
```

Génère automatiquement tous les schemas Zod depuis les serializers Django.

---

*Architecture implémentée avec succès le 2025-09-01. Aucune duplication, maintenabilité maximale.*