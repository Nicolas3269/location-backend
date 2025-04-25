import requests


def get_pays_basque_zone_geometries():
    # Création du point de l’adresse (en 3857)

    base_url = "https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/infoSheets/getData"

    features = []
    for id_value in range(1, 80):
        params = {
            "dummy": "1741970913197",
            "centroid": "false",
            "id": "f6be9f17-8b10-11ef-b6f8-3d530512f88c",
            "idValue": str(id_value),
            "srs": "EPSG:4326",
        }
        response = requests.get(base_url, params=params)

        if response.status_code == 200:
            data = response.json()
            if data.get("type") == "Feature":
                features.append(data)

    return {"features": features}


# Aller sur:
# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/index.html?dummy=1729177715102

# Puis cliquer sur les zone pour obtenir les données en
#  "crs" : "EPSG:3857"
# Coordonnées du polygone en EPSG:3857

# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/infoSheets/getData?dummy=1741970913197&centroid=false&id=f6be9f17-8b10-11ef-b6f8-3d530512f88c&idValue=14&srs=EPSG:3857

# ## QUERY PARAM ###
# le dummy vient de l'url de base:'
# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/index.html?dummy=1729177715102

# dummy,  id, idValue
# l'idValue est le seul a changer, donc a peu crawler'
