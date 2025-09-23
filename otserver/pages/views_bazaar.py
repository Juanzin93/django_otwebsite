# pages/views_bazaar.py
from time import time
from math import ceil
from django.http import JsonResponse, Http404, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .snapshots import _character_snapshot
from .db import DB
from .views import _get_acc_id_from_user, _is_player_online


db = DB()

def _now() -> int:
    return int(time())

def bazaar_list(request):
    # filters
    q = request.GET.copy()
    voc = q.get("vocation", "all")
    minlvl = max(1, int(q.get("minlvl", "1") or 1))
    maxlvl = max(minlvl, int(q.get("maxlvl", "999") or 999))
    order = q.get("order", "ending")  # ending|level|price

    where = ["status='active'", "level BETWEEN %s AND %s"]
    args = [minlvl, maxlvl]
    if voc != "all":
        where.append("vocation=%s")
        args.append(int(voc))

    order_sql = {
        "ending": "end_time ASC",
        "level":  "level DESC, end_time ASC",
        "price":  "COALESCE(current_bid, min_bid) ASC, end_time ASC",
    }.get(order, "end_time ASC")

    base = f"""
      SELECT id, player_id, player_name, level, vocation, sex,
             looktype, lookhead, lookbody, looklegs, lookfeet,
             min_bid, buyout, current_bid, end_time
        FROM bazaar_offers
       WHERE {" AND ".join(where)}
    """
    page = int(q.get("page", "1") or 1)
    rows, meta = db.run("paginate", base, args, order_by=order_sql, page=page, per_page=20)

    return render(request, "pages/bazaar_list.html", {
        "offers": rows,
        "page_meta": meta,
        "selected": {"vocation": voc, "minlvl": minlvl, "maxlvl": maxlvl, "order": order},
        "querystring": "&".join([f"{k}={v}" for k, v in q.items() if k != "page"]),
    })

def bazaar_offer(request, offer_id: int):
    offer = db.run("select_one", "SELECT * FROM bazaar_offers WHERE id=%s", [offer_id])
    if not offer:
        raise Http404("Offer not found")

    # bids
    bids = db.run("select",
        "SELECT bidder_account_id, amount, created_at FROM bazaar_bids WHERE offer_id=%s ORDER BY amount DESC, id DESC",
        [offer_id]
    )

    return render(request, "pages/bazaar_offer.html", {
        "o": offer,
        "bids": bids,
        "now": _now(),
    })

FEE_BPS = getattr(settings, "BAZAAR_FEE_BPS", 100)  # 100 = 1%
FEE_ACCT = getattr(settings, "BAZAAR_FEE_ACCOUNT_ID", 1)

@login_required
@require_POST
def bazaar_bid(request, offer_id: int):
    action = request.POST.get("action", "bid")  # 'bid' or 'buyout'
    try:
        amount = int(request.POST.get("amount", "0") or 0)
    except ValueError:
        return HttpResponseBadRequest("Bad amount.")

    offer = db.run("select_one", "SELECT * FROM bazaar_offers WHERE id=%s AND status='active'", [offer_id])
    if not offer:
        raise Http404("Offer not found")

    now = _now()
    if now >= offer["end_time"]:
        return HttpResponseBadRequest("Auction ended.")

    bidder_acc = getattr(getattr(request.user, "profile", None), "ot_account_id", None)
    if not bidder_acc:
        return HttpResponseBadRequest("No linked OT account.")

    # BUYOUT path
    if action == "buyout":
        if not offer["buyout"]:
            return HttpResponseBadRequest("Buyout not available.")
        # you must have >= buyout coins
        try:
            with db.atomic():
                # release previous hold if any
                active = db.hold_get_active(offer_id)
                if active:
                    db.hold_release(active["id"])
                # create hold for full buyout
                hid = db.hold_create(offer_id, bidder_acc, int(offer["buyout"]))
                # settle immediately to seller (fee applied)
                db.hold_settle_to_seller(hid, int(offer["seller_account_id"]), fee_bps=FEE_BPS, fee_account_id=FEE_ACCT)
                # finalize offer
                db.run("execute",
                    "UPDATE bazaar_offers SET status='sold', current_bid=%s, current_bidder_account_id=%s, updated_at=%s, end_time=%s WHERE id=%s",
                    [offer["buyout"], bidder_acc, now, now, offer_id])
        except ValueError as e:
            return HttpResponseBadRequest(str(e))
        return redirect("bazaar_offer", offer_id=offer_id)

    # BID path
    min_allowed = max(offer["min_bid"], (offer["current_bid"] or 0) + 1)
    if amount < min_allowed:
        return HttpResponseBadRequest(f"Bid must be ≥ {min_allowed} coins")

    try:
        with db.atomic():
            # release previous hold (previous highest bidder)
            active = db.hold_get_active(offer_id)
            if active:
                db.hold_release(active["id"])

            # place new bid & hold bidder's coins
            hid = db.hold_create(offer_id, bidder_acc, amount)
            db.run("execute",
                   "INSERT INTO bazaar_bids (offer_id, bidder_account_id, amount, created_at) VALUES (%s,%s,%s,%s)",
                   [offer_id, bidder_acc, amount, now])
            db.run("execute",
                   "UPDATE bazaar_offers SET current_bid=%s, current_bidder_account_id=%s, updated_at=%s WHERE id=%s",
                   [amount, bidder_acc, now, offer_id])
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

    return redirect("bazaar_offer", offer_id=offer_id)

