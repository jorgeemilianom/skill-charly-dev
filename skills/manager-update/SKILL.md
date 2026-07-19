---
name: manager-update
description: "Refreshes an existing client's Business/<cliente>/: shows current content, appends new context/notes, and can update the optional repos:/jira_key: manifest. Never touches credentials.md content — that stays manual, edited outside the conversation. Delegated to by /manager for 'update <cliente>' or a bare client name matching an existing folder."
allowed-tools: Bash Read Write
---

# Manager Update — Maintain an Existing Client

Refresh `Business/<cliente>/` for: **$ARGUMENTS**

`$ARGUMENTS` is `<cliente>`. Nothing in this file should assume a specific client's content — it only
reads/appends whatever's already there.

---

## Step 0 — Preconditions

```bash
WS=$(python3 -c "
import os, subprocess
try:
    g = subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip()
except:
    g = os.getcwd()
p = os.path.dirname(g)
print(p if os.path.exists(os.path.join(p,'CLAUDE.md')) else g)
")
CLIENTE="<\$ARGUMENTS>"
[ -d "$WS/Business/$CLIENTE" ] && echo EXISTS || echo MISSING
```

If `MISSING`: this client has no folder yet. Say so and ask:
> "`Business/<cliente>` no existe todavía. ¿Corro `/manager-create <cliente>` para crearlo?"
If confirmed, invoke `/manager-create <cliente>` and stop here — don't duplicate its bootstrap logic.

---

## Step 1 — Show current state

```bash
ls -la "$WS/Business/$CLIENTE"
cat "$WS/Business/$CLIENTE/context.md" 2>/dev/null
cat "$WS/Business/$CLIENTE/client.md" 2>/dev/null
```

Present a short summary of what's already there (don't dump raw file contents at the user unprompted
if `context.md` is long — summarize, then offer to show the full file on request).

---

## Step 2 — What to update

Ask what the user wants to do. Typical options (don't force this list — take whatever they describe):
- Agregar una nota nueva al contexto (se agrega con fecha, no se pisa lo existente).
- Actualizar el manifiesto opcional (`repos:` / `jira_key:` en `client.md`) — crear el archivo si no
  existía y el usuario ahora quiere agregarlo.
- Cualquier otro archivo suelto que quiera agregar o editar dentro de la carpeta.

**Never rewrite or ask about `credentials.md` content** — that file is edited by hand, outside this
conversation, always.

---

## Step 3 — Apply

- New context notes: append to `context.md` as a dated entry, don't overwrite prior notes:
  ```
  ## <ISO date>
  <note>
  ```
- Manifest changes: read `client.md` if it exists, merge in the requested change, write back the same
  `repos:` / `jira_key:` front-matter shape used by `/manager-create`.
- Anything else the user asked for, applied literally.

Confirm the diff/summary of what changed before writing, same as any other local file write.

---

## Step 4 — Report

Summarize what changed under `Business/<cliente>/`. Remind the user `credentials.md` (if present) was
left untouched.
