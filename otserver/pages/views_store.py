import json, os, time
from dataclasses import dataclass
from typing import List, Dict, Optional
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import stripe

from .db import DB
db = DB()

stripe.api_key = settings.STRIPE_API_KEY

# ---------- Config: coin packs ----------
@dataclass
class Pack:
    id: str
    coins: int
    price_usd: str
    price_brl: Optional[str] = None
    bonus: Optional[int] = None
    stripe_price_usd: Optional[str] = None
    stripe_price_brl: Optional[str] = None

# Example packs; map to your Stripe Price IDs
PACKS: List[Pack] = [
    Pack("25",   25,  "5.00",   "25.00",  bonus=0,  stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C25"),   stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C25")),
    Pack("50",   50,  "10.00",  "50.00",  bonus=0,  stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C50"),   stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C50")),
    Pack("100",  100, "20.00",  "100.00", bonus=0,  stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C100"),  stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C100")),
    Pack("250",  250, "50.00",  "250.00", bonus=0,  stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C250"),  stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C250")),
    Pack("550",  550, "100.00", "500.00", bonus=0,  stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C550"),  stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C550")),
    Pack("1100", 1100,"200.00", "1000.00",bonus=10, stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C1100"), stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C1100")),
]

def _pack_by_id(pid:str)->Optional[Pack]:
    for p in PACKS:
        if p.id == pid:
            return p
    return None

# ---------- Items for depot delivery ----------
# (A) If you’re linking from TinyMCE to /buy/item/<actionid>, we map actionid -> price ids here:
ITEM_PRICES_BY_AID: Dict[str, Dict[str, str]] = {
    # actionid: { price_usd, price_brl }
    "58008": {"price_usd": "price_1SIv0RP5F3OJyKcMv7HQpvDy", "price_brl": "price_1SIuziP5F3OJyKcMukAbzvlq"},
    "58007": {"price_usd": "price_1SIv4SP5F3OJyKcMuf1c7ujK", "price_brl": "price_1SIv2uP5F3OJyKcMAqYzKHT3"},
    "58006": {"price_usd": "price_1SIvCnP5F3OJyKcMCYcCITTh", "price_brl": "price_1SIvDFP5F3OJyKcMAU8DXifx"},
}

# (B) If you sell via Stripe Payment Links, map *price id* -> delivery spec:
ITEM_SPECS_BY_PRICE: Dict[str, Dict[str, int]] = {
    # price_id: {itemid, actionid, count, town_id}
    "price_1SIv0RP5F3OJyKcMv7HQpvDy": {"itemid": 5837, "actionid": 58008, "count": 1, "town_id": 1},
    "price_1SIuziP5F3OJyKcMukAbzvlq": {"itemid": 5837, "actionid": 58008, "count": 1, "town_id": 1},
    "price_1SIv4SP5F3OJyKcMuf1c7ujK": {"itemid": 5837, "actionid": 58007, "count": 1, "town_id": 1},
    "price_1SIv2uP5F3OJyKcMAqYzKHT3": {"itemid": 5837, "actionid": 58007, "count": 1, "town_id": 1},
    "price_1SIvCnP5F3OJyKcMCYcCITTh": {"itemid": 5837, "actionid": 58006, "count": 1, "town_id": 1},
    "price_1SIvDFP5F3OJyKcMAU8DXifx": {"itemid": 5837, "actionid": 58006, "count": 1, "town_id": 1},
}

DEFAULT_TOWN_ID = 1  # Thais

def _queue_depot_item(account_id: int, itemid: int, actionid: int, count: int, town_id: int, txid: str, method: str, player_name: Optional[str] = None):
    now = int(time.time())
    # Insert once per (txid, actionid) thanks to UNIQUE(txid, actionid)
    db.run("execute", """
        INSERT INTO store_orders (account_id, player_name, itemid, actionid, count, town_id, method, txid, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
        ON DUPLICATE KEY UPDATE txid = txid
    """, [account_id, player_name, itemid, actionid, count, town_id, method, txid, now])

# ---------- Helpers ----------
def _credit_coins(account_id: int, coins: int, txid: str, method: str):
    """
    Idempotent credit:
      - Insert into coin_tx first with UNIQUE(method, external_id)
      - Only if the INSERT actually created a row, bump accounts.coins
    """
    now = int(time.time())
    inserted = db.run("execute", """
        INSERT INTO coin_tx (account_id, coins, method, external_id, created_at)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE external_id = external_id
    """, [account_id, coins, method, txid, now])

    if inserted and inserted > 0:
        db.run("execute", """
            UPDATE accounts
               SET coins = COALESCE(coins, 0) + %s
             WHERE id = %s
        """, [coins, account_id])

