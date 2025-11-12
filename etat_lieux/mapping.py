"""
Mapping pour la génération des données d'état des lieux dans les PDFs
"""

from etat_lieux.models import EtatLieux
from location.utils.honoraires import get_honoraires_mandataire_for_location


class EtatDesLieuxMapping:
    @staticmethod
    def get_honoraires_mandataire_data(etat_lieux: EtatLieux):
        """
        Retourne les honoraires EDL du mandataire en lisant depuis HonoraireMandataire.
        Retourne un dict avec les données formatées pour le template PDF.

        Note: Contrairement au bail qui affiche bail + EDL, l'état des lieux n'affiche
        QUE les honoraires EDL (pas les honoraires de bail).

        Optimisation: Ne calcule les honoraires que si mandataire_doit_signer=True.
        """
        # Récupérer seulement les honoraires EDL (pas le bail)
        return get_honoraires_mandataire_for_location(
            etat_lieux.location,
            include_bail=False,
            include_edl=True,
            check_doit_signer=True,
            document=etat_lieux,
        )
