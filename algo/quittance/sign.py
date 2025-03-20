from pyhanko.sign.fields import append_signature_field, SigFieldSpec
from pyhanko.sign.signers import SimpleSigner, sign_pdf
from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader

def sign_pdf_with_pfx(input_pdf_path, output_pdf_path, pfx_path, pfx_password):
    # Charger le signataire à partir du certificat PFX
    signer = SimpleSigner.load_pkcs12(
        pfx_path,
        pfx_password.encode()
    )

    # Lire le PDF d'entrée
    with open(input_pdf_path, 'rb') as input_pdf:
        reader = PdfFileReader(input_pdf)
        writer = IncrementalPdfFileWriter(reader)

        # Ajouter un champ de signature
        append_signature_field(
            writer,
            sig_field_spec=SigFieldSpec(sig_field_name="Signature1")
        )

        # Écrire les modifications dans le fichier de sortie
        with open(output_pdf_path, 'wb') as output_pdf:
            writer.write(output_pdf)

    # Signer le PDF
    with open(output_pdf_path, 'rb+') as pdf_to_sign:
        sign_pdf(
            pdf_to_sign,
            signature_meta=PdfSignatureMetadata(field_name="Signature1"),
            signer=signer
        )






from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.sign.fields import enumerate_sig_fields

def validate_signature(signed_pdf):
    with open(signed_pdf, 'rb') as doc:
        # Vérifie toutes les signatures présentes
        sig_fields = enumerate_sig_fields(doc)
        for sig in sig_fields:
            status = validate_pdf_signature(doc, sig_field_name=sig)
            print(f"Signature sur {sig}: {status.summary()}")
            
# Exemple d'utilisation
# sign_pdf_with_pfx(
#     "quittance_loyer.pdf",                  # PDF source
#     "quittance_loyer_signed.pdf",          # PDF signé
#     "cert.pfx",                             # Certificat PFX
#     "hestia"                                 # Mot de passe du certificat
# )
validate_signature("output.pdf")

# openssl req -x509 -newkey rsa:2048 -keyout private.key -out cert.pem -days 365 -nodes -subj "/C=FR/ST=France/L=Arras/O=HBConsulting/emailAddress=nicolas3269@gmail.com" -addext "keyUsage=digitalSignature,nonRepudiation,keyEncipherment,dataEncipherment"
# openssl pkcs12 -export -out cert.pfx -inkey private.key -in cert.pem -certfile cert.pem -passout pass:hestia
poetry run pyhanko sign addfields --field 1/425,20,575,70/Signature1 quittance_loyer.pdf quittance_loyer_with_field.pdf
# poetry run pyhanko sign addsig --field Signature1 pkcs12 quittance_loyer_with_field.pdf output.pdf cert.pfx
poetry run pyhanko sign addfields --field 1/425,20,575,70/Landlord quittance_loyer.pdf quittance_loyer_with_field.pdf
poetry run pyhanko sign addfields --field 1/125,20,275,70/Tenant1 quittance_loyer_with_field.pdf quittance_loyer_with_field_2.pdf
poetry run pyhanko --config pyhanko.yml sign addsig --style-name landlord --field Landlord pkcs12 quittance_loyer_with_field_2.pdf quittance_loyer_signed_1.pdf cert.pfx
poetry run pyhanko --config pyhanko.yml sign addsig --style-name tenant --field Tenant1 pkcs12 quittance_loyer_signed_1.pdf output.pdf cert.pfx


### poetry run pyhanko sign validate --pretty-print output.pdf -> invalid
### poetry run pyhanko sign validate --trust cert.pem --pretty-print output.pdf -> valid

# et utiliser la signature manuscrite:
# npm install react-signature-canvas