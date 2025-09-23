from django.shortcuts import render, redirect
from django.http import Http404
from .db import DB

db = DB()

def _detect_houses_schema():
    """
    Returns a mapping of houses table + columns (best effort across TFS versions):
      {
        "table": "houses",
        "id_col": "id",
        "name_col": "name",
        "owner_col": "owner",
        "rent_col": "rent",
        "town_col": "townid" or "town_id",
        "size_col": "size" or "sqm",
        "beds_col": "beds" (optional, may be None),
        "guild_col": "guildhall" (optional),
      }
    """
    table = "houses"
    # If you have db._table_exists / db._columns, use them; otherwise assume standard
    try:
        cols = set(db._columns(table))  # present in your project elsewhere
    except Exception:
        cols = {
            "id", "name", "owner", "rent", "townid",
            "size", "sqm", "beds", "guildhall"
        }

    def pick(*cands):
        for c in cands:
            if c in cols:
                return c
        return None

    return {
        "table": table,
        "id_col":   pick("id"),
        "name_col": pick("name"),
        "owner_col":pick("owner"),
        "rent_col": pick("rent"),
        "town_col": pick("townid", "town_id"),
        "size_col": pick("size", "sqm"),
        "beds_col": pick("beds"),
        "guild_col":pick("guildhall"),
    }

def houses_list(request):
    schema = _detect_houses_schema()
    if not schema["table"]:
        raise Http404("Houses table not found")

    # Filters
    q       = (request.GET.get("q") or "").strip()
    town    = (request.GET.get("town") or "all").strip().lower()
    status  = (request.GET.get("status") or "all").strip().lower()   # all|empty|owned
    minsz   = request.GET.get("minsize") or ""
    maxsz   = request.GET.get("maxsize") or ""
    minrent = request.GET.get("minrent") or ""
    maxrent = request.GET.get("maxrent") or ""
    order   = (request.GET.get("order") or "name").strip().lower()   # name|rent|size

    # Paging
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1

    H = schema
    t  = H["table"]
    c_id, c_name, c_owner, c_rent, c_town, c_size = H["id_col"], H["name_col"], H["owner_col"], H["rent_col"], H["town_col"], H["size_col"]
    c_beds = H["beds_col"]

    # Make a SELECT with aliases so we can order by them later
    select_cols = [
        f"h.{c_id}      AS id",
        f"h.{c_name}    AS name",
        f"h.{c_owner}   AS owner",
        f"h.{c_rent}    AS rent",
        f"h.{c_town}    AS town_id",
        f"COALESCE(h.{c_size}, 0) AS size",
    ]
    if c_beds:
        select_cols.append(f"COALESCE(h.{c_beds}, 0) AS beds")
    else:
        select_cols.append("0 AS beds")

    base_sql = f"""
        SELECT
          {", ".join(select_cols)},
          COALESCE(p.name, '') AS owner_name
        FROM {t} h
        LEFT JOIN players p ON p.id = h.{c_owner} AND h.{c_owner} > 0
        WHERE 1=1
    """

    params = {}

    if q:
        base_sql += " AND h.{name} LIKE :q ".format(name=c_name)
        params["q"] = f"%{q}%"

    if town not in ("", "all"):
        try:
            town_id = int(town)
            base_sql += f" AND h.{c_town} = :town_id "
            params["town_id"] = town_id
        except ValueError:
            pass

    if status == "empty":
        base_sql += f" AND (h.{c_owner} IS NULL OR h.{c_owner} = 0) "
    elif status == "owned":
        base_sql += f" AND h.{c_owner} > 0 "

    def _clamp_int(val, name):
        if val == "":
            return None
        try:
            return max(0, int(val))
        except ValueError:
            return None

    v = _clamp_int(minsz, "minsize")
    if v is not None:
        base_sql += f" AND COALESCE(h.{c_size}, 0) >= :minsz "
        params["minsz"] = v

    v = _clamp_int(maxsz, "maxsize")
    if v is not None:
        base_sql += f" AND COALESCE(h.{c_size}, 0) <= :maxsz "
        params["maxsz"] = v

    v = _clamp_int(minrent, "minrent")
    if v is not None:
        base_sql += f" AND COALESCE(h.{c_rent}, 0) >= :minrent "
        params["minrent"] = v

    v = _clamp_int(maxrent, "maxrent")
    if v is not None:
        base_sql += f" AND COALESCE(h.{c_rent}, 0) <= :maxrent "
        params["maxrent"] = v

    # Order
    if order == "rent":
        order_by = "rent ASC, name ASC"
    elif order == "size":
        order_by = "size DESC, name ASC"
    else:
        order_by = "name ASC"

    rows, meta = db.run("paginate", base_sql, params, order_by=order_by, page=page, per_page=25)

    # Build town options from data (unique ids seen)
    town_ids = sorted({r["town_id"] for r in rows} | set())
    # Or gather from entire table if you prefer:
    # all_towns = db.run("select", f"SELECT DISTINCT {c_town} AS town_id FROM {t} ORDER BY {c_town} ASC")

    ctx = {
        "houses": rows,
        "page_meta": meta,
        "selected": {
            "q": q, "town": town, "status": status,
            "minsize": minsz, "maxsize": maxsz,
            "minrent": minrent, "maxrent": maxrent,
            "order": order,
        },
        "town_ids": town_ids,
        "querystring": request.GET.urlencode().replace(f"page={page}", "").strip("&"),
    }
    return render(request, "pages/houses_list.html", ctx)

def house_detail(request, house_id: int):
    H = _detect_houses_schema()
    t  = H["table"]
    c_id, c_name, c_owner, c_rent, c_town, c_size = H["id_col"], H["name_col"], H["owner_col"], H["rent_col"], H["town_col"], H["size_col"]
    c_beds = H["beds_col"]
    c_guild= H["guild_col"]

    cols = [
        f"h.{c_id}   AS id",
        f"h.{c_name} AS name",
        f"h.{c_owner} AS owner",
        f"COALESCE(h.{c_rent},0) AS rent",
        f"h.{c_town} AS town_id",
        f"COALESCE(h.{c_size},0) AS size",
        f"COALESCE(h.{c_beds},0) AS beds" if c_beds else "0 AS beds",
        f"COALESCE(h.{c_guild},0) AS guildhall" if c_guild else "0 AS guildhall",
        "COALESCE(p.name,'') AS owner_name",
        "p.level AS owner_level",
        "p.vocation AS owner_vocation",
    ]
    house = db.run("select_one", f"""
        SELECT {", ".join(cols)}
          FROM {t} h
          LEFT JOIN players p ON p.id = h.{c_owner} AND h.{c_owner} > 0
         WHERE h.{c_id} = :hid
        """, {"hid": house_id})
    if not house:
        raise Http404("House not found")

    # Optional: access lists, if present (TFS: house_lists)
    lists = []
    try:
        cols2 = set(db._columns("house_lists"))
        if {"house_id", "listid", "list"} <= cols2:
            lists = db.run("select", """
                SELECT listid, list
                  FROM house_lists
                 WHERE house_id = :hid
                 ORDER BY listid ASC
            """, {"hid": house_id})
    except Exception:
        pass

    return render(request, "pages/house_detail.html", {"h": house, "lists": lists})
