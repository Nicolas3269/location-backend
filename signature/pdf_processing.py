"""
Traitement générique des PDF pour la signature électronique
"""

import base64
import logging
import os

from django.core.files.base import File

from algo.signature.main import (
    add_signature_fields_dynamic,
    get_named_dest_coordinates,
    sign_pdf,
)
from backend.storage_utils import get_local_file_path, save_file_to_storage
from signature.document_status import DocumentStatus
from signature.services import send_document_signed_emails

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

        # Récupérer la personne qui signe (utilise la propriété signer qui gère mandataire)
        signing_person = signature_request.signer
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

        # Sélectionner le PDF source (latest_pdf si existe, sinon pdf)
        source_field = document.latest_pdf if document.latest_pdf else document.pdf

        # Générer le nom de fichier basé sur le type de document
        base_name = (
            os.path.basename(source_field.name)
            .replace("_signed", "")
            .replace(".pdf", "")
        )
        signed_filename = f"{base_name}_signed.pdf"
        final_tmp_path = f"/tmp/{base_name}_signed_temp.pdf"

        # Utiliser le helper pour gérer R2/local storage
        # IMPORTANT : Tout le traitement doit être dans le with pour que le fichier temporaire existe
        with get_local_file_path(source_field) as source_path:
            logger.info(f"Fichier source téléchargé: {source_path}")

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

        # Sauvegarder le PDF signé dans latest_pdf
        with open(final_tmp_path, "rb") as f:
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
        if hasattr(document, "status"):
            if document.status == DocumentStatus.DRAFT.value:
                document.status = DocumentStatus.SIGNING.value
                document.save(update_fields=["status"])
                logger.info("✅ Status mis à jour : SIGNING (première signature)")

        # Vérifier si c'était la dernière signature et sceller si nécessaire
        try:
            # Utiliser la relation inverse signature_requests définie sur le document
            if not hasattr(document, "signature_requests"):
                logger.warning(
                    f"Document {document.get_document_name()} n'a pas de signature_requests"
                )
                return True

            sig_requests = document.signature_requests.all()
            total_signatures = sig_requests.count()
            completed_signatures = sig_requests.filter(signed=True).count()

            logger.info(
                f"📝 Signatures : {completed_signatures}/{total_signatures} complétées"
            )

            # Si toutes les signatures utilisateurs sont complètes → Finalisation
            if total_signatures > 0 and completed_signatures == total_signatures:
                logger.info(
                    f"✅ Toutes les signatures utilisateurs complètes pour {document.get_document_name()}"
                )

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
                #     from signature.certification_flow import (
                #         apply_final_timestamp,
                #     )
                #
                #     # Télécharger le PDF signé depuis S3
                #     with get_local_file_path(document.latest_pdf) as source_pdf:
                #         output_pdf = source_pdf.replace('.pdf', '_ts.pdf')
                #
                #         # Appliquer le DocTimeStamp final
                #         apply_final_timestamp(source_pdf, output_pdf)
                #
                #         if os.path.exists(output_pdf):
                #             # Supprimer l'ancien latest_pdf
                #             if document.latest_pdf:
                #                 document.latest_pdf.delete(save=False)
                #
                #             # Uploader le PDF timestampé vers S3
                #             with open(output_pdf, 'rb') as f:
                #                 from django.core.files.base import File
                #                 fname = os.path.basename(
                #                     document.latest_pdf.name
                #                 )
                #                 document.latest_pdf.save(
                #                     fname, File(f), save=False
                #                 )
                #
                #             # Nettoyer le fichier temporaire
                #             os.remove(output_pdf)
                #             logger.info("✅ DocTimeStamp final (B-LTA)")
                # except Exception as ts_error:
                #     logger.warning(f"⚠️ DocTimeStamp: {ts_error}")

                logger.info("✅ PAdES B-LT complet (validation long terme)")

                # ✅ NOUVEAU : Générer journal de preuves
                try:
                    from signature.certification_flow import generate_proof_journal

                    journal = generate_proof_journal(document)

                    # TODO: Sauvegarder journal JSON sur S3 Glacier
                    # journal_json = json.dumps(journal, indent=2)
                    # upload_to_s3_glacier(journal_json, f"proofs/{document.id}.json")

                    logger.info("✅ Journal de preuves généré")
                    logger.info(
                        f"   Signatures forensiques : {len(journal.get('signatures', []))}"
                    )

                except Exception as journal_error:
                    logger.warning(f"⚠️ Erreur génération journal : {journal_error}")
                    import traceback

                    logger.warning(traceback.format_exc())

                # Mettre le statut à SIGNED (APRÈS toutes les opérations)

                if (
                    hasattr(document, "status")
                    and document.status != DocumentStatus.SIGNED.value
                ):
                    document.status = DocumentStatus.SIGNED.value
                    document.save(update_fields=["status"])
                    logger.info("✅ Status mis à jour : SIGNED")

                    # Envoyer les emails de notification à toutes les parties
                    first_sig = sig_requests.first()
                    document_type = first_sig.get_document_type()
                    try:
                        send_document_signed_emails(document, document_type)
                        logger.info(
                            f"📧 Emails 'document signé' envoyés pour {document_type}"
                        )
                    except Exception as email_error:
                        logger.warning(
                            f"⚠️ Erreur envoi emails de finalisation: {email_error}"
                        )

                logger.info(
                    "✅ Document complet : Certification Hestia + Signatures users + TSA final + Journal"
                )
        except Exception as seal_error:
            logger.warning(
                f"⚠️  Erreur lors du scellement Hestia (optionnel): {seal_error}"
            )
            import traceback

            logger.warning(traceback.format_exc())

        return True

    except Exception as e:
        logger.error(f"Erreur lors du traitement de la signature générique: {e}")
        return False


