# views_updater.py
import os, zlib, mimetypes, re
from pathlib import Path
from django.http import JsonResponse, Http404, FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.shortcuts import redirect

API_DIR = Path("/srv/django_otwebsite/otserver/api").resolve()
FILES_AND_DIRS = ["init.lua", "data", "modules", "mods", "layouts"]

BINARIES = {
    "WIN32-WGL":       "Retrowar_gl.exe",
    "WIN32-EGL":       "Retrowar_dx.exe",
    "WIN32-WGL-GCC":   "Retrowar_gcc_gl.exe",
    "WIN32-EGL-GCC":   "Retrowar_gcc_dx.exe",
    "X11-GLX":         "Retrowar_linux",
    "X11-EGL":         "Retrowar_linux",
    "ANDROID-EGL":     "",
    "ANDROID64-EGL":   "",
}

def _crc32_hex(path: Path) -> str:
    crc = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            crc = zlib.crc32(chunk, crc)
    return format(crc & 0xFFFFFFFF, "08x")

def _files_base_url(request) -> str:
    base = request.build_absolute_uri(reverse("api", kwargs={"subpath": ""}))
    return base if base.endswith("/") else base + "/"

URL_UNSAFE = re.compile(r"[ \t\(\)]")  # space, tab, parentheses
@csrf_exempt
def updater(request):
    """
    Generate the OTClient update manifest.
    Includes a manual version number to force updates only when bumped.
    """
    MANUAL_VERSION = "1.0.0"  # 🔧 Increase this whenever you want clients to re-update

    client_platform = None
    if request.body:
        try:
            import json
            payload = json.loads(request.body.decode("utf-8"))
            client_platform = payload.get("platform")
        except Exception:
            client_platform = None

    base_url = "https://retrowarot.com/api/"
    manifest = {
        "url": base_url,
        "files": {},
        "keepFiles": True,
        "version": MANUAL_VERSION,  # 🧩 Added manual version
    }

    wanted_binary_name = BINARIES.get(client_platform or "", "") or ""
    wanted_binary_relpath = None
    wanted_binary_checksum = None

    for root, _, files in os.walk(API_DIR):
        files.sort()
        for fname in files:
            fpath = Path(root) / fname
            rel = fpath.relative_to(API_DIR).as_posix()
            top = rel.split("/", 1)[0]

            if top not in FILES_AND_DIRS:
                continue
            if URL_UNSAFE.search(rel):
                continue

            crc = _crc32_hex(fpath)
            manifest["files"][rel] = crc

            if wanted_binary_name and rel.endswith("/" + wanted_binary_name):
                wanted_binary_relpath = rel
                wanted_binary_checksum = crc

    manifest["files"] = dict(sorted(manifest["files"].items()))

    if wanted_binary_relpath and wanted_binary_checksum:
        manifest["binary"] = {
            "file": wanted_binary_relpath,
            "checksum": wanted_binary_checksum,
        }

    resp = JsonResponse(manifest, json_dumps_params={"indent": 2})
    resp["Cache-Control"] = "no-store"
    return resp


@csrf_exempt
def api_file(request, subpath: str):
    """
    Serve /api/<subpath> as raw bytes (always application/octet-stream).
    No content-disposition attachment; the client streams it.
    """
    safe_path = (API_DIR / subpath).resolve()
    if not str(safe_path).startswith(str(API_DIR)) or not safe_path.is_file():
        raise Http404("Not found")

    resp = FileResponse(open(safe_path, "rb"),
                        as_attachment=False,
                        content_type="application/octet-stream")
    # Long cache for immutable client assets
   # resp["Cache-Control"] = "public, max-age=31536000, immutable"
   # # Inline (not “download”)
   # resp["Content-Disposition"] = f'inline; filename="{safe_path.name}"'
   # api_file()
    resp["Cache-Control"] = "no-cache, must-revalidate"
    # or the nuclear option:
    # resp["Cache-Control"] = "no-store"
    resp["Content-Disposition"] = f'inline; filename="{safe_path.name}"'
    return resp

@csrf_exempt
def updater_php(request):
    return updater(request)
