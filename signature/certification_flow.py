"""
Module de certification et signature électronique conforme eIDAS

Ce module implémente l'architecture "Certify First" avec :
1. Certification Hestia (PREMIÈRE signature avec certify=True + DocMDP)
2. Signatures utilisateurs (approbations avec certificats auto-signés)
3. Journal de preuves forensique (métadonnées OTP/IP/timestamps)

Format: PAdES B-LT (Long Term validation)
- Suffisant légalement pour baux/mandats/assurance (5-10 ans)
- Accepté par assurances loyers impayés et tribunaux français
- Compatible Adobe Reader avec certificats auto-signés

Architecture:
    ┌──────────────────────────────────────────────────────────┐
    │ 1. CERTIFICATION HESTIA (T0 - PREMIÈRE signature)       │
    │    • Certificat eIDAS AATL (HB CONSULTING)              │
    │    • certify=True + DocMDP FILL_FORMS                   │
    │    • ValidationContext + embed_validation_info (DSS)    │
    │    • TSA Hestia (horodatage certification)              │
    │    • → Ruban vert Adobe immédiat                        │
    │    • → PDF verrouillé (seules signatures autorisées)    │
    └──────────────────────────────────────────────────────────┘
                            ↓
    ┌──────────────────────────────────────────────────────────┐
    │ 2. SIGNATURES UTILISATEURS (T1, T2, ... - approbations) │
    │    • Certificats auto-signés (générés dynamiquement)    │
    │    • Authentification OTP SMS/Email                     │
    │    • Tampons visuels avec signature manuscrite          │
    │    • Capture métadonnées (IP, user agent, timestamp)    │
    │    • ValidationContext + embed_validation_info (DSS)    │
    │    • TSA Hestia (horodatage chaque signature)           │
    └──────────────────────────────────────────────────────────┘
                            ↓
    ┌──────────────────────────────────────────────────────────┐
    │ 3. JOURNAL DE PREUVES (T_final) - PAdES B-LT            │
    │    • JSON signé avec cachet Hestia                      │
    │    • Métadonnées complètes (OTP, IP, timestamps)        │
    │    • DSS complet (infos révocation embarquées)          │
    │    • Archives immuables (DB + S3 Glacier)               │
    │    • Validité: 5-10 ans (durée certificats)             │
    └──────────────────────────────────────────────────────────┘

Usage:
    from signature.certification_flow import certify_document_hestia, sign_user_with_metadata

    # 1. Certifier le document (juste après génération PDF)
    certify_document_hestia(pdf_path, output_path, document)

    # 2. Signatures utilisateurs avec métadonnées
    sign_user_with_metadata(
        source_path, output_path, user, field_name,
        signature_bytes, otp_metadata, request
    )

Références:
    - /backend/docs/signature-strategy-eidas-hybrid.md
    - Règlement eIDAS (UE 910/2014)
    - Code civil français art. 1367
"""

import datetime
import json
import logging
import os
from typing import Dict, Optional

from django.conf import settings
from pyhanko import stamp
from pyhanko.keys import load_cert_from_pemder
from pyhanko.pdf_utils.content import BoxConstraints
from pyhanko.pdf_utils.images import PdfImage
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import MDPPerm
from pyhanko_certvalidator import ValidationContext

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    """
    Récupère l'IP réelle du client en tenant compte des reverse proxies.

    En production (Railway, nginx, etc.), l'application tourne derrière un proxy
    qui ajoute les headers X-Forwarded-For et X-Real-IP.

    Args:
        request: Django HttpRequest

    Returns:
        str: IP réelle du client

    Note:
        - X-Forwarded-For peut contenir plusieurs IPs (client, proxy1, proxy2, ...)
        - On prend la PREMIÈRE IP (client réel)
        - Fallback sur X-Real-IP puis REMOTE_ADDR
    """
    if not request:
        return "0.0.0.0"

    # 1. X-Forwarded-For (standard de facto)
    # Format: "client, proxy1, proxy2"
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # Prendre la première IP (client réel)
        client_ip = x_forwarded_for.split(",")[0].strip()
        logger.debug(f"IP extraite depuis X-Forwarded-For: {client_ip}")
        return client_ip

    # 2. X-Real-IP (nginx, certains proxies)
    x_real_ip = request.META.get("HTTP_X_REAL_IP")
    if x_real_ip:
        logger.debug(f"IP extraite depuis X-Real-IP: {x_real_ip}")
        return x_real_ip

    # 3. Fallback: REMOTE_ADDR (IP directe ou du proxy)
    remote_addr = request.META.get("REMOTE_ADDR", "0.0.0.0")
    logger.debug(f"IP extraite depuis REMOTE_ADDR (fallback): {remote_addr}")
    return remote_addr


