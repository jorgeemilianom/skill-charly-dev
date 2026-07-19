---
name: dev-db-sync
description: "Pulls a fresh production DB snapshot over SSH for local development, with an interactive first-time setup for connection and per-project settings. Use for 'db-sync <project>' or 'db-sync config <project>'. Delegated to by /dev for the 'db-sync' subcommand. Requires DB_SYNC_REPOS to be configured."
allowed-tools: Bash Read Write
---

# Dev DB Sync — Production DB Snapshot

Run DB sync for: **$ARGUMENTS**

`$ARGUMENTS` is `<project>` or `config <project>`. Requires `DB_SYNC_REPOS` to be set in `config.sh`. If empty, tell the user db-sync isn't configured for this workspace and stop.

`<project>` must be one of the repos listed in `DB_SYNC_REPOS` (`config.sh`). If omitted, ask which project.

> Before improvising a multi-step procedure, check `scripts/local/MANIFEST.json` — see `dev/references/local-scripting.md`. If the user corrects an in-progress approach, capture it immediately — see "Capture Corrections as They Happen" in `dev/SKILL.md`.

---

## Step 0 — Load VPS config

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
cat $WS/memory/vps-config.json 2>/dev/null
```

**If the file does not exist**, run the first-time setup below and save it before continuing.

### First-time setup (interactive)

Ask the user for the shared connection fields once, then the per-project fields for each entry in `DB_SYNC_REPOS` (`config.sh`):

```
Host de la VPS productiva (ej: 123.45.67.89 o prod.ejemplo.com):
Usuario SSH (ej: jorge):
Ruta a la clave SSH (ej: ~/.ssh/id_rsa):

Para cada proyecto en DB_SYNC_REPOS:
  Directorio en la VPS productiva (ej: /var/www/<project>):
  Comando make para generar el backup (ej: db-backup):
  Ruta del archivo de backup generado en la VPS (ej: /tmp/backup.sql):
  Comando make para importar el backup localmente (ej: db-import FILE=):
```

Save to `$WS/memory/vps-config.json`, with one entry under `projects` per repo in `DB_SYNC_REPOS`:
```json
{
  "production_vps": {
    "host": "<host>",
    "user": "<user>",
    "key_path": "<key_path>",
    "projects": {
      "<project_name>": {
        "remote_path": "<path>",
        "backup_make_target": "<target>",
        "remote_backup_file": "<path>",
        "local_import_make_target": "<target>"
      }
    }
  }
}
```

To update a single field later: `db-sync config <project>` — re-asks only that project's fields.

## Step 1 — Test SSH connectivity

```bash
ssh -i <key_path> -o ConnectTimeout=10 -o BatchMode=yes <user>@<host> "echo ok" 2>&1
```

If this fails, abort and show the SSH error — do not proceed.

## Step 2 — Generate backup on the production VPS

Confirm before running:
> "Voy a conectarme a `<user>@<host>` y correr `make <backup_make_target>` en `<remote_path>`. ¿Confirmás?"

```bash
ssh -i <key_path> <user>@<host> "cd <remote_path> && make <backup_make_target>"
```

If the command fails, show stderr and abort.

## Step 3 — Download the backup to this VPS

Local destination: `$WS/memory/db-backups/<project>_<YYYY-MM-DD_HH-MM-SS>.sql`

```bash
mkdir -p $WS/memory/db-backups
scp -i <key_path> <user>@<host>:<remote_backup_file> \
    "$WS/memory/db-backups/<project>_$(date +%Y-%m-%d_%H-%M-%S).sql"
```

Confirm success by checking the downloaded file size:
```bash
ls -lh "$WS/memory/db-backups/<project>_<timestamp>.sql"
```

If file is 0 bytes or missing, abort with an error.

## Step 4 — Optional import

Ask:
> "Backup descargado en `<local_path>` (<size>). ¿Lo importo en el entorno local de `<project>`?"

If confirmed:
```bash
source "$WS/scripts/workspace-env.sh"
make -C $WS/${PROJECTS_PREFIX}<project> <local_import_make_target>"$WS/memory/db-backups/<downloaded_file>"
```

If the Makefile target does not exist, warn and suggest the user run the import manually, showing the exact file path.

## Step 5 — Summary

```
DB Sync — <project>
  Origen:   <user>@<host>:<remote_path>
  Backup:   <local_path> (<size>)
  Importado: sí / no
  Timestamp: <datetime>
```
