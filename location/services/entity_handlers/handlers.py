import logging
from typing import Any, Dict, Optional

from django.utils import timezone

from bail.models import Bail
from bail.utils import create_bien_from_form_data
from location.constants import UserRole
from location.models import (
    Adresse,
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
from location.services.document_utils import (
    determine_mandataire_doit_signer,
    determine_mandataire_fait_edl,
)
from location.services.form_handlers.field_locking import FieldLockingService
from rent_control.views import check_zone_status_via_ban
from signature.document_status import DocumentStatus

logger = logging.getLogger(__name__)


def adresses_are_equal(addr1: Optional[Adresse], addr2: Optional[Adresse]) -> bool:
    """Compare deux adresses par leur contenu, pas par référence."""
    if addr1 is None or addr2 is None:
        return addr1 is addr2
    return (
        addr1.voie == addr2.voie
        and addr1.numero == addr2.numero
        and addr1.complement == addr2.complement
        and addr1.code_postal == addr2.code_postal
        and addr1.ville == addr2.ville
        and addr1.pays == addr2.pays
    )


def _get_or_create_adresse(adresse_data: Dict[str, Any]) -> Optional[Adresse]:
    """
    Récupère ou crée une Adresse depuis un dictionnaire structuré.

    Args:
        adresse_data: Dict avec numero, voie, code_postal, ville, pays (optionnel)

    Returns:
        Instance d'Adresse existante ou nouvelle, None si données insuffisantes
    """
    if not adresse_data or not isinstance(adresse_data, dict):
        return None

    voie = adresse_data.get("voie")
    ville = adresse_data.get("ville")

    # Minimum requis: ville (voie optionnelle pour ZI/ZA)
    if not ville:
        logger.debug("Adresse incomplète, ignorée (ville manquante)")
        return None

    numero = adresse_data.get("numero")
    code_postal = adresse_data.get("code_postal")
    pays = adresse_data.get("pays") or "FR"
    complement = adresse_data.get("complement")
    latitude = adresse_data.get("latitude")
    longitude = adresse_data.get("longitude")

    # Chercher adresse existante pour éviter doublons
    existing = Adresse.objects.filter(
        numero=numero,
        voie=voie,
        code_postal=code_postal,
        ville=ville,
        pays=pays,
    ).first()

    if existing:
        logger.debug(f"Adresse existante réutilisée: {existing.id}")
        return existing

    # Créer nouvelle adresse
    adresse = Adresse.objects.create(
        numero=numero,
        voie=voie,
        complement=complement,
        code_postal=code_postal,
        ville=ville,
        pays=pays,
        latitude=latitude,
        longitude=longitude,
    )
    logger.info(f"Adresse créée: {adresse.id}")
    return adresse


def _update_personne_if_changed(personne: Personne, personne_data: dict) -> bool:
    """
    Met à jour une Personne si les données ont changé.
    Compatible avec django-simple-history pour historisation automatique.

    Returns:
        True si des changements ont été effectués, False sinon
    """
    changed = False
    # Champs simples (pas adresse qui est maintenant FK)
    fields_to_check = ["lastName", "firstName", "email", "iban"]

    for field in fields_to_check:
        new_value = personne_data.get(field, "")
        current_value = getattr(personne, field, "")
        if new_value != current_value:
            setattr(personne, field, new_value)
            changed = True
            logger.debug(f"  {field}: '{current_value}' → '{new_value}'")

    # Gérer l'adresse FK séparément
    adresse_value = personne_data.get("adresse")
    if adresse_value and isinstance(adresse_value, dict):
        adresse_obj = _get_or_create_adresse(adresse_value)
        if adresse_obj and personne.adresse != adresse_obj:
            personne.adresse = adresse_obj
            changed = True
            logger.debug(f"  adresse: → '{adresse_obj}'")

    if changed:
        personne.save()
    return changed


def _update_societe_if_changed(societe: Societe, societe_data: dict) -> bool:
    """
    Met à jour une Société si les données ont changé.
    Compatible avec django-simple-history pour historisation automatique.

    Returns:
        True si des changements ont été effectués, False sinon
    """
    changed = False
    # Champs simples (pas adresse qui est maintenant FK)
    fields_to_check = ["raison_sociale", "forme_juridique", "siret", "email"]

    for field in fields_to_check:
        new_value = societe_data.get(field, "")
        current_value = getattr(societe, field, "")
        if new_value != current_value:
            setattr(societe, field, new_value)
            changed = True
            logger.debug(f"  {field}: '{current_value}' → '{new_value}'")

    # Gérer l'adresse FK séparément
    adresse_value = societe_data.get("adresse")
    if adresse_value and isinstance(adresse_value, dict):
        adresse_obj = _get_or_create_adresse(adresse_value)
        if adresse_obj and societe.adresse != adresse_obj:
            societe.adresse = adresse_obj
            changed = True
            logger.debug(f"  adresse: → '{adresse_obj}'")

    if changed:
        societe.save()
    return changed


def _create_or_get_personne(personne_data: dict, include_iban: bool = True) -> Personne:
    """
    Crée ou récupère une Personne par ID.

    Args:
        personne_data: Dict avec id (optionnel), lastName, firstName,
                       email, adresse (structurée), iban
        include_iban: Si True, inclut le champ IBAN (pour bailleur).
                      Si False, l'exclut (pour signataire).

    Returns:
        Instance de Personne (réutilisée ou créée)
    """
    personne_id = personne_data.get("id")

    # Préparer les données communes
    create_data = {
        "lastName": personne_data["lastName"],
        "firstName": personne_data["firstName"],
        "email": personne_data["email"],
    }

    # Gérer l'adresse : dict structuré → créer FK Adresse
    adresse_value = personne_data.get("adresse")
    if adresse_value and isinstance(adresse_value, dict):
        adresse_obj = _get_or_create_adresse(adresse_value)
        if adresse_obj:
            create_data["adresse"] = adresse_obj

    # Ajouter IBAN seulement si demandé
    if include_iban:
        create_data["iban"] = personne_data.get("iban", "")

    if personne_id:
        try:
            personne = Personne.objects.get(id=personne_id)
            logger.info(f"✅ Personne existante réutilisée: {personne_id}")
            return personne
        except Personne.DoesNotExist:
            logger.warning(f"⚠️ Personne {personne_id} introuvable, création...")

    personne = Personne.objects.create(**create_data)
    logger.info(f"✨ Personne créée: {personne.id}")
    return personne


def _create_or_get_societe(societe_data: dict) -> Societe:
    """
    Crée ou récupère une Société par ID.

    Args:
        societe_data: Dict avec id (optionnel), raison_sociale,
                      forme_juridique, siret, adresse (structurée), email

    Returns:
        Instance de Societe (réutilisée ou créée)
    """
    societe_id = societe_data.get("id")

    create_data = {
        "raison_sociale": societe_data["raison_sociale"],
        "forme_juridique": societe_data["forme_juridique"],
        "siret": societe_data["siret"],
        "email": societe_data.get("email", ""),
    }

    # Gérer l'adresse : dict structuré → créer FK Adresse
    adresse_value = societe_data.get("adresse")
    if adresse_value and isinstance(adresse_value, dict):
        adresse_obj = _get_or_create_adresse(adresse_value)
        if adresse_obj:
            create_data["adresse"] = adresse_obj

    if societe_id:
        try:
            societe = Societe.objects.get(id=societe_id)
            logger.info(f"✅ Société existante réutilisée: {societe_id}")
            return societe
        except Societe.DoesNotExist:
            logger.warning(f"⚠️ Société {societe_id} introuvable, création...")

    societe = Societe.objects.create(**create_data)
    logger.info(f"✨ Société créée: {societe.id}")
    return societe


def _create_or_get_signataire(signataire_data: dict) -> Personne:
    """
    Crée ou récupère un signataire (Personne sans IBAN) par ID.

    Args:
        signataire_data: Dict avec id (optionnel), lastName, firstName,
                         email, adresse

    Returns:
        Instance de Personne (réutilisée ou créée)
    """
    return _create_or_get_personne(signataire_data, include_iban=False)


def _create_or_get_single_bailleur(bailleur_data: dict) -> Bailleur:
    """
    Helper: Crée ou récupère un bailleur unique depuis ses données.
    Met à jour le bailleur existant si les données ont changé.
    Gère le changement de type (PHYSIQUE ↔ MORALE).

    Args:
        bailleur_data: Dict avec id (optionnel), bailleur_type,
                       personne/societe/signataire

    Returns:
        Instance de Bailleur (réutilisée/mise à jour ou créée)
    """
    # 1. Vérifier si on doit réutiliser un bailleur existant
    bailleur_id = bailleur_data.get("id")
    if bailleur_id:
        try:
            bailleur = Bailleur.objects.select_related(
                "personne", "societe", "signataire"
            ).get(id=bailleur_id)
            logger.info(f"✅ Bailleur existant trouvé: {bailleur_id}")

            # ✅ Mettre à jour les données si nécessaire
            bailleur_type = bailleur_data.get("bailleur_type")
            updated = False

            # ✅ Détecter changement de type (PHYSIQUE ↔ MORALE)
            if bailleur.bailleur_type != bailleur_type:
                logger.info(
                    f"🔄 Changement de type : "
                    f"{bailleur.bailleur_type} → {bailleur_type}"
                )

                # Nettoyer les anciennes FK
                if bailleur.bailleur_type == BailleurType.PHYSIQUE.value:
                    # Ancien = PHYSIQUE, nouveau = MORALE
                    bailleur.personne = None
                else:
                    # Ancien = MORALE, nouveau = PHYSIQUE
                    bailleur.societe = None
                    bailleur.signataire = None

                # Mettre à jour le type
                bailleur.bailleur_type = bailleur_type

                # Créer/réutiliser les nouvelles entités selon le nouveau type
                if bailleur_type == BailleurType.PHYSIQUE.value:
                    personne_data = bailleur_data.get("personne")
                    if not personne_data:
                        raise ValueError("Personne requise pour bailleur physique")

                    bailleur.personne = _create_or_get_personne(personne_data)
                    # Note: Pour un bailleur physique, pas de signataire distinct
                    # La personne signe elle-même
                    bailleur.signataire = None

                elif bailleur_type == BailleurType.MORALE.value:
                    # Créer/réutiliser société
                    societe_data = bailleur_data.get("societe")
                    if not societe_data:
                        raise ValueError("Société requise pour bailleur moral")

                    bailleur.societe = _create_or_get_societe(societe_data)

                    # Créer/réutiliser signataire
                    signataire_data = bailleur_data.get("signataire")
                    if not signataire_data:
                        raise ValueError("Signataire requis pour bailleur moral")

                    bailleur.signataire = _create_or_get_signataire(signataire_data)

                bailleur.save()
                updated = True

            # Pas de changement de type, juste mettre à jour les données existantes
            elif bailleur_type == BailleurType.PHYSIQUE.value and bailleur.personne:
                personne_data = bailleur_data.get("personne")
                if personne_data:
                    if _update_personne_if_changed(bailleur.personne, personne_data):
                        updated = True

            elif bailleur_type == BailleurType.MORALE.value:
                # Mettre à jour la société
                societe_data = bailleur_data.get("societe")
                if societe_data and bailleur.societe:
                    if _update_societe_if_changed(bailleur.societe, societe_data):
                        updated = True

                # Mettre à jour le signataire
                signataire_data = bailleur_data.get("signataire")
                if signataire_data and bailleur.signataire:
                    if _update_personne_if_changed(
                        bailleur.signataire, signataire_data
                    ):
                        updated = True

            if updated:
                logger.info(f"🔄 Bailleur {bailleur_id} mis à jour")

            return bailleur
        except Bailleur.DoesNotExist:
            logger.warning(f"⚠️ Bailleur {bailleur_id} introuvable, création...")

    # 2. Créer un nouveau bailleur (pas de bailleur_id fourni)
    bailleur_type = bailleur_data.get("bailleur_type")
    if not bailleur_type:
        raise ValueError("Type de bailleur requis")

    if bailleur_type == BailleurType.MORALE.value:
        # Créer ou réutiliser société
        societe_data = bailleur_data["societe"]
        societe = _create_or_get_societe(societe_data)

        # Créer ou réutiliser signataire
        signataire_data = bailleur_data.get("signataire")
        if not signataire_data:
            raise ValueError("Signataire requis pour bailleur moral")

        personne_signataire = _create_or_get_signataire(signataire_data)

        bailleur = Bailleur.objects.create(
            societe=societe,
            signataire=personne_signataire,
        )
    else:
        # Créer ou réutiliser personne physique
        personne_data = bailleur_data["personne"]
        personne_bailleur = _create_or_get_personne(personne_data)

        # Note: Pour un bailleur physique, pas de signataire distinct
        # La personne signe elle-même
        bailleur = Bailleur.objects.create(
            personne=personne_bailleur,
            signataire=None,
        )

    logger.info(f"✨ Bailleur créé: {bailleur.id}")
    return bailleur


def create_or_get_bailleur(data):
    """
    Crée ou récupère un bailleur depuis les données du formulaire.
    Les données sont déjà validées par les serializers.
    Retourne le bailleur principal et les co-bailleurs.
    """
    # Les données sont déjà validées, on les utilise directement
    if "bailleur" not in data:
        raise ValueError("Données du bailleur requises")

    bailleur_data = data["bailleur"]

    # 1. Bailleur principal (réutilisé ou créé selon présence de l'ID)
    bailleur = _create_or_get_single_bailleur(bailleur_data)

    # 2. Co-bailleurs (au même niveau que bailleur principal)
    autres_bailleurs = []
    co_bailleurs_data = data.get("co_bailleurs") or []  # ✅ Même niveau
    for co_bailleur_data in co_bailleurs_data:
        # ✅ Réutiliser le même helper pour chaque co-bailleur
        autre_bailleur = _create_or_get_single_bailleur(co_bailleur_data)
        autres_bailleurs.append(autre_bailleur)

    logger.info(f"✅ Bailleur principal + {len(autres_bailleurs)} co-bailleur(s)")
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
    signataire_create_data = {
        "lastName": signataire_data["lastName"],
        "firstName": signataire_data["firstName"],
        "email": signataire_data["email"],
    }
    # Gérer l'adresse : dict structuré → créer FK Adresse
    adresse_signataire = signataire_data.get("adresse")
    if adresse_signataire and isinstance(adresse_signataire, dict):
        adresse_obj = _get_or_create_adresse(adresse_signataire)
        if adresse_obj:
            signataire_create_data["adresse"] = adresse_obj

    signataire = Personne.objects.create(**signataire_create_data)

    # 2. Créer la société (agence)
    agence_data = validated["agence"]
    agence_create_data = {
        "raison_sociale": agence_data["raison_sociale"],
        "forme_juridique": agence_data["forme_juridique"],
        "siret": agence_data["siret"],
        "email": agence_data.get("email") or "",
    }
    # Gérer l'adresse : dict structuré → créer FK Adresse
    adresse_agence = agence_data.get("adresse")
    if adresse_agence and isinstance(adresse_agence, dict):
        adresse_obj = _get_or_create_adresse(adresse_agence)
        if adresse_obj:
            agence_create_data["adresse"] = adresse_obj

    agence = Societe.objects.create(**agence_create_data)

    # 3. Créer le mandataire
    mandataire = Mandataire.objects.create(
        societe=agence,
        signataire=signataire,
        numero_carte_professionnelle=validated.get("numero_carte_professionnelle", ""),
    )
    logger.info(f"Mandataire créé: {mandataire.id}")

    return mandataire


def create_or_update_honoraires_mandataire(location: Location, data, document_type):
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
    Les données sont déjà validées par FranceBailSerializer/FranceQuittanceSerializer/FranceEtatLieuxSerializer/FranceMRHSerializer.

    Si un UUID frontend est fourni (data.locataires[].id), il est utilisé comme PK.
    Sinon Django génère un UUID automatiquement.

    Supporte deux formats:
    - locataires: liste de locataires (bail, quittance, EDL)
    - locataire: un seul locataire (MRH)
    """
    # Les données sont déjà validées, on les utilise directement
    locataires_data = data.get("locataires") or []

    # Support pour le format singulier (MRH)
    locataire_singulier = data.get("locataire")
    if locataire_singulier and not locataires_data:
        locataires_data = [locataire_singulier]

    locataires = []

    for validated in locataires_data:
        # Récupérer l'UUID frontend si fourni
        frontend_id = validated.get("id")

        # Préparer les données du locataire
        locataire_data = {
            "lastName": validated["lastName"],
            "firstName": validated["firstName"],
            "email": validated["email"],
            "date_naissance": validated.get("date_naissance"),
            "profession": validated.get("profession") or "",
            "revenu_mensuel": validated.get("revenus_mensuels"),
            "caution_requise": validated.get("cautionRequise", False),
        }

        # Gérer l'adresse : dict structuré → créer FK Adresse
        adresse_value = validated.get("adresse")
        if adresse_value and isinstance(adresse_value, dict):
            adresse_obj = _get_or_create_adresse(adresse_value)
            if adresse_obj:
                locataire_data["adresse"] = adresse_obj

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
        garant_data = {
            "lastName": validated["lastName"],
            "firstName": validated["firstName"],
            "email": validated["email"],
            "date_naissance": validated.get("date_naissance"),
            "telephone": validated.get("telephone") or "",
        }

        # Gérer l'adresse : dict structuré → créer FK Adresse
        adresse_value = validated.get("adresse")
        if adresse_value and isinstance(adresse_value, dict):
            adresse_obj = _get_or_create_adresse(adresse_value)
            if adresse_obj:
                garant_data["adresse"] = adresse_obj

        garant = Personne.objects.create(**garant_data)
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


def _extract_rent_terms_data(data, location: Location, serializer_class):
    """
    Extrait et prépare les données pour RentTerms en utilisant les mappings.
    Calcule automatiquement zone_tendue, zone_tres_tendue, zone_tendue_touristique et permis_de_louer si non fournis.
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

    # Si zone_tendue, zone_tres_tendue, zone_tendue_touristique ou permis_de_louer ne sont pas dans les données extraites,
    # les calculer depuis les coordonnées GPS
    adresse: Adresse = location.bien.adresse
    if (
        (
            "zone_tendue" not in rent_terms_data
            or "zone_tres_tendue" not in rent_terms_data
            or "zone_tendue_touristique" not in rent_terms_data
            or "permis_de_louer" not in rent_terms_data
        )
        and adresse
        and adresse.latitude
        and adresse.longitude
    ):
        ban_result = check_zone_status_via_ban(adresse.latitude, adresse.longitude)

        # Ajouter seulement si pas déjà présent
        if "zone_tendue" not in rent_terms_data:
            rent_terms_data["zone_tendue"] = ban_result.get("is_zone_tendue")
        if "zone_tres_tendue" not in rent_terms_data:
            rent_terms_data["zone_tres_tendue"] = ban_result.get("is_zone_tres_tendue")
        if "zone_tendue_touristique" not in rent_terms_data:
            rent_terms_data["zone_tendue_touristique"] = ban_result.get(
                "is_zone_tendue_touristique"
            )
        if "permis_de_louer" not in rent_terms_data:
            rent_terms_data["permis_de_louer"] = ban_result.get("is_permis_de_louer")

    return rent_terms_data


def create_rent_terms(location: Location, data, serializer_class):
    """
    Crée ou met à jour les conditions financières pour une location.
    Utilise update_or_create pour éviter les erreurs de contrainte unique.
    """
    fields_data = _extract_rent_terms_data(data, location, serializer_class)

    # Filtrer les None pour ne garder que les valeurs définies
    fields_to_create = {k: v for k, v in fields_data.items() if v is not None}

    if not fields_to_create:
        return None

    rent_terms, created = RentTerms.objects.update_or_create(
        location=location,
        defaults=fields_to_create,
    )
    action = "créé" if created else "mis à jour"
    logger.info(f"RentTerms {action} pour la location {location.id}")
    return rent_terms


def update_rent_terms(location: Location, data, serializer_class):
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


def update_bien_fields(bien: Bien, data, serializer_class, location_id=None):
    """
    Met à jour les champs manquants du Bien avec les nouvelles données.
    Met à jour uniquement les champs None/vides ET non verrouillés.
    """
    country = data.get("country", "FR")
    bien_from_form = create_bien_from_form_data(data, serializer_class, save=False)

    # Obtenir les steps verrouillées si location_id est fourni
    locked_steps = set()
    if location_id:
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
            # Comparaison spéciale pour les adresses (comparer le contenu, pas les références)
            if field_name == "adresse" and isinstance(new_value, Adresse):
                if not adresses_are_equal(current_value, new_value):
                    # Sauvegarder la nouvelle adresse si pas encore en base
                    if new_value._state.adding:
                        new_value.save()
                        logger.debug(
                            f"Adresse sauvegardée avant assignation: {new_value.id}"
                        )
                    setattr(bien, field_name, new_value)
                    updated = True
                    logger.debug("Bien.adresse mis à jour")
            elif current_value != new_value:
                setattr(bien, field_name, new_value)
                updated = True
                logger.debug(
                    f"Bien.{field_name} mis à jour: {current_value} -> {new_value}"
                )

    if updated:
        bien.save()
        logger.info(f"Bien {bien.id} mis à jour avec les nouvelles données")

    return bien


def get_or_create_etat_lieux_for_location(location: Location, validated_data, request):
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


def get_or_create_bail_for_location(
    location: Location, user_role=None, validated_data=None
):
    """
    Récupère ou crée un bail pour une location.

    Args:
        location: Instance de Location
        user_role: Rôle de l'utilisateur (UserRole.BAILLEUR ou UserRole.MANDATAIRE)
        validated_data: Données validées du formulaire (optionnel)

    Returns:
        bail_id: L'ID du bail existant ou nouvellement créé
    """

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


def update_location_fields(location: Location, data, location_id=None):
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

    # Créer les bailleurs (requis sauf pour MRH)
    bailleur_principal = None
    autres_bailleurs = []
    if "bailleur" in data:
        bailleur_principal, autres_bailleurs = create_or_get_bailleur(data)

        # Associer les bailleurs au bien (utiliser set() pour éviter les doublons)
        bailleurs_list = [bailleur_principal] + autres_bailleurs
        bien.bailleurs.set(bailleurs_list)

        logger.info(
            f"Bailleur principal et {len(autres_bailleurs)} co-bailleur(s) associés"
        )
    elif document_type == "mrh":
        # MRH n'a pas de bailleur (souscription locataire uniquement)
        logger.info("Pas de bailleur pour MRH (souscription locataire)")
    else:
        raise ValueError(
            f"Données du bailleur requises pour le document type '{document_type}'"
        )

    # 3. Créer la Location (entité pivot) avec l'ID fourni si disponible
    location_fields = get_location_fields_from_data(data)
    if location_id:
        # Utiliser get_or_create pour éviter les race conditions
        # (ex: React StrictMode double render, retry après erreur réseau)
        location, created = Location.objects.get_or_create(
            id=location_id,
            defaults={
                "bien": bien,
                "mandataire": mandataire_obj,
                **location_fields,
            },
        )
        if not created:
            # Location existait déjà - mettre à jour les champs
            location.bien = bien
            location.mandataire = mandataire_obj
            for key, value in location_fields.items():
                setattr(location, key, value)
            location.save()
            logger.info(f"Location existante réutilisée: {location_id}")
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

    # 6. Créer les conditions financières si fournies (pas pour MRH)
    if document_type != "mrh":
        create_rent_terms(location, data, serializer_class=serializer_class)

    # 7. Créer les honoraires mandataire si user_role == MANDATAIRE
    if user_role == UserRole.MANDATAIRE:
        create_or_update_honoraires_mandataire(
            location, data, document_type=document_type
        )

    logger.info(f"Location créée avec succès: {location.id}")
    return location, bien, bailleur_principal


def update_existing_location(location: Location, data, serializer_class, document_type):
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
    # Supporte locataires (liste) ou locataire (singulier pour MRH)
    locataires_data = data.get("locataires") or data.get("locataire")
    if locataires_data:
        locataires = create_locataires(data)
        # Utiliser set() pour remplacer complètement les locataires (évite les doublons)
        location.locataires.set(locataires)
        logger.info(
            f"{len(locataires)} locataire(s) associé(s) à la location {location.id}"
        )

    # 3bis. Créer et associer les bailleurs/co-bailleurs si fournis
    bailleur_principal = None
    bailleur_data = data.get("bailleur")
    if bailleur_data:
        bailleur_principal, autres_bailleurs = create_or_get_bailleur(data)
        # Remplacer complètement les bailleurs (évite les doublons)
        bailleurs_list = [bailleur_principal] + autres_bailleurs
        location.bien.bailleurs.set(bailleurs_list)

    # 4. Gérer le mandataire si user_role == MANDATAIRE
    # Note: user_role est optionnel pour MRH (pas de bailleur/mandataire)
    user_role = data.get("user_role")
    if user_role and user_role not in [UserRole.BAILLEUR, UserRole.MANDATAIRE]:
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

    # 5. Mettre à jour ou créer les conditions financières (pas pour MRH)
    if document_type != "mrh":
        update_rent_terms(location, data, serializer_class=serializer_class)

    return location, location.bien, bailleur_principal
