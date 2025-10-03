from django.contrib import admin
from .models import OTP

@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'purpose', 'created_at', 'expires_at', 'is_valid')
    list_filter = ('purpose', 'created_at')
    search_fields = ('user__email', 'user__username', 'code')
    readonly_fields = ('created_at', 'expires_at')