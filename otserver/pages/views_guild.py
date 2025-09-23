# pages/views.py
from urllib.parse import unquote
from django.shortcuts import render
from django.http import Http404
from .db import DB

db = DB()

def _detect_guild_schema():
    """Detect how guild membership is stored."""
    if not db._table_exists("guilds"):
        return {"mode": "absent"}

    gcols = set(db._columns("guilds"))
    pcols = set(db._columns("players"))
    rcols = set(db._columns("guild_ranks")) if db._table_exists("guild_ranks") else set()
    m_has  = db._table_exists("guild_membership")

    # Columns that differ by forks
    g_owner = "owner_id" if "owner_id" in gcols else ("ownerid" if "ownerid" in gcols else None)
    g_created = "creationdata" if "creationdata" in gcols else ("creationdate" if "creationdate" in gcols else None)
    g_desc = "description" if "description" in gcols else None
    g_motd = "motd" if "motd" in gcols else None

    # Modes:
    # 1) players.rank_id -> guild_ranks.id (guild via guild_ranks.guild_id)
    if (("rank_id" in pcols or "rankid" in pcols) and ("guild_id" in rcols or "guildid" in rcols)):
        return {
            "mode": "by_rank",
            "p_rank": "rank_id" if "rank_id" in pcols else "rankid",
            "gr_guild": "guild_id" if "guild_id" in rcols else "guildid",
            "gr_id": "id",
            "gr_name": "name" if "name" in rcols else None,
            "gr_level": "level" if "level" in rcols else None,
            "g_owner": g_owner, "g_created": g_created, "g_desc": g_desc, "g_motd": g_motd,
        }

    # 2) players.guild_id directly
    if "guild_id" in pcols or "guildid" in pcols:
        return {
            "mode": "players_guild_id",
            "p_guild": "guild_id" if "guild_id" in pcols else "guildid",
            "p_rank": "rank_id" if "rank_id" in pcols else ("rankid" if "rankid" in pcols else None),
            "gr_id": "id" if "id" in rcols else None,
            "gr_name": "name" if "name" in rcols else None,
            "gr_level": "level" if "level" in rcols else None,
            "g_owner": g_owner, "g_created": g_created, "g_desc": g_desc, "g_motd": g_motd,
        }

    # 3) guild_membership bridge table
    if m_has:
        mcols = set(db._columns("guild_membership"))
        return {
            "mode": "membership",
            "m_player": "player_id" if "player_id" in mcols else "playerid",
            "m_guild":  "guild_id"  if "guild_id"  in mcols else "guildid",
            "m_rank":   "rank_id"   if "rank_id"   in mcols else ("rankid" if "rankid" in mcols else None),
            "gr_id": "id" if "id" in rcols else None,
            "gr_name": "name" if "name" in rcols else None,
            "gr_level": "level" if "level" in rcols else None,
            "g_owner": g_owner, "g_created": g_created, "g_desc": g_desc, "g_motd": g_motd,
        }

    return {"mode": "unknown", "g_owner": g_owner, "g_created": g_created, "g_desc": g_desc, "g_motd": g_motd}

def _guild_member_counts(bind):
    """Return {guild_id: member_count} for the detected schema."""
    mode = bind["mode"]
    if mode == "by_rank":
        return {
            r["guild_id"]: r["ct"]
            for r in db.run("select", f"""
                SELECT gr.{bind['gr_guild']} AS guild_id, COUNT(*) AS ct
                  FROM players p
                  JOIN guild_ranks gr ON p.{bind['p_rank']} = gr.{bind['gr_id']}
                 GROUP BY gr.{bind['gr_guild']}
            """)
        }
    if mode == "players_guild_id":
        return {
            r["guild_id"]: r["ct"]
            for r in db.run("select", f"""
                SELECT {bind['p_guild']} AS guild_id, COUNT(*) AS ct
                  FROM players
                 WHERE {bind['p_guild']} IS NOT NULL AND {bind['p_guild']} <> 0
                 GROUP BY {bind['p_guild']}
            """)
        }
    if mode == "membership":
        return {
            r["guild_id"]: r["ct"]
            for r in db.run("select", f"""
                SELECT {bind['m_guild']} AS guild_id, COUNT(*) AS ct
                  FROM guild_membership
                 GROUP BY {bind['m_guild']}
            """)
        }
    return {}

def _guild_leaders(bind, guild_ids):
    """Return {guild_id: leader_name} via owner_id or highest rank."""
    leaders = {}
    if not guild_ids:
        return leaders

    # Try owner_id
    if bind.get("g_owner"):
        owners = db.run(
            "select",
            f"SELECT g.id AS gid, p.name AS leader "
            f"FROM guilds g LEFT JOIN players p ON p.id = g.{bind['g_owner']} "
            f"WHERE g.id IN ({', '.join(['%s']*len(guild_ids))})",
            guild_ids,
        )
        for r in owners:
            if r.get("leader"):
                leaders[r["gid"]] = r["leader"]

    missing = [gid for gid in guild_ids if gid not in leaders]
    if not missing:
        return leaders

    # Fallback: highest rank per guild (if ranks exist)
    if bind["mode"] in ("by_rank", "players_guild_id", "membership") and bind.get("gr_level"):
        q = None
        if bind["mode"] == "by_rank":
            q = f"""
                SELECT gr.{bind['gr_guild']} AS gid, p.name
                  FROM players p
                  JOIN guild_ranks gr ON p.{bind['p_rank']} = gr.{bind['gr_id']}
                 WHERE gr.{bind['gr_guild']} IN ({', '.join(['%s']*len(missing))})
                 ORDER BY gr.{bind['gr_level']} ASC, p.level DESC
            """
        elif bind["mode"] == "players_guild_id" and bind.get("p_rank"):
            q = f"""
                SELECT {bind['p_guild']} AS gid, p.name
                  FROM players p
                  LEFT JOIN guild_ranks gr ON p.{bind['p_rank']} = gr.{bind['gr_id']}
                 WHERE {bind['p_guild']} IN ({', '.join(['%s']*len(missing))})
                 ORDER BY COALESCE(gr.{bind['gr_level']}, 3) ASC, p.level DESC
            """
        elif bind["mode"] == "membership" and bind.get("m_rank"):
            q = f"""
                SELECT gm.{bind['m_guild']} AS gid, p.name
                  FROM guild_membership gm
                  JOIN players p ON p.id = gm.{bind['m_player']}
                  LEFT JOIN guild_ranks gr ON gm.{bind['m_rank']} = gr.{bind['gr_id']}
                 WHERE gm.{bind['m_guild']} IN ({', '.join(['%s']*len(missing))})
                 ORDER BY COALESCE(gr.{bind['gr_level']}, 3) ASC, p.level DESC
            """
        if q:
            got = set()
            for r in db.run("select", q, missing):
                gid = r["gid"]
                if gid not in leaders:
                    leaders[gid] = r["name"]
                    got.add(gid)
                if len(got) == len(missing):
                    break
    return leaders

