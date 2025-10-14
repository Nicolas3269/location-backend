"""
Management command pour tester l'email de quittance.
Usage: python manage.py send_test_email --email test@example.com
"""
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


class Command(BaseCommand):
    help = 'Envoie un email de test pour la quittance vers MailHog'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            default='locataire@example.com',
            help='Email du destinataire (défaut: locataire@example.com)'
        )

    def handle(self, *args, **options):
        recipient_email = options['email']

        # Contexte de test
        context = {
            'period': 'Janvier 2025',
            'tenant_name': 'Jean Dupont',
            'start_date': '01/01/2025',
            'end_date': '31/01/2025',
            'amount': '850.00',
            'base_rent': '750.00',
            'charges': '100.00',
            'pdf_url': 'http://localhost:8003/media/quittances/test.pdf',
        }

        self.stdout.write('📧 Génération de l\'email HTML...')

        # Render HTML email template
        html_content = render_to_string('email/quittance_email.html', context)

        self.stdout.write(self.style.SUCCESS('✅ Template HTML généré'))

        # Fallback texte brut
        text_content = f"""
Bonjour {context['tenant_name']},

Votre quittance de loyer pour {context['period']} est disponible.

Montant payé : {context['amount']}€
- Loyer HC : {context['base_rent']}€
- Charges : {context['charges']}€

Téléchargez votre quittance : {context['pdf_url']}

Cordialement,
Hestia
        """

        # Créer et envoyer l'email
        email = EmailMultiAlternatives(
            subject=f"[TEST] Quittance de loyer - {context['period']}",
            body=text_content,
            from_email="HESTIA TEST <noreply@hestia.local>",
            to=[recipient_email],
        )
        email.attach_alternative(html_content, "text/html")

        self.stdout.write(f'📮 Envoi vers {recipient_email}...')

        try:
            email.send()
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ Email envoyé avec succès !\n'
                    f'📥 Vérifiez MailHog : http://localhost:8025\n'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Erreur lors de l\'envoi : {e}')
            )
