from django.contrib import admin

from .models import Certificate, RevocationLog


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = (
        'certificate_id', 'recipient_name', 'course_title',
        'organization', 'status', 'issue_date', 'expiry_date', 'created_at',
    )
    list_filter = ('status', 'issue_date', 'organization')
    search_fields = ('certificate_id', 'recipient_name', 'recipient_email', 'course_title')
    date_hierarchy = 'created_at'
    readonly_fields = (
        'certificate_id', 'certificate_hash', 'pdf_sha256', 'blockchain_tx_hash',
        'blockchain_block_number', 'anchored_at', 'created_at', 'updated_at',
        'issuance_attempts',
    )

    fieldsets = (
        ('Identity', {'fields': ('certificate_id', 'organization', 'idempotency_key')}),
        ('Recipient', {'fields': ('recipient_name', 'recipient_email')}),
        ('Certificate', {'fields': ('course_title', 'issue_date', 'expiry_date', 'status')}),
        ('Integrity (off-chain)', {'fields': ('certificate_hash', 'pdf_sha256', 'pdf_url')}),
        ('Anchor (on-chain)', {
            'fields': ('blockchain_tx_hash', 'blockchain_block_number', 'anchored_at'),
        }),
        ('Failure', {'fields': ('failure_reason', 'issuance_attempts')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(RevocationLog)
class RevocationLogAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'revoked_by', 'revoked_at', 'confirmed_on_chain')
    list_filter = ('confirmed_on_chain', 'revoked_at')
    search_fields = ('certificate__certificate_id', 'reason')
    readonly_fields = ('revoked_at', 'blockchain_tx_hash')
