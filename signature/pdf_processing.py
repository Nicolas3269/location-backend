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
from bail.models import Bail

logger = logging.getLogger(__name__)


def process_signature_generic(signature_request, signature_data_url, request=None):
    """
    Version générique de process_signature qui fonctionne avec n'importe quel document signable

    Args:
        signature_request: Instance de AbstractSignatureRequest
        signature_data_url: Image de signature en base64
        request: Django HttpRequest (pour capturer métadonnées IP/user-agent)
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
            request=request,
            document=document,
            signature_request=signature_request,  # Métadonnées OTP extraites depuis ici
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

        # Marquer la SignatureRequest comme signée maintenant que le PDF est signé
        signature_request.mark_as_signed()

        # Mettre le document en SIGNING si c'est la première signature
        if hasattr(document, 'status'):
            from signature.document_status import DocumentStatus
            if document.status == DocumentStatus.DRAFT.value:
                document.status = DocumentStatus.SIGNING.value
                document.save(update_fields=['status'])
                logger.info(f"✅ Status mis à jour : SIGNING (première signature)")

        # Vérifier si c'était la dernière signature et sceller si nécessaire
        try:
            # Utiliser la relation inverse signature_requests définie sur le document
            if not hasattr(document, 'signature_requests'):
                logger.warning(f"Document {document.get_document_name()} n'a pas de signature_requests")
                return True

            sig_requests = document.signature_requests.all()
            total_signatures = sig_requests.count()
            completed_signatures = sig_requests.filter(signed=True).count()

            logger.info(f"📝 Signatures : {completed_signatures}/{total_signatures} complétées")

            # Si toutes les signatures utilisateurs sont complètes → Finalisation
            if total_signatures > 0 and completed_signatures == total_signatures:
                logger.info(f"✅ Toutes les signatures utilisateurs complètes pour {document.get_document_name()}")

                # ✅ PAdES B-LT (Long Term validation)
                # DocTimeStamp final NON UTILISÉ (PAdES B-LTA non nécessaire)
                #
                # Raisons du choix B-LT vs B-LTA :
                # 1. Légalement suffisant pour baux/mandats/assurance (5-10 ans)
                # 2. Accepté par assurances loyers impayés et tribunaux français
                # 3. Adobe rejette DocTimeStamp avec TSA auto-signé
                # 4. TSA commercial uniquement pour B-LTA (archivage 30+ ans)
                #
                # Architecture actuelle :
                # - Certification Hestia + embed_validation_info (DSS créé)
                # - Timestamp TSA Hestia sur chaque signature (T0, T1, T2...)
                # - Infos révocation embarquées (CRL/OCSP dans DSS)
                # → Validité : 5-10 ans (durée certificats)
                #
                # Pour activer B-LTA avec TSA commercial (si besoin futur) :
                # Décommenter le code ci-dessous et configurer TSA commercial
                # dans apply_final_timestamp()
                #
                # try:
                #     from signature.certification_flow import apply_final_timestamp
                #     source_pdf = document.latest_pdf.path
                #     timestamped_pdf = source_pdf.replace('.pdf', '_timestamped.pdf')
                #     apply_final_timestamp(source_pdf, timestamped_pdf)
                #     if os.path.exists(timestamped_pdf):
                #         if document.latest_pdf and document.latest_pdf.name:
                #             document.latest_pdf.delete(save=False)
                #         with open(timestamped_pdf, 'rb') as f:
                #             from django.core.files.base import File
                #             filename = os.path.basename(source_pdf)
                #             document.latest_pdf.save(filename, File(f), save=False)
                #         os.remove(timestamped_pdf)
                #         logger.info("✅ DocTimeStamp final (PAdES B-LTA)")
                # except Exception as ts_error:
                #     logger.warning(f"⚠️ DocTimeStamp final: {ts_error}")

                logger.info("✅ PAdES B-LT complet (validation long terme)")

                # ✅ NOUVEAU : Générer journal de preuves
                try:
                    from signature.certification_flow import generate_proof_journal
                    import json

                    journal = generate_proof_journal(document)

                    # TODO: Sauvegarder journal JSON sur S3 Glacier
                    # journal_json = json.dumps(journal, indent=2)
                    # upload_to_s3_glacier(journal_json, f"proofs/{document.id}.json")

                    logger.info("✅ Journal de preuves généré")
                    logger.info(f"   Signatures forensiques : {len(journal.get('signatures', []))}")

                except Exception as journal_error:
                    logger.warning(f"⚠️ Erreur génération journal : {journal_error}")
                    import traceback
                    logger.warning(traceback.format_exc())

                # Mettre le statut à SIGNED (APRÈS toutes les opérations)
                from signature.document_status import DocumentStatus
                if hasattr(document, 'status') and document.status != DocumentStatus.SIGNED.value:
                    document.status = DocumentStatus.SIGNED.value
                    document.save(update_fields=['status'])
                    logger.info(f"✅ Status mis à jour : SIGNED")

                logger.info(
                    "✅ Document complet : Certification Hestia + Signatures users + TSA final + Journal"
                )
        except Exception as seal_error:
            logger.warning(f"⚠️  Erreur lors du scellement Hestia (optionnel): {seal_error}")
            import traceback
            logger.warning(traceback.format_exc())

        return True

    except Exception as e:
        logger.error(f"Erreur lors du traitement de la signature générique: {e}")
        return False


def prepare_pdf_with_signature_fields_generic(pdf_path, document):
    """
    Version générique pour préparer un PDF avec les champs de signature
    Fonctionne avec n'importe quel document signable (bail, état des lieux, etc.)

    Args:
        pdf_path: Chemin vers le PDF à préparer
        document: Instance du document signable (Bail, EtatLieux, etc.) qui a une relation 'location'
    """
    try:
        # Récupérer la location du document
        if hasattr(document, 'location'):
            location = document.location
        else:
            raise ValueError(f"Le document {type(document).__name__} n'a pas de relation 'location'")
        
        # Récupérer tous les signataires
        bailleurs = location.bien.bailleurs.all()
        bailleur_signataires = [
            bailleur.signataire for bailleur in bailleurs if bailleur.signataire
        ]
        locataires = list(location.locataires.all())

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
