#!/bin/bash

# Script de backup PostgreSQL Railway
# Usage (depuis la racine du projet):
#   ./backend/scripts/backup_db.sh backend/.env.production
#   ./backend/scripts/backup_db.sh backend/.env.staging
#
# Le fichier .env doit contenir:
#   POSTGRES_DB=railway
#   POSTGRES_USER=postgres
#   POSTGRES_PASSWORD=xxx
#   POSTGRES_HOST=xxx
#   POSTGRES_PORT=xxx

set -e

# Vérification de l'argument
if [ -z "$1" ]; then
    echo "Erreur: Fichier .env non spécifié"
    echo ""
    echo "Usage:"
    echo "  ./backend/scripts/backup_db.sh backend/.env.production"
    echo "  ./backend/scripts/backup_db.sh backend/.env.staging"
    exit 1
fi

ENV_FILE="$1"

if [ ! -f "$ENV_FILE" ]; then
    echo "Erreur: Fichier $ENV_FILE introuvable"
    exit 1
fi

# Charger uniquement les variables POSTGRES_* depuis le fichier .env (dernière occurrence si doublon)
POSTGRES_DB=$(grep "^POSTGRES_DB=" "$ENV_FILE" | tail -1 | cut -d '=' -f2)
POSTGRES_USER=$(grep "^POSTGRES_USER=" "$ENV_FILE" | tail -1 | cut -d '=' -f2)
POSTGRES_PASSWORD=$(grep "^POSTGRES_PASSWORD=" "$ENV_FILE" | tail -1 | cut -d '=' -f2)
POSTGRES_HOST=$(grep "^POSTGRES_HOST=" "$ENV_FILE" | tail -1 | cut -d '=' -f2)
POSTGRES_PORT=$(grep "^POSTGRES_PORT=" "$ENV_FILE" | tail -1 | cut -d '=' -f2)

# Vérification des variables
if [ -z "$POSTGRES_HOST" ] || [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_PASSWORD" ] || [ -z "$POSTGRES_DB" ] || [ -z "$POSTGRES_PORT" ]; then
    echo "Erreur: Variables PostgreSQL manquantes dans $ENV_FILE"
    echo "Requis: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT"
    exit 1
fi

# Construire l'URL de connexion
DATABASE_URL="postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"

# Configuration - backups à la racine du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="backup_${TIMESTAMP}.dump"

# Créer le dossier de backups
mkdir -p "$BACKUP_DIR"

echo "Backup en cours..."

# Faire le backup
pg_dump -Fc "$DATABASE_URL" > "$BACKUP_DIR/$BACKUP_NAME"

# Vérifier que le fichier n'est pas vide
if [ ! -s "$BACKUP_DIR/$BACKUP_NAME" ]; then
    echo "Erreur: Le backup est vide"
    rm -f "$BACKUP_DIR/$BACKUP_NAME"
    exit 1
fi

# Taille du backup
SIZE=$(ls -lh "$BACKUP_DIR/$BACKUP_NAME" | awk '{print $5}')

echo "Backup OK: $BACKUP_DIR/$BACKUP_NAME ($SIZE)"

# Optionnel: garder seulement les N derniers backups
KEEP_LAST=10
COUNT=$(ls -1 "$BACKUP_DIR"/*.dump 2>/dev/null | wc -l)
if [ "$COUNT" -gt "$KEEP_LAST" ]; then
    ls -t "$BACKUP_DIR"/*.dump | tail -n +$((KEEP_LAST + 1)) | xargs rm -f
    echo "Anciens backups supprimés (garde les $KEEP_LAST derniers)"
fi

echo ""
echo "Pour restaurer:"
echo "  pg_restore -d \"\$DATABASE_URL\" $BACKUP_DIR/$BACKUP_NAME"
