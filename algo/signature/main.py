import datetime
import io
import os
import platform

import fitz  # PyMuPDF
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
from pyhanko import stamp
from pyhanko.pdf_utils.content import BoxConstraints
from pyhanko.pdf_utils.images import PdfImage
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import (
    SigFieldSpec,
    append_signature_field,
)
from slugify import slugify

from bail.models import Personne

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


def compose_signature_stamp(signature_bytes, user):
    # Constantes
    scale_factor = SCALE_FACTOR
    final_width = TAMPON_WIDTH_PX * scale_factor
    final_height = TAMPON_HEIGHT_PX * scale_factor
    signature_area_height = 110 * scale_factor
    margin_above_text = 20 * scale_factor
    text_padding_x = 10 * scale_factor

    # Charger et redimensionner l’image
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

    # Centrer l’image horizontalement
    img_x = (final_width - target_width) // 2
    final_img.paste(img, (img_x, 0), img)

    # Préparer le texte
    font = ImageFont.truetype(get_default_font_path(), size=12 * scale_factor)
    text = (
        f"{user.prenom} {user.nom}\n"
        f"{user.email}\n"
        f"{datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"Signature conforme eIDAS"
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


def sign_pdf(source_path, output_path, user, field_name, signature_bytes):
    signer_cert_pfx = os.path.join(settings.BASE_DIR, "cert.pfx")
    signer_password = os.getenv("KEY_PASSWORD")
    if isinstance(signer_password, str):
        signer_password = signer_password.encode("utf-8")

    signer = signers.SimpleSigner.load_pkcs12(
        pfx_file=signer_cert_pfx, passphrase=signer_password
    )

    signature_meta = signers.PdfSignatureMetadata(
        field_name=field_name,
        reason="Accord sur les conditions du bail",
        contact_info=getattr(user, "email", ""),
        location="France",
        name=f"{getattr(user, 'prenom', '')} {getattr(user, 'nom', '')}",
    )

    composed_image, composed_buffer = compose_signature_stamp(signature_bytes, user)
    box = BoxConstraints(width=TAMPON_WIDTH_PX, height=TAMPON_HEIGHT_PX)
    pdf_image = PdfImage(composed_image, box=box)
    stamp_style = stamp.StaticStampStyle(
        background=pdf_image,
        background_opacity=1.0,
        border_width=1,
    )

    with open(source_path, "rb") as inf:
        with open(output_path, "wb") as outf:
            pdf_signer = signers.PdfSigner(
                signature_meta=signature_meta,
                signer=signer,
                stamp_style=stamp_style,
            )

            writer = IncrementalPdfFileWriter(inf)
            pdf_signer.sign_pdf(writer, output=outf, existing_fields_only=True)

    return output_path


def verify_pdf_signature(pdf_path):
    # poetry run pyhanko sign validate --trust cert.pem --pretty-print media/bail_pdfs/bail_85_85d663da4dc340cdaaa257ba1086191d_signed.pdf
    # poetry run pyhanko sign validate --trust ../../cert.pem --pretty-print pdf_path
    pass
