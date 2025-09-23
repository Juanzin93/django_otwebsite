from __future__ import annotations
from typing import Dict, Any, List, Tuple, DefaultDict
from collections import defaultdict

from .db import DB

# Slot map used by most TFS-like schemas (pid for inventory slots)
SLOT_NAMES = {
    1: "head", 2: "necklace", 3: "backpack", 4: "armor",
    5: "right", 6: "left", 7: "legs", 8: "feet",
    9: "ring", 10: "ammo",
}

def _fetch_equipment_rows(db: DB, player_id: int) -> List[Dict[str, Any]]:
    sql = """
      SELECT pid, sid, itemtype, `count`
        FROM player_items
       WHERE player_id = :pid AND pid BETWEEN 1 AND 10
       ORDER BY pid ASC
    """
    return db.run("select", sql, {"pid": player_id})

def _fetch_children(db: DB, player_id: int, parent_sid: int) -> List[Dict[str, Any]]:
    # Items inside a container have pid = parent's sid
    sql = """
      SELECT pid, sid, itemtype, `count`
        FROM player_items
       WHERE player_id = :pid AND pid = :parent_sid
       ORDER BY sid ASC
    """
    return db.run("select", sql, {"pid": player_id, "parent_sid": parent_sid})

def _build_container_tree(db: DB, player_id: int, root_sid: int,
                          *, max_depth: int = 6, max_nodes: int = 5000) -> Dict[str, Any]:
    """
    Builds a nested container tree by following pid = parent.sid relationships.
    We treat an item as a container iff it has children rows.
    """
    visited = set()
    nodes = 0

    def walk(sid: int, depth: int) -> Dict[str, Any]:
        nonlocal nodes
        if depth > max_depth or nodes >= max_nodes or sid in visited:
            return {"sid": sid, "items": []}
        visited.add(sid)
        children = _fetch_children(db, player_id, sid)
        out = []
        for ch in children:
            nodes += 1
            child_sid = int(ch["sid"])
            # detect “container” by presence of its own children
            grand = _fetch_children(db, player_id, child_sid)
            if grand:
                out.append({
                    "sid": child_sid,
                    "itemtype": int(ch["itemtype"]),
                    "count": int(ch.get("count") or 0),
                    "items": walk(child_sid, depth + 1)["items"],
                })
            else:
                out.append({
                    "sid": child_sid,
                    "itemtype": int(ch["itemtype"]),
                    "count": int(ch.get("count") or 0),
                })
            if nodes >= max_nodes:
                break
        return {"sid": sid, "items": out}

    return walk(root_sid, 0)

def get_player_id(db: DB, name: str) -> int | None:
    row = db.run("select_one", "SELECT id FROM players WHERE name = :n", {"n": name})
    return int(row["id"]) if row else None

def get_equipment(db: DB, player_id: int) -> Dict[str, Dict[str, int]]:
    """
    Returns { slot_name: {sid, itemtype, count}, ... }
    """
    rows = _fetch_equipment_rows(db, player_id)
    eq: Dict[str, Dict[str, int]] = {}
    for r in rows:
        pid = int(r["pid"])
        slot = SLOT_NAMES.get(pid, f"slot{pid}")
        eq[slot] = {
            "sid": int(r["sid"]),
            "itemtype": int(r["itemtype"]),
            "count": int(r.get("count") or 0),
        }
    return eq

def get_backpack_tree(db: DB, player_id: int) -> Dict[str, Any] | None:
    """
    Finds the backpack (pid=3), and returns nested items inside it.
    """
    row = db.run("select_one",
                 "SELECT sid, itemtype, `count` FROM player_items WHERE player_id=:pid AND pid=3 LIMIT 1",
                 {"pid": player_id})
    if not row:
        return None
    root_sid = int(row["sid"])
    tree = _build_container_tree(db, player_id, root_sid)
    return {
        "root": {"sid": root_sid, "itemtype": int(row["itemtype"]), "count": int(row.get("count") or 0)},
        "items": tree["items"],
    }

# ----- Depot (two common variants) -----
# Most forks use player_depotitems with same pid/sid scheme.
# Some also have player_depotlocker marking top-level containers.
# The generic approach below builds a forest from player_depotitems.

def _fetch_depot_items(db: DB, player_id: int) -> List[Dict[str, Any]]:
    # If your table name differs, adjust here.
    # Common columns: player_id, depot_id (optional), pid, sid, itemtype, count, attributes
    sql = """
      SELECT COALESCE(depot_id, 0) AS depot_id, pid, sid, itemtype, `count`
        FROM player_depotitems
       WHERE player_id = :pid
       ORDER BY depot_id ASC, pid ASC, sid ASC
    """
    return db.run("select", sql, {"pid": player_id})

def get_depot_forest(db: DB, player_id: int, *, max_depth: int = 8, max_nodes: int = 10000):
    """
    Builds depot trees per depot_id. Root nodes have pid=0 (common schema).
    If your schema differs, adapt the root detection below.
    """
    rows = _fetch_depot_items(db, player_id)
    by_pid: DefaultDict[Tuple[int, int], List[Dict[str, Any]]] = defaultdict(list)
    # key: (depot_id, pid)
    for r in rows:
        depot_id = int(r.get("depot_id") or 0)
        by_pid[(depot_id, int(r["pid"]))].append(r)

    def build(depot_id: int, sid: int, depth: int, nodes_ref) -> Dict[str, Any]:
        if depth > max_depth or nodes_ref[0] >= max_nodes:
            return {"sid": sid, "items": []}
        children = by_pid.get((depot_id, sid), [])
        out = []
        for ch in children:
            nodes_ref[0] += 1
            child_sid = int(ch["sid"])
            out.append({
                "sid": child_sid,
                "itemtype": int(ch["itemtype"]),
                "count": int(ch.get("count") or 0),
                "items": build(depot_id, child_sid, depth + 1, nodes_ref)["items"],
            })
            if nodes_ref[0] >= max_nodes:
                break
        return {"sid": sid, "items": out}

    # Roots usually have pid=0
    roots = []
    nodes_ref = [0]
    for r in by_pid.get((0, 0), []) + sum([by_pid.get((dep, 0), []) for dep in sorted({int(x.get("depot_id") or 0) for x in rows})], []):
        depot_id = int(r.get("depot_id") or 0)
        root_sid = int(r["sid"])
        roots.append({
            "depot_id": depot_id,
            "root": {"sid": root_sid, "itemtype": int(r["itemtype"]), "count": int(r.get("count") or 0)},
            "items": build(depot_id, root_sid, 0, nodes_ref)["items"],
        })
    return roots or []  # list of depot trees
