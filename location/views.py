import json
import logging

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from bail.utils import create_bien_from_form_data
from location.models import (
    Bailleur,
    Bien,
    Locataire,
    Location,
    Personne,
    RentTerms,
    Societe,
)
from location.serializers_composed import (
    CreateBailSerializer,
    CreateEtatLieuxSerializer,
    CreateQuittanceSerializer,
)
from quittance.views import get_or_create_quittance_for_location
from rent_control.choices import ChargeType

logger = logging.getLogger(__name__)


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
    bailleur_type = validated.get("bailleur_type")
    if not bailleur_type:
        raise ValueError("Type de bailleur requis")

    if bailleur_type == "morale":
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


def create_locataires(data):
    """
    Crée les locataires depuis les données du formulaire en utilisant les serializers.
    Retourne la liste des locataires créés.
    Les données sont déjà validées par FranceBailSerializer/FranceQuittanceSerializer/FranceEtatLieuxSerializer.
    """
    # Les données sont déjà validées, on les utilise directement
    locataires_data = data.get("locataires") or []
    locataires = []

    for validated in locataires_data:
        locataire = Locataire.objects.create(
            lastName=validated["lastName"],
            firstName=validated["firstName"],
            email=validated["email"],
            adresse=validated.get("adresse") or "",
            date_naissance=validated.get("date_naissance"),
            profession=validated.get("profession") or "",
            revenu_mensuel=validated.get("revenus_mensuels"),
        )

        locataires.append(locataire)
        logger.info(f"Locataire créé: {locataire.id}")

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


def create_or_update_rent_terms(location, data):
    """
    Crée ou met à jour les conditions financières d'une location.
    Met à jour uniquement les champs None avec les nouvelles valeurs.
    Calcule automatiquement zone_tendue et permis_de_louer si non fournis.
    """
    modalites_financieres = data.get("modalites_financieres") or {}
    modalites_zone_tendue = data.get("modalites_zone_tendue") or {}
    bien_data = data.get("bien") or {}
    zone_reglementaire = bien_data.get("zone_reglementaire") or {}

    # Récupérer zone_tendue et permis_de_louer depuis les données
    zone_tendue = zone_reglementaire.get("zone_tendue")
    permis_de_louer = zone_reglementaire.get("permis_de_louer")

    # Si zone_tendue ou permis_de_louer ne sont pas définis, les calculer depuis les coordonnées
    if (
        (zone_tendue is None or permis_de_louer is None)
        and location.bien.latitude
        and location.bien.longitude
    ):
        from rent_control.views import check_zone_status_via_ban

        ban_result = check_zone_status_via_ban(
            location.bien.latitude, location.bien.longitude
        )
        if zone_tendue is None:
            zone_tendue = ban_result.get("is_zone_tendue")
        if permis_de_louer is None:
            permis_de_louer = ban_result.get("is_permis_de_louer")

    # Mapper les données vers les champs RentTerms
    fields_to_update = {
        "montant_loyer": modalites_financieres.get("loyer_hors_charges"),
        "montant_charges": modalites_financieres.get("charges"),
        "type_charges": modalites_financieres.get("type_charges"),
        "jour_paiement": modalites_financieres.get("jour_paiement"),
        "zone_tendue": zone_tendue,
        "permis_de_louer": permis_de_louer,
        "rent_price_id": bien_data.get("localisation", {}).get("area_id"),
        "premiere_mise_en_location": modalites_zone_tendue.get(
            "premiere_mise_en_location"
        ),
        "locataire_derniers_18_mois": modalites_zone_tendue.get(
            "locataire_derniers_18_mois"
        ),
        "dernier_montant_loyer": modalites_zone_tendue.get("dernier_montant_loyer"),
        "justificatif_complement_loyer": modalites_zone_tendue.get(
            "justificatif_complement_loyer"
        ),
    }

    # Filtrer les None pour ne garder que les valeurs définies
    fields_to_update = {k: v for k, v in fields_to_update.items() if v is not None}

    if not fields_to_update:
        return None

    # Récupérer ou créer RentTerms
    if hasattr(location, "rent_terms"):
        rent_terms = location.rent_terms
        # Mettre à jour seulement les champs qui sont None
        for field, value in fields_to_update.items():
            if getattr(rent_terms, field) is None:
                setattr(rent_terms, field, value)
        rent_terms.save()
    else:
        rent_terms = RentTerms.objects.create(location=location, **fields_to_update)

    return rent_terms