# ---------- Donate page (coins only; no character name) ----------
@login_required
def donate(request):
    acc_email = request.user.email
    acc_id = request.user.username
    if not acc_id:
        return HttpResponseBadRequest(json.dumps({"error":"Account not linked id"}), content_type="application/json")

    currency = request.GET.get("currency", "USD").upper()
    currency = "BRL" if currency == "BRL" else "USD"
    packs = []
    for p in PACKS:
        packs.append({
            "id": p.id,
            "coins": p.coins,
            "price_usd": p.price_usd,
            "price_brl": p.price_brl,
            "bonus": p.bonus,
        })
    ctx = {
        "packs": packs,
        "currency": currency,
        "STRIPE_PUBLIC_KEY": getattr(settings, "STRIPE_PUBLIC_KEY", None),
        "STRIPE_PIX_ENABLED": bool(getattr(settings, "STRIPE_PIX_ENABLED", False)),
        "PAYPAL_CLIENT_ID": getattr(settings, "PAYPAL_CLIENT_ID", None),
        "PIX_KEY": getattr(settings, "PIX_KEY", None),
        "PIX_QR_IMAGE": getattr(settings, "PIX_QR_IMAGE", None),
        "acc_id": acc_id,
        "acc_email": acc_email,
    }
    return render(request, "pages/donate.html", ctx)

# ---------- Coins: Stripe Checkout (unchanged; NO character name) ----------
@login_required
def create_checkout_session(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    try:
        payload = json.loads(request.body.decode())
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    pack_id = payload.get("pack")
    currency = (payload.get("currency") or "USD").upper()
    currency = "BRL" if currency == "BRL" else "USD"

    pack = _pack_by_id(pack_id)
    if not pack:
        return HttpResponseBadRequest(json.dumps({"error": "Unknown pack"}), content_type="application/json")

    # choose price by currency
    price_id = pack.stripe_price_brl if currency == "BRL" else pack.stripe_price_usd
    if not price_id:
        return HttpResponseBadRequest(json.dumps({"error": "Stripe price not configured"}), content_type="application/json")

    acc_id = request.user.username
    if not acc_id:
        return HttpResponseBadRequest(json.dumps({"error":"Account not linked"}), content_type="application/json")

    # Offer PIX in BRL if enabled
    pm_types = ["card"]
    if currency == "BRL" and getattr(settings, "STRIPE_PIX_ENABLED", False):
        pm_types = ["card", "pix"]

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=pm_types,
        line_items=[{ "price": price_id, "quantity": 1 }],
        success_url=request.build_absolute_uri(reverse("store_success")),
        cancel_url=request.build_absolute_uri(reverse("store_cancel")),
        metadata={
            "user_id": str(request.user.id),
            "ot_account_id": int(acc_id),
            "pack_id": pack.id,
            "coins": str(pack.coins),
            "currency": currency,
            # NOTE: no player_name for coins
        }
    )
    return JsonResponse({"id": session.id})

# ---------- Items: landing page that asks for Character Name ----------
ITEM_NAME: Dict[str, str] = {
    "58008": "Retrowar Pack Tier 1",
    "58007": "Retrowar Pack Tier 2",
    "58006": "Retrowar Pack Tier 3",
}

STARTER_AIDS = (58008, 58007, 58006)

def _account_already_bought_starter(account_id: int) -> bool:
    """
    Returns True if this account has already purchased a starter pack.
    We consider any existing store_orders row for starter actionids
    with status pending or delivered as 'already bought'.
    """
    row = db.run("select_one", """
        SELECT *
          FROM store_orders
         WHERE account_id = %s
    """, [account_id])

    print("DB check already bought starter:", row)
    print("DB check already bought starter (account_id):", account_id)
    return bool(row)

