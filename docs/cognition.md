# Continuidad cognitiva de Charly

Charly es el agente que corre sobre este harness. Este documento describe su **estado propio**:
`memory/cognition.json`, separado del modelo del usuario (`memory/user_profile.json`). El objetivo
es operativo y verificable: que el agente recuerde experiencias, reconozca cuándo vuelven a ser
relevantes y ajuste sus decisiones según los resultados. **No** es una personalidad ni una
afirmación de conciencia; nada de lo que sigue lo implica.

## Arquitectura

```
                   escritura (única vía)                         lectura (nunca escribe)
skills / agente ──► memory_store.py cognitive <op> ──► cognition.json ◄── cognition.py status|context|recall|metrics|tick
   JSON stdin           │  lock compartido (memory/.lock)                 │
                        │  cognition_model.apply() + validate_doc()       ├─► session_context.py (SessionStart)
                        │  reemplazo atómico, backup diario               └─► context_hook.py (repo/cliente tocado)
                        ▼
              self_model.py --refresh ──► agent.blind_spots
```

| Archivo | Rol |
|---|---|
| `scripts/cognition_model.py` | Esquema, validación y operaciones puras (sin I/O). |
| `scripts/memory_store.py` | `cognitive <op>`: corre cada operación como una transacción bajo el lock existente, valida y reemplaza atómicamente. `restore`: restauración explícita y validada. |
| `scripts/cognition.py` | Lectura: `status`, `context`, `recall`, `metrics`, `tick`. Reutiliza la resolución de repos, clientes, alias y temas de `memory_query.py`. |
| `scripts/self_model.py` | `--refresh` guarda los puntos ciegos en `agent.blind_spots`; sin flag, la consulta histórica de siempre. |
| `scripts/session_context.py`, `scripts/context_hook.py` | Inyectan identidad, puntos ciegos, pendientes, objetivos y experiencias del alcance. |
| `tests/test_cognition.py` | Pruebas en workspaces temporales (CI: `.github/workflows/tests.yml`). |

### Esquema (`schema_version: 1`)

- `agent`: `name`, `purpose`, `blind_spots[]`, `blind_spots_updated_at`, `migrated_from`.
- `episodes[]`: `id` (`ep-0001`…), `created_at`, `status` (`pending`|`evaluated`), `ticket`, `tags`,
  `context`, `action`, `prediction`, `probability`, `recalled[]`, `corrects`, `evaluation`
  (`evaluated_at`, `observation`, `interpretation`, `adjustment`, `evidence[]`, `outcome`).
- `goals[]`: `id` (`goal-0001`…), `title`, `reason`, `next_action`, `success_criterion`,
  `priority` (1 = máxima … 5), `tags`, `depends_on[]`, `activate_at`, `status`
  (`active`|`blocked`|`paused`|`done`|`abandoned`), `blocked_reason`, `history[]`.
- `beliefs[]`: `id` (`bel-0001`…), `type` (`capability`|`limitation`|`strategy`), `claim`,
  `scope_tags`, `confidence`, `evidence[]`, `counter_evidence[]`, `status`
  (`active`|`superseded`|`archived`), `supersedes`, `superseded_by`, `archive_reason`.

Todas las fechas son ISO 8601 **con zona horaria**. Una fecha sin zona se rechaza.

## Comandos

### Escritura: `python3 scripts/memory_store.py cognitive <op>`

El payload entra como JSON por stdin y la salida es `{"ok": true, "op": …, "result": …}`. Si falla,
devuelve `{"ok": false, "kind": …, "error": …}` con código de salida 1 cuando el payload es inválido
(`validation`/`input`) o 2 cuando el archivo no se puede tocar (`corrupt`/`incompatible_schema`).
Cualquier campo desconocido se rechaza.

| Operación | Campos (obligatorios en **negrita**) |
|---|---|
| `init` | — (crea el estado e importa el `self_model` legado; idempotente) |
| `experience` | **context**, **action**, **prediction**, **probability** (0–1), tags, recalled, corrects, ticket |
| `evaluate` | **id**, **observation**, **outcome** (`true`/`false`/`null`), interpretation, adjustment, evidence |
| `goal` | **title**, **reason**, **next_action**, **success_criterion**, priority, tags, depends_on, activate_at, status, blocked_reason |
| `update-goal` | **id**, status, note, evidence, reopen, blocked_reason, title, reason, next_action, success_criterion, priority, tags, depends_on, activate_at |
| `belief` | **type**, **claim**, **confidence**, **evidence**, scope_tags, counter_evidence, supersedes |
| `archive-belief` | **id**, **reason** |
| `set-blind-spots` | **blind_spots**, computed_at (lo usa `self_model.py --refresh`) |
| `set-agent` | name, purpose |