def guild_list(request):
    bind = _detect_guild_schema()
    if bind.get("mode") == "absent":
        raise Http404("Guilds table not found")

    order = request.GET.get("order", "name")  # name | members | created
    base = db.run("select", f"""
        SELECT id, name,
               {bind['g_created']} AS created,
               {bind['g_desc']} AS description,
               {bind['g_motd']} AS motd
          FROM guilds
         ORDER BY name ASC
    """)

    ids = [g["id"] for g in base]
    counts = _guild_member_counts(bind)
    leaders = _guild_leaders(bind, ids)

    # attach aggregates
    for g in base:
        g["members"] = counts.get(g["id"], 0)
        g["leader"] = leaders.get(g["id"])

    if order == "members":
        base.sort(key=lambda x: (-x["members"], x["name"].lower()))
    elif order == "created" and bind.get("g_created"):
        base.sort(key=lambda x: (0 if x["created"] is None else -int(x["created"]), x["name"].lower()))
    else:
        base.sort(key=lambda x: x["name"].lower())

    return render(request, "pages/guilds_list.html", {"guilds": base})

def _guild_by_name(name: str):
    row = db.run("select_one", "SELECT * FROM guilds WHERE name = %s", [name])
    if not row:
        # Case-insensitive fallback
        row = db.run("select_one", "SELECT * FROM guilds WHERE LOWER(name) = LOWER(%s)", [name])
    return row

def guild_detail(request, name):
    name = unquote(name)
    g = _guild_by_name(name)
    if not g:
        raise Http404("Guild not found")

    bind = _detect_guild_schema()
    gid = g["id"]

    # Members per schema
    members = []
    mode = bind["mode"]
    if mode == "by_rank":
        members = db.run("select", f"""
            SELECT p.id, p.name, p.level, p.vocation, p.sex,
                   gr.{bind['gr_name']} AS rank_name,
                   gr.{bind['gr_level']} AS rank_level,
                   CASE WHEN po.player_id IS NULL THEN 0 ELSE 1 END AS is_online
              FROM players p
              JOIN guild_ranks gr ON p.{bind['p_rank']} = gr.{bind['gr_id']}
              LEFT JOIN players_online po ON po.player_id = p.id
             WHERE gr.{bind['gr_guild']} = %s
             ORDER BY gr.{bind['gr_level']} ASC, p.level DESC, p.name ASC
        """, [gid])
    elif mode == "players_guild_id":
        members = db.run("select", f"""
            SELECT p.id, p.name, p.level, p.vocation, p.sex,
                   COALESCE(gr.{bind['gr_name']}, 'Member') AS rank_name,
                   COALESCE(gr.{bind['gr_level']}, 3) AS rank_level,
                   CASE WHEN po.player_id IS NULL THEN 0 ELSE 1 END AS is_online
              FROM players p
              LEFT JOIN guild_ranks gr ON {("p."+bind['p_rank']) if bind.get('p_rank') else "NULL"} = gr.{bind['gr_id']}
              LEFT JOIN players_online po ON po.player_id = p.id
             WHERE p.{bind['p_guild']} = %s
             ORDER BY COALESCE(gr.{bind['gr_level']}, 3) ASC, p.level DESC, p.name ASC
        """, [gid])
    elif mode == "membership":
        members = db.run("select", f"""
            SELECT p.id, p.name, p.level, p.vocation, p.sex,
                   COALESCE(gr.{bind['gr_name']}, 'Member') AS rank_name,
                   COALESCE(gr.{bind['gr_level']}, 3) AS rank_level,
                   CASE WHEN po.player_id IS NULL THEN 0 ELSE 1 END AS is_online
              FROM guild_membership gm
              JOIN players p ON p.id = gm.{bind['m_player']}
              LEFT JOIN guild_ranks gr ON gm.{bind['m_rank']} = gr.{bind['gr_id']}
              LEFT JOIN players_online po ON po.player_id = p.id
             WHERE gm.{bind['m_guild']} = %s
             ORDER BY COALESCE(gr.{bind['gr_level']}, 3) ASC, p.level DESC, p.name ASC
        """, [gid])
    else:
        members = []

    # extras
    members_total = len(members)
    online_total = sum(1 for m in members if m.get("is_online"))

    context = {
        "g": g,
        "members": members,
        "members_total": members_total,
        "online_total": online_total,
    }
    return render(request, "pages/guild_detail.html", context)
