from django.contrib import admin

from .models import NotificationRequest


@admin.register(NotificationRequest)
class NotificationRequestAdmin(admin.ModelAdmin):
    list_display = [
        "email",
        "feature_display",
        "role_display",
        "notified",
        "created_at",
    ]

    list_filter = ["feature", "role", "notified", "created_at"]

    search_fields = ["email", "role"]

    readonly_fields = ["created_at", "notified_at"]

    list_per_page = 50

    actions = ["mark_as_notified"]

    def feature_display(self, obj):
        return obj.get_feature_display()

    feature_display.short_description = "Fonctionnalité"

    def role_display(self, obj):
        return obj.get_role_display()

    role_display.short_description = "Rôle"

    def mark_as_notified(self, request, queryset):
        from django.utils import timezone

        updated = queryset.update(notified=True, notified_at=timezone.now())
        self.message_user(
            request, f"{updated} demande(s) marquée(s) comme notifiée(s)."
        )

    mark_as_notified.short_description = "Marquer comme notifié"

    fieldsets = (
        ("Informations de contact", {"fields": ("email",)}),
        (
            "Demande",
            {"fields": ("feature", "role")},
        ),
        (
            "Statut",
            {
                "fields": ("notified", "created_at", "notified_at"),
                "classes": ("collapse",),
            },
        ),
    )
