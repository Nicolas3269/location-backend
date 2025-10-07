"""
Service pour générer la liste des documents à signer
"""

from typing import Any, Dict, List

from bail.models import Bail, Document, DocumentType
from etat_lieux.models import EtatLieux


def get_bail_documents_list(bail: Bail, request) -> List[Dict[str, Any]]:
    """
    Retourne la liste des documents associés à un bail

    Args:
        bail: Instance de Bail
        request: HttpRequest pour build_absolute_uri

    Returns:
        Liste de dictionnaires avec name, url, type, required
    """
    from bail.views import get_static_pdf_iframe_url

    documents_list = []

    # 1. Contrat de bail (PDF principal)
    if bail.pdf:
        documents_list.append(
            {
                "name": "Contrat de bail",
                "url": request.build_absolute_uri(bail.pdf.url),
                "type": "bail",
                "required": True,
            }
        )

    # 2. Notice d'information (statique)
    # Toujours inclure la notice statique, même si notice_information_pdf est None
    notice_url = get_static_pdf_iframe_url(request, "bails/notice_information.pdf")
    documents_list.append(
        {
            "name": "Notice d'information",
            "url": notice_url,
            "type": "notice",
            "required": True,
        }
    )

    # 3. Diagnostics techniques
    diagnostics = Document.objects.filter(
        bail=bail, type_document=DocumentType.DIAGNOSTIC
    )
    for doc in diagnostics:
        documents_list.append(
            {
                "name": f"Diagnostic - {doc.nom_original}",
                "url": request.build_absolute_uri(doc.file.url),
                "type": "diagnostic",
                "required": False,
            }
        )

    # 4. Permis de louer
    permis = Document.objects.filter(
        bail=bail, type_document=DocumentType.PERMIS_DE_LOUER
    )
    for doc in permis:
        documents_list.append(
            {
                "name": f"Permis de louer - {doc.nom_original}",
                "url": request.build_absolute_uri(doc.file.url),
                "type": "permis_de_louer",
                "required": False,
            }
        )

    return documents_list


def get_etat_lieux_documents_list(
    etat_lieux: EtatLieux, request
) -> List[Dict[str, Any]]:
    """
    Retourne la liste des documents associés à un état des lieux

    Args:
        etat_lieux: Instance de EtatLieux
        request: HttpRequest pour build_absolute_uri

    Returns:
        Liste de dictionnaires avec name, url, type, required
    """
    documents_list = []

    # 1. État des lieux principal (PDF)
    if etat_lieux.pdf:
        type_label = (
            "État des lieux d'entrée"
            if etat_lieux.type_etat_lieux == "entree"
            else "État des lieux de sortie"
        )
        documents_list.append(
            {
                "name": type_label,
                "url": request.build_absolute_uri(etat_lieux.pdf.url),
                "type": "etat_lieux",
                "required": True,
            }
        )

    # 2. Grille de vétusté (si présente)
    if hasattr(etat_lieux, "grille_vetuste_pdf") and etat_lieux.grille_vetuste_pdf:
        documents_list.append(
            {
                "name": "Grille de vétusté",
                "url": request.build_absolute_uri(etat_lieux.grille_vetuste_pdf.url),
                "type": "grille_vetuste",
                "required": False,
            }
        )

    return documents_list
