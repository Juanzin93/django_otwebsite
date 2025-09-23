# otserver/pages/snapshots.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from .db import DB
from .items_service import SLOT_NAMES

db = DB()


def build_equipment(pid: int) -> Tuple[List[Dict], str]:
    """
    Returns (slots, schema_mode). Slots is a length-10 list with:
      {slot, slot_name, itemtype|None, count, attributes_hex}
    Works with both “slot” schema and classic pid/sid.
    """
    info = db._detect_items_schema()
    if not info:
        return [], "unknown"

    table   = info["table"]
    mode    = info["mode"]         # "slot" or "pid"
    slotcol = info.get("slot_col") # only for "slot"

    if mode == "slot":
        rows = db.run("select", f"""
            SELECT {slotcol} AS slot, itemtype, count, attributes
              FROM {table}
             WHERE player_id = %s AND {slotcol} BETWEEN 1 AND 10
             ORDER BY {slotcol} ASC, sid ASC
        """, [pid])
        by_slot = {}
        for r in rows:
            s = int(r["slot"])
            if s not in by_slot:
                by_slot[s] = r
        out = []
        for s in range(1, 11):
            it = by_slot.get(s)
            if it:
                out.append({
                    "slot": s,
                    "slot_name": SLOT_NAMES.get(s, str(s)),
                    "itemtype": int(it["itemtype"]),
                    "count": int(it.get("count") or 1),
                    "attributes_hex": db._to_hex_or_none(it.get("attributes")),
                })
            else:
                out.append({"slot": s, "slot_name": SLOT_NAMES.get(s, str(s)),
                            "itemtype": None, "count": 0, "attributes_hex": None})
        return out, mode

    # classic pid/sid schema: equipped = pid in 1..10
    rows = db.run("select", f"""
        SELECT pid AS slot, itemtype, {info['count_col']} AS count, {info['attr_col']} AS attributes
          FROM {table}
         WHERE {info['player_col']} = %s AND pid BETWEEN 1 AND 10
         ORDER BY pid ASC, sid ASC
    """, [pid])
    by_slot = {}
    for r in rows:
        s = int(r["slot"])
        if s not in by_slot:
            by_slot[s] = r
    out = []
    for s in range(1, 11):
        it = by_slot.get(s)
        if it:
            out.append({
                "slot": s,
                "slot_name": SLOT_NAMES.get(s, str(s)),
                "itemtype": int(it["itemtype"]),
                "count": int(it.get("count") or 1),
                "attributes_hex": db._to_hex_or_none(it.get("attributes")),
            })
        else:
            out.append({"slot": s, "slot_name": SLOT_NAMES.get(s, str(s)),
                        "itemtype": None, "count": 0, "attributes_hex": None})
    return out, mode

def build_inventory_tree(pid: int, root_slot: int = 3) -> Dict:
    """
    Builds the same container tree as your character_inventory view:
      { name, slot, slot_name, containers:[ ...recursive... ] }
    """
    info = db._detect_items_table()
    if not info:
        return {"name": "", "slot": root_slot, "slot_name": SLOT_NAMES.get(root_slot, str(root_slot)), "containers": []}

    table     = info["table"]
    pcol      = info["player_col"]
    count_col = info["count_col"]
    attr_col  = info["attr_col"]

    rows = db.run("select", f"""
        SELECT pid, sid, itemtype
               {", " + count_col if count_col else ""}
               {", " + attr_col  if attr_col  else ""}
          FROM {table}
         WHERE {pcol} = %s
    """, [pid])

    items = [db._encode_item(r, count_col, attr_col) for r in rows]
    children: Dict[int, List[Dict]] = {}
    for it in items:
        children.setdefault(it["pid"], []).append(it)

    def build(node):
        kidz = [build(c) for c in children.get(node["sid"], [])]
        return {**node, "children": kidz}

    roots = [it for it in items if it["pid"] == root_slot]
    containers = [build(r) for r in roots]
    return {
        "slot": root_slot,
        "slot_name": SLOT_NAMES.get(root_slot, str(root_slot)),
        "containers": containers,
    }

def _detect_depot_table() -> Optional[Dict[str, str]]:
    """Same logic you already had; kept here so views and snapshots share it."""
    for table in ("players_depotitems", "player_depotitems"):
        if not db._table_exists(table):
            continue
        cols = set(db._columns(table))

        pcol = "player_id" if "player_id" in cols else ("playerid" if "playerid" in cols else None)
        if not pcol:
            continue

        sid_col = "sid" if "sid" in cols else None
        pid_col = "pid" if "pid" in cols else None
        if not (sid_col and pid_col):
            continue

        count_col = "count" if "count" in cols else None
        attr_col  = "attributes" if "attributes" in cols else ("attr" if "attr" in cols else None)
        depot_col = "depot_id" if "depot_id" in cols else None

        return {
            "table": table, "player_col": pcol, "count_col": count_col,
            "attr_col": attr_col, "sid_col": sid_col, "pid_col": pid_col,
            "depot_col": depot_col,
        }
    return None

