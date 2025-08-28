# Architecture des Formulaires Adaptatifs - Solution Finale

## Problèmes du Système Actuel

### Points de Complexité
- **Duplication de logique** entre backend et frontend
- **FormOrchestrator trop complexe** avec gestion manuelle de l'ordre
- **Pas de source unique de vérité** pour la validation
- **Mélange des responsabilités** (titres côté backend, validation dupliquée)

## Architecture Finale Simplifiée

### Principe Fondamental
**Utiliser ce qui existe déjà** : Django Serializer → Zod Schema → Frontend

### Séparation des Responsabilités

#### Backend (Django + FormOrchestrator)
- **Définit la structure** : Serializers avec fields et validation
- **Filtre les steps** : Ne retourne que celles avec données manquantes
- **Valide à la soumission** : Sécurité finale côté serveur

#### Frontend
- **Gère la présentation** : Components, questions, UI
- **Valide la navigation** : Utilise le schema Zod généré
- **Map steps → components** : Registry local des steps

### Le Flux Complet

```mermaid
Django Serializer (source de vérité)
    ↓
Generate Zod Schema (commande)
    ↓
Frontend utilise Zod pour validation
    ↓
Backend re-valide à la soumission
```

## Implementation

### 1. Configuration Backend Minimale

```python
# serializers.py - Configuration des steps
class FranceBailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bail
        fields = [...]  # Définit tous les fields avec leur validation
        
        # Configuration minimale : ordre et conditions
        step_config = {
            'bien.localisation': {
                'order': 10,
            },
            'bien.caracteristiques': {
                'order': 20,
            },
            'bailleur.type': {
                'order': 30,
            },
            'bailleur.societe': {
                'order': 40,
                'condition': 'is_personne_morale',  # Step conditionnelle
            },
            'releve_compteurs': {
                'order': 200,
            }
        }
```

### 2. FormOrchestrator Ultra Simple

```python
class FormOrchestrator:
    def get_form_requirements(self, form_type, context):
        """
        Retourne UNIQUEMENT les steps qui manquent des données
        Pas de validation - le frontend utilise Zod pour ça
        """
        serializer = self.get_serializer(form_type)
        existing_data = context.get('existing_data', {})
        
        steps = []
        
        for step_id, config in serializer.step_config.items():
            # Skip si toutes les données de cette step existent
            if self.step_has_complete_data(step_id, existing_data):
                continue
            
            step_def = {
                'id': step_id,
                'order': config['order']
            }
            
            if config.get('condition'):
                step_def['condition'] = config['condition']
            
            steps.append(step_def)
        
        return {
            'steps': sorted(steps, key=lambda x: x['order']),
            'prefill_data': existing_data
        }
    
    def step_has_complete_data(self, step_id, existing_data):
        """
        Vérifie si tous les fields requis de la step ont des données
        """
        # Mapping step → fields (peut être dans le serializer ou séparé)
        fields = self.get_fields_for_step(step_id)
        return all(self.has_value(field, existing_data) for field in fields)
```

### 3. Frontend avec Zod

