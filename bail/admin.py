from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Bailleur,
    BailSpecificites,
    Bien,
    Document,
    EtatLieux,
    EtatLieuxPhoto,
    EtatLieuxPiece,
    EtatLieuxPieceDetail,
    EtatLieuxSignatureRequest,
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


class EtatLieuxPieceInlineBien(admin.TabularInline):
    """Inline pour afficher les pièces d'état des lieux d'un bien"""

    model = EtatLieuxPiece
    extra = 0
    fields = ("nom", "type_piece")
    show_change_link = True


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
    inlines = [BailInline, EtatLieuxPieceInlineBien]

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
        "status",
    )
    list_filter = ("zone_tendue", "date_debut", "status")
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
                    "status",
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

    count_bailleurs.short_description = "Nombre de bailleurs"


# ==============================
# ADMIN POUR ÉTAT DES LIEUX
# ==============================


class EtatLieuxSignatureRequestInline(admin.TabularInline):
    """Inline pour les demandes de signature d'un état des lieux"""

    model = EtatLieuxSignatureRequest
    extra = 0
    fields = ("order", "bailleur_signataire", "locataire", "signed", "signed_at")
    readonly_fields = ("link_token", "signed_at", "otp_generated_at")


@admin.register(EtatLieux)
class EtatLieuxAdmin(admin.ModelAdmin):
    """Interface d'administration pour les états des lieux"""

    list_display = (
        "id",
        "type_etat_lieux",
        "bien_adresse",
        "bail_id",
        "date_creation",
        "pdf_link",
    )

    list_filter = (
        "type_etat_lieux",
        "date_creation",
    )

    search_fields = (
        "bail__bien__adresse",
        "bail__id",
    )

    readonly_fields = ("id", "date_creation", "date_modification", "pdf_link")

    fieldsets = (
        (None, {"fields": ("id", "bail", "type_etat_lieux")}),
        ("PDF", {"fields": ("pdf", "pdf_link"), "classes": ("collapse",)}),
        (
            "Métadonnées",
            {
                "fields": ("date_creation", "date_modification"),
                "classes": ("collapse",),
            },
        ),
    )

    inlines = [EtatLieuxSignatureRequestInline]

    def bien_adresse(self, obj):
        """Affiche l'adresse du bien"""
        return obj.bail.bien.adresse if obj.bail and obj.bail.bien else "-"

    bien_adresse.short_description = "Adresse du bien"

    def bail_id(self, obj):
        """Affiche l'ID du bail"""
        return obj.bail.id if obj.bail else "-"

    bail_id.short_description = "ID Bail"

    def pdf_link(self, obj):
        """Affiche un lien vers le PDF s'il existe"""
        if obj.pdf:
            return format_html(
                '<a href="{}" target="_blank">Télécharger PDF</a>', obj.pdf.url
            )
        return "Pas de PDF"

    pdf_link.short_description = "PDF"


@admin.register(EtatLieuxPiece)
class EtatLieuxPieceAdmin(admin.ModelAdmin):
    """Interface d'administration pour les pièces d'état des lieux"""

    list_display = (
        "nom",
        "type_piece",
        "bien_adresse",
    )

    list_filter = (
        "type_piece",
        "bien__type_bien",
    )

    search_fields = (
        "nom",
        "bien__adresse",
    )

    fieldsets = (
        (None, {"fields": ("bien", "nom", "type_piece")}),
    )

    def bien_adresse(self, obj):
        """Bien de la pièce"""
        return obj.bien.adresse

    bien_adresse.short_description = "Bien"


@admin.register(EtatLieuxPieceDetail)
class EtatLieuxPieceDetailAdmin(admin.ModelAdmin):
    """Interface d'administration pour les détails des pièces d'état des lieux"""

    list_display = (
        "piece_nom",
        "etat_lieux_type",
        "etat_lieux_bien",
    )

    list_filter = (
        "etat_lieux__type_etat_lieux",
        "piece__type_piece",
    )

    search_fields = (
        "piece__nom",
        "etat_lieux__bail__bien__adresse",
    )

    readonly_fields = ("elements", "equipments", "mobilier")

    fieldsets = (
        (None, {"fields": ("etat_lieux", "piece")}),
        (
            "Données JSON",
            {
                "fields": ("elements", "equipments", "mobilier"),
                "classes": ("collapse",),
            },
        ),
    )

    def piece_nom(self, obj):
        """Nom de la pièce"""
        return obj.piece.nom

    piece_nom.short_description = "Pièce"

    def etat_lieux_type(self, obj):
        """Type d'état des lieux"""
        return obj.etat_lieux.get_type_etat_lieux_display()

    etat_lieux_type.short_description = "Type état des lieux"

    def etat_lieux_bien(self, obj):
        """Bien de l'état des lieux"""
        return obj.etat_lieux.bail.bien.adresse

    etat_lieux_bien.short_description = "Bien"


