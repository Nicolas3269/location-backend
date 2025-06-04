# Guide d'utilisation de l'API progressive de création de bail

Cette API permet de créer un bail étape par étape plutôt qu'en une seule fois.

## Flux de création progressive

### 1. Étape Propriétaire - `/api/bail/step/landlord/`

**POST** - Créer ou mettre à jour le propriétaire principal

```javascript
const createLandlord = async (landlordData) => {
  const response = await fetch("/api/bail/step/landlord/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      nom: "Dupont",
      prenom: "Jean",
      adresse: "123 Rue de la Paix, 75001 Paris",
      telephone: "+33123456789",
      email: "jean.dupont@email.com",
      iban: "FR1420041010050500013M02606",
    }),
  });

  const result = await response.json();
  // result.proprietaire_id à sauvegarder pour les étapes suivantes
  return result;
};
```

### 2. Étape Bien - `/api/bail/step/property/`

**POST** - Créer le bien et l'associer au propriétaire

```javascript
const createProperty = async (propertyData, proprietaireId) => {
  const response = await fetch("/api/bail/step/property/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      proprietaire_id: proprietaireId,
      adresse: "456 Avenue des Champs, 75008 Paris",
      type_bien: "APPARTEMENT",
      superficie: 75.5,
      nb_pieces: "T3",
      meuble: false,
      classe_dpe: "C",
      // ... autres champs du bien
    }),
  });

  const result = await response.json();
  // result.bien_id à sauvegarder
  return result;
};
```

### 3. Propriétaires additionnels (optionnel) - `/api/bail/step/additional-landlord/`

**POST** - Ajouter un propriétaire supplémentaire

```javascript
const addAdditionalLandlord = async (landlordData, bienId) => {
  const response = await fetch("/api/bail/step/additional-landlord/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      bien_id: bienId,
      nom: "Martin",
      prenom: "Marie",
      adresse: "789 Boulevard Saint-Germain, 75007 Paris",
      telephone: "+33987654321",
      email: "marie.martin@email.com",
    }),
  });

  return await response.json();
};
```

### 4. Étape Locataires - `/api/bail/step/tenants/`

**POST** - Créer ou mettre à jour les locataires

```javascript
const createTenants = async (tenantsData, existingIds = []) => {
  const response = await fetch("/api/bail/step/tenants/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      existing_locataires_ids: existingIds,
      locataires: [
        {
          nom: "Leroy",
          prenom: "Pierre",
          email: "pierre.leroy@email.com",
          telephone: "+33123456789",
          adresse_actuelle: "123 Rue Ancienne, 75010 Paris",
          profession: "Ingénieur",
          revenu_mensuel: 3500.0,
        },
        {
          nom: "Durand",
          prenom: "Sophie",
          email: "sophie.durand@email.com",
          telephone: "+33987654321",
          adresse_actuelle: "456 Rue Ancienne, 75011 Paris",
          profession: "Architecte",
          revenu_mensuel: 3200.0,
        },
      ],
    }),
  });

  const result = await response.json();
  // result.locataires_ids à sauvegarder
  return result;
};
```

### 5. Finalisation - `/api/bail/step/finalize/`

**POST** - Créer le bail final

```javascript
const finalizeBail = async (bailData, bienId, locatairesIds) => {
  const response = await fetch("/api/bail/step/finalize/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      bien_id: bienId,
      locataires_ids: locatairesIds,
      date_debut: "2024-01-01",
      montant_loyer: 1200.0,
      montant_charges: 150.0,
      depot_garantie: 1200.0,
      jour_paiement: 5,
      zone_tendue: false,
      observations: "Bail de location standard",
      is_draft: true,
    }),
  });

  const result = await response.json();
  // result.bail_id contient l'ID du bail créé
  return result;
};
```

### 6. Récupération des données - `/api/bail/progress/{bail_id}/`

**GET** - Récupérer toutes les données d'un bail en cours

```javascript
const getBailProgress = async (bailId) => {
  const response = await fetch(`/api/bail/progress/${bailId}/`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  const result = await response.json();
  // result contient: bail, bien, proprietaires, locataires
  return result;
};
```

## Exemple d'utilisation complète

```javascript
class BailProgressiveCreator {
  constructor() {
    this.proprietaireId = null;
    this.bienId = null;
    this.locatairesIds = [];
    this.bailId = null;
  }

  async createLandlord(data) {
    const result = await createLandlord(data);
    this.proprietaireId = result.proprietaire_id;
    return result;
  }

  async createProperty(data) {
    const result = await createProperty(data, this.proprietaireId);
    this.bienId = result.bien_id;
    return result;
  }

  async addAdditionalLandlord(data) {
    return await addAdditionalLandlord(data, this.bienId);
  }

  async createTenants(data) {
    const result = await createTenants(data, this.locatairesIds);
    this.locatairesIds = result.locataires_ids;
    return result;
  }

  async finalizeBail(data) {
    const result = await finalizeBail(data, this.bienId, this.locatairesIds);
    this.bailId = result.bail_id;
    return result;
  }

  async getBailProgress() {
    if (!this.bailId) return null;
    return await getBailProgress(this.bailId);
  }
}

// Utilisation
const bailCreator = new BailProgressiveCreator();

// Étape 1: Propriétaire
await bailCreator.createLandlord({
  nom: "Dupont",
  prenom: "Jean",
  // ... autres données
});

// Étape 2: Bien
await bailCreator.createProperty({
  adresse: "456 Avenue des Champs",
  type_bien: "APPARTEMENT",
  // ... autres données
});

// Étape 3: Locataires
await bailCreator.createTenants({
  locataires: [
    { nom: "Leroy", prenom: "Pierre" /* ... */ },
    { nom: "Durand", prenom: "Sophie" /* ... */ },
  ],
});

// Étape 4: Finalisation
await bailCreator.finalizeBail({
  date_debut: "2024-01-01",
  montant_loyer: 1200.0,
  // ... autres données du bail
});
```

## Avantages de cette approche

1. **Sauvegarde progressive** : Les données sont sauvegardées à chaque étape
2. **Récupération en cas d'interruption** : L'utilisateur peut reprendre là où il s'est arrêté
3. **Validation étape par étape** : Erreurs détectées plus tôt
4. **Flexibilité** : Possibilité de revenir en arrière et modifier
5. **Meilleure UX** : Feedback immédiat à l'utilisateur

## Gestion d'erreurs

Chaque endpoint retourne une structure cohérente :

```javascript
// Succès
{
  "message": "Propriétaire sauvegardé avec succès",
  "proprietaire_id": 123,
  "data": { /* données sérialisées */ }
}

// Erreur
{
  "error": "Message d'erreur descriptif"
}
```
