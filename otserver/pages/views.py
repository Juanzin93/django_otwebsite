from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.contrib import messages
from django.shortcuts import render, redirect
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse, Http404, HttpResponseBadRequest
from django.utils.html import escape
from django.urls import reverse
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import EmailMultiAlternatives
from django.db.models import F
from django.utils.timezone import now
from django.db import connections, transaction
import time
import hashlib
import logging

from typing import Dict, List, Optional
from .forms import EmailUpdateForm, SignUpForm, CreateCharacterForm
from .server_status import query_ot_status, query_ot_players
from .db import DB
from .items_service import SLOT_NAMES
from urllib.parse import urlencode
from .auth_backends import OT_PASSWORD_TYPE, OT_ACCOUNT_TABLE, OT_PASSWORD_COL, OT_EMAIL_COL, OT_BLOCKED_COL

User = get_user_model()
log = logging.getLogger(__name__)

db = DB(retries=2)
OT_DB_ALIAS = getattr(settings, "OT_DB_ALIAS", "retrowar")  # or "otserv" if you use a 2nd DB
OT_BLOCKED_COL = None
PLAYERS_TBL  = getattr(settings, "OT_PLAYERS_TABLE", "players")
ACC_COL      = getattr(settings, "OT_PLAYERS_ACCOUNT_COL", "account_id")
SIGNUP_CONFIRM_EMAIL = getattr(settings, "SIGNUP_CONFIRM_EMAIL", True)


SKILL_COLUMNS = {
    "level": "p.level",
    "magic": "p.maglevel",
    "shielding": "p.skill_shielding",
    "distance": "p.skill_dist",
    "club": "p.skill_club",
    "sword": "p.skill_sword",
    "axe": "p.skill_axe",
    "fist": "p.skill_fist",
    "fishing": "p.skill_fishing",
    "online time": "p.onlinetime",
    "best exp day": "p.dailyExp",
    "best exp week": "p.weeklyExp",
    "best exp month": "p.monthlyExp",
}

SKILLS = list(SKILL_COLUMNS.keys())

# vocation groups (with promotions)
VOC_GROUPS = {
    "all": None,
    "sorcerer": [1, 5],
    "druid":    [2, 6],
    "paladin":  [3, 7],
    "knight":   [4, 8],
}
VOCATIONS = list(VOC_GROUPS.keys())

@login_required
def account_manage(request):
    # Email update
    email_form = EmailUpdateForm(request.POST or None, initial={"email": request.user.email})
    if request.method == "POST" and request.POST.get("update_email") and email_form.is_valid():
        request.user.email = email_form.cleaned_data["email"]
        request.user.save(update_fields=["email"])
        messages.success(request, "Email updated.")
        return redirect("account_manage")

    # Pull characters by linked OT account id on the user profile
    acc_id = request.user.username
    characters = []
    if acc_id:
        characters = db.run("select", """
            SELECT id, name, level, vocation
                FROM players
                WHERE account_id = %s
            ORDER BY name ASC
        """, [acc_id])
        for c in characters:
            c["online"] = 0

    coins = db.run("select", """
            SELECT coins
                FROM accounts
                WHERE id = %s
        """, [acc_id])
    return render(request, "pages/account_manage.html", {
        "email_form": email_form,
        "characters": characters,
        "acc_coins": coins[0]["coins"] if coins else 0,
    })

def home(request):
    return render(request, "pages/index.html")

def news(request):
    return render(request, "pages/news.html", {})

def gallery(request):
    yt_ids = ["78n9H3Pxt8s", "-4n3egV13GE"]
    return render(request, "pages/gallery.html", {"yt_ids": yt_ids})

def signup(request):
    # Placeholder for signup view logic
    return render(request, "accounts/signup.html", {})

