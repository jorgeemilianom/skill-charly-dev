#!/usr/bin/env bash
# charly-dev — configuración del proyecto
# Copiá este archivo a config.sh y completá tus valores.
# config.sh es gitignored — nunca lo commitees.

# ── Jira ─────────────────────────────────────
# Path al directorio de scripts de jira-communication.
# Dejar vacío para usar la copia vendoreada en este repo (scripts/jira-communication),
# resuelta directamente en runtime por cada skill. Setear esto solo si querés apuntar
# a tu propia instalación separada de jira-communication.
export JIRA_SCRIPTS=""

# Project key de Jira (mayúsculas). Usado en los IDs de issue y en las búsquedas.
export PROJECT_KEY="PROJ"

# Versión en minúsculas (usada en patrones de nombre de rama como feature/proj-42)
export PROJECT_KEY_LOWER="proj"

# Tu URL base de Jira (sin barra final)
export JIRA_BASE_URL="https://your-org.atlassian.net"

# ── Repositorios ─────────────────────────────
# Lista de nombres de directorio de repos, separados por espacio, en orden de
# implementación (primero = más fundacional / backend, último = más independiente)
export REPOS="backend-api frontend-app"

# Subcarpeta (relativa a la raíz del workspace) donde viven los repos, ej. "projects"
# si clonás los repos en <workspace>/projects/<repo> en vez de <workspace>/<repo>
# directamente. Dejar vacío para el layout plano (repos como hijos directos de la raíz).
export PROJECTS_SUBDIR=""

# Si algunos repos usan una rama base no estándar (ej. "develop" en vez de "master"),
# listalos acá como patrones glob separados por espacio (nombres exactos o con "*" al final).
# Dejar vacío si todos los repos usan "master".
export SPECIAL_REPO_PATTERNS=""
export SPECIAL_REPO_BASE="develop"

# ── Sync de DB (opcional) ─────────────────────
# Repos que soportan el subcomando "db-sync" (m-dev-db-sync/SKILL.md) —
# es decir, tienen un Makefile con targets de backup/import para traer un snapshot de prod.
# Dejar vacío para deshabilitar db-sync por completo.
export DB_SYNC_REPOS=""

# ── Adaptador cross-tool (opcional) ───────────
# Path al índice de auto-memoria de Claude Code de este proyecto (~/.claude/projects/<escaped-path>/memory/MEMORY.md).
# Referenciado desde agent-context.md como fallback legacy para que Codex también lo pueda ver. Dejar vacío para omitir.
export CLAUDE_MEMORY_INDEX=""

# ── /m-infra-clean ───────────────────────────
# Aviso de cada corrida del cron de relevamiento (ver skills/m-infra-clean/notify.py). Vacío = sin aviso.
#   webhook       → POST JSON (project, status, commit, actor, message) a INFRA_NOTIFY_WEBHOOK
#   evolution-bot → el texto llega por WhatsApp vía un bot n8n/Evolution API (endpoint + token del bot)
#   mcp-whatsapp  → agenda el WhatsApp con una herramienta MCP del backend (URL + API key + id del bot)
INFRA_NOTIFY_MODE=""
INFRA_NOTIFY_MCP_URL=""          # ej. https://tu-dominio.com/api/index.php/mcp/stream
INFRA_NOTIFY_MCP_KEY=""          # API key MCP — cargarla a mano, nunca por el chat
INFRA_NOTIFY_BOT_ID=""
INFRA_NOTIFY_WEBHOOK=""
INFRA_NOTIFY_BOT_ENDPOINT=""
INFRA_NOTIFY_BOT_TOKEN=""
INFRA_NOTIFY_BOT_INSTANCE=""
INFRA_NOTIFY_BOT_SERVER_URL=""
INFRA_NOTIFY_PHONE=""            # destinatario, formato internacional sin + (ej. 5493410000000)

# ── Notas ────────────────────────────────────
# Correr /m-dev-setup después de clonar (desde Claude Code o Codex, dentro de este repo) para
# scaffoldear este archivo interactivamente en vez de editarlo a mano — también chequea
# herramientas requeridas, credenciales de Jira, auth de GitHub, y que los REPOS estén clonados bajo
# projects/. Las skills leen este archivo directamente en runtime; no hay paso de instalación.
