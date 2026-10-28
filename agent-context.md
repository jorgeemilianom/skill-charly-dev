# Contexto compartido para agentes

Este archivo es el adaptador compartido entre Claude Code y Codex para este workspace. Tratalo como el
punto de entrada estable para preferencias de usuario, ubicaciones de memoria, mapeos de skills, y
fallbacks entre herramientas. Claude Code no lee este archivo automáticamente (lee `CLAUDE.md`, que
trae un resumen del harness y le indica cuándo leer este) — es el punto de entrada de Codex, al que se
llega vía el `AGENTS.md` raíz.

## Orden de carga

1. Leer este archivo primero.
2. Leer el `CLAUDE.md` del workspace para la vista general de repos y convenciones, y
   `CLAUDE.local.md` si existe (Codex no resuelve el import `@CLAUDE.local.md`).
3. Correr `python3 scripts/session_context.py` y tomar su salida como contexto (en Claude lo hace el
   hook `SessionStart`; Codex no ejecuta los hooks de `.claude/settings.json`).
4. Leer `config.sh` para la identidad de proyecto/repos de Jira de este workspace (project key, repos, ramas base).
5. Si se está trabajando dentro de la subcarpeta de un repo, leer el `AGENTS.md` y/o `CLAUDE.md` local de ese repo.
6. Leer memoria específica de la tarea solo cuando la tarea toca esa área.

No copiar secretos de `~/.claude` u otro estado de Claude a archivos del proyecto. Si un helper ya
embebe credenciales, referenciar el path del helper en vez de duplicar la credencial.

## Preferencias del usuario

Las reglas transversales (sin `Co-Authored-By`, idioma, concisión, gates de confirmación) viven en
una sola fuente: la sección "Reglas transversales" de `CLAUDE.md`, que Claude carga automáticamente y
Codex lee en el paso 2 del orden de carga. No duplicarlas acá — si cambian, cambiarlas allá. Las
preferencias aprendidas por sesión están en `memory/user_profile.json` (en Claude, un hook
`SessionStart` inyecta un digest al arrancar; en Codex, el paso 3 del orden de carga).

- Mantener los términos técnicos en inglés cuando ese sea el término natural en el codebase.

> Agregá acá tus propias preferencias específicas del proyecto, o en `CLAUDE.local.md` si preferís
> mantener este archivo genérico (ej. una regla como "después de cualquier cambio de frontend, correr
> el paso de build antes de considerar el trabajo terminado" para un proyecto cuyo framework necesita
> un paso de compilación).

## Memoria del workspace

La memoria compartida de este workspace vive en:

`memory/` (raíz del workspace, al lado de `CLAUDE.md` — no por repo)

Archivos que las skills `/m-dev-*` leen y escriben:

- `memory/user_profile.json` — preferencias de comunicación/workflow, cargado por `/m-dev` al inicio de cada ticket.
- `memory/epics.json` — lista de epics cacheada para el project key en `config.sh`, mantenida por `/m-dev-create` para no re-consultar los epics en cada sesión.
- `memory/snapshots/<TICKET>.json` — checkpoints escritos por `/m-dev-reflect`, leídos por `/m-dev`, `/m-dev-resume`, `/m-dev-status`.
- `memory/assessments/<TICKET>.json` — assessments técnicos escritos por `/m-dev-assess`.
- `memory/vps-config.json` — configuración de conexión a la VPS de producción para `/m-dev-db-sync`.
- `memory/review_rounds/<TICKET>.json` — historial de revisiones de PR escrito por `/m-dev-pr`.
- `memory/db-backups/` — snapshots de DB descargados desde `/m-dev-db-sync`.
- `memory/patterns.json`, `memory/decisions.json`, `memory/mistakes.json`, `memory/global_rules.json` — aprendizajes cross-ticket escritos por `/m-dev-reflect`, recuperados por `/m-dev-assess` **filtrados** por `tags` (nombres de repo + keywords; `tags` vacío = universal, siempre incluido) para que una memoria creciente no vuelque historial irrelevante en cada ticket. Las entradas de `global_rules.json` también llevan `status` (`active`/`superseded`), `confidence` (`≥0.8` = aplicar por defecto, `<0.4` = omitir), y `source` (`live_correction` = capturada directamente de una corrección del usuario, confidence `0.9`; `retrospective` = inferida al cierre de `/m-dev-reflect`, confidence `0.6`).

