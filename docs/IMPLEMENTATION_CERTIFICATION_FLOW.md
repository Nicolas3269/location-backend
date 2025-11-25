# Guide d'Implémentation - Certification Flow eIDAS

**Date** : 20 Octobre 2025
**Version** : 4.0 (TSA Django intégré)
**Statut** : ✅ OPÉRATIONNEL

> **Documentation stratégique** : Voir [signature-strategy-eidas-hybrid.md](./signature-strategy-eidas-hybrid.md) pour la vue d'ensemble, conformité juridique et justifications des choix.

---

## 📁 Architecture du Code

### Flow Technique Détaillé

```
┌─────────────────────────────────────────────────────────┐
│ T0 : CERTIFICATION HESTIA                               │
│ File: signature/certification_flow.py                   │
│ Function: certify_document_hestia()                     │
│      ↓                                                   │
│ • Charge certificat AATL (cert.pfx)                     │
│ • certify=True + DocMDP(FILL_FORMS)                     │
│ • Incremental update PDF                                │
│ • is_document_certified() = True                        │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ T1/T2 : SIGNATURES UTILISATEURS                         │
│ File: signature/pdf_processing.py                       │
│ Function: process_signature_generic()                   │
│      ↓                                                   │
│ • Génère certificat user (CA Hestia)                    │
│   └─ certification_flow.py::generate_user_signer()     │
│ • Capture métadonnées OTP/HTTP                          │
│ • Signe PDF (algo/signature/main.py)                    │
│   └─ sign_pdf() → sign_user_with_metadata()            │
│ • Sauvegarde métadonnées DB                             │
│   └─ save_signature_metadata()                         │
│ • Extraction certificat depuis PDF                      │
│   └─ extract_certificate_from_pdf()                    │
│ • Status → SIGNING (première signature)                 │
│ • Status → SIGNED (toutes signatures complètes)         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ T_final : DOCTIMESTAMP FINAL                            │
│ File: signature/pdf_processing.py                       │
│ Function: apply_final_timestamp()                       │
│      ↓                                                   │
│ • Appel endpoint TSA Django (/tsa/)                     │
│ • DocTimeStamp final (PAdES B-LTA)                      │
│ • Suppression ancien PDF (delete before save)           │
│ • Génération journal de preuves JSON                    │
│   └─ generate_proof_journal()                          │
└─────────────────────────────────────────────────────────┘
```

---

## 📦 Modules et Fichiers

### Module Principal : `signature/certification_flow.py`

**Fonctions implémentées** :

| Fonction                         | Description                      | Status |
| -------------------------------- | -------------------------------- | ------ |
| `certify_document_hestia()`      | Certification première signature | ✅     |
| `generate_user_signer()`         | Génération certificat CA Hestia  | ✅     |
| `sign_user_with_metadata()`      | Signature + capture métadonnées  | ✅     |
| `extract_certificate_from_pdf()` | Extraction X.509 depuis PDF      | ✅     |
| `save_signature_metadata()`      | Sauvegarde métadonnées DB        | ✅     |
| `calculate_pdf_hash()`           | Hash SHA-256 des PDFs            | ✅     |
| `apply_final_timestamp()`        | DocTimeStamp final TSA           | ✅     |
| `generate_proof_journal()`       | Journal de preuves JSON          | ✅     |
| `is_document_certified()`        | Vérification certification       | ✅     |

### Modèle Django : `signature/models.py`

```python
class SignatureMetadata(BaseModel):
    """Métadonnées forensiques pour chaque signature utilisateur"""

    # Relations
    signature_request = GenericForeignKey  # → BailSignatureRequest/EtatLieuxSignatureRequest

    # Métadonnées OTP
    otp_validated = models.BooleanField(default=False)
    otp_sent_at = models.DateTimeField(null=True)
    otp_validated_at = models.DateTimeField(null=True)

    # Métadonnées HTTP
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    referer = models.URLField(null=True)

    # Métadonnées cryptographiques
    signature_timestamp = models.DateTimeField()
    pdf_hash_before = models.CharField(max_length=64)  # SHA-256
    pdf_hash_after = models.CharField(max_length=64)   # SHA-256

    # Certificat X.509 (extrait du PDF)
    certificate_pem = models.TextField()
    certificate_fingerprint = models.CharField(max_length=64)
    certificate_subject_dn = models.CharField(max_length=500)
    certificate_issuer_dn = models.CharField(max_length=500)
    certificate_valid_from = models.DateTimeField()
    certificate_valid_until = models.DateTimeField()

    # TSA (optionnel)
    tsa_timestamp = models.DateTimeField(null=True)
    tsa_response = models.BinaryField(null=True)
```

