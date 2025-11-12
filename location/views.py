import json
import logging

from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from bail.models import Bail
from bail.utils import create_bien_from_form_data
from etat_lieux.models import EtatLieux
from location.constants import UserRole
from location.models import (
    Bailleur,
    BailleurType,
    Bien,
    HonoraireMandataire,
    Locataire,
    Location,
    Mandataire,
    Personne,
    RentTerms,
    Societe,
)
from location.serializers_composed import (
    CreateBailSerializer,
    CreateEtatLieuxSerializer,
    CreateQuittanceSerializer,
)
from location.services.access_utils import (
    user_has_bien_access,
    user_has_location_access,
)
from location.services.document_utils import (
    determine_mandataire_doit_signer,
    determine_mandataire_fait_edl,
)
from quittance.models import Quittance
from quittance.views import get_or_create_quittance_for_location
from rent_control.choices import ChargeType
from signature.document_status import DocumentStatus

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_locataire_locations(request):
    """
    Récupère toutes les locations où l'utilisateur est locataire
    """
    try:
        user_email = request.user.email

        # Trouver tous les locataires avec cet email
        locataires = Locataire.objects.filter(email=user_email)

        if not locataires.exists():
            return JsonResponse({"success": True, "locations": []})

        # Récupérer toutes les locations de ces locataires
        locations = (
            Location.objects.filter(locataires__in=locataires)
            .distinct()
            .order_by("-created_at")
        )

        locations_data = []
        for location in locations:
            # Récupérer le bailleur principal
            bailleur = location.bien.bailleurs.first()
            bailleur_data = {}
            if bailleur:
                if bailleur.personne:
                    bailleur_data = {
                        "first_name": bailleur.personne.firstName,
                        "last_name": bailleur.personne.lastName,
                        "email": bailleur.email,
                    }
                elif bailleur.societe:
                    bailleur_data = {
                        "first_name": bailleur.societe.raison_sociale,
                        "last_name": "",
                        "email": bailleur.email,
                    }

            # Récupérer les conditions financières
            montant_loyer = 0
            montant_charges = 0
            depot_garantie = 0
            try:
                rent_terms = location.rent_terms
                montant_loyer = (
                    float(rent_terms.montant_loyer) if rent_terms.montant_loyer else 0
                )
                montant_charges = (
                    float(rent_terms.montant_charges)
                    if rent_terms.montant_charges
                    else 0
                )
                depot_garantie = (
                    float(rent_terms.depot_garantie) if rent_terms.depot_garantie else 0
                )
            except RentTerms.DoesNotExist:
                pass

            # Déterminer le statut - récupérer le bail actif (SIGNING ou SIGNED, ou le plus récent DRAFT)
            from bail.models import Bail

            bail_actif = (
                Bail.objects.filter(
                    location=location,
                    status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED],
                )
                .order_by("-created_at")
                .first()
            ) or Bail.objects.filter(location=location).order_by("-created_at").first()
            status = bail_actif.status if bail_actif else DocumentStatus.DRAFT

            locations_data.append(
                {
                    "id": str(location.id),
                    "date_debut": location.date_debut.isoformat()
                    if location.date_debut
                    else None,
                    "date_fin": location.date_fin.isoformat()
                    if location.date_fin
                    else None,
                    "montant_loyer": montant_loyer,
                    "montant_charges": montant_charges,
                    "depot_garantie": depot_garantie,
                    "status": status,
                    "bien": {
                        "id": location.bien.id,
                        "adresse": location.bien.adresse,
                        "type": location.bien.type_bien or "Appartement",
                        "superficie": float(location.bien.superficie)
                        if location.bien.superficie
                        else 0,
                        "meuble": location.bien.meuble or False,
                    },
                    "bailleur": bailleur_data,
                }
            )

        return JsonResponse({"success": True, "locations": locations_data})

    except Exception as e:
        logger.error(
            f"Erreur lors de la récupération des locations du locataire: {str(e)}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_location_detail(request, location_id):
    """
    Récupère les détails d'une location spécifique
    """
    try:
        location = Location.objects.get(id=location_id)

        # Vérifier que l'utilisateur a accès à cette location
        user_email = request.user.email
        has_access = user_has_location_access(location, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à cette location"}, status=403
            )

        # Récupérer le bailleur principal
        bailleur = location.bien.bailleurs.first()
        bailleur_data = {}
        if bailleur:
            if bailleur.personne:
                bailleur_data = {
                    "first_name": bailleur.personne.firstName,
                    "last_name": bailleur.personne.lastName,
                    "email": bailleur.email,
                }
            elif bailleur.societe:
                bailleur_data = {
                    "first_name": bailleur.societe.raison_sociale,
                    "last_name": "",
                    "email": bailleur.email,
                }

        # Récupérer les conditions financières
        montant_loyer = 0
        montant_charges = 0
        depot_garantie = 0
        try:
            rent_terms = location.rent_terms
            montant_loyer = (
                float(rent_terms.montant_loyer) if rent_terms.montant_loyer else 0
            )
            montant_charges = (
                float(rent_terms.montant_charges) if rent_terms.montant_charges else 0
            )
            depot_garantie = (
                float(rent_terms.depot_garantie) if rent_terms.depot_garantie else 0
            )
        except RentTerms.DoesNotExist:
            pass

        # Déterminer le statut - récupérer le bail actif (SIGNING ou SIGNED, ou le plus récent DRAFT)
        from bail.models import Bail

        bail_actif = (
            Bail.objects.filter(
                location=location,
                status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED],
            )
            .order_by("-created_at")
            .first()
        ) or Bail.objects.filter(location=location).order_by("-created_at").first()
        status = bail_actif.status if bail_actif else DocumentStatus.DRAFT

        location_data = {
            "id": str(location.id),
            "date_debut": location.date_debut.isoformat()
            if location.date_debut
            else None,
            "date_fin": location.date_fin.isoformat() if location.date_fin else None,
            "montant_loyer": montant_loyer,
            "montant_charges": montant_charges,
            "depot_garantie": depot_garantie,
            "status": status,
            "bien": {
                "id": location.bien.id,
                "adresse": location.bien.adresse,
                "type": location.bien.type_bien or "Appartement",
                "superficie": float(location.bien.superficie)
                if location.bien.superficie
                else 0,
                "meuble": location.bien.meuble or False,
            },
            "bailleur": bailleur_data,
        }

        return JsonResponse({"success": True, "location": location_data})

    except Location.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Location non trouvée"}, status=404
        )
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la location: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def create_or_get_bailleur(data):
    """
    Crée ou récupère un bailleur depuis les données du formulaire.
    Les données sont déjà validées par FranceBailSerializer/FranceQuittanceSerializer/FranceEtatLieuxSerializer.
    Retourne le bailleur créé et les autres bailleurs si présents.
    """
    # Les données sont déjà validées, on les utilise directement
    if "bailleur" not in data:
        raise ValueError("Données du bailleur requises")

    validated = data["bailleur"]

    # Vérifier si on doit réutiliser un bailleur existant
    # (PrefillFormState depuis bailleur OU depuis bien)
    bailleur_id = data.get("bailleur_id")  # Au niveau racine
    if bailleur_id:
        try:
            bailleur = Bailleur.objects.get(id=bailleur_id)
            logger.info(f"Réutilisation du bailleur existant: {bailleur_id}")
            # Pas de co-bailleurs en mode réutilisation
            return bailleur, []
        except Bailleur.DoesNotExist:
            logger.warning(
                f"Bailleur {bailleur_id} non trouvé, création d'un nouveau bailleur"
            )

    bailleur_type = validated.get("bailleur_type")
    if not bailleur_type:
        raise ValueError("Type de bailleur requis")

    if bailleur_type == BailleurType.MORALE.value:
        # Créer la société depuis les données validées
        societe_data = validated["societe"]
        societe = Societe.objects.create(
            raison_sociale=societe_data["raison_sociale"],
            forme_juridique=societe_data["forme_juridique"],
            siret=societe_data["siret"],
            adresse=societe_data["adresse"],
            email=societe_data.get("email") or "",
        )

        # Créer le signataire depuis les données validées
        # Pour une société, le signataire est dans "signataire" (transformé par le serializer)
        signataire_data = validated.get("signataire")
        if signataire_data:
            personne_signataire = Personne.objects.create(
                lastName=signataire_data["lastName"],
                firstName=signataire_data["firstName"],
                email=signataire_data["email"],
                adresse=signataire_data.get("adresse") or "",
            )
        else:
            raise ValueError("Données du signataire manquantes pour le bailleur moral")

        bailleur = Bailleur.objects.create(
            societe=societe,
            signataire=personne_signataire,
        )
    else:
        # Créer la personne physique depuis les données validées
        personne_data = validated["personne"]
        personne_bailleur = Personne.objects.create(
            lastName=personne_data["lastName"],
            firstName=personne_data["firstName"],
            email=personne_data["email"],
            adresse=personne_data["adresse"],
            iban=personne_data.get("iban") or "",
        )

        bailleur = Bailleur.objects.create(
            personne=personne_bailleur,
            signataire=personne_bailleur,
        )

    logger.info(f"Bailleur créé: {bailleur.id}")

    # Créer les co-bailleurs si présents
    autres_bailleurs = []
    co_bailleurs_data = validated.get("co_bailleurs") or []
    for co_bailleur_data in co_bailleurs_data:
        personne_autre = Personne.objects.create(
            lastName=co_bailleur_data["lastName"],
            firstName=co_bailleur_data["firstName"],
            email=co_bailleur_data["email"],
            adresse=co_bailleur_data.get("adresse") or "",
        )

        autre_bailleur = Bailleur.objects.create(
            personne=personne_autre,
            signataire=personne_autre,
        )
        autres_bailleurs.append(autre_bailleur)

    return bailleur, autres_bailleurs