Las escrituras a memoria son parte del workflow compartido — ambos agentes pueden actualizar archivos
de `memory/` directamente como persistencia local de memoria, incluyendo capturar una corrección en
vivo en `global_rules.json` en el momento en que el usuario corrige un enfoque en curso (ver "Capture
Corrections as They Happen" en `skills/m-dev/SKILL.md` — no esperar a que `/m-dev-reflect` la
reconstruya retrospectivamente). Preguntar antes de transiciones o comentarios de Jira, salvo que el
usuario haya pedido explícitamente el flujo que los incluye (ej. modo closing de `/m-dev-reflect`,
`/m-dev-assess`).

Índice de memoria de proyecto de Claude importado (legacy — preferir `memory/` para aprendizajes
nuevos salvo que el usuario pida explícitamente actualizar la memoria de Claude): ver
`CLAUDE_MEMORY_INDEX` en `config.sh`.

## Contexto de negocio (`Business/`)

Separado de `memory/` de arriba — `memory/` es historial operativo a nivel ticket, `Business/<cliente>/`
es conocimiento estable a nivel cliente (contexto de negocio, scripts, credenciales, información
confidencial) que no cambia de ticket a ticket. Free-form a propósito: sin schema obligatorio, las
skills simplemente leen los archivos que estén presentes. Un archivo de conveniencia opcional,
`client.md` (front-matter `repos:` / `jira_key:`), le permite a `skills/m-dev-assess/SKILL.md` mapear
repos de `projects/` de vuelta a un cliente — se ofrece, nunca es obligatorio, y `/m-dev-assess` nunca
bloquea por su ausencia. Las credenciales nunca se piden en el chat:
`skills/m-manager-create/SKILL.md` deja un archivo placeholder en blanco para que el usuario lo
complete a mano. Solo `Business/README.md` está trackeado en git; el contenido real de cliente es
gitignored y las skills nunca asumen un layout de VCS en particular para eso (repo único, un repo por
cliente, o sin versionar).

## Adaptador compartido de skills

Las fuentes canónicas de las skills viven en `skills/`. Claude Code las descubre automáticamente vía
symlinks en `.claude/skills/<name>` → `../../skills/<name>` (commiteados a git, sin paso de
generación necesario) — sin config adicional del lado de Claude. Codex no tiene un auto-discovery
equivalente confiable, así que este archivo es el camino de resolución: cuando la intención del
usuario matchea una de las filas de abajo, leer directamente el `skills/<name>/SKILL.md`
correspondiente y ejecutar ese workflow con los argumentos del usuario como `$ARGUMENTS`.

| Intención del usuario | Fuente de la skill |
| --- | --- |
| Setup inicial / chequeo de credenciales y salud del entorno | `skills/m-dev-setup/SKILL.md` |
| Workflow completo de ticket (rama, desarrollo, validación, commit, push) | `skills/m-dev/SKILL.md` |
| Idea/requerimiento nuevo sin ticket todavía — spec + crear ticket en Jira | `skills/m-dev-create/SKILL.md` |
| Deep dive técnico / assessment antes de codear | `skills/m-dev-assess/SKILL.md` |
| Crear un PR o manejar comentarios de revisión | `skills/m-dev-pr/SKILL.md` |
| Snapshot / reflexión de cierre, persistir aprendizajes | `skills/m-dev-reflect/SKILL.md` |
| Retomar un ticket ya en curso | `skills/m-dev-resume/SKILL.md` |
| Revisar el PR de un compañero ("review <URL del PR>") | `skills/m-dev-review/SKILL.md` |
| Workflow de migración de DB (el repo que sea dueño de tus migraciones SQL) | `skills/m-dev-migration/SKILL.md` |
| Estado de solo lectura de ticket/workspace | `skills/m-dev-status/SKILL.md` |
| Traer un snapshot de la DB de producción | `skills/m-dev-db-sync/SKILL.md` |
| Bootstrap de `Business/<cliente>/` para un cliente nuevo | `skills/m-manager-create/SKILL.md` |
| Refrescar/mantener el `Business/<cliente>/` de un cliente existente | `skills/m-manager-update/SKILL.md` |
| Digest de solo lectura de estado/catch-up de cliente, propuestas | `skills/m-manager-status/SKILL.md` |
| Digest consolidado dev+clientes (fusión de m-dev-status + m-manager-status) | `skills/m-manager-digest/SKILL.md` |
| Ejecutar una tarea en la infraestructura remota de un cliente (SSH/VPS), sin repo local | `skills/m-manager-exec/SKILL.md` |
| Conversar un requerimiento de cliente / listar clientes conocidos / rutear a cualquiera de las anteriores | `skills/m-manager/SKILL.md` |

