# location-backend

apt-get install libspatialite-dev spatialite-bin
sudo apt-get install libsqlite3-mod-spatialite python3-gdal gdal-bin

# Carefull for rent_control

python manage.py makemigrations rent_control
python manage.py migrate rent_control --database=geodb

## Migration des données rent_control vers production

### Vue d'ensemble

Le projet utilise un système de migration Django personnalisé pour transférer efficacement les données volumineuses de `rent_control` (zones géographiques et prix) depuis une base de données locale vers la production.

### Configuration des bases de données

Le projet utilise une configuration multi-base dans `settings.py` :

```python
DATABASES = {
    "default": {  # Production
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": os.getenv("POSTGRES_DB", "hestia_db"),
        "USER": os.getenv("POSTGRES_USER", "postgres"),
        # ... autres paramètres
    },
    "local": {  # Base de données locale
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": "hestia_db",
        "USER": "postgres",
        # ... paramètres locaux
    },
}
```

### Script de migration

#### Commande Django directe

```bash
# Migration basique
python manage.py migrate_rent_data --clear-target

# Avec options avancées
python manage.py migrate_rent_data --batch-size 500 --clear-target --dry-run
```

#### Options disponibles

| Option           | Description                                     | Exemple            |
| ---------------- | ----------------------------------------------- | ------------------ |
| `--batch-size N` | Taille des batches d'insertion (défaut: 1000)   | `--batch-size 500` |
| `--dry-run`      | Mode simulation sans écriture en base           | `--dry-run`        |
| `--force`        | Force la migration même si des données existent | `--force`          |
| `--clear-target` | Vide les tables de destination avant migration  | `--clear-target`   |

### Fonctionnement de la migration

#### 1. Tables migrées

- **`RentControlArea`** : Zones géographiques avec géométries PostGIS
- **`RentPrice`** : Prix par caractéristiques de logement
- **Relations M2M** : Liaisons entre zones et prix

#### 2. Processus de migration

1. **Test des connexions** (local + production)
2. **Vérification des données existantes**
3. **Nettoyage optionnel** (`--clear-target`)
4. **Migration des RentControlArea** avec mapping des IDs
5. **Migration des RentPrice** avec relations M2M
6. **Rapport de performance**

#### 3. Optimisations

- **Insertions par batch** : `bulk_create()` pour la performance
- **Transactions atomiques** : Rollback automatique en cas d'erreur
- **Prefetch des relations** : `prefetch_related("areas")`
- **Mapping des IDs** : Préservation des relations entre tables
- **Géométries PostGIS** : Transfert direct des données spatiales

### Performances typiques

Pour une base avec ~3000 zones et ~2400 prix :

- **Durée** : ~6 minutes
- **Débit** : ~16 zones/seconde, ~7 prix/seconde
- **Mémoire** : Optimisée par les batches
- **Réseau** : Minimisé par les insertions groupées

### Dépannage

#### Erreurs courantes

```bash
# Connexion échouée
❌ Vérifiez vos variables d'environnement de Production

# Données existantes
⚠️  Utilisez --force ou --clear-target

# Timeout réseau
📊 Réduisez --batch-size (ex: 500)
```

#### Logs détaillés

```bash
# Mode verbose avec timestamps
python manage.py migrate_rent_data --verbosity 2
```

# map

http://localhost:8003/admin/rent_control/rentcontrolarea/region_map/

# Pour encoder ton certificat :

base64 -w 0 cert.pfx

# ou `base64 cert.pfx` sur macOS

# docker:

docker build -t hestia-backend .
docker run -p 8003:8000 --env-file .env hestia-backend