def create_mandataire(data):
    """
    Crée un mandataire depuis les données du formulaire.
    Les données sont déjà validées par FranceBailSerializer.
    Retourne le mandataire créé.
    """
    # Les données sont déjà validées, on les utilise directement
    if "mandataire" not in data:
        raise ValueError("Données du mandataire requises")

    validated = data["mandataire"]

    # 1. Créer le signataire (personne physique qui signe pour l'agence)
    signataire_data = validated["signataire"]
    signataire = Personne.objects.create(
        lastName=signataire_data["lastName"],
        firstName=signataire_data["firstName"],
        email=signataire_data["email"],
        adresse=signataire_data.get("adresse"),
    )

    # 2. Créer la société (agence)
    agence_data = validated["agence"]
    agence = Societe.objects.create(
        raison_sociale=agence_data["raison_sociale"],
        forme_juridique=agence_data["forme_juridique"],
        siret=agence_data["siret"],
        adresse=agence_data["adresse"],
        email=agence_data.get("email") or "",
    )

    # 3. Créer le mandataire

    mandataire = Mandataire.objects.create(
        societe=agence,
        signataire=signataire,
        numero_carte_professionnelle=validated.get("numero_carte_professionnelle", ""),
    )
    logger.info(f"Mandataire créé: {mandataire.id}")

    return mandataire


