"""
Helpers pour les serializers READ.
Fonctions réutilisables pour éviter la duplication de code.
"""

from typing import Any, Dict, Optional

from location.models import (
    Bailleur,
    BailleurType,
    Locataire,
    Mandataire,
    Personne,
    Societe,
)


# ============================================
# HELPERS ATOMIQUES (Personne, Société, Locataire)
# ============================================


def serialize_personne_to_dict(instance: Personne) -> Dict[str, Any]:
    """
    Sérialise une Personne en dictionnaire.
    Helper atomique réutilisé partout.

    Args:
        instance: Instance de Personne

    Returns:
        Dict avec id, firstName, lastName, email, adresse (structurée)
    """
    # Adresse structurée (FK vers Adresse) - frontend construit le formaté
    adresse_data = None
    if instance.adresse:
        adresse_data = {
            "numero": instance.adresse.numero,
            "voie": instance.adresse.voie,
            "complement": instance.adresse.complement,
            "code_postal": instance.adresse.code_postal,
            "ville": instance.adresse.ville,
            "pays": instance.adresse.pays,
        }

    return {
        "id": str(instance.id),  # ✅ ID de la personne
        "firstName": instance.firstName,
        "lastName": instance.lastName,
        "email": instance.email,
        "adresse": adresse_data,
    }


def serialize_societe_to_dict(instance: Societe) -> Dict[str, Any]:
    """
    Sérialise une Société en dictionnaire.
    Helper atomique réutilisé partout.

    Args:
        instance: Instance de Societe

    Returns:
        Dict avec id, raison_sociale, siret, forme_juridique, adresse (structurée), email
    """
    # Adresse structurée (FK vers Adresse) - frontend construit le formaté
    adresse_data = None
    if instance.adresse:
        adresse_data = {
            "numero": instance.adresse.numero,
            "voie": instance.adresse.voie,
            "complement": instance.adresse.complement,
            "code_postal": instance.adresse.code_postal,
            "ville": instance.adresse.ville,
            "pays": instance.adresse.pays,
        }

    return {
        "id": str(instance.id),  # ✅ ID de la société
        "raison_sociale": instance.raison_sociale,
        "siret": instance.siret,
        "forme_juridique": instance.forme_juridique,
        "adresse": adresse_data,
        "email": instance.email,
    }


def serialize_locataire_to_dict(instance: Locataire) -> Dict[str, Any]:
    """
    Sérialise un Locataire en dictionnaire.
    Réutilise serialize_personne_to_dict() (qui inclut déjà l'ID).

    Args:
        instance: Instance de Locataire (hérite de Personne)

    Returns:
        Dict avec id, firstName, lastName, email
    """
    return serialize_personne_to_dict(instance)


# ============================================
# HELPERS COMPOSÉS (Bailleur, Mandataire)
# ============================================


def serialize_bailleur_to_dict(instance: Bailleur) -> Dict[str, Any]:
    """
    Sérialise un Bailleur en dictionnaire.
    Retourne la structure nested attendue par le serializer WRITE.
    Format aligné avec BailleurInfoSerializer.

    Args:
        instance: Instance de Bailleur à sérialiser

    Returns:
        Dict avec structure:
        {
            "id": "uuid-du-bailleur",  # ✅ Ajouté pour réutilisation
            "bailleur_type": "physique",
            "personne": {...} ou None,
            "societe": {...} ou None,
            "signataire": {...} ou None,
        }
    """
    result = {
        "id": str(instance.id),  # ✅ ID du bailleur
        "bailleur_type": instance.bailleur_type,
    }

    # Bailleur PHYSIQUE : ajouter personne
    if instance.bailleur_type == BailleurType.PHYSIQUE:
        if instance.personne:
            result["personne"] = serialize_personne_to_dict(instance.personne)
        else:
            result["personne"] = None

    # Bailleur MORALE : ajouter societe + signataire
    elif instance.bailleur_type == BailleurType.MORALE:
        result["societe"] = (
            serialize_societe_to_dict(instance.societe) if instance.societe else None
        )
        if instance.signataire:
            result["signataire"] = serialize_personne_to_dict(instance.signataire)
        else:
            result["signataire"] = None

    return result


