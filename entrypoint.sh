#!/bin/sh

# Recrée le fichier à partir de l'env var
if [ -n "$CERTIFICATE_B64" ]; then
  echo "$CERTIFICATE_B64" | base64 -d > /app/cert.pfx
fi

# Applique les migrations
python manage.py migrate

exec "$@"