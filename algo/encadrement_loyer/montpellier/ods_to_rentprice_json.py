import os

import pandas as pd


def extract_ods_file_to_json(file_path, property_type=None):
    df = pd.read_excel(file_path, engine="odf")

    # Nettoyer les données : ignorer la première ligne vide et utiliser la seconde comme en-têtes
    df_cleaned = df[1:].copy()
    df_cleaned.columns = df.iloc[0]
    df_cleaned = df_cleaned.reset_index(drop=True)

    # Compléter les valeurs manquantes pour la zone et le nombre de pièces
    df_cleaned["Secteur géographique"] = df_cleaned["Secteur géographique"].fillna(
        method="ffill"
    )
    df_cleaned["Nombre de pièces"] = df_cleaned["Nombre de pièces"].fillna(
        method="ffill"
    )

    # Renommer les colonnes dupliquées pour les meublés
    df_cleaned.columns.values[6] = "Majoration unitaire"
    df_cleaned.columns.values[7] = "Loyer de référence meublé"
    df_cleaned.columns.values[8] = "Loyer de référence majoré meublé"
    df_cleaned.columns.values[9] = "Loyer de référence minoré meublé"

    # Normaliser les valeurs dans les colonnes spécifiques
    df_cleaned["Nombre de pièces"] = df_cleaned["Nombre de pièces"].replace(
        "4 et plus", "4"
    )

    # Normaliser les valeurs de la colonne "Epoque de construction"
    df_cleaned["Epoque de construction"] = df_cleaned["Epoque de construction"].replace(
        {
            "Avant 1946": "avant 1946",
            "Après 1990": "apres 1990",
            "Après 2005": "apres 2005",
        }
    )

    # Sélectionner les colonnes pertinentes
    df_selected = df_cleaned[
        [
            "Secteur géographique",
            "Nombre de pièces",
            "Epoque de construction",
            "Loyer de référence",
            "Loyer de référence majoré",
            "Loyer de référence minoré",
            "Loyer de référence meublé",
            "Loyer de référence majoré meublé",
            "Loyer de référence minoré meublé",
        ]
    ]

    # Renommer pour correspondre au modèle Django
    df_selected.columns = [
        "area",
        "room_count",
        "construction_period",
        "ref_price_unfurnished",
        "max_price_unfurnished",
        "min_price_unfurnished",
        "ref_price_furnished",
        "max_price_furnished",
        "min_price_furnished",
    ]

    # Générer la structure JSON
    result = []
    for _, row in df_selected.iterrows():
        for furnished in [False, True]:
            result.append(
                {
                    "zone_id": row["area"].replace("Zone ", "").lower(),
                    "property_type": property_type,
                    "room_count": row["room_count"],
                    "construction_period": row["construction_period"],
                    "furnished": furnished,
                    "reference_price": row["ref_price_furnished"]
                    if furnished
                    else row["ref_price_unfurnished"],
                    "max_price": row["max_price_furnished"]
                    if furnished
                    else row["max_price_unfurnished"],
                    "min_price": row["min_price_furnished"]
                    if furnished
                    else row["min_price_unfurnished"],
                }
            )
    return result


# Charger le fichier ODS
if __name__ == "__main__":
    extract_dir = "algo/encadrement_loyer/montpellier"
    file_path = os.path.join(extract_dir, "2024.ods")
    json_file = extract_ods_file_to_json(file_path)
    print("✅ JSON exporté dans rent_prices.json")
