# pages/views_pix.py
import json, time, os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .views_store import _pack_by_id, _credit_coins
from .db import DB
from .pix_providers import create_pix_charge, PixError

db = DB()

@login_required
def pix_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    try:
        body = json.loads(request.body.decode())
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    pack_id = body.get("pack")
    pack = _pack_by_id(pack_id)
    if not pack:
        return JsonResponse({"error":"Unknown pack"}, status=400)

    acc_id = request.user.username
    if not acc_id:
        return JsonResponse({"error":"Account not linked"}, status=400)

    provider = os.getenv("PIX_PROVIDER","mercadopago").lower()
    amount_brl = pack.price_brl or pack.price_usd  # your UX shows BRL on PIX
    amount_cents = int(round(float(amount_brl.replace(",", ".")) * 100))
    tx_ref = f"acc:{acc_id}|pack:{pack.id}|coins:{pack.coins}|ts:{int(time.time())}"

    try:
        info = create_pix_charge(
            provider,
            amount_cents=amount_cents,
            description=f"Coins {pack.coins}",
            tx_ref=tx_ref,
            payer_email=request.user.email or "no-email@localhost",
        )
    except PixError as e:
        return JsonResponse({"error": str(e)}, status=400)

    # Persist for reconciliation/idempotency
    db.run("execute", """
        INSERT INTO pix_tx (txid, account_id, pack_id, coins, amount, currency,
                            provider, status, qr_emv, qr_base64, external_id,
                            created_at, expires_at)
        VALUES (%s,%s,%s,%s,%s,'BRL',%s,'pending',%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE status=VALUES(status), qr_emv=VALUES(qr_emv),
                                qr_base64=VALUES(qr_base64), expires_at=VALUES(expires_at)
    """, [info["txid"], acc_id, pack.id, pack.coins, amount_cents,
          provider, info.get("qr_emv"), info.get("qr_base64"),
          info.get("external_id"), int(time.time()), info.get("expires_at")])

    return JsonResponse({
        "txid": info["txid"],
        "emv": info.get("qr_emv"),
        "qr_base64": info.get("qr_base64"),           # data:image/png;base64,...
        "expires_at": info.get("expires_at"),
        "poll_url": reverse("pix_status", args=[info["txid"]]),
    })


@login_required
def pix_status(request, txid: str):
    row = db.run("select_one", "SELECT status FROM pix_tx WHERE txid=%s", [txid])
    if not row:
        return JsonResponse({"error":"not found"}, status=404)
    return JsonResponse({"status": row["status"]})


@csrf_exempt
def pix_webhook(request):
    provider = os.getenv("PIX_PROVIDER","mercadopago").lower()

    try:
        payload = json.loads(request.body.decode())
    except Exception:
        return HttpResponse(status=400)

    if provider == "efi":
        # Efí webhook body example:
        # { "pix": [ { "endToEndId":"...", "txid":"...", "valor":"10.00", "chave":"...", "horario":"..." } ] }
        pix_list = payload.get("pix") or []
        for p in pix_list:
            txid = p.get("txid")
            if not txid:
                continue
            # Mark paid if pending
            changed = db.run("execute", """
                UPDATE pix_tx SET status='paid'
                WHERE txid=%s AND status <> 'paid'
            """, [txid])

            if changed and changed > 0:
                # find account/coins and credit idempotently
                row = db.run("select_one", "SELECT account_id, coins FROM pix_tx WHERE txid=%s", [txid])
                if row:
                    _credit_coins(row["account_id"], row["coins"], txid=txid, method="pix")
        return HttpResponse(status=200)

    return HttpResponse(status=200)
