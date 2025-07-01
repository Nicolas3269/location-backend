#!/usr/bin/env python
"""
Script spécialisé pour migrer uniquement les géométries des RentControlArea
depuis geodb.sqlite3 vers PostgreSQL PostGIS
"""

import os
import sqlite3

import django

# Configuration de Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from rent_control.models import RentControlArea


def migrate_geometries():
    """Migre uniquement les géométries des zones de contrôle"""
    print("🗺️  Migration des géométries depuis geodb.sqlite3...")

    # Connexion à la base géographique
    geo_db = sqlite3.connect("geodb.sqlite3")
    geo_db.row_factory = sqlite3.Row

    # Charger l'extension SpatiaLite
    geo_db.enable_load_extension(True)
    try:
        geo_db.load_extension("mod_spatialite")
        spatialite_loaded = True
        print("  ✓ Extension SpatiaLite chargée")
    except sqlite3.OperationalError:
        try:
            geo_db.load_extension("libspatialite")
            spatialite_loaded = True
            print("  ✓ Extension libspatialite chargée")
        except sqlite3.OperationalError:
            print("  ❌ Impossible de charger SpatiaLite")
            return False

    # Migration des géométries uniquement
    print("  - Mise à jour des géométries des zones de contrôle...")
    cursor = geo_db.cursor()

    # Récupérer les géométries avec AsText pour SpatiaLite
    cursor.execute(
        """SELECT id, AsText(geometry) as geometry_wkt 
           FROM rent_control_rentcontrolarea 
           WHERE geometry IS NOT NULL"""
    )

    success_count = 0
    error_count = 0

    for row in cursor.fetchall():
        try:
            # Récupérer la zone existante
            area = RentControlArea.objects.get(id=row["id"])

            # Convertir la géométrie WKT en objet Django GIS
            if row["geometry_wkt"]:
                from django.contrib.gis.geos import GEOSGeometry

                geometry = GEOSGeometry(row["geometry_wkt"], srid=4326)

                # Mettre à jour seulement la géométrie
                area.geometry = geometry
                area.save(update_fields=["geometry"])

                success_count += 1
                print(f"    ✓ Géométrie mise à jour: {area.zone_name or area.zone_id}")
            else:
                print(f"    ⚠️  Pas de géométrie pour: {area.zone_name or area.zone_id}")

        except RentControlArea.DoesNotExist:
            print(f"    ❌ Zone introuvable (ID {row['id']})")
            error_count += 1
        except Exception as e:
            print(f"    ❌ Erreur pour la zone {row['id']}: {e}")
            error_count += 1

    geo_db.close()

    print("\n✅ Migration des géométries terminée!")
    print("📊 Statistiques:")
    print(f"   - Géométries mises à jour: {success_count}")
    print(f"   - Erreurs: {error_count}")

    return error_count == 0


def verify_geometries():
    """Vérifie que les géométries ont été correctement migrées"""
    print("\n🔍 Vérification des géométries...")

    # Compter les zones avec et sans géométries
    total_areas = RentControlArea.objects.count()
    areas_with_geom = (
        RentControlArea.objects.exclude(geometry__isnull=True)
        .exclude(geometry__isempty=True)
        .count()
    )
    areas_without_geom = total_areas - areas_with_geom

    print(f"  - Total des zones: {total_areas}")
    print(f"  - Zones avec géométries: {areas_with_geom}")
    print(f"  - Zones sans géométries: {areas_without_geom}")

    if areas_without_geom > 0:
        print(f"  ⚠️  {areas_without_geom} zones n'ont pas de géométries")
    else:
        print("  ✅ Toutes les zones ont des géométries valides")


if __name__ == "__main__":
    if migrate_geometries():
        verify_geometries()
        print("\n🎉 Migration des géométries réussie!")
    else:
        print("\n❌ Erreurs pendant la migration des géométries")
