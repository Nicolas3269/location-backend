import logging
import os
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from weasyprint import HTML

from bail.factories import BailSpecificitesFactory

logger = logging.getLogger(__name__)


@csrf_exempt
def generate_bail_pdf(request):
    if request.method == "POST":
        bail = BailSpecificitesFactory.create()
        html = render_to_string("pdf/bail.html", {"bail": bail})
        pdf = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()

        # Créer un nom de fichier unique
        filename = f"bail_{bail.id}_{uuid.uuid4().hex}.pdf"

        # Chemin complet où le fichier sera sauvegardé
        bail_dir = os.path.join(settings.MEDIA_ROOT, "bails")
        os.makedirs(bail_dir, exist_ok=True)  # S'assurer que le répertoire existe
        file_path = os.path.join(bail_dir, filename)

        # Sauvegarder le PDF dans le système de fichiers
        with open(file_path, "wb") as f:
            f.write(pdf)

        # Générer l'URL du fichier
        file_url = f"{settings.MEDIA_URL}bails/{filename}"

        # Renvoyer l'URL dans la réponse
        return JsonResponse({"success": True, "bail_id": bail.id, "pdfUrl": file_url})
