import mimetypes
import os

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt


@xframe_options_exempt
@csrf_exempt
def serve_pdf_for_iframe(request, file_path):
    """
    Sert les fichiers PDF sans restrictions X-Frame-Options pour permettre l'affichage en iframe.
    Cette vue est spécifiquement créée pour les visualiseurs PDF en iframe.
    """
    try:
        # Construire le chemin complet du fichier
        full_path = os.path.join(settings.MEDIA_ROOT, file_path)

        # Vérifier que le fichier existe
        if not os.path.exists(full_path):
            raise Http404("Fichier PDF non trouvé")

        # Vérifier que c'est bien un fichier PDF
        if not file_path.lower().endswith(".pdf"):
            raise Http404("Le fichier demandé n'est pas un PDF")

        # Vérifier le type MIME pour plus de sécurité
        mime_type, _ = mimetypes.guess_type(full_path)
        if mime_type != "application/pdf":
            # Forcer le type MIME pour les PDFs
            mime_type = "application/pdf"

        # Lire et servir le fichier PDF
        with open(full_path, "rb") as pdf_file:
            response = HttpResponse(pdf_file.read(), content_type=mime_type)

            # Définir les en-têtes pour affichage inline (pas de téléchargement forcé)
            filename = os.path.basename(file_path)
            response["Content-Disposition"] = f'inline; filename="{filename}"'

            # Ajouter des en-têtes de cache pour optimiser les performances
            response["Cache-Control"] = "public, max-age=3600"

            return response

    except PermissionError:
        raise Http404("Accès au fichier PDF refusé")
    except Exception as e:
        # Log l'erreur si nécessaire (en production)
        if settings.DEBUG:
            print(f"Erreur lors du service du PDF {file_path}: {str(e)}")
        raise Http404("Erreur lors du chargement du PDF")
