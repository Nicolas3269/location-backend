import requests
import json 
from shapely.geometry import shape, Point

from algo.encadrement_loyer.utils import geocode_address

### REQUETES pour tous ###
# https://www.data.gouv.fr/fr/datasets/?q=encadrement+loyers

### PARIS ###
# https://www.data.gouv.fr/fr/datasets/logement-encadrement-des-loyers/#/resources
# https://www.data.gouv.fr/fr/datasets/r/41a1c199-14ca-4cc7-a827-cc4779fed8c0

### PLEINE COMMUNE ###
# https://www.data.gouv.fr/fr/datasets/encadrement-des-loyers-de-plaine-commune/
# https://www.data.gouv.fr/fr/datasets/r/de5c9cb9-6215-4e88-aef7-ea0041984d1d

### EST ENSEMBLE ###
# https://www.data.gouv.fr/fr/datasets/encadrement-des-loyers-de-est-ensemble/
# https://www.data.gouv.fr/fr/datasets/r/7d70e696-ef9d-429d-8284-79d0ecd59ccd

### LYON ###
# https://www.data.gouv.fr/fr/datasets/encadrement-des-loyers-de-la-metropole-de-lyon-2024-2025/
# https://www.data.gouv.fr/fr/datasets/r/57266456-f9c9-4ee0-9245-26bb4e537cd6


### MONTPELLIER ###
# https://www.data.gouv.fr/fr/datasets/encadrement-des-loyers-de-montpellier/
# https://www.data.gouv.fr/fr/datasets/r/c00fa2a7-f84c-4ca4-8224-3b734242bae7





#### BORDEAUX ###
# https://www.data.gouv.fr/fr/datasets/r/08a1d711-e239-4282-938c-e6edac0090a8


#### Pays basques  ###
# https://www.data.gouv.fr/fr/datasets/r/08a1d711-e239-4282-938c-e6edac0090a8

#### LILLE ###


# URL du GeoJSON (ex: Paris)
GEOJSON_URL = "https://www.data.gouv.fr/fr/datasets/r/7d70e696-ef9d-429d-8284-79d0ecd59ccd"  # Remplace par l'URL du GeoJSON

def get_rent_control_info(lat, lng, geojson_data):
    """Récupère l'encadrement des loyers en fonction des coordonnées"""
    point = Point(lng, lat)  # Attention : Shapely utilise (lon, lat)

    for feature in geojson_data["features"]:
        polygon = shape(feature["geometry"])  # Convertit la géométrie GeoJSON en Shapely
        if polygon.contains(point):
            return feature["properties"]  # Renvoie les infos d'encadrement

    return None  # Aucune correspondance trouvée


def ile_de_france(address):
    lat, lng = geocode_address(address)
    print(f"Coordonnées trouvées : {lat}, {lng}")

    # Récupérer le GeoJSON
    geojson_data = requests.get(GEOJSON_URL).json()

    rent_info = get_rent_control_info(lat, lng, geojson_data)

    if rent_info:
        print("Encadrement des loyers trouvé :")
        print(json.dumps(rent_info, indent=2, ensure_ascii=False))
    else:
        print("Aucune information d'encadrement des loyers pour cette adresse.")

def main():
    # address = input("Entrez une adresse : ")
    address_paris = "49 rue du Sergent-Bauchat, 75012 Paris"
    address_lyon = "20, Rue Terme à Lyon 1er, 69001"
    # address_bordeaux = "11 Rue Saint-James, 33000 Bordeaux"
    address_montpellier = "3 rue Draperie Saint Firmin, 34000 Montpellier"
    address_est_ensemble = "100 Avenue Gaston Roussel, 93230 Romainville"
    address = address_est_ensemble

    
    try:
        ile_de_france(address)
    
    except Exception as e:
        print(f"Erreur : {e}")

if __name__ == "__main__":
    main()

