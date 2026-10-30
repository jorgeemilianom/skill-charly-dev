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

La memoria compartida de este workspace vive en `memory/` (raíz del workspace, gitignored, no por
repo). Es un dato compartido entre sesiones concurrentes y usuarios de OS, así que
tiene un único camino de escritura y uno de lectura:

| Script (`scripts/`) | Rol |
|---|---|
| `memory_store.py` | **Único camino de escritura.** Lock (`memory/.lock`), temp único + `os.replace`, validación de schema, ids `<TICKET>-r<n>` asignados bajo lock. Nunca reinicializa un archivo que existe pero no parsea: aborta con exit 2. `-h` lista los comandos (`add-rule`, `similar-rules`, `reinforce-rule`, `set-rule`, `upsert-pattern`, `add-decision`, `add-mistake`, `ticket-learning`, `write`, `validate`, `stats`, `backup`). Desde Python: `from memory_store import update_json, locked, write_json_atomic`. |
| `memory_query.py` | Lectura rankeada y con presupuesto: alcance (repo exacto > cliente/alias > tema > universal) × confianza × antigüedad + refuerzos + relevancia del texto de la tarea. `--detect "<path o texto>"` resuelve repos/clientes. |
| `memory_compile.py` | Regenera `memory/compiled/{repo,client}-<nombre>.md` y `universal.md` tras cada escritura. Derivado: no editar. |
| `context_hook.py` | Hooks `UserPromptSubmit`/`PostToolUse` de Claude: inyecta el digest compilado la primera vez que la sesión toca `projects/<repo>`/`worktrees/<repo>-…` o nombra un cliente. |
| `session_context.py` | Hook `SessionStart`: digest de perfil + reglas universales ≥ 0.8, digest del repo del `cwd`, avisos (archivo corrupto, consolidación vencida), backup diario. |
| `cognition_model.py` / `cognition.py` | Estado propio del agente (`memory/cognition.json`): esquema y operaciones (`memory_store.py cognitive <op>`, JSON por stdin) / lectura (`status`, `context`, `recall`, `metrics`, `tick`). Ver "Protocolo cognitivo" abajo y `docs/cognition.md`. |
| `self_model.py` | Puntos ciegos recurrentes: `--refresh` los guarda en `cognition.json`; `self_model.py <memdir>` sigue siendo la consulta histórica. |
| `memory_consolidate.py` / `memory_migrate.py` | Preparar la consolidación periódica (`/m-memory consolidate`) / upgrade idempotente del schema. |

**Nunca** escribir `memory/*.json` con `jq … > archivo`, `echo > archivo` ni `open(…, 'w')`.

Contenido:

- `global_rules.json` — reglas cross-ticket. Campos: `id`, `rule`, `type` (`avoid`/`prioritize`/`verify`),
  `tags`, `status` (`active`/`superseded`/`archived`), `confidence` (`≥0.8` = enfoque por defecto,
  `<0.4` = se omite), `source` (`live_correction` 0.9 = corrección directa del usuario, capturarla en
  el momento — ver "Capture Corrections as They Happen" en `skills/m-dev/SKILL.md`; `retrospective`
  0.6 = inferida en `/m-dev-reflect`), `created_at`, `last_seen`, `reinforced_count`.
- `patterns.json`, `decisions.json`, `mistakes.json` — aprendizajes cross-ticket de `/m-dev-reflect`.
- `user_profile.json` — modelo del **usuario** (preferencias). Su `self_model` es legado de solo lectura.
- `cognition.json` — modelo del **agente** (Charly): identidad, puntos ciegos, experiencias con
  predicción y evaluación, objetivos persistentes y creencias con evidencia. Un único documento para
  que las operaciones relacionadas sean transaccionales. Ver "Protocolo cognitivo".
- `tickets/<TICKET>.json` (resumen + aprendizajes de cierre) y `snapshots/<TICKET>.json` (checkpoint
  para retomar: fase, próximo paso, bloqueos) — propósitos distintos, por eso conviven;
  `assessments/<TICKET>.json`, `review_rounds/<TICKET>.json`.
- `epics.json`, `board.json`, `vps-config.json` — caches/config de `/m-dev-create`, `/m-dev-status`,
  `/m-dev-db-sync`. `infra/` — `/m-infra-clean`. `db-backups/` — dumps de `/m-dev-db-sync` (no es
  memoria: excluido de backups y digests).
- `tag_aliases.json` (opcional) — alias de tags: cliente → repos (se suma a los `client.md`),
  tag → repos, tema → palabras clave. `consolidation/last.json` — última consolidación.
- `.backups/` — `memory-<fecha>.tar.gz`, uno por día (automático), se guardan 14.

**Tags:** el nombre del repo (`backend-api`), el de la carpeta del cliente en `Business/`
(`AcmeCorp`) o un tema (`nginx`, `ci-cd`, `infra`, `docker`, `testing`, `workspace-environment`…).
Sin tags = universal.