def create_or_update_honoraires_mandataire(location, data, document_type):
    """
    Crée ou met à jour les honoraires mandataire pour une location.
    Système temporel : ferme les honoraires précédents avant d'en créer de nouveaux.

    Args:
        location: Instance de Location
        data: Données validées du formulaire contenant 'honoraires_mandataire'
        document_type: Type de document (SignableDocumentType)

    Returns:
        HonoraireMandataire créé ou None
    """
    if "honoraires_mandataire" not in data:
        logger.info("Pas d'honoraires mandataire dans les données")
        return None

    honoraires_data = data["honoraires_mandataire"]

    # Extraire les données bail
    bail_data = honoraires_data.get("bail", {})
    tarif_bail = bail_data.get("tarif_par_m2")
    part_bailleur_bail = bail_data.get("part_bailleur_pct")

    # Extraire les données EDL
    edl_data = honoraires_data.get("edl", {})

    # Déterminer mandataire_fait_edl automatiquement selon le type de document
    user_role = data.get("user_role")
    mandataire_fait_edl = determine_mandataire_fait_edl(
        user_role, data, document_type=document_type
    )

    tarif_edl = edl_data.get("tarif_par_m2")
    part_bailleur_edl = edl_data.get("part_bailleur_pct")

    # Vérifier s'il y a des données à sauvegarder
    has_bail_data = tarif_bail is not None or part_bailleur_bail is not None
    has_edl_data = (
        mandataire_fait_edl or tarif_edl is not None or part_bailleur_edl is not None
    )

    if not has_bail_data and not has_edl_data:
        logger.info("Pas de données honoraires mandataire à sauvegarder")
        return None

    # 1. Terminer les honoraires actifs précédents (date_fin = None)
    today = timezone.now().date()
    previous_honoraires = HonoraireMandataire.objects.filter(
        location=location,
        date_fin__isnull=True,  # Honoraires actifs (sans date de fin)
    )

    if previous_honoraires.exists():
        # Fermer les honoraires précédents avec date_fin = aujourd'hui
        # (le nouveau commence aujourd'hui, l'ancien se termine aujourd'hui)
        # Respecte la contrainte date_fin >= date_debut
        count = 0
        for honoraire in previous_honoraires:
            honoraire.date_fin = today
            honoraire.save(update_fields=["date_fin", "updated_at"])
            count += 1
        logger.info(
            f"{count} honoraire(s) précédent(s) terminé(s) "
            f"pour location {location.id} (date_fin={today})"
        )

    # 2. Créer les nouveaux honoraires mandataire
    honoraire = HonoraireMandataire.objects.create(
        location=location,
        date_debut=today,
        date_fin=None,  # Illimité par défaut
        # Honoraires bail
        honoraires_bail_par_m2=tarif_bail,
        honoraires_bail_part_bailleur_pct=part_bailleur_bail,
        # Honoraires EDL
        mandataire_fait_edl=mandataire_fait_edl,
        honoraires_edl_par_m2=tarif_edl,
        honoraires_edl_part_bailleur_pct=part_bailleur_edl,
        raison_changement="Création initiale",
    )

    logger.info(f"HonoraireMandataire créé pour location {location.id}: {honoraire.id}")

    return honoraire


def create_locataires(data):
    """
    Crée les locataires depuis les données du formulaire en utilisant les serializers.
    Retourne la liste des locataires créés.
    Les données sont déjà validées par FranceBailSerializer/FranceQuittanceSerializer/FranceEtatLieuxSerializer.

    Si un UUID frontend est fourni (data.locataires[].id), il est utilisé comme PK.
    Sinon Django génère un UUID automatiquement.
    """
    # Les données sont déjà validées, on les utilise directement
    locataires_data = data.get("locataires") or []
    locataires = []

    for validated in locataires_data:
        # Récupérer l'UUID frontend si fourni
        frontend_id = validated.get("id")

        # Préparer les données du locataire
        locataire_data = {
            "lastName": validated["lastName"],
            "firstName": validated["firstName"],
            "email": validated["email"],
            "adresse": validated.get("adresse") or "",
            "date_naissance": validated.get("date_naissance"),
            "profession": validated.get("profession") or "",
            "revenu_mensuel": validated.get("revenus_mensuels"),
            "caution_requise": validated.get("cautionRequise", False),
        }

        if frontend_id:
            import uuid as uuid_module

            # Convertir en UUID si nécessaire
            if isinstance(frontend_id, str):
                frontend_uuid = uuid_module.UUID(frontend_id)
            else:
                frontend_uuid = frontend_id

            # Utiliser get_or_create avec l'UUID fourni
            locataire, created = Locataire.objects.get_or_create(
                id=frontend_uuid, defaults=locataire_data
            )

            if created:
                logger.info(
                    f"Locataire créé: {locataire.id} ({locataire.firstName} {locataire.lastName})"
                )
            else:
                # Mettre à jour les données du locataire existant
                for key, value in locataire_data.items():
                    setattr(locataire, key, value)
                locataire.save()
                logger.info(
                    f"Locataire existant récupéré et mis à jour: {locataire.id} ({locataire.firstName} {locataire.lastName})"
                )

            locataires.append(locataire)
        else:
            # Pas d'UUID fourni, créer un nouveau locataire avec UUID auto-généré
            locataire = Locataire.objects.create(**locataire_data)
            locataires.append(locataire)
            logger.info(
                f"Locataire créé (UUID auto): {locataire.id} ({locataire.firstName} {locataire.lastName})"
            )

    return locataires


def create_garants(data):
    """
    Crée les garants depuis les données du formulaire.
    Les données sont déjà validées par FranceBailSerializer/FranceQuittanceSerializer/FranceEtatLieuxSerializer.
    Retourne la liste des garants créés.
    """
    # Les données sont déjà validées, on les utilise directement
    garants_data = data.get("garants") or []
    garants = []

    for validated in garants_data:
        garant = Personne.objects.create(
            lastName=validated["lastName"],
            firstName=validated["firstName"],
            email=validated["email"],
            adresse=validated.get("adresse") or "",
            date_naissance=validated.get("date_naissance"),
            telephone=validated.get("telephone") or "",
        )
        garants.append(garant)

    return garants


def get_location_fields_from_data(data):
    """
    Extrait les champs de Location depuis les données du formulaire.
    """
    dates = data.get("dates") or {}
    source = data.get("source")

    # Mapper les données vers les champs Location
    fields = {
        "created_from": source,
        "date_debut": dates.get("date_debut"),
        "date_fin": dates.get("date_fin"),
        "solidaires": data.get("solidaires", False),
    }

    # Filtrer les None pour ne garder que les valeurs définies
    return {k: v for k, v in fields.items() if v is not None}


def _extract_rent_terms_data(data, location, serializer_class):
    """
    Extrait et prépare les données pour RentTerms en utilisant les mappings.
    Calcule automatiquement zone_tendue et permis_de_louer si non fournis.
    """
    # Utiliser le mapping automatique pour extraire TOUTES les données RentTerms
    # Cela inclut rent_price_id (mappé depuis bien.localisation.area_id)
    rent_terms_data = serializer_class.extract_model_data(RentTerms, data)

    # Gérer justificatif_complement_loyer depuis modalites_zone_tendue si présent
    modalites_zone_tendue = data.get("modalites_zone_tendue") or {}
    if "justificatif_complement_loyer" in modalites_zone_tendue:
        rent_terms_data["justificatif_complement_loyer"] = modalites_zone_tendue[
            "justificatif_complement_loyer"
        ]

    # Si zone_tendue ou permis_de_louer ne sont pas dans les données extraites,
    # les calculer depuis les coordonnées GPS
    if (
        (
            "zone_tendue" not in rent_terms_data
            or "permis_de_louer" not in rent_terms_data
        )
        and location.bien.latitude
        and location.bien.longitude
    ):
        from rent_control.views import check_zone_status_via_ban

        ban_result = check_zone_status_via_ban(
            location.bien.latitude, location.bien.longitude
        )

        # Ajouter seulement si pas déjà présent
        if "zone_tendue" not in rent_terms_data:
            rent_terms_data["zone_tendue"] = ban_result.get("is_zone_tendue")
        if "permis_de_louer" not in rent_terms_data:
            rent_terms_data["permis_de_louer"] = ban_result.get("is_permis_de_louer")

    return rent_terms_data


