# Architecture des Formulaires Adaptatifs

## 🎯 Vue d'Ensemble

Le système de formulaires adaptatifs gère la création et l'édition de 3 types de documents :
- **Bail** (contrat de location)
- **État des lieux** (entrée/sortie)
- **Quittance** (reçu de loyer)

### Principes Fondamentaux

1. **Source unique de vérité** : Django Serializers définissent validation et règles métier
2. **Schemas Zod auto-générés** : `python manage.py generate_composed_schemas`
3. **Formulaires adaptatifs** : Affichent tous les steps sauf ceux qui sont lockés (peuvent être pré-remplis)
4. **Statuts simples** : DRAFT (éditable) → SIGNING (immuable, signature partielle) → SIGNED (immuable, toutes signatures) ou CANCELLED
5. **Approche par contexte** : 4 modes clairs (`new`, `from_bailleur`, `from_bien`, `from_location`)
6. **Field locking cumulatif** : Steps lockées masquées du formulaire selon documents SIGNING/SIGNED

---

## 🎨 Les 4 Context Modes

### Principe Central

**Deux routes distinctes** : une publique (standalone) et une authentifiée (contextualisée).

#### Route Publique (Standalone)
```
GET /api/location/forms/{form_type}/requirements/

Query params:
- location_id (optionnel - pour édition/correction DRAFT)
- type_etat_lieux: "entree" | "sortie" (pour EDL)

Mode: "new" (implicite)
Auth: ❌ Non requis
```

#### Route Authentifiée (Contextualisée)
```
GET /api/location/forms/{form_type}/requirements/authenticated/

Query params:
- context_mode: "from_bailleur" | "from_bien" | "from_location"
- context_source_id (UUID - selon context_mode)
- location_id (optionnel - pour édition/correction)
- type_etat_lieux: "entree" | "sortie" (pour EDL)

Auth: ✅ Requis (@login_required)
```

### Tableau Récapitulatif

| Context Mode | Source | Pre-fill | Locking | Auth | Use Case |
|--------------|--------|----------|---------|------|----------|
| **`new`** | Aucune | ❌ Non (sauf DRAFT) | ❌ Non | ❌ Non | Standalone, édition, correction |
| **`from_bailleur`** | User connecté | ✅ Bailleur | ❌ Non | ✅ Oui | Dashboard → choisit bien |
| **`from_bien`** | Bien (context_source_id) | ✅ Bien + Bailleur | ❌ Non | ✅ Oui | Nouveau locataire sur bien |
| **`from_location`** | Location (context_source_id) | ✅ Toutes données | ✅ SIGNING/SIGNED | ✅ Oui | Locataire/location actuel(le) ou ancien(ne) |

---

## 📋 UX : Choix par Type de Document

### 1. Quittance

**Route standalone** : `/quittance` → context_mode = `new`

**Route depuis bien** : `/mon-compte/mes-biens/{bienId}/quittance`

**UI - Choix du locataire** :
```
┌─────────────────────────────────────────┐
│  Pour qui générer cette quittance ?     │
│  Bien : 15 rue de la Paix              │  ← Pré-sélectionné
├─────────────────────────────────────────┤
│  ○ Nouveau locataire                    │ → context_mode=from_bien
│  ○ Locataire actuel (Dupont Jean)       │ → context_mode=from_location
│  ○ Ancien locataire (Martin Paul)       │ → context_mode=from_location
└─────────────────────────────────────────┘
```

| Choix | Context Mode | Pre-fill | Locking |
|-------|--------------|----------|---------|
| **Nouveau locataire** | `from_bien` | Bien + Bailleur | ❌ Non |
| **Locataire actuel** | `from_location` | Toutes données | ✅ SIGNING/SIGNED |
| **Ancien locataire** | `from_location` | Toutes données | ✅ SIGNING/SIGNED |

### 2. État des Lieux

**Route standalone** : `/etat-lieux` → context_mode = `new`

**Route depuis bien** : `/mon-compte/mes-biens/{bienId}/etat-lieux`