def dictfetchall(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def highscores(request):
    # pagination
    try:
        page = int(request.GET.get("page", 1) or 1)
    except ValueError:
        page = 1
    page = max(1, page)

    # filters
    selected_skill = (request.GET.get("skill") or "level").lower()
    if selected_skill not in SKILLS:
        selected_skill = "experience"

    selected_vocation = (request.GET.get("vocation") or "all").lower()
    if selected_vocation not in VOCATIONS:
        selected_vocation = "all"

    # base query
    base_sql = """
        SELECT p.*, a.country
          FROM players p
     LEFT JOIN accounts a ON a.id = p.account_id
    """

    params = []
    if VOC_GROUPS[selected_vocation]:
        ids = VOC_GROUPS[selected_vocation]
        # turn IN list into placeholders
        ph = ", ".join(["%s"] * len(ids))
        base_sql += f" WHERE p.vocation IN ({ph})"
        params.extend(ids)

    # order
    order_by = f"{SKILL_COLUMNS[selected_skill]} DESC, p.name ASC"

    rows, meta = db.run(
        "paginate",
        base_sql,
        params,
        order_by=order_by,
        page=page,
        per_page=25,
    )

    # pager window
    window = 2
    start = max(1, meta["page"] - window)
    end = min(meta["total_pages"], meta["page"] + window)
    page_range = range(start, end + 1)

    # build querystring minus page (so your pager links can append &page=)
    q = request.GET.copy()
    q.pop("page", None)
    querystring = q.urlencode()

    return render(request, "pages/highscores.html", {
        "players": rows,

        # pager
        "page": meta["page"],
        "total_pages": meta["total_pages"],
        "page_range": page_range,
        "has_prev": meta["has_prev"],
        "has_next": meta["has_next"],
        "start_index": meta["start_index"],
        "querystring": querystring,

        # filters panel
        "skills": SKILLS,
        "vocations": VOCATIONS,
        "selected_skill": selected_skill,
        "selected_vocation": selected_vocation,
    })


@require_GET
def server_status(request):
    host = settings.OT_STATUS_HOST
    port = int(settings.OT_STATUS_PORT)
    timeout = float(getattr(settings, "OT_STATUS_TIMEOUT", 3.0))
    min_interval = int(getattr(settings, "OT_STATUS_MIN_INTERVAL", 15))  # seconds
    retries = int(getattr(settings, "OT_STATUS_RETRIES", 1))
    backoff = float(getattr(settings, "OT_STATUS_RETRY_DELAY", 1.0))

    now = time.time()
    last_ts = cache.get("ot_status_last_ts", 0.0)
    cached = cache.get("ot_status_json")

    if cached and (now - last_ts) < min_interval:
        return JsonResponse(cached)

    # single-flight guard (5s)
    if not cache.add("ot_status_lock", "1", timeout=5):
        # someone else is querying, serve whatever we have
        if cached:
            return JsonResponse(cached)

    try:
        try:
            data = query_ot_status(host, port, timeout=timeout, retries=retries, backoff=backoff)
        except Exception as e:
            data = {"online": False, "error": str(e)}
        cache.set("ot_status_json", data, 120)
        cache.set("ot_status_last_ts", time.time(), 120)
        return JsonResponse(data)
    finally:
        cache.delete("ot_status_lock")



def _fmt_uptime(secs: int) -> str:
    secs = int(secs or 0)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d: return f"{d}d {h}h {m}m"
    if h: return f"{h}h {m}m"
    return f"{m}m"

def server_info(request):
    try:
        data = query_ot_status(
            settings.OT_STATUS_HOST,
            settings.OT_STATUS_PORT,
            getattr(settings, "OT_STATUS_TIMEOUT", 5.0),
            retries=1, backoff=1.2,
        )
        uptime_human = _fmt_uptime(data["server"].get("uptime_sec", 0))
    except Exception as e:
        data = {"online": False, "error": str(e), "players": {"online": 0, "max": 0, "peak": 0},
                "server": {"uptime_sec": 0}, "rates": {}, "map": {}, "motd": ""}
        uptime_human = "—"

    return render(request, "pages/server_info.html", {
        "status": data,
        "uptime_human": uptime_human,
    })


def server_players(request):
    data = query_ot_players(
        settings.OT_STATUS_HOST,
        settings.OT_STATUS_PORT,
        getattr(settings, "OT_STATUS_TIMEOUT", 5.0),
        retries=1, backoff=1.0,
    )
    
    names = [p.get("name") for p in data.get("list", []) if p.get("name")]
    if names:
        # Dedup
        uniq = list({n: None for n in names}.keys())

        # Detect FK to accounts (account_id vs accountid)
        acc_fk = "account_id" if db._has_column("players", "account_id") else ("accountid" if db._has_column("players", "accountid") else None)
        if not acc_fk:
            raise RuntimeError("players table has no account FK column (account_id/accountid)")

        # Helper: if column exists use it, else constant alias
        def col_or_zero(tbl, col, alias=None):
            alias = alias or col
            return (f"{tbl}.{col} AS {alias}") if db._has_column("players", col) else (f"0 AS {alias}")

        # Build SELECT pieces (fallback to 0 if column missing)
        sel_looktype   = col_or_zero("p", "looktype")
        sel_lookaddons = col_or_zero("p", "lookaddons")
        sel_lookhead   = col_or_zero("p", "lookhead")
        sel_lookbody   = col_or_zero("p", "lookbody")
        sel_looklegs   = col_or_zero("p", "looklegs")
        sel_lookfeet   = col_or_zero("p", "lookfeet")

        # Mount column varies or is absent; try common aliases
        if db._has_column("players", "lookmount"):
            sel_lookmount = "p.lookmount AS lookmount"
        elif db._has_column("players", "mount"):
            sel_lookmount = "p.mount AS lookmount"
        elif db._has_column("players", "lookmountid"):
            sel_lookmount = "p.lookmountid AS lookmount"
        else:
            sel_lookmount = "0 AS lookmount"

        def chunks(seq, n=500):
            for i in range(0, len(seq), n):
                yield seq[i:i+n]

        rows = []
        for batch in chunks(uniq, 500):
            placeholders = ",".join(["%s"] * len(batch))
            sql = f"""
                SELECT
                    p.name,
                    p.level,
                    {sel_looktype},
                    {sel_lookaddons},
                    {sel_lookhead},
                    {sel_lookbody},
                    {sel_looklegs},
                    {sel_lookfeet},
                    {sel_lookmount},
                    TRIM(COALESCE(a.country, '')) AS country
                FROM players p
                LEFT JOIN accounts a ON a.id = p.{acc_fk}
                WHERE p.name IN ({placeholders})
            """
            rows.extend(db.run("select", sql, batch) or [])

        by_name = {r["name"]: r for r in rows}

        enriched = []
        for p in data.get("list", []):
            row = by_name.get(p.get("name"))
            if row:
                p.update({
                    "looktype":   int(row.get("looktype", 0)),
                    "lookaddons": int(row.get("lookaddons", 0)),
                    "lookhead":   int(row.get("lookhead", 0)),
                    "lookbody":   int(row.get("lookbody", 0)),
                    "looklegs":   int(row.get("looklegs", 0)),
                    "lookfeet":   int(row.get("lookfeet", 0)),
                    "lookmount":  int(row.get("lookmount", 0)),
                    "country":    (row.get("country") or "").strip(),
                    "level":      row.get("level", p.get("level", 0)),
                })
            enriched.append(p)
        data["list"] = enriched
    return JsonResponse(data)

def online_list(request):
    data = query_ot_players(
        settings.OT_STATUS_HOST,
        settings.OT_STATUS_PORT,
        getattr(settings, "OT_STATUS_TIMEOUT", 5.0),
        retries=1, backoff=1.0,
    )
    return render(request, "pages/online.html", {"status": data})

def search_character(request):
    q = (request.GET.get("q") or "").strip()
    matches = []

    if q:
        # Exact match → redirect to detail if found
        exact = db.run(
            "select_one",
            """
            SELECT p.*
              FROM players p
             WHERE LOWER(p.name) = LOWER(:q)
             LIMIT 1
            """,
            {"q": q},
        )
        if exact:
            return redirect("character_detail", name=exact["name"])

        # Fuzzy list
        matches = db.run(
            "select",
            """
            SELECT p.name, p.level, p.vocation
              FROM players p
             WHERE p.name LIKE :like
          ORDER BY p.name ASC
             LIMIT 25
            """,
            {"like": f"%{q}%"},
        )

    return render(request, "pages/search_character.html", {"q": q, "matches": matches})


def character_detail(request, name: str):
    # Basic character + account fields (tweak columns to match your schema)
    p = db.run(
        "select_one",
        """
        SELECT p.*,
               a.premdays, a.created AS account_created, a.country
          FROM players p
     LEFT JOIN accounts a ON a.id = p.account_id
         WHERE p.name = :name
         LIMIT 1
        """,
        {"name": name},
    )
    if not p:
        raise Http404("Character not found")

    # (Optional) Guild info — adapt table/columns if you have them
    try:
        guild = db.run(
            "select_one",
            """
            SELECT g.name AS guild_name, r.name AS rank_name
              FROM guild_membership gm
              JOIN guilds g ON g.id = gm.guild_id
              LEFT JOIN guild_ranks r ON r.id = gm.rank_id
             WHERE gm.player_id = (
                   SELECT id FROM players WHERE name = :name LIMIT 1
             )
             LIMIT 1
            """,
            {"name": name},
        )
    except Exception:
        guild = None

    # Recent deaths (ignore if table absent)
    try:
        deaths = db.run(
            "select",
            """
            SELECT d.time, d.level, d.killed_by
              FROM player_deaths d
              JOIN players pp ON pp.id = d.player_id
             WHERE pp.name = :name
          ORDER BY d.time DESC
             LIMIT 10
            """,
            {"name": name},
        )
    except Exception:
        deaths = []

    account_chars = db.run(
        "select",
        "SELECT name, level, vocation FROM players "
        "WHERE account_id=:aid AND deleted=0 ORDER BY name",
        {"aid": p["account_id"]}
    )

    online_names = set()
    try:
        live = query_ot_players(settings.OT_STATUS_HOST,
                                settings.OT_STATUS_PORT,
                                getattr(settings, "OT_STATUS_TIMEOUT", 3.0))
        if live.get("online"):
            # normalize for safe comparison
            online_names = {row["name"].casefold() for row in live.get("list", [])}
    except Exception:
        # optional: keep a tiny DB fallback (or remove to rely ONLY on live)
        rows = db.run(
            "select",
            "SELECT name FROM players WHERE account_id=:aid AND lastlogin > lastlogout",
            {"aid": p["account_id"]}
        )
        online_names = {r["name"].casefold() for r in rows}

    # annotate account list
    for c in account_chars:
        c["online"] = (c["name"].casefold() in online_names)

    # header badge for this character
    online = (p["name"].casefold() in online_names)

    # Skills (map your column names)
    skills = [
        {"label": "Magic",     "value": p.get("maglevel", 0)},
        {"label": "Shielding", "value": p.get("skill_shielding", 0)},
        {"label": "Distance",  "value": p.get("skill_dist", 0)},
        {"label": "Club",      "value": p.get("skill_club", 0)},
        {"label": "Sword",     "value": p.get("skill_sword", 0)},
        {"label": "Axe",       "value": p.get("skill_axe", 0)},
        {"label": "Fist",      "value": p.get("skill_fist", 0)},
        {"label": "Fishing",   "value": p.get("skill_fishing", 0)},
    ]

    return render(request, "pages/character_detail.html", {
        "p": p,
        "guild": guild,
        "deaths": deaths,
        "skills": skills,
        "online": online,
        "account_chars": account_chars,
    })

def character_inventory(request, name):
    """
    Returns the container tree hanging from an equipped slot (default: 3 = backpack).
    You can pass ?slot=1..10 to pick other slots.
    """
    pid = db._get_player_id(name)
    info = db._detect_items_table()
    if not info:
        raise Http404("Items table not found")

    table     = info["table"]
    pcol      = info["player_col"]
    count_col = info["count_col"]
    attr_col  = info["attr_col"]

    # pull all items for this player
    rows = db.run("select", f"""
        SELECT pid, sid, itemtype
               {", " + count_col if count_col else ""}
               {", " + attr_col  if attr_col  else ""}
          FROM {table}
         WHERE {pcol} = :pid
    """, {"pid": pid})

    # normalize + index
    items: List[Dict] = [db._encode_item(r, count_col, attr_col) for r in rows]
    by_sid: Dict[int, Dict] = {it["sid"]: it for it in items}

    # children map
    children: Dict[int, List[Dict]] = {}
    for it in items:
        parent = it["pid"]
        children.setdefault(parent, []).append(it)

    # Which slot to traverse from? default backpack (3)
    try:
        root_slot = int(request.GET.get("slot", "3"))
    except ValueError:
        root_slot = 3
    root_slot = max(1, min(10, root_slot))

    # Find containers equipped in that slot (items whose pid == root_slot)
    roots = [it for it in items if it["pid"] == root_slot]

    # recursively attach children by pid == parent sid
    def build(node):
        sid = node["sid"]
        node_children = [build(c) for c in children.get(sid, [])]
        return {
            **node,
            "children": node_children
        }

    tree = [build(r) for r in roots]

    return JsonResponse({
        "name": name,
        "slot": root_slot,
        "slot_name": SLOT_NAMES.get(root_slot, str(root_slot)),
        "containers": tree,
    })

def character_equipment(request, name):
    pid = db._get_player_id(name)
    info = db._detect_items_schema()
    if not info:
        raise Http404("Items table not found")

    table   = info["table"]
    slotcol = info["slot_col"]
    mode    = info["mode"]

    rows = db.run("select", f"""
        SELECT itemtype, count, attributes, {slotcol} AS slot, sid
          FROM {table}
         WHERE player_id = :pid AND {slotcol} BETWEEN 1 AND 10
         ORDER BY {slotcol} ASC, sid ASC
    """, {"pid": pid})

    equip_by_slot = {}
    for r in rows:
        s = int(r["slot"])
        if s not in equip_by_slot:
            equip_by_slot[s] = r

    slots = []
    for s in range(1, 11):
        item = equip_by_slot.get(s)
        if item:
            slots.append({
                "slot": s,
                "slot_name": SLOT_NAMES.get(s, str(s)),
                "itemtype": int(item["itemtype"]),
                "count": int(item.get("count") or 1),
                # encode BLOB as hex for JSON
                "attributes_hex": db._to_hex_or_none(item.get("attributes")),
            })
        else:
            slots.append({
                "slot": s,
                "slot_name": SLOT_NAMES.get(s, str(s)),
                "itemtype": None,
                "count": 0,
                "attributes_hex": None,
            })

    return JsonResponse({
        "name": name,
        "schema": mode,          # "slot" or "pid"
        "equipment": slots,
    })

def _detect_depot_table() -> Optional[Dict[str, str]]:
    """
    Returns info about the depot items table:
      { table, player_col, count_col, attr_col, sid_col, pid_col, depot_col or None }
    or None if not found.
    """
    for table in ("players_depotitems", "player_depotitems"):
        if not db._table_exists(table):
            continue
        cols = set(db._columns(table))

        # player id column varies across forks
        pcol = "player_id" if "player_id" in cols else ("playerid" if "playerid" in cols else None)
        if not pcol:  # must have some player column
            continue

        sid_col = "sid" if "sid" in cols else None
        pid_col = "pid" if "pid" in cols else None
        if not (sid_col and pid_col):
            continue

        count_col = "count" if "count" in cols else None
        attr_col  = "attributes" if "attributes" in cols else ( "attr" if "attr" in cols else None )
        depot_col = "depot_id" if "depot_id" in cols else None

        return {
            "table": table, "player_col": pcol, "count_col": count_col,
            "attr_col": attr_col, "sid_col": sid_col, "pid_col": pid_col,
            "depot_col": depot_col,
        }
    return None

def character_depot(request, name):
    """
    GET /character/<name>/depot.json
    Supports both schemas:
      - old (7.4): no depot_id column
      - newer TFS: has depot_id (locker per town)
    Returns trees built via pid/sid linkage.
    """
    # player id
    try:
        pid = db._get_player_id(name)
    except Exception:
        raise Http404("Character not found")

    info = _detect_depot_table()
    if not info:
        raise Http404("Depot table not found")

    table     = info["table"]
    pcol      = info["player_col"]
    count_col = info["count_col"]
    attr_col  = info["attr_col"]
    sid_col   = info["sid_col"]
    pid_col   = info["pid_col"]
    depot_col = info["depot_col"]

    # Optional filter by depot_id (if that column exists)
    depot_filter = None
    if depot_col:
        q = request.GET.get("depot")
        if q is not None:
            try:
                depot_filter = int(q)
            except ValueError:
                depot_filter = None

    # Build WHERE / args
    where = f"{pcol} = %s"
    args  = [pid]
    if depot_col and depot_filter is not None:
        where += f" AND {depot_col} = %s"
        args.append(depot_filter)

    # Pull all rows for this player's depot items
    select_cols = [pid_col, sid_col, "itemtype"]
    if count_col: select_cols.append(count_col)
    if attr_col:  select_cols.append(attr_col)
    if depot_col: select_cols.append(depot_col)

    rows = db.run("select",
        f"SELECT {', '.join(select_cols)} FROM {table} WHERE {where}",
        args
    )

    # Normalize and index
    items: List[Dict] = []
    lockers: Dict[Optional[int], List[Dict]] = {}  # key: depot_id or None
    for r in rows:
        it = db._encode_item(r, count_col, attr_col)
        # attach depot id if available
        it["depot_id"] = r.get(depot_col) if depot_col else None
        items.append(it)
        key = it["depot_id"]
        lockers.setdefault(key, []).append(it)

    def build_tree(item_list: List[Dict]) -> List[Dict]:
        # index children by parent pid (pid is either slot or parent sid; here: parent sid)
        by_parent: Dict[int, List[Dict]] = {}
        by_sid: Dict[int, Dict] = {}
        for it in item_list:
            by_sid[it["sid"]] = it
        for it in item_list:
            by_parent.setdefault(it["pid"], []).append(it)

        # roots are pid==0 (top-level inside locker)
        roots = by_parent.get(0, [])
        def build(node):
            kids = by_parent.get(node["sid"], [])
            return {**node, "children": [build(c) for c in kids]}
        return [build(r) for r in roots]

    # Assemble JSON
    out_lockers = []
    for dep_id, lst in sorted(lockers.items(), key=lambda kv: (kv[0] is None, kv[0])):
        out_lockers.append({
            "depot_id": dep_id,
            "containers": build_tree(lst),
        })

    return JsonResponse({
        "name": name,
        "has_depot_id": bool(depot_col),
        "lockers": out_lockers,
    })

def _get_acc_id_from_user(user):
    return user.username

def _table_exists(table):
    try:
        return db._table_exists(table)
    except Exception:
        return False

def _is_player_online(pid: int) -> bool:
    if _table_exists("players_online"):
        return bool(db.run("scalar", "SELECT 1 FROM players_online WHERE player_id=%s", [pid]))
    return False

@login_required
def account_character_edit(request, pid: int):
    acc_id = _get_acc_id_from_user(request.user)
    if not acc_id:
        raise Http404("No linked OT account.")

    # Ownership check + fetch current fields
    row = db.run("select_one",
                 "SELECT id, account_id, name, hidden, comment FROM players WHERE id=%s",
                 [pid])
    if not row:
        raise Http404("Character not found.")
    if int(row["account_id"]) != int(acc_id):
        return HttpResponseBadRequest("Not your character.")

    if request.method == "POST":
        comment = (request.POST.get("comment") or "").strip()
        hidden  = 1 if (request.POST.get("hidden") == "on") else 0

        # optional: block if online
        if _is_player_online(pid):
            return HttpResponseBadRequest("Character must be offline to edit.")

        db.run("execute",
               "UPDATE players SET comment=%s, hidden=%s WHERE id=%s",
               [comment, hidden, pid])
        return redirect("account_manage")

    # GET -> show form
    ctx = {
        "char": row,
        "back_url": reverse("account_manage"),
    }
    return render(request, "pages/character_edit.html", ctx)

@login_required
def account_character_delete(request, pid: int):
    acc_id = _get_acc_id_from_user(request.user)
    if not acc_id:
        raise Http404("No linked OT account.")

    row = db.run("select_one",
                 "SELECT id, account_id, name, deleted FROM players WHERE id=%s",
                 [pid])
    if not row:
        raise Http404("Character not found.")
    if int(row["account_id"]) != int(acc_id):
        return HttpResponseBadRequest("Not your character.")

    if request.method == "POST":
        # Optional: require confirm field; JS confirm in template also included.
        if _is_player_online(pid):
            return HttpResponseBadRequest("Character must be offline to delete.")
        # Soft-delete (safer): mark deleted + timestamp into `deletion` (UNIX)
        now = int(time.time())
        db.run("execute",
               "UPDATE players SET deleted=1, deletion=%s WHERE id=%s",
               [now, pid])
        return redirect("account_manage")

    # If someone GETs this URL, just show a tiny confirm template
    return render(request, "pages/character_delete_confirm.html", {"char": row, "back_url": reverse("account_manage")})


#MARK: Signup
def _hash_password(plain: str, method: str) -> str:
    b = (plain or "").encode("utf-8")
    m = (method or "").lower()
    if m == "plain":  return plain
    if m == "sha1":   return hashlib.sha1(b).hexdigest()
    if m == "md5":    return hashlib.md5(b).hexdigest()
    if m == "sha256": return hashlib.sha256(b).hexdigest()
    # fallback
    return hashlib.sha1(b).hexdigest()

def signup(request):
    if request.user.is_authenticated:
        return redirect("account_manage")

    # Your form must provide: account_id (IntegerField), email (optional), password1, password2
    form = SignUpForm(request.POST or None)

    if request.method == "POST":
        if not form.is_valid():
            return render(request, "pages/signup.html", {"form": form})

        # Pull data
        try:
            account_id = int(form.cleaned_data["username"])
        except Exception:
            form.add_error("account_id", "Please enter a valid account number.")
            return render(request, "pages/signup.html", {"form": form})

        if account_id <= 0:
            form.add_error("account_id", "Account number must be a positive integer.")
            return render(request, "pages/signup.html", {"form": form})

        email = form.cleaned_data.get("email") or ""
        raw_password = form.cleaned_data["password1"]
        hashed = _hash_password(raw_password, OT_PASSWORD_TYPE)

        if OT_DB_ALIAS not in settings.DATABASES:
            form.add_error(None, f"Server error: OT_DB_ALIAS '{OT_DB_ALIAS}' not configured.")
            return render(request, "pages/signup.html", {"form": form})

        # 1) Insert into OT using the exact id provided by the user
        try:
            with transaction.atomic(using=OT_DB_ALIAS):
                with connections[OT_DB_ALIAS].cursor() as cur:
                    # Ensure the id is free
                    cur.execute(f"SELECT 1 FROM {OT_ACCOUNT_TABLE} WHERE id=%s LIMIT 1", [account_id])
                    if cur.fetchone():
                        form.add_error("account_id", "That account number is already in use.")
                        return render(request, "pages/signup.html", {"form": form})

                    cols = ["id", OT_PASSWORD_COL]
                    vals = ["%s", "%s"]
                    params = [account_id, hashed]

                    if OT_EMAIL_COL:
                        cols.append(OT_EMAIL_COL)
                        vals.append("%s")
                        params.append(email)

                    #if OT_BLOCKED_COL:
                    #    cols.append(OT_BLOCKED_COL)
                    #    vals.append("%s")
                    #    params.append(0)  # unblocked by default

                    sql = f"INSERT INTO {OT_ACCOUNT_TABLE} ({', '.join(cols)}) VALUES ({', '.join(vals)})"
                    cur.execute(sql, params)
        except Exception:
            log.exception("OT INSERT failed for id=%s", account_id)
            form.add_error(None, "We couldn’t create your game account. Please try again.")
            return render(request, "pages/signup.html", {"form": form})

        # 2) Create matching Django user (username is the account number)
        try:
            user = User.objects.create_user(
                username=str(account_id),
                email=email,
                password=raw_password,
                is_active=not SIGNUP_CONFIRM_EMAIL,
            )
        except Exception:
            log.exception("Django user creation failed; cleaning OT id=%s", account_id)
            try:
                with transaction.atomic(using=OT_DB_ALIAS):
                    with connections[OT_DB_ALIAS].cursor() as cur:
                        cur.execute(f"DELETE FROM {OT_ACCOUNT_TABLE} WHERE id=%s", [account_id])
            except Exception:
                log.exception("Failed to rollback OT account id=%s", account_id)
            form.add_error(None, "We couldn’t create your site account. Please try again.")
            return render(request, "pages/signup.html", {"form": form})

        # 3) Optional email confirmation
        if not SIGNUP_CONFIRM_EMAIL:
            messages.success(request, "Account created. You can log in now with your account number.")
            return redirect("login")

        try:
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token  = default_token_generator.make_token(user)
            confirm_url = request.build_absolute_uri(
                reverse("signup_confirm", args=[uidb64, token])
            )

            ctx = {"user": user, "confirm_url": confirm_url}
            subject   = "Confirm your Retrowar account"
            text_body = render_to_string("emails/signup_confirm.txt", ctx)
            html_body = render_to_string("emails/signup_confirm.html", ctx)

            if user.email:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=text_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[user.email],
                    reply_to=[getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL)],
                )
                msg.attach_alternative(html_body, "text/html")
                msg.send(fail_silently=False)

        except Exception:
            log.exception("Signup email failed; cleaning both sides; id=%s", account_id)
            user.delete()
            try:
                with transaction.atomic(using=OT_DB_ALIAS):
                    with connections[OT_DB_ALIAS].cursor() as cur:
                        cur.execute(f"DELETE FROM {OT_ACCOUNT_TABLE} WHERE id=%s", [account_id])
            except Exception:
                log.exception("Failed to rollback OT account id=%s after email failure", account_id)
            form.add_error(None, "We couldn’t send the confirmation email. Please try again.")
            return render(request, "pages/signup.html", {"form": form})

        return render(request, "pages/signup_check_email.html", {"email": user.email})

    # GET
    return render(request, "pages/signup.html", {"form": form})

