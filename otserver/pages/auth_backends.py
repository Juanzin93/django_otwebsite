# pages/auth_backends.py
from __future__ import annotations
import hashlib
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from .db import DB, OT_DB_ALIAS

User = get_user_model()

# Configure these in settings.py (defaults here as fallbacks)
OT_PASSWORD_TYPE = getattr(settings, "OT_PASSWORD_TYPE", "sha1")  # "plain" | "sha1" | "md5" | "sha256"
OT_ACCOUNT_TABLE = getattr(settings, "OT_ACCOUNT_TABLE", "accounts")
OT_USERNAME_COL  = getattr(settings, "OT_USERNAME_COL", "name")   # sometimes "name" or "account"
OT_PASSWORD_COL  = getattr(settings, "OT_PASSWORD_COL", "password")
OT_EMAIL_COL     = getattr(settings, "OT_EMAIL_COL", "email")     # optional
OT_BLOCKED_COL   = getattr(settings, "OT_BLOCKED_COL", "blocked") # optional (0/1)

def _check_password(plain: str, stored: str, method: str) -> bool:
    if stored is None:
        return False
    s = stored.strip()
    p = (plain or "").encode("utf-8")
    m = method.lower()
    if m == "plain":
        return s == plain
    if m == "sha1":
        return hashlib.sha1(p).hexdigest().lower() == s.lower()
    if m == "md5":
        return hashlib.md5(p).hexdigest().lower() == s.lower()
    if m == "sha256":
        return hashlib.sha256(p).hexdigest().lower() == s.lower()

    # Fallback: try common formats automatically if method unknown
    for fn in (hashlib.sha1, hashlib.md5, hashlib.sha256):
        if fn(p).hexdigest().lower() == s.lower():
            return True
    return s == plain

class OTAccountBackend(BaseBackend):
    """
    Authenticates against the OT server 'accounts' table (in MySQL).
    On success, ensures a local Django user exists (for sessions and is_authenticated).
    """

    def authenticate(self, request, username: Optional[str] = None, password: Optional[str] = None, **kwargs):
        if not username or password is None:
            return None

        db = DB(alias=OT_DB_ALIAS)

        # Try case-insensitive match on account name.
        row = db.run(
            "select_one",
            f"""
            SELECT id, {OT_USERNAME_COL} AS uname, {OT_PASSWORD_COL} AS upass,
                   {OT_EMAIL_COL} AS uemail
              FROM {OT_ACCOUNT_TABLE}
             WHERE LOWER({OT_USERNAME_COL}) = LOWER(:u)
             LIMIT 1
            """,
            {"u": username},
        )
        if not row:
            return None

        # Blocked?
        if "ublocked" in row and row["ublocked"] not in (None, 0, "0", False):
            return None

        if not _check_password(password, str(row.get("upass") or ""), OT_PASSWORD_TYPE):
            return None

        # Create or update the Django user
        uname = row["uname"]
        email = row.get("uemail") or ""
        user, created = User.objects.get_or_create(username=uname, defaults={"email": email})
        if not created:
            # Keep email in sync (optional)
            if email and user.email != email:
                user.email = email
                user.save(update_fields=["email"])

        # Store OT account id on the session for convenience
        if request is not None:
            request.session["ot_account_id"] = row["id"]
            request.session["ot_account_name"] = uname

        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