**UI - Choix type + location** :
```
┌─────────────────────────────────────────┐
│  Configuration état des lieux           │
├─────────────────────────────────────────┤
│  Type:                                  │
│  ○ Entrée  ● Sortie                     │
│                                         │
│  Location:                              │
│  ○ Nouvelle location                    │ → context_mode=from_bien
│  ● Location actuelle (Dupont)           │ → context_mode=from_location
│  ○ Ancienne location (Martin)           │ → context_mode=from_location
└─────────────────────────────────────────┘
```

**Important** : EDL entrée et sortie coexistent sur **même location** (distinction par `type_etat_lieux`).

### 3. Bail

**Route standalone** : `/bail` → context_mode = `new`

**Route depuis dashboard** : `/mon-compte/nouveau-bail` → context_mode = `from_bailleur`

**Route depuis bien** : `/mon-compte/mes-biens/{bienId}/bail`

**UI - Choix locataire** :
```
┌─────────────────────────────────────────┐
│  Nouveau bail pour :                    │
│  Bien : 15 rue de la Paix              │
├─────────────────────────────────────────┤
│  ○ Nouveau locataire                    │ → context_mode=from_bien
│  ○ Locataire actuel (Dupont)            │ → context_mode=from_location
│  ○ Ancien locataire (Martin)            │ → context_mode=from_location
└─────────────────────────────────────────┘
```

---

## 🔒 Statuts et Annulation

### Statuts des Documents

| Statut | Éditable ? | Action possible |
|--------|-----------|----------------|
| **DRAFT** | ✅ Oui | Édition directe |
| **SIGNING** | ❌ Non | Annuler (CANCELLED) → créer nouveau avec pre-fill et locking |
| **SIGNED** | ❌ Non | Annuler (CANCELLED) → créer nouveau avec pre-fill et locking |
| **CANCELLED** | ❌ Non | Consultation seule |

### Principe : Pas de versionnage

- **Correction DRAFT** : Éditer directement (pas de signature en cours)
- **Correction SIGNING** : Annuler (CANCELLED) car au moins une personne a déjà signé → créer nouveau document
- **Correction SIGNED** : Annuler (CANCELLED) → créer nouveau document sur **même location**

**Note importante** : SIGNING signifie qu'au moins une partie a signé (ex: bailleur signé, locataire pas encore). On ne peut pas simplement "retourner en DRAFT" car des signatures valides existent déjà.

**Modèles** :
```python
from simple_history.models import HistoricalRecords

class Bail(models.Model):
    location = ForeignKey(Location, related_name='bails')  # ← ForeignKey pour historique
    status = CharField()  # DRAFT, SIGNING, SIGNED, CANCELLED
    cancelled_at = DateTimeField(null=True)

    history = HistoricalRecords()  # Audit trail automatique

    class Meta:
        constraints = [
            # UN SEUL bail SIGNING ou SIGNED par location
            models.UniqueConstraint(
                fields=['location'],
                condition=Q(status__in=['SIGNING', 'SIGNED']),
                name='unique_signing_or_signed_bail_per_location'
            )
        ]

class EtatLieux(models.Model):
    location = ForeignKey(Location, related_name='etats_lieux')  # ← ForeignKey pour historique
    type_etat_lieux = CharField()  # 'entree' ou 'sortie'
    status = CharField()
    cancelled_at = DateTimeField(null=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            # UN SEUL EDL SIGNING ou SIGNED par location ET type
            models.UniqueConstraint(
                fields=['location', 'type_etat_lieux'],
                condition=Q(status__in=['SIGNING', 'SIGNED']),
                name='unique_signing_or_signed_edl_per_location_and_type'
            )
        ]

class Quittance(models.Model):
    location = ForeignKey(Location, related_name='quittances')  # ← ForeignKey (plusieurs quittances possibles)
    periode = DateField()
    status = CharField()
    cancelled_at = DateTimeField(null=True)

    history = HistoricalRecords()

    # Pas de contrainte unique - plusieurs quittances SIGNED possibles (une par mois)
```

**Pourquoi ForeignKey et non OneToOneField** :
- ✅ Historique complet : plusieurs documents (DRAFT/CANCELLED) sur même location
- ✅ Contrainte DB : un seul bail SIGNING/SIGNED à la fois par location
- ✅ django-simple-history trace toutes les modifications automatiquement