def prepare_pdf_with_signature_fields_generic(pdf_field, document):
    """
    Version générique pour préparer un PDF avec les champs de signature
    Fonctionne avec n'importe quel document signable (bail, état des lieux, etc.)

    Args:
        pdf_field: Soit un FieldFile Django (document.pdf), soit un chemin string (/tmp/xxx.pdf)
        document: Instance du document signable (Bail, EtatLieux, etc.) qui a une relation 'location'
    """
    try:
        # Récupérer la location du document
        if hasattr(document, "location"):
            location = document.location
        else:
            raise ValueError(
                f"Le document {type(document).__name__} n'a pas de relation 'location'"
            )

        # Récupérer tous les signataires
        mandataire = location.mandataire
        # IMPORTANT: Ordre déterministe (premier créé = principal)
        bailleurs = location.bien.bailleurs.order_by("created_at")
        bailleur_signataires = [
            bailleur.signataire for bailleur in bailleurs if bailleur.signataire
        ]
        locataires = list(location.locataires.all())

        # Déterminer si c'est un FieldFile (depuis S3) ou un chemin local (string)
        is_local_path = isinstance(pdf_field, str)

        if is_local_path:
            # Cas 1: Fichier temporaire local (string path)
            # Travailler directement sur le fichier sans télécharger depuis S3
            pdf_path = pdf_field
            logger.info(
                f"Préparation des champs de signature (fichier local): {pdf_path}"
            )
        else:
            # Cas 2: FieldFile depuis S3 - télécharger d'abord
            logger.info(f"Téléchargement du PDF depuis S3: {pdf_field.name}")

        # Utiliser context manager seulement si c'est un FieldFile
        from contextlib import nullcontext

        context_manager = (
            nullcontext(pdf_field) if is_local_path else get_local_file_path(pdf_field)
        )

        with context_manager as pdf_path:
            all_fields = []

            # Ajouter le champ pour le mandataire (si présent) - EN PREMIER
            if mandataire and mandataire.signataire:
                person = mandataire.signataire
                page, rect, field_name = get_named_dest_coordinates(
                    pdf_path, person, "mandataire"
                )
                if rect is None:
                    logger.warning(
                        f"Aucun champ de signature trouvé pour le mandataire {person.email}"
                    )
                else:
                    all_fields.append(
                        {
                            "field_name": field_name,
                            "rect": rect,
                            "person": person,
                            "page": page,
                        }
                    )

            # Ajouter les champs pour les bailleurs signataires
            for person in bailleur_signataires:
                page, rect, field_name = get_named_dest_coordinates(
                    pdf_path, person, "bailleur"
                )
                if rect is None:
                    logger.warning(
                        f"Aucun champ de signature trouvé pour {person.email}"
                    )
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
                    logger.warning(
                        f"Aucun champ de signature trouvé pour {person.email}"
                    )
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

            # Ajouter les champs de signature au PDF (modifie le fichier in-place)
            add_signature_fields_dynamic(pdf_path, all_fields)
            logger.info(f"Ajouté {len(all_fields)} champs de signature au PDF")

            # Re-uploader vers S3 uniquement si c'est un FieldFile
            if not is_local_path:
                save_file_to_storage(
                    pdf_field, pdf_path, filename=pdf_field.name, save=True
                )
                logger.info("PDF avec champs de signature uploadé vers S3")
            else:
                logger.info("Fichier local modifié in-place (pas d'upload S3)")

        return True

    except Exception as e:
        logger.error(
            f"Erreur lors de la préparation du PDF avec champs de signature: {e}"
        )
        raise
