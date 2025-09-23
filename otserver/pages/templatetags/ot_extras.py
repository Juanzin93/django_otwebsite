# yourapp/templatetags/ot_extras.py
from django import template
from urllib.parse import urlencode
from pages.views import OT_DB_ALIAS, dictfetchall
from django.db import connections
from django.utils import timezone
from datetime import datetime

register = template.Library()

def _get(obj, key, default=0):
    # Works for model instances or dict rows
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default

@register.simple_tag
def outfit_url(player, path="latest", animated=False, direction=2, mount=0):
    """
    Build a URL for outfit-images.ots.me from player look fields.
    path: e.g. "latest" (static), "latest_walk" (animated walking)
    """
    params = {
        "id":       _get(player, "looktype", 0),
        "addons":   _get(player, "lookaddons", 0),
        "head":     _get(player, "lookhead", 0),
        "body":     _get(player, "lookbody", 0),
        "legs":     _get(player, "looklegs", 0),
        "feet":     _get(player, "lookfeet", 0),
        "mount":    int(mount),
        "direction":int(direction),  # 0..3; 2 faces “front”
    }
    endpoint = "animoutfit.php" if animated else "outfit.php"
    return f"https://outfit-images.ots.me/{path}/{endpoint}?{urlencode(params)}"

@register.filter
def country_of(player):
    """
    Return a 2-letter country code from either:
      - ORM object: player.account.country
      - dict row:   player['country']
    """
    try:
        # ORM (Players has FK 'account')
        return (player.account.country or "").strip()
    except Exception:
        # Dict row from raw SQL
        if isinstance(player, dict):
            return (player.get("country") or "").strip()
        return ""

VOCATIONS =  {
    0: "None",
    1: "Sorcerer",
    2: "Druid",
    3: "Paladin",
    4: "Knight",
    5: "Master Sorcerer",
    6: "Elder Druid",
    7: "Royal Paladin",
    8: "Elite Knight",
}


TOWNS =  {
    1: "Thais",
    2: "Carlin",
    3: "Kazordoon",
    4: "Ab'Dendriel",
    5: "Edron",
    6: "Darashia",
    7: "Venore",
    8: "Ankrahmun",
    9: "Port Hope",
    10: "GM Island",
    11: "Rookgaard",
    12: "Liberty Bay",
    13: "Svargrond",
    14: "Yalahar",
}


@register.filter
def vocation_name(value):
    return VOCATIONS.get(value, "Unknown")

@register.filter
def town_name(value):
    return TOWNS.get(value, "Unknown")

@register.filter
def skill_value(player, skill):
    skills_column = {
        "level": "level",
        "experience": "experience",
        "magic": "maglevel",
        "shielding": "skill_shielding",
        "distance": "skill_dist",
        "club": "skill_club",
        "sword": "skill_sword",
        "axe": "skill_axe",
        "fist": "skill_fist",
        "fishing": "skill_fishing",
        "online time": "onlinetime",
        "best exp day": "dailyExp",
        "best exp week": "weeklyExp",
        "best exp month": "monthlyExp",
    }
    skill = skills_column.get(skill, skill)
    with connections[OT_DB_ALIAS].cursor() as cur:
        cur.execute(f"SELECT {skill} FROM players WHERE id = %s", [player['id']])
        value = cur.fetchone()
    return value[0]

@register.filter
def format_unixtime(value):
    try:
        ts = int(value or 0)
        if ts <= 0:
            return "Never"
        return timezone.localtime(timezone.datetime.fromtimestamp(ts, tz=timezone.get_current_timezone())).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""
    
@register.filter
def unixdatetime(value):
    try:
        v = int(value)
        if v <= 0: return "—"
        return datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"

@register.filter
def unixdate(value):
    try:
        v = int(value)
        if v <= 0: return "—"
        return datetime.fromtimestamp(v).strftime("%Y-%m-%d")
    except Exception:
        return "—"