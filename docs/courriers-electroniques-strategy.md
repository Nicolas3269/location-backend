# Stratégie Courriers Recommandés Électroniques Hestia

**Version** : 2.0 (Clarifications juridiques)
**Date** : 20 Octobre 2025
**Statut** : 🚧 EN CONCEPTION

> **Note** : Ce document concerne les **courriers recommandés électroniques** (LRE/LRAR). Pour les **signatures de documents** (baux, EDL, quittances), voir [signature-strategy-eidas-hybrid.md](./signature-strategy-eidas-hybrid.md)

---

## 📋 Résumé Exécutif

**Stratégie "Courriers Illimités & Juridiquement Sécurisés"**

Permettre aux bailleurs d'envoyer **tous les courriers de gestion locative** (relances, mises en demeure, notifications, régularisations) de manière **illimitée et probante** avec cachet électronique qualifié — tout en les protégeant en redirigeant les actes critiques (congés, commandements) vers **huissiers partenaires**.

**✅ Ce que Hestia couvre (ERDS Standard - 350€/an forfait)** :
- ✅ **Relances de loyer** → Envois illimités, cachet eIDAS qualifié
- ✅ **Mises en demeure** → Envois illimités, cachet eIDAS qualifié
- ✅ **Notifications locatives** → Envois illimités, cachet eIDAS qualifié
- ✅ **Régularisations charges** → Envois illimités, cachet eIDAS qualifié
- ✅ **Quittances / baux / EDL** → Signature électronique avancée (AES) par utilisateurs + Cachet Hestia qualifié (ruban vert Adobe)

**❌ Ce que Hestia ne fait volontairement PAS (Protection bailleurs)** :
- ❌ **Congés / Préavis bailleur** → Redirection huissier partenaire (réception garantie)
- ❌ **Commandements de payer** → Redirection huissier (loi 89-462 art. 24, monopole légal)
- ❌ **Assignations / expulsions** → Redirection avocat spécialisé

**Raison** : Trop risqué juridiquement, pas notre métier → On protège nos bailleurs en les dirigeant vers pros

**Différence clé avec signatures de documents** :
- **Signature de documents** → Les **deux parties signent** (bailleur + locataire)
- **Courriers recommandés** → **Une seule partie envoie** (bailleur → locataire), destinataire ne signe pas

**Modèle économique** :
- **350€/an** → Forfait courriers illimités (relances, mises en demeure, notifications, régularisations)
- **Cachet eIDAS qualifié** → Valeur probante forte, ruban vert Adobe
- **Redirection huissier partenaire** → Pour actes critiques (congés, commandements)
- **Commission partenariat** → 10-20€ par acte huissier (optionnel)

---

## 🚫 Scope Volontairement Exclu

**Hestia ne gère volontairement PAS les actes suivants**, par protection de nos bailleurs :

### ❌ **Congé Bailleur (Loi 89-462 art. 15)**

**Raison de l'exclusion** :
- **Risque juridique majeur** : Réception non garantie (cas "routier" célèbre)
- **Scénario catastrophe** : Locataire ne récupère jamais le courrier → Congé invalide
- **Conséquence** : Bailleur bloqué avec locataire refusant de partir
- **Enjeu financier** : Perte de plusieurs mois de loyer si procédure invalide

**Solution recommandée** :
- ✅ **Huissier de justice** : Signification en main propre (réception garantie)
- ✅ **Avocat spécialisé immobilier** : Sécurisation juridique complète
- ✅ **Partenariat huissier Hestia** : Workflow intégré, dossier pré-rempli

**Workflow Hestia** :
1. Bailleur clique "Gérer un congé" → Warning UX
2. Export dossier complet (bail, quittances, relances)
3. Redirection vers huissier partenaire
4. Huissier reçoit dossier clé en main → Devis transparent

---

### ❌ **Commandement de Payer (Loi 89-462 art. 24)**

**Raison de l'exclusion** :
- **Monopole légal huissier** : Acte réservé aux commissaires de justice
- **Responsabilité énorme** : Si commandement mal fait → Procédure nulle
- **Conséquence** : Perte de plusieurs mois de loyer + frais avocat
- **Pas notre métier** : Hestia = SaaS gestion locative, pas cabinet juridique

**Solution recommandée** :
- ✅ **Commissaire de justice** : Seul habilité légalement
- ✅ **Workflow intégré** : Export dossier Hestia → Formulaire huissier pré-rempli

**Ce que Hestia FAIT en amont** :
1. ✅ Relances automatiques (gratuites, illimitées)
2. ✅ Mises en demeure (gratuites, valeur probante)
3. ✅ Suivi impayés (tableau de bord temps réel)
4. ✅ Export dossier complet pour huissier (bail + quittances + relances + preuves)

