#!/bin/bash

#######################################################################
# Script master de régénération de TOUS les certificats Hestia
#
# Régénère dans l'ordre :
# 1. Certificate Authority (CA) Hestia
# 2. Time Stamping Authority (TSA) Hestia
# 3. Certificat serveur auto-signé (test uniquement)
#
# IMPORTANT: Ce script est pour l'environnement LOCAL uniquement.
# En PRODUCTION, utiliser le certificat qualifié CertEurope AATL.
#######################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
CERT_DIR="$BACKEND_DIR/certificates"

echo "🔐 Régénération COMPLÈTE des certificats Hestia"
echo "================================================"
echo ""
echo "⚠️  ATTENTION : Cette opération va REMPLACER tous les certificats existants!"
echo "⚠️  Les anciennes clés privées seront PERDUES!"
echo "⚠️  Les documents signés avec les anciens certificats ne seront plus vérifiables!"
echo ""
read -p "Voulez-vous continuer? (yes/NO) " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "❌ Opération annulée"
    exit 0
fi

# Créer le répertoire certificats si nécessaire
mkdir -p "$CERT_DIR"

# Sauvegarder les anciens certificats
if [ -d "$CERT_DIR" ] && [ "$(ls -A $CERT_DIR/*.pem 2>/dev/null)" ]; then
    BACKUP_DIR="$CERT_DIR/backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    echo "💾 Sauvegarde des anciens certificats dans $BACKUP_DIR..."
    cp "$CERT_DIR"/*.pem "$BACKUP_DIR/" 2>/dev/null || true
    cp "$CERT_DIR"/*.key "$BACKUP_DIR/" 2>/dev/null || true
    cp "$CERT_DIR"/*.pfx "$BACKUP_DIR/" 2>/dev/null || true
    echo "✅ Sauvegarde terminée"
    echo ""
fi

# Charger les mots de passe depuis .env si disponible
if [ -f "$BACKEND_DIR/.env" ]; then
    echo "📝 Tentative de chargement des mots de passe depuis .env..."
    # Utiliser set -a pour auto-export
    set -a
    source <(grep -E "^PASSWORD_CERT_" "$BACKEND_DIR/.env")
    set +a
    echo "✅ Variables chargées depuis .env"
    echo ""
fi

# Vérifier que tous les mots de passe sont définis
MISSING_PASSWORDS=0

if [ -z "$PASSWORD_CERT_CA" ]; then
    echo "⚠️  PASSWORD_CERT_CA non défini"
    MISSING_PASSWORDS=1
fi

if [ -z "$PASSWORD_CERT_TSA" ]; then
    echo "⚠️  PASSWORD_CERT_TSA non défini"
    MISSING_PASSWORDS=1
fi

if [ -z "$PASSWORD_CERT_SERVER" ]; then
    echo "⚠️  PASSWORD_CERT_SERVER non défini"
    MISSING_PASSWORDS=1
fi

if [ $MISSING_PASSWORDS -eq 1 ]; then
    echo ""
    echo "❌ Certains mots de passe ne sont pas définis dans .env"
    echo ""
    echo "Options:"
    echo "   1. Définir les variables dans $BACKEND_DIR/.env:"
    echo "      PASSWORD_CERT_CA=votre_mot_de_passe"
    echo "      PASSWORD_CERT_TSA=votre_mot_de_passe"
    echo "      PASSWORD_CERT_SERVER=votre_mot_de_passe"
    echo ""
    echo "   2. Exporter les variables avant d'exécuter ce script:"
    echo "      export PASSWORD_CERT_CA=..."
    echo "      export PASSWORD_CERT_TSA=..."
    echo "      export PASSWORD_CERT_SERVER=..."
    echo ""
    echo "   3. Utiliser les scripts individuels qui demandent les mots de passe:"
    echo "      ./scripts/generate_ca.sh"
    echo "      ./scripts/generate_tsa.sh"
    echo "      ./scripts/generate_server.sh"
    echo ""
    exit 1
fi

echo "🔑 Mots de passe chargés avec succès"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

#######################################################################
# 1. CERTIFICATE AUTHORITY (CA) HESTIA
#######################################################################

echo "📜 1/3 - Génération Certificate Authority (CA)..."
echo ""
bash "$SCRIPT_DIR/generate_ca.sh"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

#######################################################################
# 2. TIME STAMPING AUTHORITY (TSA) HESTIA
#######################################################################

echo "📜 2/3 - Génération Time Stamping Authority (TSA)..."
echo ""
bash "$SCRIPT_DIR/generate_tsa.sh"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

#######################################################################
# 3. CERTIFICAT SERVEUR AUTO-SIGNÉ (TEST UNIQUEMENT)
#######################################################################

echo "📜 3/3 - Génération certificat serveur (TEST)..."
echo ""
bash "$SCRIPT_DIR/generate_server.sh"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

#######################################################################
# RÉSUMÉ ET PROCHAINES ÉTAPES
#######################################################################

echo "✅ TOUS les certificats ont été régénérés avec succès!"
echo ""
echo "📂 Fichiers générés dans $CERT_DIR:"
echo "   ✅ hestia_certificate_authority.pem (CA cert)"
echo "   ✅ hestia_certificate_authority.key (CA key)"
echo "   ✅ hestia_tsa.pem (TSA cert)"
echo "   ✅ hestia_tsa.key (TSA key)"
echo "   ✅ hestia_server.pem (Server cert - TEST)"
echo "   ✅ hestia_server.key (Server key - TEST)"
echo "   ✅ hestia_server.pfx (Server PFX - TEST)"
echo ""
echo "📝 Variables .env configurées:"
echo "   PASSWORD_CERT_CA=***"
echo "   PASSWORD_CERT_TSA=***"
echo "   PASSWORD_CERT_SERVER=***"
echo ""
echo "🚀 Prochaines étapes:"
echo "   1. Créer les migrations TSA: python manage.py makemigrations tsa"
echo "   2. Appliquer les migrations: python manage.py migrate"
echo "   3. Redémarrer le serveur: python manage.py runserver 8003"
echo "   4. Tester la signature d'un document"
echo "   5. Vérifier avec Adobe Reader (warnings normaux pour certificats auto-signés)"
echo ""
echo "⚠️  RAPPEL IMPORTANT:"
echo "   Ces certificats sont AUTO-SIGNÉS et pour TEST UNIQUEMENT."
echo "   En PRODUCTION, utiliser le certificat qualifié CertEurope AATL (350€/an)."
echo "   Seul le certificat CertEurope affichera le ruban vert dans Adobe Reader."
echo ""
echo "✅ Régénération terminée!"
