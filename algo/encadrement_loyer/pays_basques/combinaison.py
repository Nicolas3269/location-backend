import itertools
import json

import requests

# URL cible
url = "https://geobasque.communaute-paysbasque.fr/adws/app/dad90ce2-8b10-11ef-b6f8-3d530512f88c/services/aas/v1/statistics/f6bf144a-8b10-11ef-b6f8-3d530512f88c/execute"

# Options possibles
zones = ["Zone 1", "Zone 2", "Zone 3"]
types_de_bien = ["Maison", "Appartement"]
nombres_de_pieces = ["1", "2", "3", "4 et plus"]
epoques_de_construction = [
    "Epoque 1 (avant 1946)",
    "Epoque 2 (1946-1970)",
    "Epoque 3 (1971-1990)",
    "Epoque 4 (après 1990)",
]
types_de_location = ["Locations meublées", "Locations non meublées"]

# Identifiants des filtres (extraits de l'exemple donné)
filter_ids = {
    "zone": "f6bfb08f-8b10-11ef-b6f8-3d530512f88c",
    "type_de_bien": "f6bf897d-8b10-11ef-b6f8-3d530512f88c",
    "nombre_de_pieces": "f6bfb08e-8b10-11ef-b6f8-3d530512f88c",
    "epoque_de_construction": "f6bf3b5b-8b10-11ef-b6f8-3d530512f88c",
    "type_de_location": "f6bf626c-8b10-11ef-b6f8-3d530512f88c",
}


def get_prices_pays_basque():
    """Récupérer les prix pour le Pays Basque"""
    # Effectuer la requête pour récupérer les prix
    # Générer toutes les combinaisons
    combinations = list(
        itertools.product(
            zones,
            types_de_bien,
            nombres_de_pieces,
            epoques_de_construction,
            types_de_location,
        )
    )

    # Stockage des résultats
    results_dict = {}

    # Effectuer les requêtes pour chaque combinaison
    for combo in combinations:
        (
            zone,
            type_de_bien,
            nombre_de_pieces,
            epoque_de_construction,
            type_de_location,
        ) = combo

        # Construire les filtres de la requête
        filters = {
            "filterInputs": [
                {
                    "id": filter_ids["zone"],
                    "index": 0,
                    "label": zone,
                    "values": [zone],
                    "fromSuggestion": False,
                },
                {
                    "id": filter_ids["type_de_bien"],
                    "index": 0,
                    "label": type_de_bien,
                    "values": [type_de_bien],
                    "fromSuggestion": False,
                },
                {
                    "id": filter_ids["nombre_de_pieces"],
                    "index": 0,
                    "label": nombre_de_pieces,
                    "values": [nombre_de_pieces],
                    "fromSuggestion": False,
                },
                {
                    "id": filter_ids["epoque_de_construction"],
                    "index": 0,
                    "label": epoque_de_construction,
                    "values": [epoque_de_construction],
                    "fromSuggestion": False,
                },
                {
                    "id": filter_ids["type_de_location"],
                    "index": 0,
                    "label": type_de_location,
                    "values": [type_de_location],
                    "fromSuggestion": False,
                },
            ],
            "featureSelectionFilter": {"features": [], "selectionCrs": "EPSG:3857"},
        }

        # FormData à envoyer
        data = {
            "filters": json.dumps(filters),
            "limit": "1",
            "contextId": "0",
            "appId": "dad90ce2-8b10-11ef-b6f8-3d530512f88c",
            "lang": "fr",
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
    return results_dict


def retrieve_data_from_json_for_pays_basques():
    """Récupérer les données du Pays Basque"""
    path = "algo/encadrement_loyer/pays_basques/results.json"
    with open(path, "r") as file:
        raw_data = json.load(file)

    # Mappings vers les constantes de Django
    property_type_map = {"Appartement": "appartement", "Maison": "maison"}

    room_count_map = {
        "1": "1",
        "2": "2",
        "3": "3",
        "4 et plus": "4",  # Transformé en "4" pour correspondre à FOUR_PLUS
    }

    construction_period_map = {
        "Epoque 1 (avant 1946)": "avant 1946",
        "Epoque 2 (1946-1970)": "1946-1970",
        "Epoque 3 (1971-1990)": "1971-1990",
        "Epoque 4 (après 1990)": "apres 1990",
    }

    # Résultats formatés
    formatted_data = []

    for key, values in raw_data.items():
        # Extraire les composants du tuple stockés sous forme de chaîne
        # Le format est "('Zone X', 'Type', 'Pièces', 'Epoque', 'Location')"
        key = key.strip("()").replace("'", "").split(", ")

        if len(key) != 5 or len(values) != 3:
            print(f"Format inattendu: {key} -> {values}")
            continue

        zone, type_bien, pieces, epoque, location = key

        # Extraction du numéro de zone (ex: "Zone 1" -> "1")
        zone_id = zone.replace("Zone ", "").lower()

        # Conversion des propriétés
        property_type = property_type_map.get(type_bien)
        room_count = room_count_map.get(pieces)
        construction_period = construction_period_map.get(epoque)
        furnished = location == "Locations meublées"  # True si meublé, False sinon

        # Les prix viennent dans l'ordre: référence, min, max
        reference_price, min_price, max_price = values

        # Créer l'entrée formatée
        formatted_data.append(
            {
                "zone_id": zone_id,
                "property_type": property_type,
                "room_count": room_count,
                "construction_period": construction_period,
                "furnished": furnished,
                "reference_price": reference_price,
                "min_price": min_price,
                "max_price": max_price,
            }
        )

    return formatted_data


if __name__ == "__main__":
    retrieve_data_from_json_for_pays_basques()