**Processus complet** :
```
Impayé détecté
    ↓
Hestia : Relances automatiques (0€)
    ↓
Hestia : Mise en demeure (0€, cachet eIDAS)
    ↓
Si toujours impayé après 2 mois
    ↓
Hestia : Export dossier → Huissier partenaire
    ↓
Huissier : Commandement de payer (150-300€)
    ↓
Délai 2 mois (clause résolutoire)
    ↓
Si impayé → Assignation tribunal
```

---

### ❌ **Assignations / Expulsions**

**Raison de l'exclusion** :
- **Procédures judiciaires complexes**
- **Monopole huissier + avocat**
- **Responsabilité juridique trop élevée**

**Solution recommandée** :
- ✅ Redirection vers avocat spécialisé immobilier
- ✅ Partenariat avec commissaire de justice

---

### 💡 **Opportunité Business : Partenariat Huissier**

**Modèle Win-Win** :
- **Hestia** : Commission 10-20€ par acte, pas de responsabilité juridique
- **Huissier** : Leads qualifiés, dossiers pré-remplis (gain de temps)
- **Bailleur** : Continuité de service, prix transparent, sécurité juridique

**Workflow intégré** :
1. Bailleur clique "Commandement de payer" dans Hestia
2. Hestia génère ZIP : Bail + Quittances + Relances + Mises en demeure
3. Export → Formulaire huissier pré-rempli (API ou email)
4. Huissier envoie devis → Bailleur valide
5. Huissier délivre acte → Commission Hestia

---

### 🎯 **Positionnement Stratégique**

**Hestia = Gestion Locative Saine & Sécurisée**

✅ **Ce qu'on maîtrise** : Suivi loyers, relances, preuves, documents signés

⚠️ **Ce qu'on délègue** : Actes juridiques critiques (congés, commandements)

🏛️ **Pourquoi** : Protéger nos bailleurs en les dirigeant vers professionnels compétents

**Messaging utilisateur** :
> "Hestia vous accompagne jusqu'au seuil de la procédure judiciaire. Pour les actes critiques (congés, commandements), nous vous mettons en relation avec nos partenaires experts (huissiers, avocats) pour garantir la sécurité juridique de votre démarche."

---

## ⚖️ Cadre Juridique - Ce qui est VRAIMENT Requis

### Sans TSA qualifié ni QTSP, tu restes 100% légal

**Code civil** :
- **Art. 1366** : L'écrit électronique a la même valeur que l'écrit papier
- **Art. 1367** : La signature électronique vaut signature manuscrite si elle identifie l'auteur et garantit l'intégrité

**Règlement eIDAS (UE 910/2014)** :
- **Art. 26** : Signature électronique avancée (AES) = juridiquement valable dans toute l'UE
- **Pas besoin d'être "qualifié"** pour que tes courriers soient recevables et probants

**Ce que tu perds sans TSA qualifié / QTSP** :

| Élément absent | Conséquence |
|----------------|-------------|
| **TSA qualifié** | Pas de **présomption automatique** de date certaine (mais tu peux la prouver par logs + hash) |
| **QTSP (AR24/Docaposte)** | Pas de **présomption légale** d'authenticité équivalente LRAR papier |

**Mais** : Ta preuve reste **recevable** → Tu dois juste démontrer la date et l'intégrité avec ton journal technique.

---

## 🔑 Différence Critique : QSealC (Signature) vs QERDS (Transmission)

### ⚠️ IMPORTANT : Cachet ≠ Transmission Qualifiée

**Le cachet qualifié (QSealC) signe le DOCUMENT, pas la TRANSMISSION.**

```
┌─────────────────────────────────────────────────────┐
│ Cachet eIDAS (QSealC)                               │
│ → Prouve : INTÉGRITÉ + ORIGINE du document          │
│ → Ne prouve PAS : Réception ni date opposable       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ QERDS (Transmission qualifiée)                      │
│ → Prouve : ENVOI + RÉCEPTION + DATE OPPOSABLE       │
│ → Équivalent LRAR (CPCE L.100)                      │
└─────────────────────────────────────────────────────┘
```

**→ Pour congé bailleur (loi 89-462 art. 15)** : LRAR exigée = **QERDS OBLIGATOIRE**

**Cachet seul = INSUFFISANT** (prouve le document, pas la réception)

---

### 1️⃣ Cachet eIDAS (QSealC) - 350€/an chez CertEurope

**C'est quoi ?**
- Certificat de **cachet électronique qualifié** (Qualified Seal Certificate)
- eIDAS Article 3(30), art. 35-36 : Signature personne morale
- AATL (Adobe Approved Trust List) : Ruban vert Adobe PDF
- **Signe au nom de** : HB CONSULTING (Hestia)

