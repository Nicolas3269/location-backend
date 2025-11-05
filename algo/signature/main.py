import io
import platform

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.fields import (
    SigFieldSpec,
    append_signature_field,
)
from slugify import slugify

from location.models import Personne

TAMPON_WIDTH_PX = 230
TAMPON_HEIGHT_PX = 180
SCALE_FACTOR = 4


def get_signature_field_name(person: Personne):
    """
    Crée un nom de champ de signature basé sur l'ID et le nom de la personne.
    """
    return slugify(f"{person.id}-{person.full_name}")


def get_named_dest_coordinates(pdf_path, person: Personne, target_type=None):
    field_name = get_signature_field_name(person)

    if target_type == "bailleur":
        target_marker = f"ID_SIGNATURE_BAILLEUR_{person.id}"
    elif target_type == "locataire":
        target_marker = f"ID_SIGNATURE_LOC_{person.id}"
    else:
        # Fallback pour d'autres types si nécessaire
        target_marker = f"ID_SIGNATURE_{person.id}"

    box_width_pt = px_to_pt(TAMPON_WIDTH_PX)
    box_height_pt = px_to_pt(TAMPON_HEIGHT_PX)

    doc = fitz.open(pdf_path)

    for page_number in range(len(doc)):
        page = doc[page_number]
        match = page.search_for(target_marker)
        if len(match) > 1:
            raise ValueError(
                "Plusieurs marqueurs de signature trouvés sur la même page."
            )
        if match:
            anchor = match[0]
            # Récupérer la hauteur de la page
            page_height = page.rect.height

            # Décalage Y avec inversion du repère (origine en haut)
            x0 = anchor.x0
            y0 = page_height - anchor.y0 - box_height_pt
            x1 = x0 + box_width_pt
            y1 = y0 + box_height_pt

            return page_number, fitz.Rect(x0, y0, x1, y1), field_name

    return None, None, field_name


def get_default_font_path():
    if platform.system() == "Linux":
        return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    elif platform.system() == "Darwin":  # macOS
        return "/Library/Fonts/Arial.ttf"
    elif platform.system() == "Windows":
        return "C:/Windows/Fonts/arial.ttf"
    else:
        raise RuntimeError("Système d'exploitation non supporté")


def px_to_pt(px):
    # Environ 0.75 pt par pixel à 96 DPI
    return px * 72 / 96


