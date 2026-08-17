# skill-charly-dev

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Del ticket de Jira al PR mergeado — un solo comando, workflow completo. Funciona desde Claude Code y Codex.**

Un conjunto de skills que actúan como un par senior: lee tu ticket, explora el codebase, implementa los cambios, corre los tests, abre el PR, maneja los comentarios de revisión, y recuerda cada decisión en el camino. Self-hosted — este repo *es* tu workspace, no algo que se instala dentro de uno.

**Para quién es esto:** developers solos y equipos chicos que manejan varios repos de clientes/productos
contra un Jira compartido, y quieren automatizar el ritual ticket→PR sin entregarle su codebase o
contexto de negocio a un servicio hosteado. Todo lo real — tus repos, tus credenciales de Jira, tus
notas de cliente, tus decisiones acumuladas — se queda en tu máquina, en carpetas gitignoreadas
(`projects/`, `Business/`, `memory/`, `config.sh`). Solo la lógica del workflow (`skills/`) está pensada
para compartirse; forkeá este repo, mantené tu fork público o privado, y las carpetas privadas nunca
salen de tu clone.

---

## El problema

Todo ticket sigue el mismo ritual: leer el ticket, encontrar los archivos, recordar la arquitectura, crear la rama, escribir código, correr tests, escribir la descripción del PR, manejar comentarios de revisión, transicionar Jira... Es lento, repetitivo, y lleno de cambios de contexto.

Estas skills automatizan todo eso. Vos seguís al mando — el agente hace el trabajo de base.

---

## Cómo funciona

```
vos                    agente
─────────────────────────────────────────────────────
/m-dev-create "agregar cancelación de reservas"
                       arma el spec con vos
                       resuelve el epic (cacheado — no vuelve a preguntar)
                       crea el ticket en Jira
─────────────────────────────────────────────────────
/m-dev PROJ-42
                       lee el ticket de Jira
                       explora el codebase (grep, git log, lectura de archivos)
                       carga decisiones pasadas desde memory/
                       ─────────────────────────────
                       Technical Assessment
                         · enfoque propuesto
                         · archivos afectados
                         · riesgos marcados
                         · confidence score
                       ─────────────────────────────
confirmás / ajustás
                       crea la rama
                       implementa los cambios
                       corre tests + linter
                       commitea
─────────────────────────────────────────────────────
/m-dev-pr PROJ-42
                       escanea el diff en busca de problemas
                       arma el cuerpo del PR (resumen, plan de test, criterios de aceptación)
                       abre el PR vía gh
                       postea el link en Jira
                       corre revisión automatizada
─────────────────────────────────────────────────────
llegan comentarios de revisión

/m-dev https://github.com/.../pull/42
                       lee cada comentario de revisión
                       implementa los fixes
                       vuelve a correr la validación
                       commitea + pide confirmación para el push
─────────────────────────────────────────────────────
PR mergeado

/m-dev-reflect PROJ-42 closing
                       guarda aprendizajes en memory/
                       transiciona Jira a Done
                       postea comentario de cierre
```

Cuanto más lo usás, mejor se pone — `memory/` va acumulando las decisiones de tu proyecto, los errores recurrentes y los patrones a través de los tickets.

---

## Skills

`/m-dev` es el orquestador — corre el loop principal (rama → código → tests → commit → push) por sí
mismo y rutea todo lo demás a estos skills hermanos:

