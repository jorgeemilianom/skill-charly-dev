#!/usr/bin/env python3
"""Single write path for the harness memory (memory/*.json): locked, atomic, validated.

Why this exists: the skills used to persist memory with inline
`jq empty X || echo '{"rules":[]}' > X` + `jq ... > memory/tmp.json && mv ...`. Two failure modes:
  1. Any jq failure (half-written file, concurrent write, jq missing) re-initialised the file —
     silently wiping every rule/decision in it.
  2. Every session (several at once, three OS users) shared the same memory/tmp.json, with no lock,
     so concurrent writes clobbered each other.
Everything that mutates memory/ goes through here now — as a CLI from the skills' bash blocks, or
imported (`from memory_store import update_json`) from their Python snippets.

Guarantees:
  - A file that exists but does not parse is NEVER overwritten: the command aborts (exit 2) and
    points to memory/.backups/. Only a *missing* file is initialised.
  - Writes take an exclusive flock on memory/.lock, write to a unique temp file in the same dir,
    fsync, then os.replace — readers never see a partial file.
  - Collections are schema-checked before writing; ids are allocated under the lock (no more
    duplicate <TICKET>-r1 ids).
  - After every mutation the compiled per-repo digests (memory/compiled/) are regenerated.

Usage: python3 scripts/memory_store.py <command> [...]   (run with -h for the command list)
"""
import argparse
import contextlib
import copy
import datetime
import errno
import fcntl
import json
import os
import re
import sys
import tarfile
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_similarity import words  # noqa: E402

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(ROOT, "memory")
LOCK = os.path.join(MEM, ".lock")
BACKUPS = os.path.join(MEM, ".backups")
# Not memory: big or derived data, excluded from backups.
BACKUP_EXCLUDE = {".backups", "compiled", "db-backups", ".lock"}

# file -> (collection key, required fields per entry)
COLLECTIONS = {
    "global_rules.json": ("rules", ["id", "rule", "type", "status", "confidence", "source"]),
    "patterns.json": ("patterns", ["pattern", "type", "frequency", "confidence"]),
    "decisions.json": ("decisions", ["context", "decision", "outcome", "score"]),
    "mistakes.json": ("mistakes", ["ticket", "description"]),
}
RULE_TYPES = {"avoid", "prioritize", "verify"}
RULE_SOURCES = {"live_correction": 0.9, "retrospective": 0.6}


class MemoryCorrupt(Exception):
    pass


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def today():
    return datetime.date.today().isoformat()


def mem_path(name):
    path = name if os.path.isabs(name) else os.path.join(MEM, name)
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(MEM) + os.sep):
        raise ValueError(f"fuera de memory/: {name}")
    return path


def default_for(name):
    base = os.path.basename(name)
    if base in COLLECTIONS:
        return {COLLECTIONS[base][0]: []}
    return {}


def read_json(name, default=None):
    """Missing file -> copy of default. Existing but unparseable -> MemoryCorrupt (never reset)."""
    path = mem_path(name)
    if not os.path.exists(path):
        return copy.deepcopy(default if default is not None else default_for(name))
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        if not raw.strip():
            raise ValueError("archivo vacío")
        return json.loads(raw)
    except Exception as e:
        raise MemoryCorrupt(
            f"{path} existe pero no se puede leer ({e}). No se sobrescribe: revisarlo a mano o "
            f"restaurar desde {BACKUPS}/ (python3 scripts/memory_store.py backup --list)."
        ) from e


