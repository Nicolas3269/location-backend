#!/bin/bash

# Script de test de restauration d'un backup PostgreSQL
# Usage:
#   ./backend/scripts/test_restore.sh backups/backup_20260113_151107.dump

set -e

if [ -z "$1" ]; then
    echo "Erreur: Fichier dump non spécifié"
    echo ""
    echo "Usage:"
    echo "  ./backend/scripts/test_restore.sh backups/backup_xxx.dump"
    exit 1
fi

DUMP_FILE="$1"

if [ ! -f "$DUMP_FILE" ]; then
    echo "Erreur: Fichier $DUMP_FILE introuvable"
    exit 1
fi

CONTAINER_NAME="pg_restore_test"
POSTGRES_PASSWORD="testpassword"

echo "=== Test de restauration du backup ==="
echo "Fichier: $DUMP_FILE"
echo ""

# Arrêter et supprimer le container s'il existe
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Lancer un container PostgreSQL avec PostGIS
echo "Demarrage du container PostgreSQL..."
docker run -d \
    --platform linux/amd64 \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB=railway \
    -p 5555:5432 \
    postgis/postgis:16-master

# Attendre que PostgreSQL soit prêt
echo "Attente du demarrage de PostgreSQL..."
sleep 5

for i in {1..30}; do
    if docker exec "$CONTAINER_NAME" pg_isready -U postgres > /dev/null 2>&1; then
        echo "PostgreSQL pret."
        break
    fi
    sleep 1
done

# Restaurer le backup
echo ""
echo "Restauration du backup..."
PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
    -h localhost \
    -p 5555 \
    -U postgres \
    -d railway \
    --no-owner \
    --no-privileges \
    "$DUMP_FILE" 2>&1 || true

# Vérifier les tables restaurées
echo ""
echo "=== Tables restaurees ==="
PGPASSWORD="$POSTGRES_PASSWORD" psql -h localhost -p 5555 -U postgres -d railway -c "\dt" 2>/dev/null

# Compter les enregistrements dans les tables principales
echo ""
echo "=== Comptage des enregistrements ==="
PGPASSWORD="$POSTGRES_PASSWORD" psql -h localhost -p 5555 -U postgres -d railway -c "
SELECT
    schemaname || '.' || relname AS table,
    n_live_tup AS rows
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC
LIMIT 20;
" 2>/dev/null

echo ""
echo "=== Test termine ==="
echo ""
echo "Pour explorer manuellement:"
echo "  PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -p 5555 -U postgres -d railway"
echo ""
echo "Pour arreter le container:"
echo "  docker rm -f $CONTAINER_NAME"
