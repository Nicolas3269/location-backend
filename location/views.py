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
    CreateLocationComposedSerializer,
    CreateQuittanceSerializer,
)
from rent_control.choices import ChargeType

logger = logging.getLogger(__name__)


def create_or_get_bailleur(data):
    """
    Crée ou récupère un bailleur depuis les données du formulaire en utilisant les serializers.
    Retourne le bailleur créé et les autres bailleurs si présents.
    """
    from location.serializers_composed import BailleurInfoSerializer

    # Extraire les données du bailleur depuis le format composé
    bailleur_data = data.get("bailleur", {})

    # Valider avec le serializer
    serializer = BailleurInfoSerializer(data=bailleur_data)
    if not serializer.is_valid():
        raise ValueError(f"Données bailleur invalides: {serializer.errors}")

    validated = serializer.validated_data
    bailleur_type = validated.get("bailleur_type", "physique")

    if bailleur_type == "morale":
        # Créer la société depuis les données validées
        societe_data = validated["societe"]
        societe = Societe.objects.create(
            raison_sociale=societe_data["raison_sociale"],
            forme_juridique=societe_data["forme_juridique"],
            siret=societe_data["siret"],
            adresse=societe_data["adresse"],
            email=societe_data.get("email", ""),
        )

        # Créer le signataire depuis les données validées
        # Pour une société, le signataire est dans "signataire" (transformé par le serializer)
        signataire_data = validated.get("signataire", {})
        if signataire_data:
            personne_signataire = Personne.objects.create(
                lastName=signataire_data["lastName"],
                firstName=signataire_data["firstName"],
                email=signataire_data["email"],
                adresse=signataire_data.get("adresse", ""),
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
            iban=personne_data.get("iban", ""),
        )

        bailleur = Bailleur.objects.create(
            personne=personne_bailleur,
            signataire=personne_bailleur,
        )

    logger.info(f"Bailleur créé: {bailleur.id}")

    # Créer les co-bailleurs si présents
    autres_bailleurs = []
    co_bailleurs_data = validated.get("co_bailleurs", [])
    for co_bailleur_data in co_bailleurs_data:
        personne_autre = Personne.objects.create(
            lastName=co_bailleur_data["lastName"],
            firstName=co_bailleur_data["firstName"],
            email=co_bailleur_data["email"],
            adresse=co_bailleur_data.get("adresse", ""),
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
    """
    from location.serializers_composed import LocataireInfoSerializer

    locataires_data = data.get("locataires", [])
    locataires = []

    for loc_data in locataires_data:
        # Valider avec le serializer
        serializer = LocataireInfoSerializer(data=loc_data)
        if not serializer.is_valid():
            raise ValueError(f"Données locataire invalides: {serializer.errors}")

        validated = serializer.validated_data
        locataire = Locataire.objects.create(
            lastName=validated["lastName"],
            firstName=validated["firstName"],
            email=validated["email"],
            adresse=validated.get("adresse", ""),
            date_naissance=validated.get("date_naissance"),
            profession=validated.get("profession", ""),
            revenu_mensuel=validated.get("revenus_mensuels"),
        )

        locataires.append(locataire)
        logger.info(f"Locataire créé: {locataire.id}")

    return locataires


def create_garants(data):
    """
    Crée les garants depuis les données du formulaire.
    Retourne la liste des garants créés.
    """
    from location.serializers_composed import PersonneBaseSerializer

    garants_data = data.get("garants", [])
    garants = []

    for garant_data in garants_data:
        serializer = PersonneBaseSerializer(data=garant_data)
        if not serializer.is_valid():
            raise ValueError(f"Données garant invalides: {serializer.errors}")

        validated = serializer.validated_data
        garant = Personne.objects.create(
            lastName=validated["lastName"],
            firstName=validated["firstName"],
            email=validated["email"],
            adresse=validated.get("adresse", ""),
            date_naissance=validated.get("date_naissance"),
            telephone=validated.get("telephone", ""),
        )
        garants.append(garant)

    return garants


def create_or_update_rent_terms(location, data):
    """
    Crée ou met à jour les conditions financières d'une location en utilisant les serializers.
    """
    from location.serializers_composed import (
        ModalitesFinancieresSerializer,
        ModalitesZoneTendueSerializer,
    )

    # Extraire les modalités financières (format composé uniquement)
    modalites_financieres = data.get("modalites_financieres", {})
    modalites_zone_tendue = data.get("modalites_zone_tendue", {})

    # Pour état des lieux et quittance, les modalités peuvent être incomplètes
    source = data.get("source", "manual")

    # Si pas de loyer défini et qu'on est pas dans un bail, ne pas créer de RentTerms
    if source in ["etat_lieux", "quittance"] and not modalites_financieres.get(
        "loyer_hors_charges"
    ):
        logger.info(
            f"Modalités financières incomplètes pour {source}, skip création RentTerms"
        )
        return

    # Valider les modalités financières
    serializer_fin = ModalitesFinancieresSerializer(data=modalites_financieres)
    if not serializer_fin.is_valid():
        # Pour état des lieux, ignorer si pas de données
        if source == "etat_lieux" and not modalites_financieres:
            return
        raise ValueError(
            f"Données modalités financières invalides: {serializer_fin.errors}"
        )

    modalites_financieres = serializer_fin.validated_data

    # Valider les modalités zone tendue si présentes
    if modalites_zone_tendue:
        serializer_zone = ModalitesZoneTendueSerializer(data=modalites_zone_tendue)
        if not serializer_zone.is_valid():
            raise ValueError(
                f"Données modalités zone tendue invalides: {serializer_zone.errors}"
            )
        modalites_zone_tendue = serializer_zone.validated_data

    # Préparer les données pour RentTerms
    # Extraire zone_reglementaire du bien si présent
    bien_data = data.get("bien", {})
    zone_reglementaire = bien_data.get("zone_reglementaire", {})

    form_data = {
        "montant_loyer": modalites_financieres.get("loyer_hors_charges"),
        "montant_charges": modalites_financieres.get("charges"),
        "type_charges": modalites_financieres.get("type_charges"),
        "depot_garantie": modalites_financieres.get("depot_garantie"),
        "jour_paiement": modalites_financieres.get("jour_paiement"),
        "zone_tendue": zone_reglementaire.get("zone_tendue", False),
        "permis_de_louer": zone_reglementaire.get("permis_de_louer", False),
        "rent_price_id": bien_data.get("localisation", {}).get("area_id"),
        # Nouveaux champs pour zone tendue
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

    # Vérifier si RentTerms existe déjà
    if hasattr(location, "rent_terms"):
        # Mettre à jour l'existant
        rent_terms = location.rent_terms
        updated = False

        # Parcourir les champs et mettre à jour ceux qui sont vides/falsy
        for field, new_value in form_data.items():
            current_value = getattr(rent_terms, field)

            # Détecter si le champ est vide/falsy
            is_empty = (
                current_value is None
                or current_value == ""
                or current_value == 0
                or (
                    field in ["zone_tendue", "permis_de_louer"]
                    and current_value is False
                )
            )

            # Vérifier que la nouvelle valeur n'est pas vide
            # Pour les booléens, on accepte False comme valeur valide
            # Pour rent_price_id, on accepte toute valeur non vide
            has_new_value = new_value is not None and (
                field in ["zone_tendue", "permis_de_louer", "rent_price_id"]
                or (new_value != "" and new_value != 0)
            )

            # Mettre à jour si nécessaire
            if is_empty and has_new_value:
                setattr(rent_terms, field, new_value)
                updated = True
                logger.debug(f"RentTerms - Champ {field} mis à jour: {new_value}")

        if updated:
            rent_terms.save()
            logger.info(f"RentTerms mis à jour pour la location {location.id}")

        return rent_terms
    else:
        # Créer un nouveau RentTerms si au moins une valeur est fournie
        if any(v is not None and v != "" for v in form_data.values()):
            # Définir les valeurs par défaut pour les champs booléens
            form_data["zone_tendue"] = form_data.get("zone_tendue", False)
            form_data["permis_de_louer"] = form_data.get("permis_de_louer", False)
            form_data["justificatif_complement_loyer"] = form_data.get(
                "justificatif_complement_loyer", ""
            )

            rent_terms = RentTerms.objects.create(
                location=location,
                **{k: v for k, v in form_data.items() if v is not None},
            )
            logger.info(f"RentTerms créé pour la location {location.id}")
            return rent_terms

        return None


def create_new_location(data):
    """
    Crée une nouvelle location complète avec toutes les entités associées.
    """
    # 1. Créer le bien (peut être partiel selon la source)
    source = data.get("source", "manual")
    bien = create_bien_from_form_data(data, save=True, source=source)
    logger.info(f"Bien créé: {bien.id}")

    # 2. Créer le bailleur principal et les autres bailleurs
    bailleur, autres_bailleurs = create_or_get_bailleur(data)

    # Associer les bailleurs au bien
    bien.bailleurs.add(bailleur)
    for autre_bailleur in autres_bailleurs:
        bien.bailleurs.add(autre_bailleur)

    # 3. Créer les locataires
    locataires = create_locataires(data)

    # 4. Créer la Location (entité pivot)
    source = data.get("source", "manual")
    # Récupérer les dates depuis dates.date_debut/date_fin
    dates_data = data.get("dates", {})
    location = Location.objects.create(
        bien=bien,
        created_from=source,
        date_debut=dates_data.get("date_debut"),
        date_fin=dates_data.get("date_fin"),
        solidaires=data.get("solidaires", False),
    )

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
    Complète les données manquantes du bien et met à jour les conditions financières.
    """
    bien = location.bien

    # Créer un objet Bien temporaire avec les données du formulaire
    source = data.get("source", "manual")
    bien_from_form = create_bien_from_form_data(data, save=False, source=source)

    # Liste des champs à mettre à jour automatiquement
    fields_to_update = [
        "superficie",
        "periode_construction",
        "type_bien",
        "meuble",
        "etage",
        "porte",
        "classe_dpe",
        "depenses_energetiques",
        "pieces_info",
        "chauffage_type",
        "chauffage_energie",
        "eau_chaude_type",
        "eau_chaude_energie",
        "annexes_privatives",
        "annexes_collectives",
        "information",
        "identifiant_fiscal",
        "regime_juridique",
    ]

    updated = False

    # Parcourir tous les champs et mettre à jour ceux qui sont vides/falsy
    for field in fields_to_update:
        current_value = getattr(bien, field)
        new_value = getattr(bien_from_form, field)

        # Détecter si le champ est vide/falsy
        is_empty = (
            current_value is None
            or current_value == ""
            or current_value == []
            or current_value == {}
            or (field == "superficie" and current_value == 0)
            or (field == "classe_dpe" and current_value == "NA")
        )

        # Vérifier que la nouvelle valeur n'est pas vide
        has_new_value = (
            new_value is not None
            and new_value != ""
            and new_value != []
            and new_value != {}
            and not (field == "superficie" and new_value == 0)
            and not (field == "classe_dpe" and new_value == "NA")
        )

        # Mettre à jour si nécessaire
        if is_empty and has_new_value:
            setattr(bien, field, new_value)
            updated = True
            logger.debug(f"Champ {field} mis à jour: {new_value}")

    # Sauvegarder si des modifications ont été faites
    if updated:
        bien.save()
        logger.info(f"Bien {bien.id} mis à jour avec les nouvelles données")

    # Mettre à jour ou créer les conditions financières si elles sont fournies
    create_or_update_rent_terms(location, data)

    source = data.get("source", "manual")
    logger.info(f"Location {location.id} utilisée pour {source}")

    return location, bien


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
        # 1. Déterminer le type de document et choisir le serializer approprié
        source = request.data.get("source", "manual")

        serializer_map = {
            "bail": CreateBailSerializer,
            "quittance": CreateQuittanceSerializer,
            "etat_lieux": CreateEtatLieuxSerializer,
            "manual": CreateLocationComposedSerializer,
        }

        serializer_class = serializer_map.get(source, CreateLocationComposedSerializer)
        serializer = serializer_class(data=request.data)

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
        source = validated_data.get("source", "manual")

        # 3. Vérifier si on met à jour une location existante
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
        bail_id = None
        if source == "bail":
            from bail.models import Bail

            # Vérifier si un bail existe déjà pour cette location
            existing_bail = Bail.objects.filter(location=location).first()
            if existing_bail:
                bail_id = existing_bail.id
                logger.info(f"Bail existant trouvé: {bail_id}")
            else:
                bail = Bail.objects.create(
                    location=location,
                    status="draft",
                    version=1,
                    is_active=True,
                )
                bail_id = bail.id
                logger.info(f"Bail créé automatiquement: {bail.id}")

        response_data = {
            "success": True,
            "location_id": str(location.id),
            "bien_id": bien.id,
            "message": f"Location {'créée' if not location_id else 'mise à jour'} avec succès depuis {source}",
        }

        if bail_id:
            response_data["bail_id"] = bail_id

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
        modalites = data.get("modalites", {})
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
