#!/usr/bin/env bash
# Corre el colector de solo lectura contra los hosts del inventario y evalúa cada corrida.
#
#   run.sh <alias>|all [--cron]
#
# Lee memory/infra/inventory.json (lo arma /m-infra-clean en su primera corrida, a partir de
# Business/). Solo maneja hosts con auth `local` o `key` — los de contraseña quedan para la corrida
# interactiva del skill, que sigue el Agent.md del cliente (el cron nunca toca passwords).
# Por host guarda en memory/infra/runs/<alias>/: <ts>.txt (salida cruda, ya redactada) y <ts>.json
# (hallazgos de evaluate.py, comparados contra la corrida anterior). Conserva las últimas 12.
# Al final actualiza memory/infra/last-run.json, que lee /m-manager-digest.
# Nunca modifica nada en los hosts: el script remoto viaja por stdin vía base64, sin dejar archivos.

set -u
HERE="$(cd "$(dirname "$0")" && pwd -P)"
WS="$(cd "$HERE/../.." && pwd -P)"
INV="$WS/memory/infra/inventory.json"
OUT="$WS/memory/infra/runs"
TARGET="${1:-}"; MODE="${2:-}"
[ -n "$TARGET" ] || { echo "uso: run.sh <alias>|all [--cron]" >&2; exit 2; }
[ -f "$INV" ] || { echo "falta $INV — correr /m-infra-clean para armar el inventario" >&2; exit 2; }

B64=$(base64 -w0 "$HERE/collect.sh")
REMOTE_CMD="echo $B64 | base64 -d | bash"
TS=$(date -u +%Y%m%dT%H%M%SZ)

python3 - "$INV" "$TARGET" <<'EOF' > /tmp/.m-infra-hosts.$$
import json, sys
inv = json.load(open(sys.argv[1]))
for h in inv.get("hosts", []):
    if h.get("scope") == "excluded" or h.get("os", "linux") != "linux":
        continue
    if sys.argv[2] not in ("all", h["alias"]):
        continue
    ports = ",".join(str(p) for p in h.get("expected_ports", [22, 80, 443]))
    print("\x1f".join([h["alias"], h.get("auth", ""), h.get("host", ""), str(h.get("port") or 22),
                     h.get("user", ""), h.get("key_path", ""), ports, str(h.get("max_backup_age_h", 26))]))
EOF

rc=0
# Separador \x1f (no espacio en blanco): con tabs, `read` colapsa los campos vacíos y corre columnas.
while IFS=$'\x1f' read -r alias auth host port user key ports age; do
  dir="$OUT/$alias"; mkdir -p "$dir"; chmod 700 "$OUT" "$dir"
  raw="$dir/$TS.txt"
  case "$auth" in
    local) bash "$HERE/collect.sh" > "$raw" 2>/dev/null ;;
    key)
      case "$key" in /*) ;; *) key="$WS/$key" ;; esac
      timeout 300 ssh -n -i "$key" -p "$port" -o BatchMode=yes -o ConnectTimeout=15 \
        -o StrictHostKeyChecking=yes "$user@$host" "$REMOTE_CMD" > "$raw" 2>/dev/null ;;
    *) echo "$alias: auth=$auth — solo corrida interactiva (/m-infra-clean $alias)"; continue ;;
  esac
  if ! grep -q '^### meta' "$raw"; then
    echo "$alias: ERROR — sin salida del colector (conexión o timeout)"; rm -f "$raw"; rc=1; continue
  fi
  chmod 600 "$raw"
  prev=$(ls -1 "$dir"/*.txt 2>/dev/null | grep -v "/$TS.txt$" | tail -1)
  if ! python3 "$HERE/evaluate.py" "$raw" ${prev:+"$prev"} --expected-ports "$ports" --max-backup-age-h "$age" > "$dir/$TS.json"; then
    echo "$alias: ERROR — evaluate.py falló (la corrida cruda queda en $raw)"; rm -f "$dir/$TS.json"; rc=1; continue
  fi
  chmod 600 "$dir/$TS.json"
  ls -1t "$dir"/*.txt | tail -n +13 | while read -r f; do rm -f "$f" "${f%.txt}.json"; done
  echo "$alias: OK ($(python3 -c "import json,sys;f=json.load(open(sys.argv[1]))['findings'];print(', '.join(f'{s}={sum(x[\"severity\"]==s for x in f)}' for s in ('alta','media','baja')))" "$dir/$TS.json"))"
done < /tmp/.m-infra-hosts.$$
rm -f /tmp/.m-infra-hosts.$$

# Resumen para /m-manager-digest: última evaluación por host y sus hallazgos altos.
python3 - "$OUT" "$WS/memory/infra/last-run.json" "$MODE" <<'EOF'
import json, os, sys, glob
out, dest, mode = sys.argv[1], sys.argv[2], sys.argv[3]
summary = {"mode": "cron" if mode == "--cron" else "manual", "hosts": {}}
for d in sorted(glob.glob(os.path.join(out, "*"))):
    runs = sorted(glob.glob(os.path.join(d, "*.json")))
    if not runs:
        continue
    r = json.load(open(runs[-1]))
    f = r["findings"]
    summary["hosts"][os.path.basename(d)] = {
        "collected_at": r.get("collected_at"),
        "counts": {s: sum(x["severity"] == s for x in f) for s in ("alta", "media", "baja")},
        "alta": [x["finding"] for x in f if x["severity"] == "alta"],
    }
json.dump(summary, open(dest, "w"), ensure_ascii=False, indent=1)
EOF
exit $rc
