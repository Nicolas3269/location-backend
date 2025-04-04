import datetime
import os

from django.conf import settings
from pyhanko import stamp
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, append_signature_field

# ####
# # Créer une clé privée et un certificat avec les extensions appropriées
# openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 3650 -nodes \
#   -subj "/CN=Test Signer/O=Test Organization/C=FR" \
#   -addext "keyUsage=digitalSignature,nonRepudiation,keyEncipherment" \
#   -addext "extendedKeyUsage=emailProtection,codeSigning"

# # Convertir en PKCS#12 pour l'utilisation avec PyHanko
# openssl pkcs12 -export -out cert.pfx -inkey key.pem -in cert.pem -name "Signing Key" -passout pass:test123


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
                box=(425, 20, 575, 70),  # Coordonnées (bas de page à droite)
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


def sign_pdf(source_path, output_path, user, field_name):
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

    # Apparence de la signature conforme aux documents légaux
    signature_appearance = stamp.TextStampStyle(
        stamp_text=(
            f"Signé électroniquement par:\n"
            f"{getattr(user, 'prenom', '')} {getattr(user, 'nom', '')}\n"
            f"Email: {getattr(user, 'email', '')}\n"
            f"Date: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"Rôle: {'Propriétaire' if field_name == 'Landlord' else 'Locataire'}\n"
            f"Signature conforme eIDAS"
        ),
        text_box_style=stamp.TextBoxStyle(font_size=9, border_width=1),
    )

    # Signer le document
    with open(source_path, "rb") as inf:
        with open(output_path, "wb") as outf:
            # Créer un PdfSigner avec les métadonnées et le style de signature
            pdf_signer = signers.PdfSigner(
                signature_meta=signature_meta,
                signer=signer,
                stamp_style=signature_appearance,
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
    # poetry run pyhanko sign validate --trust ../../cert.pem --pretty-print pdf_path
    pass
