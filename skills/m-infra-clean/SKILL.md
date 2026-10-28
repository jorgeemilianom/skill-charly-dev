---
name: m-infra-clean
description: "Maintenance sweep over the registered infrastructure (VPS/servers listed in Business/): read-only audit of logs, access (SSH config, keys, logins, failed attempts, firewall, ports), anomalies (load, OOM, processes from /tmp, suspicious crons, unexpected outbound connections, config drift vs the previous run), vulnerabilities (pending security updates, reboot, outdated runtimes, TLS expiry) and DB backups — then a fix plan where every state-changing action runs only after explicit authorization, and only on infra we maintain (audit-only clients get findings as a commercial proposal, never fixes). Writes a dated report under Business/, proposes [Tech debt] Jira tickets for high findings, and can install a weekly read-only cron that /m-manager-digest picks up. Use for '/m-infra-clean', '/m-infra-clean <alias|cliente|all>', '/m-infra-clean inventory', '/m-infra-clean cron'."
allowed-tools: Bash Read Write
---

# Infra Clean — Mantenimiento de la infraestructura registrada

Run for: **$ARGUMENTS**

`$ARGUMENTS`: `[<alias>|<cliente>|all] [audit]` (default `all`), or `inventory` (rebuild/refresh the
host inventory only), or `cron` (install/review the weekly read-only collection).
`audit` = stop after the report (Step 4), no fix plan.

> CUSTOMIZE: hosts, clients and scopes come from your own `Business/` (gitignored). Nothing in this
> file names a real host — keep it that way, this skill is public.

## Non-negotiable rules

- Everything in `Business/Agent.md` applies (identify the client before touching secrets, never reuse
  credentials across clients, never print secrets, nothing that mutates production without explicit
  authorization in the current turn).
- **Collection is read-only.** `collect.sh` only reads; the remote script travels via stdin
  (base64 → `bash`), no files are left on the host.
- **Every fix needs its own explicit OK**, shown with the exact command, risk and rollback. A blanket
  "dale con todo" is valid only for the exact list just shown, not for anything discovered later.
- **Scope decides what's allowed per host** (inventory field `scope`):
  - `maintained` — we fix (with OK) and file tickets.
  - `audit-only` — client infra without a maintenance contract: report only, never fix, never file
    Jira tickets; findings feed a commercial proposal.
  - `excluded` — decommissioned or out of scope: never connect.
- Never paste raw collector output into chat or Jira — it's stored redacted under `memory/infra/`;
  surface the evaluated findings, and quote raw lines only as targeted evidence.
- Hardening that can lock us out (disable SSH password auth, enable a firewall, change SSH port,
  revoke keys) is **never** executed by this skill — it always becomes a ticket with a rollback plan
  that includes console/provider-panel access.
- Shared hosts (several OS users or agent sessions on the same VPS): coordinate before restarting
  services or pruning anything shared; check `/proc/loadavg` before blaming a timeout on the host.

---

