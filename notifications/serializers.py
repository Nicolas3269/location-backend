from rest_framework import serializers

from .models import NotificationRequest


class NotificationRequestSerializer(serializers.ModelSerializer):
    """
    Serializer pour les demandes de notification
    """

    class Meta:
        model = NotificationRequest
        fields = ["email", "feature", "role"]

    def validate_email(self, value):
        """Validation personnalisée de l'email"""
        if not value:
            raise serializers.ValidationError("L'adresse email est requise")
        return value.lower()

    def validate_feature(self, value):
        """Validation de la fonctionnalité"""
        valid_features = [choice[0] for choice in NotificationRequest.FEATURE_CHOICES]
        if value not in valid_features:
            raise serializers.ValidationError(
                f"Fonctionnalité invalide. Options valides: {valid_features}"
            )
        return value


class NotificationRequestListSerializer(serializers.ModelSerializer):
    """
    Serializer pour la liste des demandes (avec infos supplémentaires)
    """

    feature_display = serializers.CharField(
        source="get_feature_display", read_only=True
    )
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = NotificationRequest
        fields = [
            "id",
            "email",
            "feature",
            "feature_display",
            "role",
            "role_display",
            "created_at",
            "notified",
            "notified_at",
        ]
