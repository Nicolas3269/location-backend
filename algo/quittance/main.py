from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
import os

# Charger le modèle HTML
env = Environment(loader=FileSystemLoader("./backend/quittance/"))
template = env.get_template("doc.html")

# Données dynamiques
data = {
    "start_date": "01/01/2024",
    "end_date": "31/01/2024",
    "landlord_first_name": "Jean",
    "landlord_last_name": "Dupont",
    "landlord_address": "10 rue des Lilas",
    "landlord_postal_code": "75001",
    "landlord_city": "Paris",
    "landlord_email": "jean.dupont@email.com",
    "landlord_phone": "0601020304",
    "tenant_first_name": "Marie",
    "tenant_last_name": "Durand",
    "tenant_address": "12 rue des Roses",
    "tenant_postal_code": "75002",
    "tenant_city": "Paris",
    "tenant_email": "marie.durand@email.com",
    "tenant_phone": "0702030405",
    "receipt_date": "01/02/2024",
    "rent_amount": 1200,
    "charges_amount": 200,
    "total_amount": 1400,
    "rent_receipt_date": "01/02/2024",
    "image_path": os.path.abspath("./backend/quittance/images/image.png"),
}

# Générer le contenu HTML avec les données
html_content = template.render(data)

# Générer le PDF en spécifiant le chemin des ressources (images)
HTML(string=html_content, base_url=os.path.abspath(".")).write_pdf(
    "quittance_loyer.pdf"
)

print("PDF généré avec succès !")