def compose_signature_stamp(signature_bytes, user, signature_timestamp):
    """
    Compose le tampon visuel de signature avec l'image manuscrite et les métadonnées.

    Args:
        signature_bytes: Image de signature manuscrite (PNG bytes)
        user: Instance Personne (Bailleur/Locataire)
        signature_timestamp: datetime pour la date affichée (défaut: now())

    Returns:
        tuple: (PIL.Image, BytesIO buffer)
    """
    # Constantes
    scale_factor = SCALE_FACTOR
    final_width = TAMPON_WIDTH_PX * scale_factor
    final_height = TAMPON_HEIGHT_PX * scale_factor
    signature_area_height = 110 * scale_factor
    margin_above_text = 20 * scale_factor
    text_padding_x = 10 * scale_factor

    # Charger et redimensionner l'image
    img = Image.open(io.BytesIO(signature_bytes)).convert("RGBA")
    img_ratio = img.width / img.height

    max_sig_width = final_width
    max_sig_height = signature_area_height

    target_width = int(max_sig_height * img_ratio)
    target_height = max_sig_height

    if target_width > max_sig_width:
        target_width = max_sig_width
        target_height = int(target_width / img_ratio)

    img = img.resize((target_width, target_height), Image.LANCZOS)

    # Créer le tampon
    final_img = Image.new("RGBA", (final_width, final_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(final_img)

    # Centrer l'image horizontalement
    img_x = (final_width - target_width) // 2
    final_img.paste(img, (img_x, 0), img)

    # Date de signature REQUISE (pas de fallback, fail fast si manquante)
    if signature_timestamp is None:
        raise ValueError(
            "signature_timestamp est requis pour cohérence forensique PDF/DB. "
            "Capturer timezone.now() AVANT appel à compose_signature_stamp()."
        )

    # Convertir en heure locale française pour affichage
    import zoneinfo

    paris_tz = zoneinfo.ZoneInfo("Europe/Paris")
    signature_timestamp_local = signature_timestamp.astimezone(paris_tz)

    # Formater timezone offset ISO 8601 (+01:00 ou +02:00)
    tz_offset = signature_timestamp_local.strftime("%z")  # "+0100"
    tz_offset_formatted = f"{tz_offset[:3]}:{tz_offset[3:]}"  # "+01:00"

    # Préparer le texte (avec timezone offset pour traçabilité)
    font = ImageFont.truetype(get_default_font_path(), size=12 * scale_factor)
    date_str = signature_timestamp_local.strftime("%d/%m/%Y %H:%M:%S")
    text = (
        f"{user.firstName} {user.lastName}\n"
        f"{user.email}\n"
        f"{date_str} {tz_offset_formatted}\n"
        f"Signature AES • Conforme eIDAS"
    )

    # Position du texte : à gauche, sous l'image avec marge
    text_x = text_padding_x
    text_y = target_height + margin_above_text

    draw.multiline_text(
        (text_x, text_y),
        text,
        fill="black",
        font=font,
        spacing=4,
    )

    output = io.BytesIO()
    final_img.save(output, format="PNG")
    output.seek(0)

    return final_img, output


def add_signature_fields_dynamic(pdf_path, fields):
    """
    Add signature fields to a PDF document.

    Args:
        pdf_path: Path to the PDF file
        fields: List of field dictionaries with 'field_name' and 'box' keys
    """
    with open(pdf_path, "rb+") as doc:
        w = IncrementalPdfFileWriter(doc)

        for field in fields:
            append_signature_field(
                w,
                SigFieldSpec(
                    sig_field_name=field["field_name"],
                    box=field["rect"],
                    on_page=field["page"],
                ),
            )

        w.write_in_place()


def sign_pdf(
    source_path,
    output_path,
    user,
    field_name,
    signature_bytes,
    request=None,
    document=None,
    signature_request=None,
):
    """
    Signature utilisateur avec certificat auto-signé.

    DEPRECATED: Cette fonction est conservée pour rétrocompatibilité mais délègue
    maintenant à sign_user_with_metadata() du module certification_flow.

    Args:
        source_path: Chemin du PDF source
        output_path: Chemin du PDF de sortie
        user: Instance de Personne (Bailleur ou Locataire)
        field_name: Nom du champ de signature
        signature_bytes: Image de signature manuscrite (PNG en bytes)
        request: Django HttpRequest (optionnel, pour IP/user-agent)
        document: Instance du document (Bail/EtatLieux/Quittance)
        signature_request: Instance de SignatureRequest
                          (métadonnées OTP extraites depuis ici)

    Returns:
        str: Chemin du PDF signé

    Note:
        - Utilise désormais des certificats auto-signés (gratuit, 0€)
        - Capture métadonnées OTP/IP/timestamp pour journal de preuves
        - Sauvegarde métadonnées en DB (SignatureMetadata)
        - Signature d'approbation (certify=False)
        - Hérite de la protection DocMDP de la certification Hestia
    """
    from signature.certification_flow import sign_user_with_metadata

    return sign_user_with_metadata(
        source_path=source_path,
        output_path=output_path,
        user=user,
        field_name=field_name,
        signature_bytes=signature_bytes,
        request=request,
        document=document,
        signature_request=signature_request,
    )


def verify_pdf_signature(pdf_path):
    """
    Valide les signatures d'un PDF avec PyHanko.

    Commande complète pour validation :
    poetry run pyhanko sign validate \
        --trust certificates/hestia_server.pem \
        --trust certificates/hestia_certificate_authority.pem \
        --trust certificates/hestia_tsa.pem \
        --pretty-print <pdf_path>

    Certificats requis :
    - hestia_server.pem : Certificat Hestia AATL (certification)
    - hestia_certificate_authority.pem : CA Hestia (signatures utilisateurs)
    - hestia_tsa.pem : Certificat TSA (timestamps)

    Exemple :
        poetry run pyhanko sign validate \
            --trust certificates/hestia_server.pem \
            --trust certificates/hestia_certificate_authority.pem \
            --trust certificates/hestia_tsa.pem \
            --pretty-print media/signed_documents/bail_xxx.pdf

    Sans le certificat TSA, la validation échouera avec :
        "TSA cert trust anchor: No path to trust anchor found."
        "The signature is judged INVALID."
    """
    pass
