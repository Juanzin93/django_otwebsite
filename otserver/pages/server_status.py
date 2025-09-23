# pages/server_status.py
import socket
import time
import select
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Tuple, Optional

# --- Status protocol constants ---
# Client -> Server (binary status)
P_REQ = 0x01

# Flags
REQ_PLAYERS_INFO     = 0x0008  # counts
REQ_EXT_PLAYERS_INFO = 0x0020  # online list

# Server -> Client blocks
R_PLAYERS_COUNTS = 0x20  # [u32 online][u32 max][u32 peak]
R_PLAYERS_LIST   = 0x21  # [u32 count] { [u16 len][name][u32 level] }*count


# ----------------- low-level helpers -----------------

def _recv_exact(sock: socket.socket, n: int, deadline: float) -> bytes:
    """Read exactly n bytes or b'' on timeout/close."""
    buf = bytearray()
    while len(buf) < n:
        remain = deadline - time.time()
        if remain <= 0:
            return b""
        r, _, _ = select.select([sock], [], [], min(0.25, remain))
        if not r:
            continue
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return b""
        buf.extend(chunk)
    return bytes(buf)

def _recv_until_idle(sock: socket.socket, deadline: float, idle: float = 0.25, cap: int = 1_048_576) -> bytes:
    """Read until `idle` seconds of no data or deadline; best-effort."""
    sock.setblocking(False)
    data = bytearray()
    last = time.time()
    while time.time() < deadline and len(data) < cap:
        timeout = min(idle, max(0.0, deadline - time.time()))
        r, _, _ = select.select([sock], [], [], timeout)
        if r:
            chunk = sock.recv(8192)
            if not chunk:
                break
            data.extend(chunk)
            last = time.time()
        else:
            if time.time() - last >= idle:
                break
    return bytes(data)

def _u16(b: bytes, i: int) -> Tuple[int, int]:
    return int.from_bytes(b[i:i+2], "little"), i + 2

def _u32(b: bytes, i: int) -> Tuple[int, int]:
    return int.from_bytes(b[i:i+4], "little"), i + 4

def _str(b: bytes, i: int) -> Tuple[str, int]:
    ln, i = _u16(b, i)
    s = b[i:i+ln]; i += ln
    return s.decode("utf-8", "ignore"), i

def _parse_tsqp_xml(xml_bytes: bytes) -> Dict[str, Any]:
    root = ET.fromstring(xml_bytes.decode("utf-8", "ignore"))
    F = root.find
    def A(elem, name, default=""): return elem.get(name, default) if elem is not None else default
    serverinfo, owner, players = F("serverinfo"), F("owner"), F("players")
    monsters, npcs, rates, mapinfo, motd = F("monsters"), F("npcs"), F("rates"), F("map"), F("motd")
    return {
        "online": True,
        "server": {
            "name": A(serverinfo, "servername"),
            "ip": A(serverinfo, "ip"),
            "port": int(A(serverinfo, "port") or 0),
            "uptime_sec": int(A(serverinfo, "uptime") or 0),
            "location": A(serverinfo, "location"),
            "url": A(serverinfo, "url"),
            "software": A(serverinfo, "server"),
            "version": A(serverinfo, "version"),
            "client": A(serverinfo, "client"),
        },
        "owner": {"name": A(owner, "name"), "email": A(owner, "email")},
        "players": {
            "online": int(A(players, "online") or 0),
            "max": int(A(players, "max") or 0),
            "peak": int(A(players, "peak") or 0),
        },
        "monsters": {"total": int(A(monsters, "total") or 0)},
        "npcs": {"total": int(A(npcs, "total") or 0)},
        "rates": {
            "experience": A(rates, "experience"),
            "skill": A(rates, "skill"),
            "loot": A(rates, "loot"),
            "magic": A(rates, "magic"),
            "spawn": A(rates, "spawn"),
        },
        "map": {
            "name": A(mapinfo, "name"),
            "author": A(mapinfo, "author"),
            "width": int(A(mapinfo, "width") or 0),
            "height": int(A(mapinfo, "height") or 0),
        },
        "motd": (motd.text or "").strip() if motd is not None else "",
    }


# ----------------- public: XML "info" (TSQP) -----------------

