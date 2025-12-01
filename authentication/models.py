import uuid
import datetime
from django.db import models
from django.utils import timezone


class EmailVerification(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Vérification d'email"
        verbose_name_plural = "Vérifications d'emails"
        ordering = ["-created_at"]

    def __str__(self):
        status = "Vérifié" if self.verified else "Non vérifié"
        return f"Email {self.email} - {status}"

    def is_expired(self):
        """Retourne True si la vérification a expiré (plus de 10 minutes)"""
        if self.verified:
            return False
        expiration_time = datetime.timedelta(minutes=10)
        return timezone.now() > (self.created_at + expiration_time)