`skills/m-dev/SKILL.md` es el orquestador: cuando un pedido no matchea claramente ninguna de las otras
filas, empezar ahí — rutea al resto vía su propia tabla de dispatch (incluyendo un chequeo de
precondiciones que rutea a `skills/m-dev-setup/SKILL.md` cuando faltan credenciales/config).

`skills/m-manager/SKILL.md` es un orquestador separado para pedidos de capa de negocio — nunca crea o
edita código, tickets de Jira, o PRs por sí mismo, pero su Fase 2 (intake de requerimiento) puede
delegar un requerimiento de cliente hacia afuera: a `skills/m-dev/SKILL.md` (que rutea a
`m-dev-create` para crear el ticket) cuando necesita desarrollo local, o a
`skills/m-manager-exec/SKILL.md` cuando necesita ejecución en la infraestructura remota propia del
cliente en vez de un repo bajo `projects/`. `skills/m-dev-assess/SKILL.md` delega a
`skills/m-manager-create/SKILL.md` automáticamente la primera vez que se encuentra con un repo sin
asociación de cliente bajo `Business/`.

### Caja de herramientas de scripts locales

`scripts/local/` es una caja de herramientas creciente, gitignored, por proyecto, que las skills
`/m-dev-*` se escriben a sí mismas — scripts chicos que reemplazan re-derivar el mismo procedimiento
multi-paso (y re-gastar tokens en eso) en cada sesión. Antes de improvisar un procedimiento
multi-paso de shell/git/gh/jq, leer `scripts/local/MANIFEST.json` — puede que ya exista un script
para eso. Cuando te encuentres derivando un procedimiento determinístico y repetible que valga la pena
conservar, escribilo ahí y registralo en el manifest. Convención completa:
`skills/m-dev/references/local-scripting.md`.

### Reglas de resolución de comandos

- No tratar `/m-dev-*` como un slash command literal de Codex. Resolverlo como: leer el
  `skills/<name>/SKILL.md` correspondiente y ejecutar ese workflow con los argumentos dados.
- Cuando una skill delega en otra (ej. `/m-dev` → `/m-dev-assess`), detener la fase actual y seguir
  primero el archivo de la skill delegada, exactamente como dice.
- `$ARGUMENTS` en un archivo de skill significa los argumentos provistos por el usuario o por la
  delegación de la skill padre.
- Las mecánicas de UI/CLI de Claude que aparecen en los archivos de skills tienen fallbacks para
  Codex — esta lista es la tabla de traducción canónica; no volver a derivarla por skill, y
  extenderla acá (no localmente) cuando aparezca una nueva:
  - `/rename ...`: no-op en Codex; mantener el título pretendido en el resumen de trabajo si es útil.
  - `/recap`: resumir a partir del contexto disponible en su lugar.
  - `/loop`: tratar como una sola iteración salvo que se haya pedido explícitamente monitoreo continuo.
  - `Task(...)` / delegación a subagente: hacer el trabajo localmente salvo que el usuario pida explícitamente delegación en paralelo.
  - `/code-review ultra` (llamado después de crear el PR en `/m-dev-pr`; `/ultrareview` era el nombre
    viejo de lo mismo, ahora deprecado): esto lanza una revisión en la nube, facturada, exclusiva de
    Claude Code, que ni Codex ni siquiera un agente de Claude Code plano pueden disparar
    programáticamente. Hacer en su lugar un pase de code review normal de Codex, enfocado en bugs,
    regresiones, seguridad, y tests.
  - `Ctrl+B` (el atajo de ejecución en background de Claude Code, usado ej. en la Fase 4 de `/m-dev`
    para test suites lentas): sin equivalente en Codex — correr el paso lento secuencialmente, o
    avisarle al usuario que está corriendo para que pueda trabajar en otra cosa mientras espera.
  - `claude --worktree -C <path>` (usado en la Fase 3 de `/m-dev` para desarrollo paralelo
    multi-repo): sin flag equivalente directo en Codex. Si realmente hace falta trabajo simultáneo
    entre repos, o correr sesiones de Codex secuencialmente por repo, o armar vos mismo las copias
    aisladas primero con `git worktree add <path> <branch>` antes de arrancar Codex en cada una.
  - Si `jq` no está disponible en el entorno (varias skills leen/escriben `memory/*.json` vía `jq`),
    usar el módulo `json` de Python para el mismo read-modify-write en vez de saltear la actualización
    de memoria.