**Ce qu'il fait** :
- ✅ **Signature QUALIFIÉE** de l'entreprise HB CONSULTING (eIDAS art. 35)
- ✅ **Contre-signe** les documents après signature AES des utilisateurs (baux, EDL, quittances)
- ✅ **Signe** les courriers émis par Hestia (relances, mises en demeure, notifications)
- ✅ Prouve **origine** (Hestia a émis ce document)
- ✅ Prouve **intégrité** (document inchangé depuis signature)
- ✅ Ruban vert Adobe (confiance utilisateur, AATL)
- ✅ **Présomption légale de fiabilité** (eIDAS art. 35)

**Ce qu'il NE fait PAS** :
- ❌ **Ne remplace PAS les signatures utilisateurs** (bailleur/locataire signent en AES, Hestia contre-signe en qualifié)
- ❌ **Ne prouve PAS la réception** par le destinataire (courriers)
- ❌ **Ne prouve PAS la date d'opposabilité** de la transmission
- ❌ **Ne remplace PAS un QERDS** pour congés/préavis (loi 89-462 art. 15)

**Valeur juridique** :
- ✅ **Signature qualifiée** : Présomption légale (eIDAS art. 35)
- ✅ **Document** : Preuve quasi irréfutable d'intégrité et d'origine
- 🟡 **Transmission** : Preuve libre (logs SMTP contestables)

---

### 2️⃣ ERDS Hestia (Cachet eIDAS + Email) - 350€/an forfait

**C'est quoi ?**
- **Electronic Registered Delivery Service** (non qualifié)
- Solution Hestia : Email + PDF signé cachet eIDAS + journal de preuve

**Composants** :
- ✅ **Cachet eIDAS qualifié** (signe le PDF)
- ✅ Horodatage TSA Django (date émission)
- ✅ Journal de preuve DB (logs SMTP)
- ✅ Archivage 10 ans (PostgreSQL + S3 Glacier)

**Ce qu'il prouve** :
- ✅ **Document intègre** (cachet eIDAS)
- ✅ **Origine Hestia** (présomption légale)
- ✅ **Preuve d'envoi** (logs SMTP + timestamp)
- ❌ **Pas de preuve de réception** (destinataire peut nier)

**Valeur juridique** : **Très forte** pour le document, **Moyenne** pour la transmission

---

### 3️⃣ QERDS (Transmission qualifiée) - 5€/envoi - AR24/Docaposte

**C'est quoi ?**
- **Qualified Electronic Registered Delivery Service**
- eIDAS Article 44 : Service certifié ANSSI (Prestataire de Confiance Qualifié)
- CPCE L.100 : **Équivalent LRAR** (présomption légale)
- Fournisseur externe : AR24, Docaposte

**Ce qu'il prouve** :
- ✅ **Preuve d'envoi qualifiée** (date certaine opposable)
- ✅ **Preuve de réception qualifiée** (accusé AR)
- ✅ **Présomption légale d'authenticité** (= LRAR papier)
- ✅ **Date opposable** (eIDAS art. 44 + CPCE L.100)

**Valeur juridique** : **Parfaite** (= LRAR papier)

---

### 📊 Tableau Récapitulatif : Cachet vs QERDS

| Élément | Cachet eIDAS (QSealC) | ERDS Hestia (Cachet + Email) | QERDS (AR24/Docaposte) |
|---------|----------------------|------------------------------|------------------------|
| **Signe le document** | ✅ Oui (présomption légale) | ✅ Oui | ✅ Oui |
| **Prouve l'intégrité** | ✅ Oui | ✅ Oui | ✅ Oui |
| **Prouve l'origine** | ✅ Oui (Hestia) | ✅ Oui | ✅ Oui |
| **Prouve l'envoi** | ❌ Non | 🟡 Oui (logs SMTP, contestable) | ✅ Oui (qualifié) |
| **Prouve la réception** | ❌ Non | ❌ Non | ✅ Oui (accusé AR) |
| **Date opposable** | ❌ Non | ❌ Non (TSA Django non qualifié) | ✅ Oui (présomption légale) |
| **Équivalent LRAR** | ❌ Non | ❌ Non | ✅ Oui (CPCE L.100) |
| **Conforme congé bailleur** | ❌ Non | ❌ Non | ✅ Oui (loi 89-462 art. 15) |
| **Coût** | 350€/an | 350€/an (forfait illimité) | 5€/envoi |
| **Use case** | Contre-signer PDFs (baux, EDL, quittances après signature AES utilisateurs) | Relances, notifications, mises en demeure | Congés, préavis, actes LRAR (Hestia ne gère pas) |

