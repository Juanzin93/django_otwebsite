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
from .ot_models import (
    Accounts,
    CharMarket,
    GuildWars,
    GuildwarKills,
    Houses,
    PlayerDepotitems,
    PlayerItems,
    PlayerStorage,
    Players,
    ServerConfig,
    AccountBans,
    AccountBanHistory,
    PlayersOnline,
)
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

# Helpful __str__ fallbacks (admin uses this to label rows)
def _str(obj, field):
    val = getattr(obj, field, None)
    return str(val) if val is not None else f"{obj.__class__.__name__} #{getattr(obj, 'pk', '')}"

@admin.register(AccountBans)
class AccountBansAdmin(admin.ModelAdmin):
    list_display = ("account", "reason", "banned_at", "expires_at", "banned_by")
    search_fields = ("account__id", "reason")

@admin.register(AccountBanHistory)
class AccountBanHistoryAdmin(admin.ModelAdmin):
    list_display = ("account", "reason", "banned_at", "expired_at", "banned_by")
    search_fields = ("account__id", "reason")

@admin.register(PlayersOnline)
class PlayersOnlineAdmin(admin.ModelAdmin):
    list_display = ("player_id",)
    search_fields = ("player_id",)


@admin.register(Accounts)
class AccountsAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "type", "premdays", "coins", "created", "web_lastlogin")
    search_fields = ("id", "email")
    list_filter = ("type", "email_verified")
    ordering = ("-created",)
    readonly_fields = ()  # add fields here if you want to make them read-only

@admin.register(Players)
class PlayersAdmin(admin.ModelAdmin):
    list_display = ("name", "account_id", "level", "vocation", "sex", "town_id", "lastlogin", "deleted")
    search_fields = ("name", "account_id")
    list_filter = ("vocation", "sex", "town_id", "deleted")
    ordering = ("-level", "name")

@admin.register(CharMarket)
class CharMarketAdmin(admin.ModelAdmin):
    list_display = ("name", "char_id", "seller_account", "current_bid", "auction_start", "auction_end", "highest_bid_acc")
    search_fields = ("name", "char_id", "seller_account")
    list_filter = ()
    ordering = ("-auction_end",)

@admin.register(GuildWars)
class GuildWarsAdmin(admin.ModelAdmin):
    list_display = ("name1", "name2", "guild1", "guild2", "status", "started", "ended")
    search_fields = ("name1", "name2", "guild1", "guild2")
    list_filter = ("status",)
    ordering = ("-started",)

@admin.register(GuildwarKills)
class GuildwarKillsAdmin(admin.ModelAdmin):
    list_display = ("killer", "target", "killerguild", "targetguild", "warid", "time")
    search_fields = ("killer", "target", "killerguild", "targetguild", "warid")
    list_filter = ("warid",)
    ordering = ("-time",)

@admin.register(Houses)
class HousesAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "town_id", "rent", "size", "beds", "paid", "warnings", "highest_bidder", "bid", "bid_end")
    search_fields = ("name", "owner", "town_id", "highest_bidder")
    list_filter = ("town_id", "beds")
    ordering = ("town_id", "name")
    
@admin.register(PlayerStorage)
class PlayerStorageAdmin(admin.ModelAdmin):
    list_display = ("player_id", "key", "value")
    search_fields = ("player_id", "key")
    ordering = ("player_id", "key")

@admin.register(ServerConfig)
class ServerConfigAdmin(admin.ModelAdmin):
    list_display = ("config", "value")
    search_fields = ("config",)
    ordering = ("config",)