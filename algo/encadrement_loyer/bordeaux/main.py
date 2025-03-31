import os

import fiona
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

# === 1. Chemins ===
extract_dir = "algo/encadrement_loyer/bordeaux"
shapefile_path = os.path.join(extract_dir, "dataset", "l_zonage_oll_bordeaux.shp")

# === 2. Reprojecteur EPSG:2154 → EPSG:4326 ===
transformer = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)


def reproject_geometry(geom):
    shapely_geom = shape(geom)
    reprojected = shapely_transform(transformer.transform, shapely_geom)
    return mapping(reprojected)


def get_goejson_properties():
    """Récupère les propriétés du GeoJSON"""
    # === 3. Extraction des features avec reprojection
    features = []
    with fiona.open(shapefile_path, "r") as src:
        for feat in src:
            reprojected_geom = reproject_geometry(feat["geometry"])
            # ➤ utiliser Shapely pour produire le WKT
            shapely_geom = shape(reprojected_geom)
            features.append(
                {
                    "type": "Feature",
                    "geometry": shapely_geom.wkt,
                    "properties": dict(feat["properties"]),
                }
            )
    return {"features": features}
