from django import template

register = template.Library()


@register.filter
def has_compteur_data(compteurs):
    """
    V\u00e9rifie si les compteurs contiennent des donn\u00e9es r\u00e9elles
    Retourne False si compteurs est None ou ne contient que des objets vides
    """
    if not compteurs:
        return False

    if not isinstance(compteurs, dict):
        return False

    # V\u00e9rifier si au moins un compteur a des donn\u00e9es
    for compteur_type, compteur_data in compteurs.items():
        if isinstance(compteur_data, dict) and compteur_data:
            # V\u00e9rifier si le compteur a au moins une valeur non vide
            for value in compteur_data.values():
                if value not in [None, '', {}]:
                    return True

    return False


@register.filter
def has_electricite_data(compteur):
    """V\u00e9rifie si le compteur \u00e9lectricit\u00e9 a des donn\u00e9es"""
    if not compteur or not isinstance(compteur, dict):
        return False

    return any(
        compteur.get(field) not in [None, '', {}]
        for field in ['numero', 'hp', 'hc', 'releve']
    )


@register.filter
def has_gaz_data(compteur):
    """V\u00e9rifie si le compteur gaz a des donn\u00e9es"""
    if not compteur or not isinstance(compteur, dict):
        return False

    return any(
        compteur.get(field) not in [None, '', {}]
        for field in ['numero', 'index']
    )


@register.filter
def has_eau_data(compteur):
    """V\u00e9rifie si le compteur eau a des donn\u00e9es"""
    if not compteur or not isinstance(compteur, dict):
        return False

    return any(
        compteur.get(field) not in [None, '', {}]
        for field in ['numero', 'froide', 'chaude', 'releve']
    )