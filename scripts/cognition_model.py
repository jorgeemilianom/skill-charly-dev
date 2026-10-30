#!/usr/bin/env python3
"""Schema, validation and pure operations for the agent's own state: memory/cognition.json.

This is Charly's model of itself — separate from memory/user_profile.json (the model of the user).
One document holds the four related collections so that operations touching several of them (a
belief revision that supersedes another, a goal update that checks dependencies) are a single
transaction under memory_store.py's lock:

  agent     name, operational purpose, recurring blind spots (from scripts/self_model.py --refresh)
  episodes  experiences: what was about to be done, a binary falsifiable prediction with its
            probability, the remembered episodes that actually influenced the decision, and — once
            the result is known — an evaluation (observation / interpretation / adjustment /
            evidence / outcome true|false|null). Evaluations are immutable: a correction is a new
            episode with `corrects` pointing at the old one.
  goals     persistent objectives with next action, verifiable success criterion, priority 1-5
            (1 = highest), dependencies (no cycles), optional activation date (when to start
            reviewing it — not a deadline) and a full change history.
  beliefs   evidence-backed hypotheses about capabilities, limitations and strategies. Confidence
            is capped by the evaluated episodes cited, never by how often the agent repeats itself.

Nothing in this module does I/O: memory_store.py loads the document under its lock, calls
apply(op, doc, payload), validates the result with validate_doc() and replaces the file atomically.
"""
import datetime
import re

SCHEMA_VERSION = 1
FILE = "cognition.json"

EPISODE_STATUSES = {"pending", "evaluated"}
GOAL_STATUSES = {"active", "blocked", "paused", "done", "abandoned"}
CLOSED_GOAL = {"done", "abandoned"}
BELIEF_TYPES = {"capability", "limitation", "strategy"}
BELIEF_STATUSES = {"active", "superseded", "archived"}

MAX_TEXT = 1200       # per free-text field — an experience is a summary, not a transcript
MAX_LIST = 20
MAX_REF = 300
# Heuristics only — a cheap guard against pasting secrets into persistent memory, not a scanner.
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)\b(password|passwd|contrase(ñ|n)a|secret|api[_-]?key|token)\s*[:=]\s*\S{6,}"),
]

DEFAULT_PURPOSE = ("Agente de desarrollo y operaciones del harness: llevar tickets a PR y atender "
                   "requerimientos de clientes, aprendiendo de los resultados de sus propias decisiones.")


class CognitionError(ValueError):
    """Invalid operation or payload — nothing is written."""


class IncompatibleSchema(Exception):
    """The file was written by a newer/unknown schema — never touched."""


# ---------------------------------------------------------------- helpers

def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def parse_ts(value, field):
    if not isinstance(value, str):
        raise CognitionError(f"{field}: se esperaba una fecha ISO 8601 con zona horaria")
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CognitionError(f"{field}: fecha inválida {value!r}")
    if dt.tzinfo is None:
        raise CognitionError(f"{field}: la fecha {value!r} no tiene zona horaria (ej. 2026-11-01T09:00:00-03:00)")
    return dt


def empty_doc(legacy_profile=None):
    doc = {
        "schema_version": SCHEMA_VERSION,
        "agent": {"name": "Charly", "purpose": DEFAULT_PURPOSE, "blind_spots": [],
                  "blind_spots_updated_at": None, "migrated_from": None},
        "episodes": [], "goals": [], "beliefs": [],
    }
    import_legacy(doc, legacy_profile)
    return doc


def import_legacy(doc, legacy_profile):
    """Copy user_profile.self_model into agent (idempotent; the profile itself is never modified)."""
    agent = doc["agent"]
    if agent.get("migrated_from") or not isinstance(legacy_profile, dict):
        return False
    sm = legacy_profile.get("self_model")
    if not isinstance(sm, dict):
        return False
    spots = [s for s in sm.get("top_blind_spots") or [] if isinstance(s, dict) and s.get("statement")]
    if not agent["blind_spots"]:
        agent["blind_spots"] = spots
        agent["blind_spots_updated_at"] = sm.get("last_computed")
    agent["migrated_from"] = {"source": "user_profile.json:self_model", "at": now(),
                              "legacy_last_computed": sm.get("last_computed"), "imported": len(spots)}
    return True


