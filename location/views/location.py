import json
import logging

import sentry_sdk
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from assurances.models import InsurancePolicy, StaticDocument
from backend.pdf_utils import get_static_pdf_iframe_url
from bail.models import Bail, Document, DocumentType
from etat_lieux.models import EtatLieux
from location.models import (
    Bien,
    Locataire,
    Location,
)
from location.serializers.france import (
    FranceBailSerializer as CreateBailSerializer,
)
from location.serializers.france import (
    FranceEtatLieuxSerializer as CreateEtatLieuxSerializer,
)
from location.serializers.france import (
    FranceMRHSerializer as CreateMRHSerializer,
)
from location.serializers.france import (
    FranceQuittanceSerializer as CreateQuittanceSerializer,
)

# Sérialiser le bien avec BienReadSerializer + structure nested
from location.serializers.helpers import restructure_bien_to_nested_format

# Utiliser LocationReadSerializer pour chaque location
from location.serializers.read import BienReadSerializer, LocationReadSerializer
from location.services.access_utils import (
    get_user_role_for_location,
    user_has_bien_access,
    user_has_location_access,
)
from location.services.entity_handlers.handlers import (
    create_new_location,
    get_or_create_bail_for_location,
    get_or_create_etat_lieux_for_location,
    update_existing_location,
)
from quittance.models import Quittance
from quittance.views import get_or_create_quittance_for_location
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
            # Sérialiser avec LocationReadSerializer
            serializer = LocationReadSerializer(
                location, context={"user": request.user}
            )
            location_data = serializer.data

            # Ajouter le status
            bail_actif = (
                Bail.objects.filter(
                    location=location,
                    status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED],
                )
                .order_by("-created_at")
                .first()
            ) or Bail.objects.filter(location=location).order_by("-created_at").first()

            location_data["status"] = (
                bail_actif.get_status_display()
                if bail_actif
                else DocumentStatus.DRAFT.label
            )

            locations_data.append(location_data)

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
        location = (
            Location.objects.select_related("bien", "rent_terms")
            .prefetch_related(
                "bien__bailleurs__personne",
                "bien__bailleurs__societe",
                "bien__bailleurs__signataire",
            )
            .get(id=location_id)
        )

        # Vérifier que l'utilisateur a accès à cette location
        user_email = request.user.email
        has_access = user_has_location_access(location, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à cette location"}, status=403
            )

        # Utiliser LocationReadSerializer pour la structure complète
        from location.serializers.read import LocationReadSerializer

        serializer = LocationReadSerializer(location, context={"user": request.user})
        location_data = serializer.data

        # Ajouter le status et bail_actif_id (calculés depuis baux)
        bail_signe = (
            Bail.objects.filter(
                location=location,
                status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED],
            )
            .order_by("-created_at")
            .first()
        )
        bail_actif = (
            bail_signe
            or Bail.objects.filter(location=location).order_by("-created_at").first()
        )

        location_data["status"] = (
            bail_actif.get_status_display()
            if bail_actif
            else DocumentStatus.DRAFT.label
        )
        location_data["bail_actif_id"] = str(bail_signe.id) if bail_signe else None

        return JsonResponse({"success": True, "location": location_data})

    except Location.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Location non trouvée"}, status=404
        )
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la location: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
            "mrh": CreateMRHSerializer,
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
            # Envoyer à Sentry pour tracking des erreurs de validation
            sentry_sdk.capture_message(
                f"Validation échouée pour {source}",
                level="warning",
                extras={
                    "source": source,
                    "errors": serializer.errors,
                    "user_id": request.user.id if request.user else None,
                },
            )
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
        bailleur_principal = None
        if not location:
            # Si on a un location_id spécifique, créer avec cet ID
            location, bien, bailleur_principal = create_new_location(
                validated_data,
                serializer_class,
                location_id=location_id,
                document_type=source,
            )
        else:
            location, bien, bailleur_principal = update_existing_location(
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

        if bailleur_principal:
            response_data["bailleur_id"] = str(bailleur_principal.id)

        if bail_id:
            response_data["bail_id"] = bail_id

        if etat_lieux_id:
            response_data["etat_lieux_id"] = etat_lieux_id

        if quittance_id:
            response_data["quittance_id"] = quittance_id

        # Retourner les IDs des locataires pour permettre les mises à jour ultérieures
        locataire_ids = [str(loc.id) for loc in location.locataires.all()]
        if locataire_ids:
            response_data["locataire_ids"] = locataire_ids
            # Pour MRH (un seul locataire), retourner aussi en singulier
            if source == "mrh" and len(locataire_ids) == 1:
                response_data["locataire_id"] = locataire_ids[0]

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Erreur lors de la création de la location: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_bien_locations(request, bien_id):
    """
    Récupère toutes les locations d'un bien spécifique avec leurs baux associés.
    Retourne format PREFILL/WRITE nested (source de vérité).
    """
    try:
        # Récupérer le bien avec prefetch pour optimiser
        bien = (
            Bien.objects.select_related()
            .prefetch_related("bailleurs__personne", "bailleurs__societe")
            .get(id=bien_id)
        )

        # Vérifier que l'utilisateur a accès à ce bien
        user_email = request.user.email
        has_access = user_has_bien_access(bien, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à ce bien"}, status=403
            )

        bien_serializer = BienReadSerializer(bien)
        bien_data = restructure_bien_to_nested_format(
            bien_serializer.data, calculate_zone_from_gps=False
        )

        # Récupérer toutes les locations du bien avec prefetch
        locations = (
            Location.objects.filter(bien=bien)
            .select_related("rent_terms")
            .prefetch_related("locataires")
            .order_by("-created_at")
        )

        locations_data = []
        for location in locations:
            serializer = LocationReadSerializer(
                location, context={"user": request.user}
            )
            location_data = serializer.data

            # Récupérer les baux associés à cette location
            baux = Bail.objects.filter(location=location).order_by("-created_at")

            # Récupérer le bail actif (SIGNING ou SIGNED, ou le plus récent)
            bail_actif: Bail = (
                baux.filter(
                    status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED]
                ).first()
                or baux.first()
            )

            # Déterminer le statut global
            status = (
                bail_actif.get_status_display()
                if bail_actif
                else DocumentStatus.DRAFT.label
            )

            # Ajouter les champs supplémentaires spécifiques aux baux
            location_data["status"] = status
            location_data["nombre_baux"] = baux.count()
            location_data["bail_actif_id"] = str(bail_actif.id) if bail_actif else None

            if bail_actif:
                signatures_incompletes = bail_actif.signature_requests.filter(
                    signed=False
                ).exists()
                location_data["signatures_completes"] = not signatures_incompletes
                location_data["pdf_url"] = (
                    bail_actif.pdf.url if bail_actif.pdf else None
                )
                location_data["latest_pdf_url"] = (
                    bail_actif.latest_pdf.url if bail_actif.latest_pdf else None
                )
            else:
                location_data["signatures_completes"] = True
                location_data["pdf_url"] = None
                location_data["latest_pdf_url"] = None

            locations_data.append(location_data)

        return JsonResponse(
            {
                "success": True,
                # Structure nested (localisation, caracteristiques, etc.)
                "bien": bien_data,
                # Structure nested (dates, modalites_financieres, etc.)
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
    - Bail(s) avec leurs annexes (diagnostics, permis de louer, MRH, caution)
    - Quittances
    - États des lieux (entrée et sortie) avec leurs photos
    """
    try:
        # Récupérer la location
        location = (
            Location.objects.select_related("bien", "rent_terms")
            .prefetch_related(
                "bien__bailleurs__personne",
                "bien__bailleurs__societe",
                "bien__bailleurs__signataire",
                "locataires",
            )
            .get(id=location_id)
        )

        # Vérifier que l'utilisateur a accès à cette location
        user_email = request.user.email
        has_access = user_has_location_access(location, user_email)

        if not has_access:
            return JsonResponse(
                {"error": "Vous n'avez pas accès à cette location"}, status=403
            )

        # Déterminer le rôle de l'utilisateur pour filtrer les brouillons

        user_roles = get_user_role_for_location(location, user_email)
        is_locataire = user_roles.get("is_locataire", False)

        documents = []

        # 1. Récupérer les baux associés à cette location
        baux = Bail.objects.filter(location=location).order_by("-created_at")

        for bail in baux:
            # Filtrer les brouillons pour les locataires
            if is_locataire and bail.status == DocumentStatus.DRAFT:
                continue

            # Utiliser le label de l'enum directement (source unique de vérité)
            status = bail.get_status_display()

            # Date du bail pour les annexes
            bail_date = (
                bail.date_signature.isoformat()
                if bail.date_signature
                else bail.created_at.isoformat()
            )

            # 1. Ajouter le bail principal
            locataires_names = ", ".join(
                [f"{loc.firstName} {loc.lastName}" for loc in location.locataires.all()]
            )

            # URL du PDF (None si DRAFT sans PDF)
            pdf_url = None
            if bail.latest_pdf:
                pdf_url = bail.latest_pdf.url
            elif bail.pdf:
                pdf_url = bail.pdf.url

            documents.append(
                {
                    "id": f"bail-{bail.id}",
                    "type": "bail",
                    "nom": f"Bail - {locataires_names}",
                    "date": bail_date,
                    "url": pdf_url,
                    "status": status,
                    "location_id": str(location.id),
                    "bail_id": str(bail.id),  # Pour reprendre le DRAFT
                }
            )

            # 2. Ajouter les annexes seulement si le bail est SIGNING ou SIGNED
            if bail.is_locked:
                # Notice d'information (toujours statique, via méthode du modèle)
                documents.append(
                    {
                        "id": f"notice-{bail.id}",
                        "type": "annexe_bail",
                        "nom": "Notice d'information",
                        "date": bail_date,
                        "url": bail.get_notice_information_url(request),
                        "status": "Annexe - Bail",
                    }
                )

                # Documents annexes du bail (diagnostics, permis de louer)
                documents_bail = (
                    Document.objects.filter(bail=bail)
                    .exclude(
                        type_document__in=[
                            DocumentType.ATTESTATION_MRH,
                            DocumentType.CAUTION_SOLIDAIRE,
                        ]
                    )
                    .order_by("type_document")
                )

                # Compter les diagnostics techniques pour la numérotation
                diagnostic_count = documents_bail.filter(
                    type_document=DocumentType.DIAGNOSTIC
                ).count()
                diagnostic_index = 1

                for doc in documents_bail:
                    doc_nom = doc.get_type_document_display()

                    # Si diagnostics techniques et plusieurs, ajouter numérotation
                    if (
                        doc.type_document == DocumentType.DIAGNOSTIC
                        and diagnostic_count > 1
                    ):
                        doc_nom = f"{doc_nom} - {diagnostic_index}"
                        diagnostic_index += 1

                    documents.append(
                        {
                            "id": f"doc-{doc.id}",
                            "type": "annexe_bail",
                            "nom": doc_nom,
                            "date": bail_date,
                            "url": doc.file.url,
                            "status": "Annexe - Bail",
                        }
                    )

                # Documents des locataires (MRH, caution)
                for locataire in location.locataires.all():
                    documents_locataire = Document.objects.filter(
                        locataire=locataire,
                        type_document__in=[
                            DocumentType.ATTESTATION_MRH,
                            DocumentType.CAUTION_SOLIDAIRE,
                        ],
                    ).order_by("type_document")
                    for doc in documents_locataire:
                        # Nom avec prénom/nom du locataire
                        doc_nom = (
                            f"{doc.get_type_document_display()} - "
                            f"{locataire.firstName} {locataire.lastName}"
                        )

                        # Type et statut selon le type de document
                        if doc.type_document == DocumentType.ATTESTATION_MRH:
                            doc_type = "assurance_bail"
                            doc_status = "Assurance"
                        else:  # CAUTION_SOLIDAIRE
                            doc_type = "caution_bail"
                            doc_status = "Caution - Bail"

                        documents.append(
                            {
                                "id": f"loc-doc-{doc.id}",
                                "type": doc_type,
                                "nom": doc_nom,
                                "date": bail_date,
                                "url": doc.file.url,
                                "status": doc_status,
                            }
                        )

                # Avenants au bail
                avenants = bail.avenants.order_by("numero")
                for avenant in avenants:
                    # Filtrer les brouillons pour les locataires
                    if is_locataire and avenant.status == DocumentStatus.DRAFT:
                        continue

                    avenant_date = avenant.created_at.isoformat()
                    pdf_url = None
                    if avenant.latest_pdf:
                        pdf_url = avenant.latest_pdf.url
                    elif avenant.pdf:
                        pdf_url = avenant.pdf.url

                    documents.append(
                        {
                            "id": f"avenant-{avenant.id}",
                            "type": "avenant",
                            "nom": f"Avenant n°{avenant.numero}",
                            "date": avenant_date,
                            "url": pdf_url,
                            "status": avenant.get_status_display(),
                            "avenant_id": str(avenant.id),
                            "bail_id": str(bail.id),
                        }
                    )

                    # Ajouter les annexes de l'avenant si SIGNING ou SIGNED
                    if avenant.is_locked:
                        # Documents annexes de l'avenant (diagnostics, permis de louer)
                        documents_avenant = Document.objects.filter(
                            avenant=avenant
                        ).order_by("type_document")

                        for doc in documents_avenant:
                            doc_nom = doc.get_type_document_display()

                            documents.append(
                                {
                                    "id": f"avenant-doc-{doc.id}",
                                    "type": "annexe_bail",
                                    "nom": doc_nom,
                                    "date": avenant_date,
                                    "url": doc.file.url,
                                    "status": f"Annexe - Avenant n°{avenant.numero}",
                                }
                            )

        # 2. Récupérer les quittances
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
                        "status": quittance.get_status_display(),
                        "periode": f"{quittance.mois} {quittance.annee}",
                        "quittance_id": str(quittance.id),
                    }
                )

        # 3. Récupérer les états des lieux
        etats_lieux = EtatLieux.objects.filter(location=location).order_by(
            "-date_etat_lieux"
        )

        for etat in etats_lieux:
            # Filtrer les brouillons pour les locataires
            if is_locataire and etat.status == DocumentStatus.DRAFT:
                continue

            type_doc = (
                "etat_lieux_entree"
                if etat.type_etat_lieux == "entree"
                else "etat_lieux_sortie"
            )
            type_label = "d'entrée" if etat.type_etat_lieux == "entree" else "de sortie"
            nom = f"État des lieux {type_label}"

            # Utiliser le label de l'enum directement (source unique de vérité)
            status = etat.get_status_display()

            # Date de l'EDL pour les annexes
            edl_date = (
                etat.date_etat_lieux.isoformat()
                if etat.date_etat_lieux
                else etat.created_at.isoformat()
            )

            # URL du PDF (None si DRAFT sans PDF)
            pdf_url = None
            if etat.latest_pdf:
                pdf_url = etat.latest_pdf.url
            elif etat.pdf:
                pdf_url = etat.pdf.url

            # 1. Ajouter l'EDL principal
            documents.append(
                {
                    "id": f"etat-{etat.id}",
                    "type": type_doc,
                    "nom": nom,
                    "date": edl_date,
                    "url": pdf_url,
                    "status": status,
                    "location_id": str(location.id),  # Pour reprendre le DRAFT
                    "etat_lieux_id": str(etat.id),  # Pour édition directe
                }
            )

            # 2. Ajouter les annexes seulement si l'EDL est SIGNING ou SIGNED
            if etat.is_locked:
                # Type d'EDL pour le statut de l'annexe
                edl_type_status = (
                    "Entrée" if etat.type_etat_lieux == "entree" else "Sortie"
                )

                # Grille de vétusté (toujours statique, via méthode du modèle)
                documents.append(
                    {
                        "id": f"grille-edl-{etat.id}",
                        "type": "annexe_edl",
                        "nom": "Grille de vétusté",
                        "date": edl_date,
                        "url": etat.get_grille_vetuste_url(request),
                        "status": f"Annexe - EDL {edl_type_status}",
                    }
                )

        # 4. Documents d'assurance pour le locataire souscripteur
        # Seul le locataire qui a souscrit voit ses documents contractuels
        if is_locataire:
            try:
                # Trouver les polices actives pour cette location
                # où l'utilisateur est souscripteur
                policies = InsurancePolicy.objects.filter(
                    quotation__location=location,
                    subscriber=request.user,
                    status=InsurancePolicy.Status.ACTIVE,
                ).select_related("quotation")

                for policy in policies:
                    product = policy.quotation.product
                    policy_date = (
                        policy.activated_at.isoformat()
                        if policy.activated_at
                        else policy.created_at.isoformat()
                    )

                    # Conditions Particulières (CP) signées
                    if policy.cp_document:
                        documents.append(
                            {
                                "id": f"insurance-cp-{policy.id}",
                                "type": "assurance_bail",
                                "nom": f"Conditions Particulières {product}",
                                "date": policy_date,
                                "url": policy.cp_document.url,
                                "status": "Assurance",
                            }
                        )

                    # Attestation d'assurance
                    if policy.attestation_document:
                        documents.append(
                            {
                                "id": f"insurance-attestation-{policy.id}",
                                "type": "assurance_bail",
                                "nom": f"Attestation d'assurance {product}",
                                "date": policy_date,
                                "url": policy.attestation_document.url,
                                "status": "Assurance",
                            }
                        )

                    # Conditions Générales (CGV)
                    try:
                        cgv_type = f"CGV_{product}"
                        cgv_doc = StaticDocument.objects.filter(
                            document_type=cgv_type
                        ).first()
                        if cgv_doc and cgv_doc.file:
                            documents.append(
                                {
                                    "id": f"insurance-cgv-{policy.id}",
                                    "type": "assurance_bail",
                                    "nom": f"Conditions Générales {product}",
                                    "date": policy_date,
                                    "url": cgv_doc.file.url,
                                    "status": "Assurance",
                                }
                            )
                    except Exception:
                        pass

                    # DIPA (fichier statique)
                    try:
                        dipa_url = get_static_pdf_iframe_url(
                            request, f"assurances/dipa_{product.lower()}.pdf"
                        )
                        if dipa_url:
                            documents.append(
                                {
                                    "id": f"insurance-dipa-{policy.id}",
                                    "type": "assurance_bail",
                                    "nom": f"DIPA {product}",
                                    "date": policy_date,
                                    "url": dipa_url,
                                    "status": "Assurance",
                                }
                            )
                    except Exception:
                        pass

                    # DER (Document d'Entrée en Relation)
                    try:
                        der_doc = StaticDocument.objects.filter(
                            document_type="DER"
                        ).first()
                        if der_doc and der_doc.file:
                            documents.append(
                                {
                                    "id": f"insurance-der-{policy.id}",
                                    "type": "assurance_bail",
                                    "nom": "Document d'Entrée en Relation",
                                    "date": policy_date,
                                    "url": der_doc.file.url,
                                    "status": "Assurance",
                                }
                            )
                    except Exception:
                        pass

            except ImportError:
                # Module assurances non disponible
                pass

        serializer = LocationReadSerializer(location, context={"user": request.user})
        location_info = serializer.data

        # Ajouter bail_actif_id pour le frontend (bouton avenant)
        bail_actif = (
            Bail.objects.filter(
                location=location,
                status__in=[DocumentStatus.SIGNING, DocumentStatus.SIGNED],
            )
            .order_by("-created_at")
            .first()
        )
        location_info["bail_actif_id"] = str(bail_actif.id) if bail_actif else None

        return JsonResponse(
            {
                "success": True,
                # Structure nested (dates, modalites_financieres, etc.)
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

        # Vérifier que le bail est verrouillé (SIGNING ou SIGNED)
        if not bail.is_locked:
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

        # Vérifier que l'EDL est verrouillé (SIGNING ou SIGNED)
        if not etat_lieux.is_locked:
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
