"""
Admin registration for development inspection.

NFR-1.12: /admin/ is only routed when ENABLE_ADMIN is set (see bcip_backend.urls),
so registering models here does not by itself expose them on a deployment.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    EmailVerificationCode,
    LoginAttempt,
    Organization,
    PasswordResetCode,
    RefreshToken,
)


@admin.register(Organization)
class OrganizationAdmin(UserAdmin):
    list_display = ('email', 'name', 'is_verified', 'is_active', 'wallet_address', 'created_at')
    list_filter = ('is_verified', 'is_active', 'is_staff')
    search_fields = ('email', 'name', 'wallet_address')
    ordering = ('email',)
    readonly_fields = ('id', 'created_at', 'updated_at', 'last_login')

    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        ('Organisation', {'fields': ('name', 'wallet_address')}),
        ('Status', {'fields': ('is_verified', 'is_active', 'is_staff', 'is_superuser')}),
        ('Permissions', {'fields': ('groups', 'user_permissions')}),
        ('Timestamps', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'password1', 'password2', 'is_verified'),
        }),
    )


class OneTimeCodeAdmin(admin.ModelAdmin):
    list_display = ('organization', 'code', 'created_at', 'expires_at', 'used_at')
    search_fields = ('organization__email',)
    readonly_fields = ('created_at',)


admin.site.register(EmailVerificationCode, OneTimeCodeAdmin)
admin.site.register(PasswordResetCode, OneTimeCodeAdmin)


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = ('organization', 'jti', 'created_at', 'expires_at', 'revoked_at', 'ip_address')
    list_filter = ('revoked_at',)
    search_fields = ('organization__email', 'jti')
    # token_hash is shown but the raw token is never stored anywhere.
    readonly_fields = ('token_hash', 'jti', 'created_at')


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('email', 'ip_address', 'successful', 'attempted_at')
    list_filter = ('successful', 'attempted_at')
    search_fields = ('email', 'ip_address')
    readonly_fields = ('email', 'ip_address', 'successful', 'attempted_at', 'user_agent')
