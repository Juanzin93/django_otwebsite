from django.conf import settings
from pathlib import Path

def feature_flags(request):
    return {
        "SHOP_ENABLED": settings.SHOP_ENABLED,
        "QUICKLOGIN_SHOWBOX_ENABLED": settings.QUICKLOGIN_SHOWBOX_ENABLED,
        "GALLERY_SHOWBOX_ENABLED": settings.GALLERY_SHOWBOX_ENABLED,
        "SERVERINFO_SHOWBOX_ENABLED": settings.SERVERINFO_SHOWBOX_ENABLED,
        "CHARMARKET_SHOWBOX_ENABLED": settings.CHARMARKET_SHOWBOX_ENABLED,
        "POWERGAMERS_SHOWBOX_ENABLED": settings.POWERGAMERS_SHOWBOX_ENABLED,
        "ONLINERANKING_SHOWBOX_ENABLED": settings.ONLINERANKING_SHOWBOX_ENABLED,
        "DISCORDWIDGET_ENABLED": settings.DISCORDWIDGET_ENABLED,
        
    }

def public_gallery(request):
    folder = Path(settings.BASE_DIR) / "static" / "assets" / "img" / "gallery"
    exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    try:
        gallery = sorted(
            f"assets/img/gallery/{p.name}"
            for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in exts
        )
    except FileNotFoundError:
        gallery = []
    return {"gallery": gallery}

