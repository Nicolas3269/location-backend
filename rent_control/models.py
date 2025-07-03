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
