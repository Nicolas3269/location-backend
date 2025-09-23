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


# Équipements meublés transversaux (non liés à une pièce spécifique)
EQUIPEMENTS_MEUBLES = {
    "entretien": {
        "label": "Matériel d'entretien ménager adapté",
        "equipments": [
            {"id": "aspirateur", "label": "Aspirateur", "icon": "🧹"},
            {"id": "balais", "label": "Balais", "icon": "🧹"},
            {"id": "balayettes", "label": "Balayettes", "icon": "🧹"},
            {"id": "pelles", "label": "Pelles", "icon": "🗑️"},
            {"id": "seaux", "label": "Seaux", "icon": "🪣"},
            {"id": "torchons", "label": "Torchons", "icon": "🧽"},
        ],
    },
    "linge": {
        "label": "Linge de maison et entretien du linge",
        "equipments": [
            {"id": "lave_linge", "label": "Lave-linge", "icon": "🌀"},
            {"id": "seche_linge", "label": "Sèche-linge", "icon": "♨️"},
            {"id": "fer_repasser", "label": "Fer à repasser", "icon": "👔"},
            {"id": "peignoirs_bain", "label": "Peignoirs de bain", "icon": "🧖"},
            {"id": "serviettes", "label": "Serviettes", "icon": "🧻"},
            {"id": "gants", "label": "Gants", "icon": "🧤"},
            {"id": "nappes", "label": "Nappes", "icon": "🍽️"},
            {"id": "coussins", "label": "Coussins", "icon": "🛏️"},
        ],
    },
    "cuisine": {
        "label": "Vaisselle et ustensiles de cuisine",
        "equipments": [
            {"id": "assiettes", "label": "Assiettes", "icon": "🍽️"},
            {"id": "fourchettes", "label": "Fourchettes", "icon": "🍴"},
            {"id": "cuillers", "label": "Cuillères", "icon": "🥄"},
            {"id": "couteaux", "label": "Couteaux", "icon": "🔪"},
            {"id": "verres", "label": "Verres", "icon": "🥃"},
            {"id": "bols_tasses", "label": "Bols/Tasses", "icon": "☕"},
            {"id": "ouvre_boite", "label": "Tire-bouchon/Décapsuleur/Ouvre-boîte", "icon": "🍾"},
            {"id": "carafes", "label": "Carafes", "icon": "🍶"},
            {"id": "planches_decouper", "label": "Planches à découper", "icon": "🪵"},
            {"id": "plats_saladiers", "label": "Plats/Saladiers", "icon": "🥗"},
            {"id": "passoires", "label": "Passoires", "icon": "🕳️"},
            {"id": "poeles", "label": "Poêles", "icon": "🍳"},
            {"id": "casseroles", "label": "Casseroles", "icon": "🍲"},
            {"id": "egouttoir", "label": "Égouttoir", "icon": "🍽️"},
        ],
    },
    "divertissement": {
        "label": "Divertissement",
        "equipments": [
            {"id": "television", "label": "Télévision", "icon": "📺"},
            {"id": "videoprojecteur", "label": "Vidéoprojecteur", "icon": "📽️"},
        ],
    },
    "literie": {
        "label": "Literie",
        "equipments": [
            {"id": "lit", "label": "Lit", "icon": "🛏️"},
            {"id": "matelas", "label": "Matelas", "icon": "🛏️"},
            {"id": "taies", "label": "Taies", "icon": "🛏️"},
            {"id": "oreillers", "label": "Oreillers", "icon": "🛏️"},
            {"id": "draps", "label": "Draps", "icon": "🛏️"},
            {"id": "couette_couverture", "label": "Couette/Couverture/Couvre-lit", "icon": "🛏️"},
            {"id": "housse_couette", "label": "Housse de couette", "icon": "🛏️"},
            {"id": "alaise", "label": "Alaise", "icon": "🛏️"},
        ],
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
        "meubles": EQUIPEMENTS_MEUBLES,
    }
