from django.contrib import admin
from django.utils.html import format_html

from .models import BailSpecificites, Bien, Locataire, Proprietaire


class BienInline(admin.TabularInline):
    """Affiche les biens associés à un propriétaire dans l'admin"""

    model = Bien
    extra = 0
    fields = ("adresse", "type_bien", "superficie", "nb_pieces")
    show_change_link = True


@admin.register(Proprietaire)
class ProprietaireAdmin(admin.ModelAdmin):
    """Interface d'administration pour les propriétaires"""

    list_display = ("nom", "prenom", "email", "telephone", "count_biens")
    search_fields = ("nom", "prenom", "email", "telephone")
    inlines = [BienInline]

    fieldsets = (
        ("Identité", {"fields": ("nom", "prenom")}),
        ("Coordonnées", {"fields": ("adresse", "telephone", "email")}),
        ("Informations bancaires", {"fields": ("iban",), "classes": ("collapse",)}),
    )

    def count_biens(self, obj):
        """Affiche le nombre de biens du propriétaire"""
        count = obj.biens.count()
        return count

    count_biens.short_description = "Biens"


class BailInline(admin.TabularInline):
    """Affiche les bails associés à un bien dans l'admin"""

    model = BailSpecificites
    extra = 0
    fields = ("locataire", "date_debut", "date_fin", "montant_loyer")
    show_change_link = True


@admin.register(Bien)
class BienAdmin(admin.ModelAdmin):
    """Interface d'administration pour les biens immobiliers"""

    list_display = (
        "adresse",
        "proprietaire",
        "type_bien",
        "superficie",
        "nb_pieces",
        "meuble",
        "display_dpe_class",
    )
    list_filter = (
        "type_bien",
        "nb_pieces",
        "meuble",
        "classe_dpe",
        "periode_construction",
    )
    search_fields = ("adresse", "proprietaire__nom", "proprietaire__prenom")
    inlines = [BailInline]

    fieldsets = (
        ("Propriétaire", {"fields": ("proprietaire",)}),
        ("Localisation", {"fields": ("adresse", "latitude", "longitude")}),
        (
            "Caractéristiques",
            {
                "fields": (
                    "type_bien",
                    "superficie",
                    "nb_pieces",
                    "etage",
                    "porte",
                    "dernier_etage",
                    "periode_construction",
                    "meuble",
                )
            },
        ),
        (
            "DPE",
            {
                "fields": ("classe_dpe", "depenses_energetiques"),
                "classes": ("collapse",),
            },
        ),
        (
            "Informations complémentaires",
            {
                "fields": ("annexes", "additionnal_description"),
                "classes": ("collapse",),
            },
        ),
    )

    def display_dpe_class(self, obj):
        """Affiche la classe DPE avec un code couleur"""
        colors = {
            "A": "#33a557",
            "B": "#79c267",
            "C": "#c3d545",
            "D": "#fff12c",
            "E": "#edc22e",
            "F": "#ec6730",
            "G": "#e53946",
            "NC": "#aaaaaa",
        }
        color = colors.get(obj.classe_dpe, "#aaaaaa")
        return format_html(
            '<span style="font-weight: bold; color: white; background-color: {}; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.classe_dpe,
        )

    display_dpe_class.short_description = "DPE"


@admin.register(Locataire)
class LocataireAdmin(admin.ModelAdmin):
    """Interface d'administration pour les locataires"""

    list_display = ("nom", "prenom", "email", "telephone", "count_bails")
    search_fields = ("nom", "prenom", "email", "telephone")

    fieldsets = (
        ("Identité", {"fields": ("nom", "prenom", "date_naissance", "lieu_naissance")}),
        ("Coordonnées", {"fields": ("adresse_actuelle", "telephone", "email")}),
        (
            "Informations professionnelles",
            {
                "fields": ("profession", "employeur", "revenu_mensuel"),
                "classes": ("collapse",),
            },
        ),
        (
            "Documents d'identité",
            {
                "fields": ("num_carte_identite", "date_emission_ci"),
                "classes": ("collapse",),
            },
        ),
    )

    def count_bails(self, obj):
        """Affiche le nombre de bails du locataire"""
        count = obj.bails.count()
        return count

    count_bails.short_description = "Bails"


@admin.register(BailSpecificites)
class BailSpecificitesAdmin(admin.ModelAdmin):
    """Interface d'administration pour les baux"""

    list_display = (
        "bien",
        "locataire",
        "date_debut",
        "date_fin",
        "montant_loyer",
        "zone_tendue",
    )
    list_filter = ("zone_tendue", "date_debut")
    search_fields = ("bien__adresse", "locataire__nom", "locataire__prenom")
    date_hierarchy = "date_debut"

    fieldsets = (
        ("Parties concernées", {"fields": ("bien", "locataire")}),
        (
            "Durée",
            {
                "fields": (
                    "date_debut",
                    "date_fin",
                    "date_signature",
                    "date_etat_lieux_entree",
                )
            },
        ),
        (
            "Conditions financières",
            {
                "fields": (
                    "montant_loyer",
                    "montant_charges",
                    "jour_paiement",
                    "depot_garantie",
                )
            },
        ),
        (
            "Encadrement des loyers",
            {
                "fields": ("zone_tendue", "prix_reference", "complement_loyer"),
                "classes": ("collapse",),
            },
        ),
        (
            "Relevés compteurs",
            {
                "fields": (
                    "releve_eau_entree",
                    "releve_elec_entree",
                    "releve_gaz_entree",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Observations", {"fields": ("observations",)}),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Optimise les requêtes pour les champs ForeignKey"""
        if db_field.name == "bien":
            kwargs["queryset"] = Bien.objects.select_related("proprietaire")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
