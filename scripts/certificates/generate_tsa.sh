#!/bin/bash

#######################################################################
# Génération du certificat TSA (Time Stamping Authority) Hestia
#
# Génère le certificat TSA pour horodater les signatures PDF (RFC 3161).
#
# ⚠️  IMPORTANT - Deux fichiers .cnf distincts:
# - hestia_tsa_generation.cnf : Utilisé ici pour GÉNÉRER le certificat (une fois)
# - hestia_tsa.cnf : Utilisé par tsa/views.py pour le RUNTIME (à chaque timestamp)
#
# Produit:
# - hestia_tsa.pem (certificat public)
# - hestia_tsa.key (clé privée chiffrée AES-256)
#######################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
CERT_DIR="$BACKEND_DIR/certificates"

echo "📜 Génération Time Stamping Authority (TSA) Hestia"
echo "==================================================="
echo ""

# Mot de passe depuis variable d'environnement ou demande interactive
if [ -z "$PASSWORD_CERT_TSA" ]; then
    echo "🔑 Mot de passe TSA non défini dans l'environnement"
    read -sp "   Entrez le mot de passe pour la clé TSA: " PASSWORD_CERT_TSA
    echo ""
    read -sp "   Confirmez le mot de passe: " PASSWORD_CONFIRM
    echo ""

    if [ "$PASSWORD_CERT_TSA" != "$PASSWORD_CONFIRM" ]; then
        echo "❌ Les mots de passe ne correspondent pas"
        exit 1
    fi

    if [ -z "$PASSWORD_CERT_TSA" ]; then
        echo "❌ Le mot de passe ne peut pas être vide"
        exit 1
    fi
else
    echo "🔑 Utilisation du mot de passe depuis PASSWORD_CERT_TSA"
fi
echo ""

# Vérifier que le fichier .cnf existe
if [ ! -f "$CERT_DIR/hestia_tsa_generation.cnf" ]; then
    echo "❌ Fichier de configuration introuvable: hestia_tsa_generation.cnf"
    exit 1
fi

# 1. Générer la clé privée TSA (4096 bits, chiffrée AES-256)
echo "1/2 - Génération de la clé privée (4096 bits, AES-256)..."
openssl genrsa -aes256 \
    -passout pass:"$PASSWORD_CERT_TSA" \
    -out "$CERT_DIR/hestia_tsa.key" \
    4096

echo "✅ Clé privée générée: hestia_tsa.key"
echo ""

# 2. Générer le certificat TSA auto-signé (valide 10 ans)
echo "2/2 - Génération du certificat TSA (valide 10 ans)..."
openssl req -new -x509 \
    -key "$CERT_DIR/hestia_tsa.key" \
    -passin pass:"$PASSWORD_CERT_TSA" \
    -out "$CERT_DIR/hestia_tsa.pem" \
    -days 3650 \
    -config "$CERT_DIR/hestia_tsa_generation.cnf"

echo "✅ Certificat TSA généré: hestia_tsa.pem"
echo ""

# Vérifier le certificat
echo "📋 Détails du certificat TSA:"
openssl x509 -in "$CERT_DIR/hestia_tsa.pem" -noout \
    -subject -issuer -dates -ext extendedKeyUsage

echo ""
echo "✅ Time Stamping Authority (TSA) Hestia généré avec succès!"
echo ""
echo "📝 Variables .env à configurer:"
echo "   PASSWORD_CERT_TSA=*** (déjà défini)"