def signup_confirm(request, uidb64, token):
    try:
        uid  = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        raise Http404("Invalid confirmation link")

    if user.is_active:
        messages.info(request, "Your account is already active. You can sign in.")
        return redirect("login")

    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        login(request, user)
        messages.success(request, "Welcome! Your email has been confirmed.")
        return redirect("account_manage")
    else:
        messages.error(request, "This confirmation link is invalid or expired.")
        return redirect("signup")
    

#MARK: Last Kills

DEATHS_CANDIDATES = (
    "player_deaths", "players_deaths", "deaths", "kills", "last_kills"
)

NEEDED_COLS = {
    "player_id", "time", "level", "killed_by", "is_player",
    "mostdamage_by", "mostdamage_is_player",
    "unjustified", "mostdamage_unjustified",
}

def _detect_deaths_table() -> str | None:
    for t in DEATHS_CANDIDATES:
        if db._table_exists(t):
            cols = set(db._columns(t))
            if NEEDED_COLS.issubset(cols):
                return t
    return None

def last_kills(request):
    """
    /last-kills/?q=&unjust=on&pvp=on&page=N
    - q: search victim name, killer, most damage by
    - unjust: only unjustified kills
    - pvp: only where is_player=1 (victim killed by player)
    """
    table = _detect_deaths_table()
    if not table:
        raise Http404("Deaths table with required columns not found.")

    q = (request.GET.get("q") or "").strip()
    unjust = request.GET.get("unjust") in {"1", "on", "true", "yes"}
    pvp_only = request.GET.get("pvp") in {"1", "on", "true", "yes"}

    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1

    where = ["1=1"]
    params = {}

    if q:
        where.append(
            "(LOWER(p.name) LIKE :q OR LOWER(d.killed_by) LIKE :q OR LOWER(d.mostdamage_by) LIKE :q)"
        )
        params["q"] = f"%{q.lower()}%"

    if unjust:
        where.append("(d.unjustified = 1 OR d.mostdamage_unjustified = 1)")

    if pvp_only:
        where.append("(d.is_player = 1)")

    base_sql = f"""
        SELECT
            d.player_id, d.time, d.level,
            d.killed_by, d.is_player,
            d.mostdamage_by, d.mostdamage_is_player,
            d.unjustified, d.mostdamage_unjustified,
            p.name AS victim_name
        FROM {table} d
        JOIN players p ON p.id = d.player_id
        WHERE {" AND ".join(where)}
    """

    rows, page_meta = db.run(
        "paginate",
        base_sql,
        params,
        order_by="d.time DESC",
        page=page,
        per_page=50,
    )

    # Build querystring for pager without page=
    qs = request.GET.copy()
    qs.pop("page", None)
    querystring = urlencode(qs, doseq=True)

    ctx = {
        "rows": rows,
        "page_meta": page_meta,
        "querystring": querystring,
        "selected": {
            "q": q,
            "unjust": unjust,
            "pvp": pvp_only,
        },
    }
    return render(request, "pages/last_kills.html", ctx)

