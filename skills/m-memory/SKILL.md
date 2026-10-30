---
name: m-memory
description: "Maintenance and inspection of the harness memory (memory/): health stats and schema validation, ranked queries by repo/client/topic, backups and restore, and the periodic consolidation pass — merge semantic duplicates (including across languages), archive stale retrospective rules, fix orphan tags, and propose promoting mature rules into the owning repo's CLAUDE.md. Every change goes through scripts/memory_store.py (locked, atomic, reversible). Use for '/m-memory', '/m-memory stats', '/m-memory query <repo|cliente> [texto]', '/m-memory consolidate', '/m-memory backup', '/m-memory restore <archivo>', or when the SessionStart digest says a consolidation is overdue and the user agrees."
allowed-tools: Bash Read Write Edit
---

# Memory — mantenimiento de la memoria del harness

Run for: **$ARGUMENTS** (default `stats`).

Scripts (all under `$WS/scripts/`, pure Python, no deps):

| Script | Rol |
|---|---|
| `memory_store.py` | **Único camino de escritura.** Lock (`memory/.lock`), temp único + `os.replace`, validación de schema, ids asignados bajo lock, nunca reinicializa un archivo que no parsea. `-h` lista los comandos. |
| `memory_query.py` | Lectura rankeada y con presupuesto (repo/cliente/tema/texto). Reemplaza los filtros `jq` por igualdad de tags. |
| `memory_compile.py` | Regenera `memory/compiled/*.md` (digest por repo y por cliente). Corre solo tras cada escritura. |
| `context_hook.py` | Hook `UserPromptSubmit`/`PostToolUse`: inyecta el digest compilado la primera vez que la sesión toca un repo o nombra un cliente. |
| `memory_consolidate.py` | Prepara la consolidación (candidatos); vos juzgás y aplicás. |
| `memory_migrate.py` | Upgrade idempotente del schema (ids únicos, fechas). Solo tras cambiar el schema. |

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
```

## `stats` (default) — solo lectura

```bash
python3 $WS/scripts/memory_store.py stats
python3 $WS/scripts/memory_store.py validate
```

Reportar en 3-5 líneas: totales, reforzadas vs nunca reforzadas, errores de validación, último backup,
fecha de la última consolidación (`memory/consolidation/last.json`). Si `validate` falla, eso va primero.

## `query <repo|cliente> [texto]` — solo lectura

```bash
python3 $WS/scripts/memory_query.py --detect "<argumento>"      # resuelve repo/cliente
python3 $WS/scripts/memory_query.py --repos <repos> --clients <clientes> --text "<texto>" --budget 10000
```

## `backup` / `restore <archivo>`

`python3 $WS/scripts/memory_store.py backup` (también corre solo, una vez por día, desde el hook de
SessionStart; guarda 14). `backup --list` para ver los disponibles.

Restore es una operación destructiva sobre memoria compartida entre sesiones: **mostrar el diff y pedir
OK antes de reemplazar**:

```bash
R=$(mktemp -d); tar -xzf $WS/memory/.backups/<backup>.tar.gz -C "$R" memory/<archivo>
diff <(python3 -m json.tool "$R/memory/<archivo>") <(python3 -m json.tool "$WS/memory/<archivo>") | head -80
# tras el OK:
python3 $WS/scripts/memory_store.py write <archivo> < "$R/memory/<archivo>"
```

## `consolidate` — el pase periódico

El objetivo es que la memoria **no solo crezca**: que una lección repetida se refuerce en vez de
duplicarse, que lo viejo y nunca confirmado deje de competir por contexto, y que lo maduro pase a la
documentación versionada del repo, donde lo ve todo el equipo.

1. Backup y reporte:
   ```bash
   python3 $WS/scripts/memory_store.py backup
   python3 $WS/scripts/memory_consolidate.py --md > /tmp/memconsol.md   # o el scratchpad de la sesión
   ```
2. **Duplicados semánticos.** Leer `lexical_pairs` primero y después cada grupo de `review_groups`
   completo (el universal y los de más de 10 reglas son los que importan). La similitud por palabras
   no ve paráfrasis ni traducciones (hay reglas viejas en inglés y nuevas en español): esto lo juzgás
   vos. Para cada conjunto que diga lo mismo:
   - quedarse con la redacción más clara y completa (en español) y, si hace falta, reescribirla con
     `add-rule --supersedes <id>` (el confidence de la nueva = el mayor del conjunto, `--source` el más
     fuerte: `live_correction` si alguna lo era);
   - el resto: `set-rule <id> --status superseded --superseded-by <id-que-queda>`;
   - si una solo refuerza a otra sin aportar nada: `reinforce-rule <id-que-queda> --ticket <origen>` y
     superseder la redundante.
   Ante la duda, **no fusionar**: dos reglas parecidas cuestan poco; una regla perdida cuesta un error.
3. **Stale** (`stale`): proponer `set-rule <id> --status archived` en bloque — es reversible, el rank las
   ignora. No archivar `live_correction` nunca.
4. **Tags huérfanos** (`orphan_tags`): o se corrige el tag (`set-rule <id> --tags ...`), o se agrega un
   alias en `memory/tag_aliases.json` (`clients` / `repo_aliases` / `topics`, ver `_doc` adentro; crear
   el archivo vía `memory_store.py write tag_aliases.json` si no existe).
5. **Promoción** (`promote`): estas reglas son conocimiento de un repo concreto que conviene versionar
   en su `CLAUDE.md` (o en `ia-memory/` si el repo usa esa carpeta). Eso **modifica otro repo** —
   presentar la lista agrupada por repo y pedir OK explícito; con OK, agregarlas en la sección que
   corresponda del `CLAUDE.md` (redactadas como documentación, no como lista de ids) sin commitear, y
   marcar cada una `set-rule <id> --status archived` para que no se inyecte dos veces. Respetar las
   reglas de cada repo para tocarlo (checkout compartido, prod, ramas).
6. Cerrar:
   ```bash
   python3 $WS/scripts/memory_consolidate.py --mark-done "<n fusionadas, n archivadas, n promovidas>"
   python3 $WS/scripts/memory_store.py stats
   ```
   Resumen al usuario: qué cambió, en números, y qué quedó pendiente de su OK.

## Reglas

- Nunca editar `memory/*.json` a mano ni con `jq > archivo`: siempre `memory_store.py`.
- Nunca borrar entradas: `superseded`/`archived` son el mecanismo (reversibles, auditables).
- `memory/compiled/` es derivado: no editarlo, se regenera.
- Si `validate` o cualquier comando devuelve exit 2 (archivo que no parsea): frenar, avisar, y
  proponer el restore del último backup que parsee. No "arreglarlo" reinicializándolo.
