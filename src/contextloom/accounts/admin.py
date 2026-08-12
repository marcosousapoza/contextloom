from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from contextloom.accounts.models import User

admin.site.site_header = "ContextLoom administration"
admin.site.site_title = "ContextLoom admin"
admin.site.index_title = "Account management"
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

    def save_model(self, request, obj, form, change):
        if not change:
            obj.password_change_required = True
        super().save_model(request, obj, form, change)