### Évolution du Bien entre Locations

**Problématique** : Un bien peut évoluer (rénovation, agrandissement, changement DPE) entre deux locations.

**Solution** : django-simple-history sur le modèle Bien permet de retrouver l'état exact à n'importe quelle date.

**Exemple** :
```python
# Situation
Location AAA (2024-01-01 → 2024-06-30)
├── Bail 1 (SIGNED, date_signature=2024-01-15) - Bien avec 2 chambres
└── EDL Entrée (SIGNED, created_at=2024-01-15) - État avec 2 chambres

# Le bailleur rénove le bien (2024-07-01)
Bien.objects.get(id=123).update(
    nb_chambres=3,
    cuisine_equipee=True,
    dpe_score='B'
)

# Nouvelle location
Location BBB (2024-07-01 → ...)
├── Bail 2 (SIGNED, date_signature=2024-07-10) - Bien avec 3 chambres
└── EDL Entrée (SIGNED, created_at=2024-07-10) - État avec 3 chambres

# Retrouver l'état du bien lors de Location AAA
bail_1 = Bail.objects.get(id=1)
bien_at_signature = bail_1.location.bien.history.as_of(bail_1.date_signature)

print(bien_at_signature.nb_chambres)  # → 2 (état au 2024-01-15)
print(bien_at_signature.dpe_score)    # → C (avant rénovation)

# État actuel du bien
bien_current = Bien.objects.get(id=123)
print(bien_current.nb_chambres)  # → 3 (état actuel)
print(bien_current.dpe_score)    # → B (après rénovation)
```

