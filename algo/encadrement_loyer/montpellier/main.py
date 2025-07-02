# voir sur https://www.observatoires-des-loyers.org/connaitre-les-loyers/carte-des-niveaux-de-loyers/agglomeration-de-montpellier/montpellier-34172
import json

import requests

CODE_COMMUNE = {
    "agglo": "34172",
}

MAPPING_ZONE_CODE = {
    "1.01": "1",
    "1.02": "2",
    "1.03": "3",
    "1.04": "4",
    "1.05": "5",
}

WHITELIST_ZONES = [
    "1",
    "2",
    "3",
    "4",
    "5",
]

ACCEPTED_ZONE = "ACCEPTED"


def get_montpellier_zone_geometries():
    """
    Récupère les données de zonage d'encadrement des loyers pour Grenoble
    depuis l'observatoire des loyers.
    """
    url = "https://www.observatoires-des-loyers.org/_api/geojson?agglomeration=L3400&annee=2024&page_uid=6"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        zone_data = data.get("zone_cal", [])
        zone_commune = data.get("zone_comm", [])

        zone_commune_concerned = [
            zone
            for zone in zone_commune
            if zone.get("commune") in CODE_COMMUNE.values()
        ]

        assert len(zone_commune_concerned) == 1

        # Créer le masque à partir de l'union des géométries des communes concernées
        all_features = []
        for zone in zone_commune_concerned:
            geojson = zone.get("geojson", {})
            if geojson.get("type") == "FeatureCollection":
                features = geojson.get("features", [])
                for feature in features:
                    if feature.get("type") == "Feature":
                        geometry = feature.get("geometry", {})
                        valid_types = ("Polygon", "MultiPolygon")
                        if geometry and geometry.get("type") in valid_types:
                            properties = feature.get("properties", {})

                            properties["id_zone"] = ACCEPTED_ZONE
                            feature["properties"] = properties
                            all_features.append(feature)

        for zone in zone_data:
            geojson = zone.get("geojson", {})
            if geojson.get("type") == "FeatureCollection":
                features = geojson.get("features", [])
                for feature in features:
                    if feature.get("type") == "Feature":
                        properties = feature.get("properties", {})
                        code = properties.get("code")
                        id_zone = MAPPING_ZONE_CODE.get(code)
                        if id_zone not in WHITELIST_ZONES:
                            continue
                        properties["id_zone"] = id_zone
                        feature["properties"] = properties
                        all_features.append(feature)

        return {"type": "FeatureCollection", "features": all_features}

    except requests.RequestException as e:
        raise Exception(f"Erreur lors de la récupération des données Grenoble: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"Erreur lors du décodage JSON des données Grenoble: {e}")
    except Exception as e:
        raise Exception(f"Erreur lors du traitement des données Grenoble: {e}")
