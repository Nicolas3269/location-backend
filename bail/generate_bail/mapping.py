from decimal import ROUND_HALF_UP, Decimal

from bail.models import Bail
from location.models import Bien
from rent_control.choices import PropertyType, RegimeJuridique, SystemType


class BailMapping:
    @staticmethod
    def title_bail(bien: Bien):
        if bien.meuble:
            return "CONTRAT DE LOCATION DE LOGEMENT MEUBLÉ"
        else:
            return "CONTRAT DE LOCATION DE LOGEMENT NU"

    @staticmethod
    def subtitle_bail(bien: Bien):
        text = "meublé" if bien.meuble else "nu"
        return f"Local à usage d’habitation {text} soumis à la loi n° 89-462 du 6 juillet 1989"

    @staticmethod
    def object_contrat(bien: Bien):
        if bien.meuble:
            return "CONTRAT DE LOCATION MEUBLÉE"
        else:
            return "CONTRAT DE LOCATION NON MEUBLÉE"

    @staticmethod
    def article_objet_du_contrat(bien: Bien):
        if bien.meuble:
            return """Le bailleur loue au locataire qui l'accepte, le logement dont la désignation suit. <br>
La présente location sera soumise aux dispositions du titre Ier bis (art. 25-3 à 25-11) de la loi n° 89-462 du 6 juillet 1989 et aux articles 1er, 3, 3-2, 3-3, 4 à l'exception du l), 5, 6, 7, 7-1, 8, 8-1, 18, 20-1, 22-1, 21, 22, 22-1, 22-2, 24 et 24-1, rendus applicables à ce type de contrat de location par l'article 25-3, alinéa 2 de la loi du 6 juillet 1989 précitée."""
        else:
            return """Le bailleur loue au locataire qui l’accepte, le logement dont  la désignation suit. <br>
La présente location est régie par les dispositions du titre Ier (articles 1er à 25-2 de la loi n°89-462 du 6 juillet 1989, relative aux rapports locatifs, dans sa version en vigueur à la date de signature du contrat."""

    @staticmethod
    def article_duree_contrat(bien: Bien):
        if bien.type_bien == PropertyType.APARTMENT:
            line_1 = f"l’appartement situé au {bien.adresse}, étage {bien.etage}, porte {bien.porte}"
        else:
            line_1 = f"la maison située au {bien.adresse}"

        if bien.regime_juridique == RegimeJuridique.MONOPROPRIETE:
            if bien.type_bien == PropertyType.APARTMENT:
                line_2 = "situé dans une monopropriété dans un immeuble collectif"
            else:
                line_2 = "situé dans une monopropriété dans un immeuble individuel"
        else:
            if bien.type_bien == PropertyType.APARTMENT:
                line_2 = "situé dans une copropriété dans un immeuble collectif"
            else:
                line_2 = "situé dans une copropriété dans un immeuble individuel"

        line_3 = f"construit {bien.periode_construction.lower()}" if bien.periode_construction else ""

        if bien.identifiant_fiscal:
            line_4 = (
                f"dont le numéro d’identifiant fiscal est {bien.identifiant_fiscal}"
            )
        else:
            line_4 = "l’identifiant fiscal du logement, requis par l’administration, n’a pas été renseigné au moment de la signature du présent contrat. Il sera communiqué par le bailleur dès que possible et fera, le cas échéant, l’objet d’un avenant au présent contrat, signé entre les parties, sans que cela n’affecte la validité ou les autres stipulations du bail."

        return f"""
        <ul>
        <li>{line_1}</li>
        <li>{line_2}</li>
        <li>{line_3}</li>
        <li>{line_4}</li>
        </ul>
"""

    @staticmethod
    def pieces_info(bien: Bien):
        pieces = bien.pieces_info

        # Mapping des types de pièces avec leurs labels et gestion du pluriel
        pieces_labels = {
            "chambres": ("chambre", "chambres"),
            "sallesDeBain": ("salle de bain", "salles de bain"),
            "cuisines": ("cuisine", "cuisines"),
            "sejours": ("séjour", "séjours"),
            "wc": ("WC", "WC"),
            "bureau": ("bureau", "bureaux"),
        }

        # Construire la liste des pièces
        pieces_list = []

        for piece_type, (singular, plural) in pieces_labels.items():
            count = pieces.get(piece_type, 0)
            if count > 0:
                if count == 1:
                    pieces_list.append(f"{count} {singular}")
                else:
                    pieces_list.append(f"{count} {plural}")

        # Générer le HTML avec une liste à puces
        if pieces_list:
            items_html = "".join([f"<li>{piece}</li>" for piece in pieces_list])
            return f"<ul>{items_html}</ul>"
        else:
            return "<p>Aucune pièce renseignée</p>"

    @staticmethod
    def annexes_privatives_info(bien: Bien):
        """Génère la liste HTML des annexes privatives"""
        annexes_raw = bien.annexes_privatives
        annexes = []
        annexes_labels = {
            "cave": "Cave",
            "balcon": "Balcon",
            "jardin": "Jardin",
            "parking": "Place de parking",
            "garage": "Garage ou box fermé",
            "dependance": "Dépendance ou annexe",
        }
        for annexe in annexes_raw:
            # Vérifier si l'annexe est dans les labels définis
            if annexe in annexes_labels:
                annexes.append(annexes_labels[annexe])
            else:
                # Si l'annexe n'est pas reconnue, on peut choisir de l'ignorer ou de la traiter différemment
                annexes.append(annexe)

        return annexes

    @staticmethod
    def annexes_collectives_info(bien: Bien):
        """Génère la liste HTML des annexes collectives"""
        annexes_raw = bien.annexes_collectives
        annexes = []
        annexes_labels = {
            "ascenseur": "Ascenseur",
            "local_velo": "Local à vélos",
            "local_poubelle": "Local à poubelles",
            "jardin_commun": "Jardin commun",
            "laverie": "Laverie commune",
            "salle_commune": "Salle commune",
        }
        for annexe in annexes_raw:
            # Vérifier si l'annexe est dans les labels définis
            if annexe in annexes_labels:
                annexes.append(annexes_labels[annexe])
            else:
                # Si l'annexe n'est pas reconnue, on peut choisir de l'ignorer ou de la traiter différemment
                annexes.append(annexe)

        return annexes

    @staticmethod
    def information_info(bien: Bien):
        informations_raw = bien.information
        informations = []
        informations_labels = {
            "adsl": "ADSL",
            "fibre": "Fibre optique",
            "cable": "Câble",
            "antenne": "Antenne TV",
        }

        for information in informations_raw:
            # Vérifier si l'annexe est dans les labels définis
            if information in informations_labels:
                informations.append(informations_labels[information])

        return informations

    @staticmethod
    def energy_info(bien: Bien):
        """Génère les informations sur la performance énergétique"""

        labels = {
            "gaz": "gaz",
            "electricite": "électricité",
            "fioul": "fioul",
        }
        # Pour le chauffage
        chauffage_energie = bien.chauffage_energie
        if chauffage_energie in labels:
            chauffage_energie = labels[chauffage_energie]

        # Pour l'eau chaude
        eau_chaude_energie = bien.eau_chaude_energie
        if eau_chaude_energie in labels:
            eau_chaude_energie = labels[eau_chaude_energie]

        # Construcition de la chaîne de caractère chauufage
        if bien.chauffage_type == SystemType.COLLECTIF:
            phrase_chauffage = f"La production de chauffage est collective et se fait via {chauffage_energie}."
        else:
            phrase_chauffage = f"La production de chauffage est individuelle et se fait via {chauffage_energie}."
        # Construcition de la chaîne de caractère eau chaude
        if bien.eau_chaude_type == SystemType.COLLECTIF:
            phrase_eau_chaude = f"La production d’eau chaude sanitaire est collective et se fait via {eau_chaude_energie}."
        else:
            phrase_eau_chaude = f"La production d’eau chaude sanitaire est individuelle et se fait via {eau_chaude_energie}."

        return f"""
        <p>
        {phrase_chauffage}<br>
        {phrase_eau_chaude}
        </p>
        """

    @staticmethod
    def prix_majore(bail: Bail):
        """Génère le prix majoré basé sur l'encadrement des loyers"""
        # Accéder aux données depuis location.rent_terms
        if hasattr(bail.location, "rent_terms"):
            rent_price = bail.location.rent_terms.get_rent_price()
            if rent_price:
                # Prix majoré = prix max de référence par m²
                return Decimal(str(rent_price.max_price)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
        return None

    @staticmethod
    def complement_loyer(bail: Bail):
        """Calcule le complément de loyer selon l'encadrement des loyers"""
        # Accéder aux données depuis location.rent_terms
        if hasattr(bail.location, "rent_terms"):
            rent_price = bail.location.rent_terms.get_rent_price()
            bien = bail.location.bien
            if rent_price and bien.superficie:
                # Calcul : montant_loyer - superficie * prix_max_reference
                loyer_max_autorise = Decimal(str(bien.superficie)) * Decimal(
                    str(rent_price.max_price)
                )
                montant_loyer = Decimal(str(bail.location.rent_terms.montant_loyer))

                complement = montant_loyer - loyer_max_autorise
                if complement > 0:
                    return complement.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Pas de complément si pas d'encadrement ou si le loyer est dans les clous
        return None

    @staticmethod
    def prix_reference(bail: Bail):
        """Récupère le prix de référence basé sur l'encadrement des loyers"""
        # Accéder aux données depuis location.rent_terms
        if hasattr(bail.location, "rent_terms"):
            rent_price = bail.location.rent_terms.get_rent_price()
            if rent_price:
                # Prix de référence par m²
                return Decimal(str(rent_price.reference_price)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
        return None

    @staticmethod
    def is_copropriete(bail: Bail):
        """Vérifie si le bail est dans une copropriété"""
        return bail.location.bien.regime_juridique == RegimeJuridique.COPROPRIETE

    @staticmethod
    def potentiel_permis_de_louer(bail: Bail):
        """Vérifie si le bail peut être soumis à un permis de louer"""
        # Accéder au permis de louer depuis location.rent_terms
        if hasattr(bail.location, "rent_terms"):
            return bail.location.rent_terms.permis_de_louer
        return False
