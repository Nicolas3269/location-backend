import base64
from pathlib import Path
from django.conf import settings
from django.urls import reverse


def get_logo_pdf_base64_data_uri():
    """
    Génère l'URI data en base64 du logo Hestia pour l'utiliser dans les CSS @page.
    Crée une version réduite du SVG (12px) avec alignement vertical centré.

    Returns:
        str: URI data complète (data:image/svg+xml;base64,...)
    """
    logo_path = Path(settings.BASE_DIR) / "static" / "images" / "logo.svg"

    with open(logo_path, "rb") as f:
        svg_content = f.read().decode("utf-8")

    import re

    # Remplacer width et height pour 13px
    svg_content = re.sub(r'width="[^"]*"', 'width="13"', svg_content, count=1)
    svg_content = re.sub(r'height="[^"]*"', 'height="13"', svg_content, count=1)

    # Modifier la viewBox pour descendre le logo visuellement
    # viewBox originale : "0 0 187.07032 186.52344"
    # Pour faire descendre : ajouter espace en HAUT (Y négatif) + augmenter hauteur totale
    # Nouvelle : "0 -80 187.07032 266.52344" (80 unités d'espace en haut pour descendre encore)
    svg_content = re.sub(
        r'viewBox="0 0 187\.07032 186\.52344"',
        'viewBox="0 -80 187.07032 266.52344"',
        svg_content
    )

    # Utiliser align bottom pour que le logo soit en bas du container
    svg_content = re.sub(
        r'preserveAspectRatio="[^"]*"',
        'preserveAspectRatio="xMidYMax meet"',
        svg_content
    )

    # Remplacer la couleur du logo (#3e3c41) par la couleur du texte du footer (#999999)
    svg_content = svg_content.replace('fill:#3e3c41', 'fill:#999999')

    # Ré-encoder en base64
    logo_bytes = svg_content.encode("utf-8")
    base64_encoded = base64.b64encode(logo_bytes).decode("utf-8")
    return f"data:image/svg+xml;base64,{base64_encoded}"


def get_mila_signature_base64_data_uri():
    """
    Génère l'URI data en base64 de la signature Mila pour les PDF assurance.

    Returns:
        str: URI data complète (data:image/png;base64,...)
    """
    signature_path = Path(settings.BASE_DIR) / "static" / "images" / "sign_mila.png"

    with open(signature_path, "rb") as f:
        image_bytes = f.read()

    base64_encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/png;base64,{base64_encoded}"


def get_hestia_signature_base64_data_uri():
    """
    Génère l'URI data en base64 de la signature Hestia pour les PDF assurance.

    Returns:
        str: URI data complète (data:image/png;base64,...)
    """
    signature_path = Path(settings.BASE_DIR) / "static" / "images" / "sign_hestia.png"

    with open(signature_path, "rb") as f:
        image_bytes = f.read()

    base64_encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/png;base64,{base64_encoded}"


def get_static_pdf_iframe_url(request, pdf_path):
    """
    Convertit un chemin PDF statique en URL utilisable pour iframe.

    Note: Les fichiers statiques sont TOUJOURS servis localement via Django
    (pas sur S3/MinIO), donc build_absolute_uri() est nécessaire ici.

    Args:
        request: L'objet request Django
        pdf_path: Chemin relatif du PDF depuis static/pdfs/
                  (ex: "bails/notice_information.pdf")

    Returns:
        URL complète pour afficher le PDF statique en iframe
    """
    # Construire l'URL vers notre vue PDF static iframe
    pdf_iframe_path = reverse(
        "serve_static_pdf_iframe", kwargs={"file_path": pdf_path}
    )

    # Construire l'URL absolue (toujours nécessaire pour fichiers statiques)
    return request.build_absolute_uri(pdf_iframe_path)
