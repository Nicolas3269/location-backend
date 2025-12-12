"""
Serializers par pays pour les formulaires adaptatifs.
"""

from .france import (
    FranceAvenantSerializer,
    FranceBailSerializer,
    FranceEtatLieuxSerializer,
    FranceMRHSerializer,
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
    "FranceMRHSerializer",
    "FranceQuittanceSerializer",
    "BelgiumBailSerializer",
    "BelgiumEtatLieuxSerializer",
    "BelgiumQuittanceSerializer",
]