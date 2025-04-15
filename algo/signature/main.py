import datetime
import io
import os
import platform

# ####
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
from pyhanko import stamp
from pyhanko.pdf_utils.images import PdfImage
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, append_signature_field


def get_default_font_path():
    if platform.system() == "Linux":
        return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    elif platform.system() == "Darwin":  # macOS
        return "/Library/Fonts/Arial.ttf"
    elif platform.system() == "Windows":
        return "C:/Windows/Fonts/arial.ttf"
    else:
        raise RuntimeError("Système d'exploitation non supporté")


def compose_signature_stamp(signature_bytes, user):
    img = Image.open(io.BytesIO(signature_bytes)).convert("RGBA")

    # Taille image originale
    width, height = img.size

    # Charger une police plus grande
    font = ImageFont.truetype(get_default_font_path(), size=18)

    # Texte eIDAS
    text = (
        f"{user.prenom} {user.nom} – {user.email}\n"
        f"{datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"Signature conforme eIDAS"
    )

    # Texte eIDAS
    text = (
        f"{user.prenom} {user.nom} – {user.email}\n"
        f"{datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"Signature conforme eIDAS"
    )

    # Mesurer la hauteur du texte
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=4)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Créer une image plus grande
    total_height = height + text_height + 20
    final_img = Image.new("RGBA", (width, total_height), (255, 255, 255, 0))

    # Coller la signature
    final_img.paste(img, (0, 0))

    # Dessiner le texte
    draw = ImageDraw.Draw(final_img)
    draw.multiline_text((10, height + 10), text, fill="black", font=font, spacing=4)

    output = io.BytesIO()
    final_img.save(output, format="PNG")
    output.seek(0)
    return output


def add_signature_fields(pdf_path):
    """Ajoute des champs de signature au PDF pour le propriétaire et le locataire"""
    with open(pdf_path, "rb+") as doc:
        # Créer un writer pour les modifications
        w = IncrementalPdfFileWriter(doc)

        # Ajouter le champ de signature propriétaire
        # -1 signifie la dernière page
        append_signature_field(
            w,
            SigFieldSpec(
                sig_field_name="Landlord",
                box=(425, 20, 575, 150),  # Coordonnées (bas de page à droite)
                on_page=-1,  # Dernière page
            ),
        )

        # Ajouter le champ de signature locataire
        append_signature_field(
            w,
            SigFieldSpec(
                sig_field_name="Tenant",
                box=(125, 20, 275, 70),  # Coordonnées (bas de page à gauche)
                on_page=-1,  # Dernière page
            ),
        )

        # Écrire toutes les modifications en une seule fois
        w.write_in_place()


def sign_pdf(source_path, output_path, user, field_name, signature_bytes):
    """Signe électroniquement un document PDF"""

    # Charger les certificats et clés
    signer_cert_pfx = os.path.join(settings.BASE_DIR, "cert.pfx")
    signer_password = os.getenv("KEY_PASSWORD")
    if isinstance(signer_password, str):
        signer_password = signer_password.encode("utf-8")

    # Utiliser SimpleSigner.load_pkcs12 qui fonctionne avec plusieurs versions
    signer = signers.SimpleSigner.load_pkcs12(
        pfx_file=signer_cert_pfx, passphrase=signer_password
    )

    # Configurer les paramètres de signature
    signature_meta = signers.PdfSignatureMetadata(
        field_name=field_name,
        reason="Accord sur les conditions du bail",
        contact_info=getattr(user, "email", ""),
        location="France",
        name=f"{getattr(user, 'prenom', '')} {getattr(user, 'nom', '')}",
        # Indiquer explicitement PAdES
        # subfilter=SigSeedSubFilter.PADES,
    )

    # 2. Créer un style combiné : image en fond, texte en haut
    composed_image = compose_signature_stamp(signature_bytes, user)
    pdf_image = PdfImage(Image.open(composed_image))
    stamp_style = stamp.StaticStampStyle(
        background=pdf_image,
        background_opacity=1.0,
        border_width=1,
    )

    # Signer le document
    with open(source_path, "rb") as inf:
        with open(output_path, "wb") as outf:
            # Créer un PdfSigner avec les métadonnées et le style de signature
            pdf_signer = signers.PdfSigner(
                signature_meta=signature_meta,
                signer=signer,
                stamp_style=stamp_style,
                # Ajouter un horodatage pour la conformité eIDAS
                # timestamper=HTTPTimeStamper('http://timestamp.entrust.net/TSS/RFC3161sha2TS')
            )

            # Créer un IncrementalPdfFileWriter
            writer = IncrementalPdfFileWriter(inf)

            # Signer le PDF et écrire dans le fichier de sortie
            pdf_signer.sign_pdf(
                writer,
                output=outf,
                existing_fields_only=True,  # Utiliser uniquement les champs existants
            )

    return output_path


def verify_pdf_signature(pdf_path):
    # poetry run pyhanko sign validate --trust cert.pem --pretty-print media/bail_pdfs/bail_85_85d663da4dc340cdaaa257ba1086191d_signed.pdf
    # poetry run pyhanko sign validate --trust ../../cert.pem --pretty-print pdf_path
    pass