def check_version(doc):
    if not isinstance(doc, dict) or "schema_version" not in doc:
        raise IncompatibleSchema("cognition.json sin schema_version")
    v = doc["schema_version"]
    if v != SCHEMA_VERSION:
        raise IncompatibleSchema(
            f"cognition.json tiene schema_version={v!r}; este código entiende {SCHEMA_VERSION}. "
            f"No se escribe nada: actualizar el harness o restaurar un backup.")


def _text(v, field, required=True, limit=MAX_TEXT):
    if v is None and not required:
        return None
    if not isinstance(v, str) or (required and not v.strip()):
        raise CognitionError(f"{field}: texto requerido")
    v = v.strip()
    if len(v) > limit:
        raise CognitionError(f"{field}: {len(v)} caracteres (máx {limit}) — resumir, no transcribir")
    for p in SECRET_PATTERNS:
        if p.search(v):
            raise CognitionError(f"{field}: parece contener un secreto — no se guardan credenciales en memoria")
    return v


def _str_list(v, field, item_limit=MAX_REF, allow_empty=True):
    if v is None:
        v = []
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        raise CognitionError(f"{field}: se esperaba una lista de textos")
    if len(v) > MAX_LIST:
        raise CognitionError(f"{field}: máximo {MAX_LIST} elementos")
    if not allow_empty and not v:
        raise CognitionError(f"{field}: no puede estar vacío")
    out = []
    for i, x in enumerate(v):
        x = _text(x, f"{field}[{i}]", limit=item_limit)
        if x not in out:
            out.append(x)
    return out


def _prob(v, field):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.0 <= float(v) <= 1.0:
        raise CognitionError(f"{field}: probabilidad entre 0 y 1")
    return round(float(v), 4)


def _fields(payload, required, optional, op):
    if not isinstance(payload, dict):
        raise CognitionError(f"{op}: se esperaba un objeto JSON")
    unknown = set(payload) - set(required) - set(optional)
    if unknown:
        raise CognitionError(f"{op}: campos desconocidos {sorted(unknown)}; válidos: {sorted(set(required) | set(optional))}")
    missing = [f for f in required if f not in payload]
    if missing:
        raise CognitionError(f"{op}: faltan campos {missing}")


def _next_id(items, prefix):
    n = 0
    for it in items:
        m = re.fullmatch(rf"{prefix}-(\d+)", str(it.get("id", "")))
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}-{n + 1:04d}"


def _index(items):
    return {it["id"]: it for it in items}


def _find(items, id_, kind):
    for it in items:
        if it["id"] == id_:
            return it
    raise CognitionError(f"no existe {kind} {id_!r}")


# ---------------------------------------------------------------- episodes

def op_experience(doc, p):
    _fields(p, ["context", "action", "prediction", "probability"],
            ["tags", "recalled", "corrects", "ticket"], "experience")
    eps = doc["episodes"]
    by_id = _index(eps)
    recalled = _str_list(p.get("recalled"), "recalled")
    for r in recalled:
        if r not in by_id:
            raise CognitionError(f"recalled: no existe el episodio {r}")
    corrects = p.get("corrects")
    if corrects is not None:
        if corrects not in by_id:
            raise CognitionError(f"corrects: no existe el episodio {corrects}")
        if by_id[corrects]["status"] != "evaluated":
            raise CognitionError(f"corrects: {corrects} sigue pendiente — evaluarlo, no corregirlo")
    ep = {
        "id": _next_id(eps, "ep"),
        "created_at": now(),
        "status": "pending",
        "ticket": _text(p.get("ticket"), "ticket", required=False, limit=60),
        "tags": _str_list(p.get("tags"), "tags", item_limit=80),
        "context": _text(p["context"], "context"),
        "action": _text(p["action"], "action"),
        "prediction": _text(p["prediction"], "prediction", limit=400),
        "probability": _prob(p["probability"], "probability"),
        "recalled": recalled,
        "corrects": corrects,
        "evaluation": None,
    }
    eps.append(ep)
    return {"id": ep["id"], "status": "pending"}