@login_required
@require_http_methods(["GET", "POST"])
def buy_item_landing(request, aid: str):
    """
    TinyMCE links to /buy/item/<aid>
    GET  -> show form (character name + currency select), but disable if already bought
    POST -> create Stripe Checkout Session using chosen currency (only if not already bought)
    """
    # normalize currency (GET preselect)
    preselect_currency = (request.GET.get("currency") or "USD").upper()
    if preselect_currency not in ("USD", "BRL"):
        preselect_currency = "USD"

    acc_id = request.user.username
    already_bought = _account_already_bought_starter(int(acc_id))
    print("Already bought?", already_bought)

    if request.method == "GET":
        return render(request, "pages/buy_item_landing.html", {
            "aid": aid,
            "title": f"Buy {ITEM_NAME[aid]}",
            "currency": preselect_currency,
            "submit_label": "Continue to payment",
            "already_bought": already_bought,
        })

    # POST
    if already_bought:
        # Double-check on POST to avoid race conditions
        return HttpResponseForbidden("This account has already purchased a starter pack.")

    player_name = (request.POST.get("player_name") or "").strip()
    currency    = (request.POST.get("currency") or "USD").upper()
    if not player_name:
        return HttpResponseBadRequest("Missing character name")
    if currency not in ("USD", "BRL"):
        return HttpResponseBadRequest("Invalid currency")

    mapping = ITEM_PRICES_BY_AID.get(str(aid))
    if not mapping:
        return HttpResponseBadRequest("Unknown item/actionid")

    price_id = mapping["price_brl"] if currency == "BRL" else mapping["price_usd"]
    if not price_id:
        return HttpResponseBadRequest("Stripe price not configured")

    pm_types = ["card"]
    if currency == "BRL" and getattr(settings, "STRIPE_PIX_ENABLED", False):
        pm_types = ["card", "pix"]

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=pm_types,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=request.build_absolute_uri(reverse("store_success")),
        cancel_url=request.build_absolute_uri(reverse("store_cancel")),
        metadata={
            "user_id": str(request.user.id),
            "ot_account_id": int(acc_id),
            "currency": currency,
            "player_name": player_name,   # item-only
            "actionid": str(aid),
            "town_id": str(DEFAULT_TOWN_ID),
        },
    )
    return redirect(session.url, permanent=False)

# ---------- Stripe webhook ----------
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig = request.headers.get("Stripe-Signature", "")
    endpoint_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    try:
        event = stripe.Webhook.construct_event(payload, sig, endpoint_secret) if endpoint_secret else json.loads(payload.decode())
    except Exception:
        return HttpResponse(status=400)

    if event.get("type") in ("checkout.session.completed",):
        session = event["data"]["object"]

        # Expand to get line_items -> price ids (when permitted)
        try:
            session_full = stripe.checkout.Session.retrieve(session["id"], expand=["line_items.data.price"])
        except Exception:
            session_full = session

        md = session.get("metadata", {}) or {}
        txid = session.get("id") or session.get("payment_intent") or f"stripe:{int(time.time())}"

        # 1) Coins (no character name)
        acc_id = None
        coins  = 0
        try:
            # Prefer explicit ot_account_id, else fall back to user_id
            raw_acc = md.get("ot_account_id") or md.get("user_id")
            acc_id = int(raw_acc) if raw_acc is not None else None
            coins  = int(md.get("coins") or 0)
        except Exception:
            acc_id, coins = None, 0
        if acc_id and coins > 0:
            _credit_coins(acc_id, coins, txid, method="stripe")
        # 2) Items (require character name when coming from /buy/item/..., but also support price-id mapping)
        # 2a) If metadata includes actionid (our landing flow), use it directly
        actionid = None
        try:
            actionid = int(md.get("actionid") or 0)
        except Exception:
            actionid = 0

        if acc_id and actionid:
            player_name = (md.get("player_name") or "").strip() or None
            town_id = int(md.get("town_id") or DEFAULT_TOWN_ID)

            # Resolve itemid/count via ITEM_SPECS_BY_PRICE if price present; else fallback to a default per actionid
            itemid, count = None, 1
            # Try to infer from the price id (if we can read it)
            try:
                line_items = (session_full.get("line_items") or {}).get("data") or []
                for li in line_items:
                    price = None
                    if isinstance(li.get("price"), dict):
                        price = li["price"].get("id")
                    price = price or li.get("price") or (li.get("plan") or {}).get("id")
                    if price and price in ITEM_SPECS_BY_PRICE:
                        spec = ITEM_SPECS_BY_PRICE[price]
                        itemid = int(spec["itemid"])
                        count  = int(spec.get("count", 1))
                        break
            except Exception:
                pass

            # Fallback: if we didn’t map via price, set a default itemid you sell with these actionids
            if not itemid:
                itemid = 5837  # <— default itemid used for 58008/58007/58006; change if needed

            _queue_depot_item(
                account_id=acc_id,
                itemid=itemid,
                actionid=actionid,
                count=count,
                town_id=town_id,
                txid=txid,
                method="stripe",
                player_name=player_name
            )

        # 2b) If there is no metadata.actionid (e.g., pure Payment Link flow), try to map by price id:
        elif acc_id:
            try:
                line_items = (session_full.get("line_items") or {}).get("data") or []
                for li in line_items:
                    price = None
                    if isinstance(li.get("price"), dict):
                        price = li["price"].get("id")
                    price = price or li.get("price") or (li.get("plan") or {}).get("id")

                    if price in ITEM_SPECS_BY_PRICE:
                        spec = ITEM_SPECS_BY_PRICE[price]
                        # If player_name not provided, leave NULL -> any character on account can pick it up
                        player_name = (md.get("player_name") or "").strip() or None
                        _queue_depot_item(
                            account_id=acc_id,
                            itemid=int(spec["itemid"]),
                            actionid=int(spec["actionid"]),
                            count=int(spec.get("count", 1)),
                            town_id=int(spec.get("town_id", DEFAULT_TOWN_ID)),
                            txid=txid,
                            method="stripe",
                            player_name=player_name
                        )
            except Exception:
                pass

    elif event.get("type") == "payment_intent.succeeded":
        # covers PIX if you ever use PaymentIntents directly (not needed when using Checkout)
        pass

    return HttpResponse(status=200)

