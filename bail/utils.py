import logging

from django.conf import settings
from django.core.mail import send_mail as django_send_mail

from bail.models import BailSignatureRequest
from location.models import Bien

logger = logging.getLogger(__name__)


def send_mail(subject, message, from_email, recipient_list):
    django_send_mail(subject, message, from_email, recipient_list)


def send_signature_email(signature_request: BailSignatureRequest):
    person = signature_request.bailleur_signataire or signature_request.locataire
    link = f"{settings.FRONTEND_URL}/bail/signing/{signature_request.link_token}/"
    message = f"""
Bonjour {person.firstName},

Veuillez signer le bail en suivant ce lien : {link}

Merci,
L'équipe HESTIA
"""
    send_mail(
        subject="Signature de votre bail",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        # recipient_list=[person.email],
        recipient_list=["nicolas3269@gmail.com"],
    )


def create_signature_requests(bail):
    """
    Crée les demandes de signature pour un bail.
    Utilise la fonction générique pour factoriser le code.
    """
    from signature.services import create_signature_requests_generic

    create_signature_requests_generic(bail, BailSignatureRequest)


def create_bien_from_form_data(validated_data, save=True, source="bail"):
    """
    Crée un objet Bien à partir des données VALIDÉES du serializer.

    Args:
        validated_data: Les données déjà validées par le serializer principal
        save: Si True, sauvegarde l'objet en base.
              Si False, retourne un objet non sauvegardé.
        source: Type de formulaire ("bail", "quittance", "etat_lieux")

    Returns:
        Instance de Bien
    """
    # Les données sont déjà validées, extraire directement les données du bien
    if "bien" not in validated_data:
        # Si pas de données bien, retourner None
        return None

    validated = validated_data["bien"]

    # Les données sont déjà dans le bon format (snake_case) depuis le serializer
    # Extraire directement tous les champs disponibles
    bien_fields = {}

    # Localisation (toujours présent)
    if "localisation" in validated:
        localisation = validated["localisation"]
        if "adresse" in localisation:
            bien_fields["adresse"] = localisation["adresse"]
        if "latitude" in localisation:
            bien_fields["latitude"] = localisation["latitude"]
        if "longitude" in localisation:
            bien_fields["longitude"] = localisation["longitude"]

    # Caractéristiques (optionnel pour quittance)
    if "caracteristiques" in validated:
        caracteristiques = validated["caracteristiques"]
        for field in [
            "superficie",
            "type_bien",
            "meuble",
            "etage",
            "porte",
            "dernier_etage",
            "pieces_info",
        ]:
            if field in caracteristiques:
                bien_fields[field] = caracteristiques[field]

    # Performance énergétique
    if "performance_energetique" in validated:
        perf = validated["performance_energetique"]
        if "classe_dpe" in perf:
            bien_fields["classe_dpe"] = perf["classe_dpe"]
        if "depenses_energetiques" in perf:
            bien_fields["depenses_energetiques"] = perf["depenses_energetiques"]

    # Énergie
    if "energie" in validated:
        energie = validated["energie"]
        if "chauffage" in energie:
            if "type" in energie["chauffage"]:
                bien_fields["chauffage_type"] = energie["chauffage"]["type"]
            if "energie" in energie["chauffage"]:
                bien_fields["chauffage_energie"] = energie["chauffage"]["energie"]
        if "eau_chaude" in energie:
            if "type" in energie["eau_chaude"]:
                bien_fields["eau_chaude_type"] = energie["eau_chaude"]["type"]
            if "energie" in energie["eau_chaude"]:
                bien_fields["eau_chaude_energie"] = energie["eau_chaude"]["energie"]

    # Régime juridique
    if "regime" in validated:
        regime = validated["regime"]
        for field in ["regime_juridique", "periode_construction", "identifiant_fiscal"]:
            if field in regime:
                bien_fields[field] = regime[field]

    # Équipements
    if "equipements" in validated:
        equipements = validated["equipements"]
        for field in ["annexes_privatives", "annexes_collectives", "information"]:
            if field in equipements:
                bien_fields[field] = equipements[field]

    # Enlever les valeurs None pour éviter les erreurs
    bien_fields = {k: v for k, v in bien_fields.items() if v is not None}

    bien = Bien(**bien_fields)

    if save:
        bien.save()

    return bien
