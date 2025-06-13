from bail.models import Bien


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
