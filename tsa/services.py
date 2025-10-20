"""
Services TSA internes pour génération de timestamps RFC 3161.

Ce module expose la logique métier TSA qui peut être appelée directement
depuis le code Python, sans passer par des appels HTTP.

Usage:
    from tsa.services import generate_timestamp_token, InternalTimeStamper

    # Appel direct
    tsa_response_bytes = generate_timestamp_token(tsa_request_bytes)

    # Avec PyHanko
    timestamper = InternalTimeStamper()
    # timestamper peut être passé à PdfSigner
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from django.conf import settings
from pyhanko.sign import timestamps

from .models import TsaSerial

logger = logging.getLogger(__name__)


class TsaError(Exception):
    """Exception levée en cas d'erreur TSA."""
    pass


def generate_timestamp_token(tsa_request_data: bytes) -> bytes:
    """
    Génère un token d'horodatage TSA conforme RFC 3161.

    Cette fonction est la logique métier du TSA, extraite du view HTTP
    pour permettre des appels directs depuis le code Python.

    Args:
        tsa_request_data: Requête TSA binaire (TimeStampReq)

    Returns:
        bytes: Réponse TSA binaire (TimeStampResp)

    Raises:
        TsaError: Si la génération échoue
        ValueError: Si la requête est invalide

    Example:
        >>> from tsa.services import generate_timestamp_token
        >>> tsa_response = generate_timestamp_token(tsq_bytes)
        >>> # tsa_response contient le token RFC 3161

    Note:
        - Utilise OpenSSL pour générer le token
        - Numéro de série généré atomiquement via PostgreSQL
        - Fichiers temporaires nettoyés automatiquement
        - Thread-safe (chaque appel a ses propres fichiers temp)
    """
    if not tsa_request_data:
        raise ValueError("Empty TSA request")

    logger.info("🔐 Génération token TSA (appel interne)")

    # Chemins des certificats TSA depuis settings
    tsa_cert_path = settings.TSA_CERT_PATH
    tsa_key_path = settings.TSA_KEY_PATH
    tsa_password = settings.PASSWORD_CERT_TSA

    # Chemin du template de configuration TSA
    cert_dir = Path(tsa_cert_path).parent
    tsa_config_template = cert_dir / "hestia_tsa.cnf"

    # Vérifier que les certificats existent
    if not Path(tsa_cert_path).exists():
        raise TsaError(
            f"TSA certificate not found: {tsa_cert_path}. "
            "Run setup script first."
        )

    if not Path(tsa_key_path).exists():
        raise TsaError(
            f"TSA private key not found: {tsa_key_path}. "
            "Run setup script first."
        )

    if not tsa_config_template.exists():
        raise TsaError(f"TSA configuration template not found: {tsa_config_template}")

    # Générer le prochain numéro de série de manière atomique (PostgreSQL)
    try:
        next_serial = TsaSerial.get_next_serial()
        logger.info(f"📝 Serial TSA généré : {next_serial} (hex: {next_serial:02X})")
    except Exception as e:
        raise TsaError(f"Failed to generate TSA serial: {str(e)}")

    # Créer le fichier serial AVANT le context manager
    # pour qu'il soit complètement fermé quand OpenSSL l'ouvre
    serial_fd, serial_file_path = tempfile.mkstemp(suffix='.txt', text=True)
    try:
        # Écrire le serial en hexadécimal (minimum 2 chiffres)
        # OpenSSL exige au moins 2 chiffres hex (format ASN.1 INTEGER)
        serial_hex = f"{next_serial:02X}\n"
        os.write(serial_fd, serial_hex.encode())
    finally:
        os.close(serial_fd)  # Fermer complètement le file descriptor

    # Créer les autres fichiers temporaires
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.tsq', delete=False) as req_file, \
         tempfile.NamedTemporaryFile(mode='rb', suffix='.tsr', delete=False) as resp_file, \
         tempfile.NamedTemporaryFile(mode='w', suffix='.cnf', delete=False) as config_file:

        req_file_path = req_file.name
        resp_file_path = resp_file.name
        config_file_path = config_file.name

        # Écrire la requête TSA
        req_file.write(tsa_request_data)
        req_file.flush()

        # Lire le template de configuration TSA
        with open(tsa_config_template, 'r') as template:
            config_content = template.read()

        # Remplacer les placeholders par les chemins réels
        # 1. Serial file (temporaire, unique par requête)
        config_content = config_content.replace(
            "serial = /app/certificates/hestia_tsa_serial.txt",
            f"serial = {serial_file_path}"
        )

        # 2. Certificat TSA (depuis settings.TSA_CERT_PATH)
        config_content = config_content.replace(
            "certs = /app/certificates/hestia_tsa.pem",
            f"certs = {tsa_cert_path}"
        )

        # Écrire la config temporaire
        config_file.write(config_content)
        config_file.flush()

        try:
            # Appeler openssl ts pour générer la réponse
            cmd = [
                "openssl", "ts", "-reply",
                "-config", config_file_path,
                "-queryfile", req_file_path,
                "-out", resp_file_path,
                "-inkey", tsa_key_path,
                "-signer", tsa_cert_path,
                "-passin", f"pass:{tsa_password}",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                # Erreur OpenSSL
                error_msg = result.stderr or result.stdout or "Unknown OpenSSL error"
                raise TsaError(f"OpenSSL TSA signing failed: {error_msg}")

            # Lire la réponse TSA
            with open(resp_file_path, 'rb') as f:
                tsa_response_data = f.read()

            logger.info(f"✅ Token TSA généré : {len(tsa_response_data)} bytes")
            return tsa_response_data

        except subprocess.TimeoutExpired:
            raise TsaError("TSA request timeout")

        except Exception as e:
            raise TsaError(f"TSA internal error: {str(e)}")

        finally:
            # Nettoyer tous les fichiers temporaires
            Path(req_file_path).unlink(missing_ok=True)
            Path(resp_file_path).unlink(missing_ok=True)
            Path(serial_file_path).unlink(missing_ok=True)
            Path(config_file_path).unlink(missing_ok=True)


class InternalTimeStamper(timestamps.TimeStamper):
    """
    TimeStamper PyHanko qui appelle directement le service TSA interne.

    Cette classe remplace HTTPTimeStamper pour éviter les appels HTTP
    en auto-référence (deadlock, overhead réseau).

    Usage avec PyHanko:
        timestamper = InternalTimeStamper()
        pdf_signer = signers.PdfSigner(
            signature_meta=signature_meta,
            signer=signer,
            timestamper=timestamper  # Utilise TSA interne
        )

    Note:
        - Compatible avec PdfSigner et PdfTimeStamper de PyHanko
        - Même interface que HTTPTimeStamper (duck typing)
        - Zéro overhead réseau (appel Python direct)
        - Thread-safe (via PostgreSQL serial atomique)
    """

    async def async_request_tsa_response(self, req):
        """
        Génère une réponse TSA pour une requête donnée.

        Cette méthode implémente l'interface TimeStamper de PyHanko.

        Args:
            req: TimeStampReq (asn1crypto.tsp.TimeStampReq)

        Returns:
            TimeStampResp: Réponse TSA (asn1crypto.tsp.TimeStampResp)

        Raises:
            TsaError: Si la génération du timestamp échoue
        """
        from asn1crypto import tsp
        from pyhanko_certvalidator._asyncio_compat import to_thread

        logger.info("🔐 Génération timestamp TSA (appel interne)")

        # Sérialiser la requête TSA (format DER/ASN.1)
        tsa_request_bytes = req.dump()

        # Wrapper pour exécuter dans un thread (accès DB Django)
        def generate_in_thread():
            try:
                tsa_response_bytes = generate_timestamp_token(tsa_request_bytes)
                # Parser la réponse pour retourner un objet TimeStampResp
                return tsp.TimeStampResp.load(tsa_response_bytes)
            except TsaError:
                raise
            except Exception as e:
                raise TsaError(f"Unexpected error: {str(e)}")

        # Exécuter dans un thread pour éviter le conflit async/sync Django
        try:
            tsa_response = await to_thread(generate_in_thread)
            logger.info("✅ Timestamp TSA généré avec succès (appel interne)")
            return tsa_response

        except TsaError as e:
            logger.error(f"❌ Erreur génération timestamp TSA : {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Erreur inattendue timestamp TSA : {e}")
            raise TsaError(f"Unexpected error: {str(e)}")