**Avantages** :
- ✅ Pas de duplication de données (pas de snapshot)
- ✅ Retrouver l'état exact du bien à n'importe quelle date
- ✅ Traçabilité complète pour audit et litiges
- ✅ Conformité légale (preuve de l'état du bien lors de la signature)

**Modèles avec django-simple-history** :
```python
from simple_history.models import HistoricalRecords

class Bien(models.Model):
    nb_chambres = IntegerField()
    dpe_score = CharField()
    # ... autres fields ...

    history = HistoricalRecords()  # ← Historique automatique

class Location(models.Model):
    bien = ForeignKey(Bien)  # ← Pas de snapshot, juste FK
    # ... autres fields ...

    history = HistoricalRecords()
```

**Cas d'usage** :
```python
# Comparer l'état du bien entre EDL entrée et sortie
edl_entree = EtatLieux.objects.get(location=AAA, type_etat_lieux='entree')
edl_sortie = EtatLieux.objects.get(location=AAA, type_etat_lieux='sortie')

bien_at_entree = edl_entree.location.bien.history.as_of(edl_entree.created_at)
bien_at_sortie = edl_sortie.location.bien.history.as_of(edl_sortie.created_at)

if bien_at_entree.nb_chambres != bien_at_sortie.nb_chambres:
    print("⚠️ Le bien a été modifié pendant la location")
```

### Logique cancel_and_replace (Cas 2C/3C/4B)

```python
# Annuler document SIGNING/SIGNED depuis espace utilisateur
@api_view(['POST'])
@login_required
def cancel_bail(request, bail_id):
    bail = get_object_or_404(Bail, id=bail_id)

    # 1. Annuler ancien
    bail.status = 'CANCELLED'
    bail.cancelled_at = timezone.now()
    bail.save()

    # 2. Créer nouveau DRAFT sur même location (pre-fill via frontend)
    return Response({
        "success": True,
        "location_id": bail.location_id,  # Frontend crée nouveau bail avec from_location
        "message": "Bail annulé. Créez un nouveau bail pour corriger."
    })
```

**Résultat** :
```
Location AAA
├── Bail 1 (CANCELLED) - Historique préservé
└── Bail 2 (DRAFT) - Créé via frontend avec context_mode=from_location
```

---

## 🔓 Field Locking

### Principe

Le locking empêche la modification de steps quand des documents liés sont **SIGNING/SIGNED** sur la **même location**.

**Actif uniquement en mode `from_location`.**

### Matrice de Locking

| Document SIGNING/SIGNED | Steps Lockées |
|------------------------|---------------|
| **Bail** | `bien.*`, `bailleur.*`, `locataires[]`, `rent_terms.*` |
| **EDL Entrée** | `bien.equipements.*`, `bien.etat_pieces[]` |
| **EDL Sortie** | `bien.equipements.*`, `bien.etat_pieces[]` |
| **Quittance** | Aucune (jamais de locking) |

### Cumul des Lockings

**Principe** : Union de TOUS les documents SIGNING/SIGNED sur la location.

```python
# form_orchestrator.py
if context_mode == "from_location":
    locked_steps = FieldLockingService.get_locked_steps(context_source_id, country)
    # → Vérifie Bail + EDL Entrée + EDL Sortie
    # → Retourne union des steps lockées
```

**Exemple** :
```
Location AAA:
- Bail SIGNING → Lock bien, bailleur, locataires, rent_terms
- EDL Entrée SIGNED → Lock equipements, etat_pieces

Quittance pour locataire actuel (from_location):
→ Steps lockées = {bien, bailleur, locataires, rent_terms, equipements, etat_pieces}
→ Formulaire = juste période + montants
```

---

## 🎯 Cas d'Usage Concrets

### Cas 1 : EDL Sortie avec Bail + EDL Entrée SIGNING/SIGNED

```
Location AAA:
- Bail SIGNING ✅
- EDL Entrée SIGNED ✅

User → /mon-compte/mes-biens/{bienId}/etat-lieux
     → Choisit Type "Sortie" + Location actuelle AAA
     → context_mode=from_location&context_source_id=AAA

Backend:
1. Génère nouveau document EDL Sortie (location AAA)
2. Pre-fill depuis location AAA
3. Locking cumulatif :
   - Bail SIGNING → Lock bien, bailleur, locataires
   - EDL Entrée SIGNED → Lock equipements, etat_pieces

Frontend:
→ Formulaire court : juste état sortie du bien
→ Bien/bailleur/équipements déjà remplis et lockés
```

### Cas 2A : Corriger Bail DRAFT (depuis `/bail`)

```
Location AAA:
- Bail DRAFT (loyer 800€ au lieu de 850€)

User → /bail?location_id=AAA (mode "new")

Backend:
→ Détecte Bail DRAFT existant
→ Charge le DRAFT pour édition directe
→ User corrige loyer → 850€
→ Soumission → SIGNING puis SIGNED

Résultat:
→ Location AAA
   └── Bail (SIGNED) - Loyer 850€
```

### Cas 2B : Corriger Bail SIGNING/SIGNED (depuis `/bail`)

```
Location AAA:
- Bail SIGNED ✅ (loyer 800€ au lieu de 850€)

User → /bail?location_id=AAA (mode "new")

Backend:
→ Détecte conflit (Bail SIGNING ou SIGNED)
→ Reset automatique : génère nouveau UUID (location_id=BBB)
→ Retourne has_been_renewed: true + nouveau location_id

Frontend (AdaptiveForm.tsx):
→ Détecte has_been_renewed: true
→ Clear localStorage pour ce document
→ Reset currentStep = 0
→ Reset formData (vide)
→ Affiche le formulaire depuis le début

→ User saisit loyer 850€
→ Soumission → SIGNING puis SIGNED

Résultat:
→ Location AAA (Bail 1 SIGNED - Loyer 800€)
→ Location BBB (Bail 2 SIGNED - Loyer 850€)

⚠️ Bail 1 reste SIGNED sur Location AAA (pas annulé)
→ User a maintenant 2 locations et biens distincts
```

### Cas 2C : Corriger Bail SIGNED (depuis `/mon-compte/mes-locations/AAA`)

```
Location AAA:
- Bail SIGNED ✅ (loyer 800€ au lieu de 850€)

User → /mon-compte/mes-locations/AAA
     → Clique "Corriger le bail"

Frontend:
→ Affiche modal avec options :
   - "Annuler ce bail et en créer un nouveau"
   - "Créer un avenant" (future feature)

User choisit "Annuler et créer nouveau":
1. POST /bails/{bailId}/cancel
   → Bail 1 status = CANCELLED
2. POST /bails?location_id=AAA&context_mode=from_location&context_source_id=AAA
   → Crée Bail 2 DRAFT avec pre-fill depuis Bail 1
3. Redirect /bail?bail_id={nouveauBailId}
   → User édite et signe

Résultat:
→ Location AAA (inchangée)
   ├── Bail 1 (CANCELLED) - Loyer 800€
   └── Bail 2 (SIGNED) - Loyer 850€
```

### Cas 3A : Corriger EDL DRAFT (depuis `/etat-lieux`)

```
Location AAA:
- EDL Entrée DRAFT

User → /etat-lieux?location_id=AAA&type_etat_lieux=entree (mode "new")

Backend:
→ Détecte EDL Entrée DRAFT existant
→ Charge le DRAFT pour édition directe
→ User corrige les données
→ Soumission → SIGNING puis SIGNED

Résultat:
→ Location AAA
   └── EDL Entrée (SIGNED)
```

### Cas 3B : Corriger EDL SIGNING/SIGNED (depuis `/etat-lieux`)

```
Location AAA:
- EDL Entrée SIGNED ✅

User → /etat-lieux?location_id=AAA&type_etat_lieux=entree (mode "new")

Backend:
→ Détecte conflit (EDL Entrée SIGNING ou SIGNED)
→ Reset automatique : génère nouveau UUID (location_id=BBB)
→ Retourne has_been_renewed: true + nouveau location_id

Frontend (AdaptiveForm.tsx):
→ Détecte has_been_renewed: true
→ Clear localStorage pour ce document
→ Reset currentStep = 0
→ Reset formData (vide)
→ Affiche le formulaire depuis le début

Résultat:
→ Location AAA (EDL Entrée 1 SIGNED)
→ Location BBB (EDL Entrée 2 SIGNED)

⚠️ EDL 1 reste SIGNED sur Location AAA (pas annulé)
→ User a maintenant 2 locations et biens distincts
```

### Cas 3C : Corriger EDL SIGNED (depuis `/mon-compte/mes-locations/AAA`)

```
Location AAA:
- EDL Entrée SIGNED ✅

User → /mon-compte/mes-locations/AAA
     → Clique "Corriger l'état des lieux d'entrée"

Frontend:
→ Affiche modal avec options :
   - "Annuler cet EDL et en créer un nouveau"

User choisit "Annuler et créer nouveau":
1. POST /etat-lieux/{edlId}/cancel
   → EDL 1 status = CANCELLED
2. POST /etat-lieux?location_id=AAA&context_mode=from_location&context_source_id=AAA&type_etat_lieux=entree
   → Crée EDL 2 DRAFT avec pre-fill depuis EDL 1
3. Redirect /etat-lieux?edl_id={nouveauEdlId}
   → User édite et signe

Résultat:
→ Location AAA (inchangée)
   ├── EDL Entrée 1 (CANCELLED)
   └── EDL Entrée 2 (SIGNED)
```

### Cas 4A : Créer ou Éditer Quittance DRAFT (depuis `/quittance`)

```
# Scénario 1 : Création nouvelle quittance
User → /quittance (mode "new")

Backend:
→ Génère nouveau UUID (location_id=AAA)
→ Crée nouvelle Quittance DRAFT

Frontend:
→ User saisit les données
→ Génération PDF → SIGNED

Résultat:
→ Location AAA
   └── Quittance Octobre (SIGNED)

---

# Scénario 2 : Édition DRAFT existant
User → /quittance?location_id=AAA (mode "new")
Location AAA avec Quittance Octobre DRAFT

Backend:
→ Détecte Quittance DRAFT existante
→ Charge le DRAFT pour édition directe

Frontend:
→ User corrige les données
→ Génération PDF → SIGNED

Résultat:
→ Location AAA
   └── Quittance Octobre (SIGNED)

Note: En mode "new", pas de détection de conflit pour quittances SIGNED
(plusieurs quittances possibles même mois : colocation).
Pour corriger une quittance SIGNED, utiliser le Cas 4B (depuis l'espace utilisateur).
```

### Cas 4B : Corriger Quittance SIGNED (depuis `/mon-compte/mes-biens/{bienId}`)

```
Location AAA:
- Quittance Octobre SIGNED ✅ (montant incorrect)

User → /mon-compte/mes-biens/{bienId}
     → Clique "Corriger la quittance d'Octobre"

Frontend:
→ Affiche modal avec options :
   - "Annuler cette quittance et en créer une nouvelle"

User choisit "Annuler et créer nouvelle":
1. POST /quittances/{quittanceId}/cancel
   → Quittance 1 status = CANCELLED
2. POST /quittances?location_id=AAA&context_mode=from_location&context_source_id=AAA
   → Crée Quittance 2 DRAFT avec pre-fill depuis Quittance 1
3. Redirect /quittance?quittance_id={nouvelleQuittanceId}
   → User édite et génère PDF

Résultat:
→ Location AAA (inchangée)
   ├── Quittance Octobre 1 (CANCELLED)
   └── Quittance Octobre 2 (SIGNED)
```

---

## 🔧 Implémentation Backend

### Routes API

#### Route Publique (Standalone)

```python
@api_view(["GET"])
def get_form_requirements(request, form_type):
    """Route publique - mode standalone (new)"""
    location_id = request.query_params.get("location_id")
    type_etat_lieux = request.query_params.get("type_etat_lieux")

    orchestrator = FormOrchestrator()
    requirements = orchestrator.get_form_requirements(
        form_type=form_type,
        location_id=location_id,
        context_mode="new",
        context_source_id=None,
        type_etat_lieux=type_etat_lieux,
        user=None
    )

    return Response(requirements)
```

#### Route Authentifiée (Contextualisée)

```python
@api_view(["GET"])
@login_required
def get_form_requirements_authenticated(request, form_type):
    """Route protégée - modes from_bailleur/from_bien/from_location"""
    context_mode = request.query_params.get("context_mode")
    context_source_id = request.query_params.get("context_source_id")
    location_id = request.query_params.get("location_id")
    type_etat_lieux = request.query_params.get("type_etat_lieux")

    # Validation du context_mode
    if context_mode not in ["from_bailleur", "from_bien", "from_location"]:
        return Response({"error": "Invalid context_mode"}, status=400)

    orchestrator = FormOrchestrator()
    requirements = orchestrator.get_form_requirements(
        form_type=form_type,
        location_id=location_id,
        context_mode=context_mode,
        context_source_id=context_source_id,
        type_etat_lieux=type_etat_lieux,
        user=request.user
    )

    return Response(requirements)
```

#### URLs

```python
# urls.py
urlpatterns = [
    # Route publique
    path('forms/<str:form_type>/requirements/',
         views.get_form_requirements,
         name='form_requirements'),

    # Route authentifiée
    path('forms/<str:form_type>/requirements/authenticated/',
         views.get_form_requirements_authenticated,
         name='form_requirements_authenticated'),
]
```

### Orchestrator

```python
def get_form_requirements(self, form_type, location_id, context_mode, context_source_id, type_etat_lieux, user):

    # Mode new (standalone)
    if context_mode == "new":
        if location_id:
            # Édition ou correction
            doc = self._get_document(form_type, location_id, type_etat_lieux)
            if doc and doc.status in ['SIGNING', 'SIGNED']:
                # Annuler et créer nouveau
                pass
        else:
            # Nouvelle création
            location_id = uuid4()

        locked_steps = set()  # Pas de locking en mode new

    # Mode from_bailleur
    elif context_mode == "from_bailleur":
        location_id = uuid4()
        # Pre-fill bailleur depuis user
        locked_steps = set()

    # Mode from_bien
    elif context_mode == "from_bien":
        location_id = uuid4()
        # Pre-fill bien + bailleur
        locked_steps = set()

    # Mode from_location
    elif context_mode == "from_location":
        location_id = uuid4()  # Nouveau document
        # Pre-fill depuis location source
        # Locking depuis documents SIGNING/SIGNED
        locked_steps = FieldLockingService.get_locked_steps(context_source_id, country)

    # Retourner requirements
    return {
        "location_id": location_id,
        "locked_steps": list(locked_steps),
        "formData": prefilled_data,
        "requiredSteps": missing_steps
    }
```

---

## 🧹 Nettoyage LocalStorage

### Principe

Quand **l'utilisateur a signé** (statut devient SIGNING ou SIGNED) en mode standalone, **nettoyer le localStorage** pour éviter la pollution de données lors de la prochaine création.

Le nettoyage se fait **dès que l'utilisateur courant a terminé sa signature**, pas forcément quand tous les signataires ont signé.

### Implémentation

**Quand nettoyer** :
- ✅ Après que l'utilisateur a signé (document passe à SIGNING/SIGNED pour lui)
- ✅ Avant la redirection vers l'espace utilisateur
- ✅ Après le countdown (si applicable)

```typescript
// Pour Quittance (dans StepQuittanceResult.tsx)
// Nettoyage après génération du PDF (quittance = auto-signée)
if (quittanceResult?.pdfUrl && bienId && countdown === 0) {
  localStorage.removeItem('quittance-standalone-data')
  localStorage.removeItem('quittance-standalone-progress')
  router.push(`/mon-compte/mes-biens/${bienId}`)
}

// Pour Bail (à implémenter dans le composant de signature/succès)
// Nettoyage après que l'utilisateur a signé (même si locataire n'a pas encore signé)
const handleAfterUserSigned = () => {
  localStorage.removeItem('bail-standalone-data')
  localStorage.removeItem('bail-standalone-progress')
  // Redirection ou affichage message "En attente signature locataire"
}

// Pour État des Lieux (à implémenter dans le composant de signature/succès)
// Nettoyage après que l'utilisateur a signé (même si l'autre partie n'a pas encore signé)
const handleAfterUserSigned = () => {
  localStorage.removeItem('etat-lieux-standalone-data')
  localStorage.removeItem('etat-lieux-standalone-progress')
  // Redirection ou affichage message "En attente signature"
}
```

### Pattern LocalStorage

Clés utilisées par document :
- **Bail** : `bail-standalone-data`, `bail-standalone-progress`
- **EDL** : `etat-lieux-standalone-data`, `etat-lieux-standalone-progress`
- **Quittance** : `quittance-standalone-data`, `quittance-standalone-progress`

---

## 📚 Références Techniques

- **Architecture formulaires adaptatifs** : `/backend/ADAPTIVE_FORMS_ARCHITECTURE.md`
- **Serializers Django (source de vérité)** : `/backend/location/serializers/france.py`
- **Schemas Zod générés** : `/frontend/src/types/generated/schemas-composed.zod.ts`
- **Form orchestrator** : `/backend/location/services/form_orchestrator.py`
- **Field locking** : `/backend/location/services/field_locking.py`
- **AdaptiveForm** : `/frontend/src/components/forms/adaptive/AdaptiveForm.tsx`

### Commandes Importantes

```bash
# Régénérer schemas Zod après modification serializers
cd backend
python manage.py generate_composed_schemas

# Migrations après modification modèles
python manage.py makemigrations
python manage.py migrate
```

---

## 🎯 Résumé Décisionnel

| Décision | Justification |
|----------|---------------|
| **2 routes séparées** | Publique (standalone) vs Authentifiée (contextualisée) - sécurité claire |
| **4 context modes** | Clarté UX + flexibilité technique |
| **ForeignKey (pas OneToOne)** | Historique complet sur même location + prêt pour avenants |
| **Contrainte sur SIGNING/SIGNED** | Un seul document en signature à la fois, plusieurs DRAFT/CANCELLED possibles |
| **Annulation (CANCELLED)** | Pas de suppression, traçabilité complète via `cancelled_at` |
| **django-simple-history** | Audit trail automatique - pas besoin de `version` ou `replaces` |
| **Field locking cumulatif** | Cohérence des données signées |
| **Location = pivot** | Un seul bien/bailleur, plusieurs documents dessus |

## 📝 Migration Nécessaire

**Changements Bail** :
- `OneToOneField(Location)` → `ForeignKey(Location, related_name='bails')`
- Contrainte `unique_active_bail_per_location` → `unique_signing_or_signed_bail_per_location`
- Supprimer champs `is_active`, `version`, `replaces`

**Commande** :
```bash
python manage.py makemigrations
python manage.py migrate
```

**Note** : Vérifier si `EtatLieux` nécessite les mêmes changements
