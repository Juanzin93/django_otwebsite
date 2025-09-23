# pages/mail_backends.py
import base64
import logging
import os
from typing import Iterable, Optional

import msal
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage, EmailMultiAlternatives

logger = logging.getLogger(__name__)

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
GRAPH_BASE  = "https://graph.microsoft.com/v1.0"

class GraphEmailBackend(BaseEmailBackend):
    """
    Django email backend that sends via Microsoft Graph sendMail (app-only).
    Uses: /users/{sender}/sendMail with saveToSentItems=True
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.tenant  = getattr(settings, "GRAPH_TENANT_ID", None)
        self.client  = getattr(settings, "GRAPH_CLIENT_ID", None)
        self.secret  = getattr(settings, "GRAPH_CLIENT_SECRET", None)
        self.sender  = getattr(settings, "GRAPH_SENDER", None)

        missing = [k for k, v in {
            "GRAPH_TENANT_ID": self.tenant,
            "GRAPH_CLIENT_ID": self.client,
            "GRAPH_CLIENT_SECRET": self.secret,
            "GRAPH_SENDER": self.sender,
        }.items() if not v]
        if missing:
            raise RuntimeError(f"GraphEmailBackend misconfigured; missing: {', '.join(missing)}")

        # MSAL confidential client
        self._msal_app = msal.ConfidentialClientApplication(
            client_id=self.client,
            authority=f"https://login.microsoftonline.com/{self.tenant}",
            client_credential=self.secret,
        )

    # --- Django API ---
    def open(self):
        return True

    def close(self):
        return

    def send_messages(self, email_messages: Iterable[EmailMessage]) -> int:
        sent = 0
        for msg in email_messages or []:
            try:
                self._send_one(msg)
                sent += 1
            except Exception as e:
                if not self.fail_silently:
                    raise
                logger.error("Graph sendMail error: %s", e, exc_info=True)
        return sent

    # --- internals ---
    def _get_token(self) -> str:
        # Try cache first; msal keeps an in-memory cache per app instance
        result = self._msal_app.acquire_token_silent(GRAPH_SCOPE, account=None)
        if not result:
            result = self._msal_app.acquire_token_for_client(scopes=GRAPH_SCOPE)
        if "access_token" not in result:
            raise RuntimeError(f"Token error: {result.get('error')} {result.get('error_description')}")
        return result["access_token"]

    def _send_one(self, msg: EmailMessage) -> None:
        token = self._get_token()
        endpoint = f"{GRAPH_BASE}/users/{self.sender}/sendMail"

        # Subject
        subject = msg.subject or ""

        # Body (prefer HTML alternative if present)
        content_type = "Text"
        body = msg.body or ""
        if isinstance(msg, EmailMultiAlternatives) and msg.alternatives:
            # Pick first html alternative if any
            for alt_body, alt_mime in msg.alternatives:
                if alt_mime.lower() in ("text/html", "text/x-html", "application/xhtml+xml"):
                    body = alt_body
                    content_type = "HTML"
                    break
        elif getattr(msg, "content_subtype", "") == "html":
            content_type = "HTML"

        # Recipients
        to_list  = list(msg.to or [])
        cc_list  = list(msg.cc or [])
        bcc_list = list(msg.bcc or [])
        reply_to = list(msg.reply_to or [])

        def _addr_list(addrs):
            return [{"emailAddress": {"address": a}} for a in addrs]

        # Attachments
        attachments = []
        for att in (msg.attachments or []):
            # att can be (filename, content, mimetype) OR an object with .name/.content/.mimetype
            if isinstance(att, (list, tuple)) and len(att) >= 2:
                filename, content = att[0], att[1]
                mimetype = att[2] if len(att) >= 3 and att[2] else "application/octet-stream"
            else:
                # fallback best-effort
                filename = getattr(att, "name", "attachment.bin")
                content  = getattr(att, "content", b"")
                mimetype = getattr(att, "mimetype", "application/octet-stream")

            if isinstance(content, str):
                content = content.encode("utf-8")
            b64 = base64.b64encode(content).decode("ascii")
            attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentType": mimetype,
                "contentBytes": b64,
            })

        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": content_type, "content": body},
                "from":   {"emailAddress": {"address": self.sender}},
                "sender": {"emailAddress": {"address": self.sender}},
                "toRecipients":  _addr_list(to_list),
                "ccRecipients":  _addr_list(cc_list),
                "bccRecipients": _addr_list(bcc_list),
                "attachments": attachments,
            },
            "saveToSentItems": True,
        }

        if reply_to:
            payload["message"]["replyTo"] = _addr_list(reply_to)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        r = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        logger.info("Graph sendMail -> %s", r.status_code)
        if r.status_code != 202:
            # include minimal response text for debugging (no secrets leaked)
            raise RuntimeError(f"Graph sendMail failed: {r.status_code} {r.text}")
