# pages/pix_providers.py
import os, time, json, base64, requests
from typing import Optional, Tuple

class PixError(Exception): ...
class _EfiSession:
    """
    Handles OAuth + mTLS for Efí (Gerencianet) PIX API.
    """
    def __init__(self):
        env = (os.getenv("EFI_ENV") or "production").lower()
        self.base = "https://api-pix.efi.com.br" if env == "production" else "https://api-pix-h.gerencianet.com.br"
        self.client_id = os.getenv("EFI_CLIENT_ID") or ""
        self.client_secret = os.getenv("EFI_CLIENT_SECRET") or ""
        if not self.client_id or not self.client_secret:
            raise PixError("Efí credentials missing")

        self.cert_path = os.getenv("EFI_PIX_CERT_PATH") or ""
        self.key_path  = os.getenv("EFI_PIX_KEY_PATH") or ""       # optional if using .p12
        self.cert_pass = os.getenv("EFI_PIX_CERT_PASS") or None

        # requests "cert" can be (certfile, keyfile) or single path for p12 is not directly supported.
        # For p12, we rely on system openssl->converted PEM, or use urllib3 with SSLContext.
        # Simplest: convert your .p12 to PEM pair once and point to both files.
        if not self.cert_path:
            raise PixError("Efí PIX certificate path missing (EFI_PIX_CERT_PATH)")
        # We'll support PEM pair out of the box:
        if not self.key_path:
            # Assume cert_path is a PEM that also contains private key (rare) – requests will accept a single file.
            self.cert_tuple = self.cert_path
        else:
            self.cert_tuple = (self.cert_path, self.key_path)

        self._token = None
        self._token_exp = 0

    def _auth(self):
        if self._token and time.time() < self._token_exp - 60:
            return self._token

        url = self.base + "/oauth/token"
        # Basic auth with client_id:client_secret
        auth = (self.client_id, self.client_secret)
        data = {"grant_type": "client_credentials"}
        # Efí requires mTLS on token too
        r = requests.post(url, auth=auth, data=data, cert=self.cert_tuple, timeout=20)
        if not r.ok:
            raise PixError(f"Efí OAuth failed: {r.status_code} {r.text[:300]}")
        j = r.json()
        self._token = j["access_token"]
        self._token_exp = time.time() + int(j.get("expires_in", 600))
        return self._token

    def _headers(self) -> dict:
        tok = self._auth()
        return {
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
        }

    def create_cob(self, *, txid: str, chave: str, amount_cents: int, description: str, expir_secs: int = 1800) -> dict:
        """
        Create a dynamic charge (cob) with a txid you chose (max 35 chars).
        Returns JSON with loc.id, txid, exp, etc.
        """
        url = self.base + f"/v2/cob/{txid}"
        json_body = {
            "calendario": {"expiracao": expir_secs},
            "devedor": {},            # optional (individual/company) – omitted
            "valor": {"original": f"{amount_cents/100:.2f}"},
            "chave": chave,           # your PIX key (receiver)
            "solicitacaoPagador": description[:140],
        }
        r = requests.put(url, headers=self._headers(), json=json_body, cert=self.cert_tuple, timeout=20)
        if r.status_code not in (200, 201):
            raise PixError(f"Efí /cob failed: {r.status_code} {r.text[:300]}")
        return r.json()

    def get_qrcode(self, loc_id: int) -> dict:
        url = self.base + f"/v2/loc/{loc_id}/qrcode"
        r = requests.get(url, headers=self._headers(), cert=self.cert_tuple, timeout=20)
        if not r.ok:
            raise PixError(f"Efí /qrcode failed: {r.status_code} {r.text[:300]}")
        return r.json()

def create_pix_charge(provider: str, *, amount_cents: int, description: str, tx_ref: str,
                      payer_email: Optional[str] = None) -> dict:
    """
    Provider-agnostic interface. For Efí:
      - Create COB with a generated txid (<=35 chars, a-zA-Z0-9)
      - Fetch QR code (emv + base64)
      - Return: txid, external_id (loc.id), qr_emv, qr_base64, expires_at
    """
    if provider != "efi":
        raise PixError("Unsupported provider for this function")

    sess = _EfiSession()
    chave = os.getenv("EFI_PIX_KEY") or ""
    if not chave:
        raise PixError("EFI_PIX_KEY (your receiving PIX key) not set")

    # Build a txid compatible with specs (up to 35, alnum & certain chars; keep it simple alnum)
    # include a short hash from tx_ref to ensure uniqueness
    import hashlib, re
    h = hashlib.sha1(tx_ref.encode("utf-8")).hexdigest()[:10]
    base = re.sub(r"[^A-Za-z0-9]", "", f"rw{h}{int(time.time())}")[:20]
    txid = base  # <= 35 is fine

    cob = sess.create_cob(
        txid=txid,
        chave=chave,
        amount_cents=amount_cents,
        description=description,
        expir_secs=30*60,
    )
    loc_id = int(cob["loc"]["id"])
    q = sess.get_qrcode(loc_id)
    # Efí returns { "qrcode": "data:image/png;base64,...", "imagemQrcode": "...", "textoImagem": "EMV..." }
    qr_base64 = None
    img = q.get("imagemQrcode") or q.get("qrcode")
    if img and img.startswith("data:image"):
        # strip header
        try:
            qr_base64 = img.split(",", 1)[1]
        except Exception:
            qr_base64 = None

    emv = q.get("qrcode") or q.get("textoImagem") or q.get("emv") or ""
    expires_at = int(time.time()) + int(cob.get("calendario", {}).get("expiracao", 1800))

    return {
        "txid": txid,
        "external_id": str(loc_id),     # we’ll store loc_id too
        "qr_emv": emv,
        "qr_base64": qr_base64,
        "expires_at": expires_at,
    }
