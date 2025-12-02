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


class BulkNotificationRequestSerializer(serializers.Serializer):
    """
    Serializer pour créer plusieurs demandes de notification en une fois.
    Accepte une liste de features.
    """

    email = serializers.EmailField()
    features = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        help_text="Liste des fonctionnalités demandées",
    )
    role = serializers.ChoiceField(choices=NotificationRequest.ROLE_CHOICES)

    def validate_email(self, value):
        """Normalise l'email en minuscules"""
        return value.lower()

    def validate_features(self, value):
        """Validation des fonctionnalités"""
        valid_features = [choice[0] for choice in NotificationRequest.FEATURE_CHOICES]
        invalid = [f for f in value if f not in valid_features]
        if invalid:
            raise serializers.ValidationError(
                f"Fonctionnalités invalides: {invalid}. Options valides: {valid_features}"
            )
        return list(set(value))  # Déduplique


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