def update_bien_fields(bien, data):
    """
    Met à jour les champs manquants du Bien avec les nouvelles données.
    Met à jour uniquement les champs None/vides.
    """
    source = data.get("source")
    bien_from_form = create_bien_from_form_data(data, save=False, source=source)

    updated = False
    for field in bien._meta.get_fields():
        # Ignorer les relations many-to-many et les relations inverses
        if field.many_to_many or field.one_to_many or field.one_to_one:
            continue

        field_name = field.name
        if field_name in ["id", "created_at", "updated_at"]:
            continue

        current_value = getattr(bien, field_name, None)
        new_value = getattr(bien_from_form, field_name, None)

        # Mettre à jour si le champ actuel est None et qu'on a une nouvelle valeur
        # Important: pour les listes, [] est une valeur valide, pas "vide"
        if current_value is None and new_value is not None:
            setattr(bien, field_name, new_value)
            updated = True
            logger.debug(f"Bien.{field_name} mis à jour: {new_value}")

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


def get_or_create_bail_for_location(location):
    """
    Récupère ou crée un bail pour une location.

    Returns:
        bail_id: L'ID du bail existant ou nouvellement créé
    """
    from bail.models import Bail

    # Vérifier si un bail existe déjà pour cette location
    existing_bail = Bail.objects.filter(location=location).first()
    if existing_bail:
        logger.info(f"Bail existant trouvé: {existing_bail.id}")
        return existing_bail.id

    # Créer un nouveau bail
    bail = Bail.objects.create(
        location=location,
        status="draft",
        version=1,
        is_active=True,
    )
    logger.info(f"Bail créé automatiquement: {bail.id}")
    return bail.id


def update_location_fields(location, data):
    """
    Met à jour les champs de la Location avec les nouvelles données.
    Met à jour uniquement les champs None avec les nouvelles valeurs.
    """
    fields_to_update = get_location_fields_from_data(data)

    # Enlever created_from car on ne veut pas le mettre à jour
    fields_to_update.pop("created_from", None)

    if not fields_to_update:
        return location

    updated = False
    for field, value in fields_to_update.items():
        current_value = getattr(location, field, None)
        # Pour solidaires, on met à jour si différent
        if field == "solidaires":
            if current_value != value:
                setattr(location, field, value)
                updated = True
        # Pour les autres champs, on met à jour seulement si None
        elif current_value is None and value is not None:
            setattr(location, field, value)
            updated = True

    if updated:
        location.save()
        logger.info(f"Location {location.id} mise à jour avec les nouvelles données")

    return location


def create_new_location(data):
    """
    Crée une nouvelle location complète avec toutes les entités associées.
    """
    # 1. Créer le bien (peut être partiel selon la source)
    source = data.get("source")
    bien = create_bien_from_form_data(data, save=True, source=source)

    # 2. Créer le bailleur principal et les autres bailleurs
    bailleur, autres_bailleurs = create_or_get_bailleur(data)

    # Associer les bailleurs au bien
    bien.bailleurs.add(bailleur)
    for autre_bailleur in autres_bailleurs:
        bien.bailleurs.add(autre_bailleur)

    # 3. Créer la Location (entité pivot)
    location_fields = get_location_fields_from_data(data)
    location = Location.objects.create(bien=bien, **location_fields)

    # 4. Créer les locataires
    locataires = create_locataires(data)

    # Associer les locataires à la location
    for locataire in locataires:
        location.locataires.add(locataire)

    # 6. Créer les conditions financières si fournies
    create_or_update_rent_terms(location, data)

    logger.info(f"Location créée avec succès: {location.id}")
    return location, bien


