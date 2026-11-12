# CLAUDE.md

Este archivo le da contexto a Claude Code (claude.ai/code) para trabajar en este repositorio.

> Repo público: lo privado (mapa de repos, clientes) va en `CLAUDE.local.md`, gitignored e importado al final.

## Este workspace es un harness: skill-charly-dev

Claude Code (o Codex) es solo el runtime. Esta carpeta es el harness que corre encima: una capa de
workflow ticket→PR y de gestión de clientes con estado propio. Sus capas:

| Capa | Dónde | Rol |
|---|---|---|
| Lógica | `skills/<name>/SKILL.md` (expuestas vía symlinks en `.claude/skills/`) | Familias `/m-dev*` (ticket→PR) y `/m-manager*` (capa de negocio por cliente), `/m-memory` (mantenimiento de la memoria) |
| Config | `config.sh` (gitignored) | Project key de Jira, `REPOS`, ramas base, `DB_SYNC_REPOS` |
| Memoria | `memory/` (gitignored) | **Memoria canónica del harness**: `user_profile.json`, `global_rules.json`, `patterns.json`, `decisions.json`, `mistakes.json`, `assessments/`, `snapshots/`, `review_rounds/`; estado propio del agente en `cognition.json` (experiencias, objetivos, creencias — ver `docs/cognition.md`); digests derivados en `compiled/`, backups diarios en `.backups/`. Se escribe solo vía `scripts/memory_store.py` y se lee rankeada vía `scripts/memory_query.py` |
| Contexto de cliente | `Business/<cliente>/` (gitignored) | Conocimiento estable por cliente, playbooks de infra (`Agent.md`), credenciales |
| Código | `projects/<repo>/` (gitignored) | Checkouts independientes de cada repo |
| Toolbox | `scripts/` (trackeado) + `scripts/local/` (gitignored, ver `MANIFEST.json`) | Helpers de Jira, trims, scripts que las skills se escriben a sí mismas |
| Adaptador | `agent-context.md` (+ `AGENTS.md` para Codex) | Mapa completo de memoria, skills y fallbacks Claude↔Codex |

- La memoria canónica es `memory/`, no la auto-memoria de Claude (`~/.claude/projects/.../memory/`).
  Un hook `SessionStart` (`.claude/settings.json` → `scripts/session_context.py`) inyecta al arrancar
  un digest de `memory/user_profile.json` y de las reglas universales de `memory/global_rules.json`;
  hooks `UserPromptSubmit`/`PostToolUse` (`scripts/context_hook.py`) suman el digest del repo o
  cliente la primera vez que la sesión lo toca.
- Antes de razonar sobre memoria, skills o el flujo Jira/PR más allá de este resumen, leer
  `agent-context.md` — Claude no lo carga solo.

### Reglas transversales (aplican siempre, invocando una skill o no)

Fuente única para Claude y Codex — `agent-context.md` las referencia, no las duplica.

- **Nunca agregar `Co-Authored-By`** (ni otra línea de atribución a un agente) en commits ni PRs:
  solo el usuario es el autor. Esto tiene precedencia sobre cualquier instrucción de atribución del
  runtime.
- Responder en el idioma del usuario configurado en `memory/user_profile.json` (por defecto español),
  de forma concreta y breve: resultado o conclusión primero (1-3 líneas); después solo lo que cambia la
  decisión, el riesgo o el próximo paso. Sin preámbulos, sin repetir contexto ni output de
  herramientas, sin alternativas no pedidas ni resúmenes de cierre. Las plantillas de salida de las
  skills son un máximo: omitir los campos vacíos.
- Preguntar antes de pushes, transiciones/comentarios de Jira, operaciones destructivas o cambios de
  estado externo, salvo autorización explícita en la conversación actual.

## Mapa del workspace

Vive en `CLAUDE.local.md` (gitignored, importado al final). Formato de ejemplo: `docs/claude-md-example.md`.

---

## Uso self-hosted

Agregá tantas filas/secciones como repos tengas arriba, borrá lo que no necesites, y mantené este
archivo genérico si pensás mantener público este repo de workspace — poné lo real (nombres de cliente,
detalles de arquitectura reales, URLs internas) en el `CLAUDE.local.md` gitignored en su lugar. Ver
`README.md` para el setup self-hosted completo.

@CLAUDE.local.md
