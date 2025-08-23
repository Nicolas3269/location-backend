from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Bailleur,
    Bien,
    Locataire,
    Location,
    Mandataire,
    Personne,
    RentTerms,
    Societe,
)


class BailleurBiensInline(admin.TabularInline):
    model = Bien.bailleurs.through
    extra = 1
    verbose_name = "Bien"
    verbose_name_plural = "Biens"


@admin.register(Bailleur)
class BailleurAdmin(admin.ModelAdmin):
    """Interface d'administration pour les bailleurs"""

    list_display = (
        "get_full_name",
        "bailleur_type",
        "get_email",
        "count_biens",
    )
    search_fields = (
        "personne__nom",
        "personne__prenom",
        "personne__email",
        "societe__raison_sociale",
        "societe__email",
    )
    list_filter = ()  # Suppression du filtre sur bailleur_type car c'est une propriété
    inlines = [BailleurBiensInline]

    fieldsets = (
        (
            "Personne physique",
            {
                "fields": ("personne",),
                "classes": ("collapse",),
                "description": "Sélectionner si le bailleur est une personne physique",
            },
        ),
        (
            "Société",
            {
                "fields": ("societe",),
                "classes": ("collapse",),
                "description": "Sélectionner si le bailleur est une société",
            },
        ),
        ("Signataire", {"fields": ("signataire",)}),
    )

    def get_full_name(self, obj: Bailleur):
        return obj.full_name

    get_full_name.short_description = "Nom"

    def get_email(self, obj):
        if obj.personne:
            return obj.personne.email
        elif obj.societe:
            return obj.societe.email
        return "-"

    get_email.short_description = "Email"

    def count_biens(self, obj):
        """Affiche le nombre de biens du bailleur"""
        count = obj.biens.count()
        return count

    count_biens.short_description = "Biens"


class LocationInline(admin.TabularInline):
    """Inline pour afficher les locations d'un bien"""

    model = Location
    extra = 0
    fields = ("get_locataires", "date_debut", "date_fin", "get_montant_loyer")
    show_change_link = True
    readonly_fields = ("get_locataires", "get_montant_loyer")

    def get_locataires(self, obj):
        locataires = [f"{loc.prenom} {loc.nom}" for loc in obj.locataires.all()]
        return ", ".join(locataires)

    get_locataires.short_description = "Locataires"

    def get_montant_loyer(self, obj):
        if hasattr(obj, "rent_terms"):
            return obj.rent_terms.montant_loyer
        return "-"

    get_montant_loyer.short_description = "Loyer"


