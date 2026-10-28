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
# Al final actualiza memory/infra/last-run.json (lo lee /m-manager-digest) y, con --cron, avisa al
# webhook INFRA_NOTIFY_WEBHOOK de config.sh si está definido.
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
ERRS="$(mktemp)"; MANUAL="$(mktemp)"
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
    *) echo "$alias: auth=$auth — solo corrida interactiva (/m-infra-clean $alias)"; echo "$alias" >> "$MANUAL"; continue ;;
  esac
  if ! grep -q '^### meta' "$raw"; then
    echo "$alias: ERROR — sin salida del colector (conexión o timeout)" | tee -a "$ERRS"; rm -f "$raw"; rc=1; continue
  fi
  chmod 600 "$raw"
  prev=$(ls -1 "$dir"/*.txt 2>/dev/null | grep -v "/$TS.txt$" | tail -1)
  if ! python3 "$HERE/evaluate.py" "$raw" ${prev:+"$prev"} --expected-ports "$ports" --max-backup-age-h "$age" > "$dir/$TS.json"; then
    echo "$alias: ERROR — evaluate.py falló (la corrida cruda queda en $raw)" | tee -a "$ERRS"; rm -f "$dir/$TS.json"; rc=1; continue
  fi
  chmod 600 "$dir/$TS.json"
  ls -1t "$dir"/*.txt | tail -n +13 | while read -r f; do rm -f "$f" "${f%.txt}.json"; done
  echo "$alias: OK ($(python3 -c "import json,sys;f=json.load(open(sys.argv[1]))['findings'];print(', '.join(f'{s}={sum(x[\"severity\"]==s for x in f)}' for s in ('alta','media','baja')))" "$dir/$TS.json"))"
done < /tmp/.m-infra-hosts.$$
rm -f /tmp/.m-infra-hosts.$$

# Resumen para /m-manager-digest (last-run.json) y payload del aviso (last-notify.json).
python3 "$HERE/summarize.py" "$WS/memory/infra" "$([ "$MODE" = --cron ] && echo cron || echo manual)" "$ERRS" "$MANUAL"
rm -f "$ERRS" "$MANUAL"

# Aviso por webhook (ej. bot de WhatsApp en n8n) en cada corrida del cron. La URL vive en config.sh
# (gitignored), nunca en este repo.
if [ "$MODE" = "--cron" ]; then
  [ -f "$WS/config.sh" ] && . "$WS/config.sh"
  if [ -n "${INFRA_NOTIFY_WEBHOOK:-}" ]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X POST "$INFRA_NOTIFY_WEBHOOK" \
      -H "Content-Type: application/json" --data-binary @"$WS/memory/infra/last-notify.json")
    echo "aviso webhook: HTTP $code"
  fi
fi
exit $rc
