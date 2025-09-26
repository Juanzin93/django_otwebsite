import json, os, time
from dataclasses import dataclass
from typing import List, Dict, Optional
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .db import DB
db = DB()

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
    Pack("25",  25, "5.00",  "25.00",  bonus=0,  stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C25"),  stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C25")),
    Pack("50",  50, "10.00", "50.00",  bonus=0, stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C50"),  stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C50")),
    Pack("100",100, "20.00", "100.00", bonus=0, stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C100"), stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C100")),
    Pack("250",200,"50.00", "250.00", bonus=0, stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C250"), stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C250")),
    Pack("550",550,"100.00", "500.00", bonus=0, stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C550"), stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C550")),
    Pack("1100",1100,"200.00", "1000.00", bonus=10, stripe_price_usd=os.getenv("STRIPE_PRICE_USD_C1100"), stripe_price_brl=os.getenv("STRIPE_PRICE_BRL_C1100")),
]

def _pack_by_id(pid:str)->Optional[Pack]:
    for p in PACKS:
        if p.id == pid:
            return p
    return None

# ---------- Helpers ----------
def _ot_account_id(user) -> Optional[int]:
    # your project already stores this on user.profile.ot_account_id
    prof = getattr(user, "profile", None)
    return getattr(prof, "ot_account_id", None)

def _credit_coins(account_id: int, coins: int, txid: str, method: str):
    """
    Idempotent credit:
      - Insert into coin_tx first with UNIQUE(method, external_id)
      - Only if the INSERT actually created a row, bump accounts.coins
    """
    now = int(time.time())

    # Try to record the transaction; ON DUPLICATE keeps it idempotent.
    inserted = db.run("execute", """
        INSERT INTO coin_tx (account_id, coins, method, external_id, created_at)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE external_id = external_id
    """, [account_id, coins, method, txid, now])

    # db.run("execute", ...) returns an int rowcount in your DB helper.
    # If rowcount > 0, the insert happened (not a duplicate), so credit the account.
    if inserted and inserted > 0:
        db.run("execute", """
            UPDATE accounts
               SET coins = COALESCE(coins, 0) + %s
             WHERE id = %s
        """, [coins, account_id])

# ---------- Donate page ----------
@login_required
def donate(request):
    acc_email = request.user.email
    acc_id = request.user.username
    if not acc_id:
        return HttpResponseBadRequest(json.dumps({"error":"Account not linked"}), content_type="application/json")
    
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

# ---------- Stripe ----------
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

    import stripe
    stripe.api_key = settings.STRIPE_API_KEY

    # choose price by currency
    price_id = pack.stripe_price_brl if currency == "BRL" else pack.stripe_price_usd
    if not price_id:
        return HttpResponseBadRequest(json.dumps({"error": "Stripe price not configured"}), content_type="application/json")

    acc_id = _ot_account_id(request.user)
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
            "ot_account_id": str(acc_id),
            "pack_id": pack.id,
            "coins": str(pack.coins),
            "currency": currency,
        }
    )
    return JsonResponse({"id": session.id})

@csrf_exempt
def stripe_webhook(request):
    import stripe
    stripe.api_key = settings.STRIPE_API_KEY
    payload = request.body
    sig = request.headers.get("Stripe-Signature", "")
    endpoint_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    try:
        event = stripe.Webhook.construct_event(payload, sig, endpoint_secret) if endpoint_secret else json.loads(payload.decode())
    except Exception as e:
        return HttpResponse(status=400)

    if event.get("type") in ("checkout.session.completed",):
        session = event["data"]["object"]
        md = session.get("metadata", {}) or {}
        try:
            acc_id = int(md.get("ot_account_id"))
            coins  = int(md.get("coins"))
            txid   = session.get("id")
        except Exception:
            return HttpResponse(status=200)  # ignore quietly
        _credit_coins(acc_id, coins, txid, method="stripe")
    elif event.get("type") == "payment_intent.succeeded":
        # covers PIX if you use PaymentIntents directly; Checkout already handled above
        pass

    return HttpResponse(status=200)

# ---------- PayPal (simple capture) ----------
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
    acc_id = _ot_account_id(request.user)
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
        # pull pack/coins from purchase unit
        pu = (j.get("purchase_units") or [])[0]
        ref = pu.get("reference_id")  # our pack.id
        custom = pu.get("payments",{}).get("captures",[{}])[0].get("custom_id") or pu.get("custom_id")
        # custom_id format acc:123:coins:250
        parts = (custom or "").split(":")
        acc_id = int(parts[1]) if len(parts) >= 4 else _ot_account_id(request.user)
        coins  = int(parts[3]) if len(parts) >= 4 else (_pack_by_id(ref).coins if _pack_by_id(ref) else 0)
    except Exception:
        acc_id, coins = _ot_account_id(request.user), 0

    if status == "COMPLETED" and acc_id and coins:
        _credit_coins(acc_id, coins, order_id, method="paypal")
        return JsonResponse({"ok": True})
    return JsonResponse({"ok": False, "error": "Not completed"}, status=400)

# ---------- Result pages ----------
@login_required
def store_success(request):
    return render(request, "pages/store_success.html")

@login_required
def store_cancel(request):
    return render(request, "pages/store_cancel.html")
