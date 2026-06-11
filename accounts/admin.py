from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name = 'Profil'


class CustomUserAdmin(UserAdmin):
    inlines = [UserProfileInline]
    list_display = ('email', 'get_full_name', 'get_country', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'profile__country')
    ordering = ('date_joined',)

    @admin.display(description='Nom')
    def get_full_name(self, obj):
        try:
            return obj.profile.full_name
        except UserProfile.DoesNotExist:
            return '—'

    @admin.display(description='Pays')
    def get_country(self, obj):
        try:
            return obj.profile.get_country_display()
        except UserProfile.DoesNotExist:
            return '—'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('profile')


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
