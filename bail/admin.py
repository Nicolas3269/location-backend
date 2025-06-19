from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Bailleur,
    BailSpecificites,
    Bien,
    Document,
    Locataire,
    Personne,
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


class BailInline(admin.TabularInline):
    model = BailSpecificites
    extra = 0
    fields = ("get_locataires", "date_debut", "date_fin", "montant_loyer")
    show_change_link = True
    readonly_fields = ("get_locataires",)

    def get_locataires(self, obj):
        locataires = [f"{loc.prenom} {loc.nom}" for loc in obj.locataires.all()]
        return ", ".join(locataires)

    get_locataires.short_description = "Locataires"


class DocumentInline(admin.TabularInline):
    """Inline pour afficher les documents attachés au bail"""

    model = Document
    fk_name = "bail"
    extra = 0
    fields = (
        "type_document",
        "nom_original",
        "file_link",
        "date_creation",
        "uploade_par",
    )
    readonly_fields = ("file_link", "date_creation", "uploade_par")
    show_change_link = True

    def file_link(self, obj):
        """Affiche un lien vers le fichier"""
        if obj.fichier:
            return format_html(
                '<a href="{}" target="_blank">📄 Voir le fichier</a>',
                obj.file.url,
            )
        return "-"

    file_link.short_description = "Fichier"


@admin.register(Bien)
class BienAdmin(admin.ModelAdmin):
    """Interface d'administration pour les biens immobiliers"""

    list_display = (
        "adresse",
        "display_bailleurs",
        "type_bien",
        "superficie",
        "display_nb_pieces",
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
    inlines = [BailInline]

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

    def display_nb_pieces(self, obj):
        """Affiche le nombre de pièces principales calculé"""
        return f"{obj.nombre_pieces_principales} pièces"

    display_nb_pieces.short_description = "Pièces principales"

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

    list_display = ("get_nom", "get_prenom", "email", "count_bails")
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
        "display_locataires",
        "date_debut",
        "date_fin",
        "montant_loyer",
        "zone_tendue",
        "display_documents_status",
        "is_draft",
    )
    list_filter = ("zone_tendue", "date_debut", "is_draft")
    search_fields = ("bien__adresse", "locataires__nom", "locataires__prenom")
    date_hierarchy = "date_debut"
    inlines = [DocumentInline]

    fieldsets = (
        ("Parties concernées", {"fields": ("bien", "locataires")}),
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
                "fields": (
                    "zone_tendue",
                    "rent_price_id",
                    "justificatif_complement_loyer",
                ),
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
        (
            "Documents et annexes",
            {
                "fields": (
                    "is_draft",
                    "pdf",
                    "latest_pdf",
                    "grille_vetuste_pdf",
                    "notice_information_pdf",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def display_documents_status(self, obj):
        """Affiche le statut des documents annexes"""
        docs = []
        if obj.pdf:
            docs.append('<span style="color: green;">📄 Bail</span>')
        if obj.grille_vetuste_pdf:
            docs.append('<span style="color: green;">📋 Grille vétusté</span>')
        if obj.notice_information_pdf:
            docs.append('<span style="color: green;">📋 Notice info</span>')

        if not docs:
            return '<span style="color: gray;">Aucun document</span>'

        return format_html("<br>".join(docs))

    display_documents_status.short_description = "Documents"
    display_documents_status.allow_tags = True

    def display_locataires(self, obj):
        return ", ".join(
            [
                f"{locataire.prenom} {locataire.nom}"
                for locataire in obj.locataires.all()
            ]
        )

    display_locataires.short_description = "Locataires"

    # Update formfield_for_foreignkey to remove proprietaire reference
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "bien":
            kwargs["queryset"] = Bien.objects.all()  # No select_related needed
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


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

    count_bailleurs.short_description = "Bailleurs"
