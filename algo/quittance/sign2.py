import datetime
import os

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, append_signature_field
from weasyprint import HTML

# Données dynamiques pour le bail
data = {
    "landlord": {
        "name": "Jean Dupont",
        "location": "Arras, France",
        "signature_image": "landlord_signature.png",
        "cert": "cert.pem",
        "key": "private.key",
        "pfx": "cert.pfx",
        "password": os.getenv("KEY_PASSWORD"),
    },
    "tenant": {
        "name": "Marie Durand",
        "location": "Paris, France",
        "signature_image": "tenant_signature.png",
        "cert": "cert.pem",
        "key": "private.key",
        "pfx": "cert.pfx",
        "password": os.getenv("KEY_PASSWORD"),
    },
    "contract_details": {
        "date": datetime.date.today().strftime("%d/%m/%Y"),
        "address": "12 rue des Lilas, Arras, France",
        "rent": "750 €",
        "charges": "50 €",
    },
}


# Étape 1 : Générer le PDF avec WeasyPrint
def generate_pdf_with_weasyprint(output_file, data):
    html = f'''
    <html>
    <body>
        <h1>Bail de location</h1>
        <p>Date : {data["contract_details"]["date"]}</p>
        <p>Adresse : {data["contract_details"]["address"]}</p>
        <p>Loyer : {data["contract_details"]["rent"]} + Charges : {data["contract_details"]["charges"]}</p>

        <h2>Signatures :</h2>
        <p>Propriétaire : {data["landlord"]["name"]}</p>
        <div style="text-align: right;">
            <img src="{data["landlord"]["signature_image"]}" width="150px"/>
        </div>
        <p>Locataire : {data["tenant"]["name"]}</p>
        <div style="text-align: right;">
            <img src="{data["tenant"]["signature_image"]}" width="150px"/>
        </div>
    </body>
    </html>
    '''
    HTML(string=html).write_pdf(output_file)


# Étape 2 : Ajouter un champ de signature
def add_signature_fields(input_file, output_file):
    with open(input_file, "rb+") as doc:
        w = IncrementalPdfFileWriter(doc)
        append_signature_field(
            w, SigFieldSpec(sig_field_name="Landlord", box=(425, 20, 575, 70))
        )
        append_signature_field(
            w, SigFieldSpec(sig_field_name="Tenant", box=(125, 20, 275, 70))
        )
        w.write_in_place()


# Étape 3 : Appliquer une signature électronique
def sign_pdf(input_file, output_file, signer_data, field_name):
    # Charger les certificats et clés
    signer = signers.SimpleSigner.load_pkcs12(
        signer_data["pfx"], signer_data["password"].encode()
    )

    # Appliquer la signature électronique
    with open(input_file, "rb+") as doc:
        signers.sign_pdf(
            doc,
            signature_meta=signers.PdfSignatureMetadata(
                field_name=field_name,
                reason="Signature du bail",
                location=signer_data["location"],
                signer_name=signer_data["name"],
            ),
            signer=signer,
        )


# Générer le PDF initial
generate_pdf_with_weasyprint("bail_initial.pdf", data)

# Ajouter les champs de signature
add_signature_fields("bail_initial.pdf", "bail_with_fields.pdf")

# Signature du propriétaire
sign_pdf("bail_initial.pdf", "bail_signed_landlord.pdf", data["landlord"], "Landlord")

# Signature du locataire
sign_pdf("bail_signed_landlord.pdf", "bail_final_signed.pdf", data["tenant"], "Tenant")

print("Bail signé avec succès par les deux parties !")
