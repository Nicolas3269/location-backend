import logging
from typing import Optional, Tuple

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from bail.models import Avenant, AvenantSignatureRequest, Bail, BailSignatureRequest
from location.services.access_utils import user_has_bien_access
from signature.document_status import DocumentStatus
from signature.services import create_signature_requests_generic

logger = logging.getLogger(__name__)


def get_avenant_with_access_check(
    avenant_id: str, user_email: str
) -> Tuple[Optional[Avenant], Optional[str]]:
    """
    Récupère un avenant avec vérification d'accès.

    Args:
        avenant_id: UUID de l'avenant
        user_email: Email de l'utilisateur pour vérifier l'accès

    Returns:
        Tuple (avenant, error_message)
        - Si succès: (avenant, None)
        - Si erreur: (None, message d'erreur)
    """
    try:
        avenant = (
            Avenant.objects.select_related(
                "bail__location__bien",
                "bail__location__mandataire__signataire",
                "bail__location__mandataire__societe",
            )
            .prefetch_related(
                "bail__location__bien__bailleurs__personne",
                "bail__location__bien__bailleurs__societe",
                "bail__location__bien__bailleurs__signataire",
                "bail__location__locataires",  # Locataire hérite de Personne
            )
            .get(id=avenant_id)
        )

        if not user_has_bien_access(avenant.bail.location.bien, user_email):
            return None, "Vous n'avez pas accès à cet avenant"

        return avenant, None

    except Avenant.DoesNotExist:
        return None, "Avenant non trouvé"


def get_draft_avenant(avenant_id: str, user_email: str) -> Avenant:
    """
    Récupère un avenant DRAFT pour le reprendre, avec vérifications d'accès et de statut.

    Args:
        avenant_id: UUID de l'avenant
        user_email: Email de l'utilisateur pour vérifier l'accès

    Returns:
        Instance d'Avenant

    Raises:
        NotFound: Si l'avenant n'existe pas
        PermissionDenied: Si l'utilisateur n'a pas accès
        ValidationError: Si l'avenant n'est pas en brouillon
    """

    try:
        avenant = Avenant.objects.select_related("bail__location__bien").get(
            id=avenant_id
        )

        if not user_has_bien_access(avenant.bail.location.bien, user_email):
            raise PermissionDenied("Vous n'avez pas accès à cet avenant")

        if avenant.status != DocumentStatus.DRAFT:
            raise ValidationError(
                f"Cet avenant n'est pas en brouillon ({avenant.status})"
            )

        return avenant

    except Avenant.DoesNotExist:
        raise NotFound("Avenant non trouvé")


def get_bail_for_avenant(bail_id: str, user_email: str, prefetch: bool = True) -> Bail:
    """
    Récupère un bail pour créer un avenant, avec vérifications d'accès et de statut.

    Args:
        bail_id: UUID du bail
        user_email: Email de l'utilisateur pour vérifier l'accès
        prefetch: Si True, prefetch les relations (bailleurs, locataires)

    Returns:
        Instance de Bail

    Raises:
        NotFound: Si le bail n'existe pas
        PermissionDenied: Si l'utilisateur n'a pas accès
        ValidationError: Si le bail n'est pas verrouillé
    """
    from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

    try:
        queryset = Bail.objects.select_related("location__bien")
        if prefetch:
            queryset = queryset.prefetch_related(
                "location__bien__bailleurs__personne",
                "location__bien__bailleurs__societe",
                "location__bien__bailleurs__signataire",
                "location__locataires",  # Locataire hérite de Personne
            )
        bail = queryset.get(id=bail_id)

        # Vérifier ownership via le bien
        if not user_has_bien_access(bail.location.bien, user_email):
            raise PermissionDenied("Vous n'avez pas accès à ce bail")

        # Vérifier que le bail est verrouillé (signé ou en cours de signature)
        if not bail.is_locked:
            raise ValidationError(
                "Un avenant ne peut être créé que pour un bail signé ou en cours de signature"
            )

        return bail

    except Bail.DoesNotExist:
        raise NotFound("Bail non trouvé")


def create_signature_requests(bail, user=None):
    """
    Crée les demandes de signature pour un bail.
    Utilise la fonction générique pour factoriser le code.

    Args:
        bail: Instance de Bail
        user: User qui a créé le document (sera le premier signataire)
    """
    create_signature_requests_generic(bail, BailSignatureRequest, user=user)


def create_avenant_signature_requests(avenant, user=None):
    """
    Crée les demandes de signature pour un avenant.
    Utilise la fonction générique pour factoriser le code.

    Args:
        avenant: Instance d'Avenant
        user: User qui a créé le document (sera le premier signataire)
    """
    create_signature_requests_generic(avenant, AvenantSignatureRequest, user=user)


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