**🎯 Règle d'Or** :
- **Cachet eIDAS Hestia (QSealC)** → Signature **qualifiée** de l'entreprise (présomption légale art. 35)
- **Signatures utilisateurs** → Signature **avancée** (AES, recevable art. 26)
- **QERDS** → Transmission qualifiée (envoi + réception + date opposable)
- **Pour congé bailleur** → LRAR exigée (loi 89-462 art. 15) = **Hestia ne gère pas** (redirection huissier)

---

## ✅ Ce que tu PEUX Faire - Conformité Légale RÉELLE

### Tableau de Conformité (Loi 89-462 + CPCE L.100 + eIDAS)

| Type de courrier | ERDS Standard (0€) | LRE qualifiée (QERDS) | Huissier | Base légale |
|------------------|--------------------|-----------------------|----------|-------------|
| **Relance simple / rappel de loyer** | ✅ **Suffisant** (preuve libre) | Optionnel | – | Art. 1366-1367 C. civ. |
| **Mise en demeure de payer** | 🟡 **Suffisant SAUF si bail impose LRAR** (preuve libre, contestable) | ✅ **Recommandé** (présomption légale) | – | Art. 1366-1367 C. civ. + clause bail |
| **Congé / Préavis bailleur** | ❌ **NON CONFORME** | ✅ **Exigé** (équivalent LRAR) | ✅ (alternative) | Loi 89-462 art. 15 + CPCE L.100 |
| **Révision / Régularisation de loyer** | 🟡 **Suffisant mais date contestable** | ✅ **Recommandé** (date opposable) | – | Art. 1366-1367 C. civ. |
| **Notification locative (hors congé)** | ✅ **Suffisant** (preuve libre) | Optionnel | – | Art. 1366-1367 C. civ. |
| **Quittance / bail / EDL** | ✅ **Suffisant** (signature AES utilisateurs + cachet Hestia qualifié) | – | – | eIDAS art. 26 (AES) + art. 35 (QSealC) |
| **Commandement de payer (clause résolutoire)** | ❌ **Impossible** | ❌ **Impossible** | ✅ **Exigé** (monopole) | Loi 89-462 art. 24 |

**⚠️ ATTENTION : Limites Légales de l'ERDS Standard (0€)**

- ✅ **Relances, notifications** : Suffisant juridiquement (preuve libre)
- 🟡 **Mises en demeure** : Suffisant SAUF si bail impose LRAR (vérifier clause contractuelle)
- ❌ **Congé/Préavis bailleur** : NON CONFORME (loi 89-462 art. 15 exige LRAR OU LRE qualifiée OU huissier)
- 🟡 **Révision de loyer** : Suffisant mais date contestable (sans présomption légale)

**→ Pour congés/préavis** : Utiliser **LRE qualifiée (QERDS)** obligatoirement (équivalent LRAR, CPCE L.100).

---

## 🔒 Conditions pour être "Béton" Sans TSA Qualifié

### 1. Signature électronique avancée (AES)

**Options** :
- ✅ **Cachet eIDAS CertEurope** (350€/an) - Ruban vert Adobe
- ✅ **CA interne Hestia** (0€) - Signature valable juridiquement

**Requis** :
- Hash SHA-256 du PDF avant signature
- Certificat X.509 valide

### 2. Horodatage interne (TSA Django)

- Même auto-signé, il prouve une date de génération cohérente
- Tant que tu peux montrer la cohérence des logs serveur, c'est recevable
- Archivé en DB PostgreSQL

### 3. Journal de preuve détaillé

**Métadonnées capturées** :
- ✅ Logs d'envoi (SMTP, webhook, IP)
- ✅ Timestamp UTC serveur
- ✅ Hash du document envoyé
- ✅ Identité expéditeur et destinataire
- ✅ User-agent, referer

### 4. Archivage inviolable

- Conservation 10 ans (DB PostgreSQL + S3 Glacier)
- Empêche toute altération a posteriori
- Journal JSON signé

---

## 📦 Niveaux de Service Hestia (Conforme Loi 89-462)

| Niveau | Description | Composants | Coût fixe | Coût variable | Conformité Légale |
|--------|-------------|------------|-----------|---------------|-------------------|
| **ERDS Standard** | Email + PDF signé Cachet eIDAS + TSA Django + journal DB | • Cachet eIDAS AATL Hestia (350€/an)<br>• TSA Django (0€)<br>• Logs DB | **350€/an** | **0€/envoi** | ✅ Relances, notifications<br>🟡 Mises en demeure (si bail autorise)<br>❌ Congés (non conforme) |
| **LRE qualifiée (QERDS)** | Service qualifié externe AR24/Docaposte | • API AR24/Docaposte<br>• Accusé qualifié<br>• Présomption légale | **0€** | **5€/envoi** | ✅ Congés/Préavis (équivalent LRAR)<br>✅ Révision loyer (date opposable)<br>✅ Mises en demeure (présomption) |
| **Huissier** | Actes judiciaires/extrajudiciaires | • Commissaire de justice<br>• Monopole légal | **0€** | Variable | ✅ Commandements de payer (art. 24)<br>✅ Assignations, expulsions |

