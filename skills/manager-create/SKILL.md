---
name: manager-create
description: "Interactive bootstrap of a new client's Business/<cliente>/ folder: asks non-sensitive business context in chat, leaves credentials/confidential fields as a placeholder to fill by hand outside the conversation, and offers an optional repos:/jira_key: manifest so /dev can map projects/ repos back to this client. Delegated to by /dev-assess the first time it works on a repo with no client association, and by /manager for 'create <cliente>' or a bare client name with no existing folder."
allowed-tools: Bash Read Write
---

# Manager Create — Bootstrap a New Client

Bootstrap `Business/<cliente>/` for: **$ARGUMENTS**

`$ARGUMENTS` is `<cliente>` optionally followed by one or more repo names (e.g. `QuintaApp
QuintaApp-Api QuintaApp-Frontend`) when invoked from `/dev-assess`'s auto-bootstrap — the repo names
are only a hint for Step 2's optional manifest, never required.

Nothing in this file should assume a specific client's content — it only produces generic scaffolding
and asks generic questions.

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
mkdir -p "$WS/Business"
CLIENTE="<first token of \$ARGUMENTS>"
[ -d "$WS/Business/$CLIENTE" ] && echo EXISTS || echo NEW
```

If no client name was given in `$ARGUMENTS`, ask for one before continuing.

If `EXISTS`: this client already has a folder. Say so and ask:
> "`Business/<cliente>` ya existe. ¿Preferís `/manager-update <cliente>` para mantenerlo, o seguimos acá agregando lo que falte?"
If the user wants to continue here, proceed treating existing files as a base — never overwrite a file
that already has content without asking first.

---

## Step 1 — Business context (non-sensitive only)

Ask, in a short back-and-forth (skip any the user has nothing to add for):
- ¿Qué es este cliente/negocio y qué se hace para él?
- Contexto relevante para trabajar sobre su código o sus tareas (convenciones, reglas de negocio, particularidades).
- Cualquier otra nota que sea útil tener a mano en el futuro.

**Never ask for credentials, tokens, passwords, or other confidential values here** — that's Step 3.

Write the answers to `Business/<cliente>/context.md` as plain free-form notes (no fixed schema —
whatever the user gave you, organized readably).

---

## Step 2 — Optional manifest (repos + Jira key)

Ask:
> "¿Qué repos de `projects/` pertenecen a este cliente? (separados por espacio, o ninguno)"
> "¿Tiene un project key de Jira asociado? (o ninguno)"

If the answer to either is non-empty, offer to persist it:
> "¿Guardo esto en `Business/<cliente>/client.md` para que `/dev` no tenga que volver a preguntar?"

If confirmed, write:
```yaml
---
repos: [<repo1>, <repo2>]
jira_key: <KEY>
---
```
to `Business/<cliente>/client.md`. If declined, skip silently — this is a convenience, never a
requirement, and `/dev-assess` will just ask again next time it meets one of these repos unmapped.

---

## Step 3 — Credentials placeholder (never asked in chat)

Create `Business/<cliente>/credentials.md` only if it doesn't already exist, with blank fields for the
user to fill by hand:

```markdown
# Credenciales / información confidencial — <cliente>

Completar a mano — este archivo nunca se llena por chat.

- Accesos (paneles admin, hosting, DNS): 
- Credenciales de base de datos: 
- API keys / tokens: 
- Contactos clave: 
- Otro:
```

Do not prompt for any of these values — just tell the user the file was created and needs to be
filled manually.

---

## Step 4 — Report

Summarize what was created (files written, under `Business/<cliente>/`) and remind the user:
- `credentials.md` needs to be filled in by hand — nothing sensitive was asked in this conversation.
- Content here is private: `Business/` is gitignored except for its top-level `README.md` (see
  `Business/README.md`), so nothing written in this step gets committed to the public skill repo.

If this was invoked mid-`/dev-assess` (repo names were passed in `$ARGUMENTS`), report done and resume
the assessment that triggered this bootstrap.
