import base64
import logging
import os
import random

from django.conf import settings
from django.core.files.base import File
from django.core.mail import send_mail as django_send_mail

from algo.signature.main import (
    add_signature_fields_dynamic,
    get_named_dest_coordinates,
    get_signature_field_name,
    sign_pdf,
)
from bail.models import BailSignatureRequest

logger = logging.getLogger(__name__)


def prepare_pdf_with_signature_fields(pdf_path, bail):
    landlords = list(bail.bien.proprietaires.all())
    tenants = list(bail.locataires.all())
    signatories = landlords + tenants

    all_fields = []

    for person in signatories:
        page, rect, field_name = get_named_dest_coordinates(pdf_path, person)
        if rect is None:
            raise ValueError(f"Aucun champ de signature trouvé pour {person.email}")

        all_fields.append(
            {
                "field_name": field_name,
                "rect": rect,
                "person": person,
                "page": page,
            }
        )

    # Ajouter les champs de signature
    add_signature_fields_dynamic(pdf_path, all_fields)


def send_mail(subject, message, from_email, recipient_list):
    django_send_mail(subject, message, from_email, recipient_list)


def process_signature(sig_req, signature_data_url):
    bail = sig_req.bail
    signing_person = sig_req.proprietaire or sig_req.locataire
    signature_bytes = base64.b64decode(signature_data_url.split(",")[1])
    field_name = get_signature_field_name(signing_person)

    # Chemin source : soit latest_pdf (s'il existe), soit le PDF d'origine
    source_path = bail.latest_pdf.path if bail.latest_pdf else bail.pdf.path
    file_name = os.path.basename(source_path).replace("_signed", "").replace(".pdf", "")
    # Chemin final temporaire toujours fixe
    final_tmp_path = f"/tmp/{file_name}_signed_temp.pdf"

    # Appeler `sign_pdf` pour ajouter la signature du signataire courant
    sign_pdf(
        source_path,
        final_tmp_path,
        signing_person,
        field_name,
        signature_bytes,
    )
    # Supprimer l'ancien fichier latest_pdf si existant
    if bail.latest_pdf and bail.latest_pdf.name:
        bail.latest_pdf.delete(save=False)

    # Mettre à jour le champ latest_pdf dans le modèle
    with open(final_tmp_path, "rb") as f:
        bail.latest_pdf.save(f"{file_name}_signed.pdf", File(f), save=True)

    # Nettoyage
    try:
        os.remove(final_tmp_path)
    except Exception as e:
        logger.warning(f"Impossible de supprimer le fichier temporaire : {e}")


def send_signature_email(signature_request):
    person = signature_request.proprietaire or signature_request.locataire
    link = f"{settings.FRONTEND_URL}/bail/signing/{signature_request.link_token}/"
    message = f"""
Bonjour {person.prenom},

Veuillez signer le bail en suivant ce lien : {link}

Votre code de confirmation est : {signature_request.otp}

Merci,
L'équipe HESTIA
"""
    send_mail(
        subject="Signature de votre bail",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        # recipient_list=[person.email],
        recipient_list=["nicolas3269@gmail.com"],
    )


def generate_otp():
    return str(random.randint(100000, 999999))


def create_signature_requests(bail):
    landlords = list(bail.bien.proprietaires.all())
    tenants = list(bail.locataires.all())

    for i, person in enumerate(landlords):
        otp = generate_otp()
        req = BailSignatureRequest.objects.create(
            bail=bail, proprietaire=person, order=i, otp=otp
        )

        if i == 0:
            send_signature_email(req)  # Seul le premier reçoit un lien immédiatement

    for i, person in enumerate(tenants):
        otp = generate_otp()
        req = BailSignatureRequest.objects.create(
            bail=bail, locataire=person, order=i + len(landlords), otp=otp
        )