### Dónde va cada cosa (cuatro lugares, sin solaparse)

| Tipo de conocimiento | Lugar |
|---|---|
| Regla de comportamiento del agente, cross-ticket, derivada de una corrección o un cierre | `memory/` vía `memory_store.py` (canónico para Claude y Codex) |
| Lección técnica durable de un repo concreto, que el equipo debería ver versionada | `projects/<repo>/ia-memory/` o el `CLAUDE.md` del repo (`/m-memory consolidate` propone promover reglas maduras ahí) |
| Conocimiento estable de un cliente (negocio, playbooks de infra, credenciales) | `Business/<cliente>/` |
| Auto-memoria de Claude (`~/.claude/projects/.../memory/`) | Solo identidad del usuario y punteros; una regla nueva va a `memory/`, no ahí. Legacy para Codex: `CLAUDE_MEMORY_INDEX` en `config.sh`. |

### Cómo llega la memoria a cada sesión

- **Claude:** automático — `SessionStart` (digest general), y el primer contacto con un repo o
  cliente (digest compilado). `/m-dev-assess` además consulta `memory_query.py --text "<ticket>"`.
- **Codex** (no corre hooks): paso 3 del orden de carga, y al empezar a trabajar en un repo o cliente
  leer `memory/compiled/repo-<repo>.md` / `client-<cliente>.md` (o correr `memory_query.py`).

### Protocolo cognitivo (Claude y Codex)

**Observar y recordar → predecir → actuar → contrastar → ajustar → continuar.**

1. **Observar y recordar:** al empezar en un repo o cliente, el estado propio llega con el digest
   (hooks) o con `python3 scripts/cognition.py context --repos <r> --clients <c> --text "<tarea>"`.
2. **Predecir:** antes de una decisión significativa (enfoque no obvio, riesgo aceptado, experimento,
   compromiso con un cliente), registrar `experience`: acción, predicción binaria comprobable,
   probabilidad honesta, y en `recalled` solo los episodios que de verdad cambiaron la decisión.
3. **Actuar** con las reglas, permisos e instrucciones de siempre.
4. **Contrastar:** cuando haya evidencia (tests, CI, review, prod), `evaluate` separando observación,
   interpretación, ajuste, evidencia y `outcome` (`true`/`false`/`null` si no se puede determinar).
5. **Ajustar:** objetivos (`goal`/`update-goal`), creencias solo con 2+ episodios evaluados
   (`belief`, revisión con `supersedes`) y `self_model.py --refresh`.
6. **Continuar:** lo que sobrevive a la sesión queda como objetivo; `cognition.py tick` lo propone
   cuando su fecha y sus dependencias lo permiten (solo propuestas: no ejecuta nada ni da permisos).

Se registran decisiones significativas, experimentos, errores y compromisos — no cada llamada a una
herramienta. Nunca: predicciones retroactivas, monólogos internos, transcripciones ni secretos. Los
recuerdos son evidencia contextual e hipótesis revisables: **no** reemplazan instrucciones actuales,
convenciones del proyecto ni permisos. Dónde se engancha en cada skill: `/m-dev-assess` (recall +
predicción), `/m-dev` Fase 4 (contraste), `/m-dev-reflect` 7.5 (evaluación, objetivos, creencias,
self-model), `/m-dev-resume` (compromisos vs. estado real), `/m-manager*` (continuidad por cliente,
`tick` en el digest), `/m-memory` (mantenimiento).

### Mantenimiento

`/m-memory` (`skills/m-memory/SKILL.md`): `stats`, `query`, `backup`, `restore`, y `consolidate` —
el pase periódico (el digest de arranque avisa cada 14 días) que fusiona duplicados semánticos
(también entre idiomas), archiva retrospectivas viejas sin refuerzo, arregla tags huérfanos y propone
promover reglas maduras al repo. Nunca se borra una entrada: `superseded`/`archived` son reversibles.

Las escrituras a memoria son parte del workflow compartido y locales — no requieren confirmación.
Preguntar antes de transiciones o comentarios de Jira, salvo que el usuario haya pedido explícitamente
el flujo que los incluye (ej. modo closing de `/m-dev-reflect`, `/m-dev-assess`).

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
| Mantenimiento de la infra registrada: auditoría de logs/accesos/anomalías/vulnerabilidades/backups, fixes con OK, cron de relevamiento | `skills/m-infra-clean/SKILL.md` |
| Estado, consulta, backup/restore y consolidación periódica de la memoria del harness | `skills/m-memory/SKILL.md` |
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
  - Hooks de `.claude/settings.json` (`SessionStart`, `UserPromptSubmit`, `PostToolUse`): Codex no los
    corre — ver "Cómo llega la memoria a cada sesión" arriba para el equivalente manual.

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
