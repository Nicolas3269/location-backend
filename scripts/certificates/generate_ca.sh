#!/bin/bash

#######################################################################
# Génération du Certificate Authority (CA) Hestia
#
# Génère le certificat CA pour signer les certificats utilisateurs.
# Utilise: hestia_certificate_authority.cnf
#
# Produit:
# - hestia_certificate_authority.pem (certificat public)
# - hestia_certificate_authority.key (clé privée chiffrée AES-256)
#######################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
CERT_DIR="$BACKEND_DIR/certificates"

echo "📜 Génération Certificate Authority (CA) Hestia"
echo "================================================"
echo ""

# Mot de passe depuis variable d'environnement ou demande interactive
if [ -z "$PASSWORD_CERT_CA" ]; then
    echo "🔑 Mot de passe CA non défini dans l'environnement"
    read -sp "   Entrez le mot de passe pour la clé CA: " PASSWORD_CERT_CA
    echo ""
    read -sp "   Confirmez le mot de passe: " PASSWORD_CONFIRM
    echo ""

    if [ "$PASSWORD_CERT_CA" != "$PASSWORD_CONFIRM" ]; then
        echo "❌ Les mots de passe ne correspondent pas"
        exit 1
    fi

    if [ -z "$PASSWORD_CERT_CA" ]; then
        echo "❌ Le mot de passe ne peut pas être vide"
        exit 1
    fi
else
    echo "🔑 Utilisation du mot de passe depuis PASSWORD_CERT_CA"
fi
echo ""

# Vérifier que le fichier .cnf existe
if [ ! -f "$CERT_DIR/hestia_certificate_authority.cnf" ]; then
    echo "❌ Fichier de configuration introuvable: hestia_certificate_authority.cnf"
    exit 1
fi

# 1. Générer la clé privée CA (4096 bits, chiffrée AES-256)
echo "1/2 - Génération de la clé privée (4096 bits, AES-256)..."
openssl genrsa -aes256 \
    -passout pass:"$PASSWORD_CERT_CA" \
    -out "$CERT_DIR/hestia_certificate_authority.key" \
    4096

echo "✅ Clé privée générée: hestia_certificate_authority.key"
echo ""

# 2. Générer le certificat CA auto-signé (valide 10 ans)
echo "2/2 - Génération du certificat CA (valide 10 ans)..."
openssl req -new -x509 \
    -key "$CERT_DIR/hestia_certificate_authority.key" \
    -passin pass:"$PASSWORD_CERT_CA" \
    -out "$CERT_DIR/hestia_certificate_authority.pem" \
    -days 3650 \
    -config "$CERT_DIR/hestia_certificate_authority.cnf"

echo "✅ Certificat CA généré: hestia_certificate_authority.pem"
echo ""

# Vérifier le certificat
echo "📋 Détails du certificat CA:"
openssl x509 -in "$CERT_DIR/hestia_certificate_authority.pem" -noout \
    -subject -issuer -dates -ext basicConstraints -ext keyUsage

echo ""
echo "✅ Certificate Authority (CA) Hestia généré avec succès!"
echo ""
echo "📝 Variable .env à configurer:"
echo "   PASSWORD_CERT_CA=*** (déjà défini)"
