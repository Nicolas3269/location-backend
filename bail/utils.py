import base64
import logging
import os
from decimal import Decimal
from typing import List

from django.conf import settings
from django.core.files.base import File
from django.core.mail import send_mail as django_send_mail

from algo.signature.main import (
    add_signature_fields_dynamic,
    get_named_dest_coordinates,
    get_signature_field_name,
    sign_pdf,
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


def process_signature(sig_req: BailSignatureRequest, signature_data_url):
    bail = sig_req.bail
    signing_person = sig_req.bailleur_signataire or sig_req.locataire
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


# ==============================
# UTILS POUR ÉTAT DES LIEUX
# ==============================


def create_etat_lieux_signature_requests(etat_lieux):
    """
    Crée les demandes de signature pour un état des lieux.
    Réutilise la logique des baux pour factoriser.
    """
    from bail.models import EtatLieuxSignatureRequest

    # Supprimer les anciennes demandes de signature
    EtatLieuxSignatureRequest.objects.filter(etat_lieux=etat_lieux).delete()

    # Récupérer les signataires depuis le bail associé
    bail = etat_lieux.bail
    bailleurs = bail.bien.bailleurs.all()
    bailleur_signataires = [bailleur.signataire for bailleur in bailleurs]
    locataires = bail.locataires.all()

    order = 1

    # Créer les demandes pour les bailleurs signataires
    for signataire in bailleur_signataires:
        if signataire:
            EtatLieuxSignatureRequest.objects.create(
                etat_lieux=etat_lieux,
                bailleur_signataire=signataire,
                order=order,
            )
            order += 1

    # Créer les demandes pour les locataires
    for locataire in locataires:
        EtatLieuxSignatureRequest.objects.create(
            etat_lieux=etat_lieux,
            locataire=locataire,
            order=order,
        )
        order += 1

    logger.info(
        f"Créé {order - 1} demandes de signature pour l'état des lieux {etat_lieux.id}"
    )


def send_etat_lieux_signature_email(signature_request):
    """
    Envoie un email de demande de signature pour un état des lieux.
    Factorisation de la logique d'envoi d'email.
    """

    person = signature_request.bailleur_signataire or signature_request.locataire
    etat_lieux = signature_request.etat_lieux

    subject = (
        f"Signature requise - État des lieux {etat_lieux.get_type_etat_lieux_display()}"
    )

    # URL de signature (à adapter selon votre frontend)
    signature_url = (
        f"{settings.FRONTEND_URL}/etat-lieux/signature/{signature_request.link_token}"
    )

    message = f"""
    Bonjour {person.prenom} {person.nom},

    Vous êtes invité(e) à signer l'état des lieux {etat_lieux.get_type_etat_lieux_display()} 
    pour le bien situé à : {etat_lieux.bien.adresse}

    Pour procéder à la signature, cliquez sur le lien suivant :
    {signature_url}

    Cordialement,
    L'équipe Location
    """

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[person.email],
        )
        logger.info(
            f"Email de signature envoyé à {person.email} pour l'état des lieux {etat_lieux.id}"
        )
    except Exception as e:
        logger.error(
            f"Erreur lors de l'envoi de l'email de signature à {person.email}: {e}"
        )
        raise


