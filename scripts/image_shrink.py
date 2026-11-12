#!/usr/bin/env python3
"""Claude Code hook (PreToolUse, matcher Read): achica las capturas pesadas antes de leerlas.

Una imagen leída queda en el contexto el resto de la sesión y se re-lee (cacheada) en cada turno. Si
el archivo es png/jpg/jpeg/webp y pesa más de MIN_BYTES, se genera una copia de como máximo MAX_SIDE px
(JPEG q80, transparencia sobre blanco) en el temp del sistema y el Read se redirige a esa copia.
Para leer el original igual: DISABLE_IMAGE_SHRINK=1, o un path que termine en `.orig.png`/`.orig.jpg`.

Pillow se resuelve con `uv run --with pillow` (sin instalar nada en el sistema) y solo cuando hace
falta. Nunca bloquea: ante cualquier error sale 0 sin output y el Read sigue con el original.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

MAX_SIDE = int(os.environ.get("IMAGE_SHRINK_MAX_SIDE", "1280"))
MIN_BYTES = 250_000
EXTS = (".png", ".jpg", ".jpeg", ".webp")

RESIZE = r"""
import sys
from PIL import Image
src, dst, side = sys.argv[1], sys.argv[2], int(sys.argv[3])
im = Image.open(src)
im.thumbnail((side, side))
if im.mode in ("RGBA", "LA", "P"):
    im = im.convert("RGBA")
    bg = Image.new("RGB", im.size, "white")
    bg.paste(im, mask=im.split()[-1])
    im = bg
im.convert("RGB").save(dst, "JPEG", quality=80, optimize=True)
"""


def main():
    if os.environ.get("DISABLE_IMAGE_SHRINK"):
        return
    data = json.load(sys.stdin)
    path = (data.get("tool_input") or {}).get("file_path") or ""
    low = path.lower()
    if not low.endswith(EXTS) or ".orig." in low or not os.path.isfile(path):
        return
    size = os.path.getsize(path)
    if size < MIN_BYTES:
        return
    st = os.stat(path)
    key = hashlib.sha1(f"{path}:{st.st_mtime_ns}:{size}:{MAX_SIDE}".encode()).hexdigest()[:16]
    outdir = os.path.join(tempfile.gettempdir(), f"image-shrink-{os.getuid()}")
    os.makedirs(outdir, mode=0o700, exist_ok=True)
    dst = os.path.join(outdir, f"{key}.jpg")  # transparencia aplanada sobre blanco
    if not os.path.exists(dst):
        r = subprocess.run(["uv", "run", "--quiet", "--no-project", "--with", "pillow", "python3", "-c", RESIZE,
                            path, dst, str(MAX_SIDE)], capture_output=True, text=True, timeout=25)
        if r.returncode != 0 or not os.path.exists(dst):
            return
    if os.path.getsize(dst) >= size:
        return
    out = dict(data["tool_input"])
    out["file_path"] = dst
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": f"imagen reducida a ≤{MAX_SIDE}px ({size // 1024} KB → {os.path.getsize(dst) // 1024} KB)",
            "updatedInput": out,
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
