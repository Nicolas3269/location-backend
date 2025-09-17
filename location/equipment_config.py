"""
Configuration des équipements pour les pièces d'un logement.
Source unique de vérité pour les équipements disponibles.

Tous les équipements (y compris le mobilier) sont stockés dans
EtatLieuxPieceDetail.equipments pour simplifier la gestion.
"""

# Équipements automatiques pour TOUTES les pièces (toujours présents)
EQUIPEMENTS_AUTOMATIQUES = [
    {"id": "murs", "label": "Murs", "icon": "🧱"},
    {"id": "sol", "label": "Sol", "icon": "🟫"},
    {"id": "plafond", "label": "Plafond", "icon": "⬜"},
    {
        "id": "eclairage_interrupteurs",
        "label": "Éclairages et interrupteurs",
        "icon": "💡",
    },
    {"id": "prises_electriques", "label": "Prises électriques", "icon": "🔌"},
]

# Équipements optionnels communs à toutes les pièces
EQUIPEMENTS_COMMUNS = [
    {"id": "portes", "label": "Portes", "icon": "🚪"},
    {"id": "vitrages_volets", "label": "Vitrages/Volets", "icon": "🪟"},
    {"id": "radiateur", "label": "Radiateur", "icon": "🔥"},
    {"id": "rideaux_stores", "label": "Rideaux/Stores", "icon": "🪞"},
    {"id": "luminaires_plafonniers", "label": "Luminaires/Plafonniers", "icon": "💡"},
    {"id": "lampes_appliques", "label": "Lampes/Appliques", "icon": "🛋️"},
]

# Équipements spécifiques par type de pièce
# Tout est unifié dans "equipments" (y compris le mobilier pour les meublés)
EQUIPEMENTS_SPECIFIQUES = {
    "kitchen": {
        "equipments": [
            {"id": "placards_tiroirs", "label": "Placards et tiroirs", "icon": "🗄️"},
            {
                "id": "evier_robinetterie",
                "label": "Évier et robinetterie",
                "icon": "🚰",
            },
            {"id": "plaque_cuisson", "label": "Plaque de cuisson", "icon": "🔥"},
            {"id": "four", "label": "Four", "icon": "🔥"},
            {"id": "microonde", "label": "Micro-ondes", "icon": "📡"},
            {"id": "hotte", "label": "Hotte", "icon": "💨"},
            {"id": "refrigerateur", "label": "Réfrigérateur", "icon": "❄️"},
            {"id": "congelateur", "label": "Congélateur", "icon": "🧊"},
            {"id": "cuisiniere", "label": "Cuisinière", "icon": "♨️"},
            {"id": "grille_pain", "label": "Grille-pain", "icon": "🍞"},
            {"id": "bouilloire", "label": "Bouilloire", "icon": "☕"},
            {"id": "cafetiere", "label": "Cafetière", "icon": "☕"},
            {"id": "lave_vaisselle", "label": "Lave-vaisselle", "icon": "🍽️"},
            # Mobilier (si meublé)
            {
                "id": "chaise_cuisine",
                "label": "Chaise",
                "icon": "🪑",
                "furnished_only": True,
            },
            {
                "id": "table_cuisine",
                "label": "Table",
                "icon": "🪑",
                "furnished_only": True,
            },
            {
                "id": "buffet_cuisine",
                "label": "Buffet",
                "icon": "🗄️",
                "furnished_only": True,
            },
            {
                "id": "tabouret_cuisine",
                "label": "Tabouret",
                "icon": "🪑",
                "furnished_only": True,
            },
        ],
    },
    "bathroom": {
        "equipments": [
            {"id": "lavabo", "label": "Lavabo", "icon": "🚿"},
            {"id": "robinet", "label": "Robinet", "icon": "🚰"},
            {"id": "colonne_douche", "label": "Colonne de douche", "icon": "🚿"},
            {"id": "baignoire", "label": "Baignoire", "icon": "🛁"},
            {"id": "douche", "label": "Douche", "icon": "🚿"},
            {"id": "meuble_sdb", "label": "Meuble", "icon": "🗄️"},
            {"id": "placard_sdb", "label": "Placard", "icon": "🗄️"},
            {"id": "wc_sdb", "label": "WC", "icon": "🚽"},
        ],
    },
    "wc": {
        "equipments": [
            {"id": "wc", "label": "WC", "icon": "🚽"},
            {"id": "lavabo_wc", "label": "Lavabo", "icon": "🚿"},
            {"id": "meuble_lave_main", "label": "Meuble lave-main", "icon": "🗄️"},
            {"id": "placard_wc", "label": "Placard", "icon": "🗄️"},
        ],
    },
    "bedroom": {
        "equipments": [
            {"id": "placard_chambre", "label": "Placard", "icon": "🗄️"},
            # Mobilier (si meublé)
            {
                "id": "lit_simple",
                "label": "Lit simple",
                "icon": "🛏️",
                "furnished_only": True,
            },
            {
                "id": "lit_double",
                "label": "Lit double",
                "icon": "🛏️",
                "furnished_only": True,
            },
            {
                "id": "chaise_chambre",
                "label": "Chaise",
                "icon": "🪑",
                "furnished_only": True,
            },
            {
                "id": "table_chevet",
                "label": "Table de chevet",
                "icon": "🗄️",
                "furnished_only": True,
            },
            {
                "id": "bureau_chambre",
                "label": "Bureau",
                "icon": "🖥️",
                "furnished_only": True,
            },
            {
                "id": "commode_chambre",
                "label": "Commode",
                "icon": "🗄️",
                "furnished_only": True,
            },
        ],
    },
    "living": {
        "equipments": [
            {"id": "placard_sejour", "label": "Placard", "icon": "🗄️"},
            # Mobilier (si meublé)
            {
                "id": "chaise_sejour",
                "label": "Chaise",
                "icon": "🪑",
                "furnished_only": True,
            },
            {
                "id": "tabouret_sejour",
                "label": "Tabouret",
                "icon": "🪑",
                "furnished_only": True,
            },
            {
                "id": "table_sejour",
                "label": "Table",
                "icon": "🪑",
                "furnished_only": True,
            },
            {"id": "canape", "label": "Canapé", "icon": "🛋️", "furnished_only": True},
            {
                "id": "fauteuil",
                "label": "Fauteuil",
                "icon": "🪑",
                "furnished_only": True,
            },
            {
                "id": "bureau_sejour",
                "label": "Bureau",
                "icon": "🖥️",
                "furnished_only": True,
            },
            {
                "id": "buffet_sejour",
                "label": "Buffet",
                "icon": "🗄️",
                "furnished_only": True,
            },
            {
                "id": "commode_sejour",
                "label": "Commode",
                "icon": "🗄️",
                "furnished_only": True,
            },
        ],
    },
    "other": {
        "equipments": [],
    },
    "room": {
        "equipments": [],
    },
}


def get_all_equipements_config():
    """
    Retourne la configuration complète des équipements.
    Utilisé pour la génération des schemas Zod et l'API.
    """
    return {
        "automatiques": EQUIPEMENTS_AUTOMATIQUES,
        "communs": EQUIPEMENTS_COMMUNS,
        "specifiques": EQUIPEMENTS_SPECIFIQUES,
    }
