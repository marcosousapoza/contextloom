from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from contextloom.accounts.models import ApplicationSettings, User

admin.site.site_header = "ContextLoom administration"
admin.site.site_title = "ContextLoom admin"
admin.site.index_title = "Accounts and application settings"
admin.site.unregister(Group)


@admin.register(User)
class ContextLoomUserAdmin(UserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (("Contact", {"fields": ("email",)}),)
    list_display = ("username", "email", "is_active", "is_staff", "is_superuser")
    list_filter = ("is_active", "is_staff", "is_superuser")


@admin.register(ApplicationSettings)
class ApplicationSettingsAdmin(admin.ModelAdmin):
    fields = ("registration_enabled",)

    def has_add_permission(self, request):
        return not ApplicationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