## Step 0 — Resolve the workspace and inventory

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
SK="$WS/skills/m-infra-clean"
INV="$WS/memory/infra/inventory.json"
[ -f "$INV" ] && echo "INVENTORY OK ($(python3 -c "import json;print(len(json.load(open('$INV'))['hosts']))" ) hosts, modificado $(date -r "$INV" +%F))" || echo "INVENTORY MISSING"
```

- `INVENTORY MISSING`, argument `inventory`, or any `Business/*/Agent.md` / `Business/INFRA.md`
  newer than the inventory → Step 1.
- Otherwise → Step 2.

## Step 1 — Build the inventory from `Business/`

There is no separate registry: the source of truth is what `Business/` already documents. Read:

1. `Business/INFRA.md` — our own servers (purpose, provider, how to connect, backups, monitoring).
2. `Business/Agent.md` — client registry.
3. Each `Business/<cliente>/Agent.md`, `context.md`, `client.md` — hosts, access method, layout.
4. `Business/<cliente>/credentials.md` — **only to learn whether access exists and where**, never to
   read values into chat: `grep -nF '<ip>' credentials.md | cut -d: -f1` (line numbers only; never
   `grep -A/-B/-C`, never print matching lines).

Build one entry per reachable host. Schema (no secrets — only pointers):

```json
{"hosts": [{
  "alias": "short-kebab-name",
  "client": "<propio | carpeta de Business/>",
  "scope": "maintained | audit-only | excluded",
  "os": "linux | windows",
  "auth": "local | key | password",
  "host": "<ip o dns>", "port": 22, "user": "<usuario>",
  "key_path": "<ruta relativa al workspace, si auth=key>",
  "password_ref": "Business/<cliente>/credentials.md#<sección> (si auth=password)",
  "access_helper": "<cómo conecta el Agent.md del cliente, si auth=password>",
  "expected_ports": [22, 80, 443],
  "max_backup_age_h": 26,
  "expected_backups": [{"name": "...", "where": "local|remote", "path_glob": "..."}],
  "report_dir": "Business/<cliente>  (o Business/_infra para hosts propios)",
  "notes": "decisiones conocidas que no deben reportarse como hallazgo (riesgos aceptados)"
}]}
```

Rules while building it:
- A host documented as decommissioned/"dado de baja" → `scope: excluded`.
- Scope is a business decision, not a technical one: if a client's maintenance status isn't written
  anywhere in `Business/`, **ask** — don't infer it from who owns the hardware.
- Hosts with no access documented anywhere → include with `auth: none` so the gap shows up in the
  report, and say so to the user.
- `expected_ports` must include a non-default SSH port if the host uses one.
- Accepted risks already decided and documented (e.g. "backups stay only on this VPS") go in `notes`
  so Step 3 doesn't re-report them as new findings.

Show the inventory as a table (alias, cliente, scope, auth, notas) and **confirm before writing**
`memory/infra/inventory.json` (`chmod 600`). If the argument was `inventory`, stop here.

## Step 2 — Collect

Select hosts from `$ARGUMENTS` (alias, client folder name, or `all`), skipping `excluded`,
`os: windows` (no collector yet — list them as "sin cobertura"), and `auth: none`.

**`local` / `key` hosts** — one call does collection + evaluation + summary:

```bash
"$SK/run.sh" <alias|all>
```

**`password` hosts** — follow the client's `Agent.md` access procedure (it documents the helper and
how to load the password without printing it). Send the same read-only payload and store it where
`run.sh` would, then evaluate:

```bash
B64=$(base64 -w0 "$SK/collect.sh")
TS=$(date -u +%Y%m%dT%H%M%SZ); D="$WS/memory/infra/runs/<alias>"; mkdir -p "$D"; chmod 700 "$WS/memory/infra/runs" "$D"
<helper exec del Agent.md> "echo $B64 | base64 -d | bash" > "$D/$TS.txt"; chmod 600 "$D/$TS.txt"
PREV=$(ls -1 "$D"/*.txt | grep -v "$TS" | tail -1)
python3 "$SK/evaluate.py" "$D/$TS.txt" ${PREV:+"$PREV"} --expected-ports <p1,p2> --max-backup-age-h <h> > "$D/$TS.json"
```

Clean up any temp password file the helper needed, right after. A host that fails to connect is a
finding (`alta` if `maintained`), not a reason to abort the sweep.

## Step 3 — Analyze

Start from each host's `<ts>.json` (deterministic thresholds + diff vs the previous run). Then add
what the script can't judge — read only the raw sections you need:

1. **Backups vs expectations** — check each `expected_backups` entry (newest file age, size not
   shrinking >30% vs the previous, `gzip -t` on the newest). For our own VPS also read the tail of the
   backup monitoring log documented in `Business/INFRA.md`.
2. **Accesses** — new users/keys/sudo members flagged by the diff: ask the user whether each is
   known before calling it benign. Successful logins from IPs never seen in previous runs: list them.
3. **Vulnerabilities** — for runtimes the report shows as outdated (PHP, nginx, OpenSSH, OpenSSL,
   MySQL), check known CVEs for that exact version only when it's internet-facing; cite the source.
4. **Correlate** before reporting (swap full + OOM kills + high load = one memory problem, not three).
5. **Drop accepted risks** listed in the host's `notes`; mention them in one line as "riesgo aceptado".
6. **Compare with the previous report** in `report_dir` (if any): mark each finding `nuevo`,
   `persiste`, or `resuelto`.
7. Collector ran without root (`root=false`) → say which areas had no coverage; don't present
   "no findings" there as a clean bill of health.

Classify every finding as **a resolver** (`maintained`) or **propuesta comercial** (`audit-only`).

## Step 4 — Report

Write one report per host to `<report_dir>/auditoria-infra-<alias>-<YYYY-MM-DD>.md` (same style as
existing `auditoria-infra-*.md` files there, if any):

```markdown
# Auditoría de infraestructura — <alias> (<fecha>)

<una línea: alcance (maintained/audit-only), solo lectura, root sí/no>

<SO, cores/RAM, disco, uptime — una línea>

## Hallazgos

| Prioridad | Estado | Hallazgo | Riesgo | Acción propuesta |
|---|---|---|---|---|
| Alta | nuevo/persiste | ... | ... | fix `<id>` / ticket / propuesta |

## Resueltos desde la auditoría anterior
## Riesgos aceptados (no se reportan como hallazgo)
## Sin cobertura en esta corrida
```

For `audit-only` hosts add the "Alcance sugerido del servicio" section (as in prior audits) so the
report doubles as proposal input.

`Business/` is its own git repo: per `Business/Agent.md`, offer to commit **one client per commit**
(`git -C "$WS/Business" ...`), never from the workspace root repo.

Show the user a short consolidated summary in chat (per host: counts + the `alta` items), then stop if
`$ARGUMENTS` included `audit`.

## Step 5 — Fix plan (maintained hosts only)

Build the plan only from findings whose `fix` id is in the catalog below. Present it as a numbered
list: host, fix id, exact command, expected effect, risk, rollback. Then ask which to run.

| id | Qué hace | Comando base (Debian/Ubuntu; adaptar a dnf en RHEL/Amazon) | Riesgo | Rollback |
|---|---|---|---|---|
| `journal-vacuum` | Recorta journald | `journalctl --vacuum-size=500M` | bajo | n/a (solo logs viejos) |
| `log-rotate` | Rota un log gigante | Si tiene config: `logrotate -f /etc/logrotate.d/<x>`. Si no: `gzip -c f > f.<fecha>.gz && truncate -s0 f` y proponer config de logrotate | bajo | el `.gz` queda |
| `docker-prune` | Libera imágenes colgadas y build cache viejo | `docker image prune -f && docker builder prune -f --filter until=168h` — **nunca** `-a` ni `volume prune` | bajo | rebuild de la imagen |
| `docker-log-limits` | Límite de logs de contenedores | `daemon.json` → `log-opts: max-size 50m, max-file 3`; requiere reiniciar dockerd → **solo en ventana**, si no, ticket | medio | restaurar `daemon.json` backup |
| `disk-cleanup` | Libera disco | primero `du -xh --max-depth=2 / \| sort -rh \| head`; luego `apt-get clean`, `apt-get autoremove --purge` (kernels viejos) | medio | n/a |
| `apt-refresh` | Refresca índice de paquetes | `apt-get update` | bajo | n/a |
| `security-updates` | Aplica parches de seguridad | dump de DBs del host primero (`db-backup-now`), luego `apt-get install --only-upgrade <paquetes de seguridad>`; si toca libc/openssl/kernel → reinicio de servicios o del host | medio-alto | `apt-get install <pkg>=<versión anterior>` (anotar versiones antes) |
| `reboot-window` | Reinicio pendiente | **nunca acá** — proponer ventana y ticket | — | — |
| `certbot-renew` | Renueva certificados | `certbot renew --dry-run` y, si pasa, `certbot renew` | bajo | n/a |
| `fail2ban` | Mitiga fuerza bruta SSH | instalar/habilitar jail `sshd` (bantime 1h, maxretry 5), whitelistear nuestras IPs fijas | medio | `systemctl disable --now fail2ban` |
| `add-swap` | Agrega swap | `fallocate -l 2G /swapfile && chmod 600 && mkswap && swapon` + `/etc/fstab` | bajo | `swapoff` + quitar línea |
| `db-backup-now` | Dump inmediato de una DB | el script de backup que el host ya usa (ver `Business/INFRA.md` / Agent.md); si no hay, `mysqldump --single-transaction` dentro del contenedor tomando la password del entorno del contenedor, nunca en argv; verificar `gzip -t` y tamaño | bajo | n/a |

Execution, per authorized fix:
1. Re-check the specific state right before (the finding may be stale or another session fixed it).
2. Run it. On the local host, if it needs root and `sudo -n` isn't available, give the user the exact
   command to run as `! sudo <cmd>` — don't try to work around it.
3. Verify (re-run the relevant collector check or the specific command) and record the before/after.
4. Append to the host's report: `## Acciones aplicadas` — fecha, comando, resultado, rollback.

Anything not in the catalog (hardening, version upgrades of runtimes, service config changes) →
Step 6, not improvised here.

## Step 6 — Jira (maintained hosts only)

For `alta` findings still open after Step 5, plus anything excluded from the catalog that needs work:

1. Search for an open ticket on the same host/theme first
   (`jira-search.py --json query "project = <PROJECT_KEY> AND statusCategory != Done AND summary ~ \"<alias>\""`,
   piped through `scripts/jira_trim.py`) — add a comment to it instead of creating a duplicate.
2. Otherwise draft one ticket per host (or per theme across hosts), summary
   `[Tech debt] <cliente/infra> — <tema>`, description = the findings table rows + the report path.
3. Create/comment **only after the user confirms** the draft.

Never file tickets for `audit-only` hosts — offer instead to append the findings to that client's
proposal notes via `/m-manager-update <cliente>`.

## Step 7 — Weekly read-only cron (`cron` argument, or offered once after the first full run)

`run.sh all --cron` collects every `local`/`key` host and refreshes `memory/infra/last-run.json`,
which `/m-manager-digest` reads. It never fixes anything and never touches password hosts.

1. Read the current crontab and check the host's timezone (`timedatectl` / `/etc/timezone`). Cron uses
   the host's local time: convert the user's desired local hour and say so explicitly, including
   whether a DST change will shift it.
2. Propose the exact line, e.g.:
   `30 11 * * 1 <WS>/skills/m-infra-clean/run.sh all --cron >> <WS>/memory/infra/cron.log 2>&1 # m-infra-clean: relevamiento semanal de solo lectura`
3. Install only after confirmation, appending to the existing crontab (never overwrite it):
   `(crontab -l; echo '<línea>') | crontab -`, then `crontab -l | tail -3` to verify.

---

## Related skills

- `/m-manager-exec` — one-off remote tasks on a client's infra; follows the same `Agent.md` playbooks.
- `/m-manager-digest` — reads `memory/infra/last-run.json` to surface infra alerts weekly.
- `/m-manager-update` — where audit-only findings go as proposal input.
- `/m-dev-create` — if a fix turns into real development work rather than ops.