@contextlib.contextmanager
def locked(timeout=30):
    os.makedirs(MEM, exist_ok=True)
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o666)
    with contextlib.suppress(OSError):
        os.fchmod(fd, 0o666)  # shared across OS users on the same box
    deadline = time.time() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES) or time.time() > deadline:
                    raise
                time.sleep(0.1)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def validate(name, data):
    base = os.path.basename(name)
    if base not in COLLECTIONS:
        if not isinstance(data, (dict, list)):
            raise ValueError(f"{base}: se esperaba un objeto o lista JSON")
        return
    key, required = COLLECTIONS[base]
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise ValueError(f"{base}: falta la lista '{key}'")
    for i, entry in enumerate(data[key]):
        if not isinstance(entry, dict):
            raise ValueError(f"{base}[{i}]: no es un objeto")
        missing = [f for f in required if f not in entry]
        if missing:
            raise ValueError(f"{base}[{i}]: faltan campos {missing}")
        if not isinstance(entry.get("tags", []), list):
            raise ValueError(f"{base}[{i}]: 'tags' debe ser lista")
    if key == "rules":
        ids = [r["id"] for r in data[key]]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"{base}: ids duplicados {sorted(dup)}")


def write_json_atomic(name, data):
    path = mem_path(name)
    validate(path, data)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    try:
        st = os.stat(path)
        mode, gid = st.st_mode & 0o777, st.st_gid
    except FileNotFoundError:
        mode, gid = 0o664, None
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        if gid is not None:
            with contextlib.suppress(OSError):
                os.chown(tmp, -1, gid)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def update_json(name, fn, default=None, compile_after=True):
    """Locked read-modify-write. fn(data) mutates in place and/or returns a new object (or None)."""
    with locked():
        data = read_json(name, default)
        result = fn(data)
        new = data if result is None or result is True or not isinstance(result, (dict, list)) else result
        write_json_atomic(name, new)
    if compile_after:
        recompile()
    return new


def recompile():
    try:
        import memory_compile
        memory_compile.compile_all(quiet=True)
    except Exception as e:  # never block a memory write on the derived digests
        print(f"aviso: no se pudieron regenerar los digests compilados ({e})", file=sys.stderr)


def parse_tags(s):
    return [t.strip() for t in (s or "").split(",") if t.strip()]


# ---------------------------------------------------------------- rules

def next_rule_id(rules, ticket):
    used = {r["id"] for r in rules}
    n = 1
    while f"{ticket}-r{n}" in used:
        n += 1
    return f"{ticket}-r{n}"


def similar_rules(rules, text, tags, top=3, threshold=0.2):
    """Rank active rules by word overlap. Uses max(Jaccard, containment) — Jaccard alone scores a
    short restatement of a long rule near zero, which is why dedup almost never fired before."""
    new_w = words(text)
    out = []
    for r in rules:
        if r.get("status") != "active":
            continue
        r_tags = r.get("tags") or []
        if r_tags and tags and not set(r_tags) & set(tags):
            continue
        w = words(r["rule"])
        inter = len(new_w & w)
        if not inter:
            continue
        jac = inter / len(new_w | w)
        cont = inter / max(1, min(len(new_w), len(w)))
        score = max(jac, 0.8 * cont)
        if score >= threshold:
            out.append((round(score, 2), r))
    out.sort(key=lambda x: -x[0])
    return out[:top]


def cmd_add_rule(a):
    if a.type not in RULE_TYPES:
        sys.exit(f"--type debe ser uno de {sorted(RULE_TYPES)}")
    if a.source not in RULE_SOURCES:
        sys.exit(f"--source debe ser uno de {sorted(RULE_SOURCES)}")
    out = {}

    def fn(d):
        rules = d["rules"]
        if a.supersedes and not any(r["id"] == a.supersedes for r in rules):
            raise SystemExit(f"no existe la regla {a.supersedes}")
        new_id = next_rule_id(rules, a.ticket)
        for r in rules:
            if r["id"] == a.supersedes:
                r["status"] = "superseded"
                r["superseded_by"] = new_id
        conf = a.confidence if a.confidence is not None else RULE_SOURCES[a.source]
        rules.append({
            "id": new_id, "rule": a.rule.strip(), "origin_ticket": a.ticket, "type": a.type,
            "tags": parse_tags(a.tags), "status": "active", "confidence": round(conf, 2),
            "source": a.source, "created_at": today(), "last_seen": today(),
        })
        out["id"] = new_id

    update_json("global_rules.json", fn)
    print(out["id"])


