from django.contrib import admin
from authentication.models import EmailVerification


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ('email', 'created_at', 'verified', 'verified_at')
    list_filter = ('verified',)
    search_fields = ('email',)
    readonly_fields = ('token', 'created_at', 'verified_at')
