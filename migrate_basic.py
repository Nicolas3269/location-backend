#!/usr/bin/env python
"""
Script simple pour migrer juste les données non-géométriques en attendant
une solution pour les données spatiales
"""

import os
import sqlite3

import django

# Configuration de Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from rent_control.models import RentControlArea, RentPrice


def migrate_basic_data():
    """Migre toutes les données de geodb.sqlite3 vers PostgreSQL"""
    print("🚀 Migration des données de geodb.sqlite3...")

    # Connexion à la base géographique uniquement
    geo_db = sqlite3.connect("geodb.sqlite3")
    geo_db.row_factory = sqlite3.Row

    # Charger l'extension SpatiaLite
    geo_db.enable_load_extension(True)
    try:
        geo_db.load_extension("mod_spatialite")
        spatialite_loaded = True
    except sqlite3.OperationalError:
        try:
            geo_db.load_extension("libspatialite")
            spatialite_loaded = True
        except sqlite3.OperationalError:
            print("⚠️  Impossible de charger SpatiaLite, migration sans géométries")
            spatialite_loaded = False

    # Migration des zones géographiques SANS géométries
    print("  - Migration des zones de contrôle (sans géométries)...")
    cursor = geo_db.cursor()

    cursor.execute(
        """SELECT id, region, reference_year, zone_id, quartier_id, zone_name 
           FROM rent_control_rentcontrolarea"""
    )

    for row in cursor.fetchall():
        try:
            # Créer une géométrie vide par défaut
            from django.contrib.gis.geos import MultiPolygon
            empty_geom = MultiPolygon()

            area, created = RentControlArea.objects.get_or_create(
                id=row["id"],
                defaults={
                    "region": row["region"],
                    "reference_year": row["reference_year"],
                    "zone_id": row["zone_id"],
                    "quartier_id": row["quartier_id"],
                    "zone_name": row["zone_name"],
                    "geometry": empty_geom,
                },
            )
            if created:
                print(f"    ✓ Zone créée: {area.zone_name or area.zone_id}")
            else:
                print(f"    - Zone existe: {area.zone_name or area.zone_id}")

        except Exception as e:
            print(f"    ✗ Erreur pour la zone {row['id']}: {e}")

    # Migration des prix
    print("  - Migration des prix...")
    cursor.execute("SELECT * FROM rent_control_rentprice")

    for row in cursor.fetchall():
        price, created = RentPrice.objects.get_or_create(
            id=row["id"],
            defaults={
                "reference_year": row["reference_year"],
                "property_type": row["property_type"],
                "room_count": row["room_count"],
                "construction_period": row["construction_period"],
                "furnished": bool(row["furnished"]),
                "reference_price": row["reference_price"],
                "min_price": row["min_price"],
                "max_price": row["max_price"],
            },
        )
        if created:
            print(f"    ✓ Prix créé: ID {price.id}")
        else:
            print(f"    - Prix existe: ID {price.id}")

    # Migration des relations many-to-many
    print("  - Migration des relations prix-zones...")
    cursor.execute("SELECT * FROM rent_control_rentprice_areas")

    for row in cursor.fetchall():
        try:
            price = RentPrice.objects.get(id=row["rentprice_id"])
            area = RentControlArea.objects.get(id=row["rentcontrolarea_id"])
            if not price.areas.filter(id=area.id).exists():
                price.areas.add(area)
                print(f"    ✓ Relation créée: Prix {price.id} <-> Zone {area.id}")
            else:
                print(f"    - Relation existe: Prix {price.id} <-> Zone {area.id}")
        except (RentPrice.DoesNotExist, RentControlArea.DoesNotExist) as e:
            print(f"    ✗ Relation échouée: {e}")

    # Créer un superutilisateur si nécessaire
    geo_db.close()

    print("✅ Migration terminée!")
    print("📊 Toutes les données de geodb.sqlite3 ont été migrées vers PostgreSQL")
    print("⚠️  Les géométries sont vides - utilisez migrate_geometries.py pour les migrer")


if __name__ == "__main__":
    migrate_basic_data()
