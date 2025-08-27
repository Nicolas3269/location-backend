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
    serializer_class = serializer_map.get(source, BienBailSerializer)

    # Si les données sont déjà au format composé, utiliser directement
    if "bien" in form_data and isinstance(form_data["bien"], dict):
        bien_data = form_data["bien"]
    else:
        # Sinon, transformer l'ancien format vers le nouveau format composé
        bien_data = {
            "localisation": {
                "adresse": form_data.get("adresse", ""),
                "latitude": form_data.get("latitude"),
                "longitude": form_data.get("longitude"),
            },
            "caracteristiques": {
                "superficie": form_data.get("superficie", 50),
                "type_bien": form_data.get("typeLogement", "appartement"),
                "meuble": form_data.get("meuble", False),
                "etage": form_data.get("etage", ""),
                "porte": form_data.get("porte", ""),
                "dernier_etage": form_data.get("dernierEtage", False),
                "pieces_info": form_data.get("pieces_info", {}),
            },
            "performance_energetique": {
                "classe_dpe": form_data.get("dpeGrade", "NA"),
                "depenses_energetiques": form_data.get("depensesDPE", ""),
            },
            "energie": {
                "chauffage": {
                    "type": form_data.get("chauffage", {}).get("type", "individuel"),
                    "energie": form_data.get("chauffage", {}).get(
                        "energie", "electricite"
                    ),
                },
                "eau_chaude": {
                    "type": form_data.get("eauChaude", {}).get("type", "individuel"),
                    "energie": form_data.get("eauChaude", {}).get(
                        "energie", "electricite"
                    ),
                },
            },
            "regime": {
                "regime_juridique": form_data.get("regimeJuridique", "monopropriete"),
                "periode_construction": form_data.get(
                    "periodeConstruction", "avant 1946"
                ),
                "identifiant_fiscal": form_data.get("identificationFiscale", ""),
            },
            "equipements": {
                "annexes_privatives": form_data.get("equipements", {}).get(
                    "annexes_privatives", form_data.get("annexesPrivatives", [])
                ),
                "annexes_collectives": form_data.get("equipements", {}).get(
                    "annexes_collectives", form_data.get("annexesCollectives", [])
                ),
                "information": form_data.get("equipements", {}).get(
                    "information", form_data.get("information", [])
                ),
            },
        }

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
        bien_fields.update({
            "superficie": caracteristiques.get("superficie"),
            "type_bien": caracteristiques.get("type_bien", "appartement"),
            "meuble": caracteristiques.get("meuble", False),
            "etage": caracteristiques.get("etage", ""),
            "porte": caracteristiques.get("porte", ""),
            "dernier_etage": caracteristiques.get("dernier_etage", False),
            "pieces_info": caracteristiques.get("pieces_info", {}),
        })
    else:
        # Valeurs par défaut si pas de caractéristiques (cas quittance)
        bien_fields.update({
            "type_bien": "appartement",
            "meuble": False,
            "dernier_etage": False,
            "pieces_info": {},
        })

    # Ajouter les champs optionnels s'ils existent
    if "performance_energetique" in validated:
        bien_fields["classe_dpe"] = validated["performance_energetique"]["classe_dpe"]
        bien_fields["depenses_energetiques"] = validated["performance_energetique"].get(
            "depenses_energetiques", ""
        )

    if "energie" in validated:
        if "chauffage" in validated["energie"]:
            bien_fields["chauffage_type"] = validated["energie"]["chauffage"].get(
                "type", "individuel"
            )
            bien_fields["chauffage_energie"] = validated["energie"]["chauffage"].get(
                "energie", "electricite"
            )
        if "eau_chaude" in validated["energie"]:
            bien_fields["eau_chaude_type"] = validated["energie"]["eau_chaude"].get(
                "type", "individuel"
            )
            bien_fields["eau_chaude_energie"] = validated["energie"]["eau_chaude"].get(
                "energie", "electricite"
            )

    if "regime" in validated:
        bien_fields["regime_juridique"] = validated["regime"]["regime_juridique"]
        bien_fields["periode_construction"] = validated["regime"].get(
            "periode_construction"
        )
        bien_fields["identifiant_fiscal"] = validated["regime"].get(
            "identifiant_fiscal", ""
        )

    if "equipements" in validated:
        bien_fields["annexes_privatives"] = validated["equipements"].get(
            "annexes_privatives", []
        )
        bien_fields["annexes_collectives"] = validated["equipements"].get(
            "annexes_collectives", []
        )
        bien_fields["information"] = validated["equipements"].get("information", [])

    # Enlever les valeurs None pour éviter les erreurs
    bien_fields = {k: v for k, v in bien_fields.items() if v is not None}

    bien = Bien(**bien_fields)

    if save:
        bien.save()

    return bien