@login_required
def bazaar_sell(request):
    acc_id = _get_acc_id_from_user(request.user)
    if not acc_id:
        return HttpResponseBadRequest("Your web account is not linked to an OT account.")

    if request.method == "POST":
        print("POST keys:", list(request.POST.keys()))
        def parse_int(name, *, required=False, default=None, minv=None, maxv=None):
            raw = request.POST.get(name, "")
            if raw == "":
                if required:
                    raise ValueError(f"Missing {name}")
                return default
            try:
                val = int(raw)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid {name}")
            if minv is not None and val < minv: val = minv
            if maxv is not None and val > maxv: val = maxv
            return val

        try:
            pid     = parse_int("player_id", required=True)
            min_bid = parse_int("min_bid",  required=True, minv=1)
            buyout  = parse_int("buyout",   required=False, default=0, minv=0)
            hours   = parse_int("hours",    required=False, default=24, minv=1, maxv=168)
        except ValueError as e:
            return HttpResponseBadRequest(str(e))

        # verify ownership + offline
        owner = db.run("scalar", "SELECT account_id FROM players WHERE id=%s", [pid])
        if not owner or int(owner) != int(acc_id):
            return HttpResponseBadRequest("Not your character.")
        if _is_player_online(pid):
            return HttpResponseBadRequest("Character must be offline.")

        # snapshot & base data
        p = db.run("select_one", "SELECT * FROM players WHERE id=%s", [pid])
        if not p:
            return HttpResponseBadRequest("Character not found.")
        snap = _character_snapshot(pid)
        now  = _now()
        end  = now + hours * 3600

        db.run("execute", """
          INSERT INTO bazaar_offers
          (player_id, player_name, seller_account_id, status,
           start_time, end_time, min_bid, buyout, current_bid,
           level, vocation, sex, looktype, lookhead, lookbody, looklegs, lookfeet,
           equipment_json, inventory_json, depot_json, comment, created_at, updated_at)
          VALUES
          (%s,%s,%s,'active',%s,%s,%s,%s,NULL,
           %s,%s,%s,%s,%s,%s,%s,%s,
           %s,%s,%s,%s,%s,%s)
        """, [
           p["id"], p["name"], acc_id, now, end, min_bid, (buyout or None),
           p["level"], p["vocation"], p["sex"], p["looktype"], p["lookhead"], p["lookbody"], p["looklegs"], p["lookfeet"],
           db.json(snap["equipment"]), db.json(snap["inventory"]), db.json(snap["depot"]),
           (request.POST.get("comment") or "").strip(), now, now
        ])

        return redirect("bazaar_list")

    # GET: show seller’s characters (must include id for the form)
    chars = db.run(
        "select",
        "SELECT id, name, level, vocation FROM players WHERE account_id=%s ORDER BY name ASC",
        [_get_acc_id_from_user(request.user)] if acc_id else [-1]
    )
    return render(request, "pages/bazaar_sell.html", {"chars": chars})