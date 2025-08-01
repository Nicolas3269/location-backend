from django.urls import reverse


def get_pdf_iframe_url(request, file_field):
    """
    Convertit un FileField PDF en URL utilisable pour iframe (sans X-Frame-Options).

    Args:
        request: L'objet request Django
        file_field: Le FileField contenant le PDF

    Returns:
        URL complète pour afficher le PDF en iframe, ou None si pas de fichier
    """
    if not file_field:
        return None

    # Extraire le chemin relatif depuis MEDIA_ROOT
    relative_path = file_field.name

    # Construire l'URL vers notre vue PDF iframe
    pdf_iframe_path = reverse("serve_pdf_iframe", kwargs={"file_path": relative_path})

    # Construire l'URL absolue
    return request.build_absolute_uri(pdf_iframe_path)


def get_static_pdf_iframe_url(request, pdf_path):
    """
    Convertit un chemin PDF statique en URL utilisable pour iframe.

    Args:
        request: L'objet request Django
        pdf_path: Chemin relatif du PDF depuis MEDIA_ROOT (ex: "bails/notice_information.pdf")

    Returns:
        URL complète pour afficher le PDF en iframe
    """
    # Construire l'URL vers notre vue PDF iframe
    pdf_iframe_path = reverse("serve_pdf_iframe", kwargs={"file_path": pdf_path})

    # Construire l'URL absolue
    return request.build_absolute_uri(pdf_iframe_path)