def update_existing_location(location, data):
    """
    Met à jour une location existante avec de nouvelles données.
    Complète les données manquantes du bien, de la location et met à jour les conditions financières.
    """
    source = data.get("source")

    # 1. Mettre à jour le Bien avec les champs manquants
    update_bien_fields(location.bien, data)

    # 2. Mettre à jour la Location (dates, solidaires)
    update_location_fields(location, data)

    # 3. Mettre à jour ou créer les conditions financières (incluant dépôt de garantie)
    create_or_update_rent_terms(location, data)

    logger.info(f"Location {location.id} utilisée pour {source}")
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
                logger.warning(
                    f"Location {location_id} non trouvée, création d'une nouvelle"
                )
                location = None

        # Créer ou mettre à jour la location
        if not location:
            location, bien = create_new_location(validated_data)
        else:
            location, bien = update_existing_location(location, validated_data)

        # Si la source est 'bail', créer un bail (seulement s'il n'existe pas déjà)
        bail_id = (
            get_or_create_bail_for_location(location) if source == "bail" else None
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
        has_access = False

        # Vérifier si l'utilisateur est signataire d'un des bailleurs
        for bailleur in bien.bailleurs.all():
            if bailleur.signataire and bailleur.signataire.email == user_email:
                has_access = True
                break

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

            baux = Bail.objects.filter(location=location).order_by("-version")

            # Récupérer le bail actif s'il existe
            bail_actif = baux.filter(is_active=True).first()

            # Déterminer le statut global
            status = bail_actif.status if bail_actif else "draft"
            signatures_completes = True
            pdf_url = None
            latest_pdf_url = None

            if bail_actif:
                signatures_completes = not bail_actif.signature_requests.filter(
                    signed=False
                ).exists()

                from backend.pdf_utils import get_pdf_iframe_url

                pdf_url = (
                    get_pdf_iframe_url(request, bail_actif.pdf)
                    if bail_actif.pdf
                    else None
                )
                latest_pdf_url = (
                    get_pdf_iframe_url(request, bail_actif.latest_pdf)
                    if bail_actif.latest_pdf
                    else None
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
                    "superficie": float(bien.superficie),
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


def _update_location(location, data):
    """
    Met à jour une location existante avec de nouvelles données
    Les données sont déjà validées par le serializer et converties en snake_case
    """
    try:
        # Mettre à jour les dates si fournies
        if "date_debut" in data:
            location.date_debut = data["date_debut"]
        if "date_fin" in data:
            location.date_fin = data["date_fin"]
        if "solidaires" in data:
            location.solidaires = data["solidaires"]  # Déjà un booléen validé

        location.save()

        # Mettre à jour les conditions financières si elles existent
        modalites = data.get("modalites") or {}
        if modalites and hasattr(location, "rent_terms"):
            rent_terms = location.rent_terms
            if "prix" in modalites:
                rent_terms.montant_loyer = modalites["prix"]
            if "charges" in modalites:
                rent_terms.montant_charges = modalites["charges"]
            if "type_charges" in modalites:
                rent_terms.type_charges = modalites["type_charges"]
            if "depot_garantie" in modalites:
                rent_terms.depot_garantie = modalites["depot_garantie"]
            if "justificatif_complement_loyer" in modalites:
                rent_terms.justificatif_complement_loyer = modalites[
                    "justificatif_complement_loyer"
                ]
            rent_terms.save()

        return JsonResponse(
            {
                "success": True,
                "location_id": str(location.id),
                "message": "Location mise à jour avec succès",
            }
        )
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de la location: {str(e)}")
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
        has_access = False

        # Vérifier si l'utilisateur est signataire d'un des bailleurs du bien
        for bailleur in location.bien.bailleurs.all():
            if bailleur.signataire and bailleur.signataire.email == user_email:
                has_access = True
                break

        # Vérifier si l'utilisateur est un des locataires
        if not has_access:
            for locataire in location.locataires.all():
                if locataire.email == user_email:
                    has_access = True
                    break

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à cette location"}, status=403
            )

        documents = []

        # 1. Récupérer les baux associés à cette location
        from bail.models import Bail

        baux = Bail.objects.filter(location=location).order_by("-version")

        for bail in baux:
            if bail.pdf or bail.latest_pdf:
                from backend.pdf_utils import get_pdf_iframe_url

                # Déterminer le statut du bail
                status = "Signé" if bail.status == "signed" else "En cours"
                if bail.status == "draft":
                    status = "Brouillon"

                documents.append(
                    {
                        "id": f"bail-{bail.id}",
                        "type": "bail",
                        "nom": f"Bail v{bail.version} - {', '.join([f'{l.firstName} {l.lastName}' for l in location.locataires.all()])}",
                        "date": bail.date_signature.isoformat()
                        if bail.date_signature
                        else bail.created_at.isoformat(),
                        "url": get_pdf_iframe_url(request, bail.latest_pdf)
                        if bail.latest_pdf
                        else get_pdf_iframe_url(request, bail.pdf),
                        "status": status,
                        "version": bail.version,
                        "is_active": bail.is_active,
                    }
                )

        # 2. Récupérer les quittances
        from quittance.models import Quittance

        quittances = Quittance.objects.filter(location=location).order_by(
            "-annee", "-mois"
        )

        for quittance in quittances:
            if quittance.pdf:
                from backend.pdf_utils import get_pdf_iframe_url

                documents.append(
                    {
                        "id": f"quittance-{quittance.id}",
                        "type": "quittance",
                        "nom": f"Quittance - {quittance.mois} {quittance.annee}",
                        "date": quittance.date_paiement.isoformat()
                        if quittance.date_paiement
                        else quittance.created_at.isoformat(),
                        "url": get_pdf_iframe_url(request, quittance.pdf),
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
                from backend.pdf_utils import get_pdf_iframe_url

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
                        "url": get_pdf_iframe_url(request, etat.latest_pdf)
                        if etat.latest_pdf
                        else get_pdf_iframe_url(request, etat.pdf),
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
