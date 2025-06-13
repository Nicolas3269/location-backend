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
