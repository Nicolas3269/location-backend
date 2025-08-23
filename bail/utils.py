import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail as django_send_mail

from bail.models import BailSignatureRequest
from location.models import Bien

logger = logging.getLogger(__name__)


def send_mail(subject, message, from_email, recipient_list):
    django_send_mail(subject, message, from_email, recipient_list)


def send_signature_email(signature_request: BailSignatureRequest):
    person = signature_request.bailleur_signataire or signature_request.locataire
    link = f"{settings.FRONTEND_URL}/bail/signing/{signature_request.link_token}/"
    message = f"""
Bonjour {person.prenom},

Veuillez signer le bail en suivant ce lien : {link}

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


def create_signature_requests(bail):
    """
    Crée les demandes de signature pour un bail.
    Utilise la fonction générique pour factoriser le code.
    """
    from signature.services import create_signature_requests_generic

    create_signature_requests_generic(bail, BailSignatureRequest)


def create_bien_from_form_data(form_data, save=True):
    """
    Crée un objet Bien à partir des données du formulaire.

    Args:
        form_data: Les données du formulaire
        save: Si True, sauvegarde l'objet en base.
              Si False, retourne un objet non sauvegardé.

    Returns:
        Instance de Bien
    """

    # Mapper la période de construction (basé sur rent_control.choices)
    periode_construction_map = {
        "avant_1946": "avant 1946",
        "1946_1970": "1946-1970",
        "1971_1990": "1971-1990",
        "1990_2005": "1990-2005",
        "apres_1990": "apres 1990",  # Keep for backward compatibility
        "apres_2005": "apres 2005",
    }
    periode_construction = periode_construction_map.get(
        form_data.get("periodeConstruction", ""), "avant 1946"
    )

    # Mapper le type de logement
    type_logement_map = {
        "appartement": "appartement",
        "maison": "maison",
    }
    type_bien = type_logement_map.get(form_data.get("typeLogement", ""), "appartement")

    # Mapper le meublé
    meuble_map = {
        "meuble": True,
        "vide": False,
    }
    meuble = meuble_map.get(form_data.get("meuble", "vide"), False)

    # Extract DPE expenses if provided
    dpe_grade = form_data.get("dpeGrade", "NA")
    depenses_energetiques = form_data.get("depensesDPE", "").lower()

    # Extract autre energies if needed
    chauffage_energie = form_data.get("chauffage", {}).get("energie", "")
    if chauffage_energie == "autre":
        chauffage_energie = form_data.get("chauffage", {}).get("autreDetail", "")
    eau_chaude_energie = form_data.get("eauChaude", {}).get("energie", "")
    if eau_chaude_energie == "autre":
        eau_chaude_energie = form_data.get("eauChaude", {}).get("autreDetail", "")

    # Préparer les données pour créer le bien
    fill_identification_fiscale = form_data.get("fillIdentificationFiscale") == "true"
    identifiant_fiscal = (
        form_data.get("identificationFiscale", "")
        if fill_identification_fiscale
        else ""
    )

    bien_data = {
        "adresse": form_data.get("adresse", ""),
        "latitude": form_data.get("latitude"),
        "longitude": form_data.get("longitude"),
        "identifiant_fiscal": identifiant_fiscal,
        "regime_juridique": form_data.get("regimeJuridique", ""),
        "type_bien": type_bien,
        "etage": form_data.get("etage", ""),
        "porte": form_data.get("porte", ""),
        "periode_construction": periode_construction,
        "superficie": Decimal(str(form_data.get("surface", 0))),
        "meuble": meuble,
        "classe_dpe": dpe_grade,
        "depenses_energetiques": depenses_energetiques,
        "annexes_privatives": form_data.get("annexes", []),
        "annexes_collectives": form_data.get("annexesCollectives", []),
        "information": form_data.get("information", []),
        "pieces_info": form_data.get("pieces_info", {}),
        "chauffage_type": form_data.get("chauffage", {}).get("type", ""),
        "chauffage_energie": chauffage_energie,
        "eau_chaude_type": form_data.get("eauChaude", {}).get("type", ""),
        "eau_chaude_energie": eau_chaude_energie,
    }

    if save:
        return Bien.objects.create(**bien_data)
    else:
        return Bien(**bien_data)
