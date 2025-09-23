# yourapp/admin.py
from django.contrib import admin
from django import forms
from tinymce.widgets import TinyMCE
from .models import News
from . import ot_models
from django import forms
from django.contrib import admin
from django.forms.widgets import Media
from django.templatetags.static import static
from .models import News

class TinyMCEStaticDark(TinyMCE):
    def use_required_attribute(self, *args, **kwargs):
        # Avoid admin warning for custom widget; keep default behavior
        return super().use_required_attribute(*args, **kwargs)

    @property
    def media(self):
        base = super().media
        return (
            Media(css={"all": [
                static("assets/css/tinymce-dark-ui.css"),
                static("assets/css/admin-tinymce-align.css"),   # ← add this line
            ]})
            + base
        )

class NewsAdminForm(forms.ModelForm):
    summary = forms.CharField(
        widget=TinyMCEStaticDark(
            attrs={"cols": 80, "rows": 30},
            mce_attrs={
                # Point the iframe to your dark-aware content CSS
                "content_css": static("assets/css/tinymce-dark-content.css"),
                # Optional: set a class on the editor body for extra hooks
                "body_class": "prose",
                # Nice defaults (keep whatever you already have)
                "menubar": True,
                "plugins": (
                    "advlist autolink lists link image charmap preview anchor "
                    "searchreplace visualblocks code fullscreen "
                    "insertdatetime media table code help wordcount"
                ),
                "toolbar": (
                    "undo redo | styleselect | bold italic underline | "
                    "alignleft aligncenter alignright alignjustify | "
                    "bullist numlist outdent indent | link image media | code | fullscreen"
                ),
                # (TinyMCE v4) keep lightgray skin; we theme via CSS
                # "skin": "lightgray",
            },
        )
    )

    body = forms.CharField(
        widget=TinyMCEStaticDark(
            attrs={"cols": 80, "rows": 30},
            mce_attrs={
                # Point the iframe to your dark-aware content CSS
                "content_css": static("assets/css/tinymce-dark-content.css"),
                # Optional: set a class on the editor body for extra hooks
                "body_class": "prose",
                # Nice defaults (keep whatever you already have)
                "menubar": True,
                "plugins": (
                    "advlist autolink lists link image charmap preview anchor "
                    "searchreplace visualblocks code fullscreen "
                    "insertdatetime media table code help wordcount"
                ),
                "toolbar": (
                    "undo redo | styleselect | bold italic underline | "
                    "alignleft aligncenter alignright alignjustify | "
                    "bullist numlist outdent indent | link image media | code | fullscreen"
                ),
                # (TinyMCE v4) keep lightgray skin; we theme via CSS
                # "skin": "lightgray",
            },
        )
    )

    class Meta:
        model = News
        fields = "__all__"

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    form = NewsAdminForm
    list_display = ("title", "is_published", "published_at")
    list_filter  = ("is_published",)
    search_fields = ("title", "summary", "body")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-published_at",)

@admin.register(ot_models.Players)    # class name based on inspectdb
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "vocation", "account_id")
    search_fields = ("name",)
    list_filter = ("vocation",)