def create_rent_terms(location, data, serializer_class):
    """
    Crée les conditions financières pour une nouvelle location.
    """
    fields_data = _extract_rent_terms_data(data, location, serializer_class)

    # Filtrer les None pour ne garder que les valeurs définies
    fields_to_create = {k: v for k, v in fields_data.items() if v is not None}

    if not fields_to_create:
        return None

    rent_terms = RentTerms.objects.create(location=location, **fields_to_create)
    logger.info(f"RentTerms créé pour la location {location.id}")
    return rent_terms


def update_rent_terms(location, data, serializer_class):
    """
    Met à jour les conditions financières d'une location existante.
    Met à jour uniquement les champs non verrouillés.
    """
    if not hasattr(location, "rent_terms"):
        # Si pas de rent_terms existant, en créer un
        return create_rent_terms(location, data, serializer_class)

    rent_terms: RentTerms = location.rent_terms
    country = data.get("country", "FR")

    # Obtenir les steps verrouillées
    from location.services.field_locking import FieldLockingService

    locked_steps = FieldLockingService.get_locked_steps(str(location.id), country)

    # Utiliser le serializer passé en paramètre
    field_to_step_mapping = serializer_class.get_field_to_step_mapping(RentTerms)

    # Extraire les données
    fields_data = _extract_rent_terms_data(data, location, serializer_class)

    # Filtrer les champs verrouillés et les valeurs None
    updated = False
    for field, value in fields_data.items():
        if value is None:
            continue

        step_id = field_to_step_mapping.get(field)
        if step_id and step_id in locked_steps:
            logger.debug(f"Skipping locked field: {field} (step: {step_id})")
            continue

        # Mettre à jour si la valeur est différente
        current_value = getattr(rent_terms, field)
        if current_value != value:
            setattr(rent_terms, field, value)
            updated = True
            logger.debug(f"RentTerms.{field} mis à jour: {current_value} -> {value}")

    if updated:
        rent_terms.save()
        logger.info(f"RentTerms {rent_terms.id} mis à jour")

    return rent_terms


def update_bien_fields(bien, data, serializer_class, location_id=None):
    """
    Met à jour les champs manquants du Bien avec les nouvelles données.
    Met à jour uniquement les champs None/vides ET non verrouillés.
    """
    country = data.get("country", "FR")
    bien_from_form = create_bien_from_form_data(data, serializer_class, save=False)

    # Obtenir les steps verrouillées si location_id est fourni
    locked_steps = set()
    if location_id:
        from location.services.field_locking import FieldLockingService

        locked_steps = FieldLockingService.get_locked_steps(location_id, country)
        if locked_steps:
            logger.info(
                f"Found {len(locked_steps)} locked steps for location {location_id}"
            )

    field_to_step_mapping = serializer_class.get_field_to_step_mapping(Bien)

    updated = False
    for field in bien._meta.get_fields():
        # Ignorer les relations many-to-many et les relations inverses
        if field.many_to_many or field.one_to_many or field.one_to_one:
            continue

        field_name = field.name
        if field_name in ["id", "created_at", "updated_at"]:
            continue

        # Vérifier si le champ est verrouillé
        step_id = field_to_step_mapping.get(field_name)
        if step_id and step_id in locked_steps:
            logger.debug(f"Skipping locked field: {field_name} (step: {step_id})")
            continue

        current_value = getattr(bien, field_name, None)
        new_value = getattr(bien_from_form, field_name, None)

        # Mettre à jour si on a une nouvelle valeur (permettre l'édition des champs non verrouillés)
        # Important: pour les listes, [] est une valeur valide
        if new_value is not None:
            # Comparer pour voir si la valeur a changé
            if current_value != new_value:
                setattr(bien, field_name, new_value)
                updated = True
                logger.debug(
                    f"Bien.{field_name} mis à jour: {current_value} -> {new_value}"
                )

    if updated:
        bien.save()
        logger.info(f"Bien {bien.id} mis à jour avec les nouvelles données")

    return bien


def get_or_create_etat_lieux_for_location(location, validated_data, request):
    """
    Récupère ou crée un état des lieux pour une location.
    Gère également les photos si présentes dans la requête.

    Returns:
        etat_lieux_id: L'ID de l'état des lieux existant ou nouvellement créé
    """
    from etat_lieux.views import (
        extract_photos_with_references,
        update_or_create_etat_lieux,
    )

    # Extraire les photos en utilisant les références depuis validated_data
    photo_references = validated_data.get("photo_references", [])
    uploaded_photos = extract_photos_with_references(request, photo_references)

    # Créer/mettre à jour l'état des lieux avec les photos
    etat_lieux = update_or_create_etat_lieux(
        location.id,
        validated_data,  # Utiliser directement validated_data
        uploaded_photos,  # Photos extraites de la requête
        request.user,
    )

    logger.info(f"État des lieux créé/mis à jour: {etat_lieux.id}")
    return str(etat_lieux.id)