def prepare_etat_lieux_pdf_with_signature_fields(pdf_path, etat_lieux):
    """
    Prépare le PDF d'état des lieux avec les champs de signature.
    Factorisation de la logique de préparation des signatures.
    """
    # Réutiliser la logique existante en adaptant pour l'état des lieux
    bail = etat_lieux.bail
    bailleurs = bail.bien.bailleurs.all()
    bailleur_signataires = [bailleur.signataire for bailleur in bailleurs]

    all_fields = []

    # Ajouter les champs pour les bailleurs signataires
    for person in bailleur_signataires:
        if person:
            page, rect, field_name = get_named_dest_coordinates(
                pdf_path, person, "bailleur"
            )
            if rect is None:
                logger.warning(f"Aucun champ de signature trouvé pour {person.email}")
                continue

            all_fields.append(
                {
                    "field_name": field_name,
                    "rect": rect,
                    "person": person,
                    "page": page,
                }
            )

    # Ajouter les champs pour les locataires
    for person in bail.locataires.all():
        page, rect, field_name = get_named_dest_coordinates(
            pdf_path, person, "locataire"
        )
        if rect is None:
            logger.warning(f"Aucun champ de signature trouvé pour {person.email}")
            continue

        all_fields.append(
            {
                "field_name": field_name,
                "rect": rect,
                "person": person,
                "page": page,
            }
        )

    if not all_fields:
        raise ValueError("Aucun champ de signature trouvé dans le PDF")

    # Ajouter les champs de signature au PDF
    add_signature_fields_dynamic(pdf_path, all_fields)
    logger.info(
        f"Ajouté {len(all_fields)} champs de signature au PDF de l'état des lieux"
    )


def process_etat_lieux_signature(signature_request, signature_data_url):
    """
    Traite une signature d'état des lieux.
    Factorisation de la logique de traitement des signatures.
    """
    # Décoder l'image de signature
    if not signature_data_url.startswith("data:image/"):
        raise ValueError("Format d'image de signature invalide")

    header, encoded = signature_data_url.split(",", 1)
    signature_data = base64.b64decode(encoded)

    # Sauvegarder l'image de signature
    signature_filename = f"signature_{signature_request.id}.png"
    signature_request.signature_image.save(
        signature_filename,
        File(signature_data),
        save=True,
    )

    # Obtenir les informations de signature
    person = signature_request.bailleur_signataire or signature_request.locataire
    etat_lieux = signature_request.etat_lieux

    # Signer le PDF
    input_pdf_path = etat_lieux.pdf.path
    output_pdf_path = input_pdf_path.replace(".pdf", "_signed.pdf")

    field_name = get_signature_field_name(
        person, "bailleur" if signature_request.bailleur_signataire else "locataire"
    )

    sign_pdf(
        input_pdf_path,
        output_pdf_path,
        signature_request.signature_image.path,
        field_name,
    )

    # Mettre à jour le PDF de l'état des lieux avec la version signée
    with open(output_pdf_path, "rb") as f:
        etat_lieux.pdf.save(
            os.path.basename(output_pdf_path),
            File(f),
            save=True,
        )

    # Nettoyer le fichier temporaire
    try:
        os.remove(output_pdf_path)
    except Exception as e:
        logger.warning(
            f"Impossible de supprimer le fichier temporaire {output_pdf_path}: {e}"
        )

    logger.info(
        f"Signature de {person.email} appliquée à l'état des lieux {etat_lieux.id}"
    )


def get_or_create_pieces_for_bien(bien):
    """
    Récupère ou crée les pièces pour un bien donné.
    Simple et direct.
    """
    from bail.models import EtatLieuxPiece

    # Vérifier si des pièces existent déjà
    pieces = EtatLieuxPiece.objects.filter(bien=bien)

    if pieces.exists():
        return pieces

    # Sinon, créer les pièces depuis bien.pieces_info
    if not bien.pieces_info:
        # Créer une pièce par défaut
        piece = EtatLieuxPiece.objects.create(
            bien=bien, nom="Pièce principale", type_piece="room"
        )
        return [piece]

    pieces_created = []

    # Créer les pièces basées sur pieces_info
    type_mapping = {
        "chambres": {"type": "bedroom", "nom_base": "Chambre"},
        "salons": {"type": "living", "nom_base": "Salon"},
        "cuisines": {"type": "kitchen", "nom_base": "Cuisine"},
        "sallesDeBain": {"type": "bathroom", "nom_base": "Salle de bain"},
        "sallesEau": {"type": "bathroom", "nom_base": "Salle d'eau"},
        "wc": {"type": "bathroom", "nom_base": "WC"},
        "entrees": {"type": "room", "nom_base": "Entrée"},
        "couloirs": {"type": "room", "nom_base": "Couloir"},
        "dressings": {"type": "room", "nom_base": "Dressing"},
        "celliers": {"type": "room", "nom_base": "Cellier"},
        "buanderies": {"type": "room", "nom_base": "Buanderie"},
    }

    for piece_type, count in bien.pieces_info.items():
        if isinstance(count, int) and count > 0 and piece_type in type_mapping:
            mapping = type_mapping[piece_type]
            for i in range(count):
                nom = f"{mapping['nom_base']}"
                if count > 1:
                    nom += f" {i + 1}"

                piece = EtatLieuxPiece.objects.create(
                    bien=bien, nom=nom, type_piece=mapping["type"]
                )
                pieces_created.append(piece)

    logger.info(f"Créé {len(pieces_created)} pièces pour le bien {bien.id}")
    return pieces_created


