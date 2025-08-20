"""
Utilitaires pour l'encadrement des loyers
"""

from location.models import Bien
from rent_control.choices import Region
from rent_control.models import RentControlArea, RentPrice


def get_rent_price_for_bien(bien: Bien, area_id):
    """
    Récupère le RentPrice correspondant à un bien et une zone donnée.
    Retourne exactement 1 résultat ou lève une exception.

    Args:
        bien: Instance de Bien ou objet avec les attributs nécessaires
        area_id: ID de la zone de contrôle

    Returns:
        RentPrice: L'objet RentPrice correspondant

    Raises:
        ValueError: Si aucun ou plusieurs prix trouvés
    """
    try:
        area = RentControlArea.objects.get(id=area_id)
    except RentControlArea.DoesNotExist:
        raise ValueError(f"Zone {area_id} non trouvée")

    # Utiliser la propriété nombre_pieces_principales directement
    room_count_number = bien.nombre_pieces_principales

    # Convertir le nombre en string pour le filtre (selon les choix RoomCount)
    if room_count_number == 1:
        room_count_filter = "1"
    elif room_count_number == 2:
        room_count_filter = "2"
    elif room_count_number == 3:
        room_count_filter = "3"
    else:
        room_count_filter = "4"  # 4 pièces et plus

    # Construire les filtres de recherche obligatoires
    filters = {
        "areas": area,
        "furnished": bien.meuble,
        "room_count": room_count_filter,
        "construction_period": bien.periode_construction,
    }
    if area.region not in [
        Region.PARIS,
        Region.LILLE,
        Region.LYON,
        Region.MONTPELLIER,
        Region.GRENOBLE,
    ]:
        # Pour les zones hors Paris, Lille, Lyon, on utilise le type de bien
        filters["property_type"] = bien.type_bien

    # Chercher le prix de référence correspondant
    rent_prices = RentPrice.objects.filter(**filters)

    if rent_prices.count() == 0:
        raise ValueError(f"Aucun prix trouvé pour les critères: {filters}")
    elif rent_prices.count() > 1:
        raise ValueError(
            f"Plusieurs prix trouvés pour les critères: {filters} "
            f"({rent_prices.count()} résultats)"
        )

    return rent_prices.first()


def calculate_total_prices(rent_price, surface):
    """
    Calcule les prix totaux à partir d'un RentPrice et d'une surface.

    Args:
        rent_price: Instance de RentPrice
        surface: Surface en m² (float)

    Returns:
        dict: Dictionnaire avec les prix calculés
    """
    surface_float = float(surface)

    return {
        "reference_price_per_m2": float(rent_price.reference_price),
        "min_price_per_m2": float(rent_price.min_price),
        "max_price_per_m2": float(rent_price.max_price),
        "surface": surface_float,
        "total_reference_price": float(rent_price.reference_price) * surface_float,
        "total_min_price": float(rent_price.min_price) * surface_float,
        "total_max_price": float(rent_price.max_price) * surface_float,
    }
