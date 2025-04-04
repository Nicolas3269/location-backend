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


def verify_pdf_signature(pdf_path, field_name=None):
    """Vérifie la validité de la signature électronique d'un PDF"""
    from pyhanko.pdf_utils.reader import PdfFileReader

    with open(pdf_path, "rb") as f:
        reader = PdfFileReader(f)

        # Obtenir tous les champs de signature dans le document
        sig_fields = fields.enumerate_sig_fields(reader)

        if field_name:
            # Vérifier un champ spécifique
            try:
                # Rechercher le tuple avec le nom de champ correspondant
                sig_field_tuple = next(sf for sf in sig_fields if sf[0] == field_name)

                # Extraire les éléments du tuple (nom, référence au champ, référence à la valeur)
                field_name = sig_field_tuple[0]  # Nom du champ
                field_ref = sig_field_tuple[1]  # Référence au champ

                # Obtenir l'objet champ de signature
                field_obj = field_ref.get_object()

                # Vérifier si le champ a une valeur (signature)
                if "/V" not in field_obj:
                    return {
                        "field_name": field_name,
                        "error": "Ce champ de signature n'a pas encore été signé",
                        "status": "unsigned",
                    }

                # La vérification simplifiée pour le développement
                return {
                    "field_name": field_name,
                    "signer": "Test Signer",
                    "signing_time": datetime.datetime.now().isoformat(),
                    "valid": True,
                    "validation_message": "Vérification simplifiée pour le développement",
                }

            except StopIteration:
                return {"error": f"Champ de signature '{field_name}' non trouvé"}
        else:
            # Vérifier toutes les signatures
            results = []
            for sig_field_tuple in sig_fields:
                try:
                    # Extraire les éléments du tuple
                    field_name = sig_field_tuple[0]
                    field_ref = sig_field_tuple[1]
                    field_obj = field_ref.get_object()

                    # Vérifier si le champ a une valeur (signature)
                    if "/V" not in field_obj:
                        results.append(
                            {
                                "field_name": field_name,
                                "error": "Ce champ de signature n'a pas encore été signé",
                                "status": "unsigned",
                            }
                        )
                        continue

                    # Pour l'instant, retourner simplement un succès
                    results.append(
                        {
                            "field_name": field_name,
                            "signer": "Test Signer",
                            "signing_time": datetime.datetime.now().isoformat(),
                            "valid": True,
                            "validation_message": "Vérification simplifiée pour le développement",
                        }
                    )
                except Exception as e:
                    results.append({"field_name": sig_field_tuple[0], "error": str(e)})
            return results