#MARK: Team

def team(request):
    # Detect where the staff group lives
    staff_rows = []
    grp_col_players = "group_id" if db._table_exists("players") and "group_id" in set(db._columns("players")) else None
    has_accounts   = db._table_exists("accounts")
    online_set     = set()
    # Online set (optional)
    if db._table_exists("players_online"):
        try:
            online_set = {r["player_id"] for r in db.run("select", "SELECT player_id FROM players_online")}
        except Exception:
            online_set = set()

    if grp_col_players:
        staff_rows = db.run("select", f"""
            SELECT *
              FROM players P
             WHERE {grp_col_players} >= 2  -- 2=GM, 3+=ADM (common OTS defaults)
             ORDER BY {grp_col_players} DESC, level DESC, name ASC
        """)
    elif has_accounts:
        staff_rows = db.run("select", """
            SELECT p.id, p.name, p.level, p.vocation, p.sex, a.country,
                   COALESCE(a.group_id, a.type, 1) AS grp,
                   p.lastlogin, p.lastlogout
              FROM players p
              JOIN accounts a ON a.id = p.account_id
             WHERE COALESCE(a.group_id, a.type, 1) >= 2
             ORDER BY COALESCE(a.group_id, a.type, 1) DESC, p.level DESC, p.name ASC
        """)
    else:
        staff_rows = []

    def role_from_grp(g):
        try: g = int(g or 1)
        except: g = 1
        if g >= 3: return "ADM"
        if g == 2: return "GM"
        return "Player"
    for r in staff_rows:
        r["role"] = role_from_grp(r.get(f"{grp_col_players}"))
        r["online"] = r.get("id") in online_set

    admins = [r for r in staff_rows if r["role"] == "ADM"]
    gms    = [r for r in staff_rows if r["role"] == "GM"]
    print("Admins:", admins)
    print("GMs:", gms)
    print("staff:", staff_rows)
    return render(request, "pages/team.html", {
        "admins": admins,
        "gms": gms,
        "has_staff": bool(admins or gms),
    })

