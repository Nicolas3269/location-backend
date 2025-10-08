# Guide de Debug Playwright avec VSCode

## 🚀 Installation Rapide

```bash
# Installer Playwright (déjà fait avec yarn)
yarn add -D @playwright/test

# Installer les navigateurs
npx playwright install

# Installer l'extension VSCode
# Rechercher "Playwright Test for VSCode" dans les extensions
```

## 🐛 3 Méthodes de Debug

### Méthode 1: Extension Playwright VSCode (Recommandé)

1. **Installer l'extension** : "Playwright Test for VSCode" par Microsoft
2. **Icône Testing** dans la barre latérale VSCode
3. **Cliquer sur le test** pour le lancer
4. **Icône debug** (🐞) pour débugger avec breakpoints

### Méthode 2: Mode UI Interactif

```bash
# Lancer l'interface graphique Playwright
yarn test:e2e:ui

# Ou directement
npx playwright test --ui
```

**Avantages :**
- Interface visuelle
- Timeline des actions
- Voir le DOM à chaque étape
- Rejoueur intégré

### Méthode 3: Mode Debug Pas-à-Pas

```bash
# Mode debug avec inspecteur Playwright
yarn test:e2e:debug

# Pour un fichier spécifique
npx playwright test bail.spec.ts --debug

# Pour un test spécifique
npx playwright test -g "Création bail simple" --debug
```

**Fonctionnalités :**
- Pause à chaque action
- Inspecteur d'éléments
- Console Playwright
- Modification des sélecteurs en temps réel

## 🎯 Breakpoints dans VSCode

### Configuration launch.json (déjà créée)

```json
{
  "name": "Debug Playwright Tests",
  "type": "node",
  "request": "launch",
  "program": "${workspaceFolder}/node_modules/.bin/playwright",
  "args": ["test"],
  "env": {
    "PWDEBUG": "1"
  }
}
```

### Utilisation :

1. **Ajouter breakpoints** dans le code TypeScript (clic sur la marge)
2. **F5** ou **Run → Start Debugging**
3. **Sélectionner** "Debug Playwright Tests"
4. **Naviguer** avec F10 (step over), F11 (step into)

## 🔍 Techniques de Debug Avancées

### 1. Page.pause() - Pause Manuelle

```typescript
test('Mon test', async ({ page }) => {
  await page.goto('/bail');

  // Pause ici pour inspecter
  await page.pause();

  await page.click('button:has-text("Nouvelle location")');
});
```

### 2. Slow Motion - Ralentir l'exécution

```typescript
// Dans playwright.config.ts
use: {
  launchOptions: {
    slowMo: 500, // 500ms entre chaque action
  },
}

// Ou pour un test spécifique
test.use({
  launchOptions: { slowMo: 1000 }
});
```

### 3. Screenshots à la Demande

```typescript
test('Debug visuel', async ({ page }) => {
  await page.goto('/bail');

  // Screenshot pour debug
  await page.screenshot({ path: 'debug-1.png' });

  await page.fill('input[name="adresse"]', '10 rue Test');
  await page.screenshot({ path: 'debug-2.png' });
});
```

### 4. Console Logs du Navigateur

```typescript
// Capturer les logs console du navigateur
page.on('console', msg => console.log('Browser:', msg.text()));
page.on('pageerror', error => console.log('Error:', error));

// Logs dans le navigateur
await page.evaluate(() => {
  console.log('État actuel:', document.querySelector('h2')?.textContent);
});
```

### 5. Attente Conditionnelle

```typescript
// Attendre qu'un élément soit visible
await page.waitForSelector('[data-testid="zone-tendue-badge"]', {
  state: 'visible',
  timeout: 5000
});

// Attendre une réponse API
await page.waitForResponse(response =>
  response.url().includes('/api/location') && response.status() === 200
);
```

## 📊 Analyse des Échecs

### Rapport HTML

```bash
# Générer et ouvrir le rapport
npx playwright show-report

# Après un test échoué
yarn test:e2e && npx playwright show-report
```

### Traces Playwright

```typescript
// Dans playwright.config.ts
use: {
  trace: 'on-first-retry', // ou 'on' pour toujours
}
```

```bash
# Visualiser une trace
npx playwright show-trace trace.zip
```

### Videos des Tests

```typescript
// Dans playwright.config.ts
use: {
  video: 'retain-on-failure', // Garde vidéo si échec
}
```

## 🎨 Sélecteurs Recommandés

### Ordre de Préférence

1. **data-testid** : `[data-testid="zone-tendue-badge"]`
2. **role** : `role=button[name="Suivant"]`
3. **text** : `text="Nouvelle location"`
4. **label** : `label:has-text("Appartement")`

### Test des Sélecteurs

```bash
# Ouvrir le codegen pour tester les sélecteurs
npx playwright codegen localhost:3000

# Inspector pour tester en live
npx playwright test --debug
```

## ⚡ Commandes Utiles

```bash
# Lancer un seul test
yarn playwright test -g "Création bail simple"

# Tests en mode headed (voir le navigateur)
yarn test:e2e:headed

# Tests avec un navigateur spécifique
yarn playwright test --project=chromium

# Tests en parallèle désactivé (plus facile à debug)
yarn playwright test --workers=1

# Générer des sélecteurs automatiquement
npx playwright codegen localhost:3000/bail

# Mettre à jour les snapshots
yarn playwright test --update-snapshots
```

## 🔧 Troubleshooting

### Problème : "Élément non trouvé"

```typescript
// Ajouter des logs pour debug
const element = page.locator('input[name="adresse"]');
console.log('Element count:', await element.count());
console.log('Element visible:', await element.isVisible());

// Attendre explicitement
await page.waitForSelector('input[name="adresse"]', {
  state: 'visible',
  timeout: 10000
});
```

### Problème : "Test timeout"

```typescript
// Augmenter le timeout global
test.setTimeout(60000);

// Ou pour une action spécifique
await page.click('button', { timeout: 30000 });
```

### Problème : "Flaky tests"

```typescript
// Ajouter des waitForLoadState
await page.goto('/bail');
await page.waitForLoadState('networkidle');

// Attendre les animations
await page.waitForTimeout(500);

// Retry automatique
test.describe.configure({ retries: 2 });
```

## 📝 Structure de Test Recommandée

```typescript
test.describe('Feature', () => {
  test.beforeEach(async ({ page }) => {
    // Setup commun
    await page.goto('/bail');
    await page.waitForLoadState('networkidle');
  });

  test.afterEach(async ({ page }, testInfo) => {
    // Screenshot si échec
    if (testInfo.status !== testInfo.expectedStatus) {
      await page.screenshot({
        path: `screenshots/${testInfo.title}.png`
      });
    }
  });

  test('Test spécifique', async ({ page }) => {
    await test.step('Étape 1', async () => {
      // Actions groupées
    });

    await test.step('Étape 2', async () => {
      // Plus d'actions
    });
  });
});
```

## 🚀 Workflow de Debug Recommandé

1. **Commencer avec UI mode** : `yarn test:e2e:ui`
2. **Si échec** : Examiner le rapport HTML
3. **Pour debug détaillé** : Mode debug ou breakpoints VSCode
4. **Pour comprendre** : Ajouter `page.pause()` et explorer
5. **Pour CI/CD** : Utiliser traces et videos

## 💡 Tips Pro

- **Utiliser des fixtures** pour données de test réutilisables
- **Grouper par test.step()** pour meilleure lisibilité
- **Sauvegarder les états** avec `storageState` pour auth
- **Paralléliser intelligemment** avec `fullyParallel: false` pour tests dépendants
- **Mock API calls** avec `route()` pour tests isolés