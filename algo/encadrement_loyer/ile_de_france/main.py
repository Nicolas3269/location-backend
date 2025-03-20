from playwright.sync_api import sync_playwright


def fetch_loyer_de_reference(adresse, pieces, epoque, meuble, periode):
    with sync_playwright() as p:
        # Lancer le navigateur
        browser = p.chromium.launch(
            headless=False
        )  # headless=False pour voir les actions
        page = browser.new_page()

        # Ouvrir le site
        page.goto(
            "http://www.referenceloyer.drihl.ile-de-france.developpement-durable.gouv.fr/paris/"
        )

        # Remplir le nombre de pièces principales
        page.select_option("#piece", str(pieces))  # Exemple : "2" pour 2 pièces

        # Sélectionner l'époque de construction
        page.select_option("#edit-epoque", epoque)  # Exemple : "1971-1990"

        # Sélectionner le type de location
        page.select_option("#edit-meuble", meuble)  # Exemple : "meuble"

        # Sélectionner la période
        page.select_option("#edit-date", periode)  # Exemple : "2024-07-01"

        # Simuler la saisie utilisateur pour l'adresse
        page.type(
            "#search-adresse", adresse, delay=100
        )  # Tape chaque caractère avec un délai

        # Attendre l'affichage des suggestions
        page.wait_for_selector("#result .list-group-item")

        # Cliquer sur la première suggestion
        first_suggestion = page.query_selector("#result .list-group-item")
        first_suggestion.click()

        # Soumettre le formulaire
        page.click("#edit-submit-adresse")

        # Attendre que les résultats soient affichés
        page.wait_for_selector("#encart_infos", timeout=5000)

        # Extraire les résultats
        refmin = page.text_content(".refmin")  # Loyer de référence minoré
        ref = page.text_content(".ref")  # Loyer de référence
        refmaj = page.text_content(".refmaj")  # Loyer de référence majoré

        # Fermer le navigateur
        browser.close()

        return {
            "adresse": adresse,
            "refmin": refmin.strip() if refmin else None,
            "ref": ref.strip() if ref else None,
            "refmaj": refmaj.strip() if refmaj else None,
        }


# Exemple d'utilisation
result = fetch_loyer_de_reference(
    adresse="12 rue dautancourt, 75017 Paris",
    pieces="2",
    epoque="1971-1990",
    meuble="meuble",
    periode="2024-07-01",
)

print(result)