| Skill | Qué hace |
|-------|--------------|
| [`/m-dev-setup`](skills/m-dev-setup/SKILL.md) | Setup inicial y health check del entorno: config.sh, herramientas requeridas, credenciales de Jira, auth de GitHub, repos presentes bajo `projects/`. |
| [`/m-dev`](skills/m-dev/SKILL.md) | Orquestador. Loop completo para un ticket ID; rutea ideas libres, URLs de PR, y subcomandos a los skills de abajo. |
| [`/m-dev-create`](skills/m-dev-create/SKILL.md) | Convierte una idea libre en un ticket de Jira filed — arma el spec con vos, resuelve el epic desde una lista cacheada. |
| [`/m-dev-assess`](skills/m-dev-assess/SKILL.md) | Deep dive técnico antes de escribir código. Produce un assessment estructurado con confidence score y espera tu confirmación. |
| [`/m-dev-pr`](skills/m-dev-pr/SKILL.md) | Crea el PR o maneja comentarios de revisión entrantes. Arma el cuerpo, postea en Jira, corre revisión automatizada. |
| [`/m-dev-reflect`](skills/m-dev-reflect/SKILL.md) | Guarda un snapshot en cualquier momento (checkpoint) o corre una reflexión de cierre completa cuando el PR mergea. Alimenta memory con los aprendizajes. |
| [`/m-dev-resume`](skills/m-dev-resume/SKILL.md) | Reconstruye el contexto completo de un ticket ya en curso, con un blurb para el standup. |
| [`/m-dev-review`](skills/m-dev-review/SKILL.md) | Revisa el PR de un compañero contra tu arquitectura y convenciones. |
| [`/m-dev-migration`](skills/m-dev-migration/SKILL.md) | Workflow de migración de DB (chequear pendientes, crear, revisar, correr, commitear). |
| [`/m-dev-status`](skills/m-dev-status/SKILL.md) | Estado de solo lectura de un ticket o de todo el workspace — sin efectos secundarios. |
| [`/m-dev-db-sync`](skills/m-dev-db-sync/SKILL.md) | Trae un snapshot de la DB de producción por SSH para desarrollo local. |

