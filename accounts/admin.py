from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        (_("Preferences"), {"fields": ("ui_language", "tmdb_language", "region", "theme")}),
    )