def op_evaluate(doc, p):
    _fields(p, ["id", "observation", "outcome"], ["interpretation", "adjustment", "evidence"], "evaluate")
    ep = _find(doc["episodes"], p["id"], "episodio")
    if ep["status"] == "evaluated":
        raise CognitionError(f"{ep['id']} ya fue evaluado y las evaluaciones no se editan: registrar "
                             f"otro episodio con \"corrects\": \"{ep['id']}\"")
    outcome = p["outcome"]
    if outcome not in (True, False, None):
        raise CognitionError("outcome: true, false o null (null = indeterminado)")
    evidence = _str_list(p.get("evidence"), "evidence")
    if outcome is not None and not evidence:
        raise CognitionError("evidence: un resultado determinado (true/false) necesita al menos una referencia comprobable")
    ts = now()
    if parse_ts(ts, "now") < parse_ts(ep["created_at"], "created_at"):
        raise CognitionError("la evaluación no puede ser anterior a la predicción")
    ep["evaluation"] = {
        "evaluated_at": ts,
        "observation": _text(p["observation"], "observation"),
        "interpretation": _text(p.get("interpretation"), "interpretation", required=False),
        "adjustment": _text(p.get("adjustment"), "adjustment", required=False),
        "evidence": evidence,
        "outcome": outcome,
    }
    ep["status"] = "evaluated"
    return {"id": ep["id"], "status": "evaluated", "outcome": outcome}


# ---------------------------------------------------------------- goals

def _check_deps(goals, goal_id, deps):
    by_id = _index(goals)
    for d in deps:
        if d == goal_id:
            raise CognitionError(f"depends_on: {goal_id} no puede depender de sí mismo")
        if d not in by_id:
            raise CognitionError(f"depends_on: no existe el objetivo {d}")
    graph = {g["id"]: list(g.get("depends_on") or []) for g in goals}
    graph[goal_id] = list(deps)
    # DFS from goal_id: reaching goal_id again means a cycle
    stack, seen = list(deps), set()
    while stack:
        cur = stack.pop()
        if cur == goal_id:
            raise CognitionError(f"depends_on: crearía un ciclo que vuelve a {goal_id}")
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.get(cur, []))


def _goal_fields(p, g, creating):
    if "title" in p or creating:
        g["title"] = _text(p.get("title"), "title", limit=200)
    if "reason" in p or creating:
        g["reason"] = _text(p.get("reason"), "reason")
    if "next_action" in p or creating:
        g["next_action"] = _text(p.get("next_action"), "next_action", limit=400)
    if "success_criterion" in p or creating:
        g["success_criterion"] = _text(p.get("success_criterion"), "success_criterion", limit=400)
    if "priority" in p or creating:
        pr = p.get("priority", 3)
        if isinstance(pr, bool) or not isinstance(pr, int) or not 1 <= pr <= 5:
            raise CognitionError("priority: entero de 1 (máxima) a 5")
        g["priority"] = pr
    if "tags" in p or creating:
        g["tags"] = _str_list(p.get("tags"), "tags", item_limit=80)
    if "activate_at" in p or creating:
        a = p.get("activate_at")
        if a is not None:
            parse_ts(a, "activate_at")
        g["activate_at"] = a


def op_goal(doc, p):
    _fields(p, ["title", "reason", "next_action", "success_criterion"],
            ["priority", "tags", "depends_on", "activate_at", "status", "blocked_reason"], "goal")
    goals = doc["goals"]
    gid = _next_id(goals, "goal")
    g = {"id": gid}
    _goal_fields(p, g, creating=True)
    status = p.get("status", "active")
    if status not in {"active", "blocked", "paused"}:
        raise CognitionError("status inicial: active, blocked o paused")
    deps = _str_list(p.get("depends_on"), "depends_on", item_limit=40)
    _check_deps(goals, gid, deps)
    blocked_reason = _text(p.get("blocked_reason"), "blocked_reason", required=False)
    if status == "blocked" and not blocked_reason:
        raise CognitionError("blocked_reason: obligatorio para un objetivo bloqueado")
    ts = now()
    g.update({"depends_on": deps, "status": status, "blocked_reason": blocked_reason if status == "blocked" else None,
              "created_at": ts, "updated_at": ts,
              "history": [{"at": ts, "from": None, "to": status, "note": "creado", "evidence": []}]})
    goals.append(g)
    return {"id": gid, "status": status}


