### PLEINE COMMUNE ###
# https://www.data.gouv.fr/fr/datasets/encadrement-des-loyers-de-plaine-commune/
# https://www.data.gouv.fr/fr/datasets/r/de5c9cb9-6215-4e88-aef7-ea0041984d1d

import xml.etree.ElementTree as ET

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
