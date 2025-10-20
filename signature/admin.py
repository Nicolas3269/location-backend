from django.contrib import admin
from django.utils.html import format_html
from signature.models import SignatureMetadata


@admin.register(SignatureMetadata)
class SignatureMetadataAdmin(admin.ModelAdmin):
    """Admin pour visualiser les métadonnées forensiques des signatures"""

    list_display = [
        'id',
        'signature_timestamp',
        'signer_display',
        'document_display',
        'otp_validated',
        'ip_address',
        'certificate_fingerprint_short',
    ]

    list_filter = [
        'otp_validated',
        'signature_timestamp',
        'document_content_type',
    ]

    search_fields = [
        'certificate_subject_dn',
        'ip_address',
        'certificate_fingerprint',
    ]

    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'document_display',
        'signature_request_display',
        'signer_display',
        'signature_field_name',
        'otp_code',
        'otp_generated_at',
        'otp_validated_at',
        'otp_validated',
        'ip_address',
        'user_agent',
        'referer',
        'signature_timestamp',
        'pdf_hash_before',
        'pdf_hash_after',
        'certificate_pem_display',
        'certificate_fingerprint',
        'certificate_subject_dn',
        'certificate_issuer_dn',
        'certificate_valid_from',
        'certificate_valid_until',
        'tsa_timestamp',
        'proof_json_display',
    ]

    fieldsets = (
        ('Identification', {
            'fields': (
                'id',
                'created_at',
                'updated_at',
                'document_display',
                'signature_request_display',
                'signer_display',
                'signature_field_name',
            )
        }),
        ('OTP & Authentification', {
            'fields': (
                'otp_code',
                'otp_generated_at',
                'otp_validated_at',
                'otp_validated',
            )
        }),
        ('Métadonnées HTTP', {
            'fields': (
                'ip_address',
                'user_agent',
                'referer',
            )
        }),
        ('Horodatage', {
            'fields': (
                'signature_timestamp',
                'tsa_timestamp',
            )
        }),
        ('Hash PDF', {
            'fields': (
                'pdf_hash_before',
                'pdf_hash_after',
            )
        }),
        ('Certificat X.509', {
            'fields': (
                'certificate_subject_dn',
                'certificate_issuer_dn',
                'certificate_fingerprint',
                'certificate_valid_from',
                'certificate_valid_until',
                'certificate_pem_display',
            )
        }),
        ('Journal de preuves', {
            'fields': ('proof_json_display',)
        }),
    )

    def signer_display(self, obj):
        """Affiche le signataire"""
        if obj.signer:
            return f"{obj.signer.full_name} ({obj.signer.email})"
        return "N/A"
    signer_display.short_description = "Signataire"

    def document_display(self, obj):
        """Affiche le document signé"""
        if obj.document:
            return format_html(
                '<a href="/admin/{}/{}/{}/change/">{}</a>',
                obj.document._meta.app_label,
                obj.document._meta.model_name,
                obj.document.pk,
                str(obj.document)
            )
        return "N/A"
    document_display.short_description = "Document"

    def signature_request_display(self, obj):
        """Affiche le SignatureRequest avec le signataire"""
        if obj.signature_request:
            signer = getattr(obj.signature_request, 'signer', None)
            signer_info = (
                f"{signer.full_name} ({signer.email})" if signer else "N/A"
            )
            return format_html(
                '<strong>ID:</strong> {}<br>'
                '<strong>Order:</strong> {}<br>'
                '<strong>Signataire:</strong> {}',
                obj.signature_request.id,
                getattr(obj.signature_request, 'order', 'N/A'),
                signer_info
            )
        return "N/A"
    signature_request_display.short_description = "Signature Request"

    def certificate_fingerprint_short(self, obj):
        """Affiche les 16 premiers caractères du fingerprint"""
        return obj.certificate_fingerprint[:16] + "..."
    certificate_fingerprint_short.short_description = "Fingerprint"

    def certificate_pem_display(self, obj):
        """Affiche le certificat PEM avec formatage"""
        return format_html(
            '<pre style="background:#f5f5f5;padding:10px;'
            'border-radius:5px;max-height:400px;overflow:auto">{}</pre>',
            obj.certificate_pem
        )
    certificate_pem_display.short_description = "Certificat PEM"

    def proof_json_display(self, obj):
        """Affiche le JSON du journal de preuves avec formatage"""
        import json
        proof_dict = obj.to_proof_dict()
        json_str = json.dumps(proof_dict, indent=2, ensure_ascii=False)
        return format_html(
            '<pre style="background:#f5f5f5;padding:10px;'
            'border-radius:5px;max-height:600px;overflow:auto">{}</pre>',
            json_str
        )
    proof_json_display.short_description = "Journal de preuves (JSON)"
