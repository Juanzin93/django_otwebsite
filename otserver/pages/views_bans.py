# otserver/pages/views.py
from __future__ import annotations
import time, math, struct, socket
from typing import Dict, List, Any, Optional
from django.shortcuts import render
from django.http import HttpRequest
from .db import DB

db = DB()

def _ip_to_str(v: Optional[int]) -> str:
    try:
        if v is None: return ""
        return socket.inet_ntoa(struct.pack("!I", int(v)))
    except Exception:
        return str(v)

def _col(cols: List[str], *cands: str) -> Optional[str]:
    s = set(c.lower() for c in cols)
    for c in cands:
        if c.lower() in s:
            return c
    return None

def _table_exists(name: str) -> bool:
    try:
        return db._table_exists(name)
    except Exception:
        return False

def _columns(name: str) -> List[str]:
    try:
        return db._columns(name)
    except Exception:
        return []

def _now() -> int:
    return int(time.time())

def _gather_bans() -> List[Dict[str, Any]]:
    """
    Returns a unified list:
      { kind: 'account'|'ip'|'player'|'name',
        subject: str,                   # "Account 123", "IP 1.2.3.4", "Player <name>"
        account_id: int|None,
        ip: str|None,
        player_id: int|None,
        reason: str,
        banned_by: str|int|None,
        issued_at: int,
        expires_at: int,                # 0 or None = permanent
        active: bool
      }
    """
    out: List[Dict[str, Any]] = []
    now = _now()

    # --- Schema: split tables ---
    # account_bans
    if _table_exists("account_bans"):
        cols = _columns("account_bans")
        c_account = _col(cols, "account_id", "account")
        c_added   = _col(cols, "added", "time", "banned_at", "created")
        c_expires = _col(cols, "expires", "expires_at", "unban_date", "ban_expires", "ban_end")
        c_reason  = _col(cols, "reason", "comment", "ban_reason", "description")
        c_admin   = _col(cols, "banned_by", "admin_id", "author", "gm")

        sel = [c_account]
        if c_added:   sel.append(f"{c_added} AS issued_at")
        if c_expires: sel.append(f"{c_expires} AS expires_at")
        if c_reason:  sel.append(f"{c_reason} AS reason")
        if c_admin:   sel.append(f"{c_admin} AS banned_by")

        rows = db.run("select", f"SELECT {', '.join(sel)} FROM account_bans")
        for r in rows:
            issued = int(r.get("issued_at") or 0)
            expires = int(r.get("expires_at") or 0)
            active = (expires == 0 or expires is None) or (expires > now)
            out.append({
                "kind": "account",
                "subject": f"Account {r[c_account]}",
                "account_id": int(r[c_account]),
                "ip": None,
                "player_id": None,
                "reason": r.get("reason") or "",
                "banned_by": r.get("banned_by"),
                "issued_at": issued,
                "expires_at": expires or 0,
                "active": bool(active),
            })

    # ip_bans
    if _table_exists("ip_bans"):
        cols = _columns("ip_bans")
        c_ip     = _col(cols, "ip", "ip_addr")
        c_added  = _col(cols, "added", "time", "banned_at", "created")
        c_expires= _col(cols, "expires", "expires_at", "unban_date", "ban_expires", "ban_end")
        c_reason = _col(cols, "reason", "comment", "ban_reason", "description")
        c_admin  = _col(cols, "banned_by", "admin_id", "author", "gm")

        sel = [c_ip]
        if c_added:   sel.append(f"{c_added} AS issued_at")
        if c_expires: sel.append(f"{c_expires} AS expires_at")
        if c_reason:  sel.append(f"{c_reason} AS reason")
        if c_admin:   sel.append(f"{c_admin} AS banned_by")

        rows = db.run("select", f"SELECT {', '.join(sel)} FROM ip_bans")
        for r in rows:
            issued = int(r.get("issued_at") or 0)
            expires = int(r.get("expires_at") or 0)
            active = (expires == 0 or expires is None) or (expires > now)
            ip_str = _ip_to_str(r[c_ip])
            out.append({
                "kind": "ip",
                "subject": f"IP {ip_str}",
                "account_id": None,
                "ip": ip_str,
                "player_id": None,
                "reason": r.get("reason") or "",
                "banned_by": r.get("banned_by"),
                "issued_at": issued,
                "expires_at": expires or 0,
                "active": bool(active),
            })

    # --- Unified "bans" table (older schemas) ---
    if _table_exists("bans"):
        cols = _columns("bans")
        c_type   = _col(cols, "type")
        c_value  = _col(cols, "value")
        c_param  = _col(cols, "param")
        c_added  = _col(cols, "added", "time", "banned_at", "created")
        c_expires= _col(cols, "expires", "expires_at")
        c_reason = _col(cols, "reason", "comment")
        c_admin  = _col(cols, "admin_id", "banned_by", "author")

        sel = []
        for c in (c_type, c_value, c_param):
            if c: sel.append(c)
        if c_added:   sel.append(f"{c_added} AS issued_at")
        if c_expires: sel.append(f"{c_expires} AS expires_at")
        if c_reason:  sel.append(f"{c_reason} AS reason")
        if c_admin:   sel.append(f"{c_admin} AS banned_by")

        if sel:
            rows = db.run("select", f"SELECT {', '.join(sel)} FROM bans")
            for r in rows:
                t = int(r.get(c_type) or 0)
                val = r.get(c_value)
                par = r.get(c_param)
                issued = int(r.get("issued_at") or 0)
                expires = int(r.get("expires_at") or 0)
                active = (expires == 0 or expires is None) or (expires > now)
                reason = r.get("reason") or ""

                if t == 1:  # IP ban
                    ip_str = _ip_to_str(val)
                    subject = f"IP {ip_str}"
                    out.append({
                        "kind": "ip", "subject": subject, "ip": ip_str,
                        "account_id": None, "player_id": None,
                        "reason": reason, "banned_by": r.get("banned_by"),
                        "issued_at": issued, "expires_at": expires or 0, "active": bool(active),
                    })
                elif t == 2:  # Account ban
                    subject = f"Account {val}"
                    out.append({
                        "kind": "account", "subject": subject,
                        "account_id": int(val) if val is not None else None,
                        "ip": None, "player_id": None,
                        "reason": reason, "banned_by": r.get("banned_by"),
                        "issued_at": issued, "expires_at": expires or 0, "active": bool(active),
                    })
                else:
                    # Other types (notation/namelock) – still show
                    subject = f"Type {t} value {val}"
                    out.append({
                        "kind": "other", "subject": subject,
                        "account_id": None, "ip": None, "player_id": None,
                        "reason": reason, "banned_by": r.get("banned_by"),
                        "issued_at": issued, "expires_at": expires or 0, "active": bool(active),
                    })

    # Sort newest first
    out.sort(key=lambda x: x.get("issued_at", 0), reverse=True)
    return out

