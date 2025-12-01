"""
Template filters pour la grammaire française (articles, contractions).

Usage dans les templates Django/MJML:
    {% load french_grammar %}

    {{ "bail"|avec_le }}           → "le bail"
    {{ "état des lieux"|avec_le }} → "l'état des lieux"
    {{ "bail"|avec_de }}           → "du bail"
    {{ "état des lieux"|avec_de }} → "de l'état des lieux"
"""

from django import template

register = template.Library()

# Voyelles et h muet pour élision
VOYELLES = "aeiouhàâäéèêëïîôùûüœæ"


def commence_par_voyelle(mot: str) -> bool:
    """Vérifie si un mot commence par une voyelle (pour l'élision)."""
    if not mot:
        return False
    return mot[0].lower() in VOYELLES


@register.filter(name="avec_le")
def avec_le(value: str) -> str:
    """
    Ajoute l'article défini approprié (le/l').

    Exemples:
        {{ "bail"|avec_le }}           → "le bail"
        {{ "état des lieux"|avec_le }} → "l'état des lieux"
        {{ "avenant"|avec_le }}        → "l'avenant"
    """
    if not value:
        return value

    if commence_par_voyelle(value):
        return f"l'{value}"
    return f"le {value}"


@register.filter(name="avec_de")
def avec_de(value: str) -> str:
    """
    Ajoute la préposition "de" avec contraction appropriée (du/de l').

    Exemples:
        {{ "bail"|avec_de }}           → "du bail"
        {{ "état des lieux"|avec_de }} → "de l'état des lieux"
        {{ "avenant"|avec_de }}        → "de l'avenant"
    """
    if not value:
        return value

    if commence_par_voyelle(value):
        return f"de l'{value}"
    return f"du {value}"


@register.filter(name="avec_a")
def avec_a(value: str) -> str:
    """
    Ajoute la préposition "à" avec contraction appropriée (au/à l').

    Exemples:
        {{ "bail"|avec_a }}           → "au bail"
        {{ "état des lieux"|avec_a }} → "à l'état des lieux"
    """
    if not value:
        return value

    if commence_par_voyelle(value):
        return f"à l'{value}"
    return f"au {value}"
