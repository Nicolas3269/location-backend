import itertools
import requests
import json

# URL cible
url = "https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/statistics/f6bf144a-8b10-11ef-b6f8-3d530512f88c/execute"

# Options possibles
zones = ["Zone 1", "Zone 2", "Zone 3"]
types_de_bien = ["Maison", "Appartement"]
nombres_de_pieces = ["1", "2", "3", "4 et plus"]
epoques_de_construction = ["Epoque 1 (avant 1946)", "Epoque 2 (1946-1970)", "Epoque 3 (1971-1990)", "Epoque 4 (après 1990)"]
types_de_location = ["Locations meublées", "Locations non meublées"]

# Identifiants des filtres (extraits de l'exemple donné)
filter_ids = {
    "zone": "f6bfb08f-8b10-11ef-b6f8-3d530512f88c",
    "type_de_bien": "f6bf897d-8b10-11ef-b6f8-3d530512f88c",
    "nombre_de_pieces": "f6bfb08e-8b10-11ef-b6f8-3d530512f88c",
    "epoque_de_construction": "f6bf3b5b-8b10-11ef-b6f8-3d530512f88c",
    "type_de_location": "f6bf626c-8b10-11ef-b6f8-3d530512f88c"
}

# Générer toutes les combinaisons
combinations = list(itertools.product(zones, types_de_bien, nombres_de_pieces, epoques_de_construction, types_de_location))

# Stockage des résultats
results_dict = {}

# Effectuer les requêtes pour chaque combinaison
for combo in combinations:
    zone, type_de_bien, nombre_de_pieces, epoque_de_construction, type_de_location = combo

    # Construire les filtres de la requête
    filters = {
        "filterInputs": [
            {"id": filter_ids["zone"], "index": 0, "label": zone, "values": [zone], "fromSuggestion": False},
            {"id": filter_ids["type_de_bien"], "index": 0, "label": type_de_bien, "values": [type_de_bien], "fromSuggestion": False},
            {"id": filter_ids["nombre_de_pieces"], "index": 0, "label": nombre_de_pieces, "values": [nombre_de_pieces], "fromSuggestion": False},
            {"id": filter_ids["epoque_de_construction"], "index": 0, "label": epoque_de_construction, "values": [epoque_de_construction], "fromSuggestion": False},
            {"id": filter_ids["type_de_location"], "index": 0, "label": type_de_location, "values": [type_de_location], "fromSuggestion": False}
        ],
        "featureSelectionFilter": {"features": [], "selectionCrs": "EPSG:3857"}
    }

    # FormData à envoyer
    data = {
        "filters": json.dumps(filters),
        "limit": "1",
        "contextId": "0",
        "appId": "dad90ce2-8b10-11ef-b6f8-3d530512f88c",
        "lang": "fr"
    }

    # Exécution de la requête
    response = requests.post(url, data=data)
    
    if response.status_code == 200:
        try:
            json_response = response.json()
            # Extraire les valeurs des cellules si disponibles
            cells = json_response.get("samples", [{}])[0].get("cells", [])
            values = [cell.get("value", None) for cell in cells]

            # Stocker les valeurs dans le dictionnaire
            results_dict[combo] = values
        except json.JSONDecodeError:
            print(f"Erreur de décodage JSON pour {combo}")
    else:
        print(f"Requête échouée ({response.status_code}) pour {combo}")