def build_depot(pid: int, depot_filter: Optional[int] = None) -> Dict:
    """
    Builds the same lockers/containers structure as your character_depot view.
    """
    info = _detect_depot_table()
    if not info:
        return {"has_depot_id": False, "lockers": []}

    table     = info["table"]
    pcol      = info["player_col"]
    count_col = info["count_col"]
    attr_col  = info["attr_col"]
    sid_col   = info["sid_col"]
    pid_col   = info["pid_col"]
    depot_col = info["depot_col"]

    where = f"{pcol} = %s"
    args  = [pid]
    if depot_col is not None and depot_filter is not None:
        where += f" AND {depot_col} = %s"
        args.append(depot_filter)

    select_cols = [pid_col, sid_col, "itemtype"]
    if count_col: select_cols.append(count_col)
    if attr_col:  select_cols.append(attr_col)
    if depot_col: select_cols.append(depot_col)

    rows = db.run("select", f"SELECT {', '.join(select_cols)} FROM {table} WHERE {where}", args)

    items: List[Dict] = []
    lockers: Dict[Optional[int], List[Dict]] = {}
    for r in rows:
        it = db._encode_item(r, count_col, attr_col)
        it["depot_id"] = r.get(depot_col) if depot_col else None
        items.append(it)
        lockers.setdefault(it["depot_id"], []).append(it)

    def build_tree(item_list: List[Dict]) -> List[Dict]:
        by_parent: Dict[int, List[Dict]] = {}
        for it in item_list:
            by_parent.setdefault(it["pid"], []).append(it)
        roots = by_parent.get(0, [])
        def build(node):
            kids = by_parent.get(node["sid"], [])
            return {**node, "children": [build(c) for c in kids]}
        return [build(r) for r in roots]

    out_lockers = []
    for dep_id, lst in sorted(lockers.items(), key=lambda kv: (kv[0] is None, kv[0])):
        out_lockers.append({"depot_id": dep_id, "containers": build_tree(lst)})

    return {"has_depot_id": bool(depot_col), "lockers": out_lockers}

def fetch_equipment_inventory_depot(pid: int) -> Dict[str, object]:
    """
    Single call used by the bazaar snapshot.
    Inventory defaults to the backpack tree (slot=3).
    """
    eq, schema = build_equipment(pid)
    inv        = build_inventory_tree(pid, root_slot=3)
    dep        = build_depot(pid)
    return {"equipment": eq, "inventory": inv, "depot": dep}

def _character_snapshot(pid: int) -> dict:
    """Build minimal snapshot: equipment, inventory (backpack tree), depot (all lockers)."""
    # Equipment rows (slots 1..10)
    eq_info = db._detect_items_schema()
    equipment = []
    if eq_info:
        rows = db.run("select", f"""
            SELECT itemtype, count, attributes, {eq_info['slot_col']} AS slot, sid
              FROM {eq_info['table']}
             WHERE player_id = :pid AND {eq_info['slot_col']} BETWEEN 1 AND 10
             ORDER BY {eq_info['slot_col']} ASC, sid ASC
        """, {"pid": pid})
        seen = set()
        for r in rows:
            s = int(r["slot"])
            if s in seen:   # keep first per slot
                continue
            seen.add(s)
            equipment.append({
                "slot": s,
                "itemtype": int(r["itemtype"]),
                "count": int(r.get("count") or 1),
                "attributes_hex": db._to_hex_or_none(r.get("attributes")),
            })

    # Inventory: backpack tree (slot 3)
    inv_info = db._detect_items_table()
    inventory = []
    if inv_info:
        rows = db.run("select", f"""
            SELECT pid, sid, itemtype
                   {", " + inv_info["count_col"] if inv_info["count_col"] else ""}
                   {", " + inv_info["attr_col"]  if inv_info["attr_col"]  else ""}
              FROM {inv_info['table']}
             WHERE {inv_info['player_col']} = :pid
        """, {"pid": pid})
        items = [db._encode_item(r, inv_info["count_col"], inv_info["attr_col"]) for r in rows]
        by_parent = {}
        for it in items:
            by_parent.setdefault(it["pid"], []).append(it)
        def build(node):
            kids = by_parent.get(node["sid"], [])
            return {**node, "children": [build(c) for c in kids]}
        roots = [it for it in items if it["pid"] == 3]  # backpack slot
        inventory = [build(r) for r in roots]

    # Depot: group by depot_id if present, else single locker
    depot_info = None
    for t in ("players_depotitems", "player_depotitems"):
        if db._table_exists(t):
            depot_info = t
            break
    depot = []
    if depot_info:
        cols = set(db._columns(depot_info))
        pcol  = "player_id" if "player_id" in cols else ("playerid" if "playerid" in cols else None)
        sid_c = "sid" if "sid" in cols else None
        pid_c = "pid" if "pid" in cols else None
        cnt_c = "count" if "count" in cols else None
        atr_c = "attributes" if "attributes" in cols else ("attr" if "attr" in cols else None)
        dep_c = "depot_id" if "depot_id" in cols else None
        if pcol and sid_c and pid_c:
            sel = [pid_c, sid_c, "itemtype"]
            if cnt_c: sel.append(cnt_c)
            if atr_c: sel.append(atr_c)
            if dep_c: sel.append(dep_c)
            rows = db.run("select", f"SELECT {', '.join(sel)} FROM {depot_info} WHERE {pcol}=%s", [pid])
            items = []
            for r in rows:
                it = db._encode_item(r, cnt_c, atr_c)
                it["depot_id"] = r.get(dep_c) if dep_c else None
                items.append(it)
            # group -> trees
            lockers = {}
            for it in items:
                lockers.setdefault(it["depot_id"], []).append(it)
            def make_tree(lst):
                by_parent = {}
                for it in lst:
                    by_parent.setdefault(it["pid"], []).append(it)
                def build(node):
                    kids = by_parent.get(node["sid"], [])
                    return {**node, "children": [build(c) for c in kids]}
                roots = by_parent.get(0, [])
                return [build(r) for r in roots]
            for dep_id, lst in lockers.items():
                depot.append({"depot_id": dep_id, "containers": make_tree(lst)})

    return {"equipment": equipment, "inventory": inventory, "depot": depot}