**Property clé** :

```python
# signature/models.py (AbstractSignatureRequest)
@property
def signer(self):
    """Retourne bailleur_signataire ou locataire selon le type"""
    if hasattr(self, 'bailleur_signataire'):
        return self.bailleur_signataire
    return self.locataire
```

### Modules Intégrés

**`signature/pdf_processing.py`** - Orchestration signatures

- ✅ `process_signature_generic()` (lignes 50-220)
  - Capture métadonnées OTP/HTTP
  - Appel `save_signature_metadata()`
  - Appel `apply_final_timestamp()` si toutes signatures complètes
  - Transition status DRAFT → SIGNING → SIGNED (avec `.value`)
  - Suppression ancien PDF avant DocTimeStamp final (ligne 171)

**`algo/signature/main.py`** - Signature PDF

- ✅ `sign_pdf()` - Délègue à `sign_user_with_metadata()`
- ✅ Transmission paramètres `otp_metadata`, `request`, `document`, `signature_request`

**`signature/views.py`** - API REST

- ✅ `confirm_signature_generic()` - Transmission `request` pour métadonnées HTTP

**`signature/services.py`** - Logique métier

- ✅ `send_otp_email()` - Status DRAFT → SIGNING (première OTP) (ligne 129)
- ✅ Utilisation `.value` pour enum DocumentStatus

**`bail/models.py`, `etat_lieux/models.py`** - Modèles documents

- ✅ `check_and_update_status()` - Vérification signatures complètes
- ✅ Utilisation `.value` pour enum DocumentStatus (lignes 82, 87)

**`quittance/views.py`** - Génération quittances

- ✅ Status → SIGNED après génération PDF (ligne 380)

**`location/views.py`** - Annulation documents

- ✅ Status → CANCELLED (lignes 1335, 1404, 1472)

### Module TSA : `tsa/`

**`tsa/views.py`** - Endpoint TSA Django RFC 3161

- ✅ `timestamp_request()` - Endpoint `POST /tsa/`
- ✅ Appel OpenSSL `ts -reply`
- ✅ Content-Type: `application/timestamp-query` → `application/timestamp-reply`

**`tsa/urls.py`** - URL routing

- ✅ `path('', views.timestamp_request, name='timestamp')`

**Scripts** :

- ✅ `scripts/setup_tsa.sh` - Génération certificats TSA
- ✅ `scripts/test_tsa.py` - Test endpoint TSA

**Configuration** (`backend/settings.py`) :

```python
TSA_CERT_PATH = os.getenv("TSA_CERT_PATH", BASE_DIR / "certificates/tsa_cert.pem")
TSA_KEY_PATH = os.getenv("TSA_KEY_PATH", BASE_DIR / "certificates/tsa_key.pem")
PASSWORD_CERT_TSA = os.getenv("PASSWORD_CERT_TSA", "")
```

### Admin Django : `signature/admin.py`

```python
@admin.register(SignatureMetadata)
class SignatureMetadataAdmin(admin.ModelAdmin):
    list_display = ['id', 'get_signer_name', 'signature_timestamp', 'otp_validated', 'ip_address']
    list_filter = ['otp_validated', 'signature_timestamp']
    search_fields = ['ip_address', 'certificate_subject_dn']

    fieldsets = [
        ('Métadonnées OTP', {'fields': ['otp_validated', 'otp_sent_at', 'otp_validated_at']}),
        ('Métadonnées HTTP', {'fields': ['ip_address', 'user_agent', 'referer']}),
        ('Métadonnées Crypto', {'fields': ['signature_timestamp', 'pdf_hash_before', 'pdf_hash_after']}),
        ('Certificat', {'fields': ['certificate_pem', 'certificate_fingerprint', ...]}),
        ('TSA', {'fields': ['tsa_timestamp', 'tsa_response']}),
    ]
```

---

## 🔧 Points Techniques Critiques

### 1. Status DocumentStatus - Utilisation de `.value`

**Problème** : Django `TextChoices` ne convertit pas automatiquement l'enum en string.

**Solution** : Toujours utiliser `.value`

```python
# ❌ MAUVAIS - Stocke l'objet enum
document.status = DocumentStatus.SIGNED

# ✅ BON - Stocke la valeur string
document.status = DocumentStatus.SIGNED.value  # "signed"
```

**Fichiers corrigés** :