### Recommandation par Use Case (Conforme Loi 89-462)

| Type de courrier | ERDS Standard (350€/an) | QERDS (5€/envoi) | Huissier | Base légale |
|------------------|-------------------------|------------------|----------|-------------|
| **Relances de loyer** | ✅ **Recommandé** | Optionnel | – | Art. 1366-1367 C. civ. |
| **Notifications locatives** | ✅ **Recommandé** | Optionnel | – | Art. 1366-1367 C. civ. |
| **Mises en demeure** | 🟡 **OK si bail autorise** | ✅ **Recommandé** (présomption légale) | – | Clause bail + art. 1366-1367 |
| **Congé / Préavis bailleur** | ❌ **Non conforme** | ✅ **OBLIGATOIRE** | ✅ (alternative) | **Loi 89-462 art. 15** (LRAR exigée) |
| **Révision de loyer (IRL)** | 🟡 **OK mais date contestable** | ✅ **Recommandé** (date opposable) | – | Art. 1366-1367 C. civ. |
| **Commandement de payer** | ❌ | ❌ | ✅ **OBLIGATOIRE** | **Loi 89-462 art. 24** (monopole huissier) |

---

## 💬 Ce que tu peux promettre dans ton produit (Messaging Conforme)

### Courrier Électronique Hestia (ERDS Standard)

> **Conforme au Code civil** (art. 1366-1367) et au **règlement eIDAS** (art. 26).
>
> Chaque envoi est **signé avec cachet eIDAS qualifié**, **horodaté** et **archivé**.
>
> En cas de litige, Hestia fournit un **journal de preuve complet** :
> - ✅ Cachet électronique qualifié Hestia (eIDAS AATL - ruban vert Adobe)
> - ✅ Horodatage technique (TSA Django)
> - ✅ Intégrité du document (hash SHA-256)
> - ✅ Preuve d'envoi (logs SMTP)

**✅ Juridiquement suffisant pour** :
- Relances de loyer
- Notifications locatives (hors congés)
- Mises en demeure (si bail autorise, sinon voir QERDS)

**⚠️ NON CONFORME pour** :
- ❌ **Congés / Préavis bailleur** → Loi 89-462 art. 15 exige LRAR OU LRE qualifiée (QERDS)
- ❌ **Commandements de payer** → Loi 89-462 art. 24 exige huissier (monopole)

**🔵 Option "Recommandé Qualifié" (QERDS - 5€/envoi)** :
- Pour congés, préavis, révisions de loyer avec date opposable
- Équivalent LRAR (CPCE L.100 + eIDAS art. 44)
- Présomption légale d'authenticité

**⚖️ Redirection Huissier** :
- Pour commandements de payer, assignations, expulsions

---

## 🏗️ Architecture Technique

### Flow ERDS Standard (0€)

```
┌─────────────────────────────────────────────────────────┐
│ 1. GÉNÉRATION COURRIER                                  │
│    • PDF généré (mise en demeure, congé, etc.)          │
│    • Signature CA Hestia OU Cachet eIDAS (optionnel)    │
│    • DocTimeStamp TSA Django                            │
│    • Hash SHA-256 calculé                               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. ENVOI EMAIL                                          │
│    • Email au destinataire (locataire)                  │
│    • Lien vers PDF signé (ou PDF en pièce jointe)       │
│    • Capture métadonnées (date/heure, IP émetteur)      │
│    • Logs SMTP (preuve d'envoi)                         │
│    • Journal de preuve en DB                            │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. ARCHIVAGE                                            │
│    • PDF signé archivé                                  │
│    • Journal de preuve JSON signé                       │
│    • Métadonnées en DB PostgreSQL                       │
│    • (TODO) Export S3 Glacier                           │
└─────────────────────────────────────────────────────────┘
```

### Flow ERDS Certifié (+0,05€/envoi)

Identique au flow standard, avec ajout :
- ✅ **TSA qualifié CertEurope** (au lieu de TSA Django)
- ✅ Date certaine opposable (eIDAS art. 42)

### Flow QERDS (+5€/envoi)

Délégation à prestataire certifié ANSSI :
- ✅ API AR24/Docaposte
- ✅ Accusé de réception qualifié
- ✅ Présomption légale d'authenticité

---

## 📋 Métadonnées Capturées (Journal de Preuve)

**Pour chaque courrier Hestia** :

1. **Métadonnées émetteur** :
   - Identité bailleur (nom, email)
   - IP émetteur
   - User-agent
   - Date/heure envoi (timestamp TSA Django)

