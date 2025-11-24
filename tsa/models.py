"""
Modèles pour TSA (Time Stamping Authority).

Gère la génération atomique des numéros de série pour les timestamps RFC 3161.
"""

from django.db import models


class TsaSerial(models.Model):
    """
    Numéro de série pour les timestamps TSA.

    Utilise l'auto-increment du PK PostgreSQL pour générer des serials uniques.
    Chaque timestamp crée une nouvelle ligne, le PK sert de serial.

    Avantages :
    - Atomicité garantie par PostgreSQL (pas besoin de select_for_update)
    - Historique complet des timestamps générés
    - Scaling horizontal natif (Railway multi-instances)

    Conforme RFC 3161 : serial doit être un INTEGER unique.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Date de génération du timestamp"
    )

    class Meta:
        verbose_name = "TSA Serial"
        verbose_name_plural = "TSA Serials"
        ordering = ['-id']  # Plus récent en premier

    @classmethod
    def get_next_serial(cls) -> int:
        """
        Retourne le prochain numéro de série de manière atomique.

        Crée une nouvelle ligne dans la table, le PK auto-incrémenté
        sert de serial unique. PostgreSQL garantit l'atomicité.

        Returns:
            int: Numéro de série unique (PK de la nouvelle ligne)

        Example:
            >>> serial = TsaSerial.get_next_serial()
            >>> print(serial)
            1
            >>> serial = TsaSerial.get_next_serial()
            >>> print(serial)
            2
        """
        # Créer une nouvelle ligne, PostgreSQL auto-incrémente le PK
        obj = cls.objects.create()
        return obj.pk

    def __str__(self):
        timestamp = self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        return f"TSA Serial #{self.pk} - {timestamp}"
