"""
Service responsable du filtrage des steps d'un formulaire.

Responsabilité unique : Déterminer quelles steps doivent être affichées
selon les données existantes, les steps verrouillées, et les conditions.
"""

from typing import Any, Dict, List, Set


class FormStepFilter:
    """Filtre les steps d'un formulaire selon différents critères."""

    def filter_steps(
        self,
        all_steps: List[Dict[str, Any]],
        existing_data: Dict[str, Any],
        locked_steps: Set[str],
        serializer_class: Any,
    ) -> List[Dict[str, Any]]:
        """
        Filtre les steps pour ne garder que celles à afficher.

        Args:
            all_steps: Liste complète des steps depuis le serializer
            existing_data: Données existantes de la location
            locked_steps: Set des step_ids verrouillées (signature, etc.)
            serializer_class: Classe du serializer pour enrichir les steps

        Returns:
            Liste des steps filtrées et enrichies avec leurs métadonnées
        """
        filtered_steps = []

        for step in all_steps:
            step_id = step["id"]

            # Skip si step verrouillée
            if step_id in locked_steps:
                continue

            # Copier la step SANS les fields (contiennent des objets Django non sérialisables)
            step_copy = {k: v for k, v in step.items() if k != "fields"}

            # Enrichir avec les métadonnées du serializer
            step_full_config = serializer_class.get_step_config_by_id(step_id)
            if step_full_config:
                # Business rules
                if "business_rules" in step_full_config:
                    step_copy["business_rules"] = step_full_config["business_rules"]

                # Always unlocked flag
                if "always_unlocked" in step_full_config:
                    step_copy["always_unlocked"] = step_full_config["always_unlocked"]

                # Required fields
                if "required_fields" in step_full_config:
                    step_copy["required_fields"] = step_full_config["required_fields"]

                # Mapped fields (pour info seulement)
                fields = step_full_config.get("fields", {})
                if fields:
                    step_copy["mapped_fields"] = list(fields.keys())

            # Ajouter valeur par défaut si définie et pas de données existantes
            if "default" in step and not self._field_has_value(step_id, existing_data):
                self._set_field_value(step_id, step["default"], existing_data)

            filtered_steps.append(step_copy)

        return filtered_steps

    def _field_has_value(self, field_path: str, data: Dict) -> bool:
        """
        Vérifie si un champ a une valeur dans les données.

        IMPORTANT:
        - None ou champ manquant = pas de valeur (step à afficher)
        - [], {}, "" = valeur explicitement vide (step à NE PAS afficher)

        Args:
            field_path: Chemin du champ (ex: "bien.localisation.adresse")
            data: Dictionnaire de données

        Returns:
            True si le champ a une valeur (même vide), False sinon
        """
        parts = field_path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
                # Seul None est considéré comme "pas de valeur"
                # [], {}, "" sont des valeurs explicites (vides mais définies)
                if current is None:
                    return False
            else:
                # Champ manquant = pas de valeur
                return False

        return True

    def _set_field_value(self, field_path: str, value: Any, data: Dict) -> None:
        """
        Définit une valeur dans les données en créant la structure nécessaire.

        Args:
            field_path: Chemin du champ (ex: "bien.equipements.annexes_privatives")
            value: Valeur à définir
            data: Dictionnaire à modifier (modifié en place)
        """
        parts = field_path.split(".")
        current = data

        # Parcourir jusqu'à l'avant-dernier niveau
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Définir la valeur au dernier niveau
        current[parts[-1]] = value

    def get_locked_steps(
        self, location_id: str, country: str, is_new: bool
    ) -> Set[str]:
        """
        Récupère les steps verrouillées pour une location.

        Args:
            location_id: UUID de la location
            country: Code pays (FR, BE)
            is_new: True si c'est une nouvelle location

        Returns:
            Set des step_ids verrouillées
        """
        # Pas de verrouillage pour les nouvelles locations
        if is_new:
            return set()

        import logging

        from .field_locking import FieldLockingService

        logger = logging.getLogger(__name__)

        locked_steps = FieldLockingService.get_locked_steps(location_id, country)

        if locked_steps:
            logger.info(
                f"Found {len(locked_steps)} locked steps for location {location_id}"
            )

        return locked_steps