def cmd_similar_rules(a):
    d = read_json("global_rules.json")
    hits = similar_rules(d["rules"], a.rule, parse_tags(a.tags), top=a.top, threshold=a.threshold)
    if not hits:
        print("SIN CANDIDATOS — se puede agregar como regla nueva")
    for score, r in hits:
        print(f"CANDIDATO {score:.0%} [{r['id']}] (conf {r['confidence']}, tags {r.get('tags') or 'universal'}): {r['rule']}")


def cmd_reinforce_rule(a):
    def fn(d):
        for r in d["rules"]:
            if r["id"] == a.id:
                r["confidence"] = round(min(r["confidence"] + 0.1, 0.95 if r["confidence"] < 0.95 else r["confidence"]), 2)
                r["reinforced_count"] = r.get("reinforced_count", 0) + 1
                r["last_seen"] = today()
                if a.ticket:
                    r["reinforced_by"] = sorted(set(r.get("reinforced_by", []) + [a.ticket]))
                if a.tags:  # a reinforcement from another repo widens the rule's scope
                    r["tags"] = sorted(set((r.get("tags") or []) + parse_tags(a.tags)))
                return
        raise SystemExit(f"no existe la regla {a.id}")

    update_json("global_rules.json", fn)
    print(f"reforzada {a.id}")


def cmd_set_rule(a):
    def fn(d):
        for r in d["rules"]:
            if r["id"] == a.id:
                if a.status:
                    r["status"] = a.status
                if a.tags is not None:
                    r["tags"] = parse_tags(a.tags)
                if a.confidence is not None:
                    r["confidence"] = round(a.confidence, 2)
                if a.superseded_by:
                    r["superseded_by"] = a.superseded_by
                return
        raise SystemExit(f"no existe la regla {a.id}")

    update_json("global_rules.json", fn)
    print(f"actualizada {a.id}")


# ---------------------------------------------------------------- patterns / decisions / mistakes

def cmd_upsert_pattern(a):
    def fn(d):
        for p in d["patterns"]:
            if p["pattern"] == a.pattern:
                p["frequency"] += 1
                p["confidence"] = round(min(p["confidence"] + 0.1, 0.95), 2)
                p["origin_tickets"] = sorted(set(p.get("origin_tickets", []) + [a.ticket]))
                p["last_seen"] = today()
                return
        d["patterns"].append({
            "pattern": a.pattern, "type": a.type, "frequency": 1, "confidence": 0.5,
            "tags": parse_tags(a.tags), "origin_tickets": [a.ticket],
            "created_at": today(), "last_seen": today(),
        })

    update_json("patterns.json", fn)
    print("ok")


def cmd_add_decision(a):
    if a.outcome not in {"success", "partial", "failure"}:
        sys.exit("--outcome debe ser success|partial|failure")
    update_json("decisions.json", lambda d: d["decisions"].append({
        "context": a.context, "decision": a.decision, "outcome": a.outcome, "score": a.score,
        "timestamp": now_iso(), "tags": parse_tags(a.tags),
    }))
    print("ok")


def cmd_add_mistake(a):
    def fn(d):
        if any(m["ticket"] == a.ticket and m["description"] == a.description for m in d["mistakes"]):
            return
        d["mistakes"].append({
            "ticket": a.ticket, "description": a.description, "context": a.context or "",
            "tags": parse_tags(a.tags), "date": today(),
        })

    update_json("mistakes.json", fn)
    print("ok")


def cmd_ticket_learning(a):
    def fn(d):
        d.setdefault("decisions", [])
        d.setdefault("learnings", [])
        if a.summary:
            d["summary"] = a.summary
        if a.learning and a.learning not in d["learnings"]:
            d["learnings"].append(a.learning)

    update_json(f"tickets/{a.ticket}.json", fn, default={"summary": "", "decisions": [], "learnings": []})
    print("ok")


def cmd_write(a):
    """Atomic whole-file write of JSON read from stdin (assessments, snapshots, board, review_rounds…)."""
    try:
        data = json.load(sys.stdin)
    except Exception as e:
        sys.exit(f"stdin no es JSON válido: {e}")
    with locked():
        write_json_atomic(a.path, data)
    if a.path in COLLECTIONS:
        recompile()
    print(f"escrito memory/{a.path}")