def get_or_create_bail_for_location(location, user_role=None, validated_data=None):
    """
    Récupère ou crée un bail pour une location.

    Args:
        location: Instance de Location
        user_role: Rôle de l'utilisateur (UserRole.BAILLEUR ou UserRole.MANDATAIRE)
        validated_data: Données validées du formulaire (optionnel)

    Returns:
        bail_id: L'ID du bail existant ou nouvellement créé
    """
    from bail.models import Bail

    # Vérifier si un bail DRAFT existe déjà pour cette location
    existing_bail = Bail.objects.filter(
        location=location, status=DocumentStatus.DRAFT
    ).first()

    # Déterminer si le mandataire doit signer
    mandataire_doit_signer = determine_mandataire_doit_signer(user_role, validated_data)

    if existing_bail:
        # Mettre à jour le champ mandataire_doit_signer si nécessaire
        if existing_bail.mandataire_doit_signer != mandataire_doit_signer:
            existing_bail.mandataire_doit_signer = mandataire_doit_signer
            existing_bail.save(update_fields=["mandataire_doit_signer", "updated_at"])
            logger.info(
                f"Bail DRAFT {existing_bail.id} mis à jour "
                f"(mandataire_doit_signer={mandataire_doit_signer})"
            )
        else:
            logger.info(f"Bail DRAFT existant trouvé: {existing_bail.id}")
        return existing_bail.id

    # Créer un nouveau bail
    bail = Bail.objects.create(
        location=location,
        status=DocumentStatus.DRAFT,
        mandataire_doit_signer=mandataire_doit_signer,
    )
    logger.info(
        f"Bail créé automatiquement: {bail.id} "
        f"(mandataire_doit_signer={mandataire_doit_signer})"
    )
    return bail.id


def update_location_fields(location, data, location_id=None):
    """
    Met à jour les champs de la Location avec les nouvelles données.
    Met à jour les champs non verrouillés avec les nouvelles valeurs.
    """
    fields_to_update = get_location_fields_from_data(data)
    country = data.get("country", "FR")

    # Enlever created_from car on ne veut pas le mettre à jour
    fields_to_update.pop("created_from", None)

    # Obtenir les steps verrouillées si location_id est fourni
    locked_steps = set()
    if location_id:
        from location.services.field_locking import FieldLockingService

        locked_steps = FieldLockingService.get_locked_steps(location_id, country)

    # Mapping des champs Location vers les step IDs
    field_to_step_mapping = {
        "date_debut": "dates.date_debut",
        "date_fin": "dates.date_fin",
        "solidaires": "solidaires",
    }

    if not fields_to_update:
        return location

    updated = False
    for field, value in fields_to_update.items():
        # Vérifier si le champ est verrouillé
        step_id = field_to_step_mapping.get(field)
        if step_id and step_id in locked_steps:
            logger.debug(f"Skipping locked field: {field} (step: {step_id})")
            continue

        current_value = getattr(location, field, None)
        # Mettre à jour si la valeur est différente (permettre l'édition)
        if value is not None and current_value != value:
            setattr(location, field, value)
            updated = True
            logger.debug(f"Location.{field} mis à jour: {current_value} -> {value}")

    if updated:
        location.save()
        logger.info(f"Location {location.id} mise à jour avec les nouvelles données")

    return location


def create_new_location(data, serializer_class, location_id, document_type):
    """
    Crée une nouvelle location complète avec toutes les entités associées.

    Args:
        data: Données validées du formulaire
        serializer_class: Classe de serializer à utiliser
        location_id: UUID spécifique à utiliser pour la location
        document_type: Type de document (SignableDocumentType)
    """
    # 1. Créer OU récupérer le bien existant
    # bien_id est au niveau racine (pas dans bien.bien_id)
    bien_id = data.get("bien_id")  # PrefillFormState depuis bien

    if bien_id:
        # Réutiliser le bien existant (mode PrefillFormState depuis bien)
        try:
            bien = Bien.objects.get(id=bien_id)
            logger.info(f"Réutilisation du bien existant: {bien_id}")

            # Mettre à jour le bien avec les nouvelles données
            # Note: Les champs lockés (adresse, type, etc.) ne sont pas dans data
            # car ils ont été filtrés côté frontend (steps cachés)
            # Seuls les champs unlocked_from_bien sont dans data
            update_bien_fields(bien, data, serializer_class, location_id=None)
        except Bien.DoesNotExist:
            logger.warning(f"Bien {bien_id} non trouvé, création d'un nouveau bien")
            bien = create_bien_from_form_data(data, serializer_class, save=True)
    else:
        # Créer un nouveau bien
        bien = create_bien_from_form_data(data, serializer_class, save=True)

    # 2. Déterminer le user_role et créer les entités appropriées
    user_role = data.get("user_role", UserRole.BAILLEUR)
    mandataire_obj = None

    # Créer le mandataire si nécessaire
    if user_role == UserRole.MANDATAIRE:
        mandataire_obj = create_mandataire(data)

    # Créer les bailleurs (commun aux deux parcours)
    bailleur, autres_bailleurs = create_or_get_bailleur(data)

    # Associer les bailleurs au bien
    bien.bailleurs.add(bailleur)
    for autre_bailleur in autres_bailleurs:
        bien.bailleurs.add(autre_bailleur)

    logger.info(
        f"Bailleur principal et {len(autres_bailleurs)} co-bailleur(s) associés"
    )

    # 3. Créer la Location (entité pivot) avec l'ID fourni si disponible
    location_fields = get_location_fields_from_data(data)
    if location_id:
        # Utiliser l'UUID fourni par le frontend (via form-requirements)
        location = Location.objects.create(
            id=location_id, bien=bien, mandataire=mandataire_obj, **location_fields
        )
    else:
        # Laisser Django générer un UUID
        location = Location.objects.create(
            bien=bien, mandataire=mandataire_obj, **location_fields
        )

    # 4. Créer les locataires
    locataires = create_locataires(data)

    # Associer les locataires à la location (utiliser set() pour éviter les doublons)
    if locataires:
        location.locataires.set(locataires)
        logger.info(
            f"{len(locataires)} locataire(s) associé(s) à la location {location.id}"
        )

    # 6. Créer les conditions financières si fournies
    create_rent_terms(location, data, serializer_class=serializer_class)

    # 7. Créer les honoraires mandataire si user_role == MANDATAIRE
    if user_role == UserRole.MANDATAIRE:
        create_or_update_honoraires_mandataire(
            location, data, document_type=document_type
        )

    logger.info(f"Location créée avec succès: {location.id}")
    return location, bien