def query_ot_status(host: str, port: int, timeout: float = 5.0, retries: int = 1, backoff: float = 1.0) -> Dict[str, Any]:
    """
    Query the XML 'info' (TSQP) endpoint over the status port.
    Sends one framed request: [lenLE=6][0xFF 0xFF 'info'].
    Tries framed read first; if not present, falls back to raw read and finds XML.
    """
    payload = b"\xFF\xFFinfo"
    framed  = len(payload).to_bytes(2, "little") + payload

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            if attempt:
                time.sleep(backoff)

            with socket.create_connection((host, port), timeout=timeout) as s:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.sendall(framed)

                deadline = time.time() + float(timeout)

                # Try framed header + body
                hdr = _recv_exact(s, 2, deadline)
                xml_bytes: Optional[bytes] = None
                if len(hdr) == 2:
                    total = int.from_bytes(hdr, "little")
                    if 4 <= total <= 65535:
                        body = _recv_exact(s, total, deadline)
                        if len(body) == total:
                            xml_bytes = body

                # Fallback: raw accumulation + locate XML
                if xml_bytes is None:
                    raw = _recv_until_idle(s, deadline)
                    if not raw:
                        # tiny grace
                        time.sleep(0.1)
                        raw = _recv_until_idle(s, deadline)
                    if not raw:
                        raise RuntimeError("Empty response.")

                    # If starts with length, strip it
                    if len(raw) >= 2:
                        t2 = int.from_bytes(raw[:2], "little")
                        if 2 + t2 <= len(raw):
                            cand = raw[2:2 + t2]
                            if cand.startswith(b"<") or cand.startswith(b"<?xml"):
                                raw = cand

                    if not (raw.startswith(b"<") or raw.startswith(b"<?xml")):
                        i = raw.find(b"<?xml")
                        if i == -1:
                            i = raw.find(b"<tsqp")
                        if i != -1:
                            raw = raw[i:]
                    if not (raw.startswith(b"<") or raw.startswith(b"<?xml")):
                        raise RuntimeError("No XML found in response.")
                    xml_bytes = raw

                return _parse_tsqp_xml(xml_bytes)

        except Exception as e:
            last_err = e
            continue

    raise last_err or RuntimeError("Unknown status query error.")


# ----------------- public: Binary list of players -----------------

def query_ot_players(host, port, timeout=5.0, retries=1, backoff=1.0):
    """
    Binary status request:
      [lenLE][0xFF][0x01][flagsLE]
    Response (framed):
      0x20: [u32 online][u32 max][u32 peak]
      0x21: [u32 count] { [u16 len][name][u32 level] } * count
    """
    flags = REQ_PLAYERS_INFO | REQ_EXT_PLAYERS_INFO

    # NOTE: 0xFF is the ProtocolStatus selector byte.
    body   = bytes([0xFF, P_REQ]) + flags.to_bytes(2, "little")
    packet = len(body).to_bytes(2, "little") + body

    last_err = None
    for attempt in range(retries + 1):
        try:
            if attempt:
                time.sleep(backoff)

            with socket.create_connection((host, port), timeout=timeout) as s:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.sendall(packet)

                deadline = time.time() + float(timeout)
                hdr = _recv_exact(s, 2, deadline)
                if len(hdr) != 2:
                    raise RuntimeError("No length header.")
                total = int.from_bytes(hdr, "little")
                if total < 1 or total > 65535:
                    raise RuntimeError("Bad length.")

                body = _recv_exact(s, total, deadline)
                if len(body) != total:
                    raise RuntimeError("Truncated body.")

            # Parse blocks we requested
            i = 0
            online = maxp = peak = 0
            players = []
            while i < len(body):
                code = body[i]; i += 1
                if code == R_PLAYERS_COUNTS:      # 0x20
                    online, i = _u32(body, i)
                    maxp,  i = _u32(body, i)
                    peak,  i = _u32(body, i)
                elif code == R_PLAYERS_LIST:      # 0x21
                    cnt, i = _u32(body, i)
                    for _ in range(cnt):
                        name, i = _str(body, i)
                        lvl,  i = _u32(body, i)
                        players.append({"name": name, "level": lvl})
                else:
                    break

            return {
                "online": True,
                "players": {"online": online, "max": maxp, "peak": peak},
                "list": players,
            }

        except Exception as e:
            last_err = e
            continue

    return {
        "online": False,
        "error": str(last_err) if last_err else "Unknown error.",
        "players": {"online": 0, "peak": 0},
        "list": [],
    }