Preservar cada gate de seguridad escrito en los archivos de skills: preguntar antes de operaciones
destructivas, antes de pushes, antes de transiciones/comentarios de Jira, y antes de cualquier otro
cambio de estado externo — salvo que el usuario ya lo haya autorizado en la conversación actual.

## Jira

Usar los scripts en vez de duplicar credenciales de Jira:

`uv run <JIRA_SCRIPTS de config.sh, o scripts/jira-communication/scripts si no está seteado>/<core|workflow>/<script>.py <comando> ...`

Comandos comunes — `--json` es una opción top-level y debe ir **antes** del subcomando
(`jira-issue.py --json get <KEY>`, no `get <KEY> --json`) o el CLI lo rechaza:

- `core/jira-issue.py --json get <ISSUE_KEY>`
- `core/jira-search.py --json query "<JQL>"`
- `utility/jira-qa-gather.py --json <ISSUE_KEY>` — agregación en una sola llamada (comentarios,
  worklog, links estructurados, URLs de PR/commit extraídas de la prosa, tickets hermanos) en vez de
  varias llamadas separadas; preferir esto sobre `jira-issue.py get` cuando hace falta más que los
  campos básicos.
- `workflow/jira-comment.py add <ISSUE_KEY> "<texto>"`
- `workflow/jira-transition.py do <ISSUE_KEY> "<transition>"`
- `workflow/jira-create.py issue <PROJECT_KEY> "<summary>" -t <type> -d "<description>" --parent <EPIC_KEY>`

**Redirigir cualquier salida `--json` a través de `scripts/jira_trim.py`** antes de que entre al
contexto — `uv run ... | python3 "$WS/scripts/jira_trim.py"`. Las respuestas crudas de la API de Jira
son 30-50% campos null, links `self`, y (para `qa-gather`) una copia HTML duplicada de cada campo; el
trim quita todo eso sin pérdida de información. Cada call site `--json` en las skills `m-dev-*` ya
hace esto — hacer lo mismo para cualquier caso nuevo.

Base URL y project key de Jira: ver `config.sh` (`JIRA_BASE_URL`, `PROJECT_KEY`). Si las credenciales
de Jira todavía no están configuradas (falta `~/.env.jira`), correr `skills/m-dev-setup/SKILL.md`
primero — necesita una terminal real, no este agente, ya que el prompt del token no se puede
automatizar.

## Reglas de trabajo del workspace

- Este workspace contiene varios repos — ver `REPOS` en `config.sh`. Determinar el/los repo(s) afectado(s) antes de editar — ver `CLAUDE.md` para el mapa de arquitectura completo.
- Los repos que matchean `SPECIAL_REPO_PATTERNS` (en `config.sh`) usan `SPECIAL_REPO_BASE` como rama base; todo lo demás usa `master`.
- `/m-dev-db-sync` solo está configurado para los repos listados en `DB_SYNC_REPOS` en `config.sh` (vacío significa deshabilitado).

## Actualizar este adaptador

Si una sesión futura descubre una regla nueva y recurrente que debería afectar tanto a Claude como a
Codex, agregarla acá. Los detalles específicos de un ticket van en `memory/tickets/` o
`memory/snapshots/`, no acá.