def update_existing_location(location, data, serializer_class, document_type):
    """
    Met à jour une location existante avec de nouvelles données.
    Complète les données manquantes du bien, de la location et met à jour les conditions financières.

    Args:
        location: Instance de Location existante
        data: Données validées du formulaire
        serializer_class: Classe de serializer à utiliser
        document_type: Type de document (SignableDocumentType)
    """
    # 1. Mettre à jour le Bien avec les champs manquants (en respectant les verrouillages)
    update_bien_fields(
        location.bien,
        data,
        serializer_class,
        location_id=str(location.id),
    )

    # 2. Mettre à jour la Location (dates, solidaires) en respectant les verrouillages
    update_location_fields(location, data, location_id=str(location.id))

    # 3. Créer et associer les locataires si fournis
    locataires_data = data.get("locataires")
    if locataires_data:
        locataires = create_locataires(data)
        # Utiliser set() pour remplacer complètement les locataires (évite les doublons)
        location.locataires.set(locataires)
        logger.info(
            f"{len(locataires)} locataire(s) associé(s) à la location {location.id}"
        )

    # 4. Gérer le mandataire si user_role == MANDATAIRE
    user_role = data.get("user_role")
    if user_role not in [UserRole.BAILLEUR, UserRole.MANDATAIRE]:
        raise ValueError(f"Rôle utilisateur inconnu: {user_role}")
    if user_role == UserRole.MANDATAIRE:
        # Seulement créer un mandataire si la location n'en a pas déjà un
        if not location.mandataire and "mandataire" in data:
            mandataire_obj = create_mandataire(data)
            location.mandataire = mandataire_obj
            location.save(update_fields=["mandataire", "updated_at"])
            logger.info(f"Mandataire créé et associé à la location {location.id}")

        # Créer/mettre à jour les honoraires mandataire si présents
        if "honoraires_mandataire" in data:
            create_or_update_honoraires_mandataire(
                location, data, document_type=document_type
            )

    # 5. Mettre à jour ou créer les conditions financières (incluant dépôt de garantie)
    update_rent_terms(location, data, serializer_class=serializer_class)

    return location, location.bien


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_or_update_location(request):
    """
    Créer ou mettre à jour une location avec les données minimales.
    Peut être appelé depuis bail, quittance ou état des lieux.

    Cette fonction est le point d'entrée central pour créer une Location,
    qui est l'entité pivot du système.
    """
    try:
        # 1. Extraire les données selon le type de requête
        if request.content_type and "multipart/form-data" in request.content_type:
            # Pour multipart, les données sont dans POST['json_data']
            json_data_str = request.POST.get("json_data")
            if not json_data_str:
                return JsonResponse(
                    {"success": False, "error": "json_data requis pour multipart"},
                    status=400,
                )
            data = json.loads(json_data_str)
        else:
            # Pour JSON simple, utiliser request.data
            data = request.data

        # 2. Déterminer le type de document et choisir le serializer approprié
        source = data.get("source")

        serializer_map = {
            "bail": CreateBailSerializer,
            "quittance": CreateQuittanceSerializer,
            "etat_lieux": CreateEtatLieuxSerializer,
        }

        if source not in serializer_map:
            # Si source manquant ou invalide, retourner une erreur claire
            valid_sources = list(serializer_map.keys())
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Le champ 'source' doit être l'un de: {', '.join(valid_sources)}",
                },
                status=400,
            )

        serializer_class = serializer_map[source]
        serializer = serializer_class(data=data)

        if not serializer.is_valid():
            logger.warning(f"Erreurs de validation: {serializer.errors}")
            return JsonResponse(
                {
                    "success": False,
                    "errors": serializer.errors,
                    "message": "Validation des données échouée",
                },
                status=400,
            )

        # 2. Utiliser les données validées
        validated_data = serializer.validated_data
        source = validated_data[
            "source"
        ]  # Garanti par le serializer (required=True ou default)
        location_id = validated_data.get("location_id")
        location = None

        if location_id:
            try:
                location = Location.objects.get(id=location_id)
                logger.info(f"Mise à jour de la location existante: {location_id}")
            except Location.DoesNotExist:
                logger.info(
                    f"Location {location_id} non trouvée, création avec l'UUID fourni"
                )
                location = None

        # Créer ou mettre à jour la location
        if not location:
            # Si on a un location_id spécifique, créer avec cet ID
            location, bien = create_new_location(
                validated_data,
                serializer_class,
                location_id=location_id,
                document_type=source,
            )
        else:
            location, bien = update_existing_location(
                location, validated_data, serializer_class, document_type=source
            )

        # Si la source est 'bail', créer un bail
        user_role = validated_data.get("user_role")
        bail_id = None
        if source == "bail":
            bail_id = get_or_create_bail_for_location(
                location, user_role, validated_data
            )

        # Si la source est 'etat_lieux', créer un état des lieux (avec photos si présentes)
        etat_lieux_id = None
        if source == "etat_lieux":
            etat_lieux_id = get_or_create_etat_lieux_for_location(
                location, validated_data, request
            )

        # Si la source est 'quittance', créer une quittance
        quittance_id = None
        if source == "quittance":
            quittance_id = get_or_create_quittance_for_location(
                location, validated_data
            )

        response_data = {
            "success": True,
            "location_id": str(location.id),
            "bien_id": bien.id,
            "message": f"Location {'créée' if not location_id else 'mise à jour'} avec succès depuis {source}",
        }

        if bail_id:
            response_data["bail_id"] = bail_id

        if etat_lieux_id:
            response_data["etat_lieux_id"] = etat_lieux_id

        if quittance_id:
            response_data["quittance_id"] = quittance_id

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Erreur lors de la création de la location: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_bien_locations(request, bien_id):
    """
    Récupère toutes les locations d'un bien spécifique avec leurs baux associés
    """
    try:
        # Récupérer le bien
        bien = Bien.objects.get(id=bien_id)

        # Vérifier que l'utilisateur a accès à ce bien
        user_email = request.user.email
        has_access = user_has_bien_access(bien, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à ce bien"}, status=403
            )

        # Récupérer toutes les locations du bien
        locations = Location.objects.filter(bien=bien).order_by("-created_at")

        locations_data = []
        for location in locations:
            # Récupérer les locataires
            locataires = [
                {
                    "lastName": locataire.lastName,
                    "firstName": locataire.firstName,
                    "email": locataire.email,
                }
                for locataire in location.locataires.all()
            ]

            # Récupérer les baux associés à cette location
            from bail.models import Bail

            baux = Bail.objects.filter(location=location).order_by("-created_at")

            # Récupérer le bail actif (SIGNING ou SIGNED, ou le plus récent)
            bail_actif = (
                baux.filter(
                    status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED]
                ).first()
                or baux.first()
            )

            # Déterminer le statut global
            status = bail_actif.status if bail_actif else DocumentStatus.DRAFT
            signatures_completes = True
            pdf_url = None
            latest_pdf_url = None

            if bail_actif:
                signatures_completes = not bail_actif.signature_requests.filter(
                    signed=False
                ).exists()

                pdf_url = bail_actif.pdf.url if bail_actif.pdf else None
                latest_pdf_url = (
                    bail_actif.latest_pdf.url if bail_actif.latest_pdf else None
                )

            # Récupérer les montants et le type de charges depuis RentTerms
            montant_loyer = 0
            montant_charges = 0
            depot_garantie = 0
            type_charges = ChargeType.FORFAITAIRES.value  # Valeur par défaut
            if hasattr(location, "rent_terms"):
                montant_loyer = float(location.rent_terms.montant_loyer or 0)
                montant_charges = float(location.rent_terms.montant_charges or 0)
                depot_garantie = float(location.rent_terms.depot_garantie or 0)
                type_charges = (
                    location.rent_terms.type_charges or ChargeType.FORFAITAIRES.value
                )

            location_data = {
                "id": str(location.id),
                "date_debut": location.date_debut.isoformat()
                if location.date_debut
                else None,
                "date_fin": location.date_fin.isoformat()
                if location.date_fin
                else None,
                "montant_loyer": montant_loyer,
                "montant_charges": montant_charges,
                "type_charges": type_charges,
                "depot_garantie": depot_garantie,
                "status": status,
                "locataires": locataires,
                "nombre_baux": baux.count(),
                "bail_actif_id": bail_actif.id if bail_actif else None,
                "signatures_completes": signatures_completes,
                "pdf_url": pdf_url,
                "latest_pdf_url": latest_pdf_url,
                "created_at": location.created_at.isoformat()
                if location.created_at
                else None,
                "created_from": location.created_from,
            }

            locations_data.append(location_data)

        return JsonResponse(
            {
                "success": True,
                "bien": {
                    "id": bien.id,
                    "adresse": bien.adresse,
                    "type": bien.get_type_bien_display(),
                    "superficie": float(bien.superficie) if bien.superficie else None,
                    "meuble": bien.meuble,
                },
                "locations": locations_data,
                "count": len(locations_data),
            }
        )

    except Bien.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": f"Bien {bien_id} introuvable"}, status=404
        )
    except Exception as e:
        logger.error(
            f"Erreur lors de la récupération des locations du bien {bien_id}: {str(e)}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_location_documents(request, location_id):
    """
    Récupère tous les documents associés à une location spécifique:
    - Bail(s)
    - Quittances
    - États des lieux (entrée et sortie)
    """
    try:
        # Récupérer la location
        location = Location.objects.get(id=location_id)

        # Vérifier que l'utilisateur a accès à cette location
        user_email = request.user.email
        has_access = user_has_location_access(location, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à cette location"}, status=403
            )

        documents = []

        # 1. Récupérer les baux associés à cette location
        from bail.models import Bail

        baux = Bail.objects.filter(location=location).order_by("-created_at")

        for bail in baux:
            if bail.pdf or bail.latest_pdf:
                # Déterminer le statut du bail
                status = "Signé" if bail.status == DocumentStatus.SIGNED else "En cours"
                if bail.status == DocumentStatus.DRAFT:
                    status = "Brouillon"

                documents.append(
                    {
                        "id": f"bail-{bail.id}",
                        "type": "bail",
                        "nom": f"Bail - {', '.join([f'{l.firstName} {l.lastName}' for l in location.locataires.all()])}",
                        "date": bail.date_signature.isoformat()
                        if bail.date_signature
                        else bail.created_at.isoformat(),
                        "url": bail.latest_pdf.url if bail.latest_pdf else bail.pdf.url,
                        "status": status,
                    }
                )

        # 2. Récupérer les quittances
        from quittance.models import Quittance

        quittances = Quittance.objects.filter(location=location).order_by(
            "-annee", "-mois"
        )

        for quittance in quittances:
            if quittance.pdf:
                documents.append(
                    {
                        "id": f"quittance-{quittance.id}",
                        "type": "quittance",
                        "nom": f"Quittance - {quittance.mois} {quittance.annee}",
                        "date": quittance.date_paiement.isoformat()
                        if quittance.date_paiement
                        else quittance.created_at.isoformat(),
                        "url": quittance.pdf.url,
                        "status": "Émise",
                        "periode": f"{quittance.mois} {quittance.annee}",
                    }
                )

        # 3. Récupérer les états des lieux
        from etat_lieux.models import EtatLieux

        etats_lieux = EtatLieux.objects.filter(location=location).order_by(
            "-date_etat_lieux"
        )

        for etat in etats_lieux:
            if etat.pdf or etat.latest_pdf:
                type_doc = (
                    "etat_lieux_entree"
                    if etat.type_etat_lieux == "entree"
                    else "etat_lieux_sortie"
                )
                type_label = (
                    "d'entrée" if etat.type_etat_lieux == "entree" else "de sortie"
                )
                nom = f"État des lieux {type_label}"

                # Déterminer le statut via les signatures
                has_signatures = etat.signature_requests.exists()
                all_signed = (
                    not etat.signature_requests.filter(signed=False).exists()
                    if has_signatures
                    else False
                )

                if not has_signatures:
                    status = "Brouillon"
                elif all_signed:
                    status = "Signé"
                else:
                    status = "En cours"

                documents.append(
                    {
                        "id": f"etat-{etat.id}",
                        "type": type_doc,
                        "nom": nom,
                        "date": etat.date_etat_lieux.isoformat()
                        if etat.date_etat_lieux
                        else etat.created_at.isoformat(),
                        "url": etat.latest_pdf.url if etat.latest_pdf else etat.pdf.url,
                        "status": status,
                    }
                )

        # Informations sur la location
        location_info = {
            "id": str(location.id),
            "bien": {
                "id": location.bien.id,
                "adresse": location.bien.adresse,
                "type": location.bien.get_type_bien_display(),
            },
            "locataires": [
                {
                    "lastName": locataire.lastName,
                    "firstName": locataire.firstName,
                    "email": locataire.email,
                }
                for locataire in location.locataires.all()
            ],
            "date_debut": location.date_debut.isoformat()
            if location.date_debut
            else None,
            "date_fin": location.date_fin.isoformat() if location.date_fin else None,
        }

        # Ajouter les informations financières si disponibles
        if hasattr(location, "rent_terms"):
            location_info["montant_loyer"] = float(
                location.rent_terms.montant_loyer or 0
            )
            location_info["montant_charges"] = float(
                location.rent_terms.montant_charges or 0
            )

        return JsonResponse(
            {
                "success": True,
                "location": location_info,
                "documents": documents,
                "count": len(documents),
            }
        )

    except Location.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": f"Location {location_id} introuvable"},
            status=404,
        )
    except Exception as e:
        logger.error(
            f"Erreur lors de la récupération des documents de la location {location_id}: {str(e)}"
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_bail(request, bail_id):
    """
    Annule un bail SIGNING/SIGNED.

    POST /api/location/bails/{bail_id}/cancel/

    Le frontend créera ensuite un nouveau bail via from_location pour correction.

    Returns:
        - success: True
        - location_id: UUID de la location (pour créer nouveau bail)
        - message: Message de confirmation
    """

    try:
        bail = Bail.objects.get(id=bail_id)

        # Vérifier que l'utilisateur est propriétaire du bien
        user_email = request.user.email
        has_access = user_has_bien_access(bail.location.bien, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas les droits pour annuler ce bail"}, status=403
            )

        # Vérifier que le bail est SIGNING ou SIGNED
        if bail.status not in [DocumentStatus.SIGNING, DocumentStatus.SIGNED]:
            return JsonResponse(
                {
                    "error": f"Seuls les baux en signature ou signés peuvent être annulés. Statut actuel: {bail.status}"
                },
                status=400,
            )

        # Annuler le bail
        bail.status = DocumentStatus.CANCELLED.value
        bail.cancelled_at = timezone.now()
        bail.save()

        logger.info(f"Bail {bail_id} annulé par {user_email}")

        return JsonResponse(
            {
                "success": True,
                "location_id": str(bail.location_id),
                "message": "Bail annulé avec succès. Vous pouvez maintenant créer un nouveau bail pour corriger.",
            }
        )

    except Bail.DoesNotExist:
        return JsonResponse({"error": f"Bail {bail_id} introuvable"}, status=404)
    except Exception as e:
        logger.error(f"Erreur lors de l'annulation du bail {bail_id}: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_etat_lieux(request, etat_lieux_id):
    """
    Annule un état des lieux SIGNING/SIGNED.

    POST /api/location/etats-lieux/{etat_lieux_id}/cancel/

    Le frontend créera ensuite un nouvel EDL via from_location pour correction.

    Returns:
        - success: True
        - location_id: UUID de la location (pour créer nouvel EDL)
        - type_etat_lieux: Type de l'EDL annulé ('entree' ou 'sortie')
        - message: Message de confirmation
    """

    try:
        etat_lieux = EtatLieux.objects.get(id=etat_lieux_id)

        # Vérifier que l'utilisateur est propriétaire du bien
        user_email = request.user.email
        has_access = user_has_bien_access(etat_lieux.location.bien, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas les droits pour annuler cet état des lieux"},
                status=403,
            )

        # Vérifier que l'EDL est SIGNING ou SIGNED
        if etat_lieux.status not in [DocumentStatus.SIGNING, DocumentStatus.SIGNED]:
            return JsonResponse(
                {
                    "error": f"Seuls les états des lieux en signature ou signés peuvent être annulés. Statut actuel: {etat_lieux.status}"
                },
                status=400,
            )

        # Annuler l'état des lieux
        etat_lieux.status = DocumentStatus.CANCELLED.value
        etat_lieux.cancelled_at = timezone.now()
        etat_lieux.save()

        logger.info(f"État des lieux {etat_lieux_id} annulé par {user_email}")

        return JsonResponse(
            {
                "success": True,
                "location_id": str(etat_lieux.location_id),
                "type_etat_lieux": etat_lieux.type_etat_lieux,
                "message": "État des lieux annulé avec succès. Vous pouvez maintenant créer un nouvel état des lieux pour corriger.",
            }
        )

    except EtatLieux.DoesNotExist:
        return JsonResponse(
            {"error": f"État des lieux {etat_lieux_id} introuvable"}, status=404
        )
    except Exception as e:
        logger.error(
            f"Erreur lors de l'annulation de l'état des lieux {etat_lieux_id}: {str(e)}"
        )
        return JsonResponse({"error": str(e)}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_quittance(request, quittance_id):
    """
    Annule une quittance (DRAFT, SIGNING ou SIGNED).

    POST /api/location/quittances/{quittance_id}/cancel/

    Contrairement aux bails/états des lieux, les quittances peuvent être annulées à tout moment
    car elles n'ont pas de processus de signature formel et peuvent être régénérées facilement.

    Returns:
        - success: True
        - location_id: UUID de la location
        - message: Message de confirmation
    """

    try:
        quittance = Quittance.objects.get(id=quittance_id)

        # Vérifier que l'utilisateur est propriétaire du bien
        user_email = request.user.email
        has_access = user_has_bien_access(quittance.location.bien, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas les droits pour annuler cette quittance"},
                status=403,
            )

        # Pour les quittances, on peut annuler à tout moment (pas de restriction de statut)
        quittance.status = DocumentStatus.CANCELLED.value
        quittance.cancelled_at = timezone.now()
        quittance.save()

        logger.info(f"Quittance {quittance_id} annulée par {user_email}")

        return JsonResponse(
            {
                "success": True,
                "location_id": str(quittance.location_id),
                "message": "Quittance annulée avec succès",
            }
        )

    except Quittance.DoesNotExist:
        return JsonResponse(
            {"error": f"Quittance {quittance_id} introuvable"}, status=404
        )
    except Exception as e:
        logger.error(
            f"Erreur lors de l'annulation de la quittance {quittance_id}: {str(e)}"
        )
        return JsonResponse({"error": str(e)}, status=500)
