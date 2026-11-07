from django.contrib import admin

from .models import Title, TitleTranslation


class TitleTranslationInline(admin.TabularInline):
    model = TitleTranslation
    extra = 0
    fields = ("language", "name", "poster_path", "fetched_at")
    readonly_fields = fields
    can_delete = False


@admin.register(Title)
class TitleAdmin(admin.ModelAdmin):
    """Read-only view of the TMDB cache (data comes from TMDB, not from admins)."""

    list_display = ("original_title", "media_type", "release_date", "status", "updated_at")
    list_filter = ("media_type",)
    search_fields = ("original_title", "translations__name", "tmdb_id")
    inlines = [TitleTranslationInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
