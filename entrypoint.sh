#!/bin/sh
set -e

echo "🔐 Décodage des certificats depuis variables d'environnement..."
mkdir -p /app/certificates

# Certificat serveur AATL Hestia
if [ -n "$CERTIFICATE_B64" ]; then
  echo "✅ Décodage certificat serveur AATL..."
  echo "$CERTIFICATE_B64" | base64 -d > /app/certificates/hestia_server.pfx
fi

# Certificate Authority Hestia
if [ -n "$HESTIA_CA_CERT_B64" ]; then
  echo "✅ Décodage Hestia Certificate Authority..."
  echo "$HESTIA_CA_CERT_B64" | base64 -d > /app/certificates/hestia_certificate_authority.pem
fi

if [ -n "$HESTIA_CA_KEY_B64" ]; then
  echo "✅ Décodage clé CA Hestia..."
  echo "$HESTIA_CA_KEY_B64" | base64 -d > /app/certificates/hestia_certificate_authority.key
fi

# TSA Hestia
if [ -n "$TSA_CERT_B64" ]; then
  echo "✅ Décodage certificat TSA Hestia..."
  echo "$TSA_CERT_B64" | base64 -d > /app/certificates/hestia_tsa.pem
fi

if [ -n "$TSA_KEY_B64" ]; then
  echo "✅ Décodage clé TSA Hestia..."
  echo "$TSA_KEY_B64" | base64 -d > /app/certificates/hestia_tsa.key
fi

echo "✅ Certificats décodés avec succès"

# Applique les migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

exec "$@"