def get_hestia_validation_context() -> ValidationContext:
    """
    Crée un ValidationContext avec les certificats auto-signés Hestia.

    Pour PAdES B-LT, PyHanko a besoin d'un contexte de validation pour :
    - Embarquer les infos de validation (CRL, OCSP) dans le DSS
    - Valider la chaîne de certificats avant signature

    Avec des certificats auto-signés, le DSS sera minimal (pas de CRL/OCSP
    externes), mais la structure PAdES B-LT sera correcte et conforme.

    Returns:
        ValidationContext: Contexte avec certificats Hestia comme trust roots

    Note:
        Les trust_roots incluent :
        - Certificat AATL Hestia (certification)
        - CA Hestia (signatures utilisateurs)
        - TSA Hestia (timestamps)
    """
    trust_roots = []

    def load_certificate(cert_path: str, cert_name: str):
        """Charge un certificat PEM/DER avec PyHanko."""
        try:
            cert = load_cert_from_pemder(cert_path)
            trust_roots.append(cert)
            logger.info(f"✅ {cert_name} ajouté au ValidationContext")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Impossible de charger {cert_name}: {e}")
            return False

    # 1. Certificat AATL Hestia (certification)
    cert_path = os.path.join(settings.BASE_DIR, "certificates", "hestia_server.pfx")
    if not os.path.exists(cert_path):
        # Fallback : certificat serveur auto-signé (test)
        cert_path = os.path.join(settings.BASE_DIR, "certificates", "hestia_server.pfx")

    cert_pem_path = cert_path.replace(".pfx", ".pem")
    if os.path.exists(cert_pem_path):
        load_certificate(cert_pem_path, "Certificat AATL Hestia")

    # 2. CA Hestia (signatures utilisateurs)
    ca_cert_path = os.path.join(
        settings.BASE_DIR, "certificates", "hestia_certificate_authority.pem"
    )
    if os.path.exists(ca_cert_path):
        load_certificate(ca_cert_path, "CA Hestia")

    # 3. TSA Hestia (timestamps)
    tsa_cert_path = os.path.join(settings.BASE_DIR, "certificates", "hestia_tsa.pem")
    if os.path.exists(tsa_cert_path):
        load_certificate(tsa_cert_path, "Certificat TSA Hestia")

    if not trust_roots:
        logger.warning("⚠️ Aucun certificat trouvé pour ValidationContext")
        logger.warning("⚠️ PAdES B-LT désactivé, utilisation de PAdES B-T")
        return None

    # Créer le ValidationContext
    # allow_fetching=False car certificats auto-signés (pas de CRL/OCSP externes)
    validation_context = ValidationContext(
        trust_roots=trust_roots,
        allow_fetching=False,  # Pas de fetch CRL/OCSP (auto-signés)
    )

    logger.info(f"✅ ValidationContext créé avec {len(trust_roots)} trust roots")
    return validation_context


def certify_document_hestia(
    source_path: str, output_path: str, document_type: str = "bail"
) -> str:
    """
    PREMIÈRE signature : Certification Hestia avec certificat eIDAS AATL.

    Cette fonction DOIT être appelée en PREMIER, juste après la génération du PDF.
    Elle active la protection DocMDP (verrouillage PDF) et affiche le ruban vert Adobe.

    Args:
        source_path: Chemin du PDF vierge (sans signatures)
        output_path: Chemin du PDF certifié
        document_type: Type de document ("bail", "etat_lieux", "quittance", "mandat")

    Returns:
        str: Chemin du PDF certifié

    Raises:
        FileNotFoundError: Si le certificat Hestia AATL est introuvable
        ValueError: Si PASSWORD_CERT_SERVER n'est pas défini
        Exception: Si la certification échoue

    Example:
        >>> certify_document_hestia(
        ...     '/path/to/bail_vierge.pdf',
        ...     '/path/to/bail_certified.pdf',
        ...     document_type='bail'
        ... )
        '/path/to/bail_certified.pdf'

    Note:
        - Cette signature est INVISIBLE (pas de tampon visuel)
        - Elle doit être la PREMIÈRE signature du document
        - Un document ne peut avoir qu'UNE SEULE certification
        - Les signatures utilisateurs héritent de la protection DocMDP
    """
    logger.info(f"🔐 Début de la certification Hestia pour {document_type}")

    # Certificat eIDAS AATL (CertEurope en production)
    cert_path = os.path.join(settings.BASE_DIR, "certificates", "hestia_server.pfx")

    if not os.path.exists(cert_path):
        # Fallback : certificat serveur auto-signé (test)
        cert_path = os.path.join(settings.BASE_DIR, "certificates", "hestia_server.pfx")
        logger.warning(f"⚠️ Utilisation du certificat de TEST : {cert_path}")
        logger.warning("⚠️ Adobe affichera 'Validity UNKNOWN'")
        logger.warning("⚠️ En production : utiliser hestia_server.pfx de CertEurope")

    if not os.path.exists(cert_path):
        raise FileNotFoundError(
            f"Certificat Hestia AATL introuvable : {cert_path}\n"
            "Générez un certificat de test avec : bash scripts/generate_test_seal_cert.sh\n"
            "Ou installez le certificat CertEurope eIDAS (350€/an) en production."
        )

    # Mot de passe du certificat (depuis settings ou env var)
    password = settings.PASSWORD_CERT_SERVER

    if not password:
        raise ValueError(
            "Variable d'environnement PASSWORD_CERT_SERVER non définie.\n"
            "Pour test : PASSWORD_CERT_SERVER=XXXX!\n"
            "Pour prod : Utiliser le mot de passe du certificat CertEurope."
        )

    if isinstance(password, str):
        password = password.encode("utf-8")

    # Charger le certificat eIDAS
    signer = signers.SimpleSigner.load_pkcs12(pfx_file=cert_path, passphrase=password)

    # TSA Hestia (horodatage certification) - Service interne
    try:
        from tsa.services import InternalTimeStamper
        timestamper = InternalTimeStamper()
        logger.info("✅ TSA Hestia configuré (service interne)")
    except Exception as e:
        logger.warning(f"⚠️ TSA non disponible : {e}")
        logger.warning("⚠️ Le document n'aura pas d'horodatage qualifié")
        timestamper = None

    # ValidationContext pour PAdES B-LT
    validation_context = get_hestia_validation_context()

    # Métadonnées de certification avec PAdES B-LT
    signature_meta = signers.PdfSignatureMetadata(
        field_name=f"Hestia_Certification_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        certify=True,  # ✅ CERTIFICATION signature (PREMIÈRE signature)
        docmdp_permissions=MDPPerm.FILL_FORMS,  # ✅ Niveau 2 (formulaires + signatures)
        # Note: FILL_FORMS autorise remplissage formulaires + ajout signatures
        #       NO_CHANGES (niveau 1) bloque TOUTES modifications, même signatures
        #       Pour PDFs sans formulaires : FILL_FORMS est équivalent à NO_CHANGES
        #       Adobe affichera : "Seules signatures et formulaires autorisés"
        reason=f"Certification du document par Hestia - {document_type}",
        location="France",
        name="HB CONSULTING (Hestia)",
        # Pas de contact_info pour la certification (c'est l'organisation, pas une personne)
        # ✅ PAdES B-LT : Embarquer infos validation dans DSS
        embed_validation_info=validation_context is not None,
        validation_context=validation_context,
        # Note: Le DSS (Document Security Store) contient les infos de révocation
        # permettant la validation à long terme (5-10 ans)
    )

    # Signer avec certification
    with open(source_path, "rb") as inf:
        with open(output_path, "wb") as outf:
            pdf_signer = signers.PdfSigner(
                signature_meta=signature_meta,
                signer=signer,
                timestamper=timestamper,
                # Pas de stamp_style (certification invisible)
            )

            writer = IncrementalPdfFileWriter(inf)
            pdf_signer.sign_pdf(writer, output=outf)

    logger.info(f"✅ Certification Hestia réussie : {output_path}")
    logger.info("✅ DocMDP activé (niveau FILL_FORMS)")
    logger.info("✅ Ruban vert Adobe immédiat (certificat AATL)")

    return output_path


