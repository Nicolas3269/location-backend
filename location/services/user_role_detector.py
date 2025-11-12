"""
Service pour déterminer le rôle d'un utilisateur dans le contexte d'une location.

Un utilisateur peut avoir plusieurs rôles globaux (mandataire, bailleur, locataire),
mais pour UNE location spécifique, il a UN rôle contextuel principal.
"""

from typing import Optional

from django.contrib.auth import get_user_model

from location.models import Bien, Location

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
    1. Si location_id fourni :
       a. Mandataire de cette location
       b. Bailleur du bien de cette location
       c. Locataire de cette location

    2. Si bien_id fourni (sans location_id) :
       a. Mandataire d'une location existante sur ce bien
       b. Bailleur de ce bien

    3. Si bailleur_id fourni directement (cas from_bailleur) :
       a. Vérifier si l'utilisateur est ce bailleur

    4. None (pas de rôle détecté pour ce contexte)

    Args:
        user: Utilisateur Django
        location_id: UUID de la location (priorité haute)
        bien_id: UUID du bien (si location_id non fourni)
        bailleur_id: UUID du bailleur spécifique (cas from_bailleur)

    Returns:
        'mandataire' | 'bailleur' | 'locataire' | None
    """
    user_email = user.email

    # Si location_id fourni, vérifier depuis la location
    if location_id:
        try:
            location = Location.objects.select_related(
                "mandataire__signataire",
                "bien",
            ).prefetch_related(
                "bien__bailleurs__personne",  # Pour bailleur.email property
                "bien__bailleurs__signataire",  # Pour bailleur.email property
                "locataires",
            ).get(id=location_id)

            # 1. Vérifier mandataire
            if location.mandataire and location.mandataire.signataire:
                if location.mandataire.signataire.email == user_email:
                    return "mandataire"

            # 2. Vérifier bailleur (utilise la property email du modèle)
            for bailleur in location.bien.bailleurs.all():
                try:
                    if bailleur.email == user_email:
                        return "bailleur"
                except ValueError:
                    # Bailleur invalide (pas de personne ni signataire), ignorer
                    continue

            # 3. Vérifier locataire
            for locataire in location.locataires.all():
                if locataire.email == user_email:
                    return "locataire"

            # Si on a une location, extraire bien_id pour fallback
            bien_id = str(location.bien.id)

        except Location.DoesNotExist:
            pass

    # Si bien_id fourni (ou extrait de location), vérifier mandataire puis bailleur
    if bien_id:
        try:
            bien = Bien.objects.prefetch_related(
                "bailleurs__personne",  # Pour bailleur.email property
                "bailleurs__signataire",  # Pour bailleur.email property
                "locations__mandataire__signataire",  # Pour mandataire check
            ).get(id=bien_id)

            # 1. Vérifier si mandataire d'une location sur ce bien
            for location in bien.locations.all():
                if location.mandataire and location.mandataire.signataire:
                    if location.mandataire.signataire.email == user_email:
                        return "mandataire"

            # 2. Vérifier bailleur (utilise la property email du modèle)
            for bailleur in bien.bailleurs.all():
                try:
                    if bailleur.email == user_email:
                        return "bailleur"
                except ValueError:
                    # Bailleur invalide (pas de personne ni signataire), ignorer
                    continue

        except Bien.DoesNotExist:
            pass

    # Si bailleur_id fourni directement (cas from_bailleur)
    if bailleur_id:
        try:
            from location.models import Bailleur

            bailleur = Bailleur.objects.select_related(
                "personne",  # Pour bailleur.email property
                "signataire",  # Pour bailleur.email property
            ).get(id=bailleur_id)

            # Utiliser la property email du modèle
            try:
                if bailleur.email == user_email:
                    return "bailleur"
            except ValueError:
                # Bailleur invalide (pas de personne ni signataire)
                pass

        except Bailleur.DoesNotExist:
            pass

    # Aucun rôle détecté pour ce contexte
    return None
