# pages/db.py
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union
import re
import json
import time

from django.http import JsonResponse, Http404
from django.conf import settings
from django.db import connections, transaction
from django.db.utils import OperationalError, InterfaceError

ParamMap = Mapping[str, Any]
Params   = Union[Sequence[Any], ParamMap, None]

OT_DB_ALIAS: str = getattr(settings, "OT_DB_ALIAS", "retrowar")

# -------- utilities --------
def _now() -> int:
    return int(time.time())

def wallet_ensure(self, account_id: int) -> None:
    now = _now()
    self.run("execute",
        "INSERT INTO coins_wallet (account_id,balance,created_at,updated_at) "
        "VALUES (%s,0,%s,%s) ON DUPLICATE KEY UPDATE updated_at=VALUES(updated_at)",
        [account_id, now, now])

def wallet_balance(self, account_id: int) -> int:
    row = self.run("select_one", "SELECT balance FROM coins_wallet WHERE account_id=%s", [account_id])
    if not row:
        return 0
    return int(row["balance"])

def wallet_delta(self, account_id: int, delta: int, kind: str, ref: str = None, note: str = None) -> None:
    """Atomic balance update with ledger row."""
    now = _now()
    with self.atomic():
        self.wallet_ensure(account_id)
        # Update balance
        self.run("execute",
            "UPDATE coins_wallet SET balance=balance+%s, updated_at=%s WHERE account_id=%s",
            [delta, now, account_id])
        # Ledger row
        self.run("execute",
            "INSERT INTO coins_ledger (account_id, delta, kind, ref, note, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            [account_id, delta, kind, ref, note, now])

def hold_create(self, offer_id: int, account_id: int, amount: int) -> int:
    """Create an active hold: debit coins from bidder and park them on the offer."""
    now = _now()
    ref = f"offer:{offer_id}"
    with self.atomic():
        bal = self.wallet_balance(account_id)
        if bal < amount:
            raise ValueError("Insufficient coins")
        # debit
        self.wallet_delta(account_id, -int(amount), "hold", ref=ref)
        # create hold
        self.run("execute",
            "INSERT INTO bazaar_holds (offer_id, account_id, amount, active, created_at) "
            "VALUES (%s,%s,%s,1,%s)", [offer_id, account_id, amount, now])
        # return new id
        row = self.run("select_one", "SELECT LAST_INSERT_ID() AS id", [])
        return int(row["id"])

def hold_get_active(self, offer_id: int):
    return self.run("select_one",
        "SELECT * FROM bazaar_holds WHERE offer_id=%s AND active=1", [offer_id])

def hold_release(self, hold_id: int) -> None:
    """Release an active hold back to the bidder."""
    now = _now()
    hold = self.run("select_one", "SELECT * FROM bazaar_holds WHERE id=%s AND active=1", [hold_id])
    if not hold:  # nothing to do
        return
    ref = f"offer:{hold['offer_id']}"
    with self.atomic():
        # mark inactive
        self.run("execute", "UPDATE bazaar_holds SET active=0, released_at=%s WHERE id=%s", [now, hold_id])
        # refund
        self.wallet_delta(hold["account_id"], int(hold["amount"]), "release", ref=ref)

def hold_settle_to_seller(self, hold_id: int, seller_account_id: int, *, fee_bps: int = 0, fee_account_id: int = 1) -> None:
    """
    Move the held amount to the seller (minus fee). Marks hold inactive.
    fee_bps = basis points (100 = 1%).
    """
    now = _now()
    hold = self.run("select_one", "SELECT * FROM bazaar_holds WHERE id=%s AND active=1", [hold_id])
    if not hold:
        return
    amount = int(hold["amount"])
    fee = (amount * int(fee_bps)) // 10_000 if fee_bps > 0 else 0
    net = amount - fee
    ref = f"offer:{hold['offer_id']}"
    with self.atomic():
        # deactivate hold
        self.run("execute", "UPDATE bazaar_holds SET active=0, released_at=%s WHERE id=%s", [now, hold_id])
        # settle to seller
        self.wallet_delta(seller_account_id, net, "settle", ref=ref)
        if fee > 0:
            self.wallet_delta(fee_account_id, fee, "fee", ref=ref)

def _rows_as_dicts(cur) -> List[Dict[str, Any]]:
    cols = [c[0] for c in (cur.description or [])]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

_named_re = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")

def _bind(sql: str, params: Params) -> Tuple[str, List[Any]]:
    """
    Allow both positional params and named params in SQL.
    - If params is a list/tuple: assumed '%s' placeholders in sql.
    - If params is a dict: replace :name in sql with %s and map values.
    """
    if params is None:
        return sql, []
    if isinstance(params, (list, tuple)):
        return sql, list(params)
    if isinstance(params, Mapping):
        names: List[str] = []
        def repl(m: re.Match) -> str:
            names.append(m.group(1))
            return "%s"
        sql2 = _named_re.sub(repl, sql)
        args = [params[name] for name in names]
        return sql2, args
    raise TypeError("params must be list/tuple/dict/None")

def _should_retry(exc: Exception) -> bool:
    """
    Retry on common transient MySQL errors.
    PyMySQL/Connector usually put numeric code in exc.args[0].
    """
    if not isinstance(exc, (OperationalError, InterfaceError)):
        return False
    code = None
    if getattr(exc, "args", None):
        try:
            code = int(exc.args[0])
        except Exception:
            code = None
    # Lost connection / server gone / lock timeout / deadlock
    return code in {2006, 2013, 1205, 1213}

@dataclass
class PageMeta:
    page: int
    per_page: int
    total: int
    total_pages: int
    has_prev: bool
    has_next: bool
    start_index: int

# -------- main helper --------

class DB:
    """
    One-stop DB helper.

    db.run(kind, sql, params, **opts)
      kind: "select" | "select_one" | "scalar" | "execute" | "paginate"
      params: list/tuple OR dict using :named params in SQL.

    Examples:
      rows = db.run("select", "SELECT * FROM players WHERE level >= :min", {"min": 8})
      one  = db.run("select_one", "SELECT * FROM accounts WHERE id=:id", {"id": 42})
      val  = db.run("scalar", "SELECT COUNT(*) FROM players")
      n    = db.run("execute", "UPDATE players SET level=level+1 WHERE name=:n", {"n":"Bob"})
      rows, meta = db.run("paginate", "SELECT * FROM players", {}, order_by="experience DESC", page=2, per_page=50)

    Also has builder helpers:
      insert(table, data) -> int rowcount
      update(table, data, where) -> int rowcount
      delete(table, where) -> int rowcount
      select(table, columns='*', where=None, order_by=None, limit=None, offset=None) -> rows
    """
    def __init__(self, alias: Optional[str] = None, *, retries: int = 1, backoff: float = 0.25) -> None:
        self.alias = alias or OT_DB_ALIAS
        self.retries = max(0, int(retries))
        self.backoff = max(0.0, float(backoff))

    @contextmanager
    def cursor(self):
        cur = connections[self.alias].cursor()
        try:
            yield cur
        finally:
            cur.close()

    @contextmanager
    def atomic(self):
        with transaction.atomic(using=self.alias):
            yield self

    # ---------- public: single entrypoint ----------

    def run(
        self,
        kind: str,
        sql: str,
        params: Params = None,
        *,
        order_by: str = "",
        page: int = 1,
        per_page: int = 25,
    ):
        kind = kind.lower().strip()
        if kind == "paginate":
            return self._paginate(sql, params, order_by=order_by, page=page, per_page=per_page)
        if kind == "select":
            return self._select(sql, params)
        if kind == "select_one":
            return self._select_one(sql, params)
        if kind == "scalar":
            return self._scalar(sql, params)
        if kind == "execute":
            return self._execute(sql, params)
        raise ValueError(f"Unknown kind: {kind}")

    # ---------- core ops (with retry & binding) ----------

    def _execute(self, sql: str, params: Params = None) -> int:
        sql2, args = _bind(sql, params)
        attempt = 0
        while True:
            try:
                with self.cursor() as cur:
                    cur.execute(sql2, args)
                    return cur.rowcount
            except Exception as e:
                if attempt < self.retries and _should_retry(e):
                    attempt += 1; time.sleep(self.backoff * attempt); continue
                raise

    def _select(self, sql: str, params: Params = None) -> List[Dict[str, Any]]:
        sql2, args = _bind(sql, params)
        attempt = 0
        while True:
            try:
                with self.cursor() as cur:
                    cur.execute(sql2, args)
                    return _rows_as_dicts(cur)
            except Exception as e:
                if attempt < self.retries and _should_retry(e):
                    attempt += 1; time.sleep(self.backoff * attempt); continue
                raise

    def _select_one(self, sql: str, params: Params = None, default: Any = None) -> Any:
        rows = self._select(sql, params)
        return rows[0] if rows else default

    def _scalar(self, sql: str, params: Params = None, default: Any = None) -> Any:
        sql2, args = _bind(sql, params)
        attempt = 0
        while True:
            try:
                with self.cursor() as cur:
                    cur.execute(sql2, args)
                    row = cur.fetchone()
                return (row[0] if row else default)
            except Exception as e:
                if attempt < self.retries and _should_retry(e):
                    attempt += 1; time.sleep(self.backoff * attempt); continue
                raise

    def _paginate(
        self,
        base_sql: str,
        params: Params = None,
        *,
        order_by: str = "",
        page: int = 1,
        per_page: int = 25,
    ) -> Tuple[List[Dict[str, Any]], PageMeta]:
        page = max(1, int(page))
        per_page = max(1, int(per_page))

        # Bind once for the COUNT subquery (same params).
        base_bound_sql, base_args = _bind(base_sql, params)

        total = self._scalar(f"SELECT COUNT(*) FROM ({base_bound_sql}) sub", base_args, default=0)
        offset = (page - 1) * per_page

        sql = base_bound_sql
        if order_by:
            sql += f" ORDER BY {order_by}"
        sql += " LIMIT %s OFFSET %s"
        rows = self._select(sql, list(base_args) + [per_page, offset])

        total_pages = max(1, (total + per_page - 1) // per_page)
        meta = PageMeta(
            page=page, per_page=per_page, total=total, total_pages=total_pages,
            has_prev=page > 1, has_next=page < total_pages, start_index=offset + 1
        )
        return rows, meta.__dict__
    
    def _table_exists(self, name: str) -> bool:
        return bool(self.run(
        "scalar",
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :t",
        {"t": name}
    ))

    def _columns(self, name: str) -> List[str]:
        rows = self.run("select", f"SHOW COLUMNS FROM {name}")
        return [r["Field"] for r in rows]

    def _has_column(self, table: str, col: str) -> bool:
        return bool(self.run(
            "scalar",
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c",
            {"t": table, "c": col}
        ))

    def _detect_depot_schema(self):
        """
        Returns dict like:
        {"table": "...", "mode": "new"/"legacy", "id_col": "depot_id" or None}
        Tries common table/column names used by different TFS/OT forks.
        """
        # common table name variants across versions/forks
        candidates = ["players_depotitems", "player_depotitems", "player_depot_items"]
        table = next((t for t in candidates if self._table_exists(t)), None)
        if not table:
            return None

        # new schemas: depot_id or depotid
        if self._has_column(table, "depot_id"):
            return {"table": table, "mode": "new", "id_col": "depot_id"}
        if self._has_column(table, "depotid"):
            return {"table": table, "mode": "new", "id_col": "depotid"}

        # legacy 7.4 schema (no depot_id; uses container tree via pid/sid)
        return {"table": table, "mode": "legacy", "id_col": None}
    
    def _detect_items_schema(self):
        """
        Find the inventory/equipment table and which column carries the slot.
        Many 7.4 schemas: table `player_items` with `pid` 1..10 for equipment.
        Newer forks: sometimes `slot` column exists.
        Returns: {"table": ..., "mode": "slot"|"pid", "slot_col": "slot"|"pid"}
        """
        candidates = ["player_items", "players_items", "playeritems"]
        table = next((t for t in candidates if self._table_exists(t)), None)
        if not table:
            return None

        if self._has_column(table, "slot"):
            return {"table": table, "mode": "slot", "slot_col": "slot"}
        # legacy fallback
        return {"table": table, "mode": "pid", "slot_col": "pid"}

    
    def _detect_items_table(self):
        """
        Return dict with usable columns. We only require: pid, sid, itemtype, count, attributes.
        Also determine the player id column ('player_id' or 'playerid').
        """
        for t in ("player_items", "players_items", "playeritems"):
            if not self._table_exists(t):
                continue
            # find player id column
            pcol = "player_id" if self._has_column(t, "player_id") else ("playerid" if self._has_column(t, "playerid") else None)
            if not pcol:
                continue
            required = ["pid", "sid", "itemtype"]
            if not all(self._has_column(t, c) for c in required):
                continue
            # optional but very common
            count_col = "count" if self._has_column(t, "count") else None
            attr_col  = "attributes" if self._has_column(t, "attributes") else None
            return {"table": t, "player_col": pcol, "count_col": count_col, "attr_col": attr_col}
        return None

    def _hex_bytes(self, val):
        if isinstance(val, (bytes, bytearray)):
            return val.hex()
        return val
    
    def _to_hex_or_none(self, val):
        if isinstance(val, (bytes, bytearray)):
            return val.hex() if val else None
        return val
    
    def _encode_item(self, row, count_col, attr_col):
        d = {
            "pid": int(row["pid"]),
            "sid": int(row["sid"]),
            "itemtype": int(row["itemtype"]),
            "count": int(row.get(count_col) or 1) if count_col else 1,
            "attributes_hex": self._hex_bytes(row.get(attr_col)) if attr_col else None,
        }
        return d


    def _get_player_id(self, name: str) -> int:
        row = self.run("select_one", "SELECT id FROM players WHERE name = :n", {"n": name})
        if not row:
            raise Http404("No such character")
        return row["id"] if isinstance(row, dict) else row[0]
    
    # inside class DB
    def json(self, data):
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


    # ---------- convenience builders (optional) ----------

    def insert(self, table: str, data: Mapping[str, Any]) -> int:
        cols = list(data.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        return self._execute(sql, [data[c] for c in cols])

    def update(self, table: str, data: Mapping[str, Any], where: Mapping[str, Any]) -> int:
        set_sql = ", ".join([f"{k}=%s" for k in data.keys()])
        w_sql, w_args = self._where_clause(where)
        sql = f"UPDATE {table} SET {set_sql} WHERE {w_sql}"
        return self._execute(sql, list(data.values()) + w_args)

    def delete(self, table: str, where: Mapping[str, Any]) -> int:
        w_sql, w_args = self._where_clause(where)
        return self._execute(f"DELETE FROM {table} WHERE {w_sql}", w_args)

    def select(
        self,
        table: str,
        columns: Union[str, Sequence[str]] = "*",
        where: Optional[Mapping[str, Any]] = None,
        order_by: str = "",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        cols = columns if isinstance(columns, str) else ", ".join(columns)
        sql = f"SELECT {cols} FROM {table}"
        args: List[Any] = []
        if where:
            w_sql, w_args = self._where_clause(where)
            sql += f" WHERE {w_sql}"
            args += w_args
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += " LIMIT %s"; args.append(int(limit))
        if offset is not None:
            sql += " OFFSET %s"; args.append(int(offset))
        return self._select(sql, args)

    # where builder supports __in, __gte, __lte, __gt, __lt, __ne, __like
    def _where_clause(self, where: Mapping[str, Any]) -> Tuple[str, List[Any]]:
        parts: List[str] = []
        args: List[Any] = []
        for key, val in where.items():
            if "__" in key:
                field, op = key.split("__", 1)
                if op == "in":
                    vals = list(val) if not isinstance(val, (list, tuple)) else list(val)
                    if not vals:
                        parts.append("1=0")  # empty IN -> no matches
                    else:
                        ph = ", ".join(["%s"] * len(vals))
                        parts.append(f"{field} IN ({ph})")
                        args.extend(vals)
                elif op == "gte":
                    parts.append(f"{field} >= %s"); args.append(val)
                elif op == "lte":
                    parts.append(f"{field} <= %s"); args.append(val)
                elif op == "gt":
                    parts.append(f"{field} > %s"); args.append(val)
                elif op == "lt":
                    parts.append(f"{field} < %s"); args.append(val)
                elif op == "ne":
                    parts.append(f"{field} <> %s"); args.append(val)
                elif op == "like":
                    parts.append(f"{field} LIKE %s"); args.append(val)
                else:
                    raise ValueError(f"Unsupported where operator: {op}")
            else:
                parts.append(f"{key} = %s"); args.append(val)
        return " AND ".join(parts) if parts else "1=1", args
