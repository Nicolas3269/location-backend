#!/bin/bash

#######################################################################
# Script d'encodage des certificats Hestia en base64 pour Railway
#
# Encode tous les certificats en base64 et génère le fichier
# .env.railway pour import direct dans Railway (Raw Editor).
#######################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
CERT_DIR="$BACKEND_DIR/certificates"

echo "🔐 Encodage des certificats Hestia pour Railway"
echo "================================================"
echo ""

# Vérifier que les certificats existent
if [ ! -f "$CERT_DIR/hestia_certificate_authority.pem" ]; then
    echo "❌ Certificats non trouvés dans $CERT_DIR"
    echo "❌ Exécutez d'abord: ./scripts/regenerate_all_certificates.sh"
    exit 1
fi

echo "📝 Génération du fichier .env.railway..."
echo ""

#######################################################################
# GÉNÉRATION DU FICHIER .env.railway
#######################################################################

echo "═══════════════════════════════════════════════════════════════"
echo "📦 GÉNÉRATION .env.railway (Raw Editor)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

ENV_FILE="$BACKEND_DIR/.env.railway"

cat > "$ENV_FILE" << EOF
# ============================================================
# Railway Environment Variables - Hestia Production
# ============================================================
# IMPORTANT: Ne JAMAIS committer ce fichier dans Git !
# Ce fichier contient les certificats encodés en base64
# À importer dans Railway via : Settings > Variables > Raw Editor
# ============================================================

# Certificat serveur AATL Hestia (cachet qualifié eIDAS CertEurope)
# ⚠️  En production, remplacer par le certificat CertEurope
CERTIFICATE_B64=$(base64 -w 0 "$CERT_DIR/hestia_server.pfx")

# Certificate Authority Hestia (auto-signée, signe les certificats utilisateurs)
HESTIA_CA_CERT_B64=$(base64 -w 0 "$CERT_DIR/hestia_certificate_authority.pem")
HESTIA_CA_KEY_B64=$(base64 -w 0 "$CERT_DIR/hestia_certificate_authority.key")

# TSA Hestia (Time Stamping Authority - RFC 3161)
TSA_CERT_B64=$(base64 -w 0 "$CERT_DIR/hestia_tsa.pem")
TSA_KEY_B64=$(base64 -w 0 "$CERT_DIR/hestia_tsa.key")

# ⚠️  COPIER MANUELLEMENT DEPUIS VOTRE .env LOCAL:
# PASSWORD_CERT_CA=votre_mot_de_passe_ca
# PASSWORD_CERT_TSA=votre_mot_de_passe_tsa
# PASSWORD_CERT_SERVER=votre_mot_de_passe_server
EOF

echo "✅ Fichier généré: $ENV_FILE"
echo ""
echo "📋 COMMENT IMPORTER DANS RAILWAY:"
echo ""
echo "1. Ouvrir Railway > Votre projet > Settings > Variables"
echo "2. Cliquer sur 'Raw Editor' en haut à droite"
echo "3. Copier-coller le contenu de .env.railway"
echo "4. Ajouter manuellement les mots de passe depuis votre .env local"
echo "5. Redéployer"
echo ""
echo "⚠️  N'OUBLIEZ PAS:"
echo "   - Ajouter PASSWORD_CERT_CA depuis votre .env local"
echo "   - Ajouter PASSWORD_CERT_TSA depuis votre .env local"
echo "   - Ajouter PASSWORD_CERT_SERVER depuis votre .env local"
echo ""

echo "✅ Script terminé!"