def op_update_goal(doc, p):
    _fields(p, ["id"], ["status", "note", "evidence", "reopen", "blocked_reason", "title", "reason",
                        "next_action", "success_criterion", "priority", "tags", "depends_on", "activate_at"],
            "update-goal")
    goals = doc["goals"]
    g = _find(goals, p["id"], "objetivo")
    old_status = g["status"]
    new_status = p.get("status", old_status)
    if new_status not in GOAL_STATUSES:
        raise CognitionError(f"status: uno de {sorted(GOAL_STATUSES)}")
    reopen = p.get("reopen", False)
    if not isinstance(reopen, bool):
        raise CognitionError("reopen: booleano")
    if old_status in CLOSED_GOAL and set(p) - {"id", "note", "reopen", "status"}:
        if not (reopen and new_status not in CLOSED_GOAL):
            raise CognitionError(f"{g['id']} está {old_status}: para cambiarlo, reabrirlo explícitamente con "
                                 f"\"reopen\": true y un status abierto")
    if old_status in CLOSED_GOAL and new_status != old_status and not reopen:
        raise CognitionError(f"{g['id']} está {old_status}: reabrir requiere \"reopen\": true")
    if reopen and old_status not in CLOSED_GOAL:
        raise CognitionError("reopen: solo aplica a objetivos done o abandoned")
    if reopen and new_status in CLOSED_GOAL:
        raise CognitionError("reopen: indicar el status abierto al que vuelve (active, blocked o paused)")
    evidence = _str_list(p.get("evidence"), "evidence")
    if new_status == "done" and old_status != "done" and not evidence:
        raise CognitionError("evidence: marcar un objetivo como done exige evidencia comprobable de su criterio de éxito")
    before = {k: g.get(k) for k in ("title", "reason", "next_action", "success_criterion", "priority",
                                    "tags", "depends_on", "activate_at", "blocked_reason")}
    _goal_fields(p, g, creating=False)
    if "depends_on" in p:
        deps = _str_list(p.get("depends_on"), "depends_on", item_limit=40)
        _check_deps(goals, g["id"], deps)
        g["depends_on"] = deps
    if new_status == "blocked":
        reason = _text(p.get("blocked_reason", g.get("blocked_reason")), "blocked_reason")
        g["blocked_reason"] = reason
    elif "blocked_reason" in p:
        raise CognitionError("blocked_reason: solo con status blocked")
    else:
        g["blocked_reason"] = None
    g["status"] = new_status
    changes = {k: {"from": before[k], "to": g.get(k)} for k in before if before[k] != g.get(k)}
    if new_status == old_status and not changes and not p.get("note"):
        raise CognitionError("update-goal: no hay cambios")
    ts = now()
    g["updated_at"] = ts
    g["history"].append({"at": ts, "from": old_status, "to": new_status,
                         "note": _text(p.get("note"), "note", required=False) or ("reabierto" if reopen else None),
                         "evidence": evidence, "changes": changes})
    return {"id": g["id"], "status": new_status, "changes": sorted(changes)}


# ---------------------------------------------------------------- beliefs

def confidence_cap(n_support, n_counter):
    """Laplace-smoothed upper bound on confidence from evaluated evidence: (s+1)/(s+c+2).
    Re-stating the same belief adds nothing; counter-evidence pulls the bound down."""
    return round((n_support + 1) / (n_support + n_counter + 2), 4)