- ✅ `signature/pdf_processing.py` (lignes 137, 205)
- ✅ `signature/services.py` (ligne 129)
- ✅ `bail/models.py` (lignes 82, 87)
- ✅ `etat_lieux/models.py` (lignes 127, 132)
- ✅ `quittance/views.py` (ligne 380)
- ✅ `location/views.py` (lignes 1335, 1404, 1472)

**Frontend mapping** :

- ✅ `mes-locations/page.tsx` - `'signing'` (pas `'signing_in_progress'`)
- ✅ `mon-compte/mes-biens/[bienId]/page.tsx`
- ✅ `components/biens/DocumentsList.tsx`

### 2. Duplication PDF lors du DocTimeStamp final

**Problème** : Le DocTimeStamp final créait un nouveau fichier sans supprimer l'ancien.

**Solution** : Supprimer l'ancien fichier avant `save()`

```python
# signature/pdf_processing.py (ligne 171)
if document.latest_pdf and document.latest_pdf.name:
    document.latest_pdf.delete(save=False)

document.latest_pdf.save(filename, File(f), save=False)
```

### 3. Extraction certificat depuis PDF signé

**Implémentation** : PyHanko `enumerate_sig_fields()`

```python
from pyhanko.sign.fields import enumerate_sig_fields

with open(pdf_path, 'rb') as f:
    reader = PdfFileReader(f)
    sig_fields = list(enumerate_sig_fields(reader))

    for (field_name, field_ref, sig_obj_ref) in sig_fields:
        if field_name == target_field_name:
            field_obj = reader.get_object(sig_obj_ref)
            sig_obj = field_obj['/V']
            contents = sig_obj['/Contents']
            # Parse CMS structure pour extraire certificat
```

**Fichier** : ✅ `signature/certification_flow.py` (fonction `extract_certificate_from_pdf()`)

### 4. TSA Django - Appel OpenSSL

**Implémentation** : Wrapper OpenSSL via subprocess

```python
# tsa/views.py
cmd = [
    "openssl", "ts", "-reply",
    "-queryfile", req_file_path,
    "-out", resp_file_path,
    "-inkey", tsa_key_path,
    "-signer", tsa_cert_path,
    "-passin", f"pass:{tsa_password}",
]

result = subprocess.run(cmd, capture_output=True, timeout=10)
```

**Test** : ✅ `scripts/test_tsa.py`

```python
from pyhanko.sign import timestamps

timestamper = timestamps.HTTPTimeStamper(tsa_url)
tsa_response = timestamper.request_cms(message_digest, 'sha256')
```

### 5. CA Hestia interne

**Architecture** :

- CA Hestia génère et signe les certificats utilisateurs
- Script : `backend/scripts/create_hestia_ca.sh`
- Certificats : `backend/certificates/hestia_ca.pem` + `hestia_ca_key.pem`
- Mot de passe : `HESTIA_CA_PASSWORD` (env variable)

**Fonction** : ✅ `generate_user_signer()` dans `certification_flow.py` (lignes 200-390)

---

## 📋 Checklist Implémentation

### ✅ Implémenté et Testé

**Code Backend** :

- [x] Module `certification_flow.py` complet
- [x] TSA Django endpoint `/tsa/` (RFC 3161)
- [x] Fonction `certify_document_hestia()` avec DocMDP
- [x] Fonction `generate_user_signer()` CA Hestia
- [x] Fonction `sign_user_with_metadata()` métadonnées
- [x] Fonction `extract_certificate_from_pdf()` X.509
- [x] Fonction `save_signature_metadata()` DB
- [x] Fonction `generate_proof_journal()` JSON
- [x] Fonction `apply_final_timestamp()` DocTimeStamp
- [x] Modèle `SignatureMetadata` migré
- [x] Relation GenericForeignKey → SignatureRequest
- [x] Property `signer` sur AbstractSignatureRequest
- [x] Intégration `pdf_processing.py` complète
- [x] Status transitions DRAFT → SIGNING → SIGNED
- [x] Correction `.value` pour DocumentStatus (7 fichiers)
- [x] Correction duplication PDF DocTimeStamp
- [x] Admin Django `SignatureMetadataAdmin`
- [x] CA Hestia interne configuré
- [x] TSA Hestia configuré et testé

**Tests** :

- [x] Tests E2E signature complète (Playwright)
- [x] Validation Adobe Acrobat (certificat test)
- [x] Vérification métadonnées DB
- [x] Test endpoint TSA (`scripts/test_tsa.py`)