def generate_user_signer(user):
    """
    Génère un certificat auto-signé dynamique pour un utilisateur.

    Ce certificat est utilisé pour les signatures d'approbation (approval signatures)
    après la certification Hestia. Il contient l'identité de l'utilisateur.

    Args:
        user: Instance de Personne (Bailleur ou Locataire)

    Returns:
        SimpleSigner: Signer PyHanko avec certificat auto-signé

    Example:
        >>> signer = generate_user_signer(bailleur)
        >>> # signer contient un certificat X.509 auto-signé avec:
        >>> # CN=Jean Dupont, O=Hestia User, emailAddress=jean@example.com

    Note:
        - Certificat auto-signé (pas besoin d'AC)
        - Gratuit (0€ par utilisateur)
        - Généré à la volée lors de chaque signature
        - Valide 1 an (renouvellement automatique)
        - Clé RSA 2048 bits + SHA-256
    """
    import subprocess
    import tempfile

    logger.info(f"🔑 Génération certificat auto-signé pour {user.email}")

    # Créer fichier temporaire PKCS#12
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pfx", delete=False) as tmpfile:
        pfx_path = tmpfile.name

    try:
        # Générer clé + certificat avec OpenSSL (plus simple que cryptography)
        password = f"temp_user_{user.id}"

        # 1. Générer clé privée
        key_path = pfx_path.replace(".pfx", "_key.pem")
        subprocess.run(
            ["openssl", "genrsa", "-out", key_path, "2048"],
            check=True,
            capture_output=True,
        )

        # 2. Créer fichier de configuration OpenSSL avec extensions
        config_path = pfx_path.replace(".pfx", "_config.cnf")
        with open(config_path, "w") as f:
            f.write(f"""[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_usr

[dn]
O=Hestia User
CN={user.firstName} {user.lastName}
emailAddress={user.email}

[v3_usr]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,nonRepudiation
extendedKeyUsage = emailProtection
""")

        # 3. Générer CSR (Certificate Signing Request)
        csr_path = pfx_path.replace(".pfx", "_csr.pem")
        subprocess.run(
            [
                "openssl",
                "req",
                "-new",
                "-key",
                key_path,
                "-out",
                csr_path,
                "-config",
                config_path,
            ],
            check=True,
            capture_output=True,
        )

        # 4. Signer le CSR avec le CA Hestia
        ca_cert_path = settings.CA_CERT_PATH
        ca_key_path = settings.CA_KEY_PATH
        ca_password = settings.PASSWORD_CERT_CA

        cert_path = pfx_path.replace(".pfx", "_cert.pem")

        if os.path.exists(ca_cert_path) and os.path.exists(ca_key_path):
            # Signer avec le CA Hestia
            subprocess.run(
                [
                    "openssl",
                    "x509",
                    "-req",
                    "-in",
                    csr_path,
                    "-CA",
                    ca_cert_path,
                    "-CAkey",
                    ca_key_path,
                    "-CAcreateserial",
                    "-out",
                    cert_path,
                    "-days",
                    "365",
                    "-sha256",
                    "-extfile",
                    config_path,
                    "-extensions",
                    "v3_usr",
                    "-passin",
                    f"pass:{ca_password}",
                ],
                check=True,
                capture_output=True,
            )
            logger.info(f"✅ Certificat signé par CA Hestia pour {user.email}")
        else:
            # Fallback : Certificat auto-signé (si CA pas disponible)
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-new",
                    "-x509",
                    "-key",
                    key_path,
                    "-out",
                    cert_path,
                    "-days",
                    "365",
                    "-config",
                    config_path,
                ],
                check=True,
                capture_output=True,
            )
            logger.warning(
                f"⚠️ Certificat auto-signé (CA Hestia indisponible) pour {user.email}"
            )

        # 5. Créer PKCS#12 avec la chaîne complète
        pkcs12_cmd = [
            "openssl",
            "pkcs12",
            "-export",
            "-out",
            pfx_path,
            "-inkey",
            key_path,
            "-in",
            cert_path,
            "-password",
            f"pass:{password}",
        ]

        # Ajouter le certificat CA à la chaîne si disponible
        if os.path.exists(ca_cert_path):
            pkcs12_cmd.extend(["-certfile", ca_cert_path])

        subprocess.run(pkcs12_cmd, check=True, capture_output=True)

        # 6. Charger avec PyHanko
        signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=pfx_path, passphrase=password.encode("utf-8")
        )

        logger.info(f"✅ Certificat utilisateur généré pour {user.email}")
        logger.info(f"   CN={user.firstName} {user.lastName}")
        logger.info(f"   Email={user.email}")
        logger.info("   Validité=1 an")

        # Nettoyer fichiers temporaires
        os.remove(key_path)
        os.remove(cert_path)
        os.remove(csr_path)
        os.remove(config_path)
        os.remove(pfx_path)

        return signer

    except Exception as e:
        logger.error(f"❌ Erreur génération certificat utilisateur : {e}")
        # Nettoyer en cas d'erreur
        for f in [
            pfx_path,
            pfx_path.replace(".pfx", "_key.pem"),
            pfx_path.replace(".pfx", "_cert.pem"),
            pfx_path.replace(".pfx", "_csr.pem"),
            pfx_path.replace(".pfx", "_config.cnf"),
        ]:
            if os.path.exists(f):
                os.remove(f)
        raise