def op_belief(doc, p):
    _fields(p, ["type", "claim", "confidence", "evidence"], ["scope_tags", "counter_evidence", "supersedes"], "belief")
    if p["type"] not in BELIEF_TYPES:
        raise CognitionError(f"type: uno de {sorted(BELIEF_TYPES)}")
    by_ep = _index(doc["episodes"])

    def evaluated_refs(field, refs):
        for r in refs:
            ep = by_ep.get(r)
            if ep is None:
                raise CognitionError(f"{field}: no existe el episodio {r}")
            if ep["status"] != "evaluated" or ep["evaluation"]["outcome"] is None:
                raise CognitionError(f"{field}: {r} no tiene un resultado determinado (pendiente o null) — no es evidencia")
        return refs

    support = evaluated_refs("evidence", _str_list(p["evidence"], "evidence", item_limit=40, allow_empty=False))
    counter = evaluated_refs("counter_evidence", _str_list(p.get("counter_evidence"), "counter_evidence", item_limit=40))
    if set(support) & set(counter):
        raise CognitionError("un episodio no puede ser evidencia y contraevidencia a la vez")
    if p["type"] == "capability" and len(support) < 2:
        raise CognitionError("capability: hacen falta al menos 2 episodios evaluados que la sostengan — "
                             "un único caso no generaliza una capacidad (registrarla como strategy acotada o esperar más evidencia)")
    conf = _prob(p["confidence"], "confidence")
    cap = confidence_cap(len(support), len(counter))
    if conf > cap:
        raise CognitionError(f"confidence {conf} supera el máximo que permite la evidencia ({cap} con "
                             f"{len(support)} a favor y {len(counter)} en contra)")
    beliefs = doc["beliefs"]
    old = None
    if p.get("supersedes"):
        old = _find(beliefs, p["supersedes"], "creencia")
        if old["status"] != "active":
            raise CognitionError(f"supersedes: {old['id']} no está activa ({old['status']})")
    ts = now()
    b = {"id": _next_id(beliefs, "bel"), "type": p["type"], "claim": _text(p["claim"], "claim", limit=500),
         "scope_tags": _str_list(p.get("scope_tags"), "scope_tags", item_limit=80),
         "confidence": conf, "evidence": support, "counter_evidence": counter, "status": "active",
         "supersedes": old["id"] if old else None, "superseded_by": None,
         "created_at": ts, "updated_at": ts, "archive_reason": None}
    beliefs.append(b)
    if old:
        old["status"] = "superseded"
        old["superseded_by"] = b["id"]
        old["updated_at"] = ts
    return {"id": b["id"], "confidence_cap": cap, "superseded": old["id"] if old else None}


def op_archive_belief(doc, p):
    _fields(p, ["id", "reason"], [], "archive-belief")
    b = _find(doc["beliefs"], p["id"], "creencia")
    if b["status"] != "active":
        raise CognitionError(f"{b['id']} no está activa ({b['status']})")
    b["status"] = "archived"
    b["archive_reason"] = _text(p["reason"], "reason")
    b["updated_at"] = now()
    return {"id": b["id"], "status": "archived"}


# ---------------------------------------------------------------- agent

def op_set_blind_spots(doc, p):
    _fields(p, ["blind_spots"], ["computed_at"], "set-blind-spots")
    spots = p["blind_spots"]
    if not isinstance(spots, list) or not all(isinstance(s, dict) and isinstance(s.get("statement"), str) for s in spots):
        raise CognitionError("blind_spots: lista de objetos con 'statement'")
    doc["agent"]["blind_spots"] = spots[:10]
    doc["agent"]["blind_spots_updated_at"] = p.get("computed_at") or now()
    return {"blind_spots": len(spots[:10])}


def op_set_agent(doc, p):
    _fields(p, [], ["name", "purpose"], "set-agent")
    if "name" in p:
        doc["agent"]["name"] = _text(p["name"], "name", limit=60)
    if "purpose" in p:
        doc["agent"]["purpose"] = _text(p["purpose"], "purpose", limit=500)
    return {"name": doc["agent"]["name"]}


OPS = {
    "experience": op_experience,
    "evaluate": op_evaluate,
    "goal": op_goal,
    "update-goal": op_update_goal,
    "belief": op_belief,
    "archive-belief": op_archive_belief,
    "set-blind-spots": op_set_blind_spots,
    "set-agent": op_set_agent,
}