@admin.register(EtatLieuxSignatureRequest)
class EtatLieuxSignatureRequestAdmin(admin.ModelAdmin):
    """Interface d'administration pour les demandes de signature d'état des lieux"""

    list_display = (
        "etat_lieux_display",
        "signataire_display",
        "order",
        "signed",
        "signed_at",
        "date_creation",
    )

    list_filter = (
        "signed",
        "etat_lieux__type_etat_lieux",
        "date_creation",
    )

    search_fields = (
        "bailleur_signataire__email",
        "locataire__email",
        "etat_lieux__bien__adresse",
    )

    readonly_fields = (
        "id",
        "link_token",
        "otp_generated_at",
        "signed_at",
        "date_creation",
        "signature_image_link",
    )

    fieldsets = (
        (None, {"fields": ("etat_lieux", "order", "bailleur_signataire", "locataire")}),
        (
            "Authentification",
            {
                "fields": ("link_token", "otp", "otp_generated_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Signature",
            {
                "fields": (
                    "signed",
                    "signed_at",
                    "signature_image",
                    "signature_image_link",
                ),
            },
        ),
        ("Métadonnées", {"fields": ("id", "date_creation"), "classes": ("collapse",)}),
    )

    def etat_lieux_display(self, obj):
        """Affichage de l'état des lieux"""
        etat_type = obj.etat_lieux.get_type_etat_lieux_display()
        bien_adresse = obj.etat_lieux.bail.bien.adresse
        return f"{etat_type} - {bien_adresse}"

    etat_lieux_display.short_description = "État des lieux"

    def signataire_display(self, obj):
        """Affichage du signataire"""
        if obj.bailleur_signataire:
            nom = f"{obj.bailleur_signataire.prenom} {obj.bailleur_signataire.nom}"
            return f"Bailleur: {nom}"
        elif obj.locataire:
            return f"Locataire: {obj.locataire.prenom} {obj.locataire.nom}"
        return "Aucun signataire"

    signataire_display.short_description = "Signataire"

    def signature_image_link(self, obj):
        """Lien vers l'image de signature"""
        if obj.signature_image:
            return format_html(
                '<a href="{}" target="_blank">Voir signature</a>',
                obj.signature_image.url,
            )
        return "Pas de signature"

    signature_image_link.short_description = "Image signature"


@admin.register(EtatLieuxPhoto)
class EtatLieuxPhotoAdmin(admin.ModelAdmin):
    """Interface d'administration pour les photos d'état des lieux"""

    list_display = (
        "id",
        "piece_display",
        "element_key",
        "photo_index",
        "nom_original",
        "image_preview",
        "date_upload",
    )

    list_filter = (
        "element_key",
        "date_upload",
        "piece__nom",
    )

    search_fields = (
        "piece__nom",
        "element_key",
        "nom_original",
        "piece__bien__adresse",
    )

    readonly_fields = (
        "id",
        "date_upload",
        "image_preview",
    )

    fieldsets = (
        (None, {"fields": ("piece", "element_key", "photo_index")}),
        ("Fichier", {"fields": ("image", "image_preview", "nom_original")}),
        (
            "Métadonnées",
            {
                "fields": ("id", "date_upload"),
                "classes": ("collapse",),
            },
        ),
    )

    def piece_display(self, obj):
        """Affichage de la pièce et du bien"""
        return f"{obj.piece.nom} - {obj.piece.bien.adresse}"

    piece_display.short_description = "Pièce"

    def image_preview(self, obj):
        """Prévisualisation de l'image"""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px;" />',
                obj.image.url,
            )
        return "Pas d'image"

    image_preview.short_description = "Aperçu"