### 🚧 TODO - Améliorations

**Infrastructure** :

- [ ] **Certificat eIDAS production** : Commander CertEurope (350€/an)

  - Actuellement : certificat auto-signé test
  - Adobe affiche : "Validity UNKNOWN"
  - Production : Ruban vert immédiat

- [ ] **Archivage S3 Glacier** : Journal de preuves JSON
  - Code préparé dans `generate_proof_journal()`
  - TODO : `upload_to_s3_glacier(journal_json, f"proofs/{document.id}.json")`

**Documentation** :

- [ ] **Guide utilisateur** : Signature électronique
  - Expliquer validation OTP
  - Valeur juridique
  - Conservation documents

**Frontend** :

- [ ] **Vérifier mapping status** : Autres pages
  - ✅ Corrigé : `/mes-locations/`, `/mon-compte/mes-biens/`
  - À vérifier : Autres composants utilisant `status`

---

## 🧪 Tests et Validation

### Tests E2E (Playwright)

**Fichier** : `frontend/tests/e2e/bail-signature.spec.ts`

**Scénario** :

1. Génération bail PDF
2. Certification Hestia (T0)
3. Envoi OTP bailleur
4. Signature bailleur (T1) → Status SIGNING
5. Envoi OTP locataire
6. Signature locataire (T2) → Status SIGNED
7. DocTimeStamp final TSA Django
8. Métadonnées sauvegardées en DB
9. Journal de preuves généré
10. Frontend affiche "Signé" ✅

### Validation Adobe Acrobat

**Certificat test** :

- ⚠️ "Validity UNKNOWN" (certificat auto-signé)
- ✅ DocMDP actif (protection niveau FILL_FORMS)
- ✅ Signatures visibles avec tampon manuscrit
- ✅ Incremental updates préservés
- ✅ DocTimeStamp final présent

**Certificat production** (après achat CertEurope) :

- ✅ Ruban vert "Certifié par HB CONSULTING"
- ✅ Confiance automatique (AATL)

### Base de Données

**Vérification SignatureMetadata** :

```bash
poetry run python manage.py shell -c "
from signature.models import SignatureMetadata
print(f'Total métadonnées : {SignatureMetadata.objects.count()}')
for meta in SignatureMetadata.objects.all()[:3]:
    print(f'  {meta.signer.full_name} - {meta.signature_timestamp}')
    print(f'    OTP validé : {meta.otp_validated}')
    print(f'    IP : {meta.ip_address}')
    print(f'    Certificat CN : {meta.certificate_subject_dn}')
"
```

### Test TSA

**Script** : `scripts/test_tsa.py`

```bash
poetry run python scripts/test_tsa.py
```

**Output** :

```
✅ Réponse TSA reçue avec succès !
✅ Test TSA réussi ! Le serveur fonctionne correctement.
   Le DocTimeStamp final sera appliqué automatiquement aux PDFs.
```

---

## 🚀 Mise en Production

### 1. Acheter Certificat eIDAS Production

```bash
# Provider : CertEurope
# Produit : Cachet serveur eIDAS AATL
# Prix : 350€ HT/an
# Format : PKCS#12 (.pfx)
# URL : https://www.certeurope.fr
```

**Installation** :

```bash
# Copier le certificat
cp hestia_server.pfx backend/certificates/

```

### 2. Configurer Archivage S3 Glacier

```python
# À implémenter dans certification_flow.py
def upload_to_s3_glacier(data: dict, key: str):
    """Upload journal de preuves sur S3 Glacier"""
    import boto3
    s3 = boto3.client('s3')
    s3.put_object(
        Bucket='hestia-proofs',
        Key=key,
        Body=json.dumps(data),
        StorageClass='GLACIER'
    )
```

---

## 📚 Références Techniques

- **Code principal** : [../signature/certification_flow.py](../signature/certification_flow.py)
- **Endpoint TSA** : [../tsa/views.py](../tsa/views.py)
- **Modèle DB** : [../signature/models.py](../signature/models.py)
- **PyHanko doc** : [pyhanko.readthedocs.io](https://pyhanko.readthedocs.io)
- **RFC 3161 (TSA)** : [tools.ietf.org/html/rfc3161](https://tools.ietf.org/html/rfc3161)
- **Stratégie globale** : [signature-strategy-eidas-hybrid.md](./signature-strategy-eidas-hybrid.md)

---

**Dernière mise à jour** : 20 Octobre 2025
**Statut** : ✅ Système opérationnel en mode test, TSA activé, prêt pour production
