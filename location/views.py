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
from rent_control.choices import ChargeType

logger = logging.getLogger(__name__)


def create_or_get_bailleur(data):
    """
    Crée ou récupère un bailleur depuis les données du formulaire.
    Retourne le bailleur créé et les autres bailleurs si présents.
    """
    landlord_data = data.get("landlord", {})
    bailleur_type = data.get("bailleur_type", "physique")

    if bailleur_type == "morale":
        # Créer la société
        societe_data = data.get("societe", {})
        societe = Societe.objects.create(
            raison_sociale=societe_data.get("raisonSociale", ""),
            forme_juridique=societe_data.get("formeJuridique", ""),
            siret=data.get("siret", ""),
            adresse=societe_data.get("adresse", ""),
            email=landlord_data.get("email", ""),
        )

        # Créer le signataire
        personne_signataire = Personne.objects.create(
            nom=landlord_data.get("lastName", ""),
            prenom=landlord_data.get("firstName", ""),
            email=landlord_data.get("email", ""),
            adresse=landlord_data.get("address", ""),
        )

        bailleur = Bailleur.objects.create(
            societe=societe,
            signataire=personne_signataire,
        )
    else:
        # Créer la personne physique
        personne_bailleur = Personne.objects.create(
            nom=landlord_data.get("lastName", ""),
            prenom=landlord_data.get("firstName", ""),
            email=landlord_data.get("email", ""),
            adresse=landlord_data.get("address", ""),
        )

        bailleur = Bailleur.objects.create(
            personne=personne_bailleur,
            signataire=personne_bailleur,
        )

    logger.info(f"Bailleur créé: {bailleur.id}")

    # Créer les autres bailleurs si présents
    autres_bailleurs = []
    other_landlords = data.get("other_landlords", [])
    for other_data in other_landlords:
        personne_autre = Personne.objects.create(
            nom=other_data.get("lastName", ""),
            prenom=other_data.get("firstName", ""),
            email=other_data.get("email", ""),
            adresse=other_data.get("address", ""),
        )

        autre_bailleur = Bailleur.objects.create(
            personne=personne_autre,
            signataire=personne_autre,
        )
        autres_bailleurs.append(autre_bailleur)

    return bailleur, autres_bailleurs


def create_locataires(data):
    """
    Crée les locataires depuis les données du formulaire.
    Retourne la liste des locataires créés.
    """
    locataires_data = data.get("locataires", [])
    locataires = []

    for loc_data in locataires_data:
        locataire = Locataire.objects.create(
            nom=loc_data.get("lastName", ""),
            prenom=loc_data.get("firstName", ""),
            email=loc_data.get("email", ""),
            adresse=loc_data.get("address", ""),
        )
        locataires.append(locataire)
        logger.info(f"Locataire créé: {locataire.id}")

    return locataires


def create_garants(data):
    """
    Crée les garants depuis les données du formulaire.
    Retourne la liste des garants créés.
    """
    garants_data = data.get("garants", [])
    garants = []

    for garant_data in garants_data:
        garant = Personne.objects.create(
            nom=garant_data.get("lastName", ""),
            prenom=garant_data.get("firstName", ""),
            email=garant_data.get("email", ""),
            adresse=garant_data.get("address", ""),
        )
        garants.append(garant)

    return garants


def create_or_update_rent_terms(location, data):
    """
    Crée ou met à jour les conditions financières d'une location.
    """
    modalites = data.get("modalites", {})

    # Valider le type de charges
    type_charges_value = modalites.get("typeCharges")
    if type_charges_value and type_charges_value not in [
        choice.value for choice in ChargeType
    ]:
        type_charges_value = ChargeType.FORFAITAIRES.value

    # Préparer les données depuis le formulaire
    form_data = {
        "montant_loyer": modalites.get("prix"),
        "montant_charges": modalites.get("charges"),
        "type_charges": type_charges_value,
        "depot_garantie": data.get("deposit"),
        "jour_paiement": data.get("paymentDay"),
        "zone_tendue": data.get("zoneTendue"),
        "permis_de_louer": data.get("permisDeLouer"),
        "rent_price_id": data.get("areaId"),
        "justificatif_complement_loyer": modalites.get("justificationPrix"),
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
            has_new_value = new_value is not None and (
                field in ["zone_tendue", "permis_de_louer"]
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
    bien = create_bien_from_form_data(data, save=True)
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
    location = Location.objects.create(
        bien=bien,
        created_from=source,
        date_debut=data.get("startDate"),
        solidaires=data.get("solidaires", False),
    )

    # Associer les locataires à la location
    for locataire in locataires:
        location.locataires.add(locataire)

    # 5. Ajouter les garants si présents
    garants = create_garants(data)
    for garant in garants:
        location.garants.add(garant)

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
    bien_from_form = create_bien_from_form_data(data, save=False)

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
        data = request.data

        # Vérifier si on met à jour une location existante
        location_id = data.get("location_id")
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
            location, bien = create_new_location(data)
        else:
            location, bien = update_existing_location(location, data)

        # Si la source est 'bail', créer un bail (seulement s'il n'existe pas déjà)
        bail_id = None
        if data.get("source") == "bail":
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
            "message": f"Location {'créée' if not location_id else 'mise à jour'} avec succès depuis {data.get('source', 'manual')}",
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
                    "nom": locataire.nom,
                    "prenom": locataire.prenom,
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
                        "nom": f"Bail v{bail.version} - {', '.join([f'{l.prenom} {l.nom}' for l in location.locataires.all()])}",
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
                    "nom": locataire.nom,
                    "prenom": locataire.prenom,
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
