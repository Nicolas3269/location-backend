from shapely.geometry import Point, Polygon
from pyproj import Transformer
import requests

from backend.encadrement_loyer.utils import geocode_address
# Aller sur:
# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/index.html?dummy=1729177715102

# Puis cliquer sur les zone pour obtenir les données en 
#  "crs" : "EPSG:3857"
# Coordonnées du polygone en EPSG:3857

# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/infoSheets/getData?dummy=1741970913197&centroid=false&id=f6be9f17-8b10-11ef-b6f8-3d530512f88c&idValue=14&srs=EPSG:3857

### QUERY PARAM ###
# le dummy vient de l'url de base:'
# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/index.html?dummy=1729177715102

# dummy,  id, idValue
# l'idValue est le seul a changer, donc a peu crawler'

# Adresse à vérifier
address_zone_1 = "15 rue perexune bidart"
address_zone_3 = "10 rue suzanne garanx 64100 bayonne"
address = address_zone_1
lat, lng = geocode_address(address)

# Transformer les coordonnées de EPSG:4326 à EPSG:3857
transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
address_x, address_y = transformer.transform(lng, lat)
address_point = Point(address_x, address_y)

# Base URL de l'API
base_url = "https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/infoSheets/getData"

# Vérifier si l'adresse est dans un des polygones
is_inside = False
matching_polygon_id = None
zone_encadr_loyers = None

for id_value in range(1, 80):
    params = {
        "dummy": "1741970913197",
        "centroid": "false",
        "id": "f6be9f17-8b10-11ef-b6f8-3d530512f88c",
        "idValue": str(id_value),
        "srs": "EPSG:3857"
    }
    response = requests.get(base_url, params=params)

    if response.status_code == 200:
        data = response.json()
        if "type" in data and data["type"] == "Feature":
            if "geometry" in data and data["geometry"]["type"] == "MultiPolygon":
                polygon_coords = data["geometry"]["coordinates"][0]
                polygon = Polygon(polygon_coords[0])
                if polygon.contains(address_point):
                    is_inside = True
                    matching_polygon_id = id_value
                    zone_encadr_loyers = data['properties']['zone_encadr_loyers']
                    break
        if is_inside:
            break

# Résultat
is_inside, matching_polygon_id, zone_encadr_loyers

zone = ["Zone 1", "Zone 2","Zone 3"]
type_de_bien = ["Maison", "Appartement"]   
nombre_de_pieces = ["1", "2", "3", "4 et plus"] 
epoque_de_construction = ["Epoque 1 (avant 1946)", "Epoque 2 (1946-1970)", "Epoque 3 (1971-1990)", "Epoque 4 (après 1990)"]
type_de_location = ["Locations meublées", "Locations non meublées"]