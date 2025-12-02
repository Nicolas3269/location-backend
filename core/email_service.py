"""
Service centralisé d'envoi d'emails avec templates MJML.

Utilise mrml (Rust port de MJML) pour compiler les templates en HTML
compatible avec tous les clients mail (Gmail, Outlook, etc.).
"""

import logging
from typing import Any

import mrml
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class EmailService:
    """Service d'envoi d'emails stylisés avec MJML."""

    @staticmethod
    def render_mjml(template_path: str, context: dict[str, Any]) -> str:
        """
        Render un template MJML avec le contexte Django et compile en HTML.

        Args:
            template_path: Chemin vers le template (ex: "emails/bailleur/relance_j1.mjml")
            context: Contexte Django pour le template

        Returns:
            HTML compilé prêt à être envoyé
        """
        # Ajouter les variables communes
        context.setdefault("frontend_url", settings.FRONTEND_URL)
        context.setdefault("logo_url", "https://hestia.software/icons/logo-hestia-whatsapp.png")
        context.setdefault("current_year", "2025")

        # Render le template Django (avec variables)
        mjml_content = render_to_string(template_path, context)

        # Compiler MJML → HTML via mrml (Rust)
        try:
            result = mrml.to_html(mjml_content)
            # mrml retourne un objet Output avec .content et .warnings
            if result.warnings:
                for warning in result.warnings:
                    logger.warning(f"MJML warning ({template_path}): {warning}")
            return result.content
        except Exception as e:
            logger.error(f"Erreur compilation MJML {template_path}: {e}")
            # Fallback: retourner le contenu brut
            return mjml_content

    @staticmethod
    def send(
        to: str | list[str],
        subject: str,
        template: str,
        context: dict[str, Any],
        from_email: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        reply_to: list[str] | None = None,
    ) -> bool:
        """
        Envoie un email stylisé avec un template MJML.

        Args:
            to: Email(s) destinataire(s)
            subject: Sujet de l'email
            template: Nom du template (ex: "bailleur/relance_j1")
            context: Variables pour le template
            from_email: Email expéditeur (défaut: DEFAULT_FROM_EMAIL)
            cc: Liste des emails en copie
            bcc: Liste des emails en copie cachée
            reply_to: Liste des emails pour réponse

        Returns:
            True si envoyé avec succès, False sinon
        """
        if isinstance(to, str):
            to = [to]

        template_path = f"emails/{template}.mjml"

        try:
            html_content = EmailService.render_mjml(template_path, context)

            # Créer l'email avec version texte et HTML
            email = EmailMultiAlternatives(
                subject=subject,
                body=EmailService._html_to_text(html_content),
                from_email=from_email or settings.DEFAULT_FROM_EMAIL,
                to=to,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)

            logger.info(f"Email envoyé: '{subject}' → {to}")
            return True

        except Exception as e:
            logger.error(f"Erreur envoi email '{subject}' → {to}: {e}")
            return False

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convertit HTML en texte brut simple (fallback)."""
        import re

        # Supprimer les tags HTML
        text = re.sub(r"<[^>]+>", "", html)
        # Nettoyer les espaces multiples
        text = re.sub(r"\s+", " ", text)
        # Nettoyer les lignes
        text = "\n".join(line.strip() for line in text.split("\n") if line.strip())
        return text


# Fonctions raccourcies pour usage courant
def send_email(
    to: str | list[str],
    subject: str,
    template: str,
    context: dict[str, Any],
    **kwargs,
) -> bool:
    """Raccourci pour EmailService.send()."""
    return EmailService.send(to, subject, template, context, **kwargs)


def render_email(template: str, context: dict[str, Any]) -> str:
    """Raccourci pour EmailService.render_mjml()."""
    return EmailService.render_mjml(f"emails/{template}.mjml", context)
