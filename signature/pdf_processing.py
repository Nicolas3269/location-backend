"""
Traitement générique des PDF pour la signature électronique
"""

import base64
import logging
import os

from algo.signature.main import (
    add_signature_fields_dynamic,
    get_named_dest_coordinates,
    sign_pdf,
)
from bail.models import BailSpecificites

logger = logging.getLogger(__name__)


def process_signature_generic(signature_request, signature_data_url):
    """
    Version générique de process_signature qui fonctionne avec n'importe quel document signable

    Args:
        signature_request: Instance de AbstractSignatureRequest
        signature_data_url: Image de signature en base64
    """
    try:
        # Récupérer le document signable
        document = signature_request.get_document()
        logger.info(f"Document récupéré: {type(document).__name__} - {document}")

        # Vérifier que le document implémente l'interface
        if not hasattr(document, "get_signature_field_name"):
            logger.error(
                f"Le document {type(document)} n'implémente pas l'interface SignableDocument"
            )
            return False

        # Récupérer la personne qui signe
        signing_person = (
            signature_request.bailleur_signataire or signature_request.locataire
        )
        logger.info(f"Personne qui signe: {signing_person}")

        # Vérifier que le document a un PDF
        if not document.pdf:
            logger.error(f"Le document {document} n'a pas de fichier PDF")
            return False

        # Décoder la signature
        signature_bytes = base64.b64decode(signature_data_url.split(",")[1])
        logger.info(f"Signature décodée: {len(signature_bytes)} bytes")

        # Obtenir le nom du champ de signature spécifique au document
        field_name = document.get_signature_field_name(signing_person)
        logger.info(f"Nom du champ de signature: {field_name}")

        # Chemin source : soit latest_pdf (s'il existe), soit le PDF d'origine
        source_path = (
            document.latest_pdf.path if document.latest_pdf else document.pdf.path
        )
        logger.info(f"Chemin source: {source_path}")

        # Vérifier que le fichier existe physiquement
        if not os.path.exists(source_path):
            logger.error(f"Le fichier PDF n'existe pas: {source_path}")
            logger.error("Le PDF doit être généré avant de pouvoir être signé.")
            logger.error(
                "Utilisez l'API generate-etat-lieux pour générer le PDF d'abord."
            )
            return False

        # Générer le nom de fichier basé sur le type de document
        base_name = (
            os.path.basename(source_path).replace("_signed", "").replace(".pdf", "")
        )
        final_tmp_path = f"/tmp/{base_name}_signed_temp.pdf"

        logger.info(
            f"Appel de sign_pdf avec: source={source_path}, output={final_tmp_path}, field={field_name}"
        )
        sign_pdf(
            source_path=source_path,
            output_path=final_tmp_path,
            user=signing_person,
            field_name=field_name,
            signature_bytes=signature_bytes,
        )
        logger.info("sign_pdf terminé avec succès")

        # Supprimer l'ancien fichier latest_pdf si existant
        if document.latest_pdf and document.latest_pdf.name:
            document.latest_pdf.delete(save=False)

        # Sauvegarder le PDF signé dans latest_pdf (même logique que les bails)
        with open(final_tmp_path, "rb") as f:
            from django.core.files.base import File

            signed_filename = f"{base_name}_signed.pdf"
            document.latest_pdf.save(signed_filename, File(f), save=True)

        # Vérifier que le fichier a été sauvegardé avant de nettoyer
        if document.latest_pdf and document.latest_pdf.name:
            # Nettoyer le fichier temporaire seulement si la sauvegarde a réussi
            try:
                os.remove(final_tmp_path)
                logger.info(f"Fichier temporaire supprimé: {final_tmp_path}")
            except OSError as e:
                logger.warning(
                    f"Impossible de supprimer le fichier temporaire {final_tmp_path}: {e}"
                )
        else:
            logger.error("Échec de la sauvegarde du PDF, fichier temporaire conservé")
            return False

        logger.info(f"PDF signé avec succès pour {document.get_document_name()}")
        return True

    except Exception as e:
        logger.error(f"Erreur lors du traitement de la signature générique: {e}")
        return False


def prepare_pdf_with_signature_fields_generic(pdf_path, bail: BailSpecificites):
    """
    Version générique pour préparer un PDF avec les champs de signature
    Fonctionne avec n'importe quel document signable (bail, état des lieux, etc.)

    Args:
        pdf_path: Chemin vers le PDF à préparer
        document: Instance du document signable (BailSpecificites, EtatLieux, etc.)
    """
    try:
        # Récupérer tous les signataires
        bailleurs = bail.bien.bailleurs.all()
        bailleur_signataires = [
            bailleur.signataire for bailleur in bailleurs if bailleur.signataire
        ]
        locataires = list(bail.locataires.all())

        all_fields = []

        # Ajouter les champs pour les bailleurs signataires
        for person in bailleur_signataires:
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
        for person in locataires:
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
        logger.info(f"Ajouté {len(all_fields)} champs de signature au PDF")

        return True

    except Exception as e:
        logger.error(
            f"Erreur lors de la préparation du PDF avec champs de signature: {e}"
        )
        raise
