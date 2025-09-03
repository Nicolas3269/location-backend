"""
Service de gestion du verrouillage des steps selon l'état des documents.
"""

import logging
from typing import Optional, Set

from bail.models import Bail
from location.models import Location
from signature.document_status import DocumentStatus

logger = logging.getLogger(__name__)


class FieldLockingService:
    """
    Gère le verrouillage dynamique des steps selon l'état des documents.

    Règles:
    - Si un document est en signing ou signed, toutes ses steps sont verrouillées
    - Les steps verrouillées ne peuvent pas être modifiées
    - Les serializers définissent les steps (source unique de vérité)
    """

    @classmethod
    def _get_serializer_class(cls, form_type: str, country: str):
        """Helper pour obtenir le bon serializer selon le pays et le type de formulaire"""
        if country == "FR":
            from location.serializers.france import (
                FranceBailSerializer,
                FranceEtatLieuxSerializer,
                FranceQuittanceSerializer,
            )

            serializers = {
                "bail": FranceBailSerializer,
                "etat_lieux": FranceEtatLieuxSerializer,
                "quittance": FranceQuittanceSerializer,
            }
        elif country == "BE":
            from location.serializers.belgium import (
                BelgiumBailSerializer,
                BelgiumEtatLieuxSerializer,
                BelgiumQuittanceSerializer,
            )

            serializers = {
                "bail": BelgiumBailSerializer,
                "etat_lieux": BelgiumEtatLieuxSerializer,
                "quittance": BelgiumQuittanceSerializer,
            }
        else:
            # Défaut sur FR
            from location.serializers.france import (
                FranceBailSerializer,
                FranceEtatLieuxSerializer,
                FranceQuittanceSerializer,
            )

            serializers = {
                "bail": FranceBailSerializer,
                "etat_lieux": FranceEtatLieuxSerializer,
                "quittance": FranceQuittanceSerializer,
            }

        return serializers.get(form_type)

    @classmethod
    def get_locked_steps(
        cls, location_id: Optional[str], country: str = "FR"
    ) -> Set[str]:
        """
        Retourne l'ensemble des IDs de steps verrouillées pour une location.

        Args:
            location_id: L'ID de la location
            country: Code pays pour sélectionner les bons serializers (FR, BE, etc.)

        Returns:
            Set des IDs de steps verrouillées (ex: {'bien.localisation.adresse', 'bailleur.personne'})
        """
        if not location_id:
            return set()

        try:
            location = (
                Location.objects.select_related("bail")
                .prefetch_related("etats_lieux", "quittances")
                .get(id=location_id)
            )
        except Location.DoesNotExist:
            logger.warning(f"Location {location_id} not found for field locking")
            return set()

        locked_steps = set()
        steps_to_check = []  # Collecter toutes les steps à vérifier

        # Vérifier le bail
        if hasattr(location, "bail") and location.bail:
            bail: Bail = location.bail
            if bail.status in [DocumentStatus.SIGNING, DocumentStatus.SIGNED]:
                bail_serializer = cls._get_serializer_class("bail", country)
                if bail_serializer:
                    bail_steps = bail_serializer.get_step_config()
                    steps_to_check.extend(bail_steps)
                    logger.info(
                        f"Bail {bail.id} is {bail.status}, adding {len(bail_steps)} steps to check"
                    )

        # Vérifier l'état des lieux d'entrée
        etat_entree = location.etats_lieux.filter(type_etat_lieux="entree").first()
        if etat_entree and etat_entree.status in [
            DocumentStatus.SIGNING,
            DocumentStatus.SIGNED,
        ]:
            etat_serializer = cls._get_serializer_class("etat_lieux", country)
            if etat_serializer:
                etat_steps = etat_serializer.get_step_config()
                steps_to_check.extend(etat_steps)
                logger.info(
                    f"État des lieux entrée {etat_entree.id} is {etat_entree.status}, "
                    f"adding {len(etat_steps)} steps to check"
                )

        # Vérifier l'état des lieux de sortie
        etat_sortie = location.etats_lieux.filter(type_etat_lieux="sortie").first()
        if etat_sortie and etat_sortie.status in [
            DocumentStatus.SIGNING,
            DocumentStatus.SIGNED,
        ]:
            etat_serializer = cls._get_serializer_class("etat_lieux", country)
            if etat_serializer:
                etat_steps = etat_serializer.get_step_config()
                steps_to_check.extend(etat_steps)
                logger.info(
                    f"État des lieux sortie {etat_sortie.id} is {etat_sortie.status}, "
                    f"adding {len(etat_steps)} steps to check"
                )

        # Vérifier les quittances
        quittance_signing = location.quittances.filter(
            status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED]
        ).first()
        if quittance_signing:
            serializer_class = cls._get_serializer_class("quittance", country)
            if serializer_class:
                quittance_steps = serializer_class.get_step_config()
                steps_to_check.extend(quittance_steps)
                logger.info(
                    f"Quittance is {quittance_signing.status}, "
                    f"adding {len(quittance_steps)} steps to check"
                )

        # Appliquer la logique always_unlocked une seule fois sur toutes les steps
        for step in steps_to_check:
            # Ne verrouiller que les steps qui ne sont pas marquées always_unlocked
            if not step.get("always_unlocked", False):
                locked_steps.add(step["id"])

        if locked_steps:
            logger.info(
                f"Total locked steps for location {location_id}: {len(locked_steps)}"
            )
            logger.debug(f"Locked steps: {locked_steps}")

        return locked_steps

    @classmethod
    def is_step_locked(
        cls, location_id: Optional[str], step_id: str, country: str = "FR"
    ) -> bool:
        """
        Vérifie si une step spécifique est verrouillée.

        Args:
            location_id: L'ID de la location
            step_id: L'ID de la step à vérifier
            country: Code pays pour sélectionner les bons serializers

        Returns:
            True si la step est verrouillée, False sinon
        """
        locked_steps = cls.get_locked_steps(location_id, country)
        return step_id in locked_steps

    @classmethod
    def filter_unlocked_steps(
        cls, steps: list, location_id: Optional[str], country: str = "FR"
    ) -> list:
        """
        Filtre une liste de steps pour ne garder que celles qui ne sont pas verrouillées.

        Args:
            steps: Liste des steps à filtrer
            location_id: L'ID de la location
            country: Code pays pour sélectionner les bons serializers

        Returns:
            Liste des steps non verrouillées
        """
        if not location_id:
            # Pas de verrouillage pour une nouvelle location
            return steps

        locked_steps = cls.get_locked_steps(location_id, country)

        # Filtrer les steps verrouillées
        unlocked_steps = [step for step in steps if step.get("id") not in locked_steps]

        logger.info(
            f"Filtered {len(steps) - len(unlocked_steps)} locked steps, "
            f"{len(unlocked_steps)} remaining"
        )

        return unlocked_steps
