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
        Dict avec firstName, lastName, email, adresse
    """
    return {
        "firstName": instance.firstName,
        "lastName": instance.lastName,
        "email": instance.email,
        "adresse": instance.adresse,
    }


def serialize_societe_to_dict(instance: Societe) -> Dict[str, Any]:
    """
    Sérialise une Société en dictionnaire.
    Helper atomique réutilisé partout.

    Args:
        instance: Instance de Societe

    Returns:
        Dict avec raison_sociale, siret, forme_juridique, adresse, email
    """
    return {
        "raison_sociale": instance.raison_sociale,
        "siret": instance.siret,
        "forme_juridique": instance.forme_juridique,
        "adresse": instance.adresse,
        "email": instance.email,
    }


def serialize_locataire_to_dict(instance: Locataire) -> Dict[str, Any]:
    """
    Sérialise un Locataire en dictionnaire.
    Réutilise serialize_personne_to_dict() + ajoute l'ID.

    Args:
        instance: Instance de Locataire (hérite de Personne)

    Returns:
        Dict avec id, firstName, lastName, email
    """
    data = serialize_personne_to_dict(instance)
    data["id"] = str(instance.id)
    return data


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
            "bailleur_type": "physique",
            "personne": {...} ou None,
            "societe": {...} ou None,
            "signataire": {...} ou None,
        }
    """
    result = {
        "bailleur_type": instance.bailleur_type,
    }

    # Bailleur PHYSIQUE : ajouter personne
    if instance.bailleur_type == BailleurType.PHYSIQUE:
        result["personne"] = (
            serialize_personne_to_dict(instance.personne)
            if instance.personne
            else None
        )

    # Bailleur MORALE : ajouter societe + signataire
    elif instance.bailleur_type == BailleurType.MORALE:
        result["societe"] = (
            serialize_societe_to_dict(instance.societe) if instance.societe else None
        )
        result["signataire"] = (
            serialize_personne_to_dict(instance.signataire)
            if instance.signataire
            else None
        )

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
            "bailleur_type": "physique",
            "personne": {...},
            "co_bailleurs": [...]
        }
    """

    if not bailleurs_queryset.exists():
        return {}

    # Trouver le bailleur correspondant au user connecté
    bailleur_principal = None
    if user and hasattr(user, "email"):
        user_email = user.email
        for bailleur in bailleurs_queryset.all():
            try:
                if bailleur.email == user_email:
                    bailleur_principal = bailleur
                    break
            except ValueError:
                # Bailleur invalide (pas de personne ni signataire), ignorer
                continue

    # Si pas trouvé ou pas de user, prendre le premier
    if not bailleur_principal:
        bailleur_principal = bailleurs_queryset.first()

    # Sérialiser le bailleur principal avec serialize_bailleur_to_dict
    data = serialize_bailleur_to_dict(bailleur_principal)

    # Co-bailleurs = tous SAUF celui en position principale
    co_bailleurs = bailleurs_queryset.exclude(id=bailleur_principal.id)
    if co_bailleurs.exists():
        # Utiliser serialize_bailleur_to_dict pour chaque co-bailleur (cohérence)
        data["co_bailleurs"] = [
            serialize_bailleur_to_dict(co_bailleur) for co_bailleur in co_bailleurs
        ]
    else:
        data["co_bailleurs"] = []

    return data


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
            "localisation": {...},
            "caracteristiques": {...},
            "performance_energetique": {...},
            "equipements": {...},
            "energie": {...},
            "regime": {...},
            "zone_reglementaire": {...}
        }

    Notes:
        - area_id est toujours calculé depuis GPS (si coords disponibles)
        - zone_reglementaire vient soit de override (Location existante),
          soit de GPS (nouveau bail depuis bien)
    """
    from rent_control.views import check_zone_status_via_ban, get_rent_control_info

    # Calcul de area_id (toujours depuis GPS si coords disponibles)
    area_id = None
    if bien_data.get("latitude") and bien_data.get("longitude"):
        _, area = get_rent_control_info(bien_data["latitude"], bien_data["longitude"])
        if area:
            area_id = area.id

    # Calcul zone_reglementaire selon le contexte
    zone_reglementaire = {}
    if zone_reglementaire_override is not None:
        # Cas 1 : Depuis RentTerms (Location existante)
        zone_reglementaire = zone_reglementaire_override
    elif (
        calculate_zone_from_gps
        and bien_data.get("latitude")
        and bien_data.get("longitude")
    ):
        # Cas 2 : Calculé depuis GPS (Prefill nouveau bail)
        zone_status = check_zone_status_via_ban(
            bien_data["latitude"], bien_data["longitude"]
        )
        if zone_status:
            zone_reglementaire = {
                "zone_tendue": zone_status.get("is_zone_tendue", False),
                "zone_tres_tendue": zone_status.get("is_zone_tres_tendue", False),
                "zone_tendue_touristique": zone_status.get(
                    "is_zone_tendue_touristique", False
                ),
                "permis_de_louer": zone_status.get("is_permis_de_louer", False),
            }

    # Structure nested (UNE SEULE FOIS !)
    return {
        "localisation": {
            "adresse": bien_data.get("adresse"),
            "latitude": bien_data.get("latitude"),
            "longitude": bien_data.get("longitude"),
            "area_id": area_id,
        },
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
