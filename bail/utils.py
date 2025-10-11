import logging

from bail.models import BailSignatureRequest

logger = logging.getLogger(__name__)


def create_signature_requests(bail):
    """
    Crée les demandes de signature pour un bail.
    Utilise la fonction générique pour factoriser le code.
    """
    from signature.services import create_signature_requests_generic

    create_signature_requests_generic(bail, BailSignatureRequest)


def create_bien_from_form_data(validated_data, serializer_class, save=True):
    """
    Crée un objet Bien à partir des données VALIDÉES du serializer.

    Args:
        validated_data: Les données déjà validées par le serializer principal
        save: Si True, sauvegarde l'objet en base.
              Si False, retourne un objet non sauvegardé.
        serializer_class: La classe du serializer utilisé pour extraire les mappings (obligatoire)

    Returns:
        Instance de Bien
    """
    # Utiliser le mapping automatique du serializer
    from location.models import Bien

    bien_fields = serializer_class.extract_model_data(Bien, validated_data)

    # Enlever les valeurs None pour éviter les erreurs
    bien_fields = {k: v for k, v in bien_fields.items() if v is not None}

    bien = Bien(**bien_fields)

    if save:
        bien.save()

    return bien
