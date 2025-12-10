"""
Service pour déterminer le rôle d'un utilisateur dans le contexte d'une location.

Un utilisateur peut avoir plusieurs rôles globaux (mandataire, bailleur, locataire),
mais pour UNE location spécifique, il a UN rôle contextuel principal.
"""

from typing import Optional

from django.contrib.auth import get_user_model

from location.models import Bien, Location

from .access_utils import get_user_info_for_location

User = get_user_model()


def get_user_role_for_context(
    user: User,
    location_id: Optional[str] = None,
    bien_id: Optional[str] = None,
    bailleur_id: Optional[str] = None,
) -> Optional[str]:
    """
    Détermine le rôle principal d'un utilisateur pour une location, bien ou bailleur.

    Hiérarchie de détection :
    1. Si location_id fourni → utilise get_user_info_for_location
    2. Si bien_id fourni (sans location_id) → check mandataire/bailleur sur ce bien
    3. Si bailleur_id fourni → vérifier si l'utilisateur est ce bailleur

    Args:
        user: Utilisateur Django
        location_id: UUID de la location (priorité haute)
        bien_id: UUID du bien (si location_id non fourni)
        bailleur_id: UUID du bailleur spécifique (cas from_bailleur)

    Returns:
        'mandataire' | 'bailleur' | 'locataire' | None
    """
    user_email = user.email

    # Si location_id fourni, utiliser get_user_info_for_location
    if location_id:
        try:
            location = Location.objects.select_related(
                "mandataire__signataire",
                "bien",
            ).prefetch_related(
                "bien__bailleurs__personne",
                "bien__bailleurs__signataire",
                "locataires",
            ).get(id=location_id)

            user_info = get_user_info_for_location(location, user_email)

            if user_info.is_mandataire:
                return "mandataire"
            if user_info.is_bailleur:
                return "bailleur"
            if user_info.is_locataire:
                return "locataire"

            # Fallback: extraire bien_id pour check bailleur sans location
            bien_id = str(location.bien.id)

        except Location.DoesNotExist:
            pass

    # Si bien_id fourni (ou extrait de location), vérifier mandataire puis bailleur
    if bien_id:
        try:
            bien = Bien.objects.prefetch_related(
                "bailleurs__personne",
                "bailleurs__signataire",
                "locations__mandataire__signataire",
            ).get(id=bien_id)

            # Vérifier si mandataire d'une location sur ce bien
            for loc in bien.locations.all():
                if loc.mandataire and loc.mandataire.signataire:
                    if loc.mandataire.signataire.email == user_email:
                        return "mandataire"

            # Vérifier bailleur
            for bailleur in bien.bailleurs.all():
                try:
                    if bailleur.email == user_email:
                        return "bailleur"
                except ValueError:
                    continue

        except Bien.DoesNotExist:
            pass

    # Si bailleur_id fourni directement (cas from_bailleur)
    if bailleur_id:
        try:
            from location.models import Bailleur

            bailleur = Bailleur.objects.select_related(
                "personne",
                "signataire",
            ).get(id=bailleur_id)

            try:
                if bailleur.email == user_email:
                    return "bailleur"
            except ValueError:
                pass

        except Bailleur.DoesNotExist:
            pass

    return None
