import datetime
import os

from django.conf import settings
from pyhanko import stamp
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.fields import SigFieldSpec, append_signature_field


def add_signature_fields(pdf_path):
    """Ajoute des champs de signature au PDF pour le propriétaire et le locataire"""
    with open(pdf_path, "rb+") as doc:
        w = IncrementalPdfFileWriter(doc)
        append_signature_field(
            w, SigFieldSpec(sig_field_name="Landlord", box=(425, 20, 575, 70))
        )
        w.write_in_place()
        append_signature_field(
            w, SigFieldSpec(sig_field_name="Tenant", box=(125, 20, 275, 70))
        )
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
        timestamp_field_name=str(datetime.datetime.now()),
    )

    # Créer une apparence personnalisée pour la signature
    signature_appearance = stamp.TextStampStyle(
        stamp_text=f"Signé électroniquement par:\n"
        f"{getattr(user, 'prenom', '')} {getattr(user, 'nom', '')}\n"
        f"Date: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
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
            )

            # Lire le PDF source avec PdfFileReader
            reader = PdfFileReader(inf)

            # Créer un IncrementalPdfFileWriter
            writer = IncrementalPdfFileWriter(inf)

            # Signer le PDF et écrire dans le fichier de sortie
            pdf_signer.sign_pdf(
                writer,
                output=outf,
                existing_fields_only=True,  # Utiliser uniquement les champs existants
            )

    return output_path


# La fonction verify_pdf_signature reste inchangée


def verify_pdf_signature(pdf_path, field_name=None):
    """Vérifie la validité de la signature électronique d'un PDF"""
    from pyhanko.sign import validation

    with open(pdf_path, "rb") as f:
        reader = PdfFileReader(f)

        # Obtenir tous les champs de signature dans le document
        sig_fields = fields.enumerate_sig_fields(reader)

        if field_name:
            # Vérifier un champ spécifique
            try:
                sig_field = next(sf for sf in sig_fields if sf.name == field_name)
                status = validation.read_certification_status(reader)
                result = validation.validate_pdf_signature(
                    reader=reader,
                    sig_field=sig_field,
                    signer_validation_context=validation.SimpleDocumentSecurityStore(),
                )
                return {
                    "field_name": field_name,
                    "signer": result.signer_reported_name,
                    "signing_time": result.signing_time,
                    "valid": result.trusted,
                    "validation_message": result.pretty_print_details(),
                }
            except StopIteration:
                return {"error": f"Champ de signature '{field_name}' non trouvé"}
        else:
            # Vérifier toutes les signatures
            results = []
            for sig_field in sig_fields:
                try:
                    result = validation.validate_pdf_signature(
                        reader=reader,
                        sig_field=sig_field,
                        signer_validation_context=validation.SimpleDocumentSecurityStore(),
                    )
                    results.append(
                        {
                            "field_name": sig_field.name,
                            "signer": result.signer_reported_name,
                            "signing_time": result.signing_time,
                            "valid": result.trusted,
                            "validation_message": result.pretty_print_details(),
                        }
                    )
                except Exception as e:
                    results.append({"field_name": sig_field.name, "error": str(e)})
            return results
