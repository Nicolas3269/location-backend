import os

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import Http404, HttpResponse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt


def _serve_pdf_response(pdf_content, file_path, cache_max_age):
    """
    Helper pour créer une réponse HTTP de PDF avec les bons headers.

    Args:
        pdf_content: Contenu binaire du PDF
        file_path: Chemin du fichier (pour extraire le nom)
        cache_max_age: Durée du cache en secondes

    Returns:
        HttpResponse configuré pour affichage inline
    """
    response = HttpResponse(pdf_content, content_type="application/pdf")
    filename = os.path.basename(file_path)
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Cache-Control"] = f"public, max-age={cache_max_age}"
    return response


@xframe_options_exempt
@csrf_exempt
def serve_static_pdf_for_iframe(request, file_path):
    """
    Sert les PDFs templates statiques sans restrictions X-Frame-Options.
    Utilisé pour: notice_information.pdf, grille_vetuste.pdf, etc.
    """
    try:
        if not file_path.lower().endswith(".pdf"):
            raise Http404("Le fichier demandé n'est pas un PDF")

        # Lire depuis static/ source (pas staticfiles/ collecté)
        # Car ces PDFs templates sont versionnés avec le code
        static_pdf_path = os.path.join(settings.BASE_DIR, "static", "pdfs", file_path)

        if not os.path.exists(static_pdf_path):
            raise Http404("Fichier PDF statique non trouvé")

        with open(static_pdf_path, 'rb') as f:
            pdf_content = f.read()

        # Cache agressif pour les fichiers statiques (1 jour)
        return _serve_pdf_response(pdf_content, file_path, cache_max_age=86400)

    except Exception as e:
        if settings.DEBUG:
            print(f"Erreur lors du service du PDF statique {file_path}: {str(e)}")
        raise Http404("Erreur lors du chargement du PDF statique")


@xframe_options_exempt
@csrf_exempt
def serve_pdf_for_iframe(request, file_path):
    """
    Sert les PDFs uploads utilisateurs (S3/MinIO) sans restrictions X-Frame-Options.
    Utilisé pour: baux signés, états des lieux, quittances, etc.
    """
    try:
        if not file_path.lower().endswith(".pdf"):
            raise Http404("Le fichier demandé n'est pas un PDF")

        if not default_storage.exists(file_path):
            raise Http404("Fichier PDF non trouvé")

        with default_storage.open(file_path, "rb") as pdf_file:
            pdf_content = pdf_file.read()

        # Cache modéré pour les uploads utilisateurs (1 heure)
        return _serve_pdf_response(pdf_content, file_path, cache_max_age=3600)

    except PermissionError:
        raise Http404("Accès au fichier PDF refusé")
    except Exception as e:
        if settings.DEBUG:
            print(f"Erreur lors du service du PDF {file_path}: {str(e)}")
        raise Http404("Erreur lors du chargement du PDF")
