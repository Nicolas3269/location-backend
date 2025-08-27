"""
Serializers par pays pour les formulaires adaptatifs.
"""

from .france import (
    FranceBailSerializer,
    FranceQuittanceSerializer,
    FranceEtatLieuxSerializer,
)

from .belgium import (
    BelgiumBailSerializer,
    BelgiumQuittanceSerializer,
    BelgiumEtatLieuxSerializer,
)

__all__ = [
    "FranceBailSerializer",
    "FranceQuittanceSerializer",
    "FranceEtatLieuxSerializer",
    "BelgiumBailSerializer",
    "BelgiumQuittanceSerializer",
    "BelgiumEtatLieuxSerializer",
]