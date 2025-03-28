from django.contrib.gis.db import models
from django.db.models import UniqueConstraint

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

    area = models.ForeignKey(
        RentControlArea, on_delete=models.CASCADE, related_name="prices"
    )

    # Caractéristiques avec énums
    property_type = models.CharField(max_length=20, choices=PropertyType.choices)
    room_count = models.CharField(max_length=10, choices=RoomCount.choices)
    construction_period = models.CharField(
        max_length=20, choices=ConstructionPeriod.choices
    )
    furnished = models.BooleanField()

    # Prix
    reference_price = models.DecimalField(max_digits=6, decimal_places=2)
    min_price = models.DecimalField(max_digits=6, decimal_places=2)
    max_price = models.DecimalField(max_digits=6, decimal_places=2)

    # Meta reste identique

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=[
                    "area",
                    "property_type",
                    "room_count",
                    "construction_period",
                    "furnished",
                ],
                name="unique_property_characteristics",
            )
        ]
        indexes = [
            models.Index(
                fields=[
                    "property_type",
                    "room_count",
                    "furnished",
                    "construction_period",
                ]
            ),
        ]
