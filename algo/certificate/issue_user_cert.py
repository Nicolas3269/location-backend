"""
Service pour émettre des certificats utilisateurs à la volée
depuis la CA privée Hestia signée par GlobalSign.

Architecture:
- GlobalSign Root CA (AATL trusted)
  └─> Hestia CA (hestia_ca_signed.pem)
      └─> Certificats utilisateurs (landlord.pfx, tenant.pfx)

Conformité eIDAS AES (Advanced Electronic Signature):
- Identification unique du signataire (email, nom)
- Lien exclusif certificat <-> signataire
- Intégrité du document (signature invalide si modifié)
- Audit log (métadonnées stockées en DB)
- Horodatage (optionnel via TSA)
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)

CA_DIR = Path(__file__).parent.parent.parent / "certificates"
CA_KEY_PATH = CA_DIR / "hestia_certificate_authority.key"
CA_CERT_PATH = CA_DIR / "hestia_certificate_authority.pem"
CA_PASSWORD = os.getenv("PASSWORD_CERT_CA", "").encode("utf-8")

# Fallback vers certificat auto-signé si GlobalSign pas encore reçu
if not CA_CERT_PATH.exists():
    CA_CERT_PATH = CA_DIR / "hestia_ca_selfsigned.pem"
    logger.warning("⚠️  Utilisation du certificat auto-signé (GlobalSign pas encore reçu)")


def load_ca_certificate():
    """Charge le certificat CA Hestia (signé par GlobalSign)."""
    with open(CA_CERT_PATH, "rb") as f:
        return x509.load_pem_x509_certificate(f.read(), default_backend())


def load_ca_private_key():
    """Charge la clé privée CA Hestia."""
    with open(CA_KEY_PATH, "rb") as f:
        if CA_PASSWORD:
            return serialization.load_pem_private_key(
                f.read(), password=CA_PASSWORD, backend=default_backend()
            )
        else:
            return serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )


def issue_user_certificate(
    user_email: str,
    user_name: str,
    user_type: str = "landlord",  # ou "tenant"
    validity_days: int = 365,
) -> tuple[bytes, bytes]:
    """
    Émet un certificat utilisateur signé par la CA Hestia.

    Args:
        user_email: Email de l'utilisateur (identifiant unique)
        user_name: Nom complet de l'utilisateur
        user_type: Type d'utilisateur (landlord, tenant)
        validity_days: Durée de validité du certificat en jours

    Returns:
        tuple: (certificat PEM, clé privée PEM)
    """
    logger.info(f"📝 Émission certificat pour {user_name} ({user_email})")

    # 1. Générer paire de clés utilisateur
    user_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # 2. Charger CA Hestia
    ca_cert = load_ca_certificate()
    ca_private_key = load_ca_private_key()

    # 3. Créer le certificat utilisateur
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "FR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Hauts-de-France"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Arras"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "HB CONSULTING"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, f"Hestia {user_type.capitalize()}"),
        x509.NameAttribute(NameOID.COMMON_NAME, user_name),
        x509.NameAttribute(NameOID.EMAIL_ADDRESS, user_email),
    ])

    cert_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(user_private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=validity_days))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=True,  # Non-repudiation
                key_cert_sign=False,
                crl_sign=False,
                key_agreement=False,
                data_encipherment=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.EMAIL_PROTECTION,
                ExtendedKeyUsageOID.CLIENT_AUTH,
                # Pour signature de documents (Adobe)
                x509.ObjectIdentifier("1.3.6.1.5.5.7.3.36"),  # documentSigning
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectAlternativeName([
                x509.RFC822Name(user_email),
            ]),
            critical=False,
        )
    )

    # 4. Signer avec CA Hestia
    user_cert = cert_builder.sign(ca_private_key, hashes.SHA256(), default_backend())

    # 5. Encoder en PEM
    cert_pem = user_cert.public_bytes(serialization.Encoding.PEM)
    key_pem = user_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    logger.info(f"✅ Certificat émis avec succès (serial: {user_cert.serial_number})")
    return cert_pem, key_pem


def create_pkcs12(
    user_email: str,
    user_name: str,
    password: str,
    user_type: str = "landlord",
) -> bytes:
    """
    Crée un fichier PKCS#12 (.pfx) pour l'utilisateur.

    Args:
        user_email: Email de l'utilisateur
        user_name: Nom complet de l'utilisateur
        password: Mot de passe du fichier PKCS#12
        user_type: Type d'utilisateur (landlord, tenant)

    Returns:
        bytes: Fichier PKCS#12 (.pfx)
    """
    # 1. Émettre le certificat
    cert_pem, key_pem = issue_user_certificate(user_email, user_name, user_type)

    # 2. Charger CA cert (pour chaîne de confiance)
    ca_cert_pem = CA_CERT_PATH.read_bytes()

    # 3. Créer PKCS#12 avec cryptography
    from cryptography.hazmat.primitives.serialization import pkcs12

    user_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
    user_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())

    pfx_data = pkcs12.serialize_key_and_certificates(
        name=user_name.encode("utf-8"),
        key=user_key,
        cert=user_cert,
        cas=[ca_cert],  # Inclure CA dans la chaîne
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
    )

    logger.info(f"✅ PKCS#12 créé pour {user_name}")
    return pfx_data


# API Django pour émettre certificats à la volée
def get_or_create_user_certificate(user_email: str, user_name: str, user_type: str) -> str:
    """
    Récupère ou crée un certificat utilisateur.
    Stocke le .pfx dans media/certificates/{user_email}.pfx

    Args:
        user_email: Email de l'utilisateur
        user_name: Nom complet de l'utilisateur
        user_type: Type d'utilisateur (landlord, tenant)

    Returns:
        str: Chemin vers le fichier .pfx
    """
    from django.conf import settings

    cert_dir = Path(settings.MEDIA_ROOT) / "certificates"
    cert_dir.mkdir(parents=True, exist_ok=True)

    pfx_path = cert_dir / f"{user_email}.pfx"

    # Si certificat existe déjà et valide, le réutiliser
    if pfx_path.exists():
        # TODO: Vérifier validité du certificat existant
        logger.info(f"♻️  Certificat existant réutilisé pour {user_email}")
        return str(pfx_path)

    # Sinon, émettre un nouveau certificat
    password = f"hestia_{user_email}_2025"  # TODO: Générer mot de passe aléatoire sécurisé
    pfx_data = create_pkcs12(user_email, user_name, password, user_type)

    pfx_path.write_bytes(pfx_data)
    logger.info(f"💾 Certificat sauvegardé : {pfx_path}")

    # TODO: Stocker en DB (UserCertificate model)
    # - user_id, email, pfx_path, password_hash, serial_number, valid_until, created_at

    return str(pfx_path)


if __name__ == "__main__":
    # Test : Émettre un certificat pour un utilisateur
    logging.basicConfig(level=logging.INFO)

    cert_pem, key_pem = issue_user_certificate(
        user_email="nicolas.havard@hestia-immo.fr",
        user_name="Nicolas HAVARD",
        user_type="landlord",
    )

    print("✅ Certificat émis :")
    print(cert_pem.decode("utf-8"))
