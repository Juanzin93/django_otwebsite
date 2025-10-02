# django_otwebsite/api/views.py
import os, json, zlib
from pathlib import Path
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

FILES_DIR = "/srv/django_otwebsite/otserver/api"
FILES_URL = "https://retrowarot.com/api/updater"  # public URL served by Nginx/Apache
FILES_AND_DIRS = ["init.lua", "data", "modules", "mods", "layouts"]

BINARIES = {
    "WIN32-WGL": "Retrowar_gl.exe",
    "WIN32-EGL": "Retrowar_dx.exe",
    "WIN32-WGL-GCC": "Retrowar_gcc_gl.exe",
    "WIN32-EGL-GCC": "Retrowar_gcc_dx.exe",
    "X11-GLX": "Retrowar_linux",
    "X11-EGL": "Retrowar_linux",
    "ANDROID-EGL": "",
    "ANDROID64-EGL": "",
}

CACHE_FILE = "/tmp/otclient_checksums.json"
CACHE_TTL = 60  # seconds


def compute_checksums():
    cache = {}
    dir_path = Path(FILES_DIR).resolve()
    for path in dir_path.rglob("*"):
        if path.is_file():
            rel_path = str(path).replace(str(dir_path), "").lstrip("/\\")
            with open(path, "rb") as f:
                crc = format(zlib.crc32(f.read()) & 0xFFFFFFFF, "08x")
            cache[rel_path.replace("\\", "/")] = crc
    return cache


@csrf_exempt
def updater(request):
    # Load cached checksums if recent
    if os.path.exists(CACHE_FILE) and (os.path.getmtime(CACHE_FILE) + CACHE_TTL > os.path.getmtime(CACHE_FILE)):
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
    else:
        cache = compute_checksums()
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)

    # Parse request JSON
    try:
        data = json.loads(request.body.decode() or "{}")
    except Exception:
        data = {}
    platform = data.get("platform", "")
    binary = BINARIES.get(platform, "")

    result = {"url": FILES_URL, "files": {}, "keepFiles": False}

    for file, checksum in cache.items():
        base = file.split("/")[0]
        if base in FILES_AND_DIRS:
            result["files"][file] = checksum
        if base == binary and binary:
            result["binary"] = {"file": file, "checksum": checksum}

    return JsonResponse(result, json_dumps_params={"indent": 2})
