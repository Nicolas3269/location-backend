"""
Types discriminants pour les états de formulaires adaptatifs.

Architecture: Utilise des dataclasses avec pattern matching exhaustif
pour éliminer les états invalides possibles.
"""

from dataclasses import dataclass
from typing import Literal, Union
from uuid import UUID


@dataclass
class CreateFormState:
    """
    Nouveau formulaire vide (mode standalone).

    Exemple: Créer un nouveau bail from scratch.
    """
    kind: Literal['create'] = 'create'


@dataclass
class EditFormState:
    """
    Éditer une location existante en statut DRAFT.

    Exemple: Reprendre un bail en brouillon pour le compléter.
    """
    location_id: UUID
    kind: Literal['edit'] = 'edit'


@dataclass
class ExtendFormState:
    """
    Créer document depuis location existante avec lock potentiel.

    Utilisé pour "Location Actuelle" ou "Location Ancienne" dans l'espace bailleur.

    Comportement:
    - Copie TOUTES les données de la source location
    - Vérifie si la source a des documents SIGNED/SIGNING
    - SI oui → Steps spécifiées dans lock_fields sont CACHÉES (locked)
    - SI non → Aucun lock (steps visibles et modifiables)

    Exemples:
    - Quittance pour locataire actuel (bail signé) → Lock bien/bailleur/locataires
    - Nouveau bail pour locataire actuel (pas de bail signé) → Pas de lock
    - EDL depuis bail signé → Lock bien/bailleur/locataires
    """
    source_type: Literal['location']  # Seulement location (a des docs avec statut)
    source_id: UUID
    lock_fields: list[str]  # Champs à lock SI source a docs SIGNED/SIGNING
    kind: Literal['extend'] = 'extend'


@dataclass
class PrefillFormState:
    """
    Créer document avec suggestions (pas de lock, steps toujours visibles).

    Utilisé pour "Nouvelle Location" dans l'espace bailleur.

    Comportement:
    - Copie les données de la source (bien, bailleur, ou location)
    - JAMAIS de lock, même si source=location avec docs signés
    - Toutes les steps sont VISIBLES et MODIFIABLES

    Cas d'usage:
    - Nouvelle location depuis bien → Prefill adresse/superficie modifiables
    - Nouvelle location depuis bailleur → Prefill infos bailleur modifiables
    - Nouvelle location depuis ancienne location → Suggestions modifiables (bien peut évoluer)

    Exemples:
    - Nouveau bail depuis bien → Prefill bien, user peut modifier pièces
    - Nouveau bail depuis bailleur → Prefill bailleur
    - Quittance "nouvelle location" avec prefill bailleur connu
    """
    source_type: Literal['bien', 'bailleur', 'location']
    source_id: UUID
    kind: Literal['prefill'] = 'prefill'


@dataclass
class RenewFormState:
    """
    Renouvellement d'un document signé (génère nouveau location_id).

    Exemple: Corriger une quittance déjà signée → crée nouvelle quittance.
    """
    previous_location_id: UUID
    kind: Literal['renew'] = 'renew'


# Union type pour pattern matching exhaustif
FormState = Union[CreateFormState, EditFormState, ExtendFormState, PrefillFormState, RenewFormState]