Reglas que el código aplica:

- **Experiencias:**
  - `recalled` y `corrects` tienen que apuntar a episodios existentes.
  - `corrects` solo puede apuntar a un episodio ya evaluado.
- **Evaluaciones:**
  - Son finales. Para corregir una, se registra otro episodio con `"corrects": "<id>"`.
  - Un `outcome` determinado (`true`/`false`) exige al menos una referencia en `evidence`.
  - `null` significa indeterminado: no cuenta como éxito ni como fracaso.
- **Objetivos:**
  - Se rechazan las dependencias inexistentes y los ciclos.
  - `blocked` exige `blocked_reason`.
  - `done` exige `evidence`.
  - Un objetivo `done` o `abandoned` solo cambia si se reabre con `"reopen": true` y un status abierto. La historia se conserva.
- **Creencias:**
  - La evidencia (a favor y en contra) tiene que ser episodios evaluados con resultado determinado.
  - Una `capability` necesita al menos 2 episodios a favor.
  - La confianza no puede superar `(a_favor + 1) / (a_favor + en_contra + 2)`. Repetir un id o volver a afirmar la misma creencia no la sube; la contraevidencia la baja.
  - `supersedes` revisa una creencia en la misma transacción: la anterior queda `superseded` con `superseded_by`.
- **Higiene del contenido:**
  - Los textos tienen un límite de 1200 caracteres: es un resumen, no una transcripción.
  - Se rechazan los textos que parecen contener secretos (claves privadas, tokens, `password: …`).

### Lectura: `python3 scripts/cognition.py <cmd>`

- `status`: identidad, puntos ciegos, pendientes, objetivos por estado y qué está listo para avanzar.
- `context [--repos --clients --topics --text] --budget N`: un bloque Markdown de **N caracteres como
  máximo**, con identidad, predicciones pendientes, objetivos abiertos, experiencias evaluadas
  relevantes y creencias del alcance.
- `recall [... ] [--limit] [--include-pending]`: experiencias ordenadas por puntaje. El puntaje
  combina el alcance (repo exacto > cliente/alias > tema > universal), la superposición de palabras
  con `--text` y la antigüedad (vida media de 180 días). Un fallo pesa un poco más, porque es el
  recuerdo más informativo. Una experiencia de otro repo no aparece.
- `metrics`:
  - Cantidad de experiencias pendientes y evaluadas, y de resultados determinados.
  - **Brier** (promedio de `(probabilidad − resultado)²`) total y de las últimas 20 evaluaciones.
  - Cantidad y tasa de éxito de los episodios con y sin recuerdos declarados.
  - Los `null` quedan excluidos de todos los cálculos.
- `tick [--limit N] [--now ISO]`: ver "Iniciativa".

### Ejemplo: el ciclo completo

```bash
# 1. Predecir antes de actuar
echo '{"context":"PROJ-700: migración de esquema","ticket":"PROJ-700","tags":["backend-api"],
  "action":"Migrar sin snapshot de prod","prediction":"La migración termina sin errores en staging",
  "probability":0.9}' | python3 scripts/memory_store.py cognitive experience
# → {"ok": true, "op": "experience", "result": {"id": "ep-0001", "status": "pending"}}

# 2. Contrastar cuando hay evidencia
echo '{"id":"ep-0001","outcome":false,"observation":"Falló por un índice duplicado",
  "interpretation":"Staging tenía datos que dev no","adjustment":"Validar contra snapshot de prod",
  "evidence":["log staging 2026-10-30","PR #12"]}' | python3 scripts/memory_store.py cognitive evaluate

# 3. Otra sesión, mismo alcance: recordar
python3 scripts/cognition.py recall --repos backend-api --text "migración de esquema"

# 4. Decidir influido por ese recuerdo (declararlo) y volver a contrastar
echo '{"context":"PROJ-712: otra migración","tags":["backend-api"],"recalled":["ep-0001"],
  "action":"Validar contra snapshot de prod antes de migrar",
  "prediction":"La migración termina sin errores en staging","probability":0.75}' \
  | python3 scripts/memory_store.py cognitive experience
```

## Iniciativa (`tick`) y scheduler

