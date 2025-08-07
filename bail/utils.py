import logging
from decimal import Decimal
from typing import List

from django.conf import settings
from django.core.mail import send_mail as django_send_mail

from algo.signature.main import (
    add_signature_fields_dynamic,
    get_named_dest_coordinates,
)
from bail.models import Bailleur, BailSignatureRequest, BailSpecificites, Personne

logger = logging.getLogger(__name__)


def prepare_pdf_with_signature_fields(pdf_path, bail: BailSpecificites):
    # Les signataires sont les signataires des bailleurs + les locataires

    bailleurs: List[Bailleur] = bail.bien.bailleurs.all()
    bailleur_signataires: Personne = [bailleur.signataire for bailleur in bailleurs]

    all_fields = []

    for person in bailleur_signataires:
        page, rect, field_name = get_named_dest_coordinates(
            pdf_path, person, "bailleur"
        )
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

    for person in list(bail.locataires.all()):
        page, rect, field_name = get_named_dest_coordinates(
            pdf_path, person, "locataire"
        )
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
    bailleurs: List[Bailleur] = bail.bien.bailleurs.all()
    bailleur_signataires: Personne = [bailleur.signataire for bailleur in bailleurs]
    tenants = list(bail.locataires.all())

    for i, signataire in enumerate(bailleur_signataires):
        BailSignatureRequest.objects.create(
            bail=bail, bailleur_signataire=signataire, order=i, otp=""
        )
        # OTP sera généré quand l'utilisateur arrive sur la page

    for i, person in enumerate(tenants):
        BailSignatureRequest.objects.create(
            bail=bail, locataire=person, order=i + len(bailleur_signataires), otp=""
        )
        # OTP sera généré quand l'utilisateur arrive sur la page


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
    from bail.models import Bien

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
        "pieces_info": form_data.get("pieces", {}),
        "chauffage_type": form_data.get("chauffage", {}).get("type", ""),
        "chauffage_energie": chauffage_energie,
        "eau_chaude_type": form_data.get("eauChaude", {}).get("type", ""),
        "eau_chaude_energie": eau_chaude_energie,
    }

    if save:
        return Bien.objects.create(**bien_data)
    else:
        return Bien(**bien_data)