Familia separada — solo capa de negocio, sin lógica de código/Jira/PR (ver [Contexto de negocio](#contexto-de-negocio-business) abajo):

| Skill | Qué hace |
|-------|--------------|
| [`/m-manager`](skills/m-manager/SKILL.md) | Orquestador. Lista los clientes conocidos, o rutea a los skills de abajo. |
| [`/m-manager-create`](skills/m-manager-create/SKILL.md) | Bootstrap interactivo de `Business/<cliente>/` para un cliente nuevo. |
| [`/m-manager-update`](skills/m-manager-update/SKILL.md) | Refresca/mantiene el `Business/<cliente>/` de un cliente existente. |

---

## Estructura del repo

Este repo duplica como tu workspace — lo clonás y *es* la carpeta en la que trabajás, sin un paso de
instalación separado. `skills/` es la fuente real, trackeada; `.claude/skills/<name>` son symlinks
commiteados que apuntan ahí, así que Claude Code descubre todas las skills apenas hacés `cd` después del
`git clone`.

```
skill-charly-dev/               (== tu workspace, una carpeta, un repo)
├── skills/<name>/SKILL.md      ← trackeado, público — fuente canónica de cada skill
├── .claude/skills/<name>       ← symlinks trackeados → ../../skills/<name>, para que Claude los descubra
├── scripts/
│   ├── jira-communication/     ← trackeado, CLI de Jira de terceros vendoreado (ver NOTICE.md)
│   └── local/                  ← gitignored — scripts que las skills se escriben a sí mismas con el tiempo
├── agent-context.md            ← trackeado — adaptador compartido Codex/Claude (preferencias, mapa de memoria, mapa de skills)
├── AGENTS.md                   ← trackeado — puntero raíz nativo de Codex
├── CLAUDE.md                   ← trackeado — plantilla de ejemplo de mapa de proyecto, sin secretos
├── CLAUDE.local.md             ← gitignored — tu mapa de proyecto real (importado automáticamente por CLAUDE.md)
├── config.example.sh           ← trackeado — plantilla, copiar a config.sh
├── config.sh                   ← gitignored — tus valores reales (tampoco tiene secretos — ver Jira abajo)
├── memory/                     ← gitignored — datos reales de tickets/decisiones/patrones
├── projects/                   ← solo README.md trackeado — tus checkouts de repos reales
│   ├── tu-api/
│   └── tu-frontend/
└── Business/                   ← solo README.md trackeado — contexto de cliente (ver abajo)
    └── tu-cliente/
```

No hay paso de generación ni `install.sh` — las skills leen `config.sh` directamente en runtime
(`source config.sh` dentro de los bloques bash correspondientes), así que editar la config tiene efecto
inmediato.

---

## Contexto de negocio (`Business/`)

`projects/` guarda código; `Business/<cliente>/` guarda todo lo del cliente que no es código —
contexto de negocio, scripts, credenciales, información confidencial. Es free-form a propósito: nada es
obligatorio, la skill simplemente lee los archivos que haya ahí. Un archivo de conveniencia opcional que
sí sabe usar, `client.md`, mapea los repos de `projects/` de vuelta a un cliente:

```yaml
---
repos: [tu-api, tu-frontend]
jira_key: PROJ
---
```

`/m-dev-assess` ofrece escribirlo la primera vez que se encuentra con un repo sin carpeta de cliente —
declinás y simplemente vuelve a preguntar la próxima vez, nunca bloquea el ticket. Las credenciales
nunca se tipean en el chat: `/m-manager-create` deja un archivo placeholder en blanco para que lo
completes a mano.

| Skill | Qué hace |
|-------|--------------|
| `/m-manager-create <cliente>` | Bootstrap interactivo de una carpeta de cliente nueva. |
| `/m-manager-update <cliente>` | Refresca/mantiene una existente. |
| `/m-manager` | Lista los clientes conocidos, o rutea a los dos de arriba. |

Igual que `projects/`, solo `Business/README.md` está trackeado — el contenido real es gitignored, y la
skill nunca asume un layout de VCS en particular para eso (un repo privado compartido, un repo por
cliente, o nada versionado — todo funciona igual).

---

## Cross-tool: Claude Code + Codex

Claude Code descubre automáticamente las skills symlinkeadas apenas estás dentro del repo — sin config
necesaria. Codex no tiene un auto-discovery de directorio de skills confiable entre versiones, así que
`AGENTS.md` (que Codex siempre lee) apunta a `agent-context.md`, que le indica exactamente qué
`skills/<name>/SKILL.md` leer para un pedido dado, y dónde encontrar `config.sh` para los valores
específicos del proyecto.

---

## Inicio rápido

```bash
# 1. cloná — este repo se convierte en tu workspace
git clone https://github.com/jorgeemilianom/skill-charly-dev.git ~/skills/charly-dev
cd ~/skills/charly-dev
```

Después, en Claude Code o Codex, desde dentro del repo:

```
/m-dev-setup
```

Esto scaffoldea `config.sh` interactivamente (project key de Jira, repos, ramas base — sin secretos),
chequea que `gh`/`uv` estén instalados, chequea credenciales de Jira y auth de GitHub (ambos necesitan
una terminal real — te va a decir exactamente qué correr), crea `projects/`, `scripts/local/`,
`memory/`, y reporta cuáles de tus `REPOS` configurados todavía necesitan `git clone`. Volvé a correrlo
cuando quieras — es idempotente y seguro de usar como health check.

Una vez que tengas repos reales en su lugar, completá `CLAUDE.md` con tu mapa de proyecto real — o, si
pensás mantener este repo público/compartido, escribilo en un `CLAUDE.local.md` gitignored en su lugar
(ya importado por `CLAUDE.md` vía `@CLAUDE.local.md`), así tus detalles reales de cliente/arquitectura
nunca se commitean.

Una vez que reporte todo OK:

```
/m-dev-create "descripción corta de lo que querés construir"
```

o, para un ticket existente:

```
/m-dev PROJ-42
```

`/m-dev` también corre este mismo chequeo de precondiciones por su cuenta antes de cada ticket, y
ofrece correr `/m-dev-setup` si falta algo — no tenés que acordarte de correrlo primero.

---

## Comandos comunes

| Situación | Comando |
|-----------|---------|
| Primer clone, o chequeo de credenciales/config | `/m-dev-setup` |
| Spec + crear un ticket nuevo | `/m-dev-create "<idea>"` |
| Empezar un ticket nuevo | `/m-dev PROJ-42` |
| Retomar después de una pausa | `/m-dev-resume PROJ-42` |
| Chequear el estado de un ticket | `/m-dev-status PROJ-42` |
| Crear el PR | `/m-dev-pr PROJ-42` |
| Arreglar comentarios de revisión | `/m-dev https://github.com/.../pull/42` |
| Revisar el PR de un compañero | `/m-dev-review https://github.com/.../pull/42` |
| Cerrar el ticket | `/m-dev-reflect PROJ-42 closing` |
| Ver todo el trabajo activo | `/m-dev-status` |
| Traer un snapshot fresco de la DB de producción | `/m-dev-db-sync <proyecto>` |
| Bootstrap del contexto de negocio de un cliente nuevo | `/m-manager-create <cliente>` |
| Refrescar el contexto de negocio de un cliente existente | `/m-manager-update <cliente>` |
| Listar clientes conocidos | `/m-manager` |

---

## Configuración

Todo lo específico del proyecto vive en `config.sh` (gitignored — nunca commiteado, aunque tampoco
tiene secretos; las credenciales de Jira/GitHub viven fuera de este repo, ver abajo).

```bash
cp config.example.sh config.sh
```

Las skills hacen `source` de este archivo directamente en runtime, así que no hay paso de
regeneración — lo editás y la próxima invocación de una skill lo toma.

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `JIRA_SCRIPTS` | Path a los scripts del CLI de Jira. Dejar vacío para usar la copia vendoreada en este repo | `/path/to/your-own/jira-communication/scripts` |
| `PROJECT_KEY` | Project key de Jira (mayúsculas) | `PROJ` |
| `PROJECT_KEY_LOWER` | Lo mismo, en minúsculas (nombres de rama) | `proj` |
| `JIRA_BASE_URL` | URL de tu instancia de Jira | `https://your-org.atlassian.net` |
| `REPOS` | Directorios de repos, separados por espacio | `backend-api frontend-app` |
| `PROJECTS_SUBDIR` | Subcarpeta donde viven los repos | `projects` |
| `SPECIAL_REPO_PATTERNS` | Repos (patrones glob) con una rama base no estándar | `frontend-app legacy-*` |
| `SPECIAL_REPO_BASE` | Su rama base | `develop` |
| `DB_SYNC_REPOS` | Repos que soportan `/m-dev-db-sync` — dejar vacío para deshabilitar | `backend-api` |
| `CLAUDE_MEMORY_INDEX` | Path al `MEMORY.md` de auto-memoria de Claude para este proyecto, expuesto a Codex como fallback legacy | `~/.claude/projects/<escaped-path>/memory/MEMORY.md` |

`/m-dev-setup` scaffoldea y pregunta todo esto interactivamente — editar a mano solo hace falta para
cambiar un valor después.

Las credenciales de Jira y GitHub **no** están en `config.sh` — `/m-dev-setup` te guía por ambas, pero
el paso real de ingresar el secreto siempre pasa en tu propia terminal, nunca a través del agente:
- Jira: `uv run scripts/jira-communication/scripts/core/jira-setup.py` → escribe `~/.env.jira`
- GitHub: `gh auth login`

Las skills también contienen **reglas de arquitectura** y **mapeos de keyword a repo** hechos como
ejemplo — buscá los comentarios `> CUSTOMIZE` en `skills/*/SKILL.md` y reemplazá los nombres de repo de
ejemplo (`backend-api`, `frontend-app`, `internal-platform`) por tus repos y convenciones reales.

---

## Requisitos

| Herramienta | Instalación |
|------|---------|
| [Claude Code](https://claude.ai/code) y/o [Codex CLI](https://developers.openai.com/codex) | ver docs |
| [`gh`](https://cli.github.com/) | `brew install gh` / `apt install gh` |
| [`uv`](https://github.com/astral-sh/uv) | `curl -Ls https://astral.sh/uv/install.sh \| sh` |

`/m-dev-setup` chequea que tanto `gh` como `uv` estén en el `PATH` y te avisa si falta alguno.