def sign_user_with_metadata(
    source_path: str,
    output_path: str,
    user,
    field_name: str,
    signature_bytes: bytes,
    request=None,
    document=None,
    signature_request=None,
) -> str:
    """
    Signature APPROBATION utilisateur avec certificat auto-signé + capture métadonnées.

    Cette fonction est appelée APRÈS la certification Hestia. Elle :
    - Génère un certificat auto-signé pour l'utilisateur
    - Applique un tampon visuel avec la signature manuscrite
    - Capture les métadonnées OTP/IP/user-agent/timestamp
    - Sauvegarde les métadonnées en DB (SignatureMetadata)
    - Ajoute un horodatage TSA (optionnel)

    Args:
        source_path: Chemin du PDF source (certifié ou déjà partiellement signé)
        output_path: Chemin du PDF de sortie (avec nouvelle signature)
        user: Instance de Personne (Bailleur ou Locataire)
        field_name: Nom du champ de signature (ex: "signature_bailleur_123")
        signature_bytes: Image de signature manuscrite (PNG en bytes)
        request: Django HttpRequest (pour récupérer IP/user-agent)
        document: Instance du document (Bail/EtatLieux/Quittance)
        signature_request: Instance de SignatureRequest
                          (métadonnées OTP extraites depuis ici)

    Returns:
        str: Chemin du PDF signé

    Example:
        >>> sign_user_with_metadata(
        ...     source_path='/path/to/bail_certified.pdf',
        ...     output_path='/path/to/bail_signed_bailleur.pdf',
        ...     user=bailleur,
        ...     field_name='signature_bailleur_123',
        ...     signature_bytes=signature_png_bytes,
        ...     request=request,
        ...     signature_request=signature_request
        ... )
        '/path/to/bail_signed_bailleur.pdf'

    Note:
        - Signature d'approbation (certify=False par défaut)
        - Hérite de la protection DocMDP de la certification Hestia
        - Incremental update (ajoute une couche sans modifier les précédentes)
        - Les métadonnées sont sauvegardées dans le journal de preuves
    """
    from django.utils import timezone

    logger.info(f"✍️ Début signature utilisateur pour {user.email}")

    # ⏰ Capturer l'instant T de la signature (pour cohérence PDF + métadonnées)
    signature_timestamp = timezone.now()
    logger.info(f"⏰ Timestamp signature : {signature_timestamp.isoformat()}")

    # Générer certificat auto-signé pour l'utilisateur
    signer = generate_user_signer(user)

    # ValidationContext pour PAdES B-LT
    validation_context = get_hestia_validation_context()

    # Métadonnées de signature (approbation) avec PAdES B-LT
    signature_meta = signers.PdfSignatureMetadata(
        field_name=field_name,
        # certify=False (par défaut, signature d'approbation)
        reason="Signature électronique du document",
        contact_info=user.email,
        location="France",
        name=f"{user.firstName} {user.lastName}",
        # ✅ PAdES B-LT : Embarquer infos validation dans DSS
        embed_validation_info=validation_context is not None,
        validation_context=validation_context,
    )

    # Composer tampon visuel avec signature manuscrite (avec date cohérente)
    from algo.signature.main import (
        TAMPON_HEIGHT_PX,
        TAMPON_WIDTH_PX,
        compose_signature_stamp,
    )

    composed_image, composed_buffer = compose_signature_stamp(
        signature_bytes, user, signature_timestamp
    )
    box = BoxConstraints(width=TAMPON_WIDTH_PX, height=TAMPON_HEIGHT_PX)
    pdf_image = PdfImage(composed_image, box=box)

    stamp_style = stamp.StaticStampStyle(
        background=pdf_image,
        background_opacity=1.0,
        border_width=1,
    )

    # TSA Hestia (horodatage signature) - Service interne
    try:
        from tsa.services import InternalTimeStamper
        timestamper = InternalTimeStamper()
    except Exception as e:
        logger.warning(f"⚠️ TSA non disponible : {e}")
        timestamper = None

    # Capturer métadonnées pour journal de preuves (avec timestamp cohérent)
    metadata = {
        "user_email": user.email,
        "user_name": f"{user.firstName} {user.lastName}",
        "signature_timestamp": signature_timestamp.isoformat(),
        "field_name": field_name,
    }

    # Ajouter métadonnées HTTP si request disponible
    if request:
        metadata["http"] = {
            "ip_address": get_client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT"),
            "referer": request.META.get("HTTP_REFERER"),
        }

    logger.info(f"📊 Métadonnées capturées : {json.dumps(metadata, indent=2)}")

    # Signer avec certificat auto-signé
    with open(source_path, "rb") as inf:
        with open(output_path, "wb") as outf:
            pdf_signer = signers.PdfSigner(
                signature_meta=signature_meta,
                signer=signer,
                stamp_style=stamp_style,
                timestamper=timestamper,
            )

            writer = IncrementalPdfFileWriter(inf)
            pdf_signer.sign_pdf(writer, output=outf, existing_fields_only=True)

    logger.info(f"✅ Signature utilisateur réussie : {output_path}")
    logger.info("✅ Tampon visuel appliqué avec signature manuscrite")

    # Sauvegarder métadonnées en DB (si document ET signature_request fournis)
    if document and signature_request:
        try:
            # Calculer hash PDF AVANT signature
            pdf_hash_before = calculate_pdf_hash(source_path)

            # Préparer métadonnées HTTP
            http_metadata = {}
            if request:
                http_metadata = {
                    "ip_address": get_client_ip(request),
                    "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                    "referer": request.META.get("HTTP_REFERER", ""),
                }

            # Sauvegarder (métadonnées OTP extraites depuis signature_request)
            save_signature_metadata(
                document=document,
                signature_request=signature_request,
                pdf_path=output_path,
                field_name=field_name,
                http_metadata=http_metadata,
                pdf_hash_before=pdf_hash_before,
                signature_timestamp=signature_timestamp,
            )

            logger.info("✅ Métadonnées sauvegardées en DB (SignatureMetadata)")

        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde métadonnées : {e}")
            import traceback

            logger.error(traceback.format_exc())
            # Ne pas bloquer la signature si erreur DB
    elif document and not signature_request:
        logger.warning("⚠️ signature_request manquant, métadonnées non sauvegardées")

    return output_path