# ---------------------------------------------------------------- validate / stats / backup

def iter_json_files():
    for dirpath, dirnames, filenames in os.walk(MEM):
        dirnames[:] = [x for x in dirnames if x not in BACKUP_EXCLUDE and not x.startswith(".")]
        for fn in filenames:
            if fn.endswith(".json") and not fn.startswith(".tmp-"):
                yield os.path.relpath(os.path.join(dirpath, fn), MEM)


def cmd_validate(a):
    bad = 0
    for rel in sorted(iter_json_files()):
        try:
            validate(rel, read_json(rel))
        except PermissionError:
            continue
        except Exception as e:
            bad += 1
            print(f"ERROR {rel}: {e}")
    stray = [f for f in os.listdir(MEM) if f.startswith(".tmp-") or f == "tmp.json"]
    for f in stray:
        print(f"aviso: temporal huérfano memory/{f}")
    print("OK" if not bad else f"{bad} archivo(s) con errores")
    sys.exit(1 if bad else 0)


def cmd_stats(a):
    for name, (key, _) in COLLECTIONS.items():
        try:
            items = read_json(name)[key]
        except Exception as e:
            print(f"{name}: ERROR {e}")
            continue
        line = f"{name}: {len(items)}"
        if key == "rules":
            act = [r for r in items if r["status"] == "active"]
            line += (f" ({len(act)} activas, {sum(1 for r in act if not r.get('tags'))} universales, "
                     f"{sum(1 for r in act if r.get('reinforced_count'))} reforzadas)")
        print(line)
    for sub in ("tickets", "snapshots", "assessments", "review_rounds"):
        p = os.path.join(MEM, sub)
        print(f"{sub}/: {len(os.listdir(p)) if os.path.isdir(p) else 0}")
    b = sorted(os.listdir(BACKUPS)) if os.path.isdir(BACKUPS) else []
    print(f"backups: {len(b)}" + (f" (último {b[-1]})" if b else ""))