def bans_list(request: HttpRequest):
    # Filters
    only = request.GET.get("only", "active")   # "active" | "all"
    kind = request.GET.get("type", "all")      # "all"|"account"|"ip"
    q    = (request.GET.get("q") or "").strip()

    data = _gather_bans()

    # Filter by active
    if only == "active":
        data = [r for r in data if r["active"]]

    # Filter by type
    if kind in ("account", "ip"):
        data = [r for r in data if r["kind"] == kind]

    # Search (subject or reason)
    if q:
        ql = q.lower()
        data = [r for r in data if ql in (r["subject"] or "").lower() or ql in (r["reason"] or "").lower()]

    # Paginate (simple)
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    per_page = 25
    total = len(data)
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    start = (page - 1)*per_page
    end = start + per_page
    rows = data[start:end]

    meta = {
        "page": page, "per_page": per_page, "total": total, "total_pages": total_pages,
        "has_prev": page > 1, "has_next": page < total_pages,
    }

    # Preserve querystring w/o page
    qs_items = []
    for k in ("only", "type", "q"):
        v = request.GET.get(k)
        if v:
            from urllib.parse import urlencode
            qs_items.append((k, v))
    querystring = ""
    if qs_items:
        from urllib.parse import urlencode
        querystring = urlencode(qs_items)

    return render(request, "pages/bans.html", {
        "rows": rows,
        "meta": meta,
        "selected": {"only": only, "type": kind, "q": q},
        "querystring": querystring,
    })
