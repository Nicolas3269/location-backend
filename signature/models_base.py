"""
Modèles de base pour les documents signables
"""

import logging
from abc import ABC, abstractmethod

from django.contrib.contenttypes.models import ContentType
from django.db import models

from signature.document_status import DocumentStatus
from signature.models import SignatureMetadata


class SignableDocumentMixin(models.Model):
    """
    Mixin pour les documents qui peuvent être signés électroniquement.
    Fournit :
    - Champ status (DRAFT, SIGNING, SIGNED, CANCELLED)
    - Champs PDF (pdf, latest_pdf)
    - Properties pour vérifier l'état de signature (est_signe, date_signature)
    - Properties pour accéder aux métadonnées forensiques (latest_signature_timestamp)
    - Méthode check_and_update_status() pour synchroniser status avec est_signe
    """

    # Statut du document signable
    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.DRAFT,
        verbose_name="Statut du document",
        help_text="Statut de signature du document",
    )

    pdf = models.FileField(
        upload_to="signed_documents/",
        null=True,
        blank=True,
        verbose_name="Document PDF",
    )

    latest_pdf = models.FileField(
        upload_to="signed_documents/",
        null=True,
        blank=True,
        verbose_name="Dernière version signée",
    )

    class Meta:
        abstract = True

    def get_signature_field_name(self, signing_person):
        """
        Retourne le nom du champ de signature pour une personne donnée
        Utilise la fonction standard d'algo.signature.main
        """
        from algo.signature.main import get_signature_field_name

        return get_signature_field_name(signing_person)

    @property
    def is_locked(self) -> bool:
        """
        Document verrouillé (non modifiable) si en signature ou signé.
        Utilisé pour empêcher les modifications sur les documents engagés.
        """
        return self.status in [DocumentStatus.SIGNING, DocumentStatus.SIGNED]

    @property
    def est_signe(self):
        """
        Le document est-il complètement signé par TOUTES les parties ?
        Vérifie que le nombre de SignatureMetadata (signatures forensiques)
        correspond au nombre de signature_requests attendus.
        """

        logger = logging.getLogger(__name__)

        # Compter le nombre de signatures attendues
        nb_signatures_attendues = self.signature_requests.count()

        if nb_signatures_attendues == 0:
            logger.debug(f"🔍 est_signe: 0 signature_requests pour {self}")
            return False

        # Compter le nombre de signatures forensiques complètes
        content_type = ContentType.objects.get_for_model(self)
        nb_signatures_forensiques = SignatureMetadata.objects.filter(
            document_content_type=content_type, document_object_id=self.id
        ).count()

        result = nb_signatures_forensiques == nb_signatures_attendues

        logger.info(
            f"🔍 est_signe pour {self.__class__.__name__} {self.id}: "
            f"forensiques={nb_signatures_forensiques}, attendues={nb_signatures_attendues}, "
            f"result={result}"
        )

        # Toutes les parties ont signé si nb forensiques = nb attendues
        return result

    @property
    def latest_signature_timestamp(self):
        """
        Retourne le timestamp de la dernière signature forensique.
        Utilise SignatureMetadata.signature_timestamp
        (source de vérité cryptographique NTP-sync).
        Retourne None si aucune signature n'existe.
        """
        from django.contrib.contenttypes.models import ContentType

        from signature.models import SignatureMetadata

        content_type = ContentType.objects.get_for_model(self)
        last_signature = (
            SignatureMetadata.objects.filter(
                document_content_type=content_type, document_object_id=self.id
            )
            .order_by("-signature_timestamp")
            .first()
        )

        return last_signature.signature_timestamp if last_signature else None

    @property
    def date_signature(self):
        """
        Date de finalisation du document (dernière signature).
        Documents immutables → pas de re-signature possible après finalisation.
        Si est_signe=True, alors latest_signature_timestamp = date de finalisation.
        """
        if not self.est_signe:
            return None

        return self.latest_signature_timestamp

    def reset_for_edit(self):
        """
        Réinitialise le document pour permettre une nouvelle édition.
        Utilisé quand on veut modifier un document DRAFT existant.

        Actions:
        - Supprime le PDF initial (pdf)
        - Supprime le PDF signé (latest_pdf) si présent
        - Supprime toutes les signature_requests
        - Remet le status à DRAFT
        """
        import logging

        logger = logging.getLogger(__name__)

        # Supprimer le PDF initial
        if self.pdf:
            try:
                self.pdf.delete(save=False)
            except Exception as e:
                logger.warning(f"Impossible de supprimer le PDF: {e}")

        # Supprimer le PDF signé si présent
        if self.latest_pdf:
            try:
                self.latest_pdf.delete(save=False)
            except Exception as e:
                logger.warning(f"Impossible de supprimer le latest_pdf: {e}")

        # Supprimer les signature requests
        self.signature_requests.all().delete()

        # Remettre en DRAFT
        self.status = DocumentStatus.DRAFT

    def check_and_update_status(self):
        """
        Met à jour automatiquement le statut selon les signatures forensiques.
        Utilise est_signe property (source de vérité SignatureMetadata).

        Lifecycle:
        - DRAFT → SIGNING : Fait manuellement par send_signature_email()
        - SIGNING → SIGNED : Automatique quand est_signe = True

        NOTE: Cette méthode ne devrait généralement PAS être appelée depuis
        mark_as_signed() car process_signature_generic gère déjà correctement
        le cycle de vie du statut. Elle reste disponible pour des cas d'usage
        spécifiques comme la synchronisation manuelle via admin.
        """
        import logging

        logger = logging.getLogger(__name__)
        current_status = self.status

        # Ne pas passer automatiquement de DRAFT à SIGNING
        # Cela sera fait par send_signature_email quand on envoie l'email

        # Passer de SIGNING à SIGNED si toutes les signatures forensiques
        # sont complètes
        if self.status == DocumentStatus.SIGNING.value:
            # Utiliser est_signe (vérifie SignatureMetadata)
            is_complete = self.est_signe
            if is_complete:
                self.status = DocumentStatus.SIGNED.value
                logger.info(
                    f"✅ check_and_update_status: {self.__class__.__name__} {self.id} "
                    f"passe de SIGNING à SIGNED (est_signe=True)"
                )

        if current_status != self.status:
            self.save(update_fields=["status"])

    @abstractmethod
    def get_document_name(self):
        """
        Retourne le nom du type de document (ex: "Bail", "État des lieux")
        """
        pass

    @abstractmethod
    def get_file_prefix(self):
        """
        Retourne le préfixe pour les noms de fichiers (ex: "bail", "etat_lieux")
        """
        pass


class SignableDocumentInterface(ABC):
    """
    Interface abstraite pour les documents signables
    """

    @abstractmethod
    def get_document_name(self):
        pass

    @abstractmethod
    def get_file_prefix(self):
        pass

    @property
    @abstractmethod
    def pdf(self):
        pass

    @property
    @abstractmethod
    def latest_pdf(self):
        pass
