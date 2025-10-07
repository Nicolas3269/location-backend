"""
Service responsable de la gestion des conflits et renouvellements de documents.

Responsabilité unique : Déterminer si un document est verrouillé (signature en cours/terminée)
et générer un nouveau location_id si nécessaire pour éviter les conflits.
"""

import uuid
from typing import Any, Dict, Optional

from location.models import Location


class FormConflictResolver:
    """Gère les conflits de documents et les renouvellements."""

    def resolve_location_id(
        self,
        form_type: str,
        location_id: Optional[str],
        type_etat_lieux: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Détermine le location_id à utiliser et si on est en mode création/renouvellement.

        Args:
            form_type: Type de formulaire ('bail', 'etat_lieux', 'quittance')
            location_id: ID de la location existante (peut être None)
            type_etat_lieux: Type d'état des lieux si applicable

        Returns:
            Dict avec:
                - final_location_id: UUID à utiliser
                - is_new: True si nouvelle location
                - has_been_renewed: True si renouvelé suite à conflit
                - has_conflict: True si document verrouillé
        """
        has_conflict = False
        is_new = False
        has_been_renewed = False

        # Pas de location_id fourni = nouvelle création
        if not location_id:
            return {
                "final_location_id": str(uuid.uuid4()),
                "is_new": True,
                "has_been_renewed": False,
                "has_conflict": False,
            }

        # Location_id fourni : vérifier si conflit
        try:
            location = Location.objects.get(id=location_id)
            has_conflict = self._check_document_conflict(
                location, form_type, type_etat_lieux
            )
        except Location.DoesNotExist:
            # Location n'existe pas : créer nouvelle
            return {
                "final_location_id": location_id,  # Réutiliser l'ID fourni
                "is_new": True,
                "has_been_renewed": False,
                "has_conflict": False,
            }

        # Si conflit : générer nouveau location_id (renouvellement)
        if has_conflict:
            return {
                "final_location_id": str(uuid.uuid4()),
                "is_new": True,
                "has_been_renewed": True,  # Nouveau à cause d'un conflit
                "has_conflict": True,
            }

        # Pas de conflit : réutiliser l'existant
        return {
            "final_location_id": location_id,
            "is_new": False,
            "has_been_renewed": False,
            "has_conflict": False,
        }

    def _check_document_conflict(
        self, location: Location, form_type: str, type_etat_lieux: Optional[str] = None
    ) -> bool:
        """
        Vérifie s'il y a un conflit pour le type de document demandé.

        Un conflit existe si le document est signé ou en cours de signature.

        Args:
            location: Instance de Location
            form_type: Type de document ('bail', 'etat_lieux', 'quittance')
            type_etat_lieux: Type d'état des lieux si form_type == 'etat_lieux'

        Returns:
            True si conflit (document verrouillé), False sinon
        """
        from signature.document_status import DocumentStatus

        if form_type == "bail":
            # Un bail existe et est signé ou en cours de signature ?
            from bail.models import Bail

            signing_or_signed_bail = Bail.objects.filter(
                location=location,
                status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED],
            ).first()

            return signing_or_signed_bail is not None

        elif form_type == "etat_lieux":
            if not type_etat_lieux:
                return False  # Pas de type spécifié, pas de conflit

            # Un état des lieux de ce type existe et est signé ou en cours ?
            from etat_lieux.models import EtatLieux

            etat_lieux = EtatLieux.objects.filter(
                location=location, type_etat_lieux=type_etat_lieux
            ).first()

            if etat_lieux:
                # Status SIGNING ou SIGNED = document verrouillé
                return etat_lieux.status in [
                    DocumentStatus.SIGNING,
                    DocumentStatus.SIGNED,
                ]
            return False

        elif form_type == "quittance":
            # Les quittances sont toujours éditables
            return False

        elif form_type == "tenant_documents":
            # Tenant documents n'ont pas de conflit
            return False

        return False
