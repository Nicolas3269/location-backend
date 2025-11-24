"""
Utilitaires pour la serialization des données de Bailleur et Mandataire.
"""
from typing import Any, Dict, Optional

from django.db.models import QuerySet

from location.models import Bailleur, Mandataire
from location.serializers.read import BailleurReadSerializer, MandataireReadSerializer


def serialize_bailleur(bailleur: Bailleur) -> Dict[str, Any]:
    """
    Sérialise les données d'un Bailleur pour les formulaires.

    Utilise BailleurReadSerializer (ModelSerializer) pour garantir
    la cohérence avec le modèle.
    """
    if not bailleur:
        return {}

    serializer = BailleurReadSerializer(bailleur)
    return serializer.data


def serialize_mandataire(mandataire: Mandataire) -> Dict[str, Any]:
    """
    Sérialise les données d'un Mandataire pour les formulaires.

    Utilise MandataireReadSerializer (ModelSerializer) pour garantir
    la cohérence avec le modèle.
    """
    if not mandataire:
        return {}

    serializer = MandataireReadSerializer(mandataire)
    return serializer.data


def get_primary_bailleur_for_user(
    bailleurs_queryset: QuerySet, user: Optional[Any] = None
) -> Optional[Bailleur]:
    """
    Retourne le bailleur correspondant au user connecté, sinon le premier créé.

    Cette fonction garantit un ordre déterministe et met en priorité le bailleur
    du user connecté si celui-ci est l'un des bailleurs du bien.

    Args:
        bailleurs_queryset: QuerySet de bailleurs (ManyToMany depuis Bien)
        user: Utilisateur connecté (optionnel). Si fourni et qu'il correspond
              à l'un des bailleurs, son bailleur sera retourné en priorité.

    Returns:
        Le bailleur correspondant au user (si trouvé),
        sinon le premier bailleur créé (ordre déterministe par created_at),
        sinon None si aucun bailleur.

    Exemples:
        >>> # Cas 1: User non connecté
        >>> get_primary_bailleur_for_user(bien.bailleurs, None)
        # Retourne le premier bailleur créé

        >>> # Cas 2: User connecté = co-bailleur
        >>> get_primary_bailleur_for_user(bien.bailleurs, co_bailleur_user)
        # Retourne le bailleur du co-bailleur (priorité)

        >>> # Cas 3: User connecté = bailleur principal
        >>> get_primary_bailleur_for_user(bien.bailleurs, bailleur_principal_user)
        # Retourne le bailleur principal (même résultat qu'avec None)
    """
    if not bailleurs_queryset.exists():
        return None

    # Ordre déterministe: premier créé = principal par défaut
    bailleurs_ordered = bailleurs_queryset.order_by("created_at")

    # Si user fourni, chercher son bailleur en priorité
    if user and hasattr(user, "email"):
        user_email = user.email
        for bailleur in bailleurs_ordered:
            try:
                if bailleur.email == user_email:
                    return bailleur
            except (ValueError, AttributeError):
                # Bailleur invalide (pas de personne ni signataire) ou pas d'email
                continue

    # Sinon, retourner le premier créé (ordre déterministe)
    return bailleurs_ordered.first()
