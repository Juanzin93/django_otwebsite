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
OT_PASSWORD_TYPE = getattr(settings, "OT_PASSWORD_TYPE", "sha1")   # "plain" | "sha1" | "md5" | "sha256"
OT_ACCOUNT_TABLE = getattr(settings, "OT_ACCOUNT_TABLE", "accounts")
OT_USERNAME_COL  = getattr(settings, "OT_USERNAME_COL", "id")      # often "id"; if you later add a name column, set it there
OT_PASSWORD_COL  = getattr(settings, "OT_PASSWORD_COL", "password")
OT_EMAIL_COL     = getattr(settings, "OT_EMAIL_COL", "email")      # optional, but required for email login
OT_BLOCKED_COL   = getattr(settings, "OT_BLOCKED_COL", "blocked")  # optional (0/1)


def _check_password(plain: str, stored: str, method: str) -> bool:
    if stored is None:
        return False
    s = stored.strip()
    p = (plain or "").encode("utf-8")
    m = (method or "").lower()

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
    Authenticate against the OT 'accounts' table by numeric id OR email.
    On success, ensures a local Django user exists (username=str(OT id)) so sessions & user.is_authenticated work.
    """

    def authenticate(self, request, username: Optional[str] = None, password: Optional[str] = None, **kwargs):
        if not username or password is None:
            return None

        u = str(username).strip()
        by_id = u.isdigit()
        by_email = ("@" in u) and bool(OT_EMAIL_COL)

        # Only accept id or email (no username column in OT).
        if not (by_id or by_email):
            return None

        # Build WHERE and params safely (no LOWER() around numeric id)
        where_parts = []
        params = {}

        if by_id:
            where_parts.append("id = :id")
            params["id"] = int(u)

        if by_email:
            where_parts.append(f"LOWER({OT_EMAIL_COL}) = LOWER(:email)")
            params["email"] = u

        # SELECT pieces
        # Provide a 'uname' column: if OT_USERNAME_COL == 'id', synthesize as CAST(id AS CHAR)
        uname_select = (
            "CAST(id AS CHAR) AS uname"
            if OT_USERNAME_COL == "id"
            else f"{OT_USERNAME_COL} AS uname"
        )

        db = DB(alias=OT_DB_ALIAS)
        row = db.run(
            "select_one",
            f"""
            SELECT
                id,
                {uname_select},
                {OT_PASSWORD_COL} AS upass,
                {OT_EMAIL_COL} AS uemail
            FROM {OT_ACCOUNT_TABLE}
            WHERE {" OR ".join(where_parts)}
            LIMIT 1
            """,
            params,
        )
        if not row:
            return None

        # Verify password against configured hash type
        if not _check_password(password, str(row.get("upass") or ""), OT_PASSWORD_TYPE):
            return None

        # Map to local Django user:
        # - username = OT numeric id as string (stable & unique)
        # - keep email in sync if provided
        ot_id = row["id"]
        uname = str(ot_id)  # always use id as Django username
        email = row.get("uemail") or ""

        user, created = User.objects.get_or_create(username=uname, defaults={"email": email})
        if not created and email and user.email != email:
            user.email = email
            user.save(update_fields=["email"])

        # Store convenience fields in the session
        if request is not None:
            request.session["ot_account_id"] = ot_id
            request.session["ot_account_name"] = uname  # id as name, since OT has no username

        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