def apply(op, doc, payload):
    if op not in OPS:
        raise CognitionError(f"operación desconocida {op!r}; válidas: init, {', '.join(sorted(OPS))}")
    return OPS[op](doc, payload)


# ---------------------------------------------------------------- whole-document validation

def validate_doc(doc):
    """Full structural check, run before every write and by `memory_store.py validate`."""
    check_version(doc)
    for k in ("agent", "episodes", "goals", "beliefs"):
        if k not in doc:
            raise CognitionError(f"falta '{k}'")
    if not isinstance(doc["agent"], dict) or not isinstance(doc["agent"].get("blind_spots"), list):
        raise CognitionError("agent: estructura inválida")
    for k in ("episodes", "goals", "beliefs"):
        if not isinstance(doc[k], list):
            raise CognitionError(f"{k}: debe ser una lista")
        ids = [x.get("id") for x in doc[k] if isinstance(x, dict)]
        if len(ids) != len(doc[k]) or len(set(ids)) != len(ids) or None in ids:
            raise CognitionError(f"{k}: ids faltantes o duplicados")

    eps = _index(doc["episodes"])
    for e in doc["episodes"]:
        if e.get("status") not in EPISODE_STATUSES:
            raise CognitionError(f"{e['id']}: status inválido")
        _prob(e.get("probability"), f"{e['id']}.probability")
        parse_ts(e.get("created_at"), f"{e['id']}.created_at")
        for r in e.get("recalled") or []:
            if r not in eps or r == e["id"]:
                raise CognitionError(f"{e['id']}.recalled: referencia inválida {r}")
        if e.get("corrects") and e["corrects"] not in eps:
            raise CognitionError(f"{e['id']}.corrects: referencia inválida")
        ev = e.get("evaluation")
        if (e["status"] == "evaluated") != isinstance(ev, dict):
            raise CognitionError(f"{e['id']}: status y evaluation no coinciden")
        if ev and ev.get("outcome") not in (True, False, None):
            raise CognitionError(f"{e['id']}.evaluation.outcome inválido")

    goals = _index(doc["goals"])
    for g in doc["goals"]:
        if g.get("status") not in GOAL_STATUSES:
            raise CognitionError(f"{g['id']}: status inválido")
        if not isinstance(g.get("priority"), int) or not 1 <= g["priority"] <= 5:
            raise CognitionError(f"{g['id']}: priority inválida")
        if g.get("activate_at"):
            parse_ts(g["activate_at"], f"{g['id']}.activate_at")
        if g["status"] == "blocked" and not g.get("blocked_reason"):
            raise CognitionError(f"{g['id']}: bloqueado sin blocked_reason")
        if not isinstance(g.get("history"), list) or not g["history"]:
            raise CognitionError(f"{g['id']}: sin historial")
        for d in g.get("depends_on") or []:
            if d not in goals:
                raise CognitionError(f"{g['id']}.depends_on: referencia inválida {d}")
    # cycle check over the whole graph
    state = {}

    def visit(n):
        if state.get(n) == 1:
            raise CognitionError(f"ciclo de dependencias en {n}")
        if state.get(n) == 2:
            return
        state[n] = 1
        for d in goals[n].get("depends_on") or []:
            visit(d)
        state[n] = 2
    for gid in goals:
        visit(gid)

    bels = _index(doc["beliefs"])
    for b in doc["beliefs"]:
        if b.get("type") not in BELIEF_TYPES or b.get("status") not in BELIEF_STATUSES:
            raise CognitionError(f"{b['id']}: type/status inválido")
        _prob(b.get("confidence"), f"{b['id']}.confidence")
        for r in (b.get("evidence") or []) + (b.get("counter_evidence") or []):
            if r not in eps:
                raise CognitionError(f"{b['id']}: evidencia inexistente {r}")
        for k in ("supersedes", "superseded_by"):
            if b.get(k) and b[k] not in bels:
                raise CognitionError(f"{b['id']}.{k}: referencia inválida")
        if b["status"] == "superseded" and not b.get("superseded_by"):
            raise CognitionError(f"{b['id']}: superseded sin superseded_by")
