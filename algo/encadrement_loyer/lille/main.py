import json

# Pour les references des coordonnées géométriques, voir le fichier data_year.json
# Il faut choisir l'année pour laquelle on veut les données
# https://ssilab-ddtm-encadrement-loyers-33.webself.net/baux-conclus-ou-renouveles-entre-le-142024-et-le-3132025#Meubl%c3%a9+1+1+1+1+1
# Ce qui amène a cette url:
# https://ssilab-ddtm-encadrement-loyers-33.webself.net/data-2024.json
# https://cdonline.articque.com/share/display/ddtm59-loyers2024
# Charger les données des zones (remplacez 'data.json' par le chemin vers votre fichier JSON)
from shapely.geometry import Point, Polygon

extract_dir = "algo/encadrement_loyer/lille"

year = 2024


def find_zone_data(zone_id, dataset):
    for item in dataset:
        if item[0] == zone_id:
            return item
    return None


def get_lille_zone_geometries(year):
    """
    Parse le fichier JSON de Lille (Articque) pour extraire les géométries
    au format exploitable dans RentControlArea (zone_id, zone_name, geometry...).
    Ne s'intéresse pas encore aux prix.
    """
    with open(f"{extract_dir}/data_{year}.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    ressources = data["displayingInfos"]["Resources"]
    geom_list = ressources["Maps"][0]["GeomList"]
    features = []
    for geom in geom_list:
        id_quartier = geom["id"]
        [_, zone_id] = find_zone_data(id_quartier, ressources["Datas"][0]["Values"])
        features.append(
            {
                "type": "Feature",
                "geometry": geom["geom"],
                "properties": {
                    "zone_id": zone_id,
                    "id_quartier": id_quartier,
                    "zone_name": geom["name"],
                },
            }
        )
    return {"features": features}


# Fonction pour trouver le polygone contenant un point
def find_polygon(lat, lon, ressources):
    geom_list = ressources["Maps"][0]["GeomList"]
    # Créer un point à partir des coordonnées
    point = Point(lon, lat)

    # Parcourir chaque polygone dans la liste
    for geom in geom_list:
        # Extraire les coordonnées du polygone
        coordinates = geom["geom"].replace("POLYGON((", "").replace("))", "").split(",")
        polygon_points = [tuple(map(float, coord.split())) for coord in coordinates]

        # Créer un objet Polygon
        polygon = Polygon(polygon_points)

        # Vérifier si le point est dans le polygone
        if polygon.contains(point):
            return {"zone_id": geom["id"], "zone_name": geom["name"]}

    return None


def get_zone_data(latitude, longitude, year):
    with open(f"{extract_dir}/data_{year}.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # Extraire la liste des polygones depuis le JSON
    ressources = data["displayingInfos"]["Resources"]

    result = find_polygon(latitude, longitude, ressources)

    # Afficher le résultat
    if result:
        zone_data = find_zone_data(result["zone_id"], ressources["Datas"][0]["Values"])
        if zone_data:
            print(
                f"Données pour la zone {result['zone_name']} (ID : {result['zone_id']}):"
            )
            print(f"Secteur: {zone_data[1]} pour l'année {year}")
        else:
            print(f"Aucune donnée trouvée pour la zone ID : {result['zone_id']}")
    else:
        print("Aucune zone correspondante trouvée.")

    return result, zone_data


if __name__ == "__main__":
    # Exemple d'utilisation avec les coordonnées d'une adresse
    latitude = 50.6364543  # Latitude de l'adresse
    longitude = 3.0685679  # Longitude de l'adresse
    year = 2024

    for year in range(2020, 2025):
        print(f"Année {year}")
        get_zone_data(latitude, longitude, year)
        print("")
