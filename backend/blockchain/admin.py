from django.contrib import admin

from .models import BlockchainInteractionLog


@admin.register(BlockchainInteractionLog)
class BlockchainInteractionLogAdmin(admin.ModelAdmin):
    """Read-only audit view (FR-2.10)."""

    list_display = (
        'created_at', 'interaction_type', 'certificate_public_id',
        'succeeded', 'tx_hash', 'block_number', 'duration_ms',
    )
    list_filter = ('interaction_type', 'succeeded', 'created_at')
    search_fields = ('certificate_public_id', 'tx_hash', 'error_message')
    date_hierarchy = 'created_at'
    readonly_fields = tuple(
        f.name for f in BlockchainInteractionLog._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
