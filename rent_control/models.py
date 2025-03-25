from django.contrib.gis.db import models

class RentControlZone(models.Model):
    REGION_CHOICES = [
        ('IDF', 'Île-de-France'),
        ('PAYS_BASQUE', 'Pays Basque'),
        ('LYON', 'Lyon'),
        ('MONTPELLIER', 'Montpellier'),
        ('BORDEAUX', 'Bordeaux'),
    ]
    
    region = models.CharField(max_length=20, choices=REGION_CHOICES)
    zone = models.CharField(max_length=50)
    reference_price = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    min_price = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    max_price = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    apartment_type = models.CharField(max_length=50, null=True, blank=True)
    room_count = models.CharField(max_length=20, null=True, blank=True)
    construction_period = models.CharField(max_length=50, null=True, blank=True)
    furnished = models.BooleanField(default=False)
    reference_year = models.IntegerField(null=True, blank=True)  # Ajout de l'année de référence
    
    
    # Geometry field for the polygon
    geometry = models.MultiPolygonField(srid=4326)
    
    class Meta:
        indexes = [
            models.Index(fields=['region']),
        ]
        
    def __str__(self):
        return f"{self.region} - {self.zone}"