# ---------- PayPal (coins only here; unchanged) ----------
import base64, requests

def _paypal_token() -> Optional[str]:
    cid = getattr(settings, "PAYPAL_CLIENT_ID", None)
    sec = getattr(settings, "PAYPAL_SECRET", None)
    if not (cid and sec): return None
    env = getattr(settings, "PAYPAL_ENV", "sandbox")
    host = "https://api-m.sandbox.paypal.com" if env != "live" else "https://api-m.paypal.com"
    r = requests.post(
        host + "/v1/oauth2/token",
        headers={"Accept": "application/json"},
        data={"grant_type": "client_credentials"},
        auth=(cid, sec),
        timeout=15,
    )
    if r.ok:
        return r.json().get("access_token")
    return None

@login_required
def paypal_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    data = json.loads(request.body.decode())
    pack_id = data.get("pack")
    currency = (data.get("currency") or "USD").upper()
    amount = str(data.get("amount") or "0.00")
    pack = _pack_by_id(pack_id)
    if not pack:
        return HttpResponseBadRequest(json.dumps({"error":"Bad pack"}), content_type="application/json")
    acc_id = request.user.username
    if not acc_id:
        return HttpResponseBadRequest(json.dumps({"error":"Account not linked"}), content_type="application/json")

    token = _paypal_token()
    if not token:
        return HttpResponseBadRequest(json.dumps({"error":"PayPal not configured"}), content_type="application/json")

    env = getattr(settings, "PAYPAL_ENV", "sandbox")
    host = "https://api-m.sandbox.paypal.com" if env != "live" else "https://api-m.paypal.com"

    r = requests.post(
        host + "/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}", "Content-Type":"application/json"},
        json={
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": pack.id,
                "amount": {"currency_code": currency, "value": amount},
                "custom_id": f"acc:{acc_id}:coins:{pack.coins}"
            }],
            "application_context": {
                "shipping_preference": "NO_SHIPPING",
                "brand_name": getattr(settings, "SITE_NAME", "Retrowar"),
                "user_action": "PAY_NOW",
                "return_url": request.build_absolute_uri(reverse("store_success")),
                "cancel_url": request.build_absolute_uri(reverse("store_cancel")),
            }
        },
        timeout=20
    )
    if not r.ok:
        return HttpResponseBadRequest(json.dumps({"error":"PayPal create failed"}), content_type="application/json")
    return JsonResponse({"id": r.json()["id"]})

@login_required
def paypal_capture(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    data = json.loads(request.body.decode())
    order_id = data.get("orderID")
    token = _paypal_token()
    if not (order_id and token):
        return JsonResponse({"ok": False, "error": "Missing"}, status=400)

    env = getattr(settings, "PAYPAL_ENV", "sandbox")
    host = "https://api-m.sandbox.paypal.com" if env != "live" else "https://api-m.paypal.com"

    r = requests.post(
        host + f"/v2/checkout/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {token}", "Content-Type":"application/json"},
        timeout=20
    )
    if not r.ok:
        return JsonResponse({"ok": False, "error": "Capture failed"}, status=400)

    j = r.json()
    status = j.get("status")
    try:
        pu = (j.get("purchase_units") or [])[0]
        ref = pu.get("reference_id")
        custom = pu.get("payments",{}).get("captures",[{}])[0].get("custom_id") or pu.get("custom_id")
        parts = (custom or "").split(":")
        acc_id = int(parts[1]) if len(parts) >= 4 else request.user.username
        coins  = int(parts[3]) if len(parts) >= 4 else (_pack_by_id(ref).coins if _pack_by_id(ref) else 0)
    except Exception:
        acc_id, coins = request.user.username, 0

    if status == "COMPLETED" and acc_id and coins:
        _credit_coins(acc_id, coins, order_id, method="paypal")
        return JsonResponse({"ok": True})
    return JsonResponse({"ok": False, "error": "Not completed"}, status=400)

# ---------- Result pages ----------

def store_success(request):
    return render(request, "pages/store_success.html")

def store_cancel(request):
    return render(request, "pages/store_cancel.html")
