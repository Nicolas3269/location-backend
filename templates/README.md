# Templates Centralisés - Hestia

Structure organisée pour les templates PDF et emails du projet.

## 📁 Structure

```
templates/
├── base/
│   └── pdf_base.html                     # CSS global réutilisable (Design Hestia)
├── email/
│   └── quittance_email.mjml              # Email MJML responsive
└── pdf/
    ├── bail/
    │   ├── bail.html                     # Template bail (649 lignes)
    │   └── components/
    │       └── signature_fields.html     # Champs signatures Yousign
    ├── etat_lieux/
    │   ├── etat_lieux.html               # Template état des lieux (1026 lignes)
    │   └── components/
    │       └── signature_fields.html     # Champs signatures Yousign
    └── quittance/
        ├── quittance.html                # Template quittance (80 lignes)
        └── components/
            ├── info_parties.html         # Bailleur/Locataire
            └── signature_block.html      # Signature simple
```

## 🎨 Design System

Tous les templates utilisent la **charte graphique Hestia** :

- **Couleurs principales** : `#2680eb` (bleu), `#3e3c41` (gris anthracite)
- **Font principale** : Ubuntu
- **Font footer** : Playfair Display (italique)
- **Tokens CSS** : Variables définies dans `base/pdf_base.html`

### Footer Automatique avec Logo

Tous les PDF incluent un **footer automatique avec le logo Hestia** via les règles CSS `@page` :

**Implémentation** :
- Défini dans `base/pdf_base.html` avec `@page { @bottom-center { ... } }`
- Logo encodé en base64 via `backend/pdf_utils.py::get_logo_pdf_base64_data_uri()`
- S'affiche automatiquement sur **toutes les pages** du PDF

**Contenu** :
- Logo Hestia (SVG, 13px, couleur #999999)
- Texte : "Document généré avec Hestia - Solution de gestion locative, conforme à la loi"

**Style** :
- **Font** : Playfair Display Italic, 10pt
- **Couleur** : #999999 (gris clair, identique au logo)
- **Position** : Centré en bas de page
- **Logo** : Généré dynamiquement depuis `/backend/static/images/logo.svg` (modifié : taille 13px, couleur #999999, alignement vertical ajusté)

## 🔧 Utilisation

### Templates PDF

```python
from django.template.loader import render_to_string

# Bail
html = render_to_string("pdf/bail/bail.html", context)

# État des lieux
html = render_to_string("pdf/etat_lieux/etat_lieux.html", context)

# Quittance
html = render_to_string("pdf/quittance/quittance.html", context)
```

### Emails MJML

```python
from mjml.tools import mjml_render
from django.template.loader import get_template

template = get_template('email/quittance_email.mjml')
mjml_content = template.render(context)
html_content = mjml_render(mjml_content)
```

### Test email

```bash
USE_MAILHOG=true python manage.py send_test_email --email test@example.com
```

## 📊 Statistiques

| Document | Lignes | Composants |
|----------|--------|------------|
| **Quittance** | 80 | 2 (info_parties, signature_block) |
| **Bail** | 649 | 1 (signature_fields) |
| **État des lieux** | 1026 | 1 (signature_fields) |
| **Base CSS** | 210 | - |

## 🔐 Signatures Yousign

Les champs de signature utilisent des **IDs invisibles** détectés par PyMuPDF :

- `ID_SIGNATURE_BAILLEUR_{{ bailleur.signataire.id }}`
- `ID_SIGNATURE_LOC_{{ locataire.id }}`

Ces IDs sont en texte blanc (`color:white`) et positionnés dans les blocs `.signature-block`.

## 🚀 Prochaines Améliorations

- [ ] Refactoriser les articles du bail en composants
- [ ] Créer templates emails pour bail et état des lieux
- [ ] Extraire les composants communs (adresse bien, période, etc.)