def backup(keep=14, if_older_than_hours=None, quiet=False):
    os.makedirs(BACKUPS, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(BACKUPS, 0o2770)
    existing = sorted(f for f in os.listdir(BACKUPS) if f.startswith("memory-") and f.endswith(".tar.gz"))
    if if_older_than_hours is not None and existing:
        age = time.time() - os.path.getmtime(os.path.join(BACKUPS, existing[-1]))
        if age < if_older_than_hours * 3600:
            return None
    name = f"memory-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    tmp = os.path.join(BACKUPS, "." + name)
    skipped = 0
    with locked():
        with tarfile.open(tmp, "w:gz") as tar:
            for dirpath, dirnames, filenames in os.walk(MEM):
                rel_dir = os.path.relpath(dirpath, MEM)
                if rel_dir == ".":
                    dirnames[:] = [x for x in dirnames if x not in BACKUP_EXCLUDE]
                for fn in filenames:
                    if fn == ".lock" or fn.startswith(".tmp-"):
                        continue
                    full = os.path.join(dirpath, fn)
                    try:
                        tar.add(full, arcname=os.path.join("memory", os.path.relpath(full, MEM)))
                    except (PermissionError, FileNotFoundError):
                        skipped += 1
    os.chmod(tmp, 0o600)
    os.replace(tmp, os.path.join(BACKUPS, name))
    existing.append(name)
    for old in existing[:-keep]:
        with contextlib.suppress(OSError):
            os.unlink(os.path.join(BACKUPS, old))
    if not quiet:
        print(f"backup memory/.backups/{name}" + (f" ({skipped} archivos sin permiso de lectura omitidos)" if skipped else ""))
    return name


def cmd_backup(a):
    if a.list:
        for f in sorted(os.listdir(BACKUPS)) if os.path.isdir(BACKUPS) else []:
            p = os.path.join(BACKUPS, f)
            print(f"{f}  {os.path.getsize(p) // 1024} KB")
        print("Restaurar un archivo: tar -xzf memory/.backups/<backup> -C /tmp/restore memory/<archivo> y copiarlo tras revisarlo.")
        return
    r = backup(keep=a.keep, if_older_than_hours=a.if_older_than_hours)
    if r is None:
        print("backup reciente, no hace falta otro")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("add-rule", help="agregar regla (id asignado bajo lock); --supersedes para reemplazar otra")
    s.add_argument("--rule", required=True)
    s.add_argument("--type", required=True, help="avoid|prioritize|verify")
    s.add_argument("--ticket", required=True, help="ticket de origen (o un id libre, ej. SESSION-2026-10-30)")
    s.add_argument("--tags", default="", help="repos/tags separados por coma; vacío = universal")
    s.add_argument("--source", default="retrospective", help="live_correction (0.9) | retrospective (0.6)")
    s.add_argument("--confidence", type=float)
    s.add_argument("--supersedes", help="id de la regla que esta reemplaza")
    s.set_defaults(fn=cmd_add_rule)

    s = sp.add_parser("similar-rules", help="pre-check de dedup: candidatas parecidas a un texto")
    s.add_argument("--rule", required=True)
    s.add_argument("--tags", default="")
    s.add_argument("--top", type=int, default=3)
    s.add_argument("--threshold", type=float, default=0.2)
    s.set_defaults(fn=cmd_similar_rules)

    s = sp.add_parser("reinforce-rule", help="+0.1 confidence, reinforced_count++, last_seen=hoy")
    s.add_argument("id")
    s.add_argument("--ticket")
    s.add_argument("--tags", help="tags extra a sumar a la regla")
    s.set_defaults(fn=cmd_reinforce_rule)

    s = sp.add_parser("set-rule", help="cambiar status/tags/confidence de una regla")
    s.add_argument("id")
    s.add_argument("--status", choices=["active", "superseded", "archived"])
    s.add_argument("--tags")
    s.add_argument("--confidence", type=float)
    s.add_argument("--superseded-by")
    s.set_defaults(fn=cmd_set_rule)

    s = sp.add_parser("upsert-pattern")
    s.add_argument("--pattern", required=True)
    s.add_argument("--type", required=True, choices=["error", "success"])
    s.add_argument("--ticket", required=True)
    s.add_argument("--tags", default="")
    s.set_defaults(fn=cmd_upsert_pattern)

    s = sp.add_parser("add-decision")
    s.add_argument("--context", required=True)
    s.add_argument("--decision", required=True)
    s.add_argument("--outcome", required=True)
    s.add_argument("--score", type=float, required=True)
    s.add_argument("--tags", default="")
    s.set_defaults(fn=cmd_add_decision)

    s = sp.add_parser("add-mistake")
    s.add_argument("--ticket", required=True)
    s.add_argument("--description", required=True)
    s.add_argument("--context", default="")
    s.add_argument("--tags", default="")
    s.set_defaults(fn=cmd_add_mistake)

    s = sp.add_parser("ticket-learning")
    s.add_argument("ticket")
    s.add_argument("--summary")
    s.add_argument("--learning")
    s.set_defaults(fn=cmd_ticket_learning)

    s = sp.add_parser("write", help="escritura atómica de un JSON leído de stdin, path relativo a memory/")
    s.add_argument("path")
    s.set_defaults(fn=cmd_write)

    sp.add_parser("validate", help="valida que todo memory/*.json parsee y cumpla el schema").set_defaults(fn=cmd_validate)
    sp.add_parser("stats").set_defaults(fn=cmd_stats)

    s = sp.add_parser("backup", help="tar.gz de memory/ en memory/.backups (rota)")
    s.add_argument("--keep", type=int, default=14)
    s.add_argument("--if-older-than-hours", type=float)
    s.add_argument("--list", action="store_true")
    s.set_defaults(fn=cmd_backup)

    a = p.parse_args()
    try:
        a.fn(a)
    except MemoryCorrupt as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except ValueError as e:
        print(f"ERROR de validación: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