@admin.register(Bien)
class BienAdmin(admin.ModelAdmin):
    """Interface d'administration pour les biens immobiliers"""

    list_display = (
        "adresse",
        "display_bailleurs",
        "type_bien",
        "superficie",
        "display_nombre_pieces_principales",
        "meuble",
        "display_dpe_class",
    )
    list_filter = (
        "type_bien",
        "meuble",
        "classe_dpe",
        "periode_construction",
    )
    search_fields = (
        "adresse",
        "bailleurs__personne__nom",
        "bailleurs__personne__prenom",
        "bailleurs__societe__raison_sociale",
    )
    inlines = [LocationInline]

    fieldsets = (
        ("Bailleurs", {"fields": ("bailleurs",)}),
        ("Localisation", {"fields": ("adresse", "latitude", "longitude")}),
        (
            "Caractéristiques",
            {
                "fields": (
                    "type_bien",
                    "superficie",
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
            "NA": "#aaaaaa",
        }
        color = colors.get(obj.classe_dpe, "#aaaaaa")
        return format_html(
            '<span style="font-weight: bold; color: white; '
            'background-color: {}; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.classe_dpe,
        )

    display_dpe_class.short_description = "DPE"

    def display_nombre_pieces_principales(self, obj):
        """Affiche le nombre de pièces principales calculé"""
        return f"{obj.nombre_pieces_principales} pièces"

    display_nombre_pieces_principales.short_description = "Pièces principales"

    def display_bailleurs(self, obj):
        bailleurs_names = []
        for bailleur in obj.bailleurs.all():
            if bailleur.personne:
                nom_complet = f"{bailleur.personne.prenom} {bailleur.personne.nom}"
                bailleurs_names.append(nom_complet)
            elif bailleur.societe:
                bailleurs_names.append(bailleur.societe.raison_sociale)
        return ", ".join(bailleurs_names)

    display_bailleurs.short_description = "Bailleurs"


@admin.register(Locataire)
class LocataireAdmin(admin.ModelAdmin):
    """Interface d'administration pour les locataires"""

    list_display = ("get_nom", "get_prenom", "email", "count_locations")
    search_fields = ("nom", "prenom", "email")

    fieldsets = (
        (
            "Informations personnelles",
            {"fields": ("nom", "prenom", "date_naissance", "email", "adresse")},
        ),
        (
            "Informations spécifiques",
            {"fields": ("lieu_naissance", "adresse_actuelle")},
        ),
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
        (
            "Autres",
            {
                "fields": ("caution_requise", "iban"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_nom(self, obj):
        """Affiche le nom"""
        return obj.nom

    get_nom.short_description = "Nom"
    get_nom.admin_order_field = "nom"

    def get_prenom(self, obj):
        """Affiche le prénom"""
        return obj.prenom

    get_prenom.short_description = "Prénom"
    get_prenom.admin_order_field = "prenom"

    def count_locations(self, obj):
        """Affiche le nombre de locations du locataire"""
        count = obj.locations.count()
        return count

    count_locations.short_description = "Locations"


@admin.register(Personne)
class PersonneAdmin(admin.ModelAdmin):
    """Interface d'administration pour les personnes physiques"""

    list_display = ("get_full_name", "email", "date_naissance", "count_bailleurs")
    search_fields = ("nom", "prenom", "email")
    list_filter = ("date_naissance",)

    fieldsets = (
        (
            "Informations personnelles",
            {"fields": ("nom", "prenom", "date_naissance", "email")},
        ),
        ("Adresse", {"fields": ("adresse",)}),
        (
            "Informations bancaires",
            {
                "fields": ("iban",),
                "classes": ("collapse",),
            },
        ),
    )

    def get_full_name(self, obj):
        """Affiche le nom complet"""
        return obj.full_name

    get_full_name.short_description = "Nom complet"
    get_full_name.admin_order_field = "nom"

    def count_bailleurs(self, obj):
        """Affiche le nombre de bailleurs liés à cette personne"""
        count = obj.bailleurs.count()
        return count

    count_bailleurs.short_description = "Bailleurs"


@admin.register(Societe)
class SocieteAdmin(admin.ModelAdmin):
    """Interface d'administration pour les sociétés"""

    list_display = (
        "raison_sociale",
        "siret",
        "forme_juridique",
        "email",
        "count_bailleurs",
    )
    search_fields = ("raison_sociale", "siret", "email", "forme_juridique")
    list_filter = ("forme_juridique",)

    fieldsets = (
        (
            "Informations de la société",
            {"fields": ("raison_sociale", "siret", "forme_juridique")},
        ),
        ("Contact", {"fields": ("email", "adresse")}),
        (
            "Informations bancaires",
            {
                "fields": ("iban",),
                "classes": ("collapse",),
            },
        ),
    )

    def count_bailleurs(self, obj):
        """Affiche le nombre de bailleurs liés à cette société"""
        count = obj.bailleurs.count()
        return count

    count_bailleurs.short_description = "Nombre de bailleurs"


@admin.register(Mandataire)
class MandataireAdmin(admin.ModelAdmin):
    """Interface d'administration pour les mandataires"""

    list_display = (
        "get_societe_name",
        "get_signataire_name",
        "numero_carte_professionnelle",
        "date_debut_mandat",
        "date_fin_mandat",
    )
    search_fields = (
        "societe__raison_sociale",
        "signataire__nom",
        "signataire__prenom",
        "numero_carte_professionnelle",
    )
    list_filter = ("date_debut_mandat", "date_fin_mandat")

    fieldsets = (
        (
            "Société mandataire",
            {"fields": ("societe",)},
        ),
        (
            "Signataire",
            {"fields": ("signataire",)},
        ),
        (
            "Informations du mandat",
            {
                "fields": (
                    "numero_carte_professionnelle",
                    "date_debut_mandat",
                    "date_fin_mandat",
                )
            },
        ),
    )

    def get_societe_name(self, obj):
        """Affiche le nom de la société"""
        return obj.societe.raison_sociale

    get_societe_name.short_description = "Société"
    get_societe_name.admin_order_field = "societe__raison_sociale"

    def get_signataire_name(self, obj):
        """Affiche le nom du signataire"""
        return obj.signataire.full_name

    get_signataire_name.short_description = "Signataire"
    get_signataire_name.admin_order_field = "signataire__nom"


class RentTermsInline(admin.StackedInline):
    """Inline pour les conditions financières"""

    model = RentTerms
    extra = 0
    fields = (
        "montant_loyer",
        "type_charges",
        "montant_charges",
        "jour_paiement",
        "depot_garantie",
        "zone_tendue",
        "permis_de_louer",
        "rent_price_id",
        "justificatif_complement_loyer",
    )


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    """Interface d'administration pour les locations"""

    list_display = (
        "id",
        "bien_address",
        "display_locataires",
        "date_debut",
        "date_fin",
        "get_montant_loyer",
        "created_from",
    )
    list_filter = ("created_from", "date_debut", "solidaires")
    search_fields = (
        "bien__adresse",
        "locataires__nom",
        "locataires__prenom",
    )
    date_hierarchy = "date_debut"
    inlines = [RentTermsInline]

    fieldsets = (
        (
            "Parties concernées",
            {
                "fields": (
                    "bien",
                    "mandataire",
                    "locataires",
                    "solidaires",
                    "garants",
                )
            },
        ),
        (
            "Durée",
            {
                "fields": (
                    "date_debut",
                    "date_fin",
                )
            },
        ),
        (
            "Métadonnées",
            {
                "fields": (
                    "created_from",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")

    def bien_address(self, obj):
        """Affiche l'adresse du bien"""
        return obj.bien.adresse

    bien_address.short_description = "Adresse du bien"
    bien_address.admin_order_field = "bien__adresse"

    def display_locataires(self, obj):
        """Affiche les locataires"""
        locataires = [f"{loc.prenom} {loc.nom}" for loc in obj.locataires.all()]
        return ", ".join(locataires)

    display_locataires.short_description = "Locataires"

    def get_montant_loyer(self, obj):
        """Affiche le montant du loyer"""
        if hasattr(obj, "rent_terms"):
            return obj.rent_terms.montant_loyer
        return "-"

    get_montant_loyer.short_description = "Loyer"


@admin.register(RentTerms)
class RentTermsAdmin(admin.ModelAdmin):
    """Interface d'administration pour les conditions financières"""

    list_display = (
        "location",
        "montant_loyer",
        "montant_charges",
        "depot_garantie",
        "zone_tendue",
        "permis_de_louer",
    )
    list_filter = ("zone_tendue", "permis_de_louer", "type_charges")
    search_fields = ("location__bien__adresse",)

    fieldsets = (
        (
            "Location",
            {"fields": ("location",)},
        ),
        (
            "Montants",
            {
                "fields": (
                    "montant_loyer",
                    "type_charges",
                    "montant_charges",
                    "jour_paiement",
                    "depot_garantie",
                )
            },
        ),
        (
            "Encadrement des loyers",
            {
                "fields": (
                    "zone_tendue",
                    "permis_de_louer",
                    "rent_price_id",
                    "justificatif_complement_loyer",
                ),
                "classes": ("collapse",),
            },
        ),
    )
