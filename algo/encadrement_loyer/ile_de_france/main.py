### PLEINE COMMUNE ###
# https://www.data.gouv.fr/fr/datasets/encadrement-des-loyers-de-plaine-commune/
# https://www.data.gouv.fr/fr/datasets/r/de5c9cb9-6215-4e88-aef7-ea0041984d1d

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import requests


def build_url(region, logement_type, pieces, epoque, meuble, date):
    """
    Construit l'URL du fichier KML selon les paramètres.

    Args:
        logement_type (str): Type de logement (appartement/maison)
        pieces (int): Nombre de pièces
        epoque (str): Période de construction (1946-1970, etc.)
        meuble (str): meublé, non meublé
        region (str): Région concernée
        date (str): Date au format YYYY-MM-DD (utilise la date actuelle si non spécifiée)

    Returns:
        str: URL du fichier KML
    """

    version = "202406_01"
    if region == "paris":
        url = f"http://www.referenceloyer.drihl.ile-de-france.developpement-durable.gouv.fr/{region}/kml/{date}/drihl_medianes_{pieces}_{epoque}_{meuble}.kml?v={version}"
    else:
        url = f"http://www.referenceloyer.drihl.ile-de-france.developpement-durable.gouv.fr/{region}/kml/{date}/drihl_medianes_{logement_type}_{pieces}_{epoque}_{meuble}.kml?v={version}"

    return url


def extract_data_from_kml(url):
    """
    Récupère et analyse le contenu KML depuis une URL.

    Args:
        url (str): URL du fichier KML

    Returns:
        dict: Dictionnaire avec idZone comme clé
    """
    try:
        response = requests.get(url)
        response.raise_for_status()

        content = response.content

        # Détecter le namespace utilisé dans le fichier
        if b'xmlns="http://earth.google.com/kml/2.1"' in content:
            ns = {"kml": "http://earth.google.com/kml/2.1"}
        elif b'xmlns="http://www.opengis.net/kml/2.2"' in content:
            ns = {"kml": "http://www.opengis.net/kml/2.2"}
        else:
            # Fallback: essayer sans namespace spécifique
            ns = {}

        # Analyser le contenu XML
        root = ET.fromstring(content)

        # Extraire toutes les balises Placemark qui contiennent les données
        placemarks = root.findall(".//kml:Placemark", ns)

        # Dictionnaire pour stocker les résultats
        results = {}

        for placemark in placemarks:
            # Extraire les données étendues
            extended_data = placemark.find(".//kml:ExtendedData", ns)

            if extended_data is None:
                continue

            # Créer un dictionnaire pour stocker les données de ce Placemark
            place_data = {}

            # Extraire l'ID de la zone
            id_zone = None

            # Analyser toutes les balises Data
            for data in extended_data.findall(".//kml:Data", ns):
                name = data.get("name")
                value_elem = data.find(".//kml:value", ns)

                if value_elem is not None:
                    value = value_elem.text

                    # Stocker l'ID de la zone pour l'utiliser comme clé
                    if name == "idZone":
                        id_zone = value

                    # Stocker toutes les valeurs dans le dictionnaire
                    place_data[name] = value

            # Ajouter au dictionnaire de résultats si un ID de zone a été trouvé
            if id_zone:
                results[id_zone] = place_data

        return results

    except Exception as e:
        print(f"Erreur lors de l'extraction des données: {e}")
        return {}


def save_to_json(data, filename):
    """Sauvegarde les données dans un fichier JSON"""
    output_dir = Path(
        "/home/havardn/location/backend/algo/encadrement_loyer/ile_de_france/data"
    )
    output_dir.mkdir(exist_ok=True)

    with open(output_dir / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    # Paramètres à tester
    regions = ["paris", "est-ensemble", "plaine-commune"]
    logements = ["appartement", "maison"]  # Attention paris y a rien
    pieces_values = [1, 2, 3, 4]
    epoques = ["inf1946", "1946-1970", "1971-1990", "sup1990"]
    meubles = ["meuble", "non-meuble"]
    paris_start_date = [
        "2020-07-01",
        "2021-07-01",
        "2022-07-01",
        "2023-07-01",
        "2024-07-01",
    ]

    est_ensemble_start_date = [
        "2021-12-01",
        "2022-06-01",
        "2023-06-01",
        "2024-06-01",
    ]
    plaine_commune_start_date = [
        "2021-06-01",
        "2022-06-01",
        "2023-06-01",
        "2024-06-01",
    ]

    all_data = {}

    # Exemple d'extraction pour un seul cas
    url = build_url("paris", "appartement", 2, "1946-1970", "meuble", "2024-07-01")
    print(f"Extraction des données depuis: {url}")

    data = extract_data_from_kml(url)
    print(f"Données extraites pour {len(data)} zones.")

    # Afficher un exemple de données
    if data:
        sample_key = next(iter(data))
        print(f"\nExemple de données pour la zone {sample_key}:")
        print(json.dumps(data[sample_key], indent=2))

    # Sauvegarder les données
    save_to_json(data, "est_ensemble_appartement_2_1946-1970_meuble.json")

    # Commenter cette partie et décommenter pour extraire toutes les combinaisons
    """
    for logement in logements:
        for pieces in pieces_values:
            for epoque in epoques:
                for meuble in meubles:
                    try:
                        url = build_url(logement, pieces, epoque, meuble)
                        print(f"Extraction: {logement}, {pieces} pièces, {epoque}, {'meublé' if meuble else 'non meublé'}")
                        
                        data = extract_data_from_kml(url)
                        if data:
                            filename = f"est_ensemble_{logement}_{pieces}_{epoque}_{'meuble' if meuble else 'non_meuble'}.json"
                            save_to_json(data, filename)
                            
                            # Ajouter au dictionnaire global avec une clé composée
                            key = f"{logement}_{pieces}_{epoque}_{'meuble' if meuble else 'non_meuble'}"
                            all_data[key] = data
                            
                            print(f"  Données extraites pour {len(data)} zones.")
                        else:
                            print("  Aucune donnée trouvée.")
                    except Exception as e:
                        print(f"  Erreur: {e}")
    
    # Sauvegarder toutes les données dans un seul fichier
    save_to_json(all_data, "est_ensemble_all_data.json")
    """


if __name__ == "__main__":
    main()
