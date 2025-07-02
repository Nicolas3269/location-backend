import json

import requests

# https://www.insee.fr/fr/recherche/recherche-geographique?debut=0
CODE_COMMUNE = {
    "Bresson": "38057",
    "Claix": "38111",
    "Domène": "38150",
    "Echirolles": "38151",
    "Eybens": "38158",
    "Fontaine": "38169",
    "Fontanil-Cornillon": "38170",
    "Gières": "38179",
    "Grenoble": "38185",
    "La Tronche": "38516",
    "Le Pont-de-Claix": "38317",
    "Meylan": "38229",
    "Murianette": "38271",
    "Poisat": "38309",
    "Saint-Egrève": "38382",
    "Saint-Martin-d'Hères": "38421",
    "Sassenage": "38474",
    "Seyssinet-Pariset": "38485",
    "Seyssins": "38486",
    "Varces-Allières-et-Risset": "38524",
    "Venon": "38533",
    # "Quaix-en-Chartreuse": "38420",: n'y ait pas malgré la carte
}


MAPPING_ZONE_CODE = {
    "1.01": "Zone 1",
    "1.02": "Zone 2",
    "1.03": "Zone 3",
    "1.04": "Zone A",
    "1.05": "Zone B",
    "1.06": "Zone C",
}

WHITELIST_ZONES = [
    "Zone 1",
    "Zone 2",
    "Zone A",
]

ACCEPTED_ZONE = "ACCEPTED"


def get_grenoble_zone_geometries():
    """
    Récupère les données de zonage d'encadrement des loyers pour Grenoble
    depuis l'observatoire des loyers.
    """
    url = "https://www.observatoires-des-loyers.org/_api/geojson?agglomeration=L3800&annee=2022&page_uid=6"

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
        assert len(zone_commune_concerned) == 21

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
