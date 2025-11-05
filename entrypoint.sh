#!/bin/sh
set -e

echo "🔐 Décodage des certificats depuis variables d'environnement..."
mkdir -p /app/certificates

# Certificat serveur AATL Hestia
if [ -n "$CERTIFICATE_B64" ]; then
  echo "✅ Décodage certificat serveur AATL..."
  echo "$CERTIFICATE_B64" | base64 -d > /app/certificates/hestia_server.pfx
  if [ -f /app/certificates/hestia_server.pfx ]; then
    echo "   ✅ Fichier créé: hestia_server.pfx ($(stat -c%s /app/certificates/hestia_server.pfx) bytes)"

    # Extraire le certificat PEM depuis le PFX pour ValidationContext
    if [ -n "$PASSWORD_CERT_SERVER" ]; then
      echo "   📤 Extraction du certificat PEM depuis PFX..."
      openssl pkcs12 -in /app/certificates/hestia_server.pfx \
        -clcerts -nokeys -out /app/certificates/hestia_server.pem \
        -passin pass:"$PASSWORD_CERT_SERVER" -passout pass: 2>/dev/null

      if [ -f /app/certificates/hestia_server.pem ]; then
        echo "   ✅ Certificat PEM extrait: hestia_server.pem ($(stat -c%s /app/certificates/hestia_server.pem) bytes)"
      else
        echo "   ⚠️  Échec extraction PEM (ValidationContext incomplet)"
      fi
    else
      echo "   ⚠️  PASSWORD_CERT_SERVER manquant, extraction PEM impossible"
    fi
  else
    echo "   ❌ ERREUR: Fichier hestia_server.pfx non créé!"
  fi
else
  echo "⚠️  Variable CERTIFICATE_B64 non définie - Certificat serveur manquant"
fi

# Certificate Authority Hestia
if [ -n "$HESTIA_CA_CERT_B64" ]; then
  echo "✅ Décodage Hestia Certificate Authority..."
  echo "$HESTIA_CA_CERT_B64" | base64 -d > /app/certificates/hestia_certificate_authority.pem
  if [ -f /app/certificates/hestia_certificate_authority.pem ]; then
    echo "   ✅ Fichier créé: hestia_certificate_authority.pem ($(stat -c%s /app/certificates/hestia_certificate_authority.pem) bytes)"
  else
    echo "   ❌ ERREUR: Fichier hestia_certificate_authority.pem non créé!"
  fi
else
  echo "⚠️  Variable HESTIA_CA_CERT_B64 non définie"
fi

if [ -n "$HESTIA_CA_KEY_B64" ]; then
  echo "✅ Décodage clé CA Hestia..."
  echo "$HESTIA_CA_KEY_B64" | base64 -d > /app/certificates/hestia_certificate_authority.key
  if [ -f /app/certificates/hestia_certificate_authority.key ]; then
    echo "   ✅ Fichier créé: hestia_certificate_authority.key ($(stat -c%s /app/certificates/hestia_certificate_authority.key) bytes)"
  else
    echo "   ❌ ERREUR: Fichier hestia_certificate_authority.key non créé!"
  fi
else
  echo "⚠️  Variable HESTIA_CA_KEY_B64 non définie"
fi

# TSA Hestia
if [ -n "$TSA_CERT_B64" ]; then
  echo "✅ Décodage certificat TSA Hestia..."
  echo "$TSA_CERT_B64" | base64 -d > /app/certificates/hestia_tsa.pem
  if [ -f /app/certificates/hestia_tsa.pem ]; then
    echo "   ✅ Fichier créé: hestia_tsa.pem ($(stat -c%s /app/certificates/hestia_tsa.pem) bytes)"
  else
    echo "   ❌ ERREUR: Fichier hestia_tsa.pem non créé!"
  fi
else
  echo "⚠️  Variable TSA_CERT_B64 non définie"
fi

if [ -n "$TSA_KEY_B64" ]; then
  echo "✅ Décodage clé TSA Hestia..."
  echo "$TSA_KEY_B64" | base64 -d > /app/certificates/hestia_tsa.key
  if [ -f /app/certificates/hestia_tsa.key ]; then
    echo "   ✅ Fichier créé: hestia_tsa.key ($(stat -c%s /app/certificates/hestia_tsa.key) bytes)"
  else
    echo "   ❌ ERREUR: Fichier hestia_tsa.key non créé!"
  fi
else
  echo "⚠️  Variable TSA_KEY_B64 non définie"
fi

echo ""
echo "📋 Liste des certificats décodés:"
ls -lh /app/certificates/ 2>/dev/null || echo "   ⚠️  Répertoire /app/certificates vide ou inexistant"
echo ""
echo "✅ Décodage des certificats terminé"

# Applique les migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

exec "$@"