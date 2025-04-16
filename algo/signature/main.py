import datetime
import io
import os
import platform

import fitz  # PyMuPDF
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
from pyhanko import stamp
from pyhanko.pdf_utils.images import PdfImage
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, append_signature_field
from slugify import slugify


def get_named_dest_coordinates(pdf_path, person, img_height_px):
    field_name = slugify(f"{person.id}_{person.get_full_name()}")
    target_text = f"Signature de {person.prenom} {person.nom}"
    doc = fitz.open(pdf_path)

    for page_number in range(len(doc)):
        page = doc[page_number]
        text_instances = page.search_for(target_text)
        if text_instances:
            rect = text_instances[0]

            # Agrandir le rect vers le bas pour accueillir le tampon
            stamp_height_pt = px_to_pt(img_height_px + 20)
            # décalage du haut de la boîte (sous le texte)
            rect.y0 += 10
            # hauteur du tampon : image + marge
            rect.y1 = rect.y0 + stamp_height_pt

            return page_number, rect, field_name

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
    return float(px * 0.75)


def compose_signature_stamp(signature_bytes, user):
    img = Image.open(io.BytesIO(signature_bytes)).convert("RGBA")
    signature_height = 60

    # Redimensionner si l'image est trop haute (préserve le ratio)
    width, height = img.size

    ratio = signature_height / height
    new_width = int(width * ratio)
    img = img.resize((new_width, signature_height), Image.LANCZOS)
    width, height = img.size  # maj dimensions

    # Préparer le texte
    font = ImageFont.truetype(get_default_font_path(), size=px_to_pt(12))
    text = (
        f"{user.prenom} {user.nom}\n"
        f"{user.email}\n"
        f"{datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"Signature conforme eIDAS"
    )

    # Mesurer le texte
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=4)
    text_height = bbox[3] - bbox[1]

    # Fusion image + texte
    total_height = height + text_height + 20
    final_img = Image.new("RGBA", (width, total_height), (255, 255, 255, 0))
    final_img.paste(img, (0, 0))

    draw = ImageDraw.Draw(final_img)
    draw.multiline_text((10, height + 10), text, fill="black", font=font, spacing=4)

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
    pdf_image = PdfImage(composed_image)
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


def generate_dynamic_boxes(
    landlord_imgs, tenant_imgs, start_x=100, start_y=100, spacing=20
):
    """
    Generate signature boxes for multiple landlords and tenants.

    Args:
        landlord_imgs: List of landlord signature images or single image
        tenant_imgs: List of tenant signature images or single image
        start_x: Starting X position
        start_y: Starting Y position
        spacing: Vertical spacing between boxes

    Returns:
        tuple: (landlord_boxes, tenant_boxes) where each is a list of boxes
    """
    # Ensure landlord_imgs is a list
    if not isinstance(landlord_imgs, list):
        landlord_imgs = [landlord_imgs]

    # Ensure tenant_imgs is a list
    if not isinstance(tenant_imgs, list):
        tenant_imgs = [tenant_imgs]

    landlord_boxes = []
    tenant_boxes = []

    current_y = start_y

    # Generate boxes for landlords
    for landlord_img in landlord_imgs:
        width, height = landlord_img.size
        box = (
            start_x,
            current_y,
            start_x + width,
            current_y + height,
        )
        landlord_boxes.append(box)
        current_y += height + spacing

    # Generate boxes for tenants
    for tenant_img in tenant_imgs:
        width, height = tenant_img.size
        box = (
            start_x,
            current_y,
            start_x + width,
            current_y + height,
        )
        tenant_boxes.append(box)
        current_y += height + spacing

    # If we only have one landlord box, return it as a single box (for backward compatibility)
    if len(landlord_boxes) == 1:
        landlord_boxes = landlord_boxes[0]

    return landlord_boxes, tenant_boxes


def verify_pdf_signature(pdf_path):
    # poetry run pyhanko sign validate --trust cert.pem --pretty-print media/bail_pdfs/bail_85_85d663da4dc340cdaaa257ba1086191d_signed.pdf
    # poetry run pyhanko sign validate --trust ../../cert.pem --pretty-print pdf_path
    pass
