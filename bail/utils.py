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


def create_bien_from_form_data(form_data, save=True, source="bail"):
    """
    Crée un objet Bien à partir des données du formulaire en utilisant les serializers.

    Cette fonction est maintenant un wrapper qui convertit l'ancien format
    vers le nouveau format composé et utilise les serializers pour la validation.

    Args:
        form_data: Les données du formulaire (ancien ou nouveau format)
        save: Si True, sauvegarde l'objet en base.
              Si False, retourne un objet non sauvegardé.
        source: Type de formulaire ("bail", "quittance", "etat_lieux")

    Returns:
        Instance de Bien
    """
    from location.serializers_composed import (
        BienBailSerializer,
        BienEtatLieuxSerializer,
        BienQuittanceSerializer,
    )

    # Choisir le bon serializer selon la source
    serializer_map = {
        "bail": BienBailSerializer,
        "quittance": BienQuittanceSerializer,
        "etat_lieux": BienEtatLieuxSerializer,
        "manual": BienBailSerializer,
    }

    if source not in serializer_map:
        raise ValueError(
            f"Source '{source}' non reconnue. Sources valides: {list(serializer_map.keys())}"
        )

    serializer_class = serializer_map[source]

    # Si les données sont déjà au format composé, utiliser directement
    if "bien" in form_data and isinstance(form_data["bien"], dict):
        bien_data = form_data["bien"]
    else:
        # Sinon, transformer l'ancien format vers le nouveau format composé
        bien_data = {}

        # Localisation
        localisation = {}
        if "adresse" in form_data:
            localisation["adresse"] = form_data["adresse"]
        if "latitude" in form_data:
            localisation["latitude"] = form_data["latitude"]
        if "longitude" in form_data:
            localisation["longitude"] = form_data["longitude"]
        if localisation:
            bien_data["localisation"] = localisation

        # Caractéristiques
        caracteristiques = {}
        if "superficie" in form_data:
            caracteristiques["superficie"] = form_data["superficie"]
        if "typeLogement" in form_data:
            caracteristiques["type_bien"] = form_data["typeLogement"]
        if "meuble" in form_data:
            caracteristiques["meuble"] = form_data["meuble"]
        if "etage" in form_data:
            caracteristiques["etage"] = form_data["etage"]
        if "porte" in form_data:
            caracteristiques["porte"] = form_data["porte"]
        if "dernierEtage" in form_data:
            caracteristiques["dernier_etage"] = form_data["dernierEtage"]
        if "pieces_info" in form_data:
            caracteristiques["pieces_info"] = form_data["pieces_info"]
        if caracteristiques:
            bien_data["caracteristiques"] = caracteristiques

        # Performance énergétique
        performance_energetique = {}
        if "dpeGrade" in form_data:
            performance_energetique["classe_dpe"] = form_data["dpeGrade"]
        if "depensesDPE" in form_data:
            performance_energetique["depenses_energetiques"] = form_data["depensesDPE"]
        if performance_energetique:
            bien_data["performance_energetique"] = performance_energetique

        # Energie
        energie = {}
        if "chauffage" in form_data and form_data["chauffage"]:
            chauffage = {}
            if "type" in form_data["chauffage"]:
                chauffage["type"] = form_data["chauffage"]["type"]
            if "energie" in form_data["chauffage"]:
                chauffage["energie"] = form_data["chauffage"]["energie"]
            if chauffage:
                energie["chauffage"] = chauffage

        if "eauChaude" in form_data and form_data["eauChaude"]:
            eau_chaude = {}
            if "type" in form_data["eauChaude"]:
                eau_chaude["type"] = form_data["eauChaude"]["type"]
            if "energie" in form_data["eauChaude"]:
                eau_chaude["energie"] = form_data["eauChaude"]["energie"]
            if eau_chaude:
                energie["eau_chaude"] = eau_chaude
        if energie:
            bien_data["energie"] = energie

        # Régime
        regime = {}
        if "regimeJuridique" in form_data:
            regime["regime_juridique"] = form_data["regimeJuridique"]
        if "periodeConstruction" in form_data:
            regime["periode_construction"] = form_data["periodeConstruction"]
        if "identificationFiscale" in form_data:
            regime["identifiant_fiscal"] = form_data["identificationFiscale"]
        if regime:
            bien_data["regime"] = regime

        # Equipements
        equipements = {}

        # Gérer les annexes privatives
        if (
            "equipements" in form_data
            and "annexes_privatives" in form_data["equipements"]
        ):
            equipements["annexes_privatives"] = form_data["equipements"][
                "annexes_privatives"
            ]
        elif "annexesPrivatives" in form_data:
            equipements["annexes_privatives"] = form_data["annexesPrivatives"]

        # Gérer les annexes collectives
        if (
            "equipements" in form_data
            and "annexes_collectives" in form_data["equipements"]
        ):
            equipements["annexes_collectives"] = form_data["equipements"][
                "annexes_collectives"
            ]
        elif "annexesCollectives" in form_data:
            equipements["annexes_collectives"] = form_data["annexesCollectives"]

        # Gérer les informations
        if "equipements" in form_data and "information" in form_data["equipements"]:
            equipements["information"] = form_data["equipements"]["information"]
        elif "information" in form_data:
            equipements["information"] = form_data["information"]

        if equipements:
            bien_data["equipements"] = equipements

    # Valider avec le serializer approprié
    serializer = serializer_class(data=bien_data)

    if not serializer.is_valid():
        raise ValueError(f"Données du bien invalides: {serializer.errors}")

    # Créer le bien à partir des données validées
    validated = serializer.validated_data

    # Mapper les données validées vers les champs du modèle
    bien_fields = {
        # Localisation (toujours présent)
        "adresse": validated["localisation"]["adresse"],
        "latitude": validated["localisation"].get("latitude"),
        "longitude": validated["localisation"].get("longitude"),
    }

    # Caractéristiques (optionnel pour quittance)
    if "caracteristiques" in validated:
        caracteristiques = validated["caracteristiques"]
        bien_fields.update(
            {
                "superficie": caracteristiques.get("superficie"),
                "type_bien": caracteristiques.get("type_bien"),
                "meuble": caracteristiques.get("meuble"),
                "etage": caracteristiques.get("etage"),
                "porte": caracteristiques.get("porte"),
                "dernier_etage": caracteristiques.get("dernier_etage"),
                "pieces_info": caracteristiques.get("pieces_info"),
            }
        )
    # Pas de else - ne pas ajouter de valeurs par défaut

    # Ajouter les champs optionnels s'ils existent
    if "performance_energetique" in validated:
        bien_fields["classe_dpe"] = validated["performance_energetique"]["classe_dpe"]
        bien_fields["depenses_energetiques"] = validated["performance_energetique"].get(
            "depenses_energetiques"
        )

    if "energie" in validated:
        if "chauffage" in validated["energie"]:
            bien_fields["chauffage_type"] = validated["energie"]["chauffage"].get(
                "type"
            )
            bien_fields["chauffage_energie"] = validated["energie"]["chauffage"].get(
                "energie"
            )
        if "eau_chaude" in validated["energie"]:
            bien_fields["eau_chaude_type"] = validated["energie"]["eau_chaude"].get(
                "type"
            )
            bien_fields["eau_chaude_energie"] = validated["energie"]["eau_chaude"].get(
                "energie"
            )

    if "regime" in validated:
        bien_fields["regime_juridique"] = validated["regime"]["regime_juridique"]
        bien_fields["periode_construction"] = validated["regime"].get(
            "periode_construction"
        )
        bien_fields["identifiant_fiscal"] = validated["regime"].get(
            "identifiant_fiscal"
        )

    if "equipements" in validated:
        # Ne pas defaulter à [], garder None si non défini
        if "annexes_privatives" in validated["equipements"]:
            bien_fields["annexes_privatives"] = validated["equipements"][
                "annexes_privatives"
            ]
        if "annexes_collectives" in validated["equipements"]:
            bien_fields["annexes_collectives"] = validated["equipements"][
                "annexes_collectives"
            ]
        if "information" in validated["equipements"]:
            bien_fields["information"] = validated["equipements"]["information"]

    # Enlever les valeurs None pour éviter les erreurs
    bien_fields = {k: v for k, v in bien_fields.items() if v is not None}

    bien = Bien(**bien_fields)

    if save:
        bien.save()

    return bien
