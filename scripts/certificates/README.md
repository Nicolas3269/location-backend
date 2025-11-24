# Scripts de Gestion des Certificats Hestia

Ce dossier contient tous les scripts pour générer et gérer les certificats auto-signés Hestia.

## 📁 Organisation

```
scripts/certificates/
├── README.md                              # Ce fichier
├── generate_ca.sh                         # Génère le Certificate Authority
├── generate_tsa.sh                        # Génère le Time Stamping Authority
├── generate_server.sh                     # Génère le certificat serveur (test)
├── regenerate_all_certificates.sh         # Script master (génère tout)
└── encode_certificates_for_railway.sh     # Encode en base64 pour Railway
```

## 🚀 Utilisation

### Générer TOUS les certificats (recommandé)

```bash
cd backend
./scripts/certificates/regenerate_all_certificates.sh
```

**Prérequis** : Définir les mots de passe dans `.env` :
```bash
PASSWORD_CERT_CA=votre_mot_de_passe_ca
PASSWORD_CERT_TSA=votre_mot_de_passe_tsa
PASSWORD_CERT_SERVER=votre_mot_de_passe_server
```

### Générer un certificat individuel

```bash
# Certificate Authority (CA)
./scripts/certificates/generate_ca.sh

# Time Stamping Authority (TSA)
./scripts/certificates/generate_tsa.sh

# Serveur (auto-signé pour test)
./scripts/certificates/generate_server.sh
```

**Mode interactif** : Si les mots de passe ne sont pas dans `.env`, les scripts les demandent interactivement.

### Encoder pour Railway (déploiement)

```bash
./scripts/certificates/encode_certificates_for_railway.sh
```

Copier-coller les valeurs base64 dans les variables d'environnement Railway.

## 📝 Fichiers de Configuration (`.cnf`)

Les fichiers `.cnf` sont dans `backend/certificates/` et sont **versionnés dans Git** :

| Fichier | Usage | Script |
|---------|-------|--------|
| `hestia_certificate_authority.cnf` | Génération CA | `generate_ca.sh` |
| `hestia_tsa_generation.cnf` | Génération certificat TSA | `generate_tsa.sh` |
| `hestia_server.cnf` | Génération serveur test | `generate_server.sh` |
| `hestia_tsa.cnf` | Config runtime TSA (ts -reply) | `tsa/views.py` |

## 🔐 Sécurité

- ✅ **Aucun mot de passe hardcodé** dans les scripts
- ✅ Scripts versionnables dans Git sans risque
- ✅ Mots de passe uniquement dans `.env` (non versionné)
- ✅ Mode interactif avec confirmation si `.env` absent
- ✅ Toutes les clés chiffrées AES-256 (`encrypt_key=yes`)

## 📦 Certificats Générés

Les certificats sont créés dans `backend/certificates/` :

```
certificates/
├── hestia_certificate_authority.pem   # CA cert (public)
├── hestia_certificate_authority.key   # CA key (privée, chiffrée)
├── hestia_tsa.pem                     # TSA cert (public)
├── hestia_tsa.key                     # TSA key (privée, chiffrée)
├── hestia_server.pem                  # Server cert (public)
├── hestia_server.key                  # Server key (privée, chiffrée)
└── hestia_server.pfx                  # Server PKCS#12 (pour PyHanko)
```

## ⚠️ Important

- **Certificats auto-signés** : Pour TEST uniquement en local
- **Production** : Utiliser le certificat qualifié CertEurope AATL (350€/an)
- **Backup** : Les anciens certificats sont sauvegardés dans `certificates/backup_YYYYMMDD_HHMMSS/`
- **Sécurité** : Ne JAMAIS commiter les fichiers `.key`, `.pfx`, `.pem` dans Git

## 🔄 Régénération

**Quand régénérer ?**
- Expiration des certificats (1 an pour server, 10 ans pour CA/TSA)
- Compromission de clé privée
- Changement d'organisation (SIREN, raison sociale)
- Migration vers certificat qualifié (production)

**Procédure** :
```bash
# 1. Régénérer tous les certificats
./scripts/certificates/regenerate_all_certificates.sh

# 2. Redémarrer le serveur Django
python manage.py runserver 8003

# 3. Tester la signature
# (Créer un bail/EDL/quittance)

# 4. Vérifier avec Adobe Reader
# (Warnings normaux pour certificats auto-signés)
```

## 📚 Documentation

Pour plus d'informations, voir :
- `/backend/docs/signature-strategy-eidas-hybrid.md` - Architecture signature PAdES B-LT
- `/backend/certificates/*.cnf` - Configurations OpenSSL