2. **Métadonnées destinataire** :
   - Identité locataire (nom, email)
   - Email envoyé (log SMTP)
   - (Optionnel) Ouverture email (tracking pixel)
   - (Optionnel) Téléchargement PDF

3. **Métadonnées document** :
   - Hash PDF (SHA-256)
   - Signature Hestia (CA interne ou cachet eIDAS)
   - DocTimeStamp (TSA Django ou qualifié)

4. **Archivage** :
   - Journal de preuve JSON signé
   - PDF signé original
   - Conservation 10 ans (DB + S3 Glacier)

---

## ✅ Exemple d'usage conforme (mise en demeure)

### Scénario : Bailleur envoie mise en demeure de payer (ERDS Standard - 0€)

1. **Génération PDF** :
   - "Mise en demeure de payer 3 mois de loyer impayés"
   - Signature CA Hestia (0€)
   - DocTimeStamp TSA Django
   - Hash SHA-256 : `a1b2c3d4e5f6...`

2. **Envoi email** :
   - Email au locataire : "Vous avez reçu une mise en demeure"
   - Lien vers PDF signé (ou PDF en pièce jointe)
   - Capture date/heure envoi, IP bailleur
   - Log SMTP : Message-ID, timestamp

3. **Journal de preuve** :
   ```json
   {
     "type": "mise_en_demeure",
     "emetteur": {
       "nom": "Jean BAILLEUR",
       "email": "jean@example.com",
       "ip": "192.168.1.10"
     },
     "destinataire": {
       "nom": "Marie LOCATAIRE",
       "email": "marie@example.com"
     },
     "document": {
       "hash_sha256": "a1b2c3d4e5f6...",
       "signature": "CA Hestia",
       "timestamp_tsa": "2025-10-20T14:35:22Z"
     },
     "envoi": {
       "smtp_message_id": "abc123@hestia.fr",
       "timestamp_envoi": "2025-10-20T14:35:25Z"
     }
   }
   ```

4. **Archivage** :
   - PDF signé archivé 10 ans
   - Journal JSON signé archivé 10 ans
   - Métadonnées en DB PostgreSQL

**Résultat** :
- ✅ Document intègre et signé avec cachet eIDAS qualifié (art. 1367)
- ✅ Date d'envoi prouvée (logs + TSA Django)
- ✅ Preuve recevable devant tribunal civil (preuve libre)
- ⚠️ **Mise en demeure contestable** si bail impose LRAR (vérifier clause)
- 💰 **Coût : 350€/an** (cachet eIDAS) + **0€/envoi**

**⚠️ ATTENTION** : Si mise en demeure = préalable à clause résolutoire, **vérifier clause bail**.
Si bail impose LRAR → Utiliser **QERDS (5€/envoi)** pour présomption légale.

---

## 💰 Coûts Détaillés (Conforme Loi 89-462)

### Scénario Réaliste : 100 courriers/an

**Composition** :
- 85 relances/notifications → ERDS Standard (350€/an forfait)
- 10 mises en demeure → ERDS Standard (si bail autorise) OU QERDS (50€)
- 3 congés/préavis → **QERDS OBLIGATOIRE** (15€)
- 2 commandements → **Huissier OBLIGATOIRE** (variable, ~200€)

| Solution | Coût fixe | Coût variable | Total | Conformité |
|----------|-----------|---------------|-------|------------|
| **ERDS Standard (cachet eIDAS)** | 350€/an | 0€ × 85 relances | **350€** | ✅ Relances<br>❌ Congés (non conforme) |
| **+ QERDS pour congés** | 350€/an | 5€ × 13 (10 MD + 3 congés) | **415€** | ✅ Conforme loi 89-462 |
| **+ Huissier commandements** | 350€/an | 65€ + ~200€ huissier | **~615€** | ✅ 100% conforme |
| **100% LRAR papier** | 0€ | 5€ × 98 + huissier | **~690€** | ✅ Conforme (référence) |

**Économie vs LRAR** : **~75€/an** (avec conformité totale)

### ⚠️ Scénario "0€" (NON CONFORME pour congés)

Si bailleur utilise **ERDS Standard uniquement** (350€/an, 0€/envoi) :
- ✅ Conforme pour 85% des courriers (relances, notifications)
- ❌ **NON CONFORME** pour congés/préavis (loi 89-462 art. 15)
- ⚖️ **Risque juridique** : Congé invalide, locataire peut rester

**→ Solution OBLIGATOIRE** : QERDS (5€/envoi) pour congés/préavis

---

## 🎯 Bénéfices

### Juridiques
- ✅ Conforme Code civil art. 1366-1367
- ✅ Signature électronique avancée (eIDAS AES)
- ✅ Journal de preuve complet et auditable
- ✅ Conservation long terme (10 ans)
- ✅ **Recevable devant tribunal (preuve libre)**

