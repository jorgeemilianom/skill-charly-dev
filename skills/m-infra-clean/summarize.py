#!/usr/bin/env python3
"""Resume la última corrida de cada host para /m-manager-digest y arma el aviso de WhatsApp.

Uso: summarize.py <memory/infra> <cron|manual> [<archivo_errores>] [<archivo_solo_manual>]

Escribe:
- <memory/infra>/last-run.json — última evaluación por host (conteos, hallazgos alta/media), errores
  de conexión de esta corrida, hosts solo-manuales y hosts con relevamiento viejo (> STALE_DAYS).
- <memory/infra>/last-notify.json — payload para el webhook, con los mismos campos que el aviso de
  deploy (project, status, commit, actor) más `message` con el resumen legible.
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

STALE_DAYS = 4


def read_lines(path):
    if not path or not os.path.exists(path):
        return []
    return [l.strip() for l in open(path, encoding="utf-8") if l.strip()]


def main():
    mem, mode = sys.argv[1], sys.argv[2]
    errors = read_lines(sys.argv[3] if len(sys.argv) > 3 else None)
    manual = read_lines(sys.argv[4] if len(sys.argv) > 4 else None)
    now = datetime.now(timezone.utc)
    summary = {"mode": mode, "run_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "hosts": {},
               "errors": errors, "manual_only": manual, "stale": []}

    for d in sorted(glob.glob(os.path.join(mem, "runs", "*"))):
        runs = sorted(glob.glob(os.path.join(d, "*.json")))
        if not runs:
            continue
        r = json.load(open(runs[-1], encoding="utf-8"))
        f, alias = r["findings"], os.path.basename(d)
        summary["hosts"][alias] = {
            "collected_at": r.get("collected_at"),
            "counts": {s: sum(x["severity"] == s for x in f) for s in ("alta", "media", "baja")},
            "alta": [x["finding"] for x in f if x["severity"] == "alta"],
            "media": [x["finding"] for x in f if x["severity"] == "media"],
        }
        try:
            at = datetime.strptime(r["collected_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if (now - at).days > STALE_DAYS:
                summary["stale"].append(f"{alias} ({(now - at).days} días)")
        except (KeyError, TypeError, ValueError):
            summary["stale"].append(f"{alias} (fecha ilegible)")

    with open(os.path.join(mem, "last-run.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)

    # Mensaje corto, lo grave primero.
    H = summary["hosts"]
    alerts = sum(h["counts"]["alta"] for h in H.values()) + len(errors) + len(summary["stale"])
    lines = [("🔴" if alerts else "🟢") + f" Relevamiento de infra ({mode})"]
    for alias, h in H.items():
        c = h["counts"]
        lines.append(f"• {alias}: alta {c['alta']} · media {c['media']} · baja {c['baja']}")
        lines += [f"   ⚠️ {x}" for x in h["alta"][:3]]
        lines += [f"   · {x}" for x in h["media"][:2]]
    lines += [f"❌ {e}" for e in errors]
    if summary["stale"]:
        lines.append(f"⏰ Sin relevamiento hace más de {STALE_DAYS} días: " + ", ".join(summary["stale"]))
    if manual:
        lines.append("Solo manual (password o sin acceso): " + ", ".join(manual))
    lines.append("Detalle: /m-infra-clean <alias>")

    payload = {"project": "Infra (m-infra-clean)", "status": "failure" if alerts else "success",
               "commit": summary["run_at"], "actor": mode, "message": "\n".join(lines)}
    with open(os.path.join(mem, "last-notify.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
