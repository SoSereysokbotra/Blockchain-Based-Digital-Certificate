from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    """Read-only delivery audit (FR-6.3)."""

    list_display = (
        'sent_at', 'kind', 'recipient_email', 'status',
        'attempt', 'has_attachment', 'certificate',
    )
    list_filter = ('status', 'kind', 'sent_at')
    search_fields = ('recipient_email', 'certificate__certificate_id', 'error_message')
    date_hierarchy = 'sent_at'
    readonly_fields = tuple(f.name for f in NotificationLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
