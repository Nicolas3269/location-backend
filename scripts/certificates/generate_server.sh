#!/bin/bash

#######################################################################
# Génération du certificat serveur Hestia (auto-signé pour TEST)
#
# Génère le certificat serveur pour signer les PDF en local.
# Utilise: hestia_server.cnf
#
# ⚠️  IMPORTANT: Ce certificat est AUTO-SIGNÉ (test uniquement)
# En PRODUCTION, utiliser le certificat qualifié CertEurope AATL (350€/an)
#
# Produit:
# - hestia_server.pem (certificat public)
# - hestia_server.key (clé privée chiffrée AES-256)
# - hestia_server.pfx (format PKCS#12 pour PyHanko)
#######################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
CERT_DIR="$BACKEND_DIR/certificates"

echo "📜 Génération certificat serveur Hestia (TEST)"
echo "=============================================="
echo ""
echo "⚠️  Ce certificat est AUTO-SIGNÉ (test uniquement)"
echo "⚠️  En production, utiliser le certificat CertEurope AATL"
echo ""

# Mot de passe depuis variable d'environnement ou demande interactive
if [ -z "$PASSWORD_CERT_SERVER" ]; then
    echo "🔑 Mot de passe serveur non défini dans l'environnement"
    read -sp "   Entrez le mot de passe pour la clé serveur: " PASSWORD_CERT_SERVER
    echo ""
    read -sp "   Confirmez le mot de passe: " PASSWORD_CONFIRM
    echo ""

    if [ "$PASSWORD_CERT_SERVER" != "$PASSWORD_CONFIRM" ]; then
        echo "❌ Les mots de passe ne correspondent pas"
        exit 1
    fi

    if [ -z "$PASSWORD_CERT_SERVER" ]; then
        echo "❌ Le mot de passe ne peut pas être vide"
        exit 1
    fi
else
    echo "🔑 Utilisation du mot de passe depuis PASSWORD_CERT_SERVER"
fi
echo ""

# Vérifier que le fichier .cnf existe
if [ ! -f "$CERT_DIR/hestia_server.cnf" ]; then
    echo "❌ Fichier de configuration introuvable: hestia_server.cnf"
    exit 1
fi

# 1. Générer la clé privée serveur (2048 bits, chiffrée AES-256)
echo "1/3 - Génération de la clé privée (2048 bits, AES-256)..."
openssl genrsa -aes256 \
    -passout pass:"$PASSWORD_CERT_SERVER" \
    -out "$CERT_DIR/hestia_server.key" \
    2048

echo "✅ Clé privée générée: hestia_server.key"
echo ""

# 2. Générer le certificat serveur auto-signé (valide 1 an)
echo "2/3 - Génération du certificat serveur (valide 1 an)..."
openssl req -new -x509 \
    -key "$CERT_DIR/hestia_server.key" \
    -passin pass:"$PASSWORD_CERT_SERVER" \
    -out "$CERT_DIR/hestia_server.pem" \
    -days 365 \
    -config "$CERT_DIR/hestia_server.cnf"

echo "✅ Certificat serveur généré: hestia_server.pem"
echo ""

# 3. Créer le fichier PFX (format PKCS#12 pour PyHanko)
echo "3/3 - Création du fichier PFX (PKCS#12)..."
openssl pkcs12 -export \
    -out "$CERT_DIR/hestia_server.pfx" \
    -inkey "$CERT_DIR/hestia_server.key" \
    -in "$CERT_DIR/hestia_server.pem" \
    -password pass:"$PASSWORD_CERT_SERVER" \
    -passin pass:"$PASSWORD_CERT_SERVER"

echo "✅ Fichier PFX généré: hestia_server.pfx"
echo ""

# Vérifier le certificat
echo "📋 Détails du certificat serveur:"
openssl x509 -in "$CERT_DIR/hestia_server.pem" -noout \
    -subject -issuer -dates -ext subjectAltName

echo ""
echo "✅ Certificat serveur Hestia généré avec succès!"
echo ""
echo "📝 Variable .env à configurer:"
echo "   PASSWORD_CERT_SERVER=*** (déjà défini)"
echo ""
echo "⚠️  RAPPEL:"
echo "   - Ce certificat est AUTO-SIGNÉ (test uniquement)"
echo "   - Adobe Reader affichera 'Validity UNKNOWN'"
echo "   - En production, utiliser le certificat CertEurope AATL"
