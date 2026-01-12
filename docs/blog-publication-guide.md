# 📝 Guide de publication d'articles - Hestia Blog

## Workflow simple pour publier un nouvel article

### 1. Création du contenu avec ChatGPT

**Prompt recommandé :**

```
Écris-moi un article de blog sur [SUJET] au format HTML pur pour un blog immobilier.

Utilise ces classes CSS pour le styling :
- <ul class="checklist checklist-success"> pour les listes à puces positives (✓)
- <ul class="checklist checklist-warning"> pour les listes d'attention (⚠️)
- <ul class="checklist checklist-info"> pour les listes d'information (ℹ️)
- <div class="alert alert-info"> pour les encadrés d'information
- <div class="alert alert-warning"> pour les avertissements
- <div class="cta-box"> pour les call-to-action
- <div class="warning-box"> pour les boîtes d'avertissement
- <ul class="tips-list"> pour les listes de conseils

Structure :
- Commence directement par <article>
- Utilise h2, h3, h4 pour la hiérarchie
- Paragraphes courts et accessibles
- Ton conversationnel avec "tu/toi"
- Emojis dans les titres
- CTA vers Hestia à la fin

```

### 2. Ajout de l'article au système

#### A. Créer le fichier HTML

1. Aller dans `content/blog/`
2. Créer un nouveau fichier : `titre-de-larticle.html`
3. Coller le HTML généré par ChatGPT

#### B. Ajouter les métadonnées

1. Ouvrir `content/blog/metadata.json`
2. Ajouter une nouvelle entrée :

```json
{
  "slug": "titre-de-larticle",
  "title": "Titre complet de l'article",
  "description": "Description SEO de 150-160 caractères maximum",
  "publishedAt": "2025-07-28",
  "readTime": 8,
  "category": "gestion-locative",
  "tags": ["bail", "proprietaire", "conseils"]
}
```

### 3. Templates de CTA fréquents

#### CTA vers la homepage

```html
<div class="cta-box">
  <p>💡 <strong>Prêt à simplifier ta gestion locative ?</strong></p>
  <p><a href="/" class="cta-link">Découvre Hestia gratuitement →</a></p>
</div>
```

#### CTA vers une page spécifique

```html
<div class="cta-box">
  <p>🏠 <strong>Besoin d'un bail parfaitement conforme ?</strong></p>
  <p><a href="/bail" class="cta-link">Génère ton bail en 2 minutes →</a></p>
</div>
```

#### CTA vers l'état des lieux

```html
<div class="cta-box">
  <p>📋 <strong>Prêt pour ton état des lieux ?</strong></p>
  <p>
    <a href="/etat-des-lieux" class="cta-link">Utilise notre outil gratuit →</a>
  </p>
</div>
```

### 4. Classes CSS disponibles

#### Listes

- `.checklist.checklist-success` - Liste verte avec ✓
- `.checklist.checklist-warning` - Liste orange avec ⚠️
- `.checklist.checklist-info` - Liste bleue avec ℹ️
- `.checklist.checklist-danger` - Liste rouge avec ✗
- `.tips-list` - Liste de conseils avec fond gris
- `.summary-list` - Liste de résumé numérotée

#### Encadrés

- `.alert.alert-info` - Encadré bleu d'information
- `.alert.alert-warning` - Encadré orange d'avertissement
- `.alert.alert-success` - Encadré vert de succès
- `.warning-box` - Boîte d'avertissement stylisée
- `.cta-box` - Boîte call-to-action centrée

### 5. Bonnes pratiques

#### SEO

- Titre H1 unique et accrocheur
- Sous-titres H2/H3 avec mots-clés
- Description meta de 150-160 caractères
- Balises alt sur les images
- Liens internes vers d'autres articles/pages

#### Contenu

- Paragraphes courts (3-4 lignes max)
- Listes à puces pour la lisibilité
- Emojis pour dynamiser
- Exemples concrets
- CTA clairs et incitatifs

#### Structure type

```html
<article>
  <p>Introduction accrocheuse...</p>

  <h2>🎯 Premier point important</h2>
  <p>Explication...</p>

  <ul class="checklist checklist-success">
    <li>Point positif 1</li>
    <li>Point positif 2</li>
  </ul>

  <div class="alert alert-info">
    <strong>💡 Bon à savoir :</strong> Information importante
  </div>

  <h2>📋 Conclusion</h2>
  <p>Récapitulatif...</p>

  <div class="cta-box">
    <p>💡 <strong>Call-to-action</strong></p>
    <p><a href="/" class="cta-link">Lien vers action →</a></p>
  </div>
</article>
```

### 6. Test et publication

1. Sauvegarder les fichiers
2. Tester en local : `npm run dev`
3. Vérifier l'affichage sur `/blog/titre-de-larticle`
4. Build de production : `npm run build`
5. Déploiement

## 🚀 Avantages du nouveau système

- ✅ **Pas de syntaxe MDX à apprendre**
- ✅ **HTML pur = contrôle total**
- ✅ **Classes CSS prêtes à l'emploi**
- ✅ **SEO optimisé automatiquement**
- ✅ **Liens internes faciles**
- ✅ **Prévisualisation immédiate**
- ✅ **Pas de compilation complexe**

---

**Questions ?** N'hésite pas à demander de l'aide ! 😊