def serialize_mandataire_to_dict(instance: Mandataire) -> Dict[str, Any]:
    """
    Sérialise un Mandataire en dictionnaire.
    Utilise les helpers atomiques pour Personne et Société.

    Args:
        instance: Instance de Mandataire

    Returns:
        Dict avec structure:
        {
            "signataire": {...},
            "agence": {...},
            "numero_carte_professionnelle": "..."
        }
    """
    if not instance:
        return None

    result = {}

    # Signataire (personne physique qui signe pour l'agence)
    if instance.signataire:
        result["signataire"] = serialize_personne_to_dict(instance.signataire)

    # Agence (= societe dans le modèle, mais agence dans le serializer WRITE)
    if instance.societe:
        result["agence"] = serialize_societe_to_dict(instance.societe)

    # Numéro de carte professionnelle (optionnel)
    if hasattr(instance, "numero_carte_professionnelle"):
        result["numero_carte_professionnelle"] = instance.numero_carte_professionnelle

    return result


def extract_bailleurs_with_priority(
    bailleurs_queryset, user: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Extrait les données du bailleur principal et des co-bailleurs.
    Met en priorité le bailleur correspondant au user connecté.

    Args:
        bailleurs_queryset: QuerySet de bailleurs (ManyToMany depuis Bien)
        user: Utilisateur connecté (optionnel).
              Si fourni, son bailleur sera mis en premier.

    Returns:
        Dict avec structure:
        {
            "bailleur": {
                "bailleur_type": "physique",
                "personne": {...}
            },
            "co_bailleurs": [...]
        }
    """

    if not bailleurs_queryset.exists():
        return {}

    # ✅ Utiliser la fonction existante (lazy import pour éviter circular import)
    from location.services.bailleur_utils import get_primary_bailleur_for_user

    bailleur_principal = get_primary_bailleur_for_user(bailleurs_queryset, user)

    if not bailleur_principal:
        return {}

    # Sérialiser le bailleur principal avec serialize_bailleur_to_dict
    bailleur_principal_data = serialize_bailleur_to_dict(bailleur_principal)

    # Co-bailleurs = tous SAUF celui en position principale
    co_bailleurs = bailleurs_queryset.exclude(id=bailleur_principal.id)
    co_bailleurs_list = []

    if co_bailleurs.exists():
        # ✅ Retourner la structure complète avec IDs pour permettre la réutilisation
        for co_bailleur in co_bailleurs:
            # ✅ Utiliser serialize_bailleur_to_dict pour avoir la même structure
            co_bailleur_data = serialize_bailleur_to_dict(co_bailleur)
            co_bailleurs_list.append(co_bailleur_data)

    # ✅ Retourner au même niveau
    return {
        "bailleur": bailleur_principal_data,
        "co_bailleurs": co_bailleurs_list,
    }


def restructure_bien_to_nested_format(
    bien_data: Dict[str, Any],
    calculate_zone_from_gps: bool = False,
    zone_reglementaire_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convertit les données plates de BienReadSerializer en format nested.

    Args:
        bien_data: Données du bien (format flat de BienReadSerializer)
        calculate_zone_from_gps: Si True, calcule zone_reglementaire via GPS
        zone_reglementaire_override: Si fourni, utilise ces valeurs
                                      (depuis RentTerms d'une Location)

    Returns:
        Dict avec structure nested:
        {
            "id": "...",  # UUID du bien (préservé depuis bien_data)
            "localisation": {...},
            "caracteristiques": {...},
            "performance_energetique": {...},
            "equipements": {...},
            "energie": {...},
            "regime": {...},
            "zone_reglementaire": {...}
        }

    Notes:
        - id (UUID) est préservé au root level pour navigation frontend
        - area_id est toujours calculé depuis GPS (si coords disponibles)
        - zone_reglementaire vient soit de override (Location existante),
          soit de GPS (nouveau bail depuis bien)
    """
    from rent_control.views import check_zone_status_via_ban, get_rent_control_info

    # Extraire l'adresse structurée (depuis AdresseReadSerializer)
    # bien_data["adresse"] est un dict avec {id, numero, voie, latitude, longitude...}
    adresse_data = bien_data.get("adresse")
    latitude = adresse_data.get("latitude") if adresse_data else None
    longitude = adresse_data.get("longitude") if adresse_data else None

    # Calcul de area_id (depuis GPS de l'adresse)
    area_id = None
    if latitude and longitude:
        _, area = get_rent_control_info(latitude, longitude)
        if area:
            area_id = area.id

    # Calcul zone_reglementaire selon le contexte
    zone_reglementaire = {}
    if zone_reglementaire_override is not None:
        # Cas 1 : Depuis RentTerms (Location existante)
        zone_reglementaire = zone_reglementaire_override
    elif calculate_zone_from_gps and latitude and longitude:
        # Cas 2 : Calculé depuis GPS (Prefill nouveau bail)
        zone_status = check_zone_status_via_ban(latitude, longitude)
        if zone_status:
            zone_reglementaire = {
                "zone_tendue": zone_status.get("is_zone_tendue", False),
                "zone_tres_tendue": zone_status.get("is_zone_tres_tendue", False),
                "zone_tendue_touristique": zone_status.get(
                    "is_zone_tendue_touristique", False
                ),
                "permis_de_louer": zone_status.get("is_permis_de_louer", False),
            }

    # Construire localisation_data depuis adresse structurée
    if not isinstance(adresse_data, dict):
        raise ValueError(
            f"Un bien doit avoir une adresse (dict attendu, reçu {type(adresse_data).__name__})"
        )

    localisation_data = {
        "numero": adresse_data.get("numero"),
        "voie": adresse_data.get("voie"),
        "complement": adresse_data.get("complement"),
        "code_postal": adresse_data.get("code_postal"),
        "ville": adresse_data.get("ville"),
        "pays": adresse_data.get("pays", "FR"),
        "latitude": latitude,
        "longitude": longitude,
        "area_id": area_id,
    }

    # Structure nested (UNE SEULE FOIS !)
    # IMPORTANT : Conserver les champs de metadata au root level (id, created_at, etc.)
    return {
        "id": bien_data.get("id"),  # CRITIQUE : UUID nécessaire pour navigation frontend
        "localisation": localisation_data,
        "caracteristiques": {
            "superficie": bien_data.get("superficie"),
            "type_bien": bien_data.get("type_bien"),
            "etage": bien_data.get("etage"),
            "porte": bien_data.get("porte"),
            "dernier_etage": bien_data.get("dernier_etage"),
            "meuble": bien_data.get("meuble"),
            "pieces_info": bien_data.get("pieces_info"),
        },
        "performance_energetique": {
            "classe_dpe": bien_data.get("classe_dpe"),
            "depenses_energetiques": bien_data.get("depenses_energetiques"),
        },
        "equipements": {
            "annexes_privatives": bien_data.get("annexes_privatives"),
            "annexes_collectives": bien_data.get("annexes_collectives"),
            "information": bien_data.get("information"),
        },
        "energie": {
            "chauffage": (
                {
                    "type": bien_data.get("chauffage_type"),
                    "energie": bien_data.get("chauffage_energie"),
                }
                if bien_data.get("chauffage_type")
                else {}
            ),
            "eau_chaude": (
                {
                    "type": bien_data.get("eau_chaude_type"),
                    "energie": bien_data.get("eau_chaude_energie"),
                }
                if bien_data.get("eau_chaude_type")
                else {}
            ),
        },
        "regime": {
            "regime_juridique": bien_data.get("regime_juridique", "monopropriete"),
            "periode_construction": bien_data.get("periode_construction"),
            "identifiant_fiscal": bien_data.get("identifiant_fiscal"),
        },
        "zone_reglementaire": zone_reglementaire,
    }
