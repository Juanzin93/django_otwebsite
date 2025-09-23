# pages/management/commands/bazaar_close.py
from django.core.management.base import BaseCommand
from time import time
from pages.db import DB
from django.conf import settings


FEE_BPS = getattr(settings, "BAZAAR_FEE_BPS", 100)
FEE_ACCT = getattr(settings, "BAZAAR_FEE_ACCOUNT_ID", 1)

class Command(BaseCommand):
    help = "Close ended bazaar auctions (settle coins or release holds)."

    def handle(self, *args, **kwargs):
        db = DB()
        now = int(time())
        ended = db.run("select",
            "SELECT * FROM bazaar_offers WHERE status='active' AND end_time<=%s", [now])
        closed = 0

        for o in ended:
            active = db.hold_get_active(o["id"])
            if o["current_bidder_account_id"] and active:
                # sold -> settle to seller
                db.hold_settle_to_seller(active["id"], int(o["seller_account_id"]),
                                         fee_bps=FEE_BPS, fee_account_id=FEE_ACCT)
                db.run("execute",
                    "UPDATE bazaar_offers SET status='sold', updated_at=%s WHERE id=%s",
                    [now, o["id"]])
            else:
                # no winning bidder -> release any hold and mark expired
                if active:
                    db.hold_release(active["id"])
                db.run("execute",
                    "UPDATE bazaar_offers SET status='expired', updated_at=%s WHERE id=%s",
                    [now, o["id"]])
            closed += 1

        self.stdout.write(f"Closed {closed} auctions.")