`tick` hace **un único pase de solo lectura** y devuelve, con `mode: "proposal_only"`, los objetivos
`active` que cumplen dos condiciones: su `activate_at` ya pasó (o no tiene) y todas sus dependencias
están `done`. Salen ordenados por prioridad y luego por fecha, hasta `--limit` (3 por defecto). Los
que todavía no pueden avanzar aparecen en `not_ready`, con el motivo.

`tick` nunca:
- ejecuta el texto de un objetivo;
- escribe en memoria;
- desbloquea un objetivo por inferencia;
- concede permisos.

`activate_at` indica **desde cuándo corresponde revisar** el objetivo. **No es un deadline.**

En esta versión la iniciativa aparece cuando algo activa al agente:
- el arranque de sesión (`session_context.py` muestra hasta 3 propuestas);
- `/m-manager digest`;
- una llamada explícita a `tick`.

No se instala ningún cron, ni hay daemon, ni llamadas ocultas a modelos. Para correrlo con un
scheduler externo (la decisión de instalarlo es del usuario):

```cron
# Lunes 09:00 en la zona horaria del servidor (revisarla con `date`), solo lectura:
0 9 * * 1  cd /ruta/al/workspace && python3 scripts/cognition.py tick --limit 5 > memory/tick-last.json
```

Ese JSON lo puede leer `/m-manager digest`, o se puede reenviar por el aviso de `/m-infra-clean`. Para
que alguien **actúe** sobre una propuesta hace falta una sesión, con los permisos y las
confirmaciones de siempre.

## Migración desde el `self_model` legado

- **Antes de inicializar:** `cognition.py` arma un estado virtual con `user_profile.json →
  self_model.top_blind_spots`, sin crear ni modificar archivos (`status` muestra `source: legacy`).
- **Al inicializar:** `memory_store.py cognitive init`, o la primera escritura cognitiva, crea
  `cognition.json` e importa los puntos ciegos una sola vez (queda registrado en
  `agent.migrated_from`). Repetirlo no cambia nada. `user_profile.json` no se modifica.
- **Después:** `cognition.json` tiene precedencia. `/m-dev-reflect` corre `self_model.py --refresh`,
  que escribe ahí. Si alguna fuente de memoria no se puede leer, sale con código 2 y no reemplaza el
  modelo guardado.

## Robustez

- Usa el mismo lock, la misma escritura atómica y el mismo backup diario que el resto de
  `memory/`; el estado nuevo entra solo en `memory/.backups/`.
- Un archivo corrupto, o con un `schema_version` distinto de 1, nunca se reinicializa. Las escrituras
  salen con código 2, las lecturas avisan, `memory_store.py validate` lo reporta y la sesión lo
  muestra al arrancar.
- `memory_store.py restore <backup> <archivo>` valida la copia y muestra un resumen. Con `--apply`
  hace primero un backup del estado actual y después reemplaza. Sirve para cualquier archivo de
  `memory/`.
- `cognition.json` se crea con permisos `0660` y está en gitignore, como todo `memory/`.

## Pruebas

`python3 -m unittest discover -s tests -v` (también corre en CI). Cubre:

- el caso de aceptación de punta a punta;
- recuperación tras reiniciar el proceso;
- aislamiento por repo y alias de cliente;
- migración idempotente sin tocar el perfil;
- 24 escrituras concurrentes;
- corrupción y schema incompatible;
- validación de probabilidades, referencias, estados, campos desconocidos y secretos;
- dependencias, ciclos, bloqueos, reapertura y zonas horarias;
- revisión de creencias con historial y tope de confianza;
- presupuesto del contexto;
- límite de propuestas de `tick`, y que `tick` no ejecute nada;
- compatibilidad con los comandos anteriores, el backup y el restore validado;
- `self_model --refresh`;
- los hooks.

## Límites

- **La relevancia es léxica:** alcance por tags más superposición de palabras, sin embeddings. Una
  experiencia descrita con otras palabras, o en otro idioma, puede no aparecer por texto. El alcance
  por tags sí funciona.
- **El valor depende de la disciplina de registro.** El código no puede saber si una predicción se
  escribió antes del resultado; la regla "nada retroactivo" la cumple el agente, no el validador.
  Tampoco puede saber si `recalled` refleja una influencia real.
- **Las métricas son descriptivas.** Con pocas evaluaciones, el Brier es ruido. La comparación con y
  sin recuerdos no demuestra causalidad, porque las tareas difieren, y no dice nada sobre conciencia.
- **El detector de secretos es heurístico.** Ataja los formatos comunes, no todos.
- **`tick` no es un scheduler:** propone cuando alguien lo invoca.
