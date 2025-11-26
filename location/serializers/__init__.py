"""
Serializers par pays pour les formulaires adaptatifs.
"""

from .france import (
    FranceAvenantSerializer,
    FranceBailSerializer,
    FranceEtatLieuxSerializer,
    FranceQuittanceSerializer,
)

from .belgium import (
    BelgiumBailSerializer,
    BelgiumEtatLieuxSerializer,
    BelgiumQuittanceSerializer,
)

__all__ = [
    "FranceAvenantSerializer",
    "FranceBailSerializer",
    "FranceEtatLieuxSerializer",
    "FranceQuittanceSerializer",
    "BelgiumBailSerializer",
    "BelgiumEtatLieuxSerializer",
    "BelgiumQuittanceSerializer",
]