# views_updater.py
import os, zlib, mimetypes, re
from pathlib import Path
from django.http import JsonResponse, Http404, FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse

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
    # Always end with a slash so HTTP.download(url .. file) is valid
    base_url = "https://retrowarot.com/api/"
    manifest = {"url": base_url, "files": {}, "keepFiles": True}

    for root, _, files in os.walk(API_DIR):
        for fname in files:
            fpath = Path(root) / fname
            rel = fpath.relative_to(API_DIR).as_posix()
            top = rel.split("/", 1)[0]

            # only publish wanted roots
            if top not in FILES_AND_DIRS:
                continue

            # skip paths that would break URL concatenation
            if URL_UNSAFE.search(rel):
                continue

            manifest["files"][rel] = _crc32_hex(fpath)

            # optional binary
            for _, binname in BINARIES.items():
                if binname and rel.endswith(binname):
                    manifest["binary"] = {
                        "file": rel,
                        "checksum": _crc32_hex(fpath),
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
    resp["Cache-Control"] = "public, max-age=31536000, immutable"
    # Inline (not “download”)
    resp["Content-Disposition"] = f'inline; filename="{safe_path.name}"'
    return resp
