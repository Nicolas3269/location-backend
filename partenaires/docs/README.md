# Documentation Partenaires

Ce dossier contient les documentations API et contrats des partenaires externes.

## Structure

```
docs/
├── mila/                              # Mila - Assurance
│   ├── mila_openapi.json              # Spec OpenAPI complète
│   └── mrh_locataire/                 # MRH Locataire (France métro)
│       ├── cgv-mrhind-2024061.docx    # Conditions Générales (modifiable graphiquement)
│       ├── cp-mrhind-2024061-3.docx   # Conditions Particulières (modifiable graphiquement)
│       ├── Devis-mrhind-2024061.docx  # Template devis
│       └── dipa-mrhind-2024061.pdf    # DIPA (NE PAS MODIFIER)
└── README.md
```

---

## Mila - Assurance

### Environnements

| Env | URL API | Documentation |
|-----|---------|---------------|
| Demo | `https://api.demo.mila.care/` | https://apidoc.demo.mila.care |
| Prod | `https://api.service.mila.care/` | - |

### Authentification

```python
# 1. Obtenir un JWT token
POST /auth/brk/v1/login
{
  "username": "xxx",
  "password": "xxx"
}

# Response
{
  "jwt_token": "eyJ...",
  "jwt_token_expiration_delay_seconds": 3600
}

# 2. Utiliser le token
Authorization: Bearer <jwt_token>
```

---

## Produit : MRH Locataire (France métropolitaine)

### Endpoint tarification

```
POST /brk/v1/individuals/quotations/homes/compute-pricing
```

### Request Schema

```python
{
  "effective_date": "2024-12-15",      # Date effet (optionnel, défaut: aujourd'hui)
  "deductible": 170,                    # Franchise: 170€ ou 290€ (requis)
  "real_estate_lot": {
    "address": {
      "address_line1": "123 Rue Example",  # Requis
      "address_line2": "Apt 4B",           # Optionnel
      "postal_code": "75001",              # Requis
      "city": "Paris",                     # Requis
      "country_code": "FR"                 # Requis
    },
    "real_estate_lot_type": "APARTMENT",   # Requis: HOUSE, APARTMENT, etc.
    "surface": 45,                         # Surface m² (requis pour tarif)
    "main_rooms_number": 2,                # Nb pièces principales (requis pour tarif)
    "floor": 3                             # Étage (requis si APARTMENT)
  }
}
```

### Response Schema

```python
[
  {
    "product_label": "MRH Locataire",
    "product_composition_label": "Formule Essentielle",
    "pricing_annual_amount": 156.00,       # Prime annuelle TTC
    "quotation_request": { ... }           # Copie de la request
  },
  {
    "product_label": "MRH Locataire",
    "product_composition_label": "Formule Confort",
    "pricing_annual_amount": 198.00,
    "quotation_request": { ... }
  }
]
```

### Types de lots

| Code | FR | Description |
|------|-----|-------------|
| `HOUSE` | Maison | - |
| `APARTMENT` | Appartement | Étage requis |
| `PARKING` | Parking | - |
| `ISOLATED_GARAGE` | Garage isolé | - |
| `BOX` | Box | - |

### Contraintes

- **Surface** : 1 - 2000 m²
- **Pièces principales** : 1 - 50
- **Étage** : 0 (RDC) - 99
- **Ratio surface/pièces** : ≤ 50 m²/pièce
- **Franchise** : 170€ ou 290€ uniquement

### Format numéro de contrat

```
PO-MRHIND-670000001
PO-MRHIND-670000002
...
```
Exactement 7 chiffres après "67".

---

## Produit : GLI - Garantie Loyers Impayés

*(À documenter si nécessaire)*

- Demandes d'agrément locatif (rental approvals)
- Gestion des entités (locataires, propriétaires, garants)
- Transformation en police d'assurance

---

## Webhooks

Mila envoie des webhooks pour notifier les changements d'état.

| Event | Description |
|-------|-------------|
| `APPROVAL_ACCEPTED` | Sésame accepté |
| `APPROVAL_REFUSED` | Sésame refusé |
| `APPROVAL_WAIT_REQUIRED_DOCUMENTS` | En attente de documents |
| `APPROVAL_REQUIRED_DOCUMENTS_TO_VALIDATE` | Documents à valider |

**Sécurité** : Signature HMAC SHA-256 dans header `mila-api-signature`

---

## Stratégie d'implémentation MRH

### Phase 1 : Client API de base
1. `MilaAuthClient` - Gestion authentification JWT avec refresh automatique
2. `MilaMRHClient` - Client pour endpoint quotation MRH
3. Tests unitaires avec mocks

### Phase 2 : Intégration Frontend
1. Formulaire de devis MRH (adresse, surface, pièces, étage)
2. Affichage des formules et tarifs
3. Sélection de la formule

### Phase 3 : Souscription
1. Génération des documents (CP personnalisées)
2. Signature électronique
3. Envoi à Mila pour création du contrat
4. Stockage référence contrat (PO-MRHIND-67XXXXXXX)

### Phase 4 : Production
1. Tests internes avec Mila
2. Annexe API à signer
3. Mise en production
4. Tableau de suivi mensuel

---

## Ajout d'un nouveau partenaire

1. Créer dossier `docs/<partenaire>/`
2. Y ajouter specs API et documents contractuels
3. Documenter dans ce README
4. Créer client API dans `partenaires/services/<partenaire>/`
5. Créer modèles si nécessaire dans `partenaires/models.py`
