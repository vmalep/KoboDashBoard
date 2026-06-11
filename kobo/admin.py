from django.contrib import admin
from .models import KoboConfig


@admin.register(KoboConfig)
class KoboConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Server', {'fields': ('server_url', 'api_token')}),
        ('Cache', {'fields': ('cache_ttl_seconds',)}),
    )

    def has_add_permission(self, request):
        return not KoboConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