```typescript
// step-registry.ts - Registry local des steps
const STEP_REGISTRY: Record<string, StepDefinition> = {
  'bien.localisation': {
    component: AddressStep,
    fields: ['adresse'],
    question: "Quelle est l'adresse du logement ?"
  },
  'bien.caracteristiques': {
    component: PropertyDetailsStep,
    fields: ['type_bien', 'superficie', 'nb_pieces'],
    question: "Caractéristiques du logement"
  },
  'bailleur.societe': {
    component: CompanyInfoStep,
    fields: ['siret', 'raison_sociale', 'forme_juridique'],
    question: "Informations de la société"
  },
  'releve_compteurs': {
    component: MetersStep,
    fields: ['electricite.hp', 'electricite.hc', 'gaz.index', 'eau.froide'],
    question: "Relevés des compteurs"
  }
}

// conditions.ts - Dictionnaire des conditions
const CONDITIONS: Record<string, (data: any) => boolean> = {
  'is_personne_morale': (data) => data.bailleur?.type === 'morale',
  'is_zone_tendue': (data) => data.bien?.zone_tendue === true,
  'uses_gas': (data) => {
    const chauffage = data.bien?.energie?.chauffage
    return chauffage?.type === 'individuel' && chauffage?.energie === 'gaz'
  }
}

// validation.ts - Validation pour le bouton "Suivant"
import { BailSchema } from '@/types/generated/schemas.zod'

function canGoNext(stepId: string, formData: any): boolean {
  const stepDef = STEP_REGISTRY[stepId]
  if (!stepDef) return false
  
  // Cas spéciaux (10% des cas)
  if (stepId === 'releve_compteurs') {
    // Au moins un relevé
    return stepDef.fields.some(f => !!formData[f])
  }
  
  // Cas normal (90% des cas) - Utiliser Zod
  try {
    // Extraire les fields de cette step du schema global
    const stepSchema = z.pick(BailSchema.shape, stepDef.fields)
    stepSchema.parse(formData)
    return true
  } catch {
    return false
  }
}
```

## Structures de Données

### Backend Response

```python
# Cas 1: Nouveau bail (aucune donnée)
{
    "steps": [
        {"id": "bien.localisation", "order": 10},
        {"id": "bien.caracteristiques", "order": 20},
        {"id": "bailleur.type", "order": 30},
        {"id": "bailleur.societe", "order": 40, "condition": "is_personne_morale"}
    ],
    "prefill_data": {}
}

# Cas 2: Bail existant (certaines données en DB)
{
    "steps": [
        # "bien.localisation" absent car complet en DB
        {"id": "bien.caracteristiques", "order": 20},
        {"id": "bailleur.societe", "order": 40, "condition": "is_personne_morale"}
    ],
    "prefill_data": {
        "adresse": "10 rue de la Paix",
        "type_bien": "appartement"
    }
}

# Cas 3: Quittance depuis bail existant
{
    "steps": [
        {"id": "periode_quittance", "order": 10}
    ],
    "prefill_data": {
        # Toutes les données du bail existant
    }
}
```

## Avantages de cette Architecture

### 1. Zéro Duplication
- **Une seule source de vérité** : Django Serializer
- **Validation cohérente** : Django → Zod → Frontend
- **Pas de règles custom** à maintenir

### 2. Ultra Simple
- **Backend** : Juste ordre + conditions
- **Frontend** : Registry + Zod validation
- **3 fichiers** au lieu de 10+

### 3. Maintenable
- Modifier le serializer Django met tout à jour
- Ajouter une step = 1 ligne backend + 1 entrée frontend
- Tests faciles à écrire

### 4. Performant
- Pas de calculs complexes
- Cache possible côté frontend
- Réponses backend minimales

## Migration depuis l'Existant

### Étapes
1. **Simplifier FormOrchestrator** : Enlever toute la logique de validation
2. **Générer Zod schemas** : S'assurer que la commande fonctionne
3. **Créer STEP_REGISTRY** : Mapper steps → components + fields
4. **Utiliser Zod pour validation** : Remplacer les validations custom

### Points d'Attention
- Vérifier que tous les serializers ont les bons `required=True/False`
- Tester les cas spéciaux (relevé compteurs "au moins un")
- S'assurer que les conditions sont bien définies côté frontend

## Résumé

**L'architecture finale en 3 points** :

1. **Django définit** la structure et validation (source unique)
2. **Zod transmet** cette validation au frontend (généré automatiquement)
3. **Frontend affiche** en utilisant Zod pour la navigation

**Complexité réduite de 90%** par rapport au système actuel !

---

*Ce document représente l'architecture cible pour les formulaires adaptatifs. L'implementation doit suivre ces principes pour garantir simplicité et maintenabilité.*