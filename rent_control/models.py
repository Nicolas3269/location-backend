from django.contrib.gis.db import models

from rent_control.management.commands.constants import DEFAULT_YEAR

from .choices import ConstructionPeriod, PropertyType, Region, RoomCount


class RentControlArea(models.Model):
    """Zone géographique d'encadrement des loyers"""

    region = models.CharField(max_length=20, choices=Region.choices)
    reference_year = models.IntegerField()
    zone_id = models.CharField(max_length=20, null=False)
    quartier_id = models.CharField(max_length=20, null=True, blank=True)
    zone_name = models.CharField(max_length=50, null=True, blank=True)

    # Geometry field
    geometry = models.MultiPolygonField(srid=4326)

    class Meta:
        indexes = [models.Index(fields=["region", "zone_id", "reference_year"])]

    def __str__(self):
        return f"{self.get_region_display()} - {self.zone_name} ({self.reference_year})"


class RentPrice(models.Model):
    """Prix par caractéristiques de logement dans une zone"""

    areas = models.ManyToManyField(RentControlArea, related_name="prices")
    reference_year = models.IntegerField(default=DEFAULT_YEAR)

    # Caractéristiques avec énums
    property_type = models.CharField(
        max_length=20,
        choices=PropertyType.choices,
        null=True,  # Permet NULL dans la base de données
        blank=True,
    )
    room_count = models.CharField(max_length=10, choices=RoomCount.choices)
    construction_period = models.CharField(
        max_length=20, choices=ConstructionPeriod.choices
    )
    furnished = models.BooleanField()

    # Prix
    reference_price = models.DecimalField(max_digits=6, decimal_places=2)
    min_price = models.DecimalField(max_digits=6, decimal_places=2)
    max_price = models.DecimalField(max_digits=6, decimal_places=2)


class RentMap(RentControlArea):
    class Meta:
        proxy = True
        verbose_name = "Carte des zones"
        verbose_name_plural = "Carte des zones"


class ZoneTendue(models.Model):
    """Zone tendue selon la classification INSEE"""

    agglomerations = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Agglomérations (unités urbaines au sens de l'INSEE)",
    )
    departements = models.CharField(
        max_length=255, null=False, verbose_name="Départements"
    )
    communes = models.CharField(max_length=255, null=False, verbose_name="Communes")
    code_insee = models.CharField(
        max_length=10,
        null=False,
        db_index=True,
        verbose_name="Code INSEE",
    )

    class Meta:
        indexes = [models.Index(fields=["code_insee"])]
        verbose_name = "Zone tendue"
        verbose_name_plural = "Zones tendues"

    def __str__(self):
        return f"{self.communes} ({self.code_insee})"


class ZoneTresTendue(models.Model):
    """
    Zone très tendue (Zone A bis) selon l'arrêté du 1er août 2014
    Annexe à l'arrêté du 1er août 2014 pris en application de l'article R. 304-1 du CCH
    """

    departement_code = models.CharField(
        max_length=3,
        null=False,
        verbose_name="Code département",
    )
    departement_nom = models.CharField(
        max_length=100, null=False, verbose_name="Département"
    )
    commune = models.CharField(max_length=255, null=False, verbose_name="Commune")

    class Meta:
        indexes = [
            models.Index(fields=["departement_code", "commune"]),
            models.Index(fields=["commune"]),
        ]
        verbose_name = "Zone très tendue (A bis)"
        verbose_name_plural = "Zones très tendues (A bis)"

    def __str__(self):
        return f"{self.commune} ({self.departement_code}) - {self.departement_nom}"


class ZoneTendueTouristique(models.Model):
    """
    Zone tendue touristique selon la réglementation sur les meublés de tourisme
    Communes où s'applique la règle des 120 jours maximum pour les locations touristiques
    """

    departement_code = models.CharField(
        max_length=3,
        null=False,
        verbose_name="Code département",
    )
    commune = models.CharField(max_length=255, null=False, verbose_name="Commune")
    code_insee = models.CharField(
        max_length=10,
        null=False,
        db_index=True,
        verbose_name="Code INSEE",
    )

    class Meta:
        indexes = [
            models.Index(fields=["code_insee"]),
            models.Index(fields=["departement_code", "commune"]),
            models.Index(fields=["commune"]),
        ]
        verbose_name = "Zone tendue touristique"
        verbose_name_plural = "Zones tendues touristiques"

    def __str__(self):
        return f"{self.commune} ({self.code_insee}) - Dép. {self.departement_code}"


class PermisDeLouer(models.Model):
    """Permis de louer par ville"""

    raw_data = models.TextField(verbose_name="Raw data")
    villes = models.CharField(max_length=255, null=False, verbose_name="Villes")
    specificite_par_quartier = models.BooleanField(
        default=False, verbose_name="Spécificités par Quartier"
    )
    date_inconnues = models.BooleanField(default=False, verbose_name="Date inconnue")

    class Meta:
        indexes = [models.Index(fields=["villes"])]
        verbose_name = "Permis de louer"
        verbose_name_plural = "Permis de louer"

    def __str__(self):
        return f"{self.villes}"