### Techniques
- ✅ Envoi instantané (vs 2-3 jours LRAR papier)
- ✅ Traçabilité complète
- ✅ Archivage automatique
- ✅ Interface utilisateur simple

### Économiques
- ✅ **0€ pour 95% des courriers** (ERDS Standard)
- ✅ 350€/an pour cachet eIDAS (optionnel, améliore confiance)
- ✅ 0,05€ pour courriers certifiés (vs 5€ AR24)
- ✅ Pas de coût fixe/abonnement
- ✅ Scalable à l'infini

---

## 🚧 TODO - Implémentation

**Phase 1 : ERDS Standard (Cachet eIDAS - 350€/an)** :
- [ ] ✅ Achat certificat CertEurope AATL (QSealC) - **EN COURS**
- [ ] Génération PDF courrier (templates : relance, notification, mise en demeure)
- [ ] Intégration signature cachet eIDAS qualifié (PyHanko)
- [ ] DocTimeStamp TSA Django (déjà implémenté)
- [ ] Envoi email notification (SMTP)
- [ ] Capture métadonnées en DB (logs SMTP, hash PDF, timestamp)
- [ ] Journal de preuve JSON signé
- [ ] Interface bailleur : "Envoyer un courrier" (relance, notification)
- [ ] Warning UX : "Congés/Préavis → Utiliser QERDS (5€/envoi)"

**Phase 2 : QERDS (5€/envoi) - Pour Congés/Préavis** :
- [ ] Intégration API AR24 ou Docaposte
- [ ] Interface "Envoyer Congé/Préavis" → Force QERDS (loi 89-462 art. 15)
- [ ] Accusé de réception qualifié (stockage DB)
- [ ] Facturation 5€/envoi (Stripe/Mollie)
- [ ] Templates congés : congé bailleur, préavis locataire, résiliation

**Phase 3 : Redirection Huissier** :
- [ ] Partenariat commissaire de justice
- [ ] Interface "Commandement de payer" → Redirection huissier
- [ ] Formulaire pré-rempli pour huissier (données bailleur/locataire)

**Phase 4 : Améliorations** :
- [ ] Tracking ouverture email (pixel tracking)
- [ ] Tracking téléchargement PDF
- [ ] Dashboard "Mes courriers envoyés" (historique, statuts)
- [ ] Archivage S3 Glacier (conservation 10 ans)
- [ ] Export journal de preuve (ZIP : PDF + JSON signé)
- [ ] Templates avancés (révision loyer IRL, régularisation charges, etc.)
- [ ] Système d'alerte : "Bail impose LRAR pour mise en demeure → Utiliser QERDS"

---

## 📚 Références

### Documentation Technique
- **Signature électronique** : [signature-strategy-eidas-hybrid.md](./signature-strategy-eidas-hybrid.md)
- **Implémentation TSA** : [IMPLEMENTATION_CERTIFICATION_FLOW.md](./IMPLEMENTATION_CERTIFICATION_FLOW.md)

### Standards et Règlements
- **Règlement eIDAS** : [EUR-Lex](https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32014R0910)
- **Code civil art. 1366-1367** : [Legifrance](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000032040772)
- **Code de procédure civile art. 748-1** : [Legifrance](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006410303)