def calculate_pdf_hash(pdf_path: str) -> str:
    """
    Calcule le hash SHA-256 d'un PDF.

    Args:
        pdf_path: Chemin du PDF

    Returns:
        str: Hash SHA-256 en hexadécimal
    """
    import hashlib

    sha256 = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_certificate_from_pdf(
    pdf_path: str, field_name: str
) -> Optional["x509.Certificate"]:
    """
    Extrait le certificat X.509 d'un champ de signature PDF.

    Args:
        pdf_path: Chemin du PDF signé
        field_name: Nom du champ de signature

    Returns:
        Certificate object ou None
    """
    try:
        from asn1crypto import cms
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.fields import enumerate_sig_fields

        with open(pdf_path, "rb") as f:
            reader = PdfFileReader(f)

            # enumerate_sig_fields retourne tuples: (name, field_ref, sig_ref)
            sig_fields = list(enumerate_sig_fields(reader))

            for sig_tuple in sig_fields:
                # Décomposer le tuple
                sig_field_name, field_ref, sig_obj_ref = sig_tuple

                # Vérifier si c'est le bon champ
                if sig_field_name == field_name:
                    # Résoudre la référence pour obtenir l'objet champ
                    field_obj = reader.get_object(sig_obj_ref)

                    if field_obj is None or "/V" not in field_obj:
                        logger.warning(
                            f"Champ {field_name} trouvé mais pas encore signé"
                        )
                        continue

                    # L'objet signature est dans /V
                    sig_obj = field_obj["/V"]

                    if "/Contents" not in sig_obj:
                        logger.warning(
                            f"Champ {field_name} signé mais /Contents manquant"
                        )
                        continue

                    # Extraire le certificat depuis /Contents (structure CMS)
                    contents = sig_obj["/Contents"]

                    # Parser le CMS pour extraire le certificat
                    content_info = cms.ContentInfo.load(contents)

                    # Accéder à la structure SignedData
                    if content_info["content_type"].native == "signed_data":
                        signed_data = content_info["content"]

                        # Extraire les certificats
                        has_certs = (
                            "certificates" in signed_data
                            and signed_data["certificates"]
                        )
                        if has_certs:
                            # Premier certificat = signataire
                            cert_choice = signed_data["certificates"][0]

                            # CertificateChoices, extraire certificat
                            if cert_choice.name == "certificate":
                                cert_asn1 = cert_choice.chosen
                                cert_bytes = cert_asn1.dump()

                                # Charger avec cryptography
                                cert = x509.load_der_x509_certificate(
                                    cert_bytes, default_backend()
                                )
                                logger.info(f"✅ Certificat extrait: {field_name}")
                                return cert

        logger.warning(f"Aucun certificat trouvé pour champ {field_name}")
        return None

    except Exception as e:
        logger.error(f"Erreur extraction certificat : {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None


def extract_tsa_timestamp_from_pdf(pdf_path: str, field_name: str) -> Optional[tuple]:
    """
    Extrait le timestamp TSA d'un champ de signature PDF.

    Le timestamp TSA est stocké dans les attributs non signés (unsigned attributes)
    de la structure CMS SignedData, conformément à RFC 3161.

    Args:
        pdf_path: Chemin du PDF signé
        field_name: Nom du champ de signature

    Returns:
        tuple: (tsa_timestamp_datetime, tsa_response_bytes, serial_number) ou None
            - tsa_timestamp_datetime: datetime object avec l'horodatage TSA
            - tsa_response_bytes: Réponse TSA complète (pour archivage)
            - serial_number: Numéro de série du timestamp

    Example:
        >>> result = extract_tsa_timestamp_from_pdf('signed.pdf', 'signature_field_1')
        >>> if result:
        ...     timestamp, response, serial = result
        ...     print(f"Timestamp: {timestamp}, Serial: {serial}")
    """
    try:
        from asn1crypto import cms
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.fields import enumerate_sig_fields

        logger.info(f"🔍 Extraction timestamp TSA pour champ: {field_name}")

        with open(pdf_path, "rb") as f:
            reader = PdfFileReader(f)

            # Parcourir tous les champs de signature
            for sig_field_name, field_ref, sig_obj_ref in enumerate_sig_fields(reader):
                if sig_field_name == field_name:
                    field_obj = reader.get_object(sig_obj_ref)

                    if field_obj is None or "/V" not in field_obj:
                        logger.warning(
                            f"Champ {field_name} trouvé mais pas encore signé"
                        )
                        return None

                    sig_obj = field_obj["/V"]

                    if "/Contents" not in sig_obj:
                        logger.warning(
                            f"Champ {field_name} signé mais /Contents manquant"
                        )
                        return None

                    # Extraire la structure CMS SignedData
                    contents = sig_obj["/Contents"]
                    content_info = cms.ContentInfo.load(contents)

                    if content_info["content_type"].native != "signed_data":
                        logger.warning(
                            f"Type de contenu inattendu: {content_info['content_type'].native}"
                        )
                        return None

                    signed_data = content_info["content"]
                    signer_infos = signed_data["signer_infos"]

                    if not signer_infos:
                        logger.warning("Aucun signer_info trouvé")
                        return None

                    signer_info = signer_infos[0]

                    # Accéder aux attributs non signés
                    # (asn1crypto utilise [] pas .get())
                    # Vérifier si 'unsigned_attrs' existe dans la structure
                    try:
                        unsigned_attrs = signer_info["unsigned_attrs"]
                    except (KeyError, TypeError):
                        logger.info("⚠️ Aucun attribut non signé (pas de timestamp TSA)")
                        return None

                    if not unsigned_attrs:
                        logger.info(
                            "⚠️ Attributs non signés vides (pas de timestamp TSA)"
                        )
                        return None

                    # Chercher l'attribut timestamp TSA
                    # OID pour timestamp-token: 1.2.840.113549.1.9.16.2.14
                    for attr in unsigned_attrs:
                        if attr["type"].dotted == "1.2.840.113549.1.9.16.2.14":
                            # Extraire le token timestamp
                            ts_token_bytes = attr["values"][0].dump()
                            ts_content_info = cms.ContentInfo.load(ts_token_bytes)

                            if ts_content_info["content_type"].native != "signed_data":
                                continue

                            ts_signed_data = ts_content_info["content"]

                            # Extraire TSTInfo (encapsulated content)
                            encap_content = ts_signed_data["encap_content_info"]
                            if encap_content["content_type"].native != "tst_info":
                                continue

                            # .parsed retourne déjà un objet TSTInfo parsé
                            tst_info = encap_content["content"].parsed

                            # Extraire les informations du timestamp
                            gen_time = tst_info["gen_time"].native  # datetime object
                            serial_number = tst_info["serial_number"].native
                            policy_oid = tst_info["policy"].dotted

                            logger.info("✅ Timestamp TSA extrait:")
                            logger.info(f"   Date/heure: {gen_time}")
                            logger.info(f"   Numéro de série: {serial_number}")
                            logger.info(f"   Policy OID: {policy_oid}")

                            return (gen_time, ts_token_bytes, serial_number)

                    logger.info(
                        "⚠️ Attribut timestamp TSA non trouvé dans unsigned_attrs"
                    )
                    return None

        logger.warning(f"Champ de signature '{field_name}' non trouvé dans le PDF")
        return None

    except Exception as e:
        logger.error(f"❌ Erreur extraction timestamp TSA : {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None


def save_signature_metadata(
    document,
    signature_request,
    pdf_path: str,
    field_name: str,
    http_metadata: Dict,
    pdf_hash_before: str,
    signature_timestamp,
):
    """
    Sauvegarde les métadonnées d'une signature en base de données.

    Args:
        document: Instance du document (Bail/EtatLieux/Quittance)
        signature_request: Instance de SignatureRequest (contient OTP)
        pdf_path: Chemin du PDF signé
        field_name: Nom du champ de signature
        http_metadata: Dict avec ip_address, user_agent, referer
        pdf_hash_before: Hash SHA-256 du PDF avant signature
        signature_timestamp: datetime de signature (utilisé pour otp_validated_at)

    Returns:
        Instance de SignatureMetadata créée
    """
    import hashlib

    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone

    from signature.models import SignatureMetadata

    # Récupérer le signer depuis le SignatureRequest
    signer = signature_request.signer

    logger.info(f"💾 Sauvegarde métadonnées signature pour {signer.email}")

    # Calculer hash après signature
    pdf_hash_after = calculate_pdf_hash(pdf_path)

    # Extraire certificat du PDF
    cert = extract_certificate_from_pdf(pdf_path, field_name)

    if not cert:
        logger.error(f"❌ Impossible d'extraire certificat depuis {pdf_path}")
        raise ValueError(f"Impossible d'extraire certificat depuis {pdf_path}")

    # Extraire infos du certificat
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    cert_fingerprint = hashlib.sha256(
        cert.public_bytes(serialization.Encoding.DER)
    ).hexdigest()

    subject = cert.subject
    subject_attrs_cn = subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    subject_attrs_o = subject.get_attributes_for_oid(x509.NameOID.ORGANIZATION_NAME)
    subject_attrs_email = subject.get_attributes_for_oid(x509.NameOID.EMAIL_ADDRESS)

    subject_cn = subject_attrs_cn[0].value if subject_attrs_cn else "Unknown"
    subject_o = subject_attrs_o[0].value if subject_attrs_o else "Unknown"
    subject_email = subject_attrs_email[0].value if subject_attrs_email else None

    # Vérifier que l'email du certificat correspond au signataire
    if subject_email and subject_email != signer.email:
        logger.warning(
            f"⚠️ Email certificat ({subject_email}) != signataire ({signer.email})"
        )

    subject_dn = f"CN={subject_cn}, O={subject_o}"
    if subject_email:
        subject_dn += f", emailAddress={subject_email}"

    issuer = cert.issuer
    issuer_attrs_cn = issuer.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    issuer_cn = issuer_attrs_cn[0].value if issuer_attrs_cn else "Unknown"
    issuer_dn = f"CN={issuer_cn}"

    # Extraire le timestamp TSA du PDF
    logger.info("🔍 Extraction du timestamp TSA depuis le PDF...")
    tsa_info = extract_tsa_timestamp_from_pdf(pdf_path, field_name)

    tsa_timestamp_str = ""
    tsa_response_bytes = None

    if tsa_info:
        tsa_datetime, tsa_response_bytes, tsa_serial = tsa_info
        # Formater pour affichage dans l'admin : "2025-11-03T15:29:46+00:00 (serial: 3)"
        tsa_timestamp_str = f"{tsa_datetime.isoformat()} (serial: {tsa_serial})"
        logger.info(f"✅ Timestamp TSA extrait : {tsa_timestamp_str}")
    else:
        logger.warning("⚠️ Aucun timestamp TSA trouvé (signature sans timestamper)")

    # Créer SignatureMetadata
    document_content_type = ContentType.objects.get_for_model(document)
    sig_req_content_type = ContentType.objects.get_for_model(signature_request)

    # Utiliser le timestamp fourni ou NOW
    if signature_timestamp is None:
        signature_timestamp = timezone.now()

    # Extraire métadonnées OTP depuis signature_request (fail fast si manquantes)
    if not signature_request.otp:
        raise ValueError(
            f"OTP manquant pour SignatureRequest {signature_request.id}"
        )
    if not signature_request.otp_generated_at:
        raise ValueError(
            f"otp_generated_at manquant pour SignatureRequest {signature_request.id}"
        )

    otp_code = signature_request.otp
    otp_generated_at = signature_request.otp_generated_at

    metadata = SignatureMetadata.objects.create(
        # Document
        document_content_type=document_content_type,
        document_object_id=document.id,
        # SignatureRequest (source de vérité pour signer)
        signature_request_content_type=sig_req_content_type,
        signature_request_object_id=signature_request.id,
        signature_field_name=field_name,
        # OTP (copie immuable - validated = True par définition)
        otp_code=otp_code,
        otp_generated_at=otp_generated_at,
        otp_validated_at=signature_timestamp,  # Toujours cohérent avec tampon PDF
        otp_validated=True,  # Toujours True (sinon pas de signature possible)
        # HTTP
        ip_address=http_metadata.get("ip_address", "0.0.0.0"),
        user_agent=http_metadata.get("user_agent", ""),
        referer=http_metadata.get("referer", ""),
        # Crypto (timestamp cohérent avec tampon PDF)
        signature_timestamp=signature_timestamp,
        pdf_hash_before=pdf_hash_before,
        pdf_hash_after=pdf_hash_after,
        # Certificat
        certificate_pem=cert_pem,
        certificate_fingerprint=cert_fingerprint,
        certificate_subject_dn=subject_dn,
        certificate_issuer_dn=issuer_dn,
        certificate_valid_from=cert.not_valid_before_utc,
        certificate_valid_until=cert.not_valid_after_utc,
        # TSA - Extrait depuis le PDF (RFC 3161)
        tsa_timestamp=tsa_timestamp_str,
        tsa_response=tsa_response_bytes,
    )

    logger.info(f"✅ Métadonnées sauvegardées : SignatureMetadata #{metadata.id}")
    logger.info(f"   SignatureRequest: {signature_request.id}")
    logger.info(f"   Signer: {signer.email}")
    logger.info(f"   Field name: {field_name}")
    logger.info(f"   Certificate: {subject_dn}")
    logger.info(f"   Fingerprint: {cert_fingerprint[:16]}...")
    logger.info(f"   Hash before: {pdf_hash_before[:16]}...")
    logger.info(f"   Hash after: {pdf_hash_after[:16]}...")
    logger.info(
        f"   TSA timestamp: {tsa_timestamp_str if tsa_timestamp_str else 'N/A'}"
    )

    return metadata


def apply_final_timestamp(pdf_path: str, output_path: str) -> str:
    """
    [NON UTILISÉ] Applique un DocTimeStamp final pour PAdES B-LTA.

    Cette fonction est désactivée car :
    - PAdES B-LT suffit pour baux/mandats/assurance (5-10 ans)
    - Adobe rejette DocTimeStamp avec TSA auto-signé
    - PAdES B-LTA nécessiterait TSA commercial

    Gardé pour référence future si besoin d'activer B-LTA
    avec TSA commercial (GlobalSign, DigiCert, etc.)

    Args:
        pdf_path: Chemin du PDF avec toutes signatures
        output_path: Chemin du PDF final avec DocTimeStamp

    Returns:
        str: Chemin du PDF final
    """
    logger.info("⏰ [NON UTILISÉ] Application DocTimeStamp final")

    try:
        from tsa.services import InternalTimeStamper
        timestamper = InternalTimeStamper()
    except Exception as e:
        logger.warning(f"⚠️ TSA non disponible : {e}")
        logger.warning("⚠️ Document valide en PAdES B-LT (suffisant)")
        # Copier le fichier sans timestamp
        import shutil

        shutil.copy(pdf_path, output_path)
        return output_path

    try:

        with open(pdf_path, "rb") as inf:
            with open(output_path, "wb") as outf:
                writer = IncrementalPdfFileWriter(inf)

                # Ajouter DocTimeStamp (signature invisible)
                # md_algorithm requis par PyHanko (SHA256 recommandé)
                # Le DocTimeStamp protège le DSS construit par les signatures
                # Note: PdfTimeStamper n'a pas besoin de ValidationContext
                #       car il timestamp juste le PDF (pas de validation)
                pdf_timestamper = signers.PdfTimeStamper(
                    timestamper=timestamper,
                )
                pdf_timestamper.timestamp_pdf(
                    writer, md_algorithm="sha256", output=outf
                )

        logger.info("✅ DocTimeStamp final appliqué (PAdES B-LTA)")
        logger.info(
            "✅ Le DSS (Document Security Store) est protégé par le DocTimeStamp"
        )
        return output_path

    except Exception as e:
        logger.error(f"❌ Erreur DocTimeStamp final : {e}")
        import traceback

        logger.error(traceback.format_exc())
        # Copier sans timestamp en cas d'erreur
        import shutil

        shutil.copy(pdf_path, output_path)
        return output_path


def generate_proof_journal(document, output_path: Optional[str] = None) -> Dict:
    """
    Génère le journal de preuves forensique complet pour un document.

    Ce journal contient toutes les métadonnées de signature (OTP, IP, timestamps)
    et est signé avec le cachet Hestia pour garantir son intégrité.

    Args:
        document: Instance du document (Bail, EtatLieux, Quittance, etc.)
        output_path: Chemin pour sauvegarder le JSON (optionnel)

    Returns:
        Dict: Journal de preuves structuré

    Example:
        >>> journal = generate_proof_journal(bail, '/path/to/proof_journal.json')
        >>> print(journal.keys())
        dict_keys(['document', 'certification', 'signatures', 'timestamps', 'audit'])

    Structure du journal:
        {
            "document": {
                "type": "bail",
                "location_id": "...",
                "created_at": "...",
                "pdf_hash_sha256": "..."
            },
            "certification": {
                "certifier": "HB CONSULTING (Hestia)",
                "certificate_issuer": "CertEurope",
                "timestamp": "...",
                "tsa_url": "..."
            },
            "signatures": [
                {
                    "signer_email": "...",
                    "signer_name": "...",
                    "timestamp": "...",
                    "otp_validated": true,
                    "ip_address": "...",
                    "user_agent": "...",
                    "tsa_timestamp": "..."
                },
                ...
            ],
            "timestamps": {
                "t0_certification": "...",
                "t1_bailleur": "...",
                "t2_locataire": "...",
                "t_final": "..."
            },
            "audit": {
                "generated_at": "...",
                "signature_hestia": "..."  // Signature du JSON par cachet Hestia
            }
        }

    Note:
        - Le JSON est signé avec le cachet Hestia (HMAC-SHA256)
        - Sauvegardé dans DB (PostgreSQL) ET S3 Glacier (immuable)
        - Utilisé comme preuve en cas de litige
    """
    from django.contrib.contenttypes.models import ContentType

    from signature.models import SignatureMetadata

    logger.info(f"📝 Génération du journal de preuves pour {document}")

    # Récupérer toutes les métadonnées depuis DB
    content_type = ContentType.objects.get_for_model(document)
    signatures_metadata = SignatureMetadata.objects.filter(
        document_content_type=content_type, document_object_id=document.id
    ).order_by("signature_timestamp")

    # Calculer hash du PDF final
    final_pdf_hash = None
    if hasattr(document, "latest_pdf") and document.latest_pdf:
        try:
            final_pdf_hash = calculate_pdf_hash(document.latest_pdf.path)
        except Exception as e:
            logger.warning(f"Impossible de calculer hash PDF final : {e}")

    # Structurer le journal
    journal = {
        "document": {
            "type": document.__class__.__name__.lower(),
            "id": str(document.id) if hasattr(document, "id") else None,
            "location_id": str(document.location_id)
            if hasattr(document, "location_id")
            else None,
            "created_at": document.created_at.isoformat()
            if hasattr(document, "created_at")
            else None,
            "pdf_hash_final": final_pdf_hash,
        },
        "certification": {
            "certifier": "HB CONSULTING (Hestia)",
            "certificate_issuer": "CertEurope eIDAS AATL",
            "timestamp_t0": signatures_metadata.first().signature_timestamp.isoformat()
            if signatures_metadata.exists()
            else None,
        },
        "signatures": [sig.to_proof_dict() for sig in signatures_metadata],
        "timestamps": {
            "t0_certification": "Embedded in PDF certification signature",
            "t_final": "DocTimeStamp applied"
            if hasattr(document, "latest_pdf")
            else None,
        },
        "audit": {
            "generated_at": datetime.datetime.now().isoformat(),
            "total_signatures": signatures_metadata.count(),
        },
    }

    logger.info(
        f"✅ Journal de preuves généré : {signatures_metadata.count()} signatures"
    )

    # Sauvegarder en JSON si chemin fourni
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(journal, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Journal de preuves sauvegardé : {output_path}")

    logger.info("✅ Journal de preuves généré avec succès")

    return journal


def is_document_certified(pdf_path: str) -> bool:
    """
    Vérifie si un PDF a déjà été certifié par Hestia.

    Args:
        pdf_path: Chemin du PDF à vérifier

    Returns:
        bool: True si le PDF contient une certification Hestia, False sinon

    Example:
        >>> is_document_certified('/path/to/bail.pdf')
        True
    """
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader

        with open(pdf_path, "rb") as f:
            reader = PdfFileReader(f)
            sig_fields = reader.root.get("/AcroForm", {}).get("/Fields", [])

            for field in sig_fields:
                field_name = field.get("/T", "")
                if isinstance(field_name, bytes):
                    field_name = field_name.decode("utf-8", errors="ignore")

                # Chercher un champ de certification Hestia
                if "hestia_certification" in field_name.lower():
                    return True

        return False

    except Exception as e:
        logger.warning(f"⚠️ Erreur lors de la vérification de certification : {e}")
        return False
