"""
Modèles de base pour les documents signables
"""

from abc import ABC, abstractmethod

from django.db import models


class SignableDocumentMixin(models.Model):
    """
    Mixin pour les documents qui peuvent être signés électroniquement
    """

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
