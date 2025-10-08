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
    Créer un nouveau document depuis une source existante (mode extend).

    Exemples:
    - Quittance depuis un bail → source_type='location', prefill tout
    - Nouveau bail depuis un bien → source_type='bien', prefill bien+bailleur seulement
    """
    source_type: Literal['location', 'bien', 'bailleur']
    source_id: UUID
    prefill_fields: list[str]
    kind: Literal['extend'] = 'extend'


@dataclass
class RenewFormState:
    """
    Renouvellement d'un document signé (génère nouveau location_id).

    Exemple: Corriger une quittance déjà signée → crée nouvelle quittance.
    """
    previous_location_id: UUID
    kind: Literal['renew'] = 'renew'


# Union type pour pattern matching exhaustif
FormState = Union[CreateFormState, EditFormState, ExtendFormState, RenewFormState]