### Providers
- **CertEurope** : [www.certeurope.fr](https://www.certeurope.fr) - Cachet eIDAS + TSA qualifié
- **AR24** : [www.ar24.fr](https://www.ar24.fr) - QERDS
- **Docaposte** : [www.docaposte.com](https://www.docaposte.com) - QERDS

---

## 📝 TL;DR - Récapitulatif Juridique

### ✅ **Avec Cachet eIDAS Qualifié (QSealC) - 350€/an**

**Ce que tu PEUX faire** (juridiquement conforme) :
- ✅ **Relances de loyer** → Valeur probante très forte (cachet qualifié, 0€/envoi)
- ✅ **Notifications locatives** → Valeur probante très forte (cachet qualifié, 0€/envoi)
- 🟡 **Mises en demeure** → Très forte (cachet qualifié) SAUF si bail impose LRAR
- ✅ **Quittances / Baux / EDL** → Signature avancée (AES) utilisateurs + Cachet Hestia qualifié (ruban vert Adobe)

**Valeur juridique** :
- ✅ **Cachet Hestia (QSealC)** : Signature qualifiée (présomption légale eIDAS art. 35-36)
- ✅ **Signatures utilisateurs** : Signature avancée (AES, recevable eIDAS art. 26)
- ✅ Document : **Présomption légale d'intégrité** (cachet qualifié)
- ✅ Origine : **Présomption légale** (Hestia a émis ce document)
- 🟡 Transmission : **Preuve libre** (logs SMTP contestables, pas QERDS)

---

### ❌ **Ce que Hestia NE FAIT PAS (Volontairement)**

**Actes exclus pour protection des bailleurs** :
- ❌ **Congé / Préavis bailleur** → **Risque juridique majeur** (réception non garantie, cas "routier")
- ❌ **Commandement de payer** → **Monopole légal huissier** (loi 89-462 art. 24)
- ❌ **Assignations / Expulsions** → **Procédures judiciaires complexes**

**Raison stratégique** :
- Cachet eIDAS = Signe le **DOCUMENT** (intégrité + origine) ✅
- Cachet eIDAS ≠ Prouve la **RÉCEPTION** (destinataire peut ignorer) ❌
- Pour congés → Risque : Locataire ne récupère pas courrier → Procédure invalide
- Pour commandements → Responsabilité trop élevée, pas notre métier

**Solution Hestia** :
- ✅ **Redirection huissier partenaire** (workflow intégré, dossier pré-rempli)
- ✅ **Commission 10-20€** par acte (pas de responsabilité juridique)
- ✅ **Protection bailleur** (garantie réception, sécurité juridique)

---

### 🎯 **Architecture Optimale Hestia**

```
┌─────────────────────────────────────────────────────┐
│ ERDS Hestia (350€/an forfait illimité)              │
│ • Cachet eIDAS qualifié (signe PDFs)                │
│ • TSA Django (horodatage interne)                   │
│ • Logs SMTP (preuve d'envoi)                        │
│ • Journal de preuve DB                              │
│ • Archivage 10 ans (PostgreSQL + S3)                │
│ → Relances, mises en demeure, notifications         │
└─────────────────────────────────────────────────────┘
                        +
┌─────────────────────────────────────────────────────┐
│ Redirection Huissier Partenaire                     │
│ • Workflow intégré (export dossier Hestia)          │
│ • Formulaire pré-rempli (bail, quittances, preuves) │
│ • Devis transparent (150-300€/acte)                 │
│ • Commission Hestia (10-20€/acte)                   │
│ → Congés, commandements, assignations, expulsions   │
└─────────────────────────────────────────────────────┘
```

**Workflow type** :
1. Bailleur envoie **relances + mises en demeure** via Hestia (0€/envoi, illimité)
2. Si impayé persiste → **Export dossier complet** (bail + quittances + relances)
3. Redirection **huissier partenaire** → Devis transparent
4. Huissier délivre **commandement de payer** → Réception garantie
5. Hestia reçoit **commission 10-20€** (optionnel)

---

### 💰 **Coût Réaliste : Scénario Impayés (1 dossier/an)**

**Workflow complet avec redirection huissier** :

1. **Relances automatiques** (x5) → Hestia ERDS : **0€** (inclus forfait 350€/an)
2. **Mise en demeure** (x2) → Hestia ERDS : **0€** (inclus forfait)
3. **Export dossier complet** → Hestia : **0€** (automatique)
4. **Commandement de payer** → Huissier partenaire : **~200€**
   - Commission Hestia : **+15€** (optionnel)
5. **Si procédure judiciaire** → Avocat : **Variable**

**Total bailleur** : **~200€** (huissier uniquement)
**Revenue Hestia** : **350€/an** (forfait) + **15€** (commission) = **365€**

**Comparaison LRAR classique** :
- 5 relances LRAR : **25€**
- 2 mises en demeure LRAR : **10€**
- Commandement huissier : **200€**
- **Total** : **235€**

**Avantage Hestia** :
- ✅ Relances/MD illimitées (pas de coût variable)
- ✅ Workflow intégré (gain de temps)
- ✅ Dossier pré-rempli pour huissier (pro)
- ✅ Traçabilité complète (journal de preuve)
- ✅ Cachet eIDAS qualifié (confiance)

---

### ⚖️ **Positionnement Produit Hestia**

**"Courriers Illimités & Sécurisés, Redirection Experts pour Actes Critiques"**

✅ **350€/an forfait** → Envois illimités (relances, mises en demeure, notifications, régularisations)

✅ **Cachet eIDAS qualifié** → Valeur probante forte, ruban vert Adobe

⚖️ **Redirection huissier partenaire** → Congés, commandements (réception garantie, sécurité juridique)

💡 **Protection bailleurs** → Pas de risque juridique sur actes critiques, workflow intégré

**Conforme** : Code civil 1366-1367, eIDAS art. 26/35/44, loi 89-462

---

**Contact technique** : HB CONSULTING - contact@hestia-immo.fr
**Dernière mise à jour** : 20 Octobre 2025
**Statut** : 🚧 EN CONCEPTION - Implémentation à venir
