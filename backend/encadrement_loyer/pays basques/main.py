from shapely.geometry import Point, Polygon
from pyproj import Transformer
import requests

from backend.encadrement_loyer.utils import geocode_address
# Aller sur:
# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/index.html?dummy=1729177715102

# Puis cliquer sur les zone pour obtenir les données en 
#  "crs" : "EPSG:3857"
# le call dans le network a regarder est le suivant: 
# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/interactivity/getFeatureGeometry?dummy=1736545730144&featureId=73&simplificationTolerance=141.11103491115225&sourceOwnerId=f6bd1875-8b10-11ef-b6f8-3d530512f88c&targetSrid=EPSG:3857
# Coordonnées du polygone en EPSG:3857

def legacy():
    polygon_coords = [
        [-175701.8500299732, 5376280.590763259],
        [-175323.10255857382, 5376602.087097176],
        [-175091.03162607746, 5377252.077412805],
        [-174105.76694193858, 5377566.689024307],
        [-173947.18474216404, 5377852.999500588],
        [-174322.8417294372, 5378060.774293069],
        [-173455.16287961273, 5378499.743121959],
        [-173783.725735181, 5379249.375463562],
        [-173727.5918297777, 5379639.491686672],
        [-172851.77752949955, 5379274.810229326],
        [-172190.00416702867, 5379260.618405115],
        [-171672.65123995117, 5380345.304950371],
        [-171427.2517654036, 5380356.581721392],
        [-171231.0279561995, 5379602.176006303],
        [-171410.40321975376, 5379030.612422128],
        [-170907.73649993778, 5378693.39045467],
        [-170541.35389487902, 5377809.828808404],
        [-170809.09476108642, 5377024.45233669],
        [-171197.58085646306, 5376927.444610659],
        [-171498.30156685182, 5376140.354070586],
        [-170983.13747488853, 5375056.4480766],
        [-170481.2465379281, 5375091.613166379],
        [-170209.21497995273, 5372691.957269732],
        [-171077.12182532126, 5372408.729084569],
        [-171514.04260731075, 5371927.10941135],
        [-171427.56782581485, 5372256.516413121],
        [-171739.15147402973, 5372510.751422154],
        [-172147.18189426017, 5374230.815758777],
        [-172541.3160845298, 5374567.16461885],
        [-172938.00160028078, 5374557.44747698],
        [-173073.45760043882, 5375053.492739472],
        [-173571.40394526316, 5374902.132264797],
        [-174065.9529667205, 5375105.0150696505],
        [-173949.7110274388, 5375657.124323864],
        [-174892.850852903, 5375500.815361395],
        [-175701.8500299732, 5376280.590763259],
    ]

    # Ensuite on convertir la long et lat dans cette norme:
    # Adresse à vérifier (latitude et longitude en EPSG:4326)
    address_lat = 50.6364543
    address_lon = 3.0685679

    # Convertir l'adresse de EPSG:4326 à EPSG:3857
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    address_x, address_y = transformer.transform(address_lon, address_lat)

    # Créer un polygone Shapely
    polygon = Polygon(polygon_coords)

    # Vérifier si l'adresse est dans le polygone
    point = Point(address_x, address_y)
    is_inside = polygon.contains(point)
    a=1


# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/applications/getApplicationDescriptor?id=dad90ce2-8b10-11ef-b6f8-3d530512f88c&translationKey=fr&bgAppTimestamp=1734620745284

# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/infoSheets/getData?dummy=1741971473617&centroid=false&id=f6be9f17-8b10-11ef-b6f8-3d530512f88c&idValue=63&srs=EPSG:3857


# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/infoSheets/getData?dummy=1741970913197&centroid=false&id=f6be9f17-8b10-11ef-b6f8-3d530512f88c&idValue=14&srs=EPSG:3857

### QUERY PARAM ###
# le dummy vient de l'url de base:'
# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/index.html?dummy=1729177715102

# https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/wmtsWrapper/getTileMatrixSet?dummy=1741971835482&id=0539cda6-b4ad-11ee-b591-49f6393d77f1
# dummy,  id, idValue
# l'idValue est le seul a changer, donc a peu crawler'

# Adresse à vérifier
address = "15 rue perexune bidart"
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
is_inside, matching_polygon_id