#MARK: Commands & Rules
def commands(request):
    return render(request, "pages/commands.html", {})

def rules(request):
    return render(request, "pages/rules.html", {"now": now()})

#MARK: Create Character

def _players_columns():
    """Return set of column names present on the players table."""
    with connections[OT_DB_ALIAS].cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM {PLAYERS_TBL}")
        return {row[0] for row in cur.fetchall()}

@login_required
def account_character_create(request):
    # We stored this on login in your auth backend:
    ot_account_id = request.session.get("ot_account_id")
    if not ot_account_id:
        messages.error(request, "Your OT account session is missing. Please log in again.")
        return redirect("login")

    form = CreateCharacterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        name     = form.cleaned_data["name"].strip()
        vocation = form.cleaned_data["vocation"]
        sex      = form.cleaned_data["sex"]
        town_id  = form.cleaned_data.get("town_id") or getattr(settings, "OT_DEFAULT_TOWN_ID", 1)

        cols = _players_columns()

        # Uniqueness check (case-insensitive)
        with connections[OT_DB_ALIAS].cursor() as cur:
            cur.execute(f"SELECT 1 FROM {PLAYERS_TBL} WHERE LOWER(name)=LOWER(%s) LIMIT 1", [name])
            if cur.fetchone():
                form.add_error("name", "That name is already taken.")
                return render(request, "pages/account_character_create.html", {"form": form})

        # Build a defaults map with sensible values, then only keep keys that exist in your schema
        defaults = {
            "name": name,
            ACC_COL: ot_account_id,
            "vocation": vocation,
            "sex": sex,
            "town_id": int(town_id),

            # Common TFS columns (only included if they exist)
            "level":            int(getattr(settings, "OT_START_LEVEL", 8)),
            "experience":       0,
            "health":           int(getattr(settings, "OT_START_HEALTH", 185)),
            "healthmax":        int(getattr(settings, "OT_START_HEALTH", 185)),
            "mana":             int(getattr(settings, "OT_START_MANA", 35)),
            "manamax":          int(getattr(settings, "OT_START_MANA", 35)),
            "maglevel":         int(getattr(settings, "OT_START_MAGLEVEL", 0)),
            "cap":              int(getattr(settings, "OT_START_CAP", 470)),
            "soul":             int(getattr(settings, "OT_START_SOUL", 100)),

            # Position (0/0/0 lets town spawn handle it on some engines; otherwise set your temple coords)
            "posx":             int(getattr(settings, "OT_START_POSX", 0)),
            "posy":             int(getattr(settings, "OT_START_POSY", 0)),
            "posz":             int(getattr(settings, "OT_START_POSZ", 0)),

            # Look / outfit
            "looktype":         int(getattr(settings, "OT_START_LOOKTYPE", 128)),
            "lookhead":         int(getattr(settings, "OT_START_LOOKHEAD", 78)),
            "lookbody":         int(getattr(settings, "OT_START_LOOKBODY", 88)),
            "looklegs":         int(getattr(settings, "OT_START_LOOKLEGS", 58)),
            "lookfeet":         int(getattr(settings, "OT_START_LOOKFEET", 0)),

            # Optional often-present columns
            "skull":            0,
            #"shield":           0,
            #"loss_experience":  100,
            #"loss_mana":        100,
            #"loss_skills":      100,
            #"loss_containers":  100,
        }

        war_server = {
            "name": name,
            ACC_COL: ot_account_id,
            "vocation": vocation,
            "sex": sex,
            "town_id": int(town_id),

            # Common TFS columns (only included if they exist)
            "level":            int(getattr(settings, "WAR_OT_START_LEVEL", 8)),
            "experience":       0,
            "health":           int(getattr(settings, "WAR_OT_START_HEALTH", 185)),
            "healthmax":        int(getattr(settings, "WAR_OT_START_HEALTH", 185)),
            "mana":             int(getattr(settings, "WAR_OT_START_MANA", 35)),
            "manamax":          int(getattr(settings, "WAR_OT_START_MANA", 35)),
            "maglevel":         int(getattr(settings, "WAR_OT_START_MAGLEVEL", 0)),
            "cap":              int(getattr(settings, "WAR_OT_START_CAP", 470)),
            "soul":             int(getattr(settings, "WAR_OT_START_SOUL", 100)),

            # Position (0/0/0 lets town spawn handle it on some engines; otherwise set your temple coords)
            "posx":             int(getattr(settings, "WAR_OT_START_POSX", 0)),
            "posy":             int(getattr(settings, "WAR_OT_START_POSY", 0)),
            "posz":             int(getattr(settings, "WAR_OT_START_POSZ", 0)),

            # Look / outfit
            "looktype":         int(getattr(settings, "WAR_OT_START_LOOKTYPE", 128)),
            "lookhead":         int(getattr(settings, "WAR_OT_START_LOOKHEAD", 78)),
            "lookbody":         int(getattr(settings, "WAR_OT_START_LOOKBODY", 88)),
            "looklegs":         int(getattr(settings, "WAR_OT_START_LOOKLEGS", 58)),
            "lookfeet":         int(getattr(settings, "WAR_OT_START_LOOKFEET", 0)),

            # Optional often-present columns
            "skull":            0,
            "skill_axe":        10, #int(getattr(settings, "WAR_OT_START_AXE_SKILL", 0)),
            "skill_club":       10, #int(getattr(settings, "WAR_OT_START_CLUB_SKILL", 0)),
            "skill_sword":      10, #int(getattr(settings, "WAR_OT_START_SWORD_SKILL", 0)),
            "skill_dist":       10, #int(getattr(settings, "WAR_OT_START_DISTANCE_SKILL", 0)),
            "skill_shielding":  10, #int(getattr(settings, "WAR_OT_START_SHIELDING_SKILL", 0)),
        }

        if settings.WAR_SERVER_ENABLED:
            for k, v in war_server.items():
                if k in cols:
                    if k == "vocation":
                        if v in [1, 2]:
                            war_server["maglevel"] = int(getattr(settings, "WAR_OT_START_MAGE_MAGIC_SKILL", 0))
                        elif v == 3:
                            war_server["maglevel"] = int(getattr(settings, "WAR_OT_START_PALADIN_MAGIC_SKILL", 0))
                            war_server["skill_dist"] = int(getattr(settings, "WAR_OT_START_DISTANCE_SKILL", 0))
                            war_server["skill_shielding"] = int(getattr(settings, "WAR_OT_START_SHIELDING_SKILL", 0))
                        elif v == 4:
                            war_server["maglevel"] = int(getattr(settings, "WAR_OT_START_KNIGHT_MAGIC_SKILL", 0))
                            war_server["skill_axe"] = int(getattr(settings, "WAR_OT_START_AXE_SKILL", 0))
                            war_server["skill_club"] = int(getattr(settings, "WAR_OT_START_CLUB_SKILL", 0))
                            war_server["skill_sword"] = int(getattr(settings, "WAR_OT_START_SWORD_SKILL", 0))
                            war_server["skill_shielding"] = int(getattr(settings, "WAR_OT_START_SHIELDING_SKILL", 0))
                    
            data = {k: v for k, v in war_server.items() if k in cols}
        else:
            data = {k: v for k, v in defaults.items() if k in cols}

        # Final safety: required minimum
        for required in ("name", ACC_COL, "vocation", "sex", "town_id"):
            if required not in data:
                # If your schema is unusual, tell yourself why:
                log.error("Missing required column on players table: %s", required)
                messages.error(request, f"Server is missing required column '{required}' in '{PLAYERS_TBL}'.")
                return render(request, "pages/account_character_create.html", {"form": form})


        cur.execute(f"SELECT COUNT(*) FROM {PLAYERS_TBL} WHERE {ACC_COL}=%s", [ot_account_id])
        if cur.fetchone()[0] >= 5:
            form.add_error(None, "You reached the character limit on this account.")
            return render(request, "pages/account_character_create.html", {"form": form})
        # Insert
        field_list = list(data.keys())
        placeholders = ", ".join(["%s"] * len(field_list))
        sql = f"INSERT INTO {PLAYERS_TBL} ({', '.join(field_list)}) VALUES ({placeholders})"
        params = [data[f] for f in field_list]

        try:
            with transaction.atomic(using=OT_DB_ALIAS):
                with connections[OT_DB_ALIAS].cursor() as cur:
                    cur.execute(sql, params)
        except Exception:
            log.exception("Failed to insert character '%s' for account %s", name, ot_account_id)
            messages.error(request, "Couldn’t create your character. Please try again.")
            return render(request, "pages/account_character_create.html", {"form": form})

        messages.success(request, f"Character '{name}' created!")
        return redirect("account_manage")

    return render(request, "pages/account_character_create.html", {"form": form})