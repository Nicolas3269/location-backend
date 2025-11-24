"""
Serializers de base communs entre Read et Write.
Définit les champs partagés pour éviter la duplication.
"""

from rest_framework import serializers

from location.models import Location


class LocationBaseSerializer(serializers.ModelSerializer):
    """
    Champs de base d'une Location (communs entre Read et Write).
    """

    class Meta:
        model = Location
        fields = ["date_debut", "date_fin", "solidaires"]
