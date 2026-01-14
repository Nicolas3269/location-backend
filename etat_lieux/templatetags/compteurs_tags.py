from django import template

register = template.Library()


@register.filter
def has_compteur_data(compteurs):
    """
    Vérifie si les compteurs contiennent des données réelles
    Retourne False si compteurs est None ou ne contient que des objets vides
    """
    if not compteurs:
        return False

    if not isinstance(compteurs, dict):
        return False

    # Vérifier si au moins un compteur a des données
    for compteur_type, compteur_data in compteurs.items():
        if isinstance(compteur_data, dict) and compteur_data:
            # Vérifier si le compteur a au moins une valeur non vide
            for value in compteur_data.values():
                if value not in [None, '', {}]:
                    return True

    return False


@register.filter
def has_electricite_data(compteur):
    """Vérifie si le compteur électricité a des données"""
    if not compteur or not isinstance(compteur, dict):
        return False

    fields = [
        'numero', 'hp', 'hc', 'releve',  # Standard
        'hp_saison_basse', 'hp_saison_haute',  # Saisonnier
        'hc_saison_basse', 'hc_saison_haute',
    ]
    return any(
        compteur.get(field) not in [None, '', {}]
        for field in fields
    )


@register.filter
def has_seasonal_data(compteur):
    """Vérifie si le compteur a des données saisonnières"""
    if not compteur or not isinstance(compteur, dict):
        return False

    seasonal_fields = [
        'hp_saison_basse', 'hp_saison_haute',
        'hc_saison_basse', 'hc_saison_haute'
    ]
    return any(
        compteur.get(field) not in [None, '', {}]
        for field in seasonal_fields
    )


@register.filter
def has_gaz_data(compteur):
    """Vérifie si le compteur gaz a des données"""
    if not compteur or not isinstance(compteur, dict):
        return False

    return any(
        compteur.get(field) not in [None, '', {}]
        for field in ['numero', 'index']
    )


@register.filter
def has_eau_data(compteur):
    """Vérifie si le compteur eau a des données"""
    if not compteur or not isinstance(compteur, dict):
        return False

    return any(
        compteur.get(field) not in [None, '', {}]
        for field in ['numero', 'froide', 'chaude', 'releve']
    )