def create_etat_lieux_from_form_data(form_data, bail_id, user):
    """
    Crée un état des lieux à partir des données du formulaire.
    Simple et direct.
    """
    from bail.models import BailSpecificites, EtatLieux, EtatLieuxPieceDetail

    # Récupérer le bail
    bail = BailSpecificites.objects.get(id=bail_id)

    # Créer l'état des lieux principal
    etat_lieux = EtatLieux.objects.create(
        bail=bail,
        type_etat_lieux=form_data.get("type", "entree"),
    )

    # Récupérer les pièces du bien (ou les créer si elles n'existent pas)
    pieces = get_or_create_pieces_for_bien(bail.bien)

    # Créer les détails pour chaque pièce depuis les données du formulaire
    rooms_by_id = {}
    for room_data in form_data.get("rooms", []):
        room_id = room_data.get("id")
        if room_id:
            rooms_by_id[room_id] = room_data

    for piece in pieces:
        room_data = rooms_by_id.get(str(piece.id), {})
        EtatLieuxPieceDetail.objects.create(
            etat_lieux=etat_lieux,
            piece=piece,
            elements=room_data.get("elements", {}),
            equipments=room_data.get("equipments", []),
            mobilier=room_data.get("mobilier", []),
        )

    logger.info(f"État des lieux créé: {etat_lieux.id} avec {len(pieces)} pièces")
    return etat_lieux


def save_etat_lieux_photos(etat_lieux, uploaded_photos, photo_references):
    """
    Sauvegarde les photos uploadées pour un état des lieux.
    Super simple maintenant !
    """
    from bail.models import EtatLieuxPhoto

    if not uploaded_photos:
        return

    saved_photos = []

    # Récupérer toutes les pièces du bien
    pieces = etat_lieux.bail.bien.pieces_etat_lieux.all()
    pieces_map = {str(piece.id): piece for piece in pieces}

    for photo_ref in photo_references:
        frontend_room_id = photo_ref["room_id"]  # UUID de la pièce
        photo_key = (
            f"{frontend_room_id}_{photo_ref['element_key']}_{photo_ref['photo_index']}"
        )

        if photo_key in uploaded_photos and frontend_room_id in pieces_map:
            uploaded_file = uploaded_photos[photo_key]
            piece = pieces_map[frontend_room_id]

            # Créer la photo directement liée à la pièce
            photo = EtatLieuxPhoto.objects.create(
                piece=piece,
                element_key=photo_ref["element_key"],
                photo_index=photo_ref["photo_index"],
                image=uploaded_file,
                nom_original=uploaded_file.name,
            )

            saved_photos.append(
                {
                    "id": str(photo.id),
                    "piece_id": str(photo.piece.id),
                    "piece_nom": photo.piece.nom,
                    "element_key": photo.element_key,
                    "photo_index": photo.photo_index,
                    "url": photo.image.url,
                    "original_name": photo.nom_original,
                }
            )

    logger.info(f"Sauvegardé {len(saved_photos)} photos")
    return